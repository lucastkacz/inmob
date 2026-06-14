"""Filesystem implementation of the Bronze raw artifact store."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from loguru import logger

from inmob.ingestion.contracts import IngestionResponse, IngestionRunContext, RawArtifact


class FileSystemRawArtifactStore:
    """Persist raw payloads and metadata to local storage."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def persist(
        self,
        *,
        context: IngestionRunContext,
        response: IngestionResponse,
    ) -> RawArtifact:
        artifact_id = uuid4().hex
        payload_sha = sha256(response.payload).hexdigest()
        captured_at = response.captured_at.astimezone(UTC)
        store_logger = logger.bind(
            source_id=response.request.source_id,
            run_id=context.run_id,
            target_id=response.request.target.target_id,
            target_kind=response.request.target.kind.value,
        )

        artifact_dir = self._artifact_dir(
            source_id=response.request.source_id,
            run_id=context.run_id,
            captured_at=captured_at,
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)

        extension = self._extension_for_media_type(response.media_type)
        payload_path = artifact_dir / f"{artifact_id}.{extension}"
        metadata_path = artifact_dir / f"{artifact_id}.metadata.json"

        payload_path.write_bytes(response.payload)
        store_logger.debug(
            "Raw payload written payload_path={} payload_bytes={} payload_sha256={}",
            str(payload_path),
            len(response.payload),
            payload_sha,
        )

        artifact = RawArtifact(
            artifact_id=artifact_id,
            run_id=context.run_id,
            source_id=response.request.source_id,
            target_id=response.request.target.target_id,
            target_kind=response.request.target.kind,
            requested_uri=response.request.target.uri,
            final_uri=response.final_uri,
            captured_at=response.captured_at,
            status_code=response.status_code,
            media_type=response.media_type,
            payload_sha256=payload_sha,
            payload_size_bytes=len(response.payload),
            payload_path=payload_path,
            metadata_path=metadata_path,
            headers=response.headers,
            target_metadata=response.request.target.metadata,
        )

        metadata_path.write_text(
            json.dumps(artifact.to_json_ready_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        store_logger.info(
            "Raw artifact persisted artifact_id={} payload_path={} metadata_path={}",
            artifact_id,
            str(payload_path),
            str(metadata_path),
        )

        return artifact

    def _artifact_dir(self, *, source_id: str, run_id: str, captured_at: datetime) -> Path:
        return (
            self._root
            / source_id
            / f"{captured_at.year:04d}"
            / f"{captured_at.month:02d}"
            / f"{captured_at.day:02d}"
            / run_id
        )

    def _extension_for_media_type(self, media_type: str | None) -> str:
        if media_type == "application/json":
            return "json"
        if media_type in {"text/html", "application/xhtml+xml"}:
            return "html"
        if media_type is not None and media_type.startswith("text/"):
            return "txt"
        return "bin"
