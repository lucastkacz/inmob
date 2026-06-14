from inmob.ingestion.contracts import IngestionRunContext
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import RemaxSearchCriteria, RemaxSource


CAPITAL_FEDERAL_LOCATION_FILTER = "in:CF@<b>Capital</b> <b>F</b>ederal::::::"


def test_remax_first_filtered_listing_detail_is_landed_as_raw_html(tmp_path) -> None:
    criteria = RemaxSearchCriteria(
        page_size=24,
        operation_ids=(1,),
        sort="-createdAt",
        filters=(("locations", CAPITAL_FEDERAL_LOCATION_FILTER),),
        landing_path="comprar-propiedades",
        filter_count=0,
        view_mode="listViewMode",
        label="capital-federal-buy",
    )
    search_target = RemaxSource.search_target(criteria=criteria, page=0)
    search_source = RemaxSource(targets=(search_target,))
    context = IngestionRunContext(run_id="integration-remax-first-filtered-listing")
    store = FileSystemRawArtifactStore(tmp_path)

    search_request = next(iter(search_source.plan_requests(context)))
    search_response = search_source.fetch(search_request)
    listing_targets = search_source.discover_listing_targets(search_response.payload)

    print(f"Search URL: {search_request.target.uri}")
    print(f"Search status: {search_response.status_code}")
    print(f"Search raw bytes: {len(search_response.payload)}")
    print(f"Discovered listings: {len(listing_targets)}")

    assert search_response.status_code == 200
    assert listing_targets

    listing_target = listing_targets[0]
    print(f"Selected listing URL: {listing_target.uri}")
    print(f"Selected listing slug: {listing_target.metadata['slug']}")

    listing_source = RemaxSource(targets=(listing_target,))
    listing_request = next(iter(listing_source.plan_requests(context)))
    listing_response = listing_source.fetch(listing_request)
    artifact = store.persist(context=context, response=listing_response)
    payload = artifact.payload_path.read_bytes()

    print(f"Listing status: {listing_response.status_code}")
    print(f"Listing raw bytes: {len(listing_response.payload)}")
    print(f"Temporary raw path: {artifact.payload_path}")
    print(f"Temporary metadata path: {artifact.metadata_path}")

    assert listing_response.status_code == 200
    assert artifact.source_id == "remax"
    assert artifact.target_id == listing_target.target_id
    assert artifact.target_kind == "listing_detail"
    assert artifact.media_type in {"text/html", "application/octet-stream", None}
    assert listing_target.metadata["slug"].encode() in payload
    assert artifact.metadata_path.exists()
