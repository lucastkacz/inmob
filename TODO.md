# TODO

This file tracks upcoming tasks, enhancements, and operational updates for the Inmob real estate platform.

## Ingest / Scraping Layer

- [x] **Implement Professional Logging (`loguru`)**
  - Integrate `loguru` to replace basic print statements across the ingestion CLI, adapters, and traffic controllers.
  - Configure log levels (`INFO`, `WARNING`, `ERROR`, `DEBUG`) to capture:
    - Ingestion startup configurations.
    - Search result page request status.
    - Discovered listings totals.
    - Step-by-step sequential property crawls and storage status.
    - Network retries, transient rate limit delays, and WAF challenge refreshes.
    - Detailed exception traces on fetch/parse failures.
    - Execution timings (start/end timestamps, elapsed durations of fetches, intentional politeness delays, and session updates) to inspect anti-bot behavior.
  - Setup rotation and retention policies for log files (e.g., storing operational execution logs under `logs/ingest_{time}.log`).
