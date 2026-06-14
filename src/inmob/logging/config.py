"""Loguru configuration for operational ingestion logs."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


DEFAULT_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "source={extra[source_id]} run={extra[run_id]} "
    "target={extra[target_kind]}:{extra[target_id]} | "
    "{name}:{function}:{line} - {message}"
)


def configure_logging(
    *,
    log_dir: Path | str = Path("logs"),
    level: str = "INFO",
    file_level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "14 days",
    diagnose: bool = False,
) -> Path:
    """Configure console and rotating file logging.

    The configuration is intentionally idempotent: every CLI invocation replaces
    previous sinks, which avoids duplicated log lines in tests or repeated calls.
    """

    normalized_level = level.upper()
    normalized_file_level = file_level.upper()
    log_root = Path(log_dir).expanduser().resolve(strict=False)
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "ingest_{time:YYYY-MM-DD_HH-mm-ss}.log"

    logger.remove()
    logger.configure(
        extra={
            "source_id": "-",
            "run_id": "-",
            "target_id": "-",
            "target_kind": "-",
        }
    )
    logger.add(
        sys.stderr,
        level=normalized_level,
        format=DEFAULT_LOG_FORMAT,
        backtrace=True,
        diagnose=diagnose,
        enqueue=True,
    )
    logger.add(
        log_path,
        level=normalized_file_level,
        format=DEFAULT_LOG_FORMAT,
        rotation=rotation,
        retention=retention,
        backtrace=True,
        diagnose=diagnose,
        enqueue=True,
        encoding="utf-8",
    )

    logger.debug(
        "Logging configured log_dir={} level={} file_level={} rotation={} retention={}",
        str(log_root),
        normalized_level,
        normalized_file_level,
        rotation,
        retention,
    )
    return log_root
