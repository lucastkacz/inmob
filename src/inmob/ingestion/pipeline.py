"""Bronze ingestion pipeline service."""

from __future__ import annotations

from dataclasses import dataclass

from inmob.ingestion.contracts import IngestionRunContext, RawArtifact
from inmob.ingestion.raw_store import RawArtifactStore
from inmob.ingestion.sources import SourceAdapter


@dataclass(frozen=True, slots=True)
class BronzeIngestionResult:
    """Result of a Bronze ingestion run."""

    artifacts: tuple[RawArtifact, ...]
    failures: tuple[str, ...] = ()


@dataclass(slots=True)
class BronzeIngestionPipeline:
    """Coordinates source adapters and raw artifact persistence."""

    raw_store: RawArtifactStore
    continue_on_error: bool = True

    def run(
        self,
        *,
        context: IngestionRunContext,
        sources: tuple[SourceAdapter, ...],
    ) -> BronzeIngestionResult:
        artifacts: list[RawArtifact] = []
        failures: list[str] = []

        for source in sources:
            for request in source.plan_requests(context):
                try:
                    response = source.fetch(request)
                    artifact = self.raw_store.persist(context=context, response=response)
                    artifacts.append(artifact)
                except Exception as exc:
                    failure = f"{source.definition.source_id}:{request.target.target_id}:{exc}"
                    if not self.continue_on_error:
                        raise
                    failures.append(failure)

        return BronzeIngestionResult(artifacts=tuple(artifacts), failures=tuple(failures))
