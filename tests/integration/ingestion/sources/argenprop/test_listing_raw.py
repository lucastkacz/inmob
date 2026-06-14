from inmob.ingestion.contracts import IngestionRunContext
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import ArgenpropSource


ARGENPROP_LISTING_URL = (
    "https://www.argenprop.com/"
    "departamento-en-venta-en-palermo-3-ambientes--19622671"
)


def test_argenprop_listing_detail_is_landed_as_raw_html(tmp_path) -> None:
    source = ArgenpropSource()
    listing_target = source.listing_target_from_url(ARGENPROP_LISTING_URL)
    context = IngestionRunContext(run_id="integration-argenprop-listing")
    store = FileSystemRawArtifactStore(tmp_path)

    with ArgenpropSource(targets=(listing_target,)) as listing_source:
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
    assert artifact.source_id == "argenprop"
    assert artifact.target_id == "argenprop-listing-19622671"
    assert artifact.target_kind == "listing_detail"
    assert artifact.payload_path.suffix == ".html"
    assert b"application/ld+json" in payload
    assert b"19622671" in payload
    assert artifact.metadata_path.exists()
