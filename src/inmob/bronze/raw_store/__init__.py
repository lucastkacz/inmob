"""Raw artifact persistence for the Bronze layer."""

from inmob.bronze.raw_store.filesystem import FileSystemRawArtifactStore
from inmob.bronze.raw_store.store import RawArtifactStore

__all__ = ["FileSystemRawArtifactStore", "RawArtifactStore"]
