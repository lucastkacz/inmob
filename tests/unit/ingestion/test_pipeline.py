from collections.abc import Iterable

from inmob.ingestion import BronzeIngestionPipeline
from inmob.ingestion.contracts import (
    IngestionRequest,
    IngestionResponse,
    IngestionRunContext,
    IngestionTarget,
    PolitenessProfile,
    SourceDefinition,
    TargetKind,
)
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import SourceAdapter


class FakeSource(SourceAdapter):
    @property
    def definition(self) -> SourceDefinition:
        return SourceDefinition(
            source_id="fake",
            display_name="Fake",
            homepage_url="https://fake.example.test/",
            allowed_domains=("fake.example.test",),
            politeness=PolitenessProfile(requests_per_minute=10, burst_size=1),
        )

    def plan_requests(self, context: IngestionRunContext) -> Iterable[IngestionRequest]:
        del context
        target = IngestionTarget(
            target_id="fake-target",
            kind=TargetKind.OTHER,
            uri="https://fake.example.test/raw",
        )
        yield IngestionRequest(source_id=self.definition.source_id, target=target)

    def fetch(self, request: IngestionRequest) -> IngestionResponse:
        return IngestionResponse(
            request=request,
            status_code=200,
            final_uri=request.target.uri,
            media_type="application/json",
            payload=b'{"raw": true}',
        )


def test_bronze_pipeline_lands_raw_artifacts(tmp_path) -> None:
    pipeline = BronzeIngestionPipeline(raw_store=FileSystemRawArtifactStore(tmp_path))
    result = pipeline.run(
        context=IngestionRunContext(run_id="run-001"),
        sources=(FakeSource(),),
    )

    assert len(result.artifacts) == 1
    assert result.failures == ()
    assert result.artifacts[0].payload_path.read_bytes() == b'{"raw": true}'
