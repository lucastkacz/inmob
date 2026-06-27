# Lucas Zonaprop API and Gold Strategy Notes

## Purpose

This document records the working conversation with Lucas about moving from broad HTML scraping toward a leaner API-first Zonaprop ingestion strategy, plus the proposed Gold storage model.

It is optimized for future LLM agents. Start here when the task mentions:

- Zonaprop API
- `rplis-api/postings`
- daily scraping of 500k listings
- view count or `usersViews`
- Supabase/Postgres Gold storage
- Bronze/Silver/Gold restructuring
- Lucas strategy notes

## Current Date and Repo Context

- Date recorded: 2026-06-27
- Repo: `/Users/rayox/Desktop/inmob`
- Related external repo inspected: `/Users/rayox/Desktop/maximascraper`
- Branch at time of documentation: `feature/bronze-augmentation`

## Conversation Summary

Lucas wants an ingestion system for Argentine real estate listings across multiple sources. The sources do not share identical schemas, but their structures are relatively stable over time.

The target product is not just raw listings. The desired analytical layer should support:

- current listings
- price history
- view history when available
- status/disappearance detection
- derived metrics such as price per square meter
- enrichment and augmentation over time
- BI/dashboard use cases
- alerts for unusually cheap or attractive listings
- maps and zone statistics
- future macro/cost reference data

The immediate question was whether the discovery of a Zonaprop JSON API changes the scraping strategy. It does.

## High-Level Strategy

Use Zonaprop API-first ingestion for broad coverage.

Use detail HTML only for fields not present in the API, especially public view count and antiquity label.

Recommended split:

```text
rplis_api_sync
- broad coverage
- cheap relative to HTML
- fetches list/search data
- updates universe, prices, status, modified date, features, location, publisher, pictures

detail_metrics_sync
- narrower coverage
- fetches detail HTML
- extracts usersViews and antiquity
- writes historical observations
```

The jobs must share one global Zonaprop traffic policy. Do not let independent loops compete from the same IP/session without coordination.

## External Repo Finding

The repo `/Users/rayox/Desktop/maximascraper` contains a working Zonaprop API scraper pattern.

Key endpoint:

```text
https://www.zonaprop.com.ar/rplis-api/postings
```

The repo uses `cloudscraper`, SQLite, and throttled looping. The useful discovery is the endpoint and payload shape, not the specific storage choice.

## Zonaprop API POC

A POC was run in this repo using the API endpoint.

Output file:

```text
data/raw/zonaprop_api_poc/zonaprop_rplis_api_poc_100_full_pages_20260627_202328.json
```

POC properties:

- Source: Zonaprop
- Endpoint: `https://www.zonaprop.com.ar/rplis-api/postings`
- Query target: CABA, Departamento, Venta
- Sort: `more_recent`
- API pages fetched: 4
- Final postings selected: 100
- First-page paging observed:
  - `total`: 76572
  - `limit`: 30
  - `totalPages`: 2553

The POC JSON includes:

- `poc`
- `endpoint`
- `captured_at`
- `requested_postings`
- `postings_count`
- `pages_fetched`
- `query`
- `base_payload`
- `headers_used`
- `http_events`
- `postings`
- `raw_page_responses`

Important: this POC file intentionally preserves more than a cleaned Gold record. It includes raw page responses and execution metadata, so it is heavier than the final Gold model should be.

## API Data Shape

The `rplis-api/postings` response contains useful listing data such as:

- `postingId`
- `postingCode`
- `url`
- `title`
- `status`
- `reserved`
- `premier`
- `modified_date`
- `priceOperationTypes`
- `expenses`
- `mainFeatures`
- `postingLocation`
- `publisher`
- `visiblePictures`
- `paging`
- `listPostings`

The API is strong enough to maintain the listing universe and most current listing fields.

## Specific Property Investigated

Lucas asked about this property:

```text
https://www.zonaprop.com.ar/propiedades/clasificado/veclapin-ph-reciclado-de-3-ambientes-1er-piso-por-escalera-en-59486695.html
```

Property identifiers:

- `postingId`: `59486695`
- `postingCode`: `MAP5838091`
- URL path: `/propiedades/clasificado/veclapin-ph-reciclado-de-3-ambientes-1er-piso-por-escalera-en-59486695.html`
- Title: `PH Reciclado de 3 Ambientes 1er Piso por Escalera en Las Cañitas`
- Status: `ONLINE`
- Modified date from API: `2026-06-27T11:51:37-0400`
- Price: USD 205000
- Publisher: Maure Inmobiliaria
- `publisherId`: `17043666`

Selected API features observed:

| Feature ID | Meaning | Value |
| --- | --- | --- |
| `CFT100` | Total area | 88 m2 |
| `CFT101` | Covered area | 79 m2 |
| `CFT1` | Rooms | 3 |
| `CFT2` | Bedrooms | 2 |
| `CFT3` | Bathrooms | 1 |
| `CFT4` | Toilettes | 1 |
| `CFT5` | Age | 63 |
| `1000019` | Disposition | Frente |
| `1000029` | Orientation | NE |
| `1000027` | Luminosity | Muy luminoso |

Location:

- Address label: `Maure al 1800 Piso 1 PH - Reservado`
- Neighborhood: Las Cañitas / Palermo / CABA
- Latitude: `-34.5678663`
- Longitude: `-58.4368188`

## View Count Investigation

Lucas showed a page element:

```html
<div id="user-views" class="view-users-container">
  ...
  <p>Publicado hoy</p>
  ...
  <p>26 visualizaciones</p>
</div>
```

The question was: where does `26 visualizaciones` come from?

Files produced during the investigation:

```text
data/raw/zonaprop_api_poc/59486695/zonaprop_59486695_detail_http.html
data/raw/zonaprop_api_poc/59486695/zonaprop_59486695_network_capture.json
data/raw/zonaprop_api_poc/59486695/zonaprop_59486695_detail_rendered.html
```

Finding:

The value did not come from a visible XHR/fetch JSON response in the captured network traffic.

It was embedded in the initial detail HTML document:

```js
const usersViews =  26
const antiquity =  'Publicado hoy'
```

The rendered React component then displays:

```text
Publicado hoy
26 visualizaciones
```

When inspecting in the browser Network tab, look at:

```text
Document -> Response -> search "usersViews"
```

Do not expect this value in normal XHR/fetch requests based on current evidence.

Observed network candidates:

```text
/rplis-api/user/activity?postingsIds=59486695
/rpfic-api/listado/activity
/aviso_hit.ajax?idAviso=59486695
/tracking/g/collect
```

Interpretation:

- `/aviso_hit.ajax` likely records a visit/hit.
- `/tracking/g/collect` is analytics/tracking.
- `/rplis-api/user/activity` likely describes logged-in user activity such as favorites or seen state.
- `/rpfic-api/listado/activity` also appears user/listing activity related.
- None was proven to return the public `usersViews` count.

Most likely backend flow:

```text
Zonaprop backend queries internal metrics storage
-> server renders detail HTML
-> HTML includes const usersViews = 26
-> frontend JS renders the visible element
```

## View Count Extraction Strategy

For now, use detail HTML as the reliable source for public view count.

Extractor pattern:

```regex
const usersViews\s*=\s*(\d+)
const antiquity\s*=\s*'([^']+)'
```

Store extraction metadata:

```text
views_source = detail_html_inline_script
views_count = 26
antiquity_label = Publicado hoy
observed_at = capture timestamp
```

Use plain HTTP detail GET if possible. Playwright is not required for this field because the value exists in the initial HTML document.

## Can We Ask Only for the View Count?

No public endpoint was found that returns only this number.

Options considered:

- Normal GET of detail HTML: best current option.
- Streaming response and stopping after `usersViews`: possible, but fragile and may not save much because the script appears relatively low in the document.
- HTTP Range request: fragile because gzip/brotli and server behavior can make ranges unreliable.
- Internal API discovery: ideal if found later, but not present in current captured network evidence.

Current recommendation:

```text
Use rplis-api/postings for broad daily sync.
Use detail HTML only for selected properties that need view metrics.
```

## Ban and Rate-Limit Discussion

Lucas wants to monitor roughly 500k Zonaprop properties daily.

Risks:

- IP-level rate limiting
- session/fingerprint limiting
- Cloudflare challenges
- service instability if multiple jobs run independently
- HTML detail fetches are much heavier than API list calls

Important point:

Running `rplis_api_sync` and `detail_metrics_sync` separately can still affect the same IP/domain budget. If one job triggers throttling, the other job may suffer.

Recommendation:

- One global rate limiter per source/domain.
- Shared request budget across all Zonaprop jobs.
- Full-jitter backoff on 403, 429, captcha, connection errors, or latency spikes.
- Start with small POCs and scale gradually.
- Measure actual status codes, body sizes, and latency before attempting full coverage.

Do not begin with 500k detail HTML requests per day.

## Suggested Daily Crawl Tiers

Use the API to decide what needs detail refresh.

Suggested priority:

| Tier | Properties | View HTML refresh cadence |
| --- | --- | --- |
| Hot | new today, modified today, top target zones | every 6-12h |
| Warm | recently active or recently changed | daily |
| Cold | old listings with no API changes | weekly or rotating sample |
| Dead | offline/disappeared/reserved long ago | rarely or never |

This keeps the view-count job useful without forcing 500k HTML documents every day.

## HTML Size and Storage Estimate

The specific detail HTML saved for property `59486695` was approximately:

```text
532 KB
```

If fetching 500k detail pages daily at that rough size:

```text
500,000 * 0.5 MB = roughly 250 GB/day uncompressed
```

The request count is:

```text
500,000 requests/day = about 5.8 requests/second sustained over 24h
```

This is technically possible from an infrastructure perspective, but it is a meaningful load and raises rate-limit risk.

## POC JSON Size Estimate

Lucas asked how large 500k cleaned API listings would be.

Measured file:

```text
data/raw/zonaprop_api_poc/zonaprop_rplis_api_poc_100_full_pages_20260627_202328.json
```

Measured sizes:

| Shape | Bytes for 100 | Approx per property | Approx for 500k |
| --- | ---: | ---: | ---: |
| Full POC file | 3,147,277 | 31.5 KB | 15.7 GB |
| `.postings` only | 908,467 | 9.1 KB | 4.5 GB |
| Clean useful subset | 596,399 | 6.0 KB | 3.0 GB |

Clean useful subset included:

```text
postingId
postingCode
url
title
status
modified_date
priceOperationTypes
expenses
mainFeatures
postingLocation
publisher
visiblePictures
```

Conclusion:

Gold storage for 500k current listings is not the hard part. It likely lands around 2.5-5 GB before indexes and history.

JSON compression can reduce storage substantially. A JSON-like dataset may compress by roughly 70-85%, so 3 GB can become approximately 500 MB to 1 GB if stored as compressed artifacts.

The hard parts are:

- daily acquisition volume
- source rate limits
- historical growth
- index design
- schema evolution
- deduplication across sources

## Database Strategy

Lucas asked whether Postgres can behave like a SQL + NoSQL hybrid.

Answer:

Yes. Postgres supports structured relational tables plus flexible `jsonb`, and Supabase provides hosted Postgres with APIs, auth, storage, and a dashboard.

This is a good fit because:

- core fields can be typed columns
- variable attributes can be key/value rows or `jsonb`
- source-specific leftovers can remain in `jsonb`
- new derived metrics can be added later as typed columns or generated/materialized fields
- different property types can coexist without huge sparse tables

Avoid one giant table with hundreds of nullable columns.

Use a hybrid model:

```text
typed columns for stable high-value fields
attribute rows for variable source/property attributes
jsonb for raw source-specific leftovers
history tables for time series
```

## Recommended Gold Tables

### `gold.listings_current`

One row per canonical listing/source listing identity.

Use for dashboards and current state.

Suggested columns:

```text
id
source
source_listing_id
source_listing_code
canonical_url
title
description
property_type
operation_type
status
reserved
publisher_id
publisher_name
price_amount
price_currency
expenses_amount
expenses_currency
total_area_m2
covered_area_m2
rooms
bedrooms
bathrooms
toilettes
age_years
address_label
neighborhood
city
province
country
latitude
longitude
first_seen_at
last_seen_at
source_modified_at
latest_views_count
latest_views_observed_at
source_specific_jsonb
created_at
updated_at
```

### `gold.listing_observations`

Append-only observations for each crawl/touch.

Use this to know what changed over time.

Suggested columns:

```text
id
listing_id
source
source_listing_id
observed_at
observation_type
status
price_amount
price_currency
expenses_amount
views_count
antiquity_label
source_modified_at
http_status
extraction_source
error
raw_snapshot_hash
raw_snapshot_jsonb
```

### `gold.price_history`

Only append when price changes.

Suggested columns:

```text
id
listing_id
source
source_listing_id
valid_from
valid_to
price_amount
price_currency
expenses_amount
expenses_currency
change_detected_at
change_reason
```

### `gold.view_history`

Append each successful view-count observation, if this metric remains valuable.

Suggested columns:

```text
id
listing_id
source
source_listing_id
observed_at
views_count
views_window
antiquity_label
extraction_source
http_status
error
```

The `views_window` should start as:

```text
unknown_or_30d
```

Reason: the Zonaprop UI tooltip/code suggests the count may represent people who saw the listing in the last 30 days, but this should be validated before treating it as lifetime views.

### `gold.listing_attributes`

Use for variable features across apartments, houses, land, PH, developments, and source-specific attributes.

Suggested columns:

```text
id
listing_id
source
source_listing_id
attribute_key
attribute_label
attribute_value_text
attribute_value_number
attribute_unit
attribute_group
source_attribute_id
observed_at
```

Examples:

```text
CFT100 -> total area
CFT101 -> covered area
CFT1 -> rooms
1000019 -> disposition
1000029 -> orientation
1000027 -> luminosity
```

### `gold.listing_media`

Use for photos and media URLs.

Suggested columns:

```text
id
listing_id
source
source_listing_id
media_type
url
position
is_cover
caption
observed_at
```

Store image URLs first. Do not store binary images unless there is a concrete product need.

### `gold.publishers`

Optional but useful for agency/seller analysis.

Suggested columns:

```text
id
source
source_publisher_id
publisher_name
publisher_type
phone
email
url
source_specific_jsonb
first_seen_at
last_seen_at
```

## Supabase Recommendation

Lucas asked what cloud tool is lean, easy, low-maintenance, and low-cost for Gold.

Recommendation:

Use Supabase hosted Postgres for Gold.

Reasons:

- simple hosted Postgres
- supports SQL and `jsonb`
- low operational overhead
- good enough dashboard/admin tools
- direct APIs available
- easy to evolve schema
- can integrate storage later if raw snapshots or exports are needed

Use filesystem or object storage only when needed for raw artifacts, large snapshots, or replay. If the only thing that matters is Gold, do not overbuild a lakehouse early.

## Raw/Bronze/Silver/Gold Position

Lucas asked whether intermediate tiers need to store data if only Gold matters.

Practical answer:

For a lean MVP:

```text
API/HTML fetch -> normalize -> upsert Gold + append history
```

Do not over-invest in full raw retention if traceability is not important right now.

However, keep enough lightweight evidence to debug:

- source
- source URL
- source listing ID
- observed timestamp
- extraction method
- HTTP status
- payload hash
- error text
- optional small raw JSON snapshot for API records

For API responses, storing compact `jsonb` snapshots is cheap and useful.

For detail HTML, do not store full HTML for every daily view update unless debugging requires it. Store extracted value, extraction source, status code, and maybe a hash.

## Derived Metrics

Future metrics such as price per square meter should not block the current schema.

Add later as:

- typed columns on `listings_current` if high-value and heavily queried
- materialized views if derived from stable fields
- metric tables if versioned or recalculated over time
- `jsonb` or attribute rows for experimental values

Example:

```text
price_per_total_m2 = price_amount / total_area_m2
price_per_covered_m2 = price_amount / covered_area_m2
```

Do not store every possible derived metric as a physical column on day one.

## Practical Next Steps

Recommended short path:

1. Keep using `rplis-api/postings` for Zonaprop broad ingestion.
2. Normalize 100-1000 API records into a proposed Gold schema locally.
3. Add a tiny detail HTML extractor for `usersViews` and `antiquity`.
4. Run view extraction on a small sample.
5. Store results as observations, not destructive updates.
6. Measure:
   - success rate
   - 403/429/captcha rate
   - average HTML bytes
   - latency
   - extracted view-count coverage
7. Only then decide crawl budget for daily view updates.

## Known Open Questions

- Is `usersViews` lifetime views or rolling 30-day views?
- Can a hidden/internal public JSON endpoint for view counts be discovered later?
- Does `modified_date` reliably change when price changes?
- Does `modified_date` change when only views change?
- Can `rplis-api/postings` cover all Zonaprop listing categories reliably?
- How stable are feature IDs such as `CFT100`, `CFT101`, `CFT1`, etc.?
- How should cross-source deduplication identify the same physical property?
- Which fields are truly needed for the first dashboard?

## Strong Recommendations

1. Do not scrape 500k detail HTML pages daily at the beginning.
2. Do use the API to reduce detail-page work.
3. Do keep a global rate limiter per source/domain.
4. Do write observations historically.
5. Do use Postgres/Supabase with typed columns plus `jsonb`.
6. Do avoid one huge sparse table full of nulls.
7. Do keep source-specific attributes flexible.
8. Do not overbuild Bronze/Silver storage if Gold delivery is the immediate business goal.

## Key Local Files

POC API data:

```text
data/raw/zonaprop_api_poc/zonaprop_rplis_api_poc_100_full_pages_20260627_202328.json
data/raw/zonaprop_api_poc/zonaprop_rplis_api_poc_100_20260627_202220.json
```

Detail view-count investigation:

```text
data/raw/zonaprop_api_poc/59486695/zonaprop_59486695_detail_http.html
data/raw/zonaprop_api_poc/59486695/zonaprop_59486695_network_capture.json
data/raw/zonaprop_api_poc/59486695/zonaprop_59486695_detail_rendered.html
```

Existing operational docs:

```text
docs/Home.md
docs/08 - Implementation and Run Log.md
docs/06 - Decision Log.md
```

## One-Sentence Handoff

Use Zonaprop `rplis-api/postings` as the daily high-volume source of truth for listing state, use detail HTML only as a secondary metrics source for `usersViews` and `antiquity`, and store Gold in Supabase/Postgres with typed core fields, flexible attributes, `jsonb` leftovers, and append-only history tables.
