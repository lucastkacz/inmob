from inmob.ingestion.contracts import IngestionRunContext, TargetKind
from inmob.ingestion.sources import RemaxSearchCriteria, RemaxSource


CAPITAL_FEDERAL_LOCATION_FILTER = "in:CF@<b>Capital</b> <b>F</b>ederal::::::"


def test_remax_capital_federal_filter_discovers_first_page_listing_links() -> None:
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
    target = RemaxSource.search_target(criteria=criteria, page=0)
    source = RemaxSource(targets=(target,))
    context = IngestionRunContext(run_id="integration-remax-capital-federal-search")

    request = next(iter(source.plan_requests(context)))
    response = source.fetch(request)
    listing_targets = source.discover_listing_targets(response.payload)

    print(f"Filtered search URL: {request.target.uri}")
    print(f"Filtered search status: {response.status_code}")
    print(f"Filtered search raw bytes: {len(response.payload)}")
    print(f"Discovered filtered listings: {len(listing_targets)}")
    for index, listing_target in enumerate(listing_targets[:5], start=1):
        print(f"Filtered listing {index}: {listing_target.uri}")

    assert response.status_code == 200
    assert target.metadata["criteria_label"] == "capital-federal-buy"
    assert "page=0" in target.uri
    assert "pageSize=24" in target.uri
    assert "locations=in%3ACF%40%3Cb%3ECapital%3C%2Fb%3E" in target.uri
    assert listing_targets
    assert all(
        target.uri.startswith("https://www.remax.com.ar/listings/")
        for target in listing_targets
    )
    assert all(target.kind == TargetKind.LISTING_DETAIL for target in listing_targets)
