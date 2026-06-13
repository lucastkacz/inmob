# Failure Replay and Operations

## Purpose

This document defines the operational architecture for orchestration, failure isolation, replay, observability, and traffic politeness.

The processing layers must remain focused on their own responsibilities. Operational sequencing and monitoring belong to a separate control plane.

## Control Plane

### Responsibility

The control plane coordinates pipeline execution and monitors outcomes.

It is responsible for:

- Triggering pipeline stages in order
- Tracking run state
- Recording layer outcomes
- Detecting failed or partial runs
- Routing alerts
- Initiating replay workflows
- Applying traffic governance policies to acquisition

### Non-Responsibilities

The control plane must not:

- Parse listings
- Validate business fields
- Deduplicate properties
- Compute analytical metrics
- Own source-specific business logic

### Source Grounding

Enterprise Integration Patterns defines Control Bus as a separate management mechanism for administering a distributed integration system while keeping management concerns separate from application data flow: [Enterprise Integration Patterns - Control Bus](https://www.enterpriseintegrationpatterns.com/patterns/messaging/ControlBus.html).

## Pipeline State Model

Each pipeline run should expose a small, explicit state model.

Recommended conceptual states:

- Pending
- Running
- Completed
- Completed with quarantined records
- Partial failure
- Failed
- Cancelled
- Replayed

Record-level failures should not automatically become run-level failures. A run can complete with quarantined records when the failure is isolated and downstream processing can continue safely.

## Failure Taxonomy

### Acquisition Failure

The platform could not acquire a source payload.

Examples:

- Source unavailable
- Timeout
- Rate limit response
- Authentication or access change
- Unexpected transport-level response

Expected handling:

- Retry according to backoff policy
- Preserve acquisition diagnostics
- Mark source run outcome
- Alert if threshold is exceeded

### Parser Failure

The raw artifact was acquired but cannot be interpreted by the selected source parser.

Expected handling:

- Create Quarantine Artifact
- Continue with other records where possible
- Preserve raw artifact for future replay

### Validation Failure

The parser produced a candidate canonical record, but the record violates the canonical contract or quality rules.

Expected handling:

- Create Validation Result
- Route invalid record to quarantine if required
- Continue with valid records

### Analytical Failure

The clean record is valid, but analytical processing cannot safely enrich it.

Expected handling:

- Preserve clean input
- Capture analytical diagnostic artifact
- Avoid corrupting existing enriched entities

## Quarantine

Quarantine is a durable diagnostic store for failed records.

It is not a trash bin.

It exists to support:

- Investigation
- Parser repair
- Validation rule improvement
- Replay
- Source change detection
- Data quality reporting

This is grounded in the Dead Letter Channel pattern: [Enterprise Integration Patterns - Dead Letter Channel](https://www.enterpriseintegrationpatterns.com/patterns/messaging/DeadLetterChannel.html).

## Replay

Replay means reprocessing persisted upstream artifacts without re-acquiring the external source.

Replay is required when:

- A parser is fixed
- A validation rule is corrected
- A canonical contract evolves
- A feature engineering rule changes
- A historical audit is needed

Replay must identify:

- Input artifact set
- Transformation version
- Target layer
- Reason for replay
- Replay outcome

Replay depends on immutable raw capture and lineage.

## Observability

The platform must produce operational signals without coupling business logic to monitoring tools.

Minimum conceptual signals:

- Run identifier
- Layer status
- Source status
- Artifact counts
- Success counts
- Quarantine counts
- Failure categories
- Retry counts
- Replay counts
- Processing duration
- Alert routing outcome

Enterprise Integration Patterns describes Message Store as a way to capture information about messages in a central location for reporting without disturbing loose coupling: [Enterprise Integration Patterns - Message Store](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageStore.html).

## Traffic Politeness

Acquisition must behave defensively and politely.

The goal is not only to protect the local system. It is also to avoid abusive traffic patterns against external sources.

### Token Bucket

Use a Token Bucket model for rate limiting acquisition.

The Token Bucket pattern allows natural bursts while enforcing a long-term average rate. RFC 2697 describes token bucket-based traffic metering through committed information rate and burst sizes: [RFC 2697 - A Single Rate Three Color Marker](https://www.rfc-editor.org/rfc/rfc2697.html).

In this architecture, Token Bucket belongs to acquisition governance and the control plane. It must not be embedded in parsing or analytical logic.

### Exponential Backoff with Full Jitter

Use exponential backoff with jitter when retrying remote acquisition failures or rate-limit responses.

AWS Architecture Blog recommends adding jitter to exponential backoff to spread out retry spikes and reduce client work and server load. It identifies Full Jitter as a strong standard approach for remote clients: [AWS Architecture Blog - Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/).

Backoff belongs to traffic management and retry policy, not to parser behavior.

## Alerting

Alerts should be routed by the control plane based on state transitions and thresholds.

Examples:

- Source acquisition failure threshold exceeded
- Parser failure rate increased for one source
- Validation failure rate increased after contract change
- Replay failed
- Quarantine volume exceeded expected baseline

Alerts should link to diagnostic artifacts rather than only textual logs.

## Summary

Operations are part of the architecture, not an afterthought.

The system must be able to fail partially, preserve evidence, alert clearly, and replay deterministically.
