from datetime import UTC, datetime

import pytest

from inmob.ingestion.contracts import IngestionRequest, IngestionResponse, IngestionTarget
from inmob.ingestion.sources import ArgenpropSource, MudafySource, ProperatiSource


@pytest.mark.parametrize(
    ("source", "target"),
    (
        (
            ArgenpropSource(),
            ArgenpropSource.listing_target(
                listing_id="123",
                path="/departamento-en-venta-en-palermo--123",
            ),
        ),
        (
            MudafySource(),
            MudafySource.listing_target(
                listing_id="123",
                category="departamento",
                slug="departamento-palermo",
            ),
        ),
        (ProperatiSource(), ProperatiSource.listing_target(listing_id="abc123")),
    ),
)
def test_html_listing_sources_use_browser_rendering_for_detail_pages(
    monkeypatch: pytest.MonkeyPatch,
    source: ArgenpropSource | MudafySource | ProperatiSource,
    target: IngestionTarget,
) -> None:
    request = source.build_request(target)
    called = False

    def fake_browser_fetch(incoming: IngestionRequest) -> IngestionResponse:
        nonlocal called
        called = True
        return IngestionResponse(
            request=incoming,
            status_code=200,
            final_uri=incoming.target.uri,
            captured_at=datetime.now(UTC),
            media_type="text/html",
            capture_metadata={"render_strategy": "playwright_reveal_v1"},
            payload=b"<html></html>",
        )

    monkeypatch.setattr(source, "fetch_with_browser_rendering", fake_browser_fetch)

    response = source.fetch(request)

    assert called
    assert response.capture_metadata["render_strategy"] == "playwright_reveal_v1"
