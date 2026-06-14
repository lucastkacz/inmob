from inmob.ingestion.contracts import IngestionRunContext
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import MudafySource


MUDAFY_LISTING_URL = (
    "https://mudafy.com.ar/departamentos/larrea-1000-departamento-en-venta-588058"
)


def test_mudafy_listing_detail_is_landed_as_raw_html(tmp_path) -> None:
    source = MudafySource()
    listing_target = source.listing_target_from_url(MUDAFY_LISTING_URL)
    context = IngestionRunContext(run_id="integration-mudafy-listing")
    store = FileSystemRawArtifactStore(tmp_path)

    with MudafySource(targets=(listing_target,)) as listing_source:
        listing_request = next(iter(listing_source.plan_requests(context)))
        listing_response = listing_source.fetch(listing_request)

    artifact = store.persist(context=context, response=listing_response)
    payload = artifact.payload_path.read_bytes()

    print(f"Listing URL: {listing_request.target.uri}")
    print(f"Listing status: {listing_response.status_code}")
    print(f"Listing raw bytes: {len(listing_response.payload)}")
    print(f"Temporary raw path: {artifact.payload_path}")
    print(f"Temporary metadata path: {artifact.metadata_path}")

    assert listing_response.status_code == 200
    assert listing_response.media_type == "text/html"
    assert artifact.source_id == "mudafy"
    assert artifact.target_id == "mudafy-listing-588058"
    assert artifact.target_kind == "listing_detail"
    assert artifact.payload_path.suffix == ".html"
    assert b"588058" in payload
    assert b"Larrea 1000" in payload
    assert artifact.metadata_path.exists()
