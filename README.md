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

Browser capture notes:

- `argenprop`, `mudafy`, `properati`, and `zonaprop` listing-detail pages are fetched through Playwright because important HTML evidence can be rendered or revealed only after JavaScript runs.
- The shared browser helper performs a bounded same-page reveal pass for safe expansion/map controls, records `capture_metadata`, and persists the final DOM as Bronze evidence.
- Search/discovery pages still use regular HTTP where possible. `cabaprop` and `remax` stay API-first because their JSON payloads already carry better structured evidence.

## Silver CLI

Silver is the local, replayable standardization step. It reads Bronze raw
artifacts from `data/raw`, extracts stable structured listing facts, and writes
queryable current state plus observation history to SQLite.

Run Silver:

```bash
PYTHONPATH=src poetry run inmob silver \
  --raw-dir data/raw \
  --db-path data/silver/inmob.sqlite \
  --quarantine-dir data/quarantine \
  --log-level INFO \
  --log-file-level DEBUG
```

Main outputs:

```text
data/silver/inmob.sqlite
data/silver/listings_current.csv
data/silver/listing_attributes_current.csv
data/quarantine/{source}/{raw_artifact_id}_quarantine.json
logs/ingest_YYYY-MM-DD_HH-mm-ss.log
```

SQLite tables:

```text
listings_current             One current row per (source_id, source_listing_id).
listing_observations         One replayable observation per raw artifact.
listing_attributes_current   Queryable amenities, booleans, and source-specific filters.
silver_quarantine            Parser/validation failures with raw paths and reasons.
```

Current v2 Silver extracts:

- Lineage: source, source listing id, raw artifact id, capture time, payload hash, parser id/version.
- Commercial facts: price, currency, expenses, price visibility.
- Surfaces: total, covered, uncovered, semicovered, terrace, exclusive m2.
- Location: address, street, neighborhood, city, province, postal code, commune, map address, latitude, longitude.
- Seller/contact: seller/agency/office, license, phone, email, WhatsApp, contact URL.
- Listing facts: operation type, property type/subtype, rooms, bedrooms, bathrooms, toilettes, parking, age, construction year, floor, building floors, orientation, disposition, brightness, condition.
- Source IDs: advertiser/agency/branch/office/internal/posting code, external reference.
- Filterable attributes: amenities and booleans from each source, stored in `listing_attributes_current`.

Source parser notes:

- `cabaprop` and `remax` are JSON-first and usually have the best structured coverage.
- `zonaprop`, `argenprop`, `properati`, and `mudafy` are HTML/script-state parsers.
- `mudafy` uses Next.js/RSC script chunks; Silver parses the visible structured `fields` block where possible.
- `zonaprop` development listings (`emprendimiento`) may have location/views/amenities but no unit price or surface in the saved detail page.

Known limitations:

- Static raw HTML does not always contain every field visible in the browser. Some contact data, map state, unit details, phone numbers, and WhatsApp links can appear only after JavaScript runs or after a click.
- HTML listing-detail Bronze capture for `argenprop`, `mudafy`, `properati`, and `zonaprop` uses a bounded Playwright reveal pass before saving HTML. Search pages still use regular HTTP except `zonaprop`, which already needs Playwright for acquisition.
- The reveal pass is acquisition-only: Bronze clicks safe same-page expansion/map controls, logs the browser path, stores `capture_metadata`, and saves the final DOM. Silver remains responsible for parsing facts such as coordinates.
- `cabaprop` and `remax` remain API-first. Do not replace structured API payloads with browser HTML unless the API stops carrying required evidence.
- Numeric source codes are preserved when no reliable label exists. Do not invent mappings without source proof.
- Description text is intentionally not used for analytics because it is free-form and unstable.

Useful Silver queries:

```bash
# Counts by table.
sqlite3 data/silver/inmob.sqlite "
SELECT 'listings_current', count(*) FROM listings_current
UNION ALL SELECT 'listing_attributes_current', count(*) FROM listing_attributes_current
UNION ALL SELECT 'listing_observations', count(*) FROM listing_observations
UNION ALL SELECT 'silver_quarantine', count(*) FROM silver_quarantine;
"

# Coverage by source.
sqlite3 -header -column data/silver/inmob.sqlite "
SELECT
  source_id,
  count(*) AS rows,
  sum(price_amount IS NOT NULL) AS price,
  sum(surface_total_m2 IS NOT NULL) AS total_m2,
  sum(surface_covered_m2 IS NOT NULL) AS covered_m2,
  sum(latitude IS NOT NULL AND longitude IS NOT NULL) AS coords,
  sum(address IS NOT NULL) AS address,
  sum(views_count IS NOT NULL) AS views
FROM listings_current
GROUP BY source_id
ORDER BY source_id;
"

# Export all rows for one source to CSV.
sqlite3 -header -csv data/silver/inmob.sqlite "
SELECT *
FROM listings_current
WHERE source_id = 'zonaprop'
ORDER BY source_listing_id;
" > data/silver/zonaprop_all.csv

open data/silver/zonaprop_all.csv

# Export all amenities/attributes for one source to CSV.
sqlite3 -header -csv data/silver/inmob.sqlite "
SELECT *
FROM listing_attributes_current
WHERE source_id = 'zonaprop'
ORDER BY source_listing_id, attribute_key;
" > data/silver/zonaprop_attributes.csv

open data/silver/zonaprop_attributes.csv

# Same pattern for another source.
sqlite3 -header -csv data/silver/inmob.sqlite "
SELECT *
FROM listings_current
WHERE source_id = 'argenprop'
ORDER BY source_listing_id;
" > data/silver/argenprop_all.csv
```

LLM handoff summary for this branch:

- Branch: `feature/bronze-augmentation`.
- Bronze listing-detail HTML capture now uses shared Playwright rendering with bounded safe reveal clicks for `argenprop`, `mudafy`, `properati`, and `zonaprop`; `cabaprop` and `remax` stay API-first.
- Bronze metadata now includes `capture_metadata` so downstream tools can tell whether a payload came from HTTP, browser render, or browser render plus reveal.
- Added `inmob silver` to the Typer CLI.
- Added Silver contracts, parsers, runner, SQLite store, quarantine support, and fixture-backed unit tests under `src/inmob/standardization` and `tests/unit/standardization`.
- Added additive SQLite migration behavior so re-running Silver upgrades an existing `data/silver/inmob.sqlite`.
- Added `listing_attributes_current` to avoid hundreds of sparse amenity columns while keeping filter fields queryable.
- Added a Zonaprop coordinate fallback from rendered map marker HTML when script geolocation is missing.
- Last validated local unit checks before the data refresh passed: `pytest tests/unit -q`, `ruff check src tests`, and `mypy src/inmob`.
- Latest full data refresh on 2026-06-27:
  - Bronze command: `PYTHONPATH=src poetry run inmob ingest --target-dir data/raw --log-dir logs --log-level INFO --log-file-level DEBUG`
  - Bronze result: 15 listings per source, 90 new raw detail artifacts total, 0 command failures.
  - Silver command: `PYTHONPATH=src poetry run inmob silver --raw-dir data/raw --db-path data/silver/inmob.sqlite --quarantine-dir data/quarantine --log-level INFO --log-file-level DEBUG`
  - Silver result: 178 artifacts parsed, 0 quarantined, 178 `listings_current`, 3312 `listing_attributes_current`, 178 `listing_observations`.
  - Fresh 2026-06-27 slice: 90 rows, exactly 15 per source.
  - CSV exports: `data/silver/listings_current.csv` and `data/silver/listing_attributes_current.csv`.
  - Logs: `logs/ingest_2026-06-27_11-20-09.log` for Bronze and `logs/ingest_2026-06-27_11-26-38.log` for Silver.

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
