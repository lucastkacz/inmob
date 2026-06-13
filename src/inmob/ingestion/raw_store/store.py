"""Raw artifact store boundary."""

from __future__ import annotations

from typing import Protocol

from inmob.ingestion.contracts import IngestionResponse, IngestionRunContext, RawArtifact


class RawArtifactStore(Protocol):
    """Persistence boundary for raw Bronze artifacts."""

    def persist(
        self,
        *,
        context: IngestionRunContext,
        response: IngestionResponse,
    ) -> RawArtifact:
        """Persist the raw payload and return artifact metadata."""
