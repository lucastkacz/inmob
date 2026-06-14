"""OOP boundary for external real estate web sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import ClassVar
from urllib.parse import urlparse

import httpx

from inmob.ingestion.contracts import (
    HttpMethod,
    IngestionRequest,
    IngestionResponse,
    IngestionRunContext,
    IngestionTarget,
    SourceDefinition,
)
from inmob.ingestion.traffic import TrafficController


class WebSearchCriteria(ABC):
    """Abstract criteria for a paginated source search/list page."""

    @property
    @abstractmethod
    def page_size(self) -> int:
        """Return the requested number of results per search page."""

    @abstractmethod
    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

    @abstractmethod
    def build_url(self, *, page: int) -> str:
        """Build the deterministic source search URL for one result page."""


class RealEstateWebSource(ABC):
    """Base class for semantically blind real estate web sources.

    The common source shape is:
    - search/listing-index pages expose links to listing detail pages
    - listing detail pages expose the raw payload Silver will later parse

    Bronze may discover URLs and fetch raw payloads. It must not extract real
    estate facts such as price, address, rooms, area, or currency.
    """

    _traffic_controllers: ClassVar[dict[str, TrafficController]] = {}
    _clients: ClassVar[dict[str, httpx.Client]] = {}

    def __init__(
        self,
        *,
        targets: Iterable[IngestionTarget] = (),
        timeout_seconds: float = 30.0,
        traffic_controller: TrafficController | None = None,
    ) -> None:
        self._targets = tuple(targets)
        self._timeout_seconds = timeout_seconds
        self._traffic_controller = traffic_controller

    @property
    @abstractmethod
    def definition(self) -> SourceDefinition:
        """Return stable source identity and traffic policy."""

    @property
    def default_headers(self) -> dict[str, str]:
        """Return source-specific HTTP headers."""

        return {}

    def headers_for_target(self, target: IngestionTarget) -> dict[str, str]:
        """Return HTTP headers for one target."""

        del target
        return self.default_headers

    def plan_requests(self, context: IngestionRunContext) -> Iterable[IngestionRequest]:
        """Plan raw acquisition requests for a run."""

        del context
        for target in self._targets:
            yield self.build_request(target)

    def build_request(self, target: IngestionTarget) -> IngestionRequest:
        """Build one raw acquisition request for a target."""

        self._ensure_allowed_uri(target.uri)
        return IngestionRequest(
            source_id=self.definition.source_id,
            target=target,
            method=HttpMethod.GET,
            headers=self.headers_for_target(target),
        )

    def fetch(self, request: IngestionRequest) -> IngestionResponse:
        """Fetch one raw payload."""

        if request.source_id != self.definition.source_id:
            raise ValueError(
                f"request source_id {request.source_id!r} does not match "
                f"source_id {self.definition.source_id!r}"
            )
        self._ensure_allowed_uri(request.target.uri)

        source_id = self.definition.source_id
        if source_id not in self._clients:
            self._clients[source_id] = httpx.Client(
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
        client = self._clients[source_id]

        response = self._traffic.request(
            lambda: client.request(
                method=request.method.value,
                url=str(request.target.uri),
                headers=request.headers,
                params=request.query_params or None,
                content=request.body,
                timeout=self._timeout_seconds,
            )
        )

        media_type = response.headers.get("content-type")
        if media_type is not None:
            media_type = media_type.split(";", maxsplit=1)[0].strip().lower()

        self._ensure_allowed_uri(str(response.url))

        return IngestionResponse(
            request=request,
            status_code=response.status_code,
            final_uri=str(response.url),
            media_type=media_type,
            headers=dict(response.headers),
            payload=response.content,
        )

    def close(self) -> None:
        """Close the underlying HTTP client session."""
        source_id = self.definition.source_id
        client = self._clients.pop(source_id, None)
        if client is not None:
            client.close()

    def __enter__(self) -> RealEstateWebSource:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    @classmethod
    def close_all_clients(cls) -> None:
        """Close all globally cached HTTP clients."""
        for client in cls._clients.values():
            client.close()
        cls._clients.clear()

    @abstractmethod
    def listing_target_from_url(self, url: str) -> IngestionTarget:
        """Build a listing-detail target from a source listing URL."""

    @abstractmethod
    def discover_listing_targets(self, payload: bytes | str) -> tuple[IngestionTarget, ...]:
        """Discover listing-detail targets from a raw search/list page payload."""

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

    def _ensure_allowed_uri(self, uri: str) -> None:
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


SourceAdapter = RealEstateWebSource
