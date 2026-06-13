"""Contracts for the Bronze ingestion layer."""

from inmob.ingestion.contracts.bronze import (
    HttpMethod,
    IngestionRequest,
    IngestionResponse,
    IngestionRunContext,
    IngestionTarget,
    PolitenessProfile,
    RawArtifact,
    RetryProfile,
    SourceDefinition,
    TargetKind,
)

__all__ = [
    "HttpMethod",
    "IngestionRequest",
    "IngestionResponse",
    "IngestionRunContext",
    "IngestionTarget",
    "PolitenessProfile",
    "RawArtifact",
    "RetryProfile",
    "SourceDefinition",
    "TargetKind",
]
