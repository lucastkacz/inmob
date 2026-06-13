from inmob.ingestion.sources import SourceRegistry, build_initial_source_adapters


def test_initial_sources_are_registered_by_stable_source_id() -> None:
    registry = SourceRegistry()
    registry.register_many(build_initial_source_adapters())

    assert registry.source_ids() == (
        "argenprop",
        "mercadolibre",
        "property",
        "remax",
        "zonaprop",
    )


def test_initial_sources_have_politeness_profiles() -> None:
    for adapter in build_initial_source_adapters():
        assert adapter.definition.politeness.requests_per_minute > 0
        assert adapter.definition.politeness.burst_size > 0
        assert adapter.definition.allowed_domains
