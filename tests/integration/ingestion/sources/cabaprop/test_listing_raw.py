import json

from inmob.ingestion.contracts import IngestionRunContext
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import CabapropSource


def test_cabaprop_listing_detail_api_is_landed_as_fact_rich_raw_json(tmp_path) -> None:
    listing_target = CabapropSource.listing_target(
        listing_id="6a2e203cef1190992353bef6",
        title="Penthouse En Belgrano",
    )
    context = IngestionRunContext(run_id="integration-cabaprop-listing-api")
    store = FileSystemRawArtifactStore(tmp_path)

    with CabapropSource(targets=(listing_target,)) as listing_source:
        listing_request = next(iter(listing_source.plan_requests(context)))
        listing_response = listing_source.fetch(listing_request)

    artifact = store.persist(context=context, response=listing_response)
    payload = json.loads(artifact.payload_path.read_text(encoding="utf-8"))

    print(f"Listing API URL: {listing_request.target.uri}")
    print(f"Listing API status: {listing_response.status_code}")
    print(f"Listing API raw bytes: {len(listing_response.payload)}")
    print(f"Temporary raw path: {artifact.payload_path}")
    print(f"Temporary metadata path: {artifact.metadata_path}")
    print(f"Price: {payload['price']}")
    print(f"Location: {payload['location']}")
    print(f"Surface: {payload['surface']}")

    assert listing_response.status_code == 200
    assert listing_response.media_type == "application/json"
    assert artifact.source_id == "cabaprop"
    assert artifact.target_id == "cabaprop-listing-6a2e203cef1190992353bef6"
    assert artifact.target_kind == "api_endpoint"
    assert artifact.payload_path.suffix == ".json"
    assert payload["_id"] == "6a2e203cef1190992353bef6"
    assert payload["title"] == "Penthouse En Belgrano"
    assert payload["description"]
    assert payload["price"]["total"] > 0
    assert payload["surface"]["totalSurface"] > 0
    assert payload["location"]["street"]
    assert payload["location"]["lat"]
    assert payload["location"]["lng"]
    assert artifact.metadata_path.exists()
