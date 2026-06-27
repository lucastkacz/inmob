"""Argenprop Bronze source adapter.

This module owns Argenprop-specific acquisition rules: URL construction,
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
from inmob.bronze.sources.argenprop.search import (
    ARGENPROP_HOME_URL,
    ArgenpropSearchCriteria,
)
from inmob.bronze.sources.base import WebSourceRuntime
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

_LISTING_PATH_PATTERN = re.compile(
    r"(?:https?://(?:www\.)?argenprop\.com)?"
    r"(?P<path>/[a-z0-9][a-z0-9-]*-en-[a-z0-9-]+[^\"'<>\\\s?]*--(?P<id>\d+))",
    re.IGNORECASE,
)


class ArgenpropSource:
    """Argenprop raw acquisition source."""

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
            source_id="argenprop",
            display_name="Argenprop",
            homepage_url=ARGENPROP_HOME_URL,
            allowed_domains=("argenprop.com", "www.argenprop.com"),
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

    def __enter__(self) -> ArgenpropSource:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def traffic_snapshot(self) -> TrafficSnapshot:
        return self._runtime.traffic_snapshot()

    def reset_traffic_stats(self) -> None:
        self._runtime.reset_traffic_stats()

    @classmethod
    def listing_target(cls, *, listing_id: str, path: str) -> BronzeTarget:
        """Build a Bronze target for an Argenprop listing detail page."""

        normalized_url = _path_to_url(path)
        slug = normalized_url.rstrip("/").split("/")[-1]
        return BronzeTarget(
            target_id=f"argenprop-listing-{listing_id}",
            kind=TargetKind.LISTING_DETAIL,
            uri=normalized_url,
            metadata={
                "listing_id": listing_id,
                "slug": slug,
            },
        )

    def listing_target_from_url(self, url: str) -> BronzeTarget:
        """Build a listing target from a normalized Argenprop listing URL."""

        normalized = _normalize_listing_url(url)
        if normalized is None:
            raise ValueError(f"URL is not an Argenprop listing detail URL: {url}")
        listing_id = normalized.rsplit("--", maxsplit=1)[-1]
        path = urlparse(normalized).path
        return self.listing_target(listing_id=listing_id, path=path)

    @classmethod
    def search_target(
        cls,
        *,
        criteria: ArgenpropSearchCriteria,
        page: int,
    ) -> BronzeTarget:
        """Build a Bronze target for one Argenprop search-results page."""

        return BronzeTarget(
            target_id=f"argenprop-search-{criteria.target_key()}-page-{page}",
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
        criteria: ArgenpropSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build Bronze targets for multiple Argenprop search-results pages."""

        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[BronzeTarget, ...]:
        """Discover listing-detail targets from raw Argenprop search HTML."""

        discovery_logger = logger.bind(source_id=self.definition.source_id)
        html = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )

        parser = _ArgenpropListingLinkParser()
        parser.feed(html)

        discovered_urls: list[str] = []
        seen: set[str] = set()
        script_candidates = tuple(
            _path_to_url(match.group("path")) for match in _LISTING_PATH_PATTERN.finditer(html)
        )
        rejected_candidates = 0
        duplicate_candidates = 0

        for candidate in [*parser.hrefs, *script_candidates]:
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
            "Argenprop HTML discovery completed href_candidates={} regex_candidates={} "
            "discovered={} rejected={} duplicates={}",
            len(parser.hrefs),
            len(script_candidates),
            len(discovered_urls),
            rejected_candidates,
            duplicate_candidates,
        )
        return tuple(self.listing_target_from_url(url) for url in discovered_urls)


class _ArgenpropListingLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _path_to_url(path: str) -> str:
    return urljoin(ARGENPROP_HOME_URL, path)


def _normalize_listing_url(candidate: str) -> str | None:
    absolute = urljoin(ARGENPROP_HOME_URL, candidate)
    parsed = urlparse(absolute)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"argenprop.com", "www.argenprop.com"}:
        return None

    path = parsed.path.rstrip("/")
    if "/" in path.removeprefix("/"):
        return None

    match = _LISTING_PATH_PATTERN.fullmatch(path)
    if match is None:
        return None

    return f"https://www.argenprop.com{path}"
