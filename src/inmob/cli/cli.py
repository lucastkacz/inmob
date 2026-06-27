"""Typer-based CLI for running Inmob ingestion jobs."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Optional

import typer
from loguru import logger

from inmob.cli.bronze import (
    DEFAULT_PROPERTY_LIMIT,
    DEFAULT_RAW_DATA_DIR,
    BronzeIngestionError,
    BronzeIngestionRunner,
)
from inmob.logging import configure_logging
from inmob.standardization import SilverProcessingError, SilverProcessingRunner


app = typer.Typer(
    help="Inmob Real Estate Scraper Command-Line Interface.",
    no_args_is_help=True,
)


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
        help=f"Maximum properties to scrape per source. Defaults to {DEFAULT_PROPERTY_LIMIT} when --pages is not provided.",
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
        help="Console log level (DEBUG, INFO, WARNING, ERROR).",
    ),
    log_file_level: str = typer.Option(
        "INFO",
        "--log-file-level",
        help="File log level (use DEBUG for verbose diagnostics).",
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
        file_level=log_file_level,
        rotation=log_rotation,
        retention=log_retention,
    )
    logger.info(
        "Ingestion command started source={} limit={} pages={} target_dir={} "
        "config_path={} log_dir={} log_level={} log_file_level={}",
        source,
        limit,
        pages,
        str(target_dir),
        str(config_path) if config_path is not None else None,
        str(log_dir),
        log_level,
        log_file_level,
    )

    runner = BronzeIngestionRunner()
    try:
        results = runner.run(
            source=source,
            limit=limit,
            pages=pages,
            target_dir=target_dir,
            config_path=config_path,
        )
    except BronzeIngestionError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc

    logger.info(
        "Ingestion command finished elapsed_seconds={} results={}",
        round(perf_counter() - ingest_started_at, 3),
        results,
    )


@app.command(name="silver")
def silver(
    raw_dir: Path = typer.Option(
        Path(DEFAULT_RAW_DATA_DIR),
        "--raw-dir",
        help="Bronze raw artifact directory to process.",
    ),
    db_path: Path = typer.Option(
        Path("data/silver/inmob.sqlite"),
        "--db-path",
        help="SQLite database path for Silver current state and observations.",
    ),
    quarantine_dir: Path = typer.Option(
        Path("data/quarantine"),
        "--quarantine-dir",
        help="Directory where Silver quarantine artifacts are written.",
    ),
    log_dir: Path = typer.Option(
        Path("logs"),
        "--log-dir",
        help="Directory where rotating processing log files are written.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Console log level (DEBUG, INFO, WARNING, ERROR).",
    ),
    log_file_level: str = typer.Option(
        "INFO",
        "--log-file-level",
        help="File log level (use DEBUG for verbose diagnostics).",
    ),
) -> None:
    """Process Bronze raw artifacts into Silver canonical listing state."""
    started_at = perf_counter()
    configure_logging(log_dir=log_dir, level=log_level, file_level=log_file_level)
    logger.info(
        "Silver command started raw_dir={} db_path={} quarantine_dir={} log_dir={}",
        str(raw_dir),
        str(db_path),
        str(quarantine_dir),
        str(log_dir),
    )
    try:
        results = SilverProcessingRunner().run(
            raw_dir=raw_dir,
            db_path=db_path,
            quarantine_dir=quarantine_dir,
        )
    except SilverProcessingError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc

    logger.info(
        "Silver command finished elapsed_seconds={} results={}",
        round(perf_counter() - started_at, 3),
        results,
    )


if __name__ == "__main__":
    app()
