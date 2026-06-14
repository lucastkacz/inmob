"""Source adapter definitions for the Bronze ingestion layer."""

from inmob.ingestion.sources.argenprop import ArgenpropSearchCriteria, ArgenpropSource
from inmob.ingestion.sources.base import RealEstateWebSource, SourceAdapter, WebSearchCriteria
from inmob.ingestion.sources.remax import RemaxSearchCriteria, RemaxSource
from inmob.ingestion.sources.registry import SourceRegistry

__all__ = [
    "ArgenpropSearchCriteria",
    "ArgenpropSource",
    "RealEstateWebSource",
    "RemaxSearchCriteria",
    "RemaxSource",
    "SourceAdapter",
    "SourceRegistry",
    "WebSearchCriteria",
]
