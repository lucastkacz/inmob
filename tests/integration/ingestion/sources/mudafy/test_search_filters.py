from inmob.ingestion.contracts import IngestionRunContext, TargetKind
from inmob.ingestion.sources import MudafySearchCriteria, MudafySource


def test_mudafy_caba_sale_search_discovers_listing_links() -> None:
    criteria = MudafySearchCriteria(
        operation="venta",
        location="caba",
        property_type="departamentos",
        sort="published_at:desc:nulls_last",
        label="caba-apartment-sale",
    )
    target = MudafySource.search_target(criteria=criteria, page=1)
    source = MudafySource(targets=(target,))
    context = IngestionRunContext(run_id="integration-mudafy-caba-search")

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
    assert target.uri == "https://mudafy.com.ar/venta/departamentos/caba?sort=published_at%3Adesc%3Anulls_last"
    
    # Assert pagination URL is constructed properly with /page-p suffix
    assert MudafySource.search_target(criteria=criteria, page=2).uri == (
        "https://mudafy.com.ar/venta/departamentos/caba/2-p?sort=published_at%3Adesc%3Anulls_last"
    )

    assert len(listing_targets) >= 20
    assert all(
        target.uri.startswith("https://mudafy.com.ar/")
        for target in listing_targets
    )
    assert all(target.kind == TargetKind.LISTING_DETAIL for target in listing_targets)
    assert all(target.metadata["listing_id"] for target in listing_targets)
