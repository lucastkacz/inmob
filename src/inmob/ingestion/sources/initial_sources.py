"""Initial source definitions for Argentine real estate portals."""

from __future__ import annotations

from collections.abc import Sequence

from inmob.ingestion.contracts import IngestionTarget, PolitenessProfile, SourceDefinition
from inmob.ingestion.sources.configured_http import ConfiguredHttpSourceAdapter


DEFAULT_POLITENESS = PolitenessProfile(requests_per_minute=20, burst_size=3)


class ZonaPropSource(ConfiguredHttpSourceAdapter):
    def __init__(self, targets: Sequence[IngestionTarget] = ()) -> None:
        super().__init__(
            definition=SourceDefinition(
                source_id="zonaprop",
                display_name="ZonaProp",
                homepage_url="https://www.zonaprop.com.ar/",
                allowed_domains=("zonaprop.com.ar", "www.zonaprop.com.ar"),
                politeness=DEFAULT_POLITENESS,
            ),
            targets=targets,
        )


class ArgenpropSource(ConfiguredHttpSourceAdapter):
    def __init__(self, targets: Sequence[IngestionTarget] = ()) -> None:
        super().__init__(
            definition=SourceDefinition(
                source_id="argenprop",
                display_name="Argenprop",
                homepage_url="https://www.argenprop.com/",
                allowed_domains=("argenprop.com", "www.argenprop.com"),
                politeness=DEFAULT_POLITENESS,
            ),
            targets=targets,
        )


class RemaxSource(ConfiguredHttpSourceAdapter):
    def __init__(self, targets: Sequence[IngestionTarget] = ()) -> None:
        super().__init__(
            definition=SourceDefinition(
                source_id="remax",
                display_name="RE/MAX Argentina",
                homepage_url="https://www.remax.com.ar/",
                allowed_domains=("remax.com.ar", "www.remax.com.ar"),
                politeness=DEFAULT_POLITENESS,
            ),
            targets=targets,
        )


class MercadoLibreSource(ConfiguredHttpSourceAdapter):
    def __init__(self, targets: Sequence[IngestionTarget] = ()) -> None:
        super().__init__(
            definition=SourceDefinition(
                source_id="mercadolibre",
                display_name="Mercado Libre Inmuebles",
                homepage_url="https://inmuebles.mercadolibre.com.ar/",
                allowed_domains=(
                    "mercadolibre.com.ar",
                    "www.mercadolibre.com.ar",
                    "inmuebles.mercadolibre.com.ar",
                ),
                politeness=DEFAULT_POLITENESS,
            ),
            targets=targets,
        )


class PropertySource(ConfiguredHttpSourceAdapter):
    def __init__(self, targets: Sequence[IngestionTarget] = ()) -> None:
        super().__init__(
            definition=SourceDefinition(
                source_id="property",
                display_name="Properati / Property",
                homepage_url="https://www.properati.com.ar/",
                allowed_domains=("properati.com.ar", "www.properati.com.ar"),
                politeness=DEFAULT_POLITENESS,
                notes="Named 'property' by project convention; homepage points to Properati.",
            ),
            targets=targets,
        )


def build_initial_source_adapters() -> tuple[ConfiguredHttpSourceAdapter, ...]:
    """Return configured adapters for the first supported portals."""

    return (
        ZonaPropSource(),
        ArgenpropSource(),
        RemaxSource(),
        MercadoLibreSource(),
        PropertySource(),
    )
