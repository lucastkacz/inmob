"""Zonaprop Bronze source adapter backed by the postings API."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from time import perf_counter
from typing import Any
from urllib.parse import urljoin, urlparse

from curl_cffi import requests as curl_requests
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
from inmob.bronze.sources.zonaprop.search import (
    ZONAPROP_API_POSTINGS_URL,
    ZONAPROP_HOME_URL,
    ZonapropSearchCriteria,
)
from inmob.bronze.traffic import TrafficController
from inmob.bronze.traffic.controller import TrafficSnapshot


_LISTING_ID_PATTERN = re.compile(r"-(?P<id>\d+)\.html$", re.IGNORECASE)
_EMBEDDED_PAYLOAD_METADATA_KEY = "embedded_payload"


class ZonapropSource:
    """Zonaprop raw acquisition source."""

    DEFAULT_HEADERS = {
        "accept": "*/*",
        "accept-language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "content-type": "application/json",
        "origin": "https://www.zonaprop.com.ar",
        "referer": ZONAPROP_HOME_URL,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) "
            "Gecko/20100101 Firefox/126.0"
        ),
    }

    def __init__(
        self,
        targets: Sequence[BronzeTarget] = (),
        timeout_seconds: float = 30.0,
        traffic_controller: TrafficController | None = None,
    ) -> None:
        definition = SourceDefinition(
            source_id="zonaprop",
            display_name="Zonaprop",
            homepage_url=ZONAPROP_HOME_URL,
            allowed_domains=("zonaprop.com.ar", "www.zonaprop.com.ar"),
        )
        self._runtime = WebSourceRuntime(
            definition=definition,
            targets=targets,
            default_headers=self.DEFAULT_HEADERS,
            timeout_seconds=timeout_seconds,
            traffic_controller=traffic_controller,
        )
        self._timeout_seconds = timeout_seconds
        self._scraper: Any | None = None

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
        """Fetch one raw Zonaprop payload without browser rendering."""

        embedded_payload = request.target.metadata.get(_EMBEDDED_PAYLOAD_METADATA_KEY)
        if embedded_payload is not None:
            return self._embedded_listing_response(request, embedded_payload)
        if request.target.kind == TargetKind.API_ENDPOINT:
            return self._fetch_api(request)

        raise ValueError(
            "Zonaprop listing details are captured from the postings API search response; "
            "build targets through discover_listing_targets() instead of fetching public HTML."
        )

    def close(self) -> None:
        if self._scraper is not None:
            self._scraper.close()
            self._scraper = None
        self._runtime.close()

    def __enter__(self) -> ZonapropSource:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def traffic_snapshot(self) -> TrafficSnapshot:
        return self._runtime.traffic_snapshot()

    def reset_traffic_stats(self) -> None:
        self._runtime.reset_traffic_stats()

    @classmethod
    def listing_target(
        cls,
        *,
        listing_id: str,
        public_url: str,
        posting_payload: dict[str, object] | None = None,
    ) -> BronzeTarget:
        """Build a Bronze target for a Zonaprop listing API payload."""

        metadata = {
            "listing_id": listing_id,
            "api_payload": "embedded_search_posting",
            "api_url": ZONAPROP_API_POSTINGS_URL,
            "public_url": public_url,
        }
        if posting_payload is not None:
            metadata[_EMBEDDED_PAYLOAD_METADATA_KEY] = json.dumps(
                posting_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )

        return BronzeTarget(
            target_id=f"zonaprop-listing-{listing_id}",
            kind=TargetKind.LISTING_DETAIL,
            uri=public_url,
            metadata=metadata,
        )

    def listing_target_from_url(self, url: str) -> BronzeTarget:
        """Build a public listing target placeholder from a Zonaprop URL."""

        public_url = _normalize_public_url(url)
        listing_id = _listing_id_from_public_url(public_url)
        if listing_id is None:
            raise ValueError(f"URL is not a Zonaprop listing detail URL: {url}")
        return self.listing_target(listing_id=listing_id, public_url=public_url)

    @classmethod
    def search_target(
        cls,
        *,
        criteria: ZonapropSearchCriteria,
        page: int,
    ) -> BronzeTarget:
        """Build a Bronze target for one Zonaprop postings API page."""

        return BronzeTarget(
            target_id=f"zonaprop-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.API_ENDPOINT,
            uri=ZONAPROP_API_POSTINGS_URL,
            metadata={
                "page": str(page),
                "page_size": str(criteria.page_size),
                "criteria_label": criteria.label or "",
                "api_url": ZONAPROP_API_POSTINGS_URL,
                "public_url": criteria.build_url(page=page),
                "request_body": criteria.build_api_body(page=page).decode("utf-8"),
            },
        )

    @classmethod
    def search_targets(
        cls,
        *,
        criteria: ZonapropSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build API Bronze targets for multiple Zonaprop search pages."""

        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[BronzeTarget, ...]:
        """Discover listing-detail payloads from a Zonaprop postings API response."""

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
                "Zonaprop discovery skipped because payload is not JSON payload_bytes={}",
                len(text.encode("utf-8")),
            )
            return ()

        postings = decoded.get("listPostings")
        if not isinstance(postings, list):
            discovery_logger.warning(
                "Zonaprop discovery skipped because listPostings is missing or invalid type={}",
                type(postings).__name__,
            )
            return ()

        discovered: list[BronzeTarget] = []
        seen: set[str] = set()
        skipped_items = 0
        duplicate_items = 0
        for posting in postings:
            if not isinstance(posting, dict):
                skipped_items += 1
                continue

            listing_id = _listing_id_from_posting(posting)
            public_url = _public_url_from_posting(posting)
            if listing_id is None or public_url is None:
                skipped_items += 1
                continue
            if public_url in seen:
                duplicate_items += 1
                continue

            seen.add(public_url)
            discovered.append(
                self.listing_target(
                    listing_id=listing_id,
                    public_url=public_url,
                    posting_payload=posting,
                )
            )

        discovery_logger.info(
            "Zonaprop API discovery completed postings={} discovered={} skipped={} duplicates={}",
            len(postings),
            len(discovered),
            skipped_items,
            duplicate_items,
        )
        return tuple(discovered)

    def _embedded_listing_response(
        self,
        request: BronzeRequest,
        embedded_payload: str,
    ) -> BronzeResponse:
        metadata = dict(request.target.metadata)
        metadata.pop(_EMBEDDED_PAYLOAD_METADATA_KEY, None)
        sanitized_target = request.target.model_copy(update={"metadata": metadata})
        sanitized_request = request.model_copy(update={"target": sanitized_target})
        payload = embedded_payload.encode("utf-8")
        public_url = metadata.get("public_url") or request.target.uri

        return BronzeResponse(
            request=sanitized_request,
            status_code=200,
            final_uri=public_url,
            media_type="application/json",
            headers={},
            capture_metadata={
                "capture_strategy": "zonaprop_postings_api_embedded_listing",
                "api_url": ZONAPROP_API_POSTINGS_URL,
            },
            payload=payload,
        )

    def _fetch_api(self, request: BronzeRequest) -> BronzeResponse:
        if request.source_id != self.definition.source_id:
            raise ValueError(
                f"request source_id {request.source_id!r} does not match "
                f"source_id {self.definition.source_id!r}"
            )
        self._runtime.ensure_allowed_uri(request.target.uri)

        source_id = self.definition.source_id
        request_logger = logger.bind(
            source_id=source_id,
            target_id=request.target.target_id,
            target_kind=request.target.kind.value,
        )
        if self._scraper is None:
            request_logger.debug("Creating curl_cffi session for Zonaprop API")
            self._scraper = curl_requests.Session(impersonate="chrome136")
        scraper = self._scraper

        started_at = perf_counter()
        request_logger.info(
            "Fetching target method={} uri={} transport=curl_cffi",
            request.method.value,
            request.target.uri,
        )
        try:
            response = self._runtime._traffic.request(
                lambda: scraper.request(
                    method=request.method.value,
                    url=request.target.uri,
                    headers=request.headers,
                    params=request.query_params or None,
                    data=request.body,
                    timeout=self._timeout_seconds,
                ),
                log_context={
                    "source_id": source_id,
                    "target_id": request.target.target_id,
                    "target_kind": request.target.kind.value,
                },
            )
        except Exception:
            elapsed_seconds = perf_counter() - started_at
            request_logger.exception(
                "Fetch failed method={} uri={} elapsed_seconds={}",
                request.method.value,
                request.target.uri,
                round(elapsed_seconds, 3),
            )
            raise

        media_type = response.headers.get("content-type")
        if media_type is not None:
            media_type = media_type.split(";", maxsplit=1)[0].strip().lower()

        self._runtime.ensure_allowed_uri(str(response.url))
        elapsed_seconds = perf_counter() - started_at
        log_method = request_logger.warning if response.status_code >= 400 else request_logger.info
        log_method(
            "Fetched target status_code={} media_type={} payload_bytes={} final_uri={} "
            "elapsed_seconds={}",
            response.status_code,
            media_type,
            len(response.content),
            str(response.url),
            round(elapsed_seconds, 3),
        )

        return BronzeResponse(
            request=request,
            status_code=response.status_code,
            final_uri=str(response.url),
            media_type=media_type,
            headers=dict(response.headers),
            capture_metadata={"transport": "curl_cffi", "impersonate": "chrome136"},
            payload=response.content,
        )


def _public_url_from_posting(posting: dict[str, object]) -> str | None:
    raw_url = posting.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None
    return _normalize_public_url(raw_url)


def _normalize_public_url(candidate: str) -> str:
    absolute = urljoin(ZONAPROP_HOME_URL, candidate)
    parsed = urlparse(absolute)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"zonaprop.com.ar", "www.zonaprop.com.ar"}:
        raise ValueError(f"URL is not a Zonaprop URL: {candidate}")
    return absolute


def _listing_id_from_posting(posting: dict[str, object]) -> str | None:
    for key in ("postingId", "postingCode", "id"):
        value = posting.get(key)
        if value is not None:
            return str(value)
    public_url = _public_url_from_posting(posting)
    if public_url is None:
        return None
    return _listing_id_from_public_url(public_url)


def _listing_id_from_public_url(public_url: str) -> str | None:
    match = _LISTING_ID_PATTERN.search(urlparse(public_url).path)
    return match.group("id") if match else None
