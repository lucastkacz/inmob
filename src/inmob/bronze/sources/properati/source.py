"""Properati Bronze source adapter.

This module owns Properati-specific acquisition rules: URL construction,
source identity, and technical listing discovery. It deliberately avoids
extracting real estate facts such as price, area, rooms, or address.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from loguru import logger

from inmob.bronze.contracts import (
    BronzeRequest,
    BronzeResponse,
    BronzeRunContext,
    BronzeTarget,
    PolitenessProfile,
    RetryProfile,
    SourceDefinition,
    TargetKind,
)
from inmob.bronze.sources.base import WebSourceRuntime
from inmob.bronze.sources.properati.search import PROPERATI_HOME_URL, ProperatiSearchCriteria
from inmob.bronze.traffic import TrafficController
from inmob.bronze.traffic.controller import TrafficSnapshot


DEFAULT_POLITENESS = PolitenessProfile(
    requests_per_minute=20,
    burst_size=2,
    retry=RetryProfile(
        max_attempts=3,
        initial_delay_seconds=1.0,
        max_delay_seconds=20.0,
    ),
)


class ProperatiSource:
    """Properati raw acquisition source."""

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
        targets: Sequence[BronzeTarget] = (),
        timeout_seconds: float = 30.0,
        traffic_controller: TrafficController | None = None,
    ) -> None:
        definition = SourceDefinition(
            source_id="properati",
            display_name="Properati",
            homepage_url=PROPERATI_HOME_URL,
            allowed_domains=("properati.com.ar", "www.properati.com.ar"),
            politeness=DEFAULT_POLITENESS,
        )
        self._runtime = WebSourceRuntime(
            definition=definition,
            targets=targets,
            default_headers=self.DEFAULT_HEADERS,
            timeout_seconds=timeout_seconds,
            traffic_controller=traffic_controller,
        )

    @property
    def definition(self) -> SourceDefinition:
        return self._runtime.definition

    @property
    def default_headers(self) -> dict[str, str]:
        return self.DEFAULT_HEADERS

    def plan_requests(self, context: BronzeRunContext) -> Iterable[BronzeRequest]:
        del context
        for target in self._runtime.targets:
            yield self.build_request(target)

    def build_request(self, target: BronzeTarget) -> BronzeRequest:
        return self._runtime.build_request(target)

    def fetch(self, request: BronzeRequest) -> BronzeResponse:
        """Fetch listing details with browser rendering; keep search pages as HTTP."""
        if request.target.kind == TargetKind.LISTING_DETAIL:
            return self._runtime.fetch_browser(request)
        return self._runtime.fetch_http(request)

    def close(self) -> None:
        self._runtime.close()

    def __enter__(self) -> ProperatiSource:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def traffic_snapshot(self) -> TrafficSnapshot:
        return self._runtime.traffic_snapshot()

    def reset_traffic_stats(self) -> None:
        self._runtime.reset_traffic_stats()

    @classmethod
    def listing_target(cls, *, listing_id: str) -> BronzeTarget:
        """Build a Bronze target for a Properati listing detail page."""
        return BronzeTarget(
            target_id=f"properati-listing-{listing_id}",
            kind=TargetKind.LISTING_DETAIL,
            uri=f"https://www.properati.com.ar/detalle/{listing_id}",
            metadata={"listing_id": listing_id},
        )

    def listing_target_from_url(self, url: str) -> BronzeTarget:
        """Build a listing target from a normalized Properati listing URL."""
        normalized = _normalize_listing_url(url)
        if normalized is None:
            raise ValueError(f"URL is not a Properati listing detail URL: {url}")
        parsed = urlparse(normalized)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "detalle":
            raise ValueError(f"URL is not a Properati listing detail URL: {url}")
        listing_id = parts[1]
        return self.listing_target(listing_id=listing_id)

    @classmethod
    def search_target(
        cls,
        *,
        criteria: ProperatiSearchCriteria,
        page: int,
    ) -> BronzeTarget:
        """Build a Bronze target for one Properati search-results page."""
        return BronzeTarget(
            target_id=f"properati-search-{criteria.target_key()}-page-{page}",
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
        criteria: ProperatiSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build Bronze targets for multiple Properati search-results pages."""
        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[BronzeTarget, ...]:
        """Discover listing-detail targets from raw Properati search HTML."""
        discovery_logger = logger.bind(source_id=self.definition.source_id)
        html = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )

        pattern = re.compile(r"/detalle/(?P<id>[a-zA-Z0-9-]+)", re.IGNORECASE)
        
        discovered_urls: list[str] = []
        seen: set[str] = set()

        parser = _ProperatiListingLinkParser()
        parser.feed(html)

        regex_candidates = tuple(
            f"https://www.properati.com.ar/detalle/{m.group('id')}"
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
            "Properati HTML discovery completed href_candidates={} regex_candidates={} "
            "discovered={} rejected={} duplicates={}",
            len(parser.hrefs),
            len(regex_candidates),
            len(discovered_urls),
            rejected_candidates,
            duplicate_candidates,
        )
        return tuple(self.listing_target_from_url(url) for url in discovered_urls)


class _ProperatiListingLinkParser(HTMLParser):
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
    absolute = urljoin(PROPERATI_HOME_URL, candidate)
    parsed = urlparse(absolute)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"properati.com.ar", "www.properati.com.ar"}:
        return None

    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) != 2 or parts[0] != "detalle":
        return None

    listing_id = parts[1]
    if not re.match(r"^[a-zA-Z0-9-]+$", listing_id):
        return None

    return f"https://www.properati.com.ar/detalle/{listing_id}"
