"""OOP boundary for external data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from inmob.ingestion.contracts import (
    IngestionRequest,
    IngestionResponse,
    IngestionRunContext,
    SourceDefinition,
)


class SourceAdapter(ABC):
    """Abstract base class for semantically blind source adapters.

    A source adapter may know how to discover or fetch raw payloads from one
    external source. It must not parse real estate meaning from those payloads.
    """

    @property
    @abstractmethod
    def definition(self) -> SourceDefinition:
        """Return stable source identity and traffic policy."""

    @abstractmethod
    def plan_requests(self, context: IngestionRunContext) -> Iterable[IngestionRequest]:
        """Plan raw acquisition requests for a run."""

    @abstractmethod
    def fetch(self, request: IngestionRequest) -> IngestionResponse:
        """Fetch one raw payload."""
