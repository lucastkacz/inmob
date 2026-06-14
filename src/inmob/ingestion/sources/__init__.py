"""Source adapter definitions for the Bronze ingestion layer."""

from inmob.ingestion.sources.base import RealEstateWebSource, SourceAdapter, WebSearchCriteria
from inmob.ingestion.sources.remax import RemaxSearchCriteria, RemaxSource
from inmob.ingestion.sources.registry import SourceRegistry

__all__ = [
    "RealEstateWebSource",
    "RemaxSearchCriteria",
    "RemaxSource",
    "SourceAdapter",
    "SourceRegistry",
    "WebSearchCriteria",
]
