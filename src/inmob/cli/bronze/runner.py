"""Bronze runner used by the CLI."""

from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import uuid4

from loguru import logger

from inmob.cli.bronze.config import DEFAULT_PROPERTY_LIMIT, DEFAULT_SOURCES_CONFIG
from inmob.cli.bronze.store import PropertyFolderRawArtifactStore
from inmob.bronze.contracts import BronzeRunContext, BronzeTarget, PolitenessProfile
from inmob.bronze.traffic import TrafficSnapshot


class BronzeError(ValueError):
    """Raised when a Bronze request is invalid."""


@dataclass(frozen=True)
class BronzeRunner:
    """Runs Bronze raw scraping for one or many configured sources."""

    sources_config: dict[str, dict[str, Any]] = field(default_factory=lambda: DEFAULT_SOURCES_CONFIG)
    default_limit: int = DEFAULT_PROPERTY_LIMIT

    def run(
        self,
        *,
        source: str,
        limit: int | None,
        pages: int | None,
        target_dir: Path,
        config_path: Path | None = None,
    ) -> dict[str, int]:
        effective_limit = self._effective_limit(limit=limit, pages=pages)
        self._validate_window(limit=effective_limit, pages=pages)
        normalized_pages = None if effective_limit is not None else pages
        overrides = self._load_overrides(config_path)
        sources_to_scrape = self._select_sources(source)

        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Starting Bronze target_dir={} source_count={} sources={}",
            str(target_dir.resolve()),
            len(sources_to_scrape),
            sorted(sources_to_scrape),
        )
        if effective_limit is not None:
            logger.info("Limits up to {} properties per source", effective_limit)
        else:
            logger.info("Limits up to {} index pages per source", normalized_pages)

        results: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=len(sources_to_scrape)) as executor:
            future_to_source = {
                executor.submit(
                    self.scrape_source,
                    source_id=source_id,
                    source_cfg=cfg,
                    limit=effective_limit,
                    pages=normalized_pages,
                    target_dir=target_dir,
                    custom_criteria_args=overrides.get(source_id),
                ): source_id
                for source_id, cfg in sources_to_scrape.items()
            }

            for future in as_completed(future_to_source):
                source_id = future_to_source[future]
                try:
                    results[source_id] = future.result()
                except Exception as exc:
                    logger.bind(source_id=source_id).exception(
                        "Worker crashed with exception={}",
                        exc,
                    )
                    results[source_id] = 0

        logger.info("Bronze job summary start")
        for source_id, success_count in sorted(results.items()):
            logger.bind(source_id=source_id).info(
                "Bronze source summary success_count={}",
                success_count,
            )
        return results

    def scrape_source(
        self,
        *,
        source_id: str,
        source_cfg: dict[str, Any],
        limit: int | None,
        pages: int | None,
        target_dir: Path,
        custom_criteria_args: dict[str, Any] | None = None,
    ) -> int:
        """Scrape a single source and return successfully stored listing count."""
        task_started_at = perf_counter()
        source_logger = logger.bind(source_id=source_id)
        target_desc = f"limit: {limit}" if limit is not None else f"pages: {pages}"
        source_logger.info("Starting scraper task {}", target_desc)

        source_class = source_cfg["source_class"]
        criteria_class = source_cfg["criteria_class"]
        page_index_starts_at = source_cfg["page_index_starts_at"]
        search_targets_method = source_cfg["search_targets_method"]

        criteria_args = dict(source_cfg["default_criteria"])
        if custom_criteria_args:
            criteria_args.update(custom_criteria_args)

        criteria = criteria_class(**criteria_args)
        source_logger.debug(
            "Built search criteria class={} args={}",
            criteria_class.__name__,
            criteria_args,
        )

        pages_range = self._page_range(
            page_index_starts_at=page_index_starts_at,
            page_size=criteria.page_size,
            limit=limit,
            pages=pages,
        )
        source_logger.info("Target page range={} page_size={}", pages_range, criteria.page_size)

        run_id = f"cli-run-{source_id}-{uuid4().hex[:8]}"
        context = BronzeRunContext(run_id=run_id, requested_at=datetime.now(UTC))
        source_logger = source_logger.bind(run_id=run_id)
        source_logger.info(
            "Created Bronze run requested_at={} target_dir={}",
            context.requested_at.isoformat(),
            str(target_dir),
        )

        target_builder = getattr(source_class, search_targets_method)
        search_targets = target_builder(criteria=criteria, pages=pages_range)
        source_logger.info(
            "Planned search targets count={} builder={}",
            len(search_targets),
            search_targets_method,
        )

        discovered_by_uri = self._discover_listing_targets(
            source_class=source_class,
            search_targets=search_targets,
            context=context,
            source_logger=source_logger,
        )

        if limit is not None:
            listing_targets = tuple(discovered_by_uri.values())[:limit]
        else:
            listing_targets = tuple(discovered_by_uri.values())

        source_logger.info(
            "Unique listings discovered total={} selected_for_detail_fetch={}",
            len(discovered_by_uri),
            len(listing_targets),
        )

        if not listing_targets:
            source_logger.warning("Scraper finished with no listing detail URIs discovered")
            return 0

        success_count = self._fetch_and_store_listing_details(
            source_class=source_class,
            listing_targets=listing_targets,
            context=context,
            source_logger=source_logger,
            target_dir=target_dir,
        )
        source_logger.info(
            "Scraper task finished success_count={} selected_count={} elapsed_seconds={}",
            success_count,
            len(listing_targets),
            round(perf_counter() - task_started_at, 3),
        )
        return success_count

    def _discover_listing_targets(
        self,
        *,
        source_class: Any,
        search_targets: tuple[BronzeTarget, ...],
        context: BronzeRunContext,
        source_logger: Any,
    ) -> dict[str, BronzeTarget]:
        discovered_by_uri: dict[str, BronzeTarget] = {}
        with source_class(targets=search_targets) as search_source:
            search_source.reset_traffic_stats()
            _log_traffic_policy(source_logger, search_source.definition.politeness)
            for request in search_source.plan_requests(context):
                request_logger = source_logger.bind(
                    target_id=request.target.target_id,
                    target_kind=request.target.kind.value,
                )
                try:
                    page_started_at = perf_counter()
                    request_logger.info("Fetching search page uri={}", request.target.uri)
                    response = search_source.fetch(request)
                    if response.status_code not in (200, 201):
                        request_logger.warning(
                            "Search page returned unexpected status_code={} uri={}",
                            response.status_code,
                            request.target.uri,
                        )
                        continue

                    page_targets = search_source.discover_listing_targets(response.payload)
                    request_logger.info(
                        "Discovered listings on search page count={} elapsed_seconds={}",
                        len(page_targets),
                        round(perf_counter() - page_started_at, 3),
                    )
                    for target in page_targets:
                        discovered_by_uri.setdefault(target.uri, target)

                except Exception:
                    request_logger.exception(
                        "Exception while fetching or parsing search page uri={}",
                        request.target.uri,
                    )

            _log_traffic_summary(
                source_logger,
                search_source.traffic_snapshot(),
                phase="search",
            )
        return discovered_by_uri

    def _fetch_and_store_listing_details(
        self,
        *,
        source_class: Any,
        listing_targets: tuple[BronzeTarget, ...],
        context: BronzeRunContext,
        source_logger: Any,
        target_dir: Path,
    ) -> int:
        store = PropertyFolderRawArtifactStore(target_dir)
        success_count = 0

        with source_class(targets=listing_targets) as listing_source:
            listing_source.reset_traffic_stats()
            for idx, request in enumerate(listing_source.plan_requests(context), start=1):
                request_logger = source_logger.bind(
                    target_id=request.target.target_id,
                    target_kind=request.target.kind.value,
                )
                try:
                    detail_started_at = perf_counter()
                    request_logger.info(
                        "Fetching listing detail index={} total={} uri={}",
                        idx,
                        len(listing_targets),
                        request.target.uri,
                    )
                    response = listing_source.fetch(request)
                    if response.status_code == 200:
                        artifact = store.persist(context=context, response=response)
                        success_count += 1
                        prop_id = artifact.payload_path.parent.name
                        request_logger.info(
                            "Saved listing detail index={} total={} property_id={} "
                            "payload_bytes={} payload_path={} elapsed_seconds={}",
                            idx,
                            len(listing_targets),
                            prop_id,
                            len(response.payload),
                            str(artifact.payload_path),
                            round(perf_counter() - detail_started_at, 3),
                        )
                    else:
                        request_logger.warning(
                            "Listing detail returned unexpected status_code={} "
                            "index={} total={} uri={}",
                            response.status_code,
                            idx,
                            len(listing_targets),
                            request.target.uri,
                        )
                except Exception:
                    request_logger.exception(
                        "Exception while fetching or storing listing detail "
                        "index={} total={} uri={}",
                        idx,
                        len(listing_targets),
                        request.target.uri,
                    )

            _log_traffic_summary(
                source_logger,
                listing_source.traffic_snapshot(),
                phase="listing_detail",
            )
        return success_count

    def _select_sources(self, source: str) -> dict[str, dict[str, Any]]:
        if source.lower() == "all":
            return self.sources_config

        norm_source = source.lower()
        if norm_source not in self.sources_config:
            valid_sources = ", ".join(self.sources_config.keys())
            raise BronzeError(
                f"Unknown source source={source} valid_sources={valid_sources}"
            )
        return {norm_source: self.sources_config[norm_source]}

    def _effective_limit(self, *, limit: int | None, pages: int | None) -> int | None:
        if limit is None and pages is None:
            logger.info("No --limit or --pages provided. Using default limit={}", self.default_limit)
            return self.default_limit
        if limit is not None and pages is not None:
            logger.warning("Both --limit and --pages provided. Prioritizing --limit")
        return limit

    @staticmethod
    def _validate_window(*, limit: int | None, pages: int | None) -> None:
        if limit is not None and limit <= 0:
            raise BronzeError("--limit must be greater than zero")
        if pages is not None and pages <= 0:
            raise BronzeError("--pages must be greater than zero")

    @staticmethod
    def _load_overrides(config_path: Path | None) -> dict[str, Any]:
        if config_path is None:
            return {}
        if not config_path.exists():
            raise BronzeError(f"Config file not found path={config_path}")
        try:
            with config_path.open("r", encoding="utf-8") as f:
                overrides = cast(dict[str, Any], json.load(f))
            logger.info("Loaded custom criteria overrides path={}", config_path)
            return overrides
        except Exception as exc:
            raise BronzeError(f"Error reading config file path={config_path}") from exc

    @staticmethod
    def _page_range(
        *,
        page_index_starts_at: int,
        page_size: int,
        limit: int | None,
        pages: int | None,
    ) -> list[int]:
        if limit is not None:
            pages_needed = max(1, math.ceil(limit / page_size))
        else:
            pages_needed = pages if pages is not None else 1
        return list(range(page_index_starts_at, page_index_starts_at + pages_needed))


def _log_traffic_policy(source_logger: Any, profile: PolitenessProfile) -> None:
    retry = profile.retry
    source_logger.info(
        "Traffic policy requests_per_minute={} burst_size={} retry_policy={} "
        "retry_max_attempts={} retry_initial_delay_seconds={} retry_max_delay_seconds={}",
        profile.requests_per_minute,
        profile.burst_size,
        retry.policy_id,
        retry.max_attempts,
        retry.initial_delay_seconds,
        retry.max_delay_seconds,
    )


def _log_traffic_summary(source_logger: Any, snapshot: TrafficSnapshot, *, phase: str) -> None:
    source_logger.info(
        "Traffic summary phase={} logical_requests={} request_attempts={} responses_returned={} "
        "retries={} transport_errors={} retryable_statuses={} politeness_waits={} "
        "politeness_wait_total_seconds={} retry_waits={} retry_wait_total_seconds={}",
        phase,
        snapshot.logical_requests,
        snapshot.request_attempts,
        snapshot.responses_returned,
        snapshot.retry_count,
        snapshot.transport_error_count,
        snapshot.retryable_status_count,
        snapshot.politeness_wait_count,
        snapshot.politeness_wait_total_seconds,
        snapshot.retry_wait_count,
        snapshot.retry_wait_total_seconds,
    )
