"""Reusable HTTP source adapter for configured raw targets."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
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
from inmob.ingestion.sources.base import SourceAdapter


class ConfiguredHttpSourceAdapter(SourceAdapter):
    """HTTP adapter driven by explicit source targets.

    This adapter is intentionally generic. It is useful for early Bronze runs
    where the input is a set of seed URLs or source endpoints. More complex
    sources can later provide their own adapter implementation while preserving
    the same SourceAdapter interface.
    """

    def __init__(
        self,
        *,
        definition: SourceDefinition,
        targets: Sequence[IngestionTarget] = (),
        timeout_seconds: float = 30.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._definition = definition
        self._targets = tuple(targets)
        self._timeout_seconds = timeout_seconds
        self._default_headers = default_headers or {}

    @property
    def definition(self) -> SourceDefinition:
        return self._definition

    def plan_requests(self, context: IngestionRunContext) -> Iterable[IngestionRequest]:
        del context
        for target in self._targets:
            self._ensure_allowed_uri(target.uri)
            yield IngestionRequest(
                source_id=self.definition.source_id,
                target=target,
                method=HttpMethod.GET,
                headers=self._default_headers,
            )

    def fetch(self, request: IngestionRequest) -> IngestionResponse:
        if request.source_id != self.definition.source_id:
            raise ValueError(
                f"request source_id {request.source_id!r} does not match "
                f"adapter source_id {self.definition.source_id!r}"
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
