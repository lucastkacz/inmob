from inmob.ingestion.contracts import IngestionRunContext, TargetKind
from inmob.ingestion.sources import ArgenpropSearchCriteria, ArgenpropSource


def test_argenprop_capital_federal_sale_search_discovers_listing_links() -> None:
    criteria = ArgenpropSearchCriteria(
        property_type="departamentos",
        operation="venta",
        location="capital-federal",
        label="capital-federal-apartment-sale",
    )
    target = ArgenpropSource.search_target(criteria=criteria, page=1)
    source = ArgenpropSource(targets=(target,))
    context = IngestionRunContext(run_id="integration-argenprop-capital-federal-search")

    request = next(iter(source.plan_requests(context)))
    response = source.fetch(request)
    listing_targets = source.discover_listing_targets(response.payload)

    print(f"Search URL: {request.target.uri}")
    print(f"Search status: {response.status_code}")
    print(f"Search raw bytes: {len(response.payload)}")
    print(f"Discovered listings: {len(listing_targets)}")
    for index, listing_target in enumerate(listing_targets[:5], start=1):
        print(f"Listing {index}: {listing_target.uri}")

    assert response.status_code == 200
    assert response.media_type == "text/html"
    assert target.uri == "https://www.argenprop.com/departamentos/venta/capital-federal"
    assert ArgenpropSource.search_target(criteria=criteria, page=2).uri.endswith("?pagina-2")
    sorted_criteria = ArgenpropSearchCriteria(
        property_type="departamentos",
        operation="venta",
        location="capital-federal",
        sort="masnuevos",
    )
    assert (
        ArgenpropSource.search_target(criteria=sorted_criteria, page=1).uri
        == "https://www.argenprop.com/departamentos/venta/capital-federal?orden-masnuevos"
    )
    assert ArgenpropSource.search_target(criteria=sorted_criteria, page=2).uri.endswith(
        "?orden-masnuevos&pagina-2"
    )
    assert len(listing_targets) >= 10
    assert all(
        target.uri.startswith("https://www.argenprop.com/")
        for target in listing_targets
    )
    assert all("--" in target.uri for target in listing_targets)
    assert all(target.kind == TargetKind.LISTING_DETAIL for target in listing_targets)
