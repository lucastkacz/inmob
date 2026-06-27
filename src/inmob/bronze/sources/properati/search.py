"""Properati search-page URL construction."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin



PROPERATI_HOME_URL = "https://www.properati.com.ar/"


@dataclass(frozen=True, slots=True)
class ProperatiSearchCriteria:
    """Properati search-page criteria used to build reproducible Bronze targets."""

    operation: str  # e.g., "venta", "alquiler"
    location: str   # e.g., "capital-federal"
    property_type: str = "departamento"  # e.g., "departamento", "casa", "ph"
    sort: str | None = None  # e.g., "published_on_desc"
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
        """Build the deterministic Properati search URL for one result page."""

        if page <= 0:
            raise ValueError("page must be greater than zero")

        # Properati URL path pattern: s/{location}/{property_type}/{operation}/{page}
        path = f"s/{self.location}/{self.property_type}/{self.operation}"
        if page > 1:
            path = f"{path}/{page}"

        url = urljoin(PROPERATI_HOME_URL, path)
        if self.sort:
            url = f"{url}?sort={self.sort}"
        return url
