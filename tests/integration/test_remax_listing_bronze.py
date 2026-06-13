from inmob.ingestion.contracts import IngestionRunContext
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import RemaxSource


REMAX_LISTING_URL = (
    "https://www.remax.com.ar/listings/"
    "venta-casa-con-jardin-y-cochera-en-villa-urquiza"
)


def test_remax_listing_detail_is_landed_as_raw_html(tmp_path) -> None:
    target = RemaxSource.listing_target(
        slug="venta-casa-con-jardin-y-cochera-en-villa-urquiza",
        url=REMAX_LISTING_URL,
    )
    source = RemaxSource(targets=(target,))
    context = IngestionRunContext(run_id="integration-remax-listing")
    store = FileSystemRawArtifactStore(tmp_path)

    request = next(iter(source.plan_requests(context)))
    response = source.fetch(request)
    artifact = store.persist(context=context, response=response)

    payload = artifact.payload_path.read_bytes()

    assert response.status_code == 200
    assert artifact.source_id == "remax"
    assert artifact.target_id == "remax-listing-venta-casa-con-jardin-y-cochera-en-villa-urquiza"
    assert artifact.target_kind == "listing_detail"
    assert artifact.media_type in {"text/html", "application/octet-stream", None}
    assert b"Villa Urquiza" in payload or b"villa-urquiza" in payload.lower()
    assert artifact.metadata_path.exists()
