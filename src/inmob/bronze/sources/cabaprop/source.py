"""CabaProp Bronze source adapter.

This module owns CabaProp-specific acquisition rules: URL construction,
source identity, and technical listing discovery. It deliberately avoids
extracting real estate facts such as price, area, rooms, or address.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from urllib.parse import urlparse

from loguru import logger

from inmob.bronze.contracts import (
    HttpMethod,
    BronzeRequest,
    BronzeResponse,
    BronzeRunContext,
    BronzeTarget,
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


_LISTING_PATH_PATTERN = re.compile(
    r"^/propiedad/(?P<id>[a-f0-9]{24})(?:/[^/?#]+)?/?$",
    re.IGNORECASE,
)


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
    def listing_target(cls, *, listing_id: str) -> BronzeTarget:
        """Build a Bronze target for a CabaProp listing detail API payload."""

        return BronzeTarget(
            target_id=f"cabaprop-listing-{listing_id}",
            kind=TargetKind.API_ENDPOINT,
            uri=CABAPROP_API_PROPERTY_URL_TEMPLATE.format(listing_id=listing_id),
            metadata={
                "listing_id": listing_id,
                "api_payload": "listing_detail",
            },
        )

    def listing_target_from_url(self, url: str) -> BronzeTarget:
        """Build an API listing target from a public CabaProp listing URL."""

        listing_id = _listing_id_from_url(url)
        return self.listing_target(listing_id=listing_id)

    @classmethod
    def search_target(
        cls,
        *,
        criteria: CabapropSearchCriteria,
        page: int,
    ) -> BronzeTarget:
        """Build a Bronze target for one CabaProp API search page."""

        return BronzeTarget(
            target_id=f"cabaprop-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.API_ENDPOINT,
            uri=criteria.build_api_url(page=page),
            metadata={
                "page": str(page),
                "page_size": str(criteria.page_size),
                "criteria_label": criteria.label or "",
                "api_url": CABAPROP_API_SEARCH_URL,
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
        """Build API Bronze targets for multiple CabaProp search pages."""

        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

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
            if not isinstance(listing_id, str) or not listing_id:
                skipped_items += 1
                continue
            if listing_id in seen:
                duplicate_items += 1
                continue
            seen.add(listing_id)
            discovered.append(self.listing_target(listing_id=listing_id))

        discovery_logger.info(
            "CabaProp API discovery completed result_items={} discovered={} skipped={} duplicates={}",
            len(result),
            len(discovered),
            skipped_items,
            duplicate_items,
        )
        return tuple(discovered)


def _listing_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"cabaprop.com.ar", "www.cabaprop.com.ar"}:
        raise ValueError(f"URL is not a CabaProp listing detail URL: {url}")
    match = _LISTING_PATH_PATTERN.fullmatch(parsed.path)
    if match is None:
        raise ValueError(f"URL is not a CabaProp listing detail URL: {url}")
    return match.group("id")
