"""RE/MAX Argentina Bronze source adapter.

This module owns RE/MAX-specific acquisition rules: URL construction,
source identity, and technical listing discovery. It deliberately avoids
extracting real estate facts such as price, area, rooms, or address.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from inmob.ingestion.contracts import (
    IngestionTarget,
    PolitenessProfile,
    SourceDefinition,
    TargetKind,
)
from inmob.ingestion.sources.base import RealEstateWebSource
from inmob.ingestion.sources.remax.search import (
    REMAX_BUY_PATH,
    REMAX_HOME_URL,
    RemaxSearchCriteria,
)


DEFAULT_POLITENESS = PolitenessProfile(requests_per_minute=20, burst_size=3)

_LISTING_PATH_PATTERN = re.compile(
    r"(?:https?://(?:www\.)?remax\.com\.ar)?"
    r"(?P<path>/listings/[A-Za-z0-9][^\"'<>\\\s?]*)"
)
_LISTING_SLUG_PATTERN = re.compile(r'"slug"\s*:\s*"(?P<slug>[a-z0-9][a-z0-9-]*)"')


class RemaxSource(RealEstateWebSource):
    """RE/MAX Argentina raw acquisition source."""

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
    ) -> None:
        super().__init__(targets=targets, timeout_seconds=timeout_seconds)
        self._definition = SourceDefinition(
            source_id="remax",
            display_name="RE/MAX Argentina",
            homepage_url=REMAX_HOME_URL,
            allowed_domains=("remax.com.ar", "www.remax.com.ar"),
            politeness=DEFAULT_POLITENESS,
        )

    @property
    def definition(self) -> SourceDefinition:
        return self._definition

    @property
    def default_headers(self) -> dict[str, str]:
        return self.DEFAULT_HEADERS

    @classmethod
    def listing_target(cls, *, slug: str, url: str) -> IngestionTarget:
        """Build a Bronze target for a RE/MAX listing detail page."""

        return IngestionTarget(
            target_id=f"remax-listing-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=url,
            metadata={"slug": slug},
        )

    def listing_target_from_url(self, url: str) -> IngestionTarget:
        """Build a listing target from a normalized RE/MAX listing URL."""

        slug = _listing_slug_from_url(url)
        return self.listing_target(slug=slug, url=url)

    @classmethod
    def search_target(cls, *, criteria: RemaxSearchCriteria, page: int) -> IngestionTarget:
        """Build a Bronze target for one RE/MAX search-results page."""

        operation_ids = ",".join(
            str(operation_id) for operation_id in criteria.operation_ids
        )
        return IngestionTarget(
            target_id=f"remax-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.SEARCH_RESULTS,
            uri=criteria.build_url(page=page),
            metadata={
                "operation_ids": operation_ids,
                "page": str(page),
                "page_size": str(criteria.page_size),
                "landing_path": criteria.landing_path or "",
                "criteria_label": criteria.label or "",
            },
        )

    @classmethod
    def search_targets(
        cls,
        *,
        criteria: RemaxSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[IngestionTarget, ...]:
        """Build Bronze targets for multiple RE/MAX search-results pages."""

        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[IngestionTarget, ...]:
        """Discover listing-detail targets from raw RE/MAX search HTML.

        This is Bronze crawl-frontier discovery only. It extracts URLs/slugs so
        the raw detail pages can be landed later; it does not extract property
        attributes.
        """

        html = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )

        parser = _RemaxListingLinkParser()
        parser.feed(html)

        discovered_urls: list[str] = []
        seen: set[str] = set()

        script_candidates = (
            _path_to_url(match.group("path"))
            for match in _LISTING_PATH_PATTERN.finditer(html)
        )
        slug_candidates = (
            _path_to_url(f"/listings/{match.group('slug')}")
            for match in _LISTING_SLUG_PATTERN.finditer(html)
        )

        for candidate in [*parser.hrefs, *script_candidates, *slug_candidates]:
            normalized = _normalize_listing_url(candidate)
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            discovered_urls.append(normalized)

        return tuple(self.listing_target_from_url(url) for url in discovered_urls)


class _RemaxListingLinkParser(HTMLParser):
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
    return urljoin(REMAX_HOME_URL, path)


def _normalize_listing_url(candidate: str) -> str | None:
    absolute = urljoin(REMAX_HOME_URL, candidate)
    parsed = urlparse(absolute)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"remax.com.ar", "www.remax.com.ar"}:
        return None

    path = parsed.path.rstrip("/")
    if not path.startswith("/listings/") or path == REMAX_BUY_PATH:
        return None
    if "/" in path.removeprefix("/listings/"):
        return None
    if "-" not in path.removeprefix("/listings/"):
        return None

    return f"https://www.remax.com.ar{path}"


def _listing_slug_from_url(url: str) -> str:
    normalized = _normalize_listing_url(url)
    if normalized is None:
        raise ValueError(f"URL is not a RE/MAX listing detail URL: {url}")
    return normalized.rstrip("/").split("/")[-1]
