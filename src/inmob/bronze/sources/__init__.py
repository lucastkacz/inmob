"""Source adapter definitions for the Bronze layer."""

from inmob.bronze.sources.argenprop import ArgenpropSearchCriteria, ArgenpropSource
from inmob.bronze.sources.base import SourceAdapter, WebSearchCriteria, WebSourceRuntime
from inmob.bronze.sources.cabaprop import CabapropSearchCriteria, CabapropSource
from inmob.bronze.sources.remax import RemaxSearchCriteria, RemaxSource
from inmob.bronze.sources.mudafy import MudafySearchCriteria, MudafySource
from inmob.bronze.sources.properati import ProperatiSearchCriteria, ProperatiSource
from inmob.bronze.sources.zonaprop import ZonapropSearchCriteria, ZonapropSource

__all__ = [
    "ArgenpropSearchCriteria",
    "ArgenpropSource",
    "CabapropSearchCriteria",
    "CabapropSource",
    "MudafySearchCriteria",
    "MudafySource",
    "ProperatiSearchCriteria",
    "ProperatiSource",
    "RemaxSearchCriteria",
    "RemaxSource",
    "SourceAdapter",
    "WebSearchCriteria",
    "WebSourceRuntime",
    "ZonapropSearchCriteria",
    "ZonapropSource",
]
