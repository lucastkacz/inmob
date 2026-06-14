"""Typer-based CLI for running the real estate scraping orchestrator."""

from __future__ import annotations

import json
import math
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, as_completed

import typer

from inmob.cli.config import DEFAULT_RAW_DATA_DIR, DEFAULT_SOURCES_CONFIG
from inmob.cli.store import PropertyFolderRawArtifactStore
from inmob.ingestion.contracts import IngestionRunContext, IngestionTarget


app = typer.Typer(
    help="Inmob Real Estate Scraper Command-Line Interface.",
    no_args_is_help=True,
)


def scrape_source(
    source_id: str,
    source_cfg: dict[str, Any],
    limit: int,
    target_dir: Path,
    pages_limit: int,
    custom_criteria_args: dict[str, Any] | None = None,
) -> int:
    """Worker function to scrape a single source.

    Returns the number of successfully ingested listing detail files.
    """
    print(f"[{source_id.upper()}] Starting scraper task (target limit: {limit})...")

    source_class = source_cfg["source_class"]
    criteria_class = source_cfg["criteria_class"]
    page_index_starts_at = source_cfg["page_index_starts_at"]
    search_targets_method = source_cfg["search_targets_method"]

    # Merge criteria args
    criteria_args = dict(source_cfg["default_criteria"])
    if custom_criteria_args:
        criteria_args.update(custom_criteria_args)

    criteria = criteria_class(**criteria_args)

    # Calculate search pages needed
    page_size = criteria.page_size
    pages_needed = math.ceil(limit / page_size)
    pages_needed = min(pages_needed, pages_limit)

    pages = list(range(page_index_starts_at, page_index_starts_at + pages_needed))

    print(f"[{source_id.upper()}] Target page range: {pages} (size per page: {page_size})")

    # Ingestion run context
    run_id = f"cli-run-{source_id}-{uuid4().hex[:8]}"
    context = IngestionRunContext(run_id=run_id, requested_at=datetime.now(UTC))

    # Retrieve targets
    target_builder = getattr(source_class, search_targets_method)
    search_targets = target_builder(criteria=criteria, pages=pages)

    discovered_by_uri: dict[str, IngestionTarget] = {}

    # 1. Fetch search pages and discover individual listing target URIs
    with source_class(targets=search_targets) as search_source:
        for request in search_source.plan_requests(context):
            try:
                print(f"[{source_id.upper()}] Fetching listing list page: {request.target.uri}")
                response = search_source.fetch(request)
                if response.status_code not in (200, 201):
                    print(
                        f"[{source_id.upper()}] WARNING: Search page returned status {response.status_code}"
                    )
                    continue

                page_targets = search_source.discover_listing_targets(response.payload)
                print(f"[{source_id.upper()}] Discovered {len(page_targets)} listing(s) on page.")
                for target in page_targets:
                    discovered_by_uri.setdefault(target.uri, target)

            except Exception as e:
                print(
                    f"[{source_id.upper()}] ERROR: Exception fetching listing list page "
                    f"{request.target.uri}: {e}"
                )

    # 2. Slice listing targets to the exact user limit
    listing_targets = tuple(discovered_by_uri.values())[:limit]
    total_discovered = len(discovered_by_uri)
    print(
        f"[{source_id.upper()}] Unique listings discovered: {total_discovered}. "
        f"Selected for details fetching: {len(listing_targets)}"
    )

    if not listing_targets:
        print(f"[{source_id.upper()}] Scraper finished: No listing detail URIs discovered.")
        return 0

    # 3. Retrieve and persist each listing detail page sequentially (respecting politeness limits)
    store = PropertyFolderRawArtifactStore(target_dir)
    success_count = 0

    with source_class(targets=listing_targets) as listing_source:
        for idx, request in enumerate(listing_source.plan_requests(context), start=1):
            try:
                print(
                    f"[{source_id.upper()}] [{idx}/{len(listing_targets)}] "
                    f"Fetching details: {request.target.uri}"
                )
                response = listing_source.fetch(request)
                if response.status_code == 200:
                    artifact = store.persist(context=context, response=response)
                    success_count += 1
                    prop_id = artifact.payload_path.parent.name
                    print(
                        f"[{source_id.upper()}] [{idx}/{len(listing_targets)}] "
                        f"Saved: {prop_id} ({len(response.payload)} bytes)"
                    )
                else:
                    print(
                        f"[{source_id.upper()}] [{idx}/{len(listing_targets)}] "
                        f"FAILED with HTTP status {response.status_code}: {request.target.uri}"
                    )
            except Exception as e:
                print(
                    f"[{source_id.upper()}] [{idx}/{len(listing_targets)}] "
                    f"ERROR fetching listing details page: {e}"
                )

    print(
        f"[{source_id.upper()}] Task finished! Successfully saved {success_count}/{len(listing_targets)} properties."
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
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        help="Maximum properties to scrape per source.",
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
    pages_limit: int = typer.Option(
        10,
        "--pages-limit",
        "-p",
        help="Maximum search result pages to scan.",
    ),
) -> None:
    """Execute raw property ingestion from multiple real estate search portals."""
    # 1. Parse JSON configs if provided
    overrides: dict[str, Any] = {}
    if config_path:
        if not config_path.exists():
            typer.echo(f"Error: Config file not found at {config_path}", err=True)
            raise typer.Exit(code=1)
        try:
            with config_path.open("r", encoding="utf-8") as f:
                overrides = json.load(f)
            typer.echo(f"Loaded custom criteria overrides from: {config_path}")
        except Exception as e:
            typer.echo(f"Error reading config file {config_path}: {e}", err=True)
            raise typer.Exit(code=1)

    # 2. Filter target sources
    sources_to_scrape: dict[str, dict[str, Any]] = {}
    if source.lower() == "all":
        sources_to_scrape = DEFAULT_SOURCES_CONFIG
    else:
        norm_source = source.lower()
        if norm_source not in DEFAULT_SOURCES_CONFIG:
            valid_sources = ", ".join(DEFAULT_SOURCES_CONFIG.keys())
            typer.echo(
                f"Error: Unknown source '{source}'. Valid sources are: {valid_sources}",
                err=True,
            )
            raise typer.Exit(code=1)
        sources_to_scrape = {norm_source: DEFAULT_SOURCES_CONFIG[norm_source]}

    # Ensure output root directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Starting ingestion on target directory: {target_dir.resolve()}")
    typer.echo(f"Limits: up to {limit} properties per source (max {pages_limit} index pages)")

    # 3. Parallel Execution using ThreadPoolExecutor
    results: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=len(sources_to_scrape)) as executor:
        future_to_source = {
            executor.submit(
                scrape_source,
                source_id=source_id,
                source_cfg=cfg,
                limit=limit,
                target_dir=target_dir,
                pages_limit=pages_limit,
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
                typer.echo(f"[{source_id.upper()}] Worker crashed with exception: {exc}", err=True)
                results[source_id] = 0

    # 4. Summary display
    typer.echo("\n" + "=" * 40)
    typer.echo("          INGESTION JOB SUMMARY")
    typer.echo("=" * 40)
    for source_id, success_count in sorted(results.items()):
        typer.echo(f" - {source_id.upper():12}: successfully saved {success_count} properties.")
    typer.echo("=" * 40)


if __name__ == "__main__":
    app()
