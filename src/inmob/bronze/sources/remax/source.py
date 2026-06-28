"""RE/MAX Argentina Bronze source adapter.

This module owns RE/MAX-specific acquisition rules: URL construction,
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
    BronzeRequest,
    BronzeResponse,
    BronzeRunContext,
    BronzeTarget,
    SourceDefinition,
    TargetKind,
)
from inmob.bronze.sources.base import WebSourceRuntime
from inmob.bronze.sources.remax.search import (
    REMAX_API_ENTREPRENEURSHIP_BY_SLUG_URL,
    REMAX_API_LISTING_BY_SLUG_URL,
    REMAX_API_SEARCH_URL,
    REMAX_HOME_URL,
    RemaxSearchCriteria,
)
from inmob.bronze.traffic import TrafficController
from inmob.bronze.traffic.controller import TrafficSnapshot


_PUBLIC_LISTING_PATH_PATTERN = re.compile(r"^/listings/(?P<slug>[a-z0-9][a-z0-9-]*)/?$")


class RemaxSource:
    """RE/MAX Argentina raw acquisition source."""

    DEFAULT_HEADERS = {
        "accept": "application/json, text/plain, */*",
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
            source_id="remax",
            display_name="RE/MAX Argentina",
            homepage_url=REMAX_HOME_URL,
            allowed_domains=("api-ar.redremax.com",),
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
        return self._runtime.fetch_http(request)

    def close(self) -> None:
        self._runtime.close()

    def __enter__(self) -> RemaxSource:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def traffic_snapshot(self) -> TrafficSnapshot:
        return self._runtime.traffic_snapshot()

    def reset_traffic_stats(self) -> None:
        self._runtime.reset_traffic_stats()

    @classmethod
    def listing_target(cls, *, slug: str) -> BronzeTarget:
        """Build a Bronze target for one RE/MAX listing detail API payload."""

        return BronzeTarget(
            target_id=f"remax-listing-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=f"{REMAX_API_LISTING_BY_SLUG_URL}/{slug}",
            metadata={
                "slug": slug,
                "api_url": REMAX_API_LISTING_BY_SLUG_URL,
            },
        )

    @classmethod
    def entrepreneurship_target(
        cls,
        *,
        slug: str,
        entity_id: str | None = None,
    ) -> BronzeTarget:
        """Build a Bronze target for one RE/MAX entrepreneurship detail API payload."""

        metadata = {
            "slug": slug,
            "api_url": REMAX_API_ENTREPRENEURSHIP_BY_SLUG_URL,
            "detail_type": "entrepreneurship",
        }
        if entity_id:
            metadata["entity_id"] = entity_id

        return BronzeTarget(
            target_id=f"remax-entrepreneurship-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=f"{REMAX_API_ENTREPRENEURSHIP_BY_SLUG_URL}/{slug}",
            metadata=metadata,
        )

    def listing_target_from_url(self, url: str) -> BronzeTarget:
        """Build a listing API target from a normalized public RE/MAX listing URL."""

        slug = _listing_slug_from_url(url)
        return self.listing_target(slug=slug)

    @classmethod
    def search_target(cls, *, criteria: RemaxSearchCriteria, page: int) -> BronzeTarget:
        """Build a Bronze target for one RE/MAX API search-results page."""

        operation_ids = ",".join(
            str(operation_id) for operation_id in criteria.operation_ids
        )
        return BronzeTarget(
            target_id=f"remax-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.API_ENDPOINT,
            uri=criteria.build_api_url(page=page),
            metadata={
                "operation_ids": operation_ids,
                "page": str(page),
                "page_size": str(criteria.page_size),
                "landing_path": criteria.landing_path or "",
                "criteria_label": criteria.label or "",
                "api_url": REMAX_API_SEARCH_URL,
            },
        )

    @classmethod
    def search_targets(
        cls,
        *,
        criteria: RemaxSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build Bronze API targets for multiple RE/MAX search-results pages."""

        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[BronzeTarget, ...]:
        text = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )
        discovery_logger = logger.bind(source_id=self.definition.source_id)
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            discovery_logger.warning("RE/MAX discovery skipped because payload is not JSON")
            return ()

        data = decoded.get("data")
        if not isinstance(data, dict):
            discovery_logger.debug(
                "RE/MAX API discovery skipped because data is not an object data_type={}",
                type(data).__name__,
            )
            return ()

        items = data.get("data")
        if not isinstance(items, list):
            discovery_logger.debug(
                "RE/MAX API discovery skipped because data.data is not a list items_type={}",
                type(items).__name__,
            )
            return ()

        discovered: list[BronzeTarget] = []
        seen: set[str] = set()
        skipped_items = 0
        duplicate_items = 0
        entrepreneurship_items = 0
        for item in items:
            if not isinstance(item, dict):
                skipped_items += 1
                continue
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug or slug in seen:
                if isinstance(slug, str) and slug in seen:
                    duplicate_items += 1
                else:
                    skipped_items += 1
                continue
            seen.add(slug)
            entity_id = item.get("entityId")
            if item.get("entrepreneurship") is True:
                entrepreneurship_items += 1
                discovered.append(
                    self.entrepreneurship_target(
                        slug=slug,
                        entity_id=entity_id if isinstance(entity_id, str) else None,
                    )
                )
            else:
                discovered.append(self.listing_target(slug=slug))

        discovery_logger.info(
            "RE/MAX API discovery completed items={} discovered={} entrepreneurships={} "
            "skipped={} duplicates={}",
            len(items),
            len(discovered),
            entrepreneurship_items,
            skipped_items,
            duplicate_items,
        )
        return tuple(discovered)


def _listing_slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"remax.com.ar", "www.remax.com.ar"}:
        raise ValueError(f"URL is not a RE/MAX listing detail URL: {url}")
    match = _PUBLIC_LISTING_PATH_PATTERN.fullmatch(parsed.path)
    if match is None:
        raise ValueError(f"URL is not a RE/MAX listing detail URL: {url}")
    return match.group("slug")
