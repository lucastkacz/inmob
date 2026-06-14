"""Zonaprop search-page URL construction."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from inmob.ingestion.sources.base import WebSearchCriteria


ZONAPROP_HOME_URL = "https://www.zonaprop.com.ar/"


@dataclass(frozen=True, slots=True)
class ZonapropSearchCriteria(WebSearchCriteria):
    """Zonaprop search-page criteria used to build reproducible Bronze targets."""

    operation: str  # e.g., "venta", "alquiler"
    location: str   # e.g., "capital-federal"
    property_type: str = "inmuebles"  # e.g., "inmuebles", "departamentos", "casas"
    sort: str | None = None  # e.g., "publicado-descendente"
    label: str | None = None

    @property
    def page_size(self) -> int:
        """Return the requested number of results per search page."""
        return 30

    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

        if self.label:
            return self.label

        return f"{self.operation}-{self.property_type}-{self.location}"

    def build_url(self, *, page: int) -> str:
        """Build the deterministic Zonaprop search URL for one result page."""

        if page <= 0:
            raise ValueError("page must be greater than zero")

        # Page 1: {property_type}-{operation}-{location}.html
        # Page > 1: {property_type}-{operation}-{location}-pagina-{page}.html
        if page == 1:
            path = f"{self.property_type}-{self.operation}-{self.location}.html"
        else:
            path = f"{self.property_type}-{self.operation}-{self.location}-pagina-{page}.html"

        url = urljoin(ZONAPROP_HOME_URL, path)
        if self.sort:
            url = f"{url}?sort_by={self.sort}"
        return url
