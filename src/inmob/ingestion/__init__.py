"""Bronze ingestion layer.

This package contains source-agnostic abstractions for landing raw external
payloads without interpreting real estate business meaning.
"""

from inmob.ingestion.pipeline import BronzeIngestionPipeline, BronzeIngestionResult

__all__ = ["BronzeIngestionPipeline", "BronzeIngestionResult"]
