# Decision Log

## Purpose

This document records architecturally significant decisions in one place.

The project intentionally uses a single decision log instead of a large folder of individual ADR files. The format is inspired by Architecture Decision Records, which capture a decision, its context, and consequences in a small durable document: [Michael Nygard - Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

## Decision Format

Each decision uses:

- Status
- Context
- Decision
- Grounding
- Consequences

## DEC-001 - Adopt a Multi-Hop Immutable Pipeline

Status: Accepted

### Context

The platform must ingest listings from multiple independent websites with different formats and frequent external change.

Directly coupling acquisition, parsing, and analytics would make the system fragile.

### Decision

We will split the platform into three persisted layers:

1. Raw Ingestion
2. Standardization and Validation
3. Analytical Enrichment

Each layer communicates with the next layer through durable persisted artifacts.

### Grounding

This follows the multi-hop data architecture style described by Medallion Architecture, where raw data is progressively refined into cleaned and business-ready data: [Databricks - What is Medallion Architecture?](https://www.databricks.com/glossary/medallion-architecture).

### Consequences

- Raw data can be replayed.
- Parser failures do not erase acquisition history.
- Analytical logic remains isolated from source volatility.
- More artifact contracts must be defined and maintained.

## DEC-002 - Use Persisted Artifacts as Layer Boundaries

Status: Accepted

### Context

Layers should be independently evolvable and failure-isolated.

If layers communicate through direct calls or hidden runtime state, replay and auditability become weak.

### Decision

Layer boundaries will be persisted artifacts, not function calls or shared runtime state.

### Grounding

This supports loose coupling and traceability. Enterprise Integration Patterns describes Message Store and Message History as mechanisms for understanding message flow in loosely coupled systems: [Enterprise Integration Patterns - Message Store](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageStore.html).

### Consequences

- Every layer output must have an explicit contract.
- Downstream processing can be replayed from stored artifacts.
- Operational storage and lineage become architectural responsibilities.

## DEC-003 - Keep Raw Ingestion Semantically Blind

Status: Accepted

### Context

External websites may change layout or field structure frequently.

If acquisition extracts semantic fields, source layout changes can cause data loss before raw evidence is preserved.

### Decision

Raw Ingestion will acquire and persist payloads exactly as received, with acquisition metadata only.

It will not extract price, location, size, currency, seller, or property identity.

### Grounding

This aligns with the raw Bronze layer idea in Medallion Architecture, where external source data is landed as-is with metadata for historical archive, lineage, auditability, and reprocessing: [Databricks - Bronze layer](https://www.databricks.com/glossary/medallion-architecture).

### Consequences

- Acquisition remains robust against semantic layout changes.
- Historical payloads remain available for future parser improvements.
- Downstream layers carry the responsibility for interpretation and validation.

## DEC-004 - Use a Canonical Listing Contract

Status: Accepted

### Context

Each external source may represent equivalent listing concepts differently.

Without a canonical contract, every downstream analytical component would need to understand every source-specific format.

### Decision

Layer 2 will map all source-specific formats into one canonical listing contract.

Layer 3 may consume only the canonical listing contract.

### Grounding

Enterprise Integration Patterns recommends Canonical Data Model to minimize dependencies when integrating systems with different data formats: [Enterprise Integration Patterns - Canonical Data Model](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CanonicalDataModel.html).

### Consequences

- Downstream analytics become source-agnostic.
- New sources require only source-to-canonical mapping.
- Canonical contract evolution must be managed carefully.

## DEC-005 - Isolate Source Parsers Behind Strategies

Status: Accepted

### Context

Each source can require a different parsing approach, and those approaches can change independently.

The pipeline should not become a single conditional block containing all parser logic.

### Decision

Each source parser will be treated as a source-specific strategy selected by source identity and raw artifact metadata.

A parser factory will select the correct parser strategy without coupling the pipeline coordinator to parser internals.

### Grounding

The Strategy and Factory Method patterns are part of the Gang of Four design pattern catalog published in *Design Patterns: Elements of Reusable Object-Oriented Software*: [Design Patterns - Book Reference](https://en.wikipedia.org/wiki/Design_Patterns).

Enterprise Integration Patterns also describes Normalizer as routing different input formats through appropriate translators so they match a common format: [Enterprise Integration Patterns - Normalizer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html).

### Consequences

- Parser changes remain source-local.
- Adding a source does not require changing the analytical layer.
- Parser selection and parser behavior must be observable and versioned.

## DEC-006 - Quarantine Invalid Records Instead of Crashing the Pipeline

Status: Accepted

### Context

External source changes may break individual records or individual source parsers.

The platform must continue processing valid records when failures are isolated.

### Decision

Parser and validation failures will produce durable Quarantine Artifacts and diagnostic metadata.

Record-level failures will not automatically crash the entire pipeline.

### Grounding

Enterprise Integration Patterns defines Dead Letter Channel as a channel for messages that cannot or should not be delivered normally: [Enterprise Integration Patterns - Dead Letter Channel](https://www.enterpriseintegrationpatterns.com/patterns/messaging/DeadLetterChannel.html).

### Consequences

- Failed records remain inspectable and replayable.
- Operators can detect source-specific breakage.
- The system needs clear severity and retryability classifications.

## DEC-007 - Keep Analytical Logic Source-Agnostic

Status: Accepted

### Context

Analytical features such as entity resolution, currency normalization, and opportunity detection should not change because a website changes its layout.

### Decision

The analytical engine will consume only validated canonical records and domain reference data.

It will not consume raw payloads, parser internals, or source-specific field names.

### Grounding

Clean Architecture separates business rules from external details such as databases, frameworks, and web concerns: [Clean Coder - The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

### Consequences

- Business logic remains stable under source changes.
- Analytical outputs are easier to test and explain.
- The canonical contract must contain enough information for domain use cases.

## DEC-008 - Use an External Operational Control Plane

Status: Accepted

### Context

Pipeline sequencing, run state, alerts, retries, and replay are operational concerns.

Embedding those concerns into parsers or analytical business logic would blur responsibilities.

### Decision

Pipeline execution will be managed by an external control plane.

The control plane will trigger stages, track state, monitor outcomes, and route alerts.

### Grounding

Enterprise Integration Patterns defines Control Bus as a separate management mechanism for administering an integration system: [Enterprise Integration Patterns - Control Bus](https://www.enterpriseintegrationpatterns.com/patterns/messaging/ControlBus.html).

### Consequences

- Processing layers remain focused.
- Operational behavior becomes explicit.
- The system must define clear run states and diagnostic outputs.

## DEC-009 - Govern Acquisition Traffic with Token Bucket and Full Jitter Backoff

Status: Accepted

### Context

The platform must avoid aggressive or unstable acquisition behavior against external sources.

It must handle burst browsing, throttling, failures, and rate-limit responses gracefully.

### Decision

Acquisition traffic will be governed conceptually by:

- Token Bucket for rate limiting and controlled bursts
- Exponential Backoff with Full Jitter for retries

### Grounding

RFC 2697 describes token bucket based traffic metering using committed rate and burst sizes: [RFC 2697 - A Single Rate Three Color Marker](https://www.rfc-editor.org/rfc/rfc2697.html).

AWS Architecture Blog recommends jittered exponential backoff to spread retry spikes and reduce client work and server load: [AWS Architecture Blog - Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/).

### Consequences

- Acquisition becomes more polite and resilient.
- Retry behavior becomes predictable and auditable.
- Traffic policy must be external to parser and analytical logic.
