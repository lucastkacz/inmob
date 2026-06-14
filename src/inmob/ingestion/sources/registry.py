"""Registry for Bronze source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from inmob.ingestion.sources.base import RealEstateWebSource


@dataclass(slots=True)
class SourceRegistry:
    """Stores source adapters by stable source identifier."""

    _adapters: dict[str, RealEstateWebSource] = field(default_factory=dict)

    def register(self, adapter: RealEstateWebSource) -> None:
        source_id = adapter.definition.source_id
        if source_id in self._adapters:
            raise ValueError(f"source adapter already registered: {source_id}")
        self._adapters[source_id] = adapter

    def register_many(self, adapters: tuple[RealEstateWebSource, ...]) -> None:
        for adapter in adapters:
            self.register(adapter)

    def get(self, source_id: str) -> RealEstateWebSource:
        try:
            return self._adapters[source_id]
        except KeyError as exc:
            raise KeyError(f"unknown source adapter: {source_id}") from exc

    def source_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def adapters(self) -> tuple[RealEstateWebSource, ...]:
        return tuple(self._adapters[source_id] for source_id in self.source_ids())
