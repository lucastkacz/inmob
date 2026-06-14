from inmob.ingestion.contracts import IngestionRunContext, IngestionTarget, TargetKind
from inmob.ingestion.sources import RemaxSource


REMAX_BASE_BUY_URL = "https://www.remax.com.ar/comprar-propiedades"


def test_remax_base_search_page_discovers_first_page_listing_links() -> None:
    search_page = IngestionTarget(
        target_id="remax-base-buy-search-page",
        kind=TargetKind.SEARCH_RESULTS,
        uri=REMAX_BASE_BUY_URL,
    )
    source = RemaxSource(targets=(search_page,))
    context = IngestionRunContext(run_id="integration-remax-base-search")

    request = next(iter(source.plan_requests(context)))
    response = source.fetch(request)
    listing_targets = source.discover_listing_targets(response.payload)

    print(f"Base search URL: {request.target.uri}")
    print(f"Base search status: {response.status_code}")
    print(f"Base search raw bytes: {len(response.payload)}")
    print(f"Discovered base listings: {len(listing_targets)}")
    for index, listing_target in enumerate(listing_targets[:5], start=1):
        print(f"Base listing {index}: {listing_target.uri}")

    assert response.status_code == 200
    assert response.media_type == "text/html"
    assert listing_targets
    assert all(
        target.uri.startswith("https://www.remax.com.ar/listings/")
        for target in listing_targets
    )
    assert all(target.kind == TargetKind.LISTING_DETAIL for target in listing_targets)
