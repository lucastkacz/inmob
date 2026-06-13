# Repository Structure

## Purpose

This document defines the initial repository skeleton for the ETL/data platform.

The structure mirrors the architectural layers already defined in the vault:

- Layer 1: Raw Ingestion
- Layer 2: Standardization and Validation
- Layer 3: Analytical Enrichment
- Operational Control Plane

No implementation logic is introduced at this stage.

## Proposed Skeleton

```text
src/
  inmob/
    ingestion/
      sources/
      raw_store/
      traffic/
      contracts/

    standardization/
      parsers/
      validation/
      quarantine/
      contracts/

    enrichment/
      entity_resolution/
      currency/
      features/
      opportunity/
      contracts/

    orchestration/
      runs/
      state/
      diagnostics/

    shared/

tests/
  unit/
  integration/
  fixtures/

var/
  raw/
  clean/
  quarantine/
  enriched/
```

## Naming Rationale

`ingestion` is used instead of `acquisition` because it is more common in ETL and data platform repositories while still matching the architecture's Raw Ingestion layer.

`standardization` is used instead of only `transform` because this layer has a narrower responsibility: parse source-specific raw artifacts, validate them, and map them into a canonical listing contract.

`enrichment` is used for domain analytics because this layer produces business-level derived entities and features from clean source-agnostic records.

`orchestration` is separated because pipeline sequencing, run state, diagnostics, retries, replay, and alerts belong to the control plane rather than to any one processing layer.

`var` is local runtime storage and should not contain versioned data. It exists only to provide an obvious local home for raw, clean, quarantine, and enriched artifacts during development.

## Dependency Policy

The initial Poetry environment includes only foundational libraries:

- Data contracts and settings
- HTTP client foundation
- Retry foundation
- Structured logging
- CLI foundation
- Test, lint, and type-check tooling

Heavy source-specific dependencies, browser automation, dataframe engines, geospatial libraries, and analytical engines should be added only when a concrete layer decision requires them.
