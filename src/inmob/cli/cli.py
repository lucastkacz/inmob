"""Typer-based CLI for running the real estate scraping orchestrator."""

from __future__ import annotations

import json
import math
from time import perf_counter
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, as_completed

import typer
from loguru import logger

from inmob.cli.config import DEFAULT_RAW_DATA_DIR, DEFAULT_SOURCES_CONFIG
from inmob.cli.store import PropertyFolderRawArtifactStore
from inmob.ingestion.contracts import IngestionRunContext, IngestionTarget
from inmob.logging import configure_logging


app = typer.Typer(
    help="Inmob Real Estate Scraper Command-Line Interface.",
    no_args_is_help=True,
)


def scrape_source(
    source_id: str,
    source_cfg: dict[str, Any],
    limit: int | None,
    pages: int | None,
    target_dir: Path,
    custom_criteria_args: dict[str, Any] | None = None,
) -> int:
    """Worker function to scrape a single source.

    Returns the number of successfully ingested listing detail files.
    """
    task_started_at = perf_counter()
    source_logger = logger.bind(source_id=source_id)
    target_desc = f"limit: {limit}" if limit is not None else f"pages: {pages}"
    source_logger.info("Starting scraper task {}", target_desc)

    source_class = source_cfg["source_class"]
    criteria_class = source_cfg["criteria_class"]
    page_index_starts_at = source_cfg["page_index_starts_at"]
    search_targets_method = source_cfg["search_targets_method"]

    # Merge criteria args
    criteria_args = dict(source_cfg["default_criteria"])
    if custom_criteria_args:
        criteria_args.update(custom_criteria_args)

    criteria = criteria_class(**criteria_args)
    source_logger.debug(
        "Built search criteria class={} args={}",
        criteria_class.__name__,
        criteria_args,
    )

    # Calculate search pages needed
    page_size = criteria.page_size
    if limit is not None:
        pages_needed = math.ceil(limit / page_size)
        pages_needed = max(1, pages_needed)
    else:
        pages_needed = pages if pages is not None else 1

    pages_range = list(range(page_index_starts_at, page_index_starts_at + pages_needed))

    source_logger.info("Target page range={} page_size={}", pages_range, page_size)

    # Ingestion run context
    run_id = f"cli-run-{source_id}-{uuid4().hex[:8]}"
    context = IngestionRunContext(run_id=run_id, requested_at=datetime.now(UTC))
    source_logger = source_logger.bind(run_id=run_id)
    source_logger.info(
        "Created ingestion run requested_at={} target_dir={}",
        context.requested_at.isoformat(),
        str(target_dir),
    )

    # Retrieve targets
    target_builder = getattr(source_class, search_targets_method)
    search_targets = target_builder(criteria=criteria, pages=pages_range)
    source_logger.info(
        "Planned search targets count={} builder={}",
        len(search_targets),
        search_targets_method,
    )

    discovered_by_uri: dict[str, IngestionTarget] = {}

    # 1. Fetch search pages and discover individual listing target URIs
    with source_class(targets=search_targets) as search_source:
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

    # 2. Slice listing targets (if limit is specified)
    if limit is not None:
        listing_targets = tuple(discovered_by_uri.values())[:limit]
    else:
        listing_targets = tuple(discovered_by_uri.values())

    total_discovered = len(discovered_by_uri)
    source_logger.info(
        "Unique listings discovered total={} selected_for_detail_fetch={}",
        total_discovered,
        len(listing_targets),
    )

    if not listing_targets:
        source_logger.warning("Scraper finished with no listing detail URIs discovered")
        return 0

    # 3. Retrieve and persist each listing detail page sequentially (respecting politeness limits)
    store = PropertyFolderRawArtifactStore(target_dir)
    success_count = 0

    with source_class(targets=listing_targets) as listing_source:
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
                        "Listing detail returned unexpected status_code={} index={} total={} uri={}",
                        response.status_code,
                        idx,
                        len(listing_targets),
                        request.target.uri,
                    )
            except Exception:
                request_logger.exception(
                    "Exception while fetching or storing listing detail index={} total={} uri={}",
                    idx,
                    len(listing_targets),
                    request.target.uri,
                )

    source_logger.info(
        "Scraper task finished success_count={} selected_count={} elapsed_seconds={}",
        success_count,
        len(listing_targets),
        round(perf_counter() - task_started_at, 3),
    )
    return success_count


@app.callback()
def callback() -> None:
    """Inmob Real Estate Scraper Command-Line Interface."""


@app.command(name="ingest")
def ingest(
    source: str = typer.Option(
        "all",
        "--source",
        "-s",
        help="Specific source to scrape (argenprop, cabaprop, remax, mudafy, properati, zonaprop) or 'all'.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum properties to scrape per source.",
    ),
    pages: Optional[int] = typer.Option(
        None,
        "--pages",
        "-p",
        help="Number of search result pages to scan.",
    ),
    target_dir: Path = typer.Option(
        Path(DEFAULT_RAW_DATA_DIR),
        "--target-dir",
        "-d",
        help="Output root directory where property subfolders are stored.",
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Optional path to a JSON file overriding default search criteria arguments.",
    ),
    log_dir: Path = typer.Option(
        Path("logs"),
        "--log-dir",
        help="Directory where rotating ingestion log files are written.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Console log level (DEBUG, INFO, WARNING, ERROR). File logs always capture DEBUG+.",
    ),
    log_rotation: str = typer.Option(
        "10 MB",
        "--log-rotation",
        help="Loguru rotation policy for ingestion log files.",
    ),
    log_retention: str = typer.Option(
        "14 days",
        "--log-retention",
        help="Loguru retention policy for ingestion log files.",
    ),
) -> None:
    """Execute raw property ingestion from multiple real estate search portals."""
    ingest_started_at = perf_counter()
    configure_logging(
        log_dir=log_dir,
        level=log_level,
        rotation=log_rotation,
        retention=log_retention,
    )
    logger.info(
        "Ingestion command started source={} limit={} pages={} target_dir={} "
        "config_path={} log_dir={}",
        source,
        limit,
        pages,
        str(target_dir),
        str(config_path) if config_path is not None else None,
        str(log_dir),
    )

    # 1. Validate inputs: at least one of limit or pages must be specified
    if limit is None and pages is None:
        logger.error("You must specify either --limit / -l or --pages / -p")
        raise typer.Exit(code=1)

    # 2. Prioritize limit if both are provided (prelacion al limit)
    if limit is not None and pages is not None:
        logger.warning("Both --limit and --pages provided. Prioritizing --limit")
        pages = None

    # Validate numbers
    if limit is not None and limit <= 0:
        logger.error("--limit must be greater than zero")
        raise typer.Exit(code=1)

    if pages is not None and pages <= 0:
        logger.error("--pages must be greater than zero")
        raise typer.Exit(code=1)

    # 3. Parse JSON configs if provided
    overrides: dict[str, Any] = {}
    if config_path:
        if not config_path.exists():
            logger.error("Config file not found path={}", config_path)
            raise typer.Exit(code=1)
        try:
            with config_path.open("r", encoding="utf-8") as f:
                overrides = json.load(f)
            logger.info("Loaded custom criteria overrides path={}", config_path)
        except Exception:
            logger.exception("Error reading config file path={}", config_path)
            raise typer.Exit(code=1)

    # 4. Filter target sources
    sources_to_scrape: dict[str, dict[str, Any]] = {}
    if source.lower() == "all":
        sources_to_scrape = DEFAULT_SOURCES_CONFIG
    else:
        norm_source = source.lower()
        if norm_source not in DEFAULT_SOURCES_CONFIG:
            valid_sources = ", ".join(DEFAULT_SOURCES_CONFIG.keys())
            logger.error(
                "Unknown source source={} valid_sources={}",
                source,
                valid_sources,
            )
            raise typer.Exit(code=1)
        sources_to_scrape = {norm_source: DEFAULT_SOURCES_CONFIG[norm_source]}

    # Ensure output root directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting ingestion target_dir={} source_count={} sources={}",
        str(target_dir.resolve()),
        len(sources_to_scrape),
        sorted(sources_to_scrape),
    )
    if limit is not None:
        logger.info("Limits up to {} properties per source", limit)
    else:
        logger.info("Limits up to {} index pages per source", pages)

    # 5. Parallel Execution using ThreadPoolExecutor
    results: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=len(sources_to_scrape)) as executor:
        future_to_source = {
            executor.submit(
                scrape_source,
                source_id=source_id,
                source_cfg=cfg,
                limit=limit,
                pages=pages,
                target_dir=target_dir,
                custom_criteria_args=overrides.get(source_id),
            ): source_id
            for source_id, cfg in sources_to_scrape.items()
        }

        for future in as_completed(future_to_source):
            source_id = future_to_source[future]
            try:
                success_count = future.result()
                results[source_id] = success_count
            except Exception as exc:
                logger.bind(source_id=source_id).exception(
                    "Worker crashed with exception={}",
                    exc,
                )
                results[source_id] = 0

    # 6. Summary display
    logger.info("Ingestion job summary start")
    for source_id, success_count in sorted(results.items()):
        logger.bind(source_id=source_id).info(
            "Ingestion source summary success_count={}",
            success_count,
        )
    logger.info(
        "Ingestion command finished elapsed_seconds={} results={}",
        round(perf_counter() - ingest_started_at, 3),
        results,
    )


if __name__ == "__main__":
    app()
