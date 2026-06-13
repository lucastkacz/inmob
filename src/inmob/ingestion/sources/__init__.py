"""Source adapter definitions for the Bronze ingestion layer."""

from inmob.ingestion.sources.base import SourceAdapter
from inmob.ingestion.sources.configured_http import ConfiguredHttpSourceAdapter
from inmob.ingestion.sources.initial_sources import (
    ArgenpropSource,
    MercadoLibreSource,
    PropertySource,
    RemaxSource,
    ZonaPropSource,
    build_initial_source_adapters,
)
from inmob.ingestion.sources.registry import SourceRegistry

__all__ = [
    "ArgenpropSource",
    "ConfiguredHttpSourceAdapter",
    "MercadoLibreSource",
    "PropertySource",
    "RemaxSource",
    "SourceAdapter",
    "SourceRegistry",
    "ZonaPropSource",
    "build_initial_source_adapters",
]
