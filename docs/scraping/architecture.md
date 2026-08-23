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
[Duplicate Detector] ── Multi-tier deduplication (source+id, URL fingerprint, title+deadline)
  │
  ▼
[Persistence Repository] ── Upserts Source metadata & OpportunityModel records via SQLAlchemy
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

## 2. Core Components

### 2.1. Internal Data Representation (`scrapers/models.py`)

- **`RawOpportunity`**: Represents unstructured raw text strings as extracted directly from the HTML source (title, abbreviation, raw deadline, raw event dates, raw location, source URL, and raw source ID).
- **`NormalizedOpportunity`**: Clean, strongly-typed domain model mapped 1:1 to `OpportunityModel` fields (parsed ISO/UTC datetimes, validated URLs, inferred enum types, normalized location, delivery mode, and validation metadata).

### 2.2. Source Interface (`scrapers/protocols.py`)

All scrapers conform to `SourceProtocol` (structural subtyping via `typing.Protocol`):
- `source_name: str`
- `source_type: str` (`"SCRAPER" | "RSS" | "API" | "MANUAL"`)
- `base_url: str`
- `crawl_delay_seconds: float`
- `fetch_pages(**kwargs) -> list[tuple[str, str]]`: Fetches raw HTML strings and page URLs without parsing.
- `parse(html: str, page_url: str) -> list[RawOpportunity]`: Parses a single page into raw opportunity records.

### 2.3. HTTP Fetching Layer (`scrapers/http_client.py`)

- **Transport**: `requests.Session` with connection pooling and custom User-Agent identifying the research project.
- **Resilience**: `urllib3.util.retry.Retry` with exponential backoff (0s, 1.5s, 3s) for transient 5xx server errors (`500`, `502`, `503`, `504`). 4xx errors are not retried.
- **Timeouts**: Explicit connect (10s) and read (20s) timeouts preventing hanging threads.
- **Ethical Crawling**: `fetch_with_delay()` enforces the source's crawl delay (5.0s for WikiCFP) between requests.

### 2.4. Source Parser (`scrapers/parsers/wikicfp_parser.py`)

- **Target**: WikiCFP search list pages (`/cfp/call?conference=<topic>&page=<n>`).
- **Mechanism**: Static HTML parsing via BeautifulSoup (`html.parser`).
- **Selector Rationale**: WikiCFP markup uses alternating table row `bgcolor` attributes (`#f6f6f6` and `#e6e6e6`) rather than CSS classes. Entries are paired across two consecutive `<tr>` elements:
  - Row 1: Event abbreviation link (containing `eventid`), full title in colspan cell.
  - Row 2: Event dates ("When"), location ("Where"), submission deadline ("Deadline").
- **Error Handling**: Missing cells, empty rows, or malformed table fragments are skipped gracefully with logging.

### 2.5. Normalization (`scrapers/normalizers/opportunity_normalizer.py`)

- **Whitespace**: Strips leading/trailing spaces and collapses internal whitespace.
- **Dates**: Multi-format datetime parser (`%b %d, %Y`, `%B %d, %Y`, `%Y-%m-%d`, etc.) converting dates to UTC midnight datetimes.
- **Type Inference**: Rule-based regex heuristics identifying `SPECIAL_ISSUE`, `WORKSHOP`, `JOURNAL`, `CALL_FOR_PAPERS`, or `CONFERENCE`.
- **Delivery Mode**: Inferred from location string (`"Virtual"`, `"Online"` → `ONLINE`, `"Hybrid"` → `HYBRID`, specific city/country → `OFFLINE`).
- **URLs**: Scheme addition (`http://`), trailing whitespace cleanup, and host validation.

### 2.6. Validation (`scrapers/validators/opportunity_validator.py`)

Rejects malformed or incomplete records before reaching the persistence layer:
- Required non-empty `title`, `source_name`, and `raw_source_id`.
- Permitted `opportunity_type` in (`CONFERENCE`, `JOURNAL`, `WORKSHOP`, `CALL_FOR_PAPERS`, `SPECIAL_ISSUE`).
- Permitted `delivery_mode` in (`ONLINE`, `OFFLINE`, `HYBRID`).
- Valid HTTP/HTTPS URLs with valid domain names.
- Sensible date boundaries (deadlines between year 2000 and now + 6 years; start date $\le$ end date).

### 2.7. Duplicate Detection (`scrapers/deduplication/detector.py`)

A session-scoped three-tier deduplication engine:
1. **Tier 1 (Primary)**: `(source_name, raw_source_id)` composite key match.
2. **Tier 2 (Secondary)**: SHA-256 fingerprint of normalized URL (ignoring casing and trailing slashes).
3. **Tier 3 (Tertiary / Soft)**: SHA-256 fingerprint of normalized `title` + `submission_deadline` date string (informational flag).

### 2.8. Persistence (`scrapers/persistence/opportunity_repo.py`)

- Manages database transactions cleanly via SQLAlchemy `Session`.
- Idempotently creates or finds the `SourceModel` by name.
- Upserts `OpportunityModel` records: inserts new records or updates mutable metadata (dates, location, summary, delivery mode) while preserving existing IDs and timestamps.
- Updates `source.last_scraped_at` timestamp upon completion.

---

## 3. Manual Pipeline Execution

The scraping pipeline is strictly manual and does not run automatically on FastAPI startup.

### Running via CLI:

```bash
# Run a dry-run test (fetches, parses, validates, and deduplicates without DB write)
python -m scrapers.pipelines.collect_opportunities --topic "artificial intelligence" --pages 1 --dry-run

# Run live ingestion against PostgreSQL
python -m scrapers.pipelines.collect_opportunities --topic "machine learning" --pages 2
```

### CLI Arguments:
- `--topic`: Search term for WikiCFP categories (default: `"artificial intelligence"`).
- `--pages`: Number of paginated pages to fetch (default: `1`).
- `--dry-run`: Flag to run pipeline without database writes.

---

## 4. Source-Specific Details & Limitations (WikiCFP)

- **Access Policy**: WikiCFP allows web crawling with a mandatory minimum crawl delay of 5.0 seconds (specified in `robots.txt` and `/cfp/data.jsp`).
- **Content Type**: Server-side rendered static HTML; no JavaScript execution or Playwright required.
- **Limitations**:
  - Search list pages do not include full CFP descriptions or external submission URLs; only event titles, dates, locations, deadlines, and WikiCFP detail links are provided.
  - Detail page scraping can be added as an optional enrichment stage with appropriate rate limiting if required.

---

## 5. How to Add a New Source

1. **Create Source Class** in `scrapers/sources/<source_name>.py`:
   - Implement `SourceProtocol` (`source_name`, `source_type`, `base_url`, `crawl_delay_seconds`, `fetch_pages()`).
2. **Create Parser Class** in `scrapers/parsers/<source_name>_parser.py`:
   - Extract records into `RawOpportunity` instances.
3. **Add HTML Fixtures & Tests** in `scrapers/tests/`:
   - Save sample HTML fixtures to `scrapers/tests/fixtures/<source_name>_list_page.html`.
   - Write comprehensive parser unit tests mocking the HTML content.
4. **Register in Pipeline** (`scrapers/pipelines/collect_opportunities.py`):
   - Instantiate the new source and pass raw records through `normalize_opportunity()` and `validate_opportunity()`.
