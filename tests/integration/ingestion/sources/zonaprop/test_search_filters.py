from inmob.ingestion.contracts import IngestionRunContext, TargetKind
from inmob.ingestion.sources import ZonapropSearchCriteria, ZonapropSource


def test_zonaprop_capital_federal_sale_search_discovers_listing_links() -> None:
    criteria = ZonapropSearchCriteria(
        operation="venta",
        location="capital-federal",
        property_type="departamentos",
        sort="publicado-descendente",
        label="capital-federal-apartment-sale",
    )
    target = ZonapropSource.search_target(criteria=criteria, page=1)
    source = ZonapropSource(targets=(target,))
    context = IngestionRunContext(run_id="integration-zonaprop-capital-federal-search")

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
    assert target.uri == "https://www.zonaprop.com.ar/departamentos-venta-capital-federal.html?sort_by=publicado-descendente"
    
    # Assert pagination URL is constructed properly with pagina-{page} path segment
    assert ZonapropSource.search_target(criteria=criteria, page=2).uri == (
        "https://www.zonaprop.com.ar/departamentos-venta-capital-federal-pagina-2.html?sort_by=publicado-descendente"
    )

    assert len(listing_targets) >= 20
    assert all(
        target.uri.startswith("https://www.zonaprop.com.ar/propiedades/")
        for target in listing_targets
    )
    assert all(target.kind == TargetKind.LISTING_DETAIL for target in listing_targets)
    assert all(target.metadata["listing_id"] for target in listing_targets)
    assert all(target.metadata["kind"] for target in listing_targets)
    assert all(target.metadata["slug"] for target in listing_targets)
