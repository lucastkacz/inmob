"""Silver runner for replaying Bronze raw artifacts into canonical listings."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from loguru import logger

from inmob.standardization.contracts import QuarantineArtifact, RawArtifactMetadata
from inmob.standardization.parsers import ParserError, parse_listing
from inmob.standardization.store import SilverSQLiteStore


class SilverProcessingError(ValueError):
    """Raised when a Silver processing request is invalid."""


@dataclass(frozen=True)
class SilverProcessingRunner:
    """Process Bronze raw artifacts into Silver canonical state."""

    def run(self, *, raw_dir: Path, db_path: Path, quarantine_dir: Path) -> dict[str, int]:
        started_at = perf_counter()
        if not raw_dir.exists():
            raise SilverProcessingError(f"Raw directory not found raw_dir={raw_dir}")

        metadata_paths = tuple(sorted(raw_dir.glob("*/*/*_raw_metadata.json")))
        store = SilverSQLiteStore(db_path)
        store.initialize()
        quarantine_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Silver processing started raw_dir={} db_path={} quarantine_dir={} artifacts={}",
            str(raw_dir),
            str(db_path),
            str(quarantine_dir),
            len(metadata_paths),
        )

        parsed_by_source: Counter[str] = Counter()
        quarantined_by_source: Counter[str] = Counter()
        for metadata_path in metadata_paths:
            try:
                metadata = RawArtifactMetadata.from_file(metadata_path)
                payload = metadata.payload_path.read_bytes()
                listing = parse_listing(metadata, payload)
                store.upsert_listing(listing)
                parsed_by_source[metadata.source_id] += 1
                logger.bind(
                    source_id=metadata.source_id,
                    run_id=metadata.run_id,
                    target_id=metadata.target_id,
                    target_kind=metadata.target_kind,
                ).info(
                    "Silver artifact accepted parser_id={} raw_artifact_id={} payload_path={} metadata_path={}",
                    listing.parser_id,
                    metadata.artifact_id,
                    str(metadata.payload_path),
                    str(metadata.metadata_path),
                )
            except Exception as exc:
                metadata = _metadata_or_stub(metadata_path)
                artifact = QuarantineArtifact(
                    raw_artifact_id=metadata.artifact_id,
                    source_id=metadata.source_id,
                    parser_id=f"{metadata.source_id}_parser",
                    parser_version="v1",
                    failure_category=_failure_category(exc),
                    diagnostic_detail=str(exc),
                    retryable=isinstance(exc, ParserError),
                    metadata_path=metadata_path,
                    payload_path=metadata.payload_path,
                )
                _write_quarantine_file(quarantine_dir, artifact)
                store.quarantine(artifact)
                quarantined_by_source[metadata.source_id] += 1
                logger.bind(
                    source_id=metadata.source_id,
                    run_id=metadata.run_id,
                    target_id=metadata.target_id,
                    target_kind=metadata.target_kind,
                ).warning(
                    "Silver artifact quarantined category={} raw_artifact_id={} detail={} metadata_path={}",
                    artifact.failure_category,
                    artifact.raw_artifact_id,
                    artifact.diagnostic_detail,
                    str(metadata_path),
                )

        counts = store.counts()
        result = {
            "artifacts": len(metadata_paths),
            "parsed": sum(parsed_by_source.values()),
            "quarantined": sum(quarantined_by_source.values()),
            **counts,
        }
        logger.info(
            "Silver processing finished elapsed_seconds={} result={} parsed_by_source={} quarantined_by_source={}",
            round(perf_counter() - started_at, 3),
            result,
            dict(sorted(parsed_by_source.items())),
            dict(sorted(quarantined_by_source.items())),
        )
        return result


def _metadata_or_stub(metadata_path: Path) -> RawArtifactMetadata:
    try:
        return RawArtifactMetadata.from_file(metadata_path)
    except Exception:
        return RawArtifactMetadata(
            artifact_id=metadata_path.stem,
            run_id="-",
            source_id=metadata_path.parent.parent.name or "-",
            target_id="-",
            target_kind="-",
            requested_uri="https://invalid.local/",
            final_uri="https://invalid.local/",
            captured_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            status_code=0,
            media_type=None,
            payload_sha256="0" * 64,
            payload_size_bytes=0,
            payload_path=metadata_path.with_name(metadata_path.name.replace("_raw_metadata.json", "_raw_payload.html")),
            metadata_path=metadata_path,
        )


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, ParserError):
        return "parser_error"
    if isinstance(exc, FileNotFoundError):
        return "missing_payload"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    return "unexpected_error"


def _write_quarantine_file(root: Path, artifact: QuarantineArtifact) -> None:
    source_dir = root / artifact.source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / f"{artifact.raw_artifact_id}_quarantine.json"
    path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
