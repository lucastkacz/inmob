# Lean Implementation Path

## Purpose

This document translates the architecture into the smallest useful implementation path.

The goal is not to select a forever stack. The goal is to choose the fewest parts needed to prove the pipeline against one real source while preserving replayability, validation, quarantine, and lineage.

## Lean Rule

Best part is no part.

Do not add a component because a mature data platform usually has it. Add it only when the current system has a measured pain that the component directly removes.

## MVP Vertical Slice

Build this first:

1. One source adapter
2. One raw artifact writer
3. One parser strategy
4. One canonical listing model
5. One validator
6. One quarantine writer
7. One enrichment script
8. One replay command
9. One run manifest

This should run locally from one CLI command and write inspectable files under `data/`.

## Suggested Local Artifact Layout

```text
data/
  raw/{source}/{run_id}/
  canonical/{source}/{run_id}/
  validation/{source}/{run_id}/
  quarantine/{source}/{run_id}/
  enriched/{run_id}/
  runs/{run_id}.json
```

This is intentionally plain. It can later map to object storage, tables, or a lakehouse if volume or collaboration requires it.

## Candidate Public Libraries

These are candidates, not automatic dependencies.

### Acquisition

- [HTTPX](https://github.com/encode/httpx): smallest useful starting point for direct HTTP acquisition when the source exposes stable HTML or JSON without browser interaction.
- [Scrapy](https://github.com/scrapy/scrapy): strong default for HTTP crawling, retries, throttling, and structured spider organization.
- [Playwright](https://github.com/microsoft/playwright): use only when the source requires browser rendering, interaction, or JavaScript execution.
- [Crawlee](https://github.com/apify/crawlee) / [Crawlee Python](https://github.com/apify/crawlee-python): useful if we want a higher-level crawling framework that can combine HTTP, browser automation, proxies, sessions, and retries.

Lean recommendation: start with HTTPX if one request is enough, Scrapy if crawling behavior matters, and Playwright only for sources that cannot be captured reliably without a browser.

### HTML and Payload Extraction

- [Parsel](https://github.com/scrapy/parsel): good fit for CSS/XPath extraction from HTML/XML and JSON extraction helpers.
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/): good fit for forgiving HTML parsing and readable extraction code.
- [selectolax](https://github.com/rushter/selectolax): useful later if HTML parsing speed becomes a measured bottleneck.

Lean recommendation: start with Parsel or Beautiful Soup. Add selectolax only after profiling shows parser speed matters.

### Contracts and Validation

- [Pydantic](https://github.com/pydantic/pydantic): good default for canonical listing models and record-level validation.
- [Pandera](https://github.com/unionai-oss/pandera): useful later if validation becomes dataframe-oriented.

Lean recommendation: start with Pydantic. Add Pandera only when batch/table validation becomes painful.

### Local Analytics and Storage

- [DuckDB](https://github.com/duckdb/duckdb): strong local analytical database for querying JSON, CSV, and Parquet without running a server.
- [Polars](https://github.com/pola-rs/polars): fast dataframe engine for transformations when SQL is not the best expression.

Lean recommendation: start with JSONL plus DuckDB for inspection and simple analytics. Add Polars when transformation code becomes clearer as dataframe operations.

### Entity Resolution

- [recordlinkage](https://github.com/J535D165/recordlinkage): useful for small-to-medium record linkage experiments.
- [dedupe](https://github.com/dedupeio/dedupe): useful when active-learning-assisted matching is needed.
- [Splink](https://moj-analytical-services.github.io/splink/index.html): useful later for probabilistic linkage at larger scale.

Lean recommendation: start with duplicate candidates and manual review. Do not auto-merge until false positives are understood.

### Later, Not MVP

- [Prefect](https://github.com/PrefectHQ/prefect): upgrade path when scripts need scheduling, retries, caching, and monitored unattended runs.
- [Dagster](https://github.com/dagster-io/dagster): upgrade path when data assets, lineage, and observability become central.
- [dbt Core](https://github.com/dbt-labs/dbt-core): upgrade path if transformations become mostly SQL models over warehouse/lake tables.
- [OpenLineage](https://github.com/OpenLineage/openlineage): upgrade path if lineage needs to integrate across tools and teams.

Lean recommendation: do not start here. A run manifest is enough until orchestration or metadata management becomes a real operational bottleneck.

## Upgrade Triggers

Add a new component only when one of these is true:

- Local runs are too slow for the current dataset.
- Multiple scheduled sources need unattended retries.
- Manual run inspection is no longer enough.
- Quarantine volume requires triage workflows.
- Artifact files are too large or numerous for simple local management.
- More than one developer/operator needs coordinated run visibility.
- Analytical transformations are mostly SQL and need stronger model governance.

## First Milestone Definition of Done

The first milestone is done when:

- One source can be acquired politely.
- Raw artifacts can be replayed without re-acquisition.
- One parser can produce canonical listings.
- Invalid records produce quarantine artifacts.
- Enriched output includes simple metrics and lineage.
- A developer can inspect every step from files and manifests.

## Devil's Advocate Guardrails

- If the raw payload is not enough to replay, acquisition captured the wrong artifact.
- If analytics needs source-specific fields, the canonical contract is incomplete.
- If parser failures only appear in logs, quarantine is not real.
- If duplicate handling erases source listings, lineage is broken.
- If adding a tool does not remove a current failure mode, the tool is probably premature.
