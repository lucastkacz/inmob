"""Raw artifact store boundary."""

from __future__ import annotations

from typing import Protocol

from inmob.bronze.contracts import BronzeResponse, BronzeRunContext, RawArtifact


class RawArtifactStore(Protocol):
    """Persistence boundary for raw Bronze artifacts."""

    def persist(
        self,
        *,
        context: BronzeRunContext,
        response: BronzeResponse,
    ) -> RawArtifact:
        """Persist the raw payload and return artifact metadata."""
