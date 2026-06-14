from inmob.ingestion.contracts import IngestionRunContext
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import ProperatiSource


PROPERATI_LISTING_URL = (
    "https://www.properati.com.ar/detalle/14032-32-699-8e78b5aabfaa-19c2da1-8b5b-731b"
)


def test_properati_listing_detail_is_landed_as_raw_html(tmp_path) -> None:
    source = ProperatiSource()
    listing_target = source.listing_target_from_url(PROPERATI_LISTING_URL)
    context = IngestionRunContext(run_id="integration-properati-listing")
    store = FileSystemRawArtifactStore(tmp_path)

    with ProperatiSource(targets=(listing_target,)) as listing_source:
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
    assert artifact.source_id == "properati"
    assert artifact.target_id == "properati-listing-14032-32-699-8e78b5aabfaa-19c2da1-8b5b-731b"
    assert artifact.target_kind == "listing_detail"
    assert artifact.payload_path.suffix == ".html"
    assert b"14032-32-699-8e78b5aabfaa-19c2da1-8b5b-731b" in payload
    assert b"Centro / Microcentro" in payload
    assert b"65.000" in payload
    assert artifact.metadata_path.exists()
