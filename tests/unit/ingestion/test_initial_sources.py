from pytest import raises

from inmob.ingestion.contracts import IngestionTarget, TargetKind
from inmob.ingestion.sources import SourceRegistry, ZonaPropSource, build_initial_source_adapters


def test_initial_sources_are_registered_by_stable_source_id() -> None:
    registry = SourceRegistry()
    registry.register_many(build_initial_source_adapters())

    assert registry.source_ids() == (
        "argenprop",
        "mercadolibre",
        "remax",
        "zonaprop",
    )


def test_initial_sources_have_politeness_profiles() -> None:
    for adapter in build_initial_source_adapters():
        assert adapter.definition.politeness.requests_per_minute > 0
        assert adapter.definition.politeness.burst_size > 0
        assert adapter.definition.allowed_domains


def test_property_source_requires_explicit_portal_configuration() -> None:
    registry = SourceRegistry()
    registry.register_many(
        build_initial_source_adapters(
            property_homepage_url="https://property.example.test/",
            property_allowed_domains=("property.example.test",),
        )
    )

    assert "property" in registry.source_ids()


def test_configured_source_rejects_targets_outside_allowed_domains() -> None:
    adapter = ZonaPropSource(
        targets=(
            IngestionTarget(
                target_id="bad-target",
                kind=TargetKind.SEARCH_RESULTS,
                uri="https://not-zonaprop.example.test/search",
            ),
        )
    )

    with raises(ValueError, match="not allowed"):
        tuple(adapter.plan_requests(context=None))  # type: ignore[arg-type]
