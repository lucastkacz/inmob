# Implementation and Run Log

## Purpose

This page is the short operational memory for future agents.

Use it to answer three questions quickly:

1. What changed in the current branch?
2. Why was it changed?
3. How was the latest data set produced and verified?

## Current Branch

- Branch: `feature/bronze-augmentation`
- Date recorded: 2026-06-27
- Goal: improve Bronze HTML acquisition so Silver can standardize a fresher and more complete listing set.

## Implemented Changes

### Shared Browser Capture

Added `src/inmob/ingestion/sources/browser.py`.

It fetches HTML pages with Playwright, waits for browser-rendered DOM, then performs a bounded reveal pass over safe same-page controls.

The reveal pass is intentionally narrow:

- It accepts map, location, expansion, amenity, school, restaurant, and characteristic controls.
- It rejects contact, WhatsApp, phone, email, login, favorite, share, download, and navigation actions.
- It stops if a click changes the document URL.
- It logs click count, payload bytes, final URI, elapsed time, and partial reveal errors.

This keeps Bronze semantically blind. Bronze only preserves better source evidence. Silver decides what the evidence means.

### Sources Using Browser Detail Capture

Listing detail pages now use browser capture for:

- `argenprop`
- `mudafy`
- `properati`
- `zonaprop`

Search and discovery remain HTTP where possible.

`cabaprop` and `remax` remain API-first because their JSON responses are already structured and more stable than browser HTML.

### Metadata Contract

Bronze and Silver metadata now carry `capture_metadata`.

Use this field to understand acquisition path:

- `browser_rendered`
- `render_strategy`
- `render_status`
- `reveal_click_count`
- `render_error`, only when reveal partially fails

### Silver Parser Improvement

Zonaprop now falls back to rendered map marker coordinates when script geolocation is missing.

The fallback reads marker HTML shaped like:

```html
position="-34.560893,-58.4429387"
```

## Tests and Checks

Before the full data refresh, these local checks passed:

```bash
PYTHONPATH=src poetry run pytest tests/unit -q
PYTHONPATH=src poetry run ruff check src tests
PYTHONPATH=src poetry run mypy src/inmob
```

New focused tests cover:

- HTML listing sources routing detail pages through browser rendering.
- Safe reveal candidate allow/deny behavior.
- Zonaprop marker-coordinate fallback.

## Latest Data Refresh

Run timestamp: 2026-06-27, America/Argentina/Buenos_Aires.

Bronze command:

```bash
PYTHONPATH=src poetry run inmob ingest --target-dir data/raw --log-dir logs --log-level INFO --log-file-level DEBUG
```

Bronze result:

| Source | New detail artifacts |
| --- | ---: |
| argenprop | 15 |
| cabaprop | 15 |
| mudafy | 15 |
| properati | 15 |
| remax | 15 |
| zonaprop | 15 |

Bronze log:

```text
logs/ingest_2026-06-27_11-20-09.log
```

Silver command:

```bash
PYTHONPATH=src poetry run inmob silver --raw-dir data/raw --db-path data/silver/inmob.sqlite --quarantine-dir data/quarantine --log-level INFO --log-file-level DEBUG
```

Silver result:

| Table | Rows |
| --- | ---: |
| listings_current | 178 |
| listing_attributes_current | 3312 |
| listing_observations | 178 |
| silver_quarantine | 0 |

Parsed by source:

| Source | Current rows |
| --- | ---: |
| argenprop | 30 |
| cabaprop | 30 |
| mudafy | 30 |
| properati | 30 |
| remax | 30 |
| zonaprop | 28 |

Fresh 2026-06-27 slice:

| Source | Refreshed rows |
| --- | ---: |
| argenprop | 15 |
| cabaprop | 15 |
| mudafy | 15 |
| properati | 15 |
| remax | 15 |
| zonaprop | 15 |

Silver log:

```text
logs/ingest_2026-06-27_11-26-38.log
```

CSV exports:

```text
data/silver/listings_current.csv
data/silver/listing_attributes_current.csv
```

## Replay Notes

Silver reads every artifact currently under `data/raw`, not only the newest run.

That is why the latest Silver database has 178 current rows while the 2026-06-27 refreshed slice has 90 rows.

To reproduce the latest current-list exports after running Silver:

```bash
sqlite3 -header -csv data/silver/inmob.sqlite "SELECT * FROM listings_current ORDER BY source_id, source_listing_id;" > data/silver/listings_current.csv
sqlite3 -header -csv data/silver/inmob.sqlite "SELECT * FROM listing_attributes_current ORDER BY source_id, source_listing_id, attribute_key;" > data/silver/listing_attributes_current.csv
```

## Commit Scope Guidance

Commit code, docs, tests, compact Silver outputs, and run logs.

Do not commit the full `data/raw` tree by default. It is large, ignored, and replayable from the documented Bronze command unless the user explicitly asks for a raw evidence snapshot.
