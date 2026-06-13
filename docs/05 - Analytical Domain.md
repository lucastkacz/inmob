# Analytical Domain

## Purpose

This document defines the conceptual responsibilities of the analytical domain.

The analytical domain begins after standardization and validation. It operates only on canonical, validated, source-agnostic data.

Lean constraint: the first analytical domain should explain and preserve evidence. It should not pretend to make final investment decisions.

## Domain Boundary

The analytical domain must not know:

- Website layouts
- HTML structure
- Source-specific field names
- Network requests
- Acquisition retries
- Parser internals
- Raw payload parsing rules

The analytical domain may know:

- Canonical listing attributes
- Property entity concepts
- Currency normalization rules
- Deduplication and entity resolution rules
- Feature engineering definitions
- Opportunity classification rules

This follows Clean Architecture's separation between business rules and external details: [Clean Coder - The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

## Core Analytical Capabilities

The following capabilities are the target domain. They should not all be built on day one.

### Entity Resolution

Entity Resolution identifies whether multiple canonical listings refer to the same real-world property.

This is not merely technical deduplication. It is a business-domain capability because different sources may describe the same property with incomplete, inconsistent, or differently formatted attributes.

Record linkage is the broader discipline of identifying records that refer to the same entity across different sources, especially when no universal identifier exists: [Record Linkage - Overview](https://en.wikipedia.org/wiki/Record_linkage).

### Deduplication

Deduplication is the operational outcome of entity resolution.

The system must preserve all contributing listings while producing a consolidated property entity. The analytical output must not erase source evidence.

### Currency Normalization

Currency Normalization converts listing prices into a reference currency for comparable analysis.

This belongs in the analytical layer because source values may be valid but not directly comparable.

Currency normalization must preserve:

- Original currency
- Original amount
- Reference currency
- Conversion rule identifier
- Conversion timestamp or rate context

### Feature Engineering

Feature Engineering derives analytical metrics from canonical data.

Examples:

- Price per square meter
- Days on market
- Relative price deviation
- Location-based comparison metrics
- Confidence indicators

Feature definitions must be versioned because changes to formulas alter analytical meaning.

### Opportunity Detection

Opportunity Detection flags properties that may be undervalued, unusual, inconsistent, or worth manual review.

This capability must depend on derived features and validated canonical data, not on raw source payloads.

## MVP Analytical Scope

Start with:

- Basic price-per-area metrics
- Original and reference currency context
- Duplicate candidates, not automatic merges
- Manual-review flags, not final opportunity scores
- Lineage from each output back to canonical listings and raw artifacts

Defer:

- Machine learning
- Automated valuation models
- Complex geo-spatial analysis
- Full confidence scoring
- Irreversible deduplication decisions

## Analytical Inputs

The analytical layer consumes:

- Canonical Listing
- Validation Result for accepted records
- Lineage references
- Domain reference data

It does not consume Raw Artifacts directly.

## Analytical Outputs

The analytical layer produces:

- Enriched Property Entity
- Deduplication outcome
- Currency-normalized values
- Feature set
- Opportunity flags
- Analytical lineage

## Domain Rules

1. Analytical outputs must remain traceable to canonical listings.
2. Canonical listing identity must never be destroyed by deduplication.
3. Analytical formulas must be versioned.
4. Opportunity flags are analytical judgments, not raw facts.
5. The domain must be able to recompute outputs when business rules change.

## Source Grounding

This document is grounded in Clean Architecture. Business rules should be isolated from external details so that source volatility, persistence choices, and interface concerns do not leak into the domain model: [Clean Coder - The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

It also relies on the data warehousing idea that business-level outputs are downstream of raw and conformed data. Medallion Architecture describes Gold data as curated business-level data prepared for analytics: [Databricks - Gold layer](https://www.databricks.com/glossary/medallion-architecture).

## Summary

The analytical domain is where the platform becomes useful, but it is useful only because it is protected from source volatility.

Its inputs are clean contracts, not websites.
