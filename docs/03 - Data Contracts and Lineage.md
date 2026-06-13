# Data Contracts and Lineage

## Purpose

This document defines the conceptual data artifacts that cross architectural boundaries.

The system must not rely on implicit runtime knowledge between layers. Every layer boundary is represented by a durable artifact with a clear contract.

Lean constraint: contracts begin as small versioned files or models. Do not introduce a schema registry, metadata platform, or lineage server until local files and tests stop being enough.

## Contract Principles

1. Every artifact has an identity.
2. Every artifact has a creation time.
3. Every artifact has a producing layer.
4. Every artifact records the source or upstream artifact it came from.
5. Every artifact records the contract version used to produce it.
6. Every downstream artifact is traceable to raw acquisition.
7. Raw artifacts are immutable by default.

## Raw Artifact Contract

### Purpose

The Raw Artifact preserves the external payload exactly as acquired.

### Created By

Layer 1: Raw Ingestion.

### Consumed By

Layer 2: Standardization and Validation.

### Required Conceptual Fields

- Raw artifact identifier
- Source identifier
- Acquisition run identifier
- Acquisition timestamp
- Acquisition target
- Response status
- Payload format at acquisition level
- Raw payload location
- Payload checksum
- Acquisition metadata

### Lean Physical Shape

Start with a payload file plus a JSON metadata sidecar:

- `data/raw/{source}/{run_id}/{raw_artifact_id}.payload`
- `data/raw/{source}/{run_id}/{raw_artifact_id}.metadata.json`

The metadata sidecar carries identity, source, acquisition timing, target, status, format, checksum, and run context.

### Explicitly Excluded Fields

- Price
- Address
- Neighborhood
- Surface area
- Property type
- Currency
- Seller
- Analytical classification

These fields are excluded because their extraction would violate semantic blindness in Layer 1.

### Source Grounding

This contract supports replayability and auditability, consistent with the Bronze layer purpose in Medallion Architecture: [Databricks - What is Medallion Architecture?](https://www.databricks.com/glossary/medallion-architecture).

## Canonical Listing Contract

### Purpose

The Canonical Listing represents a standardized listing record independent of the external source format.

### Created By

Layer 2: Standardization and Validation.

### Consumed By

Layer 3: Analytical Enrichment.

### Required Conceptual Fields

- Canonical listing identifier
- Source identifier
- Source listing reference, if available
- Raw artifact identifier
- Parser strategy identifier
- Parser version
- Canonical contract version
- Property attributes
- Commercial attributes
- Location attributes
- Publication attributes
- Validation status
- Validation timestamp

### Contract Rule

The Canonical Listing is the only listing shape that the analytical layer may consume.

### Lean Physical Shape

Start with newline-delimited JSON or Parquet for accepted records:

- `data/canonical/{source}/{run_id}/listings.jsonl`

JSONL is easiest to inspect and debug. Parquet can be introduced when local analytics volume justifies columnar storage.

### Source Grounding

The Canonical Data Model pattern minimizes dependencies between heterogeneous source formats by requiring each participant to translate into a common model: [Enterprise Integration Patterns - Canonical Data Model](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CanonicalDataModel.html).

## Validation Result Contract

### Purpose

The Validation Result records whether a parsed canonical record satisfies the expected contract and quality rules.

### Created By

Layer 2: Standardization and Validation.

### Consumed By

Layer 2 for routing and Layer 3 for accepted records.

### Required Conceptual Fields

- Validation result identifier
- Canonical listing identifier, if created
- Raw artifact identifier
- Validation rule set version
- Validation status
- Severity
- Failed rule identifiers
- Diagnostic message
- Validation timestamp

### Contract Rule

Validation failure must not be represented only as a log event. It must be represented as data.

### Lean Physical Shape

Start with:

- `data/validation/{source}/{run_id}/results.jsonl`

## Quarantine Artifact Contract

### Purpose

The Quarantine Artifact preserves records that cannot be parsed, standardized, or validated safely.

### Created By

Layer 2: Standardization and Validation.

### Consumed By

Operations, diagnostics, parser improvement workflows, and replay processes.

### Required Conceptual Fields

- Quarantine artifact identifier
- Raw artifact identifier
- Source identifier
- Parser strategy identifier, if selected
- Parser version, if selected
- Failure category
- Failure severity
- Diagnostic detail
- Retryability classification
- Quarantine timestamp

### Lean Physical Shape

Start with:

- `data/quarantine/{source}/{run_id}/quarantine.jsonl`

The quarantine record should reference the raw artifact and include enough diagnostic detail to repair the parser without re-acquiring the source.

### Source Grounding

This is the data-platform equivalent of a Dead Letter Channel. Enterprise Integration Patterns defines Dead Letter Channel as the place for messages that cannot or should not be delivered normally: [Enterprise Integration Patterns - Dead Letter Channel](https://www.enterpriseintegrationpatterns.com/patterns/messaging/DeadLetterChannel.html).

## Enriched Property Entity Contract

### Purpose

The Enriched Property Entity represents a business-level property entity derived from one or more validated canonical listings.

### Created By

Layer 3: Analytical Enrichment.

### Consumed By

Analytical reporting, opportunity detection, decision support, and downstream business workflows.

### Required Conceptual Fields

- Property entity identifier
- Contributing canonical listing identifiers
- Entity resolution status
- Deduplication confidence
- Normalized commercial values
- Derived metrics
- Feature set version
- Analytical flags
- Lineage references
- Enrichment timestamp

### Contract Rule

An enriched property entity may combine multiple listings, but it must never erase the identities of the contributing canonical listings.

### Lean Physical Shape

Start with:

- `data/enriched/{run_id}/properties.jsonl`

The initial enriched entity can be intentionally shallow. It only needs to prove lineage, deterministic feature calculation, and duplicate candidate preservation.

## Lineage Contract

### Purpose

Lineage links every downstream artifact to the upstream artifacts and transformation versions that produced it.

### Required Conceptual Fields

- Downstream artifact identifier
- Upstream artifact identifiers
- Producing layer
- Transformation identifier
- Transformation version
- Contract version
- Created timestamp

### Lean Physical Shape

Start with a run manifest:

- `data/runs/{run_id}.json`

The manifest records input artifact paths, output artifact paths, transformation versions, counts, and outcome. This is enough lineage for the MVP.

### Source Grounding

Enterprise Integration Patterns describes Message Store and Message History as mechanisms for understanding and reporting against message flow in loosely coupled systems without disturbing the flow itself: [Enterprise Integration Patterns - Message Store](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageStore.html).

## Summary

The contracts are intentionally conceptual at this stage. They define obligations and boundaries, not a physical schema.

The central rule is simple: if a layer needs another layer's output, it reads a persisted artifact with a known contract.
