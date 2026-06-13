from datetime import UTC, datetime
from hashlib import sha256

from inmob.ingestion.contracts import (
    IngestionRequest,
    IngestionResponse,
    IngestionRunContext,
    IngestionTarget,
    TargetKind,
)
from inmob.ingestion.raw_store import FileSystemRawArtifactStore


def test_filesystem_raw_store_persists_payload_and_metadata(tmp_path) -> None:
    target = IngestionTarget(
        target_id="zonaprop-search-caba",
        kind=TargetKind.SEARCH_RESULTS,
        uri="https://www.zonaprop.com.ar/departamentos-alquiler.html",
    )
    request = IngestionRequest(source_id="zonaprop", target=target)
    response = IngestionResponse(
        request=request,
        status_code=200,
        final_uri=target.uri,
        captured_at=datetime(2026, 6, 13, tzinfo=UTC),
        media_type="text/html",
        headers={"content-type": "text/html"},
        payload=b"<html>raw only</html>",
    )
    context = IngestionRunContext(run_id="run-001")
    store = FileSystemRawArtifactStore(tmp_path)

    artifact = store.persist(context=context, response=response)

    assert artifact.source_id == "zonaprop"
    assert artifact.run_id == "run-001"
    assert artifact.target_id == "zonaprop-search-caba"
    assert artifact.payload_sha256 == sha256(b"<html>raw only</html>").hexdigest()
    assert artifact.payload_path.read_bytes() == b"<html>raw only</html>"
    assert artifact.metadata_path.exists()
