"""Mudafy search-page URL construction."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urljoin

from inmob.ingestion.sources.base import WebSearchCriteria


MUDAFY_HOME_URL = "https://mudafy.com.ar/"


@dataclass(frozen=True, slots=True)
class MudafySearchCriteria(WebSearchCriteria):
    """Mudafy search-page criteria used to build reproducible Bronze targets."""

    operation: str  # e.g., "venta", "alquiler"
    location: str   # e.g., "caba"
    property_type: str = "propiedades"  # e.g., "propiedades", "departamentos", "casas"
    sort: str | None = None  # e.g., "published_at:desc:nulls_last"
    label: str | None = None

    @property
    def page_size(self) -> int:
        """Return the requested number of results per search page."""
        return 20

    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

        if self.label:
            return self.label

        return f"{self.operation}-{self.property_type}-{self.location}"

    def build_url(self, *, page: int) -> str:
        """Build the deterministic Mudafy search URL for one result page."""

        if page <= 0:
            raise ValueError("page must be greater than zero")

        path = f"{self.operation}/{self.property_type}/{self.location}"
        if page > 1:
            path = f"{path}/{page}-p"

        url = urljoin(MUDAFY_HOME_URL, path)
        if self.sort:
            # Encode colon characters to match Mudafy sorting query string format
            encoded_sort = quote(self.sort, safe="")
            url = f"{url}?sort={encoded_sort}"
        return url
