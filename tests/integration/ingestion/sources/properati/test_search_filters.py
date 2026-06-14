from inmob.ingestion.contracts import IngestionRunContext, TargetKind
from inmob.ingestion.sources import ProperatiSearchCriteria, ProperatiSource


def test_properati_capital_federal_sale_search_discovers_listing_links() -> None:
    criteria = ProperatiSearchCriteria(
        operation="venta",
        location="capital-federal",
        property_type="departamento",
        sort="published_on_desc",
        label="capital-federal-apartment-sale",
    )
    target = ProperatiSource.search_target(criteria=criteria, page=1)
    source = ProperatiSource(targets=(target,))
    context = IngestionRunContext(run_id="integration-properati-capital-federal-search")

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
    assert target.uri == "https://www.properati.com.ar/s/capital-federal/departamento/venta?sort=published_on_desc"
    
    # Assert pagination URL is constructed properly with page path suffix
    assert ProperatiSource.search_target(criteria=criteria, page=2).uri == (
        "https://www.properati.com.ar/s/capital-federal/departamento/venta/2?sort=published_on_desc"
    )

    assert len(listing_targets) >= 20
    assert all(
        target.uri.startswith("https://www.properati.com.ar/detalle/")
        for target in listing_targets
    )
    assert all(target.kind == TargetKind.LISTING_DETAIL for target in listing_targets)
    assert all(target.metadata["listing_id"] for target in listing_targets)
