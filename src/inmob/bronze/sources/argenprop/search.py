"""Argenprop search-page URL construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote, urljoin



ARGENPROP_HOME_URL = "https://www.argenprop.com/"


@dataclass(frozen=True, slots=True)
class ArgenpropSearchCriteria:
    """Argenprop search-page criteria used to build reproducible Bronze targets."""

    property_type: str
    operation: str
    location: str
    page_size: int = 20
    filters: tuple[str, ...] = field(default_factory=tuple)
    sort: str | None = None
    label: str | None = None

    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

        if self.label:
            return self.label

        base = f"{self.property_type}-{self.operation}-{self.location}"
        if not self.filters:
            return base
        return "-".join((base, *self.filters))

    def build_url(self, *, page: int) -> str:
        """Build the deterministic Argenprop search URL for one result page."""

        if page <= 0:
            raise ValueError("page must be greater than zero")

        path_parts = (
            self.property_type,
            self.operation,
            self.location,
            *self.filters,
        )
        path = "/".join(quote(part.strip("/"), safe="-") for part in path_parts)
        url = urljoin(ARGENPROP_HOME_URL, path)
        if page == 1:
            return _append_query_tokens(url, self._query_tokens())

        return _append_query_tokens(url, (*self._query_tokens(), f"pagina-{page}"))

    def _query_tokens(self) -> tuple[str, ...]:
        if self.sort is None:
            return ()

        return (f"orden-{self.sort}",)


def _append_query_tokens(url: str, tokens: tuple[str, ...]) -> str:
    if not tokens:
        return url
    return f"{url}?{'&'.join(tokens)}"
