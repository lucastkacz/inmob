"""Raw artifact store for CLI Bronze property captures."""

from __future__ import annotations

import json
from datetime import UTC
from hashlib import md5, sha256
from pathlib import Path

from loguru import logger

from inmob.ingestion.contracts import IngestionResponse, IngestionRunContext, RawArtifact


class PropertyFolderRawArtifactStore:
    """Stores raw payloads in property-specific folders.

    Structure:
    {root}/{source_id}/{property_id}/
      - {source_id}_{property_id}_raw_payload.html (or .json)
      - {source_id}_{property_id}_raw_metadata.json
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def persist(
        self,
        *,
        context: IngestionRunContext,
        response: IngestionResponse,
    ) -> RawArtifact:
        target = response.request.target
        source_id = response.request.source_id
        store_logger = logger.bind(
            source_id=source_id,
            run_id=context.run_id,
            target_id=target.target_id,
            target_kind=target.kind.value,
        )

        prop_id = target.metadata.get("listing_id") or target.metadata.get("slug")
        if not prop_id:
            if "-" in target.target_id:
                prop_id = target.target_id.split("-")[-1]
            else:
                prop_id = md5(target.uri.encode("utf-8")).hexdigest()

        property_dir = self._root / source_id / prop_id
        property_dir.mkdir(parents=True, exist_ok=True)

        ext = self._extension_for_media_type(response.media_type)
        payload_path = property_dir / f"{source_id}_{prop_id}_raw_payload.{ext}"
        metadata_path = property_dir / f"{source_id}_{prop_id}_raw_metadata.json"

        payload_path.write_bytes(response.payload)

        payload_sha = sha256(response.payload).hexdigest()
        store_logger.debug(
            "Property raw payload written property_id={} payload_path={} payload_bytes={} "
            "payload_sha256={}",
            prop_id,
            str(payload_path),
            len(response.payload),
            payload_sha,
        )

        artifact = RawArtifact(
            artifact_id=f"{source_id}-{prop_id}",
            run_id=context.run_id,
            source_id=source_id,
            target_id=target.target_id,
            target_kind=target.kind,
            requested_uri=target.uri,
            final_uri=response.final_uri,
            captured_at=response.captured_at.astimezone(UTC),
            status_code=response.status_code,
            media_type=response.media_type,
            payload_sha256=payload_sha,
            payload_size_bytes=len(response.payload),
            payload_path=payload_path,
            metadata_path=metadata_path,
            headers=response.headers,
            target_metadata=target.metadata,
            capture_metadata=response.capture_metadata,
        )

        metadata_path.write_text(
            json.dumps(artifact.to_json_ready_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        store_logger.info(
            "Property raw artifact persisted property_id={} payload_path={} metadata_path={}",
            prop_id,
            str(payload_path),
            str(metadata_path),
        )

        return artifact

    @staticmethod
    def _extension_for_media_type(media_type: str | None) -> str:
        if media_type == "application/json":
            return "json"
        if media_type in {"text/html", "application/xhtml+xml"}:
            return "html"
        if media_type is not None and media_type.startswith("text/"):
            return "txt"
        return "bin"
