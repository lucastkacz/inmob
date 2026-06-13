# Architecture Overview

## Purpose

This document defines the top-level architecture of the property listings data platform. It exists to align the system around stable architectural principles before implementation choices are made.

The platform must ingest property listings from multiple independent websites, preserve source data, standardize heterogeneous payloads, and support analytical business logic without coupling that business logic to external source volatility.

## Scope

This document covers:

- System intent
- Architectural style
- System boundaries
- Core principles
- Quality attributes
- Source-backed architectural grounding

This document does not cover:

- Programming languages
- Frameworks
- Databases
- Cloud providers
- Specific scraping libraries
- Deployment topology

## Architectural Intent

The system is a source-agnostic, replayable, and fault-isolated data platform for real estate listing intelligence.

The core architectural intent is to separate three kinds of change:

1. External source change: websites, payload formats, rate limits, page layouts, and availability.
2. Data interpretation change: parsing rules, validation rules, canonical schema evolution, and anomaly classification.
3. Business logic change: deduplication, currency normalization, feature engineering, and opportunity scoring.

These changes must not force each other to change unnecessarily.

## Core Architecture

The platform follows a Multi-Hop Immutable Data Pipeline:

1. Raw Ingestion
2. Standardization and Validation
3. Analytical Enrichment

Each layer writes durable artifacts to a persistence boundary. The next layer reads those artifacts. Layers do not communicate through direct calls, shared memory, or hidden runtime state.

This structure is aligned with the Medallion Architecture concept, where raw data is progressively refined into cleaned, conformed, and business-ready data. Databricks describes this as a multi-hop architecture with Bronze, Silver, and Gold layers for progressive data quality refinement: [Databricks - What is Medallion Architecture?](https://www.databricks.com/glossary/medallion-architecture).

## System Boundaries

### External Sources

External sources are outside the system boundary. They are unstable, independently owned, and not contractually reliable.

The platform must assume that each source can change layout, availability, payload shape, pagination behavior, throttling rules, and response quality without notice.

### Acquisition Boundary

The acquisition boundary ends when a raw payload and its acquisition metadata are durably stored.

No semantic extraction is allowed before this boundary.

### Standardization Boundary

The standardization boundary ends when source-specific raw artifacts have been translated into a canonical listing contract or quarantined with a diagnostic artifact.

### Analytical Boundary

The analytical boundary begins only after data conforms to the canonical contract and has passed validation.

The analytical layer must have no knowledge of websites, HTML, network requests, source-specific parsers, or acquisition strategies.

## Architectural Principles

### 1. Persisted Artifacts Are Layer Boundaries

Layer boundaries are not function calls or runtime dependencies. They are persisted artifacts with explicit contracts.

Rationale: persisted boundaries enable replay, auditability, independent evolution, and fault containment.

### 2. Raw Ingestion Is Semantically Blind

Raw ingestion may know how to acquire data, but it must not know what the data means.

It may know source identity, acquisition time, request context, response status, payload bytes, and checksums. It must not extract price, location, size, rooms, seller, or property identity.

### 3. Source Volatility Is Isolated

Changes in one source must not destabilize other sources or the analytical domain.

This aligns with Separation of Concerns and the Single Responsibility Principle. Robert C. Martin summarizes SRP as a module having one reason to change: [Clean Coder - The Single Responsibility Principle](https://blog.cleancoder.com/uncle-bob/2014/05/08/SingleReponsibilityPrinciple.html).

### 4. Transformations Must Be Replayable

The system must be able to reprocess historical raw artifacts after parsers, validators, or canonical contracts evolve.

Raw data is therefore immutable by default.

### 5. Business Logic Is Source-Agnostic

The analytical domain operates on clean, structured entities only.

This follows Clean Architecture's separation between business rules and external details. Clean Architecture places external details such as databases, web, and frameworks outside the core business rules: [Clean Coder - The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

### 6. Failures Are Data, Not Just Logs

Parser failures, validation failures, schema mismatches, and anomalous records must produce durable diagnostic artifacts.

Logs are useful for operators, but they are not a substitute for replayable failure records.

### 7. Operations Are Controlled Externally

Pipeline execution is coordinated by an operational control plane. Processing layers should expose status and outcomes, but the sequencing and monitoring of execution belong outside the business logic.

## Architecture Views

The project will use lightweight architecture views inspired by the C4 Model:

- System context: actors, external sources, communication channels, and platform scope.
- Container view: major runtime and persistence responsibilities at a conceptual level.
- Dynamic view: pipeline flow across persisted artifacts.
- Operational view: orchestration, monitoring, retry, quarantine, and replay.

The C4 Model is appropriate at this stage because it is notation-independent, tooling-independent, and organized around hierarchical abstractions: [C4 Model](https://c4model.com/).

## Quality Attributes

### Replayability

Historical raw data must be preserved so that improved parsers and validators can be applied later.

### Fault Isolation

A parser failure for one source or one record must not crash unrelated sources or the entire pipeline.

### Evolvability

The platform must tolerate new sources, changed source formats, and canonical contract evolution.

### Auditability

Every clean or enriched record must trace back to the raw artifact and transformation version that produced it.

### Politeness

Acquisition must respect traffic limits, backoff behavior, and source stability.

### Analytical Integrity

Business conclusions must be based on validated, canonical, source-agnostic data.

## Summary

The platform is not a scraper with analytics attached. It is a data architecture where acquisition, standardization, validation, and analytical reasoning are separated by durable contracts.

The top-level design priority is to preserve data and isolate change.
