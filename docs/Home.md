# Inmob Architecture Vault

This vault is the Single Source of Truth for the high-level architecture of the property listings data platform.

The current focus is a lean vertical slice: preserve the important architectural boundaries while removing every component that is not yet necessary.

## Navigation

- [[01 - Architecture Overview]]
- [[02 - Pipeline Layers]]
- [[03 - Data Contracts and Lineage]]
- [[04 - Failure Replay and Operations]]
- [[05 - Analytical Domain]]
- [[06 - Decision Log]]
- [[07 - Lean Implementation Path]]

## Documentation Rules

1. Every architectural boundary must be explicit.
2. Every major architectural decision must be justified by a known pattern, framework, or industry source.
3. Source-specific volatility must be isolated from analytical business logic.
4. Raw data preservation is a first-class architectural requirement.
5. Documents should stay few, robust, and navigable.
6. Best part is no part: do not add infrastructure, services, tools, queues, schedulers, or abstractions until a real constraint requires them.

## Current Architectural Thesis

The platform follows a lean multi-hop immutable data pipeline:

1. Raw Ingestion
2. Standardization and Validation
3. Analytical Enrichment

Each layer communicates with the next layer only through persisted data artifacts. In the MVP, those artifacts can be plain local files and run manifests inside one repo, produced by one CLI/process.

The architecture protects replayability and source isolation, but the first implementation must avoid microservices, queues, workflow engines, schema registries, warehouses, and dashboards unless a concrete failure mode forces them into existence.
