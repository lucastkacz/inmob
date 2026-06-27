"""RE/MAX search-page URL construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote, urljoin



REMAX_HOME_URL = "https://www.remax.com.ar/"
REMAX_BUY_PATH = "/listings/buy"
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
    """RE/MAX search-page criteria used to build reproducible Bronze targets."""

    page_size: int
    operation_ids: tuple[int, ...] = ()
    sort: str | None = None
    filters: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    landing_path: str | None = None
    filter_count: int | None = None
    view_mode: str | None = None
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

    def build_url(self, *, page: int) -> str:
        """Build the deterministic RE/MAX search URL for one result page."""

        return self._build_url(base_url=f"{urljoin(REMAX_HOME_URL, REMAX_BUY_PATH)}", page=page)

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

    def _build_url(self, *, base_url: str, page: int) -> str:
        """Build a RE/MAX search URL for one result page."""

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
            params.append(("in:operationId", operation_ids))
        params.extend(self.filters)
        if self.landing_path:
            params.append(("landingPath", self.landing_path))
        if self.filter_count is not None:
            params.append(("filterCount", str(self.filter_count)))
        if self.view_mode:
            params.append(("viewMode", self.view_mode))

        query = "&".join(
            f"{quote(key, safe=':')}={quote(value, safe='')}" for key, value in params
        )
        return f"{base_url}?{query}"
