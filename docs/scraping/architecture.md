# Data Ingestion & Scraper Architecture

## 1. Overview

The ResearchConnect AI scraping pipeline is a modular, multi-stage ingestion system designed to discover, extract, normalize, validate, deduplicate, and persist academic opportunities (conferences, journals, workshops, special issues, calls for papers) into PostgreSQL.

The architecture strictly adheres to single-responsibility principles without heavy distributed systems or external queue brokers:

```
WikiCFP (or other external source)
  │
  ▼
[HTTP Client] ── Transport layer (retries, backoff, User-Agent, timeouts)
  │
  ▼
[Source Fetcher] ── Pagination, crawl-delay enforcement (robots.txt compliance)
  │
  ▼
[Source Parser] ── Extracts typed `RawOpportunity` records via BeautifulSoup
  │
  ▼
[Normalizer] ── Cleans whitespace, canonicalizes URLs, parses dates, infers types & delivery modes
  │
  ▼
[Validator] ── Schema validation, date sanity checks, type allowlists (drops invalid records)
  │
  ▼
[Duplicate Detector] ── Multi-tier deduplication (Confirmed vs Potential duplicates vs Unique)
  │
  ▼
[Change Detection & Persistence] ── Upserts records (NEW, UPDATED, UNCHANGED, EXPIRED) & tracks IngestionRuns
  │
  ▼
PostgreSQL Database
  │
  ▼
FastAPI API (`GET /api/opportunities`)
  │
  ▼
React + TypeScript Frontend
```

---

## 2. Record Lifecycle & State Management

The ingestion system distinguishes between **Ingestion Actions** (the outcome of an ingestion cycle) and **Business Lifecycle Statuses** (persisted on the opportunity model):

### 2.1. Ingestion Lifecycle Actions (`LifecycleAction`)
- **`NEW`**: An opportunity discovered for the first time; inserted into PostgreSQL.
- **`UPDATED`**: An existing opportunity whose metadata (deadline, location, title, etc.) has changed since the last scrape; mutable fields and `updated_at` are refreshed.
- **`UNCHANGED`**: An existing opportunity with identical data; only `last_seen_at` is refreshed.
- **`DUPLICATE`**: A confirmed duplicate within the current feed (same `source_id + raw_source_id` or canonical URL); skipped.
- **`POTENTIAL_DUPLICATE`**: A soft duplicate across categories/feeds (same normalized title + submission deadline); flagged for audit but not automatically merged.
- **`INVALID`**: Record failed structural validation or date sanity checks; dropped with logged reasons.
- **`EXPIRED`**: Record whose submission deadline or event date has passed; persisted with `status = "EXPIRED"`.

### 2.2. Business Statuses (`OpportunityModel.status`)
- **`ACTIVE`**: Verified active submission target with upcoming deadline.
- **`UNVERIFIED`**: Freshly ingested opportunity awaiting secondary enrichment or verification.
- **`EXPIRED`**: Passed submission deadline/event date; preserved for historical analysis and tracking.
- **`ARCHIVED`**: Manually archived or discontinued venue.
- **`DRAFT`**: Draft opportunity posting.

---

## 3. Change Detection & Freshness

### 3.1. Change Detection (`scrapers/change_detection/detector.py`)
Compares incoming normalized data against current database records across all mutable fields:
- `title`, `opportunity_type`, `publisher`, `organizer`, `series_name`, `edition`
- `summary`, `description`, `website_url`, `submission_url`
- `location`, `delivery_mode`
- `submission_deadline`, `notification_date`, `camera_ready_deadline`
- `event_start_date`, `event_end_date`
- `indexing`, `apc_or_fee`

**Preservation Guarantee:** Primary key UUID and `created_at` are never altered. Detailed non-empty existing fields are protected from being overwritten by `None` values from lightweight list pages.

### 3.2. Freshness Tracking (`scrapers/freshness/manager.py`)
- **`created_at`**: Timestamp when the opportunity was first discovered.
- **`last_seen_at`**: Timestamp when the opportunity was last observed in a live crawl (updated on `NEW`, `UPDATED`, and `UNCHANGED`).
- **`last_verified_at`**: Timestamp of last automated or human verification.
- **Staleness Assessment**: Data is flagged as stale if `last_seen_at` exceeds a configurable threshold (default: 30 days).

---

## 4. Expiration Management (`scrapers/expiration/manager.py`)

- **Deterministic Evaluation**: Compares `submission_deadline` against current UTC time. If no submission deadline exists, compares `event_end_date` against current UTC date.
- **Preservation of History**: Expired opportunities are transitioned to `status = "EXPIRED"`; records are never deleted.
- **Scheduled Sweep**: CLI flag `--sweep-expired` performs an indexed database sweep over all active records to transition expired deadlines.

---

## 5. Duplicate Detection (`scrapers/deduplication/detector.py`)

Three-tier duplicate classification engine:

1. **Tier 1 (Primary / Strongest)**: `(source_name, raw_source_id)` composite key match $\rightarrow$ `CONFIRMED_DUPLICATE`.
2. **Tier 2 (Secondary)**: SHA-256 fingerprint of canonicalized external `website_url` $\rightarrow$ `CONFIRMED_DUPLICATE`.
3. **Tier 3 (Tertiary / Soft Match)**: SHA-256 fingerprint of normalized `title` + `submission_deadline` date string $\rightarrow$ `POTENTIAL_DUPLICATE` (logged for metrics, not automatically blocked).
4. **Unique Records**: No matching fingerprints $\rightarrow$ `UNIQUE`.

---

## 6. Source Health & Ingestion Audit (`IngestionRunModel`)

Every pipeline run automatically records operational metrics in PostgreSQL:

- **Source Health (`sources` table)**:
  - `last_scraped_at`: Timestamp of latest scrape attempt.
  - `last_successful_scrape_at`: Timestamp of latest successful scrape without unhandled errors.
  - `last_failed_scrape_at`: Timestamp of latest failed run.
  - `consecutive_failure_count`: Counter incremented on error, reset to 0 on success.
  - `total_scrape_count`: Total lifetime ingestion runs.
- **Ingestion Run Audit (`ingestion_runs` table)**:
  - `source_id`, `status` (`RUNNING`, `COMPLETED`, `FAILED`), `topic`
  - Metrics: `pages_fetched`, `records_parsed`, `records_valid`, `records_invalid`, `records_inserted`, `records_updated`, `records_unchanged`, `duplicates_detected`, `potential_duplicates_detected`, `records_expired`
  - Timestamps: `started_at`, `completed_at`
  - `error_message` & `metrics_detail` (JSONB)

---

## 7. Manual Pipeline Execution

The scraping pipeline is strictly manual and does not run automatically on FastAPI startup.

### Running via CLI:

```bash
# Dry-run test (fetches, parses, validates, and deduplicates without database writes)
python -m scrapers.pipelines.collect_opportunities --topic "artificial intelligence" --pages 1 --dry-run

# Live ingestion against PostgreSQL with expiration sweep
python -m scrapers.pipelines.collect_opportunities --topic "machine learning" --pages 2 --sweep-expired
```

### CLI Arguments:
- `--topic`: Search term for WikiCFP categories (default: `"artificial intelligence"`).
- `--pages`: Number of paginated pages to fetch (default: `1`).
- `--dry-run`: Flag to run pipeline without database writes.
- `--sweep-expired`: Flag to sweep existing active database records for expired deadlines.

### Structured Output:

```json
{
  "source": "WikiCFP",
  "topic": "artificial intelligence",
  "pages_fetched": 1,
  "parsed": 20,
  "valid": 20,
  "invalid": 0,
  "inserted": 18,
  "updated": 1,
  "unchanged": 1,
  "duplicates": 0,
  "potential_duplicates": 0,
  "expired": 0,
  "errors": 0,
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

---

## 8. Source-Specific Details (WikiCFP)

- **Access Policy**: WikiCFP allows web crawling with a mandatory minimum crawl delay of 5.0 seconds (specified in `robots.txt` and `/cfp/data.jsp`).
- **Content Type**: Server-side rendered static HTML; no JavaScript execution or Playwright required.
- **Limitations**:
  - Search list pages do not include full CFP descriptions or external submission URLs; only event titles, dates, locations, deadlines, and WikiCFP detail links are provided.
  - Detail page scraping can be attached in future phases to fetch full CFP descriptions and organizer URLs.
