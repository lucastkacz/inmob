"""CabaProp Bronze source adapter.

This module owns CabaProp-specific acquisition rules: URL construction,
source identity, and technical listing discovery. It deliberately avoids
extracting real estate facts such as price, area, rooms, or address.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Sequence
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from loguru import logger

from inmob.bronze.contracts import (
    HttpMethod,
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
from inmob.bronze.sources.cabaprop.search import (
    CABAPROP_API_PROPERTY_URL_TEMPLATE,
    CABAPROP_API_SEARCH_URL,
    CABAPROP_HOME_URL,
    CabapropSearchCriteria,
)
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
    r"(?:https?://(?:www\.)?cabaprop\.com\.ar)?"
    r"(?P<path>/propiedad/(?P<id>[a-f0-9]{24})/[^\"'<>\\\s?]+)",
    re.IGNORECASE,
)
_SLUG_CHARACTER_PATTERN = re.compile(r"[^A-Za-z0-9]+")


class CabapropSource:
    """CabaProp raw acquisition source."""

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
            source_id="cabaprop",
            display_name="CabaProp",
            homepage_url=CABAPROP_HOME_URL,
            allowed_domains=("cabaprop.com.ar", "www.cabaprop.com.ar"),
            politeness=DEFAULT_POLITENESS,
        )
        self._runtime = WebSourceRuntime(
            definition=definition,
            targets=targets,
            default_headers=self.DEFAULT_HEADERS,
            headers_for_target=self.headers_for_target,
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

    def headers_for_target(self, target: BronzeTarget) -> dict[str, str]:
        if target.kind == TargetKind.API_ENDPOINT:
            return {
                **self.DEFAULT_HEADERS,
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
            }
        return self.DEFAULT_HEADERS

    def build_request(self, target: BronzeTarget) -> BronzeRequest:
        request = self._runtime.build_request(target)
        if target.kind != TargetKind.API_ENDPOINT:
            return request

        body = target.metadata.get("request_body")
        if body is None:
            return request

        return request.model_copy(
            update={
                "method": HttpMethod.POST,
                "body": body.encode("utf-8"),
            }
        )

    def fetch(self, request: BronzeRequest) -> BronzeResponse:
        return self._runtime.fetch_http(request)

    def close(self) -> None:
        self._runtime.close()

    def __enter__(self) -> CabapropSource:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def traffic_snapshot(self) -> TrafficSnapshot:
        return self._runtime.traffic_snapshot()

    def reset_traffic_stats(self) -> None:
        self._runtime.reset_traffic_stats()

    @classmethod
    def listing_target(cls, *, listing_id: str, title: str | None = None) -> BronzeTarget:
        """Build a Bronze target for a CabaProp listing detail API payload."""

        metadata = {
            "listing_id": listing_id,
            "api_payload": "listing_detail",
        }
        if title:
            slug = _slugify_title(title)
            metadata["slug"] = slug
            metadata["public_url"] = _path_to_url(f"/propiedad/{listing_id}/{slug}")

         # target_id matches cabaprop-listing-{id} to preserve original convention
        return BronzeTarget(
            target_id=f"cabaprop-listing-{listing_id}",
            kind=TargetKind.API_ENDPOINT,
            uri=CABAPROP_API_PROPERTY_URL_TEMPLATE.format(listing_id=listing_id),
            metadata=metadata,
        )

    # Alias for backward compatibility
    api_listing_target = listing_target

    def listing_target_from_url(self, url: str) -> BronzeTarget:
        """Build a listing target from a normalized CabaProp listing URL."""

        normalized = _normalize_listing_url(url)
        if normalized is None:
            raise ValueError(f"URL is not a CabaProp listing detail URL: {url}")
        parsed = urlparse(normalized)
        parts = parsed.path.strip("/").split("/")
        title = parts[2] if len(parts) > 2 else None
        return self.listing_target(listing_id=parts[1], title=title)

    @classmethod
    def search_target(
        cls,
        *,
        criteria: CabapropSearchCriteria,
        page: int,
    ) -> BronzeTarget:
        """Build a Bronze target for one public CabaProp search page."""

        return BronzeTarget(
            target_id=f"cabaprop-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.SEARCH_RESULTS,
            uri=criteria.build_url(page=page),
            metadata={
                "page": str(page),
                "page_size": str(criteria.page_size),
                "criteria_label": criteria.label or "",
            },
        )

    @classmethod
    def api_search_target(
        cls,
        *,
        criteria: CabapropSearchCriteria,
        page: int,
    ) -> BronzeTarget:
        """Build a Bronze target for one CabaProp API search page."""

        return BronzeTarget(
            target_id=f"cabaprop-api-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.API_ENDPOINT,
            uri=criteria.build_api_url(page=page),
            metadata={
                "page": str(page),
                "page_size": str(criteria.page_size),
                "criteria_label": criteria.label or "",
                "api_url": CABAPROP_API_SEARCH_URL,
                "public_url": criteria.build_url(page=page),
                "request_body": criteria.build_api_body().decode("utf-8"),
            },
        )

    @classmethod
    def search_targets(
        cls,
        *,
        criteria: CabapropSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build public Bronze targets for multiple CabaProp search pages."""

        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    @classmethod
    def api_search_targets(
        cls,
        *,
        criteria: CabapropSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build API Bronze targets for multiple CabaProp search pages."""

        return tuple(cls.api_search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[BronzeTarget, ...]:
        """Discover listing-detail targets from raw CabaProp search payloads."""

        discovery_logger = logger.bind(source_id=self.definition.source_id)
        text = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            discovery_logger.warning(
                "CabaProp discovery skipped because payload is not JSON payload_bytes={}",
                len(text.encode("utf-8")),
            )
            return ()

        result = decoded.get("result")
        if not isinstance(result, list):
            discovery_logger.warning(
                "CabaProp discovery skipped because result is not a list result_type={}",
                type(result).__name__,
            )
            return ()

        discovered: list[BronzeTarget] = []
        seen: set[str] = set()
        skipped_items = 0
        duplicate_items = 0
        for item in result:
            if not isinstance(item, dict):
                skipped_items += 1
                continue
            listing_id = item.get("_id")
            title = item.get("title")
            if not isinstance(listing_id, str) or not listing_id:
                skipped_items += 1
                continue
            if listing_id in seen:
                duplicate_items += 1
                continue
            seen.add(listing_id)
            discovered.append(self.listing_target(listing_id=listing_id, title=title))

        discovery_logger.info(
            "CabaProp API discovery completed result_items={} discovered={} skipped={} duplicates={}",
            len(result),
            len(discovered),
            skipped_items,
            duplicate_items,
        )
        return tuple(discovered)

    # Alias for backward compatibility
    discover_api_listing_targets = discover_listing_targets


class _CabapropListingLinkParser(HTMLParser):
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
    return urljoin(CABAPROP_HOME_URL, path)


def _normalize_listing_url(candidate: str) -> str | None:
    absolute = urljoin(CABAPROP_HOME_URL, candidate)
    parsed = urlparse(absolute)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"cabaprop.com.ar", "www.cabaprop.com.ar"}:
        return None

    path = parsed.path.rstrip("/")
    match = _LISTING_PATH_PATTERN.fullmatch(path)
    if match is None:
        return None

    return f"https://cabaprop.com.ar{path}"


def _slugify_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", errors="ignore").decode("ascii")
    slug = _SLUG_CHARACTER_PATTERN.sub("-", ascii_title).strip("-")
    return slug or "propiedad"
