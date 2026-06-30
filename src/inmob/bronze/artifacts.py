"""Bronze raw artifact persistence."""

from __future__ import annotations

import json
import re
from datetime import UTC
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from inmob.bronze.contracts import BronzeResponse, BronzeRunContext, RawArtifact, TargetKind


class BronzeArtifactStore:
    """Persist raw Bronze payloads under one run-scoped directory."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def run_dir(self, run_id: str) -> Path:
        return self._root / "runs" / _safe_path_segment(run_id)

    def persist_search_item(
        self,
        *,
        context: BronzeRunContext,
        source_id: str,
        item_id: str,
        payload: dict[str, Any],
    ) -> Path:
        """Persist one item already present inside a search response."""

        item_path = (
            self.run_dir(context.run_id)
            / _safe_path_segment(source_id)
            / "search_items"
            / f"{_safe_path_segment(item_id)}.json"
        )
        item_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(item_path, payload)

        logger.bind(
            source_id=source_id,
            run_id=context.run_id,
            item_id=item_id,
        ).info("bronze.search_item.persisted item_path={}", str(item_path))
        return item_path

    def persist(
        self,
        *,
        context: BronzeRunContext,
        response: BronzeResponse,
    ) -> RawArtifact:
        target = response.request.target
        source_id = response.request.source_id
        payload_sha = sha256(response.payload).hexdigest()
        artifact_origin: Literal["fetched", "derived"] = (
            "derived"
            if response.capture_metadata.get("artifact_origin")
            == "derived_from_parent_payload"
            else "fetched"
        )
        parent_artifact_id = (
            response.capture_metadata.get("parent_artifact_id")
            or target.metadata.get("parent_artifact_id")
        )

        artifact_id = "-".join(
            (
                _safe_path_segment(context.run_id),
                source_id,
                target.kind.value,
                _safe_path_segment(target.target_id),
                payload_sha[:12],
            )
        )
        artifact_dir = (
            self.run_dir(context.run_id)
            / source_id
            / target.kind.value
            / _safe_path_segment(target.target_id)
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = artifact_dir / "metadata.json"
        payload_path: Path | None = None
        if target.kind != TargetKind.SEARCH_RESULTS:
            ext = self._extension_for_media_type(response.media_type)
            payload_path = artifact_dir / f"payload.{ext}"
            _write_bytes_atomic(payload_path, response.payload)

        artifact = RawArtifact(
            artifact_id=artifact_id,
            artifact_origin=artifact_origin,
            parent_artifact_id=parent_artifact_id or None,
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
        _write_json_atomic(metadata_path, artifact.to_json_ready_dict())

        logger.bind(
            source_id=source_id,
            run_id=context.run_id,
            target_id=target.target_id,
            target_kind=target.kind.value,
            artifact_id=artifact.artifact_id,
        ).info(
            "bronze.artifact.persisted origin={} status_code={} payload_bytes={} "
            "payload_sha256={} payload_path={} metadata_path={}",
            artifact.artifact_origin,
            artifact.status_code,
            artifact.payload_size_bytes,
            artifact.payload_sha256,
            str(payload_path) if payload_path is not None else None,
            str(metadata_path),
        )
        return artifact

    @staticmethod
    def _extension_for_media_type(media_type: str | None) -> str:
        if media_type == "application/json" or (
            media_type is not None and media_type.endswith("+json")
        ):
            return "json"
        if media_type in {"text/html", "application/xhtml+xml"}:
            return "html"
        if media_type is not None and media_type.startswith("text/"):
            return "txt"
        return "bin"


def _safe_path_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._=-]+", "-", value).strip("-._")
    if not cleaned:
        return sha256(value.encode("utf-8")).hexdigest()[:16]
    if len(cleaned) <= 120:
        return cleaned
    return f"{cleaned[:103]}-{sha256(value.encode('utf-8')).hexdigest()[:16]}"


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(path)


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)
