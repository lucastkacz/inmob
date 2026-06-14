"""Source adapter definitions for the Bronze ingestion layer."""

from inmob.ingestion.sources.argenprop import ArgenpropSearchCriteria, ArgenpropSource
from inmob.ingestion.sources.base import RealEstateWebSource, SourceAdapter, WebSearchCriteria
from inmob.ingestion.sources.cabaprop import CabapropSearchCriteria, CabapropSource
from inmob.ingestion.sources.remax import RemaxSearchCriteria, RemaxSource
from inmob.ingestion.sources.mudafy import MudafySearchCriteria, MudafySource
from inmob.ingestion.sources.properati import ProperatiSearchCriteria, ProperatiSource
from inmob.ingestion.sources.zonaprop import ZonapropSearchCriteria, ZonapropSource
from inmob.ingestion.sources.registry import SourceRegistry

__all__ = [
    "ArgenpropSearchCriteria",
    "ArgenpropSource",
    "CabapropSearchCriteria",
    "CabapropSource",
    "MudafySearchCriteria",
    "MudafySource",
    "ProperatiSearchCriteria",
    "ProperatiSource",
    "RealEstateWebSource",
    "RemaxSearchCriteria",
    "RemaxSource",
    "SourceAdapter",
    "SourceRegistry",
    "WebSearchCriteria",
    "ZonapropSearchCriteria",
    "ZonapropSource",
]
