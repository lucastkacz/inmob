# Inmob Architecture Vault

This vault is the Single Source of Truth for the high-level architecture of the property listings data platform.

The current focus is architectural alignment before any technology stack, programming language, framework, database, or library is selected.

## Navigation

- [[Architecture Canvas]]
- [[01 - Architecture Overview]]
- [[02 - Pipeline Layers]]
- [[03 - Data Contracts and Lineage]]
- [[04 - Failure Replay and Operations]]
- [[05 - Analytical Domain]]
- [[06 - Decision Log]]
- [[07 - Repository Structure]]
- [[08 - Implementation and Run Log]]

## Documentation Rules

1. Every architectural boundary must be explicit.
2. Every major architectural decision must be justified by a known pattern, framework, or industry source.
3. Source-specific volatility must be isolated from analytical business logic.
4. Raw data preservation is a first-class architectural requirement.
5. Documents should stay few, robust, and navigable.

## Current Architectural Thesis

The platform follows a multi-hop immutable data pipeline:

1. Raw Ingestion
2. Standardization and Validation
3. Analytical Enrichment

Each layer communicates with the next layer only through persisted data artifacts. This keeps acquisition, parsing, validation, and analytical business logic independently evolvable.

## Current Agent Entry Point

Start with [[08 - Implementation and Run Log]] for the latest branch state, run commands, generated artifacts, and verification results.
