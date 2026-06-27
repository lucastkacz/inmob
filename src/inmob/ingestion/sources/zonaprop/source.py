"""Zonaprop Bronze source adapter.

This module owns Zonaprop-specific acquisition rules: URL construction,
source identity, and technical listing discovery. It deliberately avoids
extracting real estate facts such as price, area, rooms, or address.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from loguru import logger

from inmob.ingestion.contracts import (
    IngestionRequest,
    IngestionResponse,
    IngestionTarget,
    PolitenessProfile,
    RetryProfile,
    SourceDefinition,
    TargetKind,
)
from inmob.ingestion.sources.base import RealEstateWebSource
from inmob.ingestion.sources.zonaprop.search import ZONAPROP_HOME_URL, ZonapropSearchCriteria
from inmob.ingestion.traffic import TrafficController


DEFAULT_POLITENESS = PolitenessProfile(
    requests_per_minute=20,
    burst_size=2,
    retry=RetryProfile(
        max_attempts=3,
        initial_delay_seconds=1.0,
        max_delay_seconds=20.0,
    ),
)

class ZonapropSource(RealEstateWebSource):
    """Zonaprop raw acquisition source."""

    DEFAULT_HEADERS = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "es-AR,es;q=0.9,en;q=0.8",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
    }

    def __init__(
        self,
        targets: Sequence[IngestionTarget] = (),
        timeout_seconds: float = 30.0,
        traffic_controller: TrafficController | None = None,
    ) -> None:
        super().__init__(
            targets=targets,
            timeout_seconds=timeout_seconds,
            traffic_controller=traffic_controller,
        )
        self._definition = SourceDefinition(
            source_id="zonaprop",
            display_name="Zonaprop",
            homepage_url=ZONAPROP_HOME_URL,
            allowed_domains=("zonaprop.com.ar", "www.zonaprop.com.ar"),
            politeness=DEFAULT_POLITENESS,
        )

    @property
    def definition(self) -> SourceDefinition:
        return self._definition

    @property
    def default_headers(self) -> dict[str, str]:
        return self.DEFAULT_HEADERS

    def fetch(self, request: IngestionRequest) -> IngestionResponse:
        """Fetch one raw payload using headless Playwright."""
        return self.fetch_with_browser_rendering(request)

    @classmethod
    def listing_target(cls, *, listing_id: str, kind: str, slug: str) -> IngestionTarget:
        """Build a Bronze target for a Zonaprop listing detail page."""
        return IngestionTarget(
            target_id=f"zonaprop-listing-{listing_id}",
            kind=TargetKind.LISTING_DETAIL,
            uri=f"https://www.zonaprop.com.ar/propiedades/{kind}/{slug}-{listing_id}.html",
            metadata={
                "listing_id": listing_id,
                "slug": slug,
                "kind": kind,
            },
        )

    def listing_target_from_url(self, url: str) -> IngestionTarget:
        """Build a listing target from a normalized Zonaprop listing URL."""
        normalized = _normalize_listing_url(url)
        if normalized is None:
            raise ValueError(f"URL is not a Zonaprop listing detail URL: {url}")
        
        parsed = urlparse(normalized)
        path = parsed.path.strip("/")
        match = re.match(
            r"^propiedades/(?P<kind>[a-zA-Z0-9-]+)/(?P<slug>[a-zA-Z0-9-]+)-(?P<id>\d+)\.html$",
            path,
        )
        if not match:
            raise ValueError(f"URL is not a Zonaprop listing detail URL: {url}")
            
        listing_id = match.group("id")
        kind = match.group("kind")
        slug = match.group("slug")
        return self.listing_target(listing_id=listing_id, kind=kind, slug=slug)

    @classmethod
    def search_target(
        cls,
        *,
        criteria: ZonapropSearchCriteria,
        page: int,
    ) -> IngestionTarget:
        """Build a Bronze target for one Zonaprop search-results page."""
        return IngestionTarget(
            target_id=f"zonaprop-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.SEARCH_RESULTS,
            uri=criteria.build_url(page=page),
            metadata={
                "page": str(page),
                "page_size": str(criteria.page_size),
                "criteria_label": criteria.label or "",
            },
        )

    @classmethod
    def search_targets(
        cls,
        *,
        criteria: ZonapropSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[IngestionTarget, ...]:
        """Build Bronze targets for multiple Zonaprop search-results pages."""
        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[IngestionTarget, ...]:
        """Discover listing-detail targets from raw Zonaprop search HTML."""
        discovery_logger = logger.bind(source_id=self.definition.source_id)
        html = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )

        pattern = re.compile(
            r"/propiedades/(?:(?P<kind>[a-zA-Z0-9-]+)/)?(?P<slug>[a-zA-Z0-9-]+)-(?P<id>\d+)\.html",
            re.IGNORECASE,
        )

        discovered_urls: list[str] = []
        seen: set[str] = set()

        parser = _ZonapropListingLinkParser()
        parser.feed(html)

        regex_candidates = tuple(
            f"https://www.zonaprop.com.ar/propiedades/{m.group('kind') or 'clasificado'}/{m.group('slug')}-{m.group('id')}.html"
            for m in pattern.finditer(html)
        )
        rejected_candidates = 0
        duplicate_candidates = 0

        for candidate in [*parser.hrefs, *regex_candidates]:
            normalized = _normalize_listing_url(candidate)
            if normalized is None:
                rejected_candidates += 1
                continue
            if normalized in seen:
                duplicate_candidates += 1
                continue
            seen.add(normalized)
            discovered_urls.append(normalized)

        discovery_logger.info(
            "Zonaprop HTML discovery completed href_candidates={} regex_candidates={} "
            "discovered={} rejected={} duplicates={}",
            len(parser.hrefs),
            len(regex_candidates),
            len(discovered_urls),
            rejected_candidates,
            duplicate_candidates,
        )
        return tuple(self.listing_target_from_url(url) for url in discovered_urls)


class _ZonapropListingLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _normalize_listing_url(candidate: str) -> str | None:
    absolute = urljoin(ZONAPROP_HOME_URL, candidate)
    parsed = urlparse(absolute)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"zonaprop.com.ar", "www.zonaprop.com.ar"}:
        return None

    path = parsed.path.strip("/")
    if not path.startswith("propiedades/"):
        return None

    match = re.match(
        r"^propiedades/(?:(?P<kind>[a-zA-Z0-9-]+)/)?(?P<slug>[a-zA-Z0-9-]+)-(?P<id>\d+)\.html$",
        path,
    )
    if not match:
        return None

    kind = match.group("kind") or "clasificado"
    slug = match.group("slug")
    listing_id = match.group("id")

    return f"https://www.zonaprop.com.ar/propiedades/{kind}/{slug}-{listing_id}.html"
