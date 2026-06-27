"""Composable runtime for external real estate web sources."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from time import perf_counter
from typing import ClassVar, Protocol
from urllib.parse import urlparse

import httpx
from loguru import logger

from inmob.bronze.contracts import (
    HttpMethod,
    BronzeRequest,
    BronzeResponse,
    BronzeRunContext,
    BronzeTarget,
    SourceDefinition,
)
from inmob.bronze.sources.browser import fetch_rendered_html
from inmob.bronze.traffic import TrafficController
from inmob.bronze.traffic.controller import TrafficSnapshot


class WebSearchCriteria(Protocol):
    """Criteria for a paginated source search/list page."""

    @property
    def page_size(self) -> int:
        """Return the requested number of results per search page."""

    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

    def build_url(self, *, page: int) -> str:
        """Build the deterministic source search URL for one result page."""


class SourceAdapter(Protocol):
    """Runtime interface expected by the Bronze runner."""

    @property
    def definition(self) -> SourceDefinition: ...

    def plan_requests(self, context: BronzeRunContext) -> Iterable[BronzeRequest]: ...

    def fetch(self, request: BronzeRequest) -> BronzeResponse: ...

    def close(self) -> None: ...

    def traffic_snapshot(self) -> TrafficSnapshot: ...

    def reset_traffic_stats(self) -> None: ...

    def listing_target_from_url(self, url: str) -> BronzeTarget: ...

    def discover_listing_targets(self, payload: bytes | str) -> tuple[BronzeTarget, ...]: ...


HeadersForTarget = Callable[[BronzeTarget], dict[str, str]]


class WebSourceRuntime:
    """Shared HTTP/browser runtime composed into concrete source adapters."""

    _traffic_controllers: ClassVar[dict[str, TrafficController]] = {}
    _clients: ClassVar[dict[str, httpx.Client]] = {}

    def __init__(
        self,
        *,
        definition: SourceDefinition,
        targets: Iterable[BronzeTarget] = (),
        default_headers: dict[str, str] | None = None,
        headers_for_target: HeadersForTarget | None = None,
        timeout_seconds: float = 30.0,
        traffic_controller: TrafficController | None = None,
    ) -> None:
        self.definition = definition
        self.targets = tuple(targets)
        self.default_headers = default_headers or {}
        self._headers_for_target = headers_for_target
        self._timeout_seconds = timeout_seconds
        self._traffic_controller = traffic_controller

    def headers_for_target(self, target: BronzeTarget) -> dict[str, str]:
        """Return HTTP headers for one target."""

        if self._headers_for_target is not None:
            return self._headers_for_target(target)
        return self.default_headers

    def plan_requests(self, context: BronzeRunContext) -> Iterable[BronzeRequest]:
        """Plan raw acquisition requests for a run."""

        del context
        for target in self.targets:
            yield self.build_request(target)

    def build_request(self, target: BronzeTarget) -> BronzeRequest:
        """Build one raw acquisition request for a target."""

        self.ensure_allowed_uri(target.uri)
        return BronzeRequest(
            source_id=self.definition.source_id,
            target=target,
            method=HttpMethod.GET,
            headers=self.headers_for_target(target),
        )

    def fetch_http(self, request: BronzeRequest) -> BronzeResponse:
        """Fetch one raw payload through regular HTTP."""

        self._validate_request(request)

        source_id = self.definition.source_id
        request_logger = logger.bind(
            source_id=source_id,
            target_id=request.target.target_id,
            target_kind=request.target.kind.value,
        )
        if source_id not in self._clients:
            request_logger.debug(
                "Creating HTTP client timeout_seconds={} follow_redirects=True",
                self._timeout_seconds,
            )
            self._clients[source_id] = httpx.Client(
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
        client = self._clients[source_id]

        started_at = perf_counter()
        request_logger.info(
            "Fetching target method={} uri={}",
            request.method.value,
            request.target.uri,
        )
        try:
            response = self._traffic.request(
                lambda: client.request(
                    method=request.method.value,
                    url=str(request.target.uri),
                    headers=request.headers,
                    params=request.query_params or None,
                    content=request.body,
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

        self.ensure_allowed_uri(str(response.url))
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
            payload=response.content,
        )

    def fetch_browser(self, request: BronzeRequest) -> BronzeResponse:
        """Fetch one raw payload through Playwright when HTML needs browser state."""

        self._validate_request(request)

        source_id = self.definition.source_id
        request_logger = logger.bind(
            source_id=source_id,
            target_id=request.target.target_id,
            target_kind=request.target.kind.value,
        )
        try:
            response = self._traffic.request(
                lambda: fetch_rendered_html(
                    request=request,
                    source_id=source_id,
                    default_user_agent=self.default_headers.get("user-agent", ""),
                    timeout_seconds=self._timeout_seconds,
                    request_logger=request_logger,
                ),
                log_context={
                    "source_id": source_id,
                    "target_id": request.target.target_id,
                    "target_kind": request.target.kind.value,
                },
            )
        except Exception:
            request_logger.exception("Playwright fetch failed uri={}", request.target.uri)
            raise

        self.ensure_allowed_uri(response.final_uri)
        return response

    def close(self) -> None:
        """Close the underlying HTTP client session."""

        source_id = self.definition.source_id
        client = self._clients.pop(source_id, None)
        if client is not None:
            logger.bind(source_id=source_id).debug("Closing HTTP client")
            client.close()

    def cached_http_client(self) -> httpx.Client | None:
        """Return the cached HTTP client for this source, when it exists."""

        return self._clients.get(self.definition.source_id)

    @classmethod
    def close_all_clients(cls) -> None:
        """Close all globally cached HTTP clients."""

        for client in cls._clients.values():
            client.close()
        cls._clients.clear()

    def traffic_snapshot(self) -> TrafficSnapshot:
        """Return accumulated traffic metrics for this source."""

        return self._traffic.snapshot()

    def reset_traffic_stats(self) -> None:
        """Reset accumulated traffic metrics for this source."""

        self._traffic.reset_stats()

    def ensure_allowed_uri(self, uri: str) -> None:
        hostname = urlparse(uri).hostname
        if hostname is None:
            raise ValueError(f"target URI must include a hostname: {uri}")

        normalized = hostname.lower()
        if normalized not in self.definition.allowed_domains:
            allowed = ", ".join(self.definition.allowed_domains)
            raise ValueError(
                f"target hostname {normalized!r} is not allowed for "
                f"{self.definition.source_id}; allowed domains: {allowed}"
            )

    @property
    def _traffic(self) -> TrafficController:
        if self._traffic_controller is None:
            source_id = self.definition.source_id
            if source_id not in self._traffic_controllers:
                self._traffic_controllers[source_id] = TrafficController(
                    profile=self.definition.politeness
                )
            return self._traffic_controllers[source_id]

        return self._traffic_controller

    def _validate_request(self, request: BronzeRequest) -> None:
        if request.source_id != self.definition.source_id:
            raise ValueError(
                f"request source_id {request.source_id!r} does not match "
                f"source_id {self.definition.source_id!r}"
            )
        self.ensure_allowed_uri(request.target.uri)
