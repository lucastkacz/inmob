"""Initial source definitions for Argentine real estate portals."""

from __future__ import annotations

from collections.abc import Sequence

from inmob.ingestion.contracts import (
    IngestionTarget,
    PolitenessProfile,
    SourceDefinition,
    TargetKind,
)
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
    DEFAULT_HEADERS = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "es-AR,es;q=0.9,en;q=0.8",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
    }

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
            default_headers=self.DEFAULT_HEADERS,
        )

    @classmethod
    def listing_target(cls, *, slug: str, url: str) -> IngestionTarget:
        """Build a Bronze target for a RE/MAX listing detail page."""

        return IngestionTarget(
            target_id=f"remax-listing-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=url,
            metadata={"slug": slug},
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
    """Configurable placeholder for the project-specific 'Property' source.

    The project has not yet confirmed the exact Property portal URL. Keeping
    this source configurable avoids silently treating it as Properati.
    """

    def __init__(
        self,
        *,
        homepage_url: str,
        allowed_domains: tuple[str, ...],
        targets: Sequence[IngestionTarget] = (),
    ) -> None:
        super().__init__(
            definition=SourceDefinition(
                source_id="property",
                display_name="Property",
                homepage_url=homepage_url,
                allowed_domains=allowed_domains,
                politeness=DEFAULT_POLITENESS,
                notes="Project-specific source; exact portal URL must be configured explicitly.",
            ),
            targets=targets,
        )


def build_initial_source_adapters(
    *,
    property_homepage_url: str | None = None,
    property_allowed_domains: tuple[str, ...] = (),
) -> tuple[ConfiguredHttpSourceAdapter, ...]:
    """Return configured adapters for the first supported portals.

    Property is included only when its exact portal URL is provided.
    """

    adapters: list[ConfiguredHttpSourceAdapter] = [
        ZonaPropSource(),
        ArgenpropSource(),
        RemaxSource(),
        MercadoLibreSource(),
    ]

    if property_homepage_url is not None:
        adapters.append(
            PropertySource(
                homepage_url=property_homepage_url,
                allowed_domains=property_allowed_domains,
            )
        )

    return tuple(adapters)
