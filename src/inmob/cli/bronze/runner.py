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

from inmob.bronze.artifacts import BronzeArtifactStore
from inmob.bronze.contracts import BronzeRunContext, BronzeTarget, PolitenessProfile, RawArtifact
from inmob.bronze.traffic import DEFAULT_TRAFFIC_PROFILE, TrafficController, TrafficSnapshot
from inmob.cli.bronze.config import DEFAULT_PROPERTY_LIMIT, DEFAULT_SOURCES_CONFIG


class BronzeError(ValueError):
    """Raised when a Bronze request is invalid."""


_EMBEDDED_SEARCH_ITEM_METADATA_KEY = "embedded_payload"


@dataclass
class _SourceRunSummary:
    source_id: str
    run_id: str
    started_at: datetime
    status: str = "running"
    finished_at: datetime | None = None
    search_targets_planned: int = 0
    search_artifacts_persisted: int = 0
    listing_targets_discovered: int = 0
    listing_targets_selected: int = 0
    search_items_persisted: int = 0
    listing_artifacts_persisted: int = 0
    listing_details_succeeded: int = 0
    search_failures: int = 0
    listing_failures: int = 0
    errors: list[str] = field(default_factory=list)

    def finish(self, *, status: str) -> None:
        self.status = status
        self.finished_at = datetime.now(UTC)

    def to_json_ready_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "search_targets_planned": self.search_targets_planned,
            "search_artifacts_persisted": self.search_artifacts_persisted,
            "listing_targets_discovered": self.listing_targets_discovered,
            "listing_targets_selected": self.listing_targets_selected,
            "search_items_persisted": self.search_items_persisted,
            "listing_artifacts_persisted": self.listing_artifacts_persisted,
            "listing_details_succeeded": self.listing_details_succeeded,
            "search_failures": self.search_failures,
            "listing_failures": self.listing_failures,
            "errors": self.errors,
        }


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
        requested_at = datetime.now(UTC)
        run_id = f"cli-run-{requested_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        context = BronzeRunContext(run_id=run_id, requested_at=requested_at)
        run_started_at = perf_counter()

        target_dir.mkdir(parents=True, exist_ok=True)
        store = BronzeArtifactStore(target_dir)

        logger.info(
            "Starting Bronze run_id={} target_dir={} source_count={} sources={}",
            context.run_id,
            str(target_dir.resolve()),
            len(sources_to_scrape),
            sorted(sources_to_scrape),
        )
        if effective_limit is not None:
            logger.info("Limits up to {} listing targets per source", effective_limit)
        else:
            logger.info("Limits up to {} index pages per source", normalized_pages)

        results: dict[str, int] = {}
        summaries: dict[str, _SourceRunSummary] = {}
        with ThreadPoolExecutor(max_workers=len(sources_to_scrape)) as executor:
            future_to_source = {
                executor.submit(
                    self.scrape_source,
                    source_id=source_id,
                    source_cfg=cfg,
                    limit=effective_limit,
                    pages=normalized_pages,
                    target_dir=target_dir,
                    context=context,
                    custom_criteria_args=overrides.get(source_id),
                ): source_id
                for source_id, cfg in sources_to_scrape.items()
            }

            for future in as_completed(future_to_source):
                source_id = future_to_source[future]
                try:
                    summary = future.result()
                    summaries[source_id] = summary
                    results[source_id] = summary.listing_details_succeeded
                except Exception as exc:
                    logger.bind(source_id=source_id).exception(
                        "Worker crashed with exception={}",
                        exc,
                    )
                    summary = _SourceRunSummary(
                        source_id=source_id,
                        run_id=context.run_id,
                        started_at=context.requested_at,
                    )
                    summary.errors.append(f"{type(exc).__name__}: {exc}")
                    summary.finish(status="failed")
                    summaries[source_id] = summary
                    results[source_id] = 0

        manifest_path = _write_run_manifest(
            target_dir=target_dir,
            context=context,
            summaries=summaries,
            selected_source=source,
            limit=limit,
            pages=pages,
            effective_limit=effective_limit,
            elapsed_seconds=perf_counter() - run_started_at,
            config_path=config_path,
            store=store,
        )
        logger.info("Bronze job summary start")
        for source_id, success_count in sorted(results.items()):
            logger.bind(source_id=source_id).info(
                "Bronze source summary success_count={}",
                success_count,
            )
        totals = _run_totals(summaries)
        logger.success(
            "Bronze run finished status={} run_id={} sources={} "
            "search_artifacts={} listings_discovered={} search_items={} "
            "listing_artifacts={} search_failures={} listing_failures={} "
            "manifest_path={}",
            _overall_status(tuple(summaries.values())),
            context.run_id,
            len(summaries),
            totals["search_artifacts_persisted"],
            totals["listing_targets_discovered"],
            totals["search_items_persisted"],
            totals["listing_artifacts_persisted"],
            totals["search_failures"],
            totals["listing_failures"],
            str(manifest_path),
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
        context: BronzeRunContext,
        custom_criteria_args: dict[str, Any] | None = None,
    ) -> _SourceRunSummary:
        """Scrape a single source and return its run summary."""
        task_started_at = perf_counter()
        source_logger = logger.bind(source_id=source_id, run_id=context.run_id)
        store = BronzeArtifactStore(target_dir)
        summary = _SourceRunSummary(
            source_id=source_id,
            run_id=context.run_id,
            started_at=datetime.now(UTC),
        )
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
        summary.search_targets_planned = len(search_targets)

        discovered_by_uri = self._discover_listing_targets(
            source_class=source_class,
            source_cfg=source_cfg,
            search_targets=search_targets,
            context=context,
            source_logger=source_logger,
            store=store,
            summary=summary,
        )

        if limit is not None:
            listing_targets = tuple(discovered_by_uri.values())[:limit]
        else:
            listing_targets = tuple(discovered_by_uri.values())
        summary.listing_targets_discovered = len(discovered_by_uri)
        summary.listing_targets_selected = len(listing_targets)

        source_logger.info(
            "Unique listings discovered total={} selected_for_detail_fetch={}",
            len(discovered_by_uri),
            len(listing_targets),
        )

        if not listing_targets:
            source_logger.warning("Scraper finished with no listing detail URIs discovered")
            summary.finish(status="completed_with_warnings")
            return summary

        if _all_targets_are_derived_from_search_payload(listing_targets):
            self._persist_derived_search_items(
                source_id=source_id,
                listing_targets=listing_targets,
                context=context,
                source_logger=source_logger,
                store=store,
                summary=summary,
            )
            summary.finish(
                status=(
                    "completed"
                    if summary.search_failures == 0 and summary.listing_failures == 0
                    else "completed_with_warnings"
                )
            )
            source_logger.info(
                "Skipping listing detail fetch for derived targets selected_count={} "
                "search_items_persisted={} reason=already_present_in_search_payload",
                len(listing_targets),
                summary.search_items_persisted,
            )
            source_logger.info(
                "Scraper task finished success_count={} selected_count={} "
                "elapsed_seconds={}",
                summary.listing_details_succeeded,
                len(listing_targets),
                round(perf_counter() - task_started_at, 3),
            )
            return summary

        self._fetch_and_store_listing_details(
            source_class=source_class,
            source_cfg=source_cfg,
            listing_targets=listing_targets,
            context=context,
            source_logger=source_logger,
            store=store,
            summary=summary,
        )
        status = (
            "completed"
            if summary.search_failures == 0 and summary.listing_failures == 0
            else "completed_with_warnings"
        )
        summary.finish(status=status)
        source_logger.info(
            "Scraper task finished success_count={} selected_count={} elapsed_seconds={}",
            summary.listing_details_succeeded,
            len(listing_targets),
            round(perf_counter() - task_started_at, 3),
        )
        return summary

    def _discover_listing_targets(
        self,
        *,
        source_class: Any,
        source_cfg: dict[str, Any],
        search_targets: tuple[BronzeTarget, ...],
        context: BronzeRunContext,
        source_logger: Any,
        store: BronzeArtifactStore,
        summary: _SourceRunSummary,
    ) -> dict[str, BronzeTarget]:
        discovered_by_uri: dict[str, BronzeTarget] = {}
        traffic_profile = _traffic_profile_from_config(source_cfg)
        _log_traffic_policy(source_logger, traffic_profile)
        with source_class(
            targets=search_targets,
            traffic_controller=TrafficController(profile=traffic_profile),
        ) as search_source:
            search_source.reset_traffic_stats()
            for request in search_source.plan_requests(context):
                request_logger = source_logger.bind(
                    target_id=request.target.target_id,
                    target_kind=request.target.kind.value,
                )
                try:
                    page_started_at = perf_counter()
                    request_logger.info("Fetching search page uri={}", request.target.uri)
                    response = search_source.fetch(request)
                    artifact = store.persist(context=context, response=response)
                    summary.search_artifacts_persisted += 1
                    if response.status_code not in (200, 201):
                        summary.search_failures += 1
                        request_logger.warning(
                            "Search page returned unexpected status_code={} uri={}",
                            response.status_code,
                            request.target.uri,
                        )
                        continue

                    page_targets = search_source.discover_listing_targets(response.payload)
                    request_logger.info(
                        "Discovered listings on search page count={} artifact_id={} "
                        "elapsed_seconds={}",
                        len(page_targets),
                        artifact.artifact_id,
                        round(perf_counter() - page_started_at, 3),
                    )
                    for target in page_targets:
                        discovered_by_uri.setdefault(
                            target.uri,
                            _with_parent_artifact(target=target, parent=artifact),
                        )

                except Exception as exc:
                    summary.search_failures += 1
                    summary.errors.append(
                        f"search:{request.target.target_id}:{type(exc).__name__}: {exc}"
                    )
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
        source_cfg: dict[str, Any],
        listing_targets: tuple[BronzeTarget, ...],
        context: BronzeRunContext,
        source_logger: Any,
        store: BronzeArtifactStore,
        summary: _SourceRunSummary,
    ) -> None:
        traffic_profile = _traffic_profile_from_config(source_cfg)
        with source_class(
            targets=listing_targets,
            traffic_controller=TrafficController(profile=traffic_profile),
        ) as listing_source:
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
                    artifact = store.persist(context=context, response=response)
                    summary.listing_artifacts_persisted += 1
                    if response.status_code == 200:
                        summary.listing_details_succeeded += 1
                        request_logger.info(
                            "Saved listing detail index={} total={} artifact_id={} "
                            "payload_bytes={} payload_path={} elapsed_seconds={}",
                            idx,
                            len(listing_targets),
                            artifact.artifact_id,
                            len(response.payload),
                            str(artifact.payload_path),
                            round(perf_counter() - detail_started_at, 3),
                        )
                    else:
                        summary.listing_failures += 1
                        request_logger.warning(
                            "Listing detail returned unexpected status_code={} "
                            "index={} total={} uri={}",
                            response.status_code,
                            idx,
                            len(listing_targets),
                            request.target.uri,
                        )
                except Exception as exc:
                    summary.listing_failures += 1
                    summary.errors.append(
                        f"listing:{request.target.target_id}:{type(exc).__name__}: {exc}"
                    )
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
        return None

    def _persist_derived_search_items(
        self,
        *,
        source_id: str,
        listing_targets: tuple[BronzeTarget, ...],
        context: BronzeRunContext,
        source_logger: Any,
        store: BronzeArtifactStore,
        summary: _SourceRunSummary,
    ) -> None:
        for target in listing_targets:
            embedded_payload = target.metadata.get(_EMBEDDED_SEARCH_ITEM_METADATA_KEY)
            if embedded_payload is None:
                source_logger.warning(
                    "Derived target has no embedded search item payload target_id={}",
                    target.target_id,
                )
                continue

            try:
                item_payload = json.loads(embedded_payload)
            except json.JSONDecodeError as exc:
                summary.listing_failures += 1
                summary.errors.append(
                    f"search_item:{target.target_id}:{type(exc).__name__}: {exc}"
                )
                source_logger.warning(
                    "Could not persist malformed embedded search item target_id={} error={}",
                    target.target_id,
                    exc,
                )
                continue

            if not isinstance(item_payload, dict):
                source_logger.warning(
                    "Embedded search item is not a JSON object target_id={} type={}",
                    target.target_id,
                    type(item_payload).__name__,
                )
                continue

            store.persist_search_item(
                context=context,
                source_id=source_id,
                item_id=target.target_id,
                payload=item_payload,
            )
            summary.search_items_persisted += 1

        source_logger.info(
            "Persisted derived search items count={} selected_count={}",
            summary.search_items_persisted,
            len(listing_targets),
        )

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


def _with_parent_artifact(*, target: BronzeTarget, parent: RawArtifact) -> BronzeTarget:
    if target.metadata.get("artifact_origin") != "derived_from_parent_payload":
        return target

    metadata = {
        **target.metadata,
        "parent_artifact_id": parent.artifact_id,
        "parent_target_id": parent.target_id,
        "parent_payload_sha256": parent.payload_sha256,
    }
    return target.model_copy(update={"metadata": metadata})


def _all_targets_are_derived_from_search_payload(targets: tuple[BronzeTarget, ...]) -> bool:
    return all(
        target.metadata.get("artifact_origin") == "derived_from_parent_payload"
        for target in targets
    )


def _run_totals(summaries: dict[str, _SourceRunSummary]) -> dict[str, int]:
    return {
        "search_targets_planned": sum(
            summary.search_targets_planned for summary in summaries.values()
        ),
        "search_artifacts_persisted": sum(
            summary.search_artifacts_persisted for summary in summaries.values()
        ),
        "listing_targets_discovered": sum(
            summary.listing_targets_discovered for summary in summaries.values()
        ),
        "listing_targets_selected": sum(
            summary.listing_targets_selected for summary in summaries.values()
        ),
        "search_items_persisted": sum(
            summary.search_items_persisted for summary in summaries.values()
        ),
        "listing_artifacts_persisted": sum(
            summary.listing_artifacts_persisted for summary in summaries.values()
        ),
        "listing_details_succeeded": sum(
            summary.listing_details_succeeded for summary in summaries.values()
        ),
        "search_failures": sum(summary.search_failures for summary in summaries.values()),
        "listing_failures": sum(summary.listing_failures for summary in summaries.values()),
    }


def _write_run_manifest(
    *,
    target_dir: Path,
    context: BronzeRunContext,
    summaries: dict[str, _SourceRunSummary],
    selected_source: str,
    limit: int | None,
    pages: int | None,
    effective_limit: int | None,
    elapsed_seconds: float,
    config_path: Path | None,
    store: BronzeArtifactStore,
) -> Path:
    manifest_path = store.run_dir(context.run_id) / "manifest.json"
    source_payloads = {
        source_id: summary.to_json_ready_dict()
        for source_id, summary in sorted(summaries.items())
    }
    totals = _run_totals(summaries)
    manifest = {
        "artifact_type": "bronze_run_manifest",
        "run_id": context.run_id,
        "status": _overall_status(tuple(summaries.values())),
        "requested_at": context.requested_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "target_dir": str(target_dir),
        "settings": {
            "source": selected_source,
            "limit": limit,
            "pages": pages,
            "effective_limit": effective_limit,
            "config_path": str(config_path) if config_path is not None else None,
        },
        "totals": totals,
        "sources": source_payloads,
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest_path


def _overall_status(summaries: tuple[_SourceRunSummary, ...]) -> str:
    if not summaries:
        return "failed"
    statuses = {summary.status for summary in summaries}
    if "failed" in statuses:
        return "failed"
    if "completed_with_warnings" in statuses:
        return "completed_with_warnings"
    return "completed"


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _traffic_profile_from_config(source_cfg: dict[str, Any]) -> PolitenessProfile:
    profile = source_cfg.get("traffic_profile", DEFAULT_TRAFFIC_PROFILE)
    if not isinstance(profile, PolitenessProfile):
        raise BronzeError("source traffic_profile must be a PolitenessProfile")
    return profile


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
