from inmob.ingestion.contracts import IngestionRunContext, TargetKind
from inmob.ingestion.sources import CabapropSearchCriteria, CabapropSource


BELGRANO_BARRIO_ID = 14


def test_cabaprop_belgrano_buy_search_discovers_listing_links() -> None:
    criteria = CabapropSearchCriteria(
        operation="comprar",
        barrios=(BELGRANO_BARRIO_ID,),
        location_slug="belgrano",
        page_size=12,
        label="belgrano-buy",
    )
    target = CabapropSource.api_search_target(criteria=criteria, page=1)
    source = CabapropSource(targets=(target,))
    context = IngestionRunContext(run_id="integration-cabaprop-belgrano-search")

    request = next(iter(source.plan_requests(context)))
    response = source.fetch(request)
    listing_targets = source.discover_listing_targets(response.payload)

    print(f"Search URL: {request.target.uri}")
    print(f"Public URL: {request.target.metadata['public_url']}")
    print(f"Search status: {response.status_code}")
    print(f"Search raw bytes: {len(response.payload)}")
    print(f"Discovered listings: {len(listing_targets)}")
    for index, listing_target in enumerate(listing_targets[:5], start=1):
        print(f"Listing {index}: {listing_target.uri}")

    assert response.status_code == 201
    assert response.media_type == "application/json"
    assert request.target.metadata["public_url"] == (
        "https://cabaprop.com.ar/propiedades/comprar-belgrano?pagina=1"
    )
    assert request.method == "POST"
    assert len(listing_targets) == 12
    assert all(
        target.uri.startswith("https://cabaprop.com.ar/api/v1/properties/")
        for target in listing_targets
    )
    assert all(target.metadata["listing_id"] for target in listing_targets)
    assert all(target.kind == TargetKind.API_ENDPOINT for target in listing_targets)
