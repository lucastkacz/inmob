"""Default CLI Bronze settings."""

from typing import Any

from inmob.bronze.sources import (
    ArgenpropSearchCriteria,
    ArgenpropSource,
    CabapropSearchCriteria,
    CabapropSource,
    MudafySearchCriteria,
    MudafySource,
    ProperatiSearchCriteria,
    ProperatiSource,
    RemaxSearchCriteria,
    RemaxSource,
    ZonapropSearchCriteria,
    ZonapropSource,
)


DEFAULT_BRONZE_DATA_DIR = "data/bronze"
DEFAULT_RAW_DATA_DIR = DEFAULT_BRONZE_DATA_DIR
DEFAULT_PROPERTY_LIMIT = 15

# Targets "Capital Federal" / "CABA", buy/sale operation, sorted by newest first.
DEFAULT_SOURCES_CONFIG: dict[str, dict[str, Any]] = {
    "argenprop": {
        "source_class": ArgenpropSource,
        "criteria_class": ArgenpropSearchCriteria,
        "page_index_starts_at": 1,
        "search_targets_method": "search_targets",
        "default_criteria": {
            "property_type": "departamentos",
            "operation": "venta",
            "location": "capital-federal",
            "sort": "masnuevos",
            "page_size": 20,
            "label": "argenprop-caba-newest",
        },
    },
    "cabaprop": {
        "source_class": CabapropSource,
        "criteria_class": CabapropSearchCriteria,
        "page_index_starts_at": 1,
        "search_targets_method": "api_search_targets",
        "default_criteria": {
            "operation": "comprar",
            "barrios": (),
            "location_slug": "caba",
            "page_size": 12,
            "order_by": "created_at",
            "sort": "desc",
            "label": "cabaprop-caba-newest",
        },
    },
    "mudafy": {
        "source_class": MudafySource,
        "criteria_class": MudafySearchCriteria,
        "page_index_starts_at": 1,
        "search_targets_method": "search_targets",
        "default_criteria": {
            "operation": "venta",
            "location": "caba",
            "property_type": "propiedades",
            "sort": "published_at:desc:nulls_last",
            "label": "mudafy-caba-newest",
        },
    },
    "properati": {
        "source_class": ProperatiSource,
        "criteria_class": ProperatiSearchCriteria,
        "page_index_starts_at": 1,
        "search_targets_method": "search_targets",
        "default_criteria": {
            "operation": "venta",
            "location": "capital-federal",
            "property_type": "departamento",
            "sort": "published_on_desc",
            "label": "properati-caba-newest",
        },
    },
    "remax": {
        "source_class": RemaxSource,
        "criteria_class": RemaxSearchCriteria,
        "page_index_starts_at": 0,
        "search_targets_method": "api_search_targets",
        "default_criteria": {
            "page_size": 24,
            "operation_ids": (1,),
            "sort": "-createdAt",
            "filters": (("locations", "in:CF@<b>Capital</b> <b>F</b>ederal::::::"),),
            "landing_path": "comprar-propiedades",
            "filter_count": 0,
            "view_mode": "listViewMode",
            "label": "remax-caba-newest",
        },
    },
    "zonaprop": {
        "source_class": ZonapropSource,
        "criteria_class": ZonapropSearchCriteria,
        "page_index_starts_at": 1,
        "search_targets_method": "api_search_targets",
        "default_criteria": {
            "filters": {
                "tipoDeOperacion": "1",
                "preTipoDeOperacion": "1",
                "tipoDePropiedad": "2",
                "province": 6,
                "sort": "more_recent",
            },
            "public_url": "https://www.zonaprop.com.ar/departamentos-venta-capital-federal.html",
            "label": "zonaprop-caba-newest",
        },
    },
}
