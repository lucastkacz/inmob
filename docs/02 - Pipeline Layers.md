# Pipeline Layers

## Purpose

This document defines the three conceptual layers of the platform and the responsibilities, non-responsibilities, inputs, outputs, and governing patterns for each layer.

The pipeline is intentionally split into persisted hops so that external volatility, data interpretation, and analytical business logic can evolve independently.

Lean constraint: a layer is a contract boundary, not necessarily a separate service. The MVP should run as a single local command that writes explicit artifacts between steps.

## Layer Summary

| Layer | Name | Primary Responsibility | Output |
| --- | --- | --- | --- |
| 1 | Raw Ingestion | Acquire and persist source payloads exactly as received | Raw Artifact |
| 2 | Standardization and Validation | Convert raw artifacts into canonical validated records | Canonical Listing or Quarantine Artifact |
| 3 | Analytical Enrichment | Apply business logic to clean source-agnostic records | Enriched Property Entity |

## MVP Runtime Shape

The first implementation should be boring:

- One repository
- One CLI entrypoint
- One source adapter
- One local artifact directory
- One canonical listing model
- One quarantine path
- One replay command

Do not add a message broker, distributed worker, API server, workflow engine, data warehouse, object store, or dashboard until the local vertical slice fails for a specific measured reason.

This aligns with the Medallion Architecture concept of progressively refining raw data into cleaned and business-ready data: [Databricks - What is Medallion Architecture?](https://www.databricks.com/glossary/medallion-architecture).

## Layer 1: Raw Ingestion

### Responsibility

Raw Ingestion acquires external source payloads and stores them exactly as received, together with acquisition metadata.

This layer answers:

- What source was contacted?
- When was it contacted?
- What payload was received?
- What acquisition metadata is needed for audit and replay?

### Non-Responsibilities

Raw Ingestion must not:

- Parse business fields
- Extract price
- Extract location
- Extract size
- Infer property identity
- Deduplicate listings
- Normalize currency
- Validate business meaning
- Classify opportunities

### Allowed Knowledge

Raw Ingestion may know:

- Source identity
- Acquisition target
- Request timing
- Response status
- Payload format at the transport level
- Payload bytes or text exactly as received
- Checksum
- Acquisition run identifier

### Forbidden Knowledge

Raw Ingestion must not know:

- What a price is
- What a neighborhood is
- What a square meter is
- What fields are required for business analysis
- How two listings should be compared

### Output

The output is a Raw Artifact.

The Raw Artifact is immutable by default and becomes the replayable source of truth for downstream transformation.

### Lean Starting Point

Start by storing:

- Raw payload file
- Metadata sidecar
- Checksum
- Acquisition run identifier

Avoid browser automation unless a source requires rendered JavaScript or interaction. Prefer simple HTTP acquisition first when it captures the relevant payload reliably.

### Architectural Grounding

This layer corresponds to a landing zone or raw Bronze layer in a multi-hop data architecture. Databricks describes the Bronze layer as the place where external source data is landed as-is with metadata for historical archive, lineage, auditability, and reprocessing: [Databricks - Bronze layer](https://www.databricks.com/glossary/medallion-architecture).

## Layer 2: Standardization and Validation

### Responsibility

Standardization and Validation reads Raw Artifacts and converts source-specific payloads into a canonical corporate listing contract.

This layer answers:

- Which parser strategy applies to this source?
- Can the raw artifact be interpreted?
- Does the interpreted record satisfy the canonical contract?
- If not, what diagnostic artifact should be persisted?

### Non-Responsibilities

Standardization and Validation must not:

- Contact external websites
- Re-fetch missing data by itself
- Apply analytical scoring
- Merge duplicate properties across sources
- Make investment conclusions
- Hide failed records in logs only

### Pattern: Pipes and Filters

The layer is modeled as a sequence of independent processing steps: source routing, parsing, canonical mapping, validation, and quarantine routing.

Enterprise Integration Patterns defines Pipes and Filters as a way to divide complex processing into smaller independent steps connected by channels: [Enterprise Integration Patterns - Pipes and Filters](https://www.enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html).

### Pattern: Normalizer

Different websites may provide semantically equivalent listing information in different formats. The Normalizer pattern routes each input type through an appropriate translator so the result matches a common format.

Source: [Enterprise Integration Patterns - Normalizer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html).

### Pattern: Canonical Data Model

The clean layer exposes a single corporate listing contract independent of any source format.

Enterprise Integration Patterns recommends a Canonical Data Model to minimize dependencies when integrating applications or sources with different data formats: [Enterprise Integration Patterns - Canonical Data Model](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CanonicalDataModel.html).

### Pattern: Strategy and Factory Method

Each source parser is a separate strategy selected by source identity and raw artifact metadata. A parser factory resolves the correct parser without embedding all parser logic in the pipeline coordinator.

The Strategy and Factory Method patterns are part of the Gang of Four design pattern catalog, originally published in *Design Patterns: Elements of Reusable Object-Oriented Software*: [Design Patterns - Book Reference](https://en.wikipedia.org/wiki/Design_Patterns).

In this architecture, Strategy is used because parsing algorithms vary by source while the pipeline flow stays stable. Factory Method is used because parser creation and selection must be decoupled from the layer's core processing flow.

### Output

The output is one of:

- Canonical Listing
- Validation Result
- Quarantine Artifact

The layer must continue processing after record-level failures whenever the overall run can still make progress.

### Lean Starting Point

Start with one parser strategy for one source and a small canonical model. Use a validation library instead of a custom validation framework.

Parser output should be deterministic: the same raw artifact, parser version, and contract version should produce the same canonical or quarantine artifact.

## Layer 3: Analytical Enrichment

### Responsibility

Analytical Enrichment applies source-agnostic business logic to validated canonical records.

This layer answers:

- Do multiple listings refer to the same real-world property?
- What is the normalized reference currency value?
- What derived features can be calculated?
- Which records deserve opportunity flags?

### Non-Responsibilities

Analytical Enrichment must not:

- Fetch source websites
- Parse HTML or raw payloads
- Know source-specific field names
- Depend on parser internals
- Treat source-specific shape as business truth

### Architectural Grounding

This layer follows Clean Architecture's emphasis on keeping business rules isolated from external details. The analytical engine should depend on canonical business entities, not on acquisition details, source formats, web concerns, or persistence mechanics.

Source: [Clean Coder - The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

### Output

The output is an Enriched Property Entity and related analytical artifacts.

These outputs must retain lineage to the canonical listing records and raw artifacts from which they were derived.

### Lean Starting Point

Start with simple deterministic features:

- Price per square meter
- Currency context preservation
- Basic duplicate candidate grouping
- Manual-review opportunity flags

Avoid machine learning, automated investment conclusions, and complex scoring until enough validated historical data exists.

## Layer Interaction Rules

1. Layer 1 writes Raw Artifacts.
2. Layer 2 reads Raw Artifacts and writes Canonical Listings or Quarantine Artifacts.
3. Layer 3 reads Canonical Listings and writes Enriched Property Entities.
4. No layer may bypass the persistence boundary of the previous layer.
5. No downstream layer may mutate upstream artifacts.
6. Every downstream output must preserve lineage to its upstream input.

## Summary

The pipeline is deliberately boring at the top level: land, clean, enrich.

The power of the design comes from what the layers are forbidden to know.
