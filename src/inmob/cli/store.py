"""Custom raw artifact store for property-specific directories."""

from __future__ import annotations

import json
from datetime import UTC
from hashlib import sha256
from pathlib import Path

from inmob.ingestion.contracts import IngestionResponse, IngestionRunContext, RawArtifact


class PropertyFolderRawArtifactStore:
    """Stores raw payloads in property-specific folders.

    Structure:
    {root}/{source_id}/{property_id}/
      ├── {source_id}_{property_id}_raw_payload.html (or .json)
      └── {source_id}_{property_id}_raw_metadata.json
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

        # Determine unique property id from target metadata
        prop_id = target.metadata.get("listing_id") or target.metadata.get("slug")
        if not prop_id:
            # Fallback based on target_id or uri hash
            if "-" in target.target_id:
                prop_id = target.target_id.split("-")[-1]
            else:
                from hashlib import md5
                prop_id = md5(target.uri.encode("utf-8")).hexdigest()

        # Build subfolder path
        property_dir = self._root / source_id / prop_id
        property_dir.mkdir(parents=True, exist_ok=True)

        # Determine extension
        media_type = response.media_type
        if media_type == "application/json":
            ext = "json"
        elif media_type in {"text/html", "application/xhtml+xml"}:
            ext = "html"
        elif media_type is not None and media_type.startswith("text/"):
            ext = "txt"
        else:
            ext = "bin"

        payload_path = property_dir / f"{source_id}_{prop_id}_raw_payload.{ext}"
        metadata_path = property_dir / f"{source_id}_{prop_id}_raw_metadata.json"

        # Write payload
        payload_path.write_bytes(response.payload)

        # Compute hash
        payload_sha = sha256(response.payload).hexdigest()

        # Create artifact contract
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
        )

        # Write metadata JSON
        metadata_path.write_text(
            json.dumps(artifact.to_json_ready_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        return artifact
