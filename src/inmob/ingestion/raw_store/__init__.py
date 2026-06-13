"""Raw artifact persistence for the Bronze layer."""

from inmob.ingestion.raw_store.filesystem import FileSystemRawArtifactStore
from inmob.ingestion.raw_store.store import RawArtifactStore

__all__ = ["FileSystemRawArtifactStore", "RawArtifactStore"]
