# Inmob

ETL/data platform for Argentine real estate listing ingestion.

## Setup

Requirements:

- Python `>=3.12,<4.0`
- Poetry

Install dependencies from the repo root:

```bash
poetry install
```

Install the Playwright browser used by browser-based sources:

```bash
poetry run playwright install chromium
```

Optional sanity check:

```bash
PYTHONPATH=src poetry run pytest tests/unit -q
```

## Bronze CLI

Run the default Bronze download:

```bash
PYTHONPATH=src poetry run inmob ingest
```

Default behavior:

- Source: `all`
- Limit: `15` properties per source
- Output data: `data/raw`
- Output logs: `logs`
- Sources: `argenprop`, `cabaprop`, `mudafy`, `properati`, `remax`, `zonaprop`

Expected raw output shape:

```text
data/raw/{source}/{property_id}/{source}_{property_id}_raw_payload.html
data/raw/{source}/{property_id}/{source}_{property_id}_raw_metadata.json
```

JSON API sources write `.json` payloads instead of `.html`.

Expected log output:

```text
logs/ingest_YYYY-MM-DD_HH-mm-ss.log
```

The log includes command start/end, source summaries, fetch status, saved payload paths, traffic policy, politeness waits, retries, and per-source traffic summaries.

## Common Commands

Run all sources with the default 15 properties each:

```bash
PYTHONPATH=src poetry run inmob ingest
```

Run one source with the default 15 properties:

```bash
PYTHONPATH=src poetry run inmob ingest --source zonaprop
```

Run one source with a custom property limit:

```bash
PYTHONPATH=src poetry run inmob ingest --source properati --limit 30
```

Run all sources with a custom property limit:

```bash
PYTHONPATH=src poetry run inmob ingest --limit 50
```

Scan search pages instead of using a property limit:

```bash
PYTHONPATH=src poetry run inmob ingest --source cabaprop --pages 2
```

Write data and logs to custom directories:

```bash
PYTHONPATH=src poetry run inmob ingest --limit 15 --target-dir data/raw-smoke --log-dir logs/smoke
```

Keep console quiet and write verbose diagnostics to file:

```bash
PYTHONPATH=src poetry run inmob ingest --log-level INFO --log-file-level DEBUG
```

## CLI Options

```text
--source, -s       Source to scrape: argenprop, cabaprop, mudafy, properati, remax, zonaprop, all.
--limit, -l        Max properties per source. Defaults to 15 when --pages is not provided.
--pages, -p        Number of search result pages to scan. Used only when --limit is omitted.
--target-dir, -d   Raw data output directory. Default: data/raw.
--config, -c       JSON file with per-source criteria overrides.
--log-dir          Log output directory. Default: logs.
--log-level        Console log level. Default: INFO.
--log-file-level   File log level. Default: INFO.
--log-rotation     Loguru rotation policy. Default: 10 MB.
--log-retention    Loguru retention policy. Default: 14 days.
```

If both `--limit` and `--pages` are provided, `--limit` wins.

## Criteria Override File

Pass a JSON file with source keys and criteria fields to override the defaults.

Example:

```json
{
  "properati": {
    "location": "capital-federal",
    "property_type": "departamento",
    "sort": "published_on_desc"
  }
}
```

Run it:

```bash
PYTHONPATH=src poetry run inmob ingest --source properati --config criteria.json
```

## Code Layout

```text
src/inmob/cli/cli.py            Typer entrypoint.
src/inmob/cli/bronze/config.py  Default Bronze source criteria.
src/inmob/cli/bronze/runner.py  Bronze orchestration.
src/inmob/cli/bronze/store.py   Raw artifact persistence.
src/inmob/ingestion/sources/    Source-specific fetch and discovery logic.
src/inmob/ingestion/traffic/    Politeness, pacing, and retry controller.
src/inmob/logging/              Loguru setup.
```

## Checks

```bash
PYTHONPATH=src poetry run ruff check src tests
PYTHONPATH=src poetry run mypy src/inmob
PYTHONPATH=src poetry run pytest -q
```
