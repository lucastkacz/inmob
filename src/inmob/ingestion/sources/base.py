"""OOP boundary for external real estate web sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
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

    def __init__(
        self,
        *,
        targets: Iterable[IngestionTarget] = (),
        timeout_seconds: float = 30.0,
    ) -> None:
        self._targets = tuple(targets)
        self._timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def definition(self) -> SourceDefinition:
        """Return stable source identity and traffic policy."""

    @property
    def default_headers(self) -> dict[str, str]:
        """Return source-specific HTTP headers."""

        return {}

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
            headers=self.default_headers,
        )

    def fetch(self, request: IngestionRequest) -> IngestionResponse:
        """Fetch one raw payload."""

        if request.source_id != self.definition.source_id:
            raise ValueError(
                f"request source_id {request.source_id!r} does not match "
                f"source_id {self.definition.source_id!r}"
            )
        self._ensure_allowed_uri(request.target.uri)

        with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True) as client:
            response = client.request(
                method=request.method.value,
                url=str(request.target.uri),
                headers=request.headers,
                params=request.query_params,
                content=request.body,
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

    @abstractmethod
    def listing_target_from_url(self, url: str) -> IngestionTarget:
        """Build a listing-detail target from a source listing URL."""

    @abstractmethod
    def discover_listing_targets(self, payload: bytes | str) -> tuple[IngestionTarget, ...]:
        """Discover listing-detail targets from a raw search/list page payload."""

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
