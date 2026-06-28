"""RE/MAX API search URL construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote



REMAX_HOME_URL = "https://www.remax.com.ar/"
REMAX_API_SEARCH_URL = (
    "https://api-ar.redremax.com/remaxweb-ar/api/listings/findAllWithEntrepreneurships"
)
REMAX_API_LISTING_BY_SLUG_URL = (
    "https://api-ar.redremax.com/remaxweb-ar/api/listings/findBySlug"
)
REMAX_API_ENTREPRENEURSHIP_BY_SLUG_URL = (
    "https://api-ar.redremax.com/remaxweb-ar/api/entrepreneurships/findBySlug"
)


@dataclass(frozen=True, slots=True)
class RemaxSearchCriteria:
    """RE/MAX API search criteria used to build reproducible Bronze targets."""

    page_size: int
    operation_ids: tuple[int, ...] = ()
    sort: str | None = None
    filters: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    landing_path: str | None = None
    label: str | None = None

    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

        if self.label:
            return self.label

        operation = (
            "all-operations"
            if not self.operation_ids
            else "operations-"
            + "-".join(str(operation_id) for operation_id in self.operation_ids)
        )
        return f"{operation}-page-size-{self.page_size}"

    def build_api_url(self, *, page: int) -> str:
        """Build the deterministic RE/MAX API search URL for one result page."""

        if page < 0:
            raise ValueError("page must be greater than or equal to zero")
        if self.page_size <= 0:
            raise ValueError("page_size must be greater than zero")

        params: list[tuple[str, str]] = [
            ("page", str(page)),
            ("pageSize", str(self.page_size)),
        ]
        if self.sort:
            params.append(("sort", self.sort))
        if self.operation_ids:
            operation_ids = ",".join(
                str(operation_id) for operation_id in self.operation_ids
            )
            params.append(("in", f"operationId:{operation_ids}"))
        params.extend(self.filters)
        if self.landing_path:
            params.append(("landingPath", self.landing_path))

        query = "&".join(
            f"{quote(key, safe=':')}={quote(value, safe=':' if key == 'in' else '')}"
            for key, value in params
        )
        return f"{REMAX_API_SEARCH_URL}?{query}"
