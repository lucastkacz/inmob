"""CabaProp search URL and API request construction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlencode, urljoin

from inmob.ingestion.sources.base import WebSearchCriteria


CABAPROP_HOME_URL = "https://cabaprop.com.ar/"
CABAPROP_API_SEARCH_URL = "https://cabaprop.com.ar/api/v1/properties/find-properties"
CABAPROP_API_PROPERTY_URL_TEMPLATE = "https://cabaprop.com.ar/api/v1/properties/{listing_id}"


@dataclass(frozen=True, slots=True)
class CabapropSearchCriteria(WebSearchCriteria):
    """CabaProp search criteria used to build reproducible Bronze targets."""

    operation: str
    barrios: tuple[int, ...] = ()
    location_slug: str | None = None
    page_size: int = 12
    order_by: str = "created_at"
    sort: str = "desc"
    property_types: tuple[int, ...] = field(default_factory=tuple)
    label: str | None = None

    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

        if self.label:
            return self.label

        location = self.location_slug or "all-locations"
        return f"{self.operation}-{location}-page-size-{self.page_size}"

    def build_url(self, *, page: int) -> str:
        """Build the deterministic public CabaProp search URL for one page."""

        if page <= 0:
            raise ValueError("page must be greater than zero")

        query = self.operation
        if self.location_slug:
            query = f"{query}-{self.location_slug}"

        path = f"propiedades/{query}"
        return f"{urljoin(CABAPROP_HOME_URL, path)}?pagina={page}"

    def build_api_url(self, *, page: int) -> str:
        """Build the deterministic CabaProp API search URL for one page."""

        if page <= 0:
            raise ValueError("page must be greater than zero")
        if self.page_size <= 0:
            raise ValueError("page_size must be greater than zero")

        params = {
            "offset": str((page - 1) * self.page_size),
            "limit": str(self.page_size),
            "orderBy": self.order_by,
            "sort": self.sort,
        }
        return f"{CABAPROP_API_SEARCH_URL}?{urlencode(params)}"

    def build_api_body(self) -> bytes:
        """Build the CabaProp search API JSON body."""

        body = {
            "operationType": _operation_type_id(self.operation),
            "propertyTypes": list(self.property_types),
            "barrios": list(self.barrios),
            "price": {
                "currency": "ARS",
                "min": 0,
                "max": 0,
                "tag": "pesos",
            },
            "surface": {
                "tag": "superficieTotal",
                "type": "totalSurface",
                "min": "",
                "max": "",
            },
            "ambiences": [],
            "bedrooms": [],
            "characteristics": [],
            "bathrooms": 0,
            "garages": 0,
            "extras": [],
            "antiquity": "",
        }
        return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _operation_type_id(operation: str) -> int:
    if operation == "comprar":
        return 1
    if operation == "alquilar":
        return 2
    raise ValueError(f"unsupported CabaProp operation: {operation}")
