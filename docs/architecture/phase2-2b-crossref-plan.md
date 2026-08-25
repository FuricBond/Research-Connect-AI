# Phase 2.2B Implementation Plan: Crossref Research Knowledge Integration

## 1. Crossref Role in the Architecture

Crossref is a primary digital object identifier (DOI) registration agency for scholarly publishing. In ResearchConnect AI, Crossref serves as an authoritative metadata provider and enrichment engine within the **Research Knowledge Layer**.

### Layer Separation
- **Opportunity Discovery Layer**: WikiCFP (and future conference/CFP scrapers) → `opportunities` table (actionable submission deadlines, CFP tracks).
- **Research Knowledge Layer**: OpenAlex + Crossref → `research_works`, `research_sources`, `researchers`, `institutions` (scholarly graph, publication histories, authoritative metadata).

Crossref does NOT generate actionable opportunities; it enriches existing scholarly works or introduces new works indexed by DOI.

---

## 2. Crossref → `research_works` Relationship

```
                          CROSSREF INGESTION
                                 │
                         Crossref API (REST)
                                 │
                         CrossrefClient
                                 │
                         Raw JSON Message
                                 │
                     CrossrefNormalizer (JATS XML strip, author/date/source parse)
                                 │
                     CrossrefValidator (DOI, title, structure)
                                 │
                     DOI Canonicalizer (e.g., 10.7717/peerj.4375)
                                 │
                                 ▼
                     Matching & Enrichment Engine
                                 │
        ┌────────────────────────┴────────────────────────┐
        ▼                                                 ▼
[DOI matches existing work]                     [DOI does not match]
   • Non-destructive field enrichment              • Create new research_works
   • Merge publisher/ISSN/license                  • Ingestion source = Crossref
   • Match authors (ORCID/name)                    • openalex_id = NULL
   • Link research_sources                         • Tracked under IngestionRun
```

---

## 3. DOI Identity & Canonicalization Strategy

DOIs are case-insensitive in the prefix (e.g. `10.1234`) and practically case-insensitive across major resolvers, though suffix casing should be preserved in canonical clean form.

### Canonicalization Rules (`scrapers/crossref/doi_utils.py`):
1. Strip leading/trailing whitespace.
2. Strip URL schemes and resolver domains (`https://doi.org/`, `http://dx.doi.org/`, `https://dx.doi.org/`, `http://doi.org/`).
3. Strip URI schemes (`doi:`, `DOI:`).
4. Strip URL-encoding artifacts where safe (`%2F` → `/`).
5. Ensure prefix starts with `10.\d{4,9}/`.
6. Strip trailing dots or slashes introduced by typos.
7. Return standard form: `10.xxxx/yyyy`.

---

## 4. Metadata Precedence & Enrichment Rules

When a Crossref record matches an existing `research_works` record (created via OpenAlex), updates must be non-destructive and field-specific:

| Field | Source Preference | Enrichment Rule |
|---|---|---|
| `doi` | Both / Authoritative | Canonical key. Must match. |
| `title` | OpenAlex (Default) / Crossref (Fallback) | Retain existing non-empty title. If existing title is missing or generic, use Crossref. |
| `abstract` | OpenAlex (Full) / Crossref (JATS stripped) | If existing is None, populate with Crossref JATS-cleaned abstract. Do not overwrite existing abstract with shorter snippet. |
| `publisher` / `primary_source` | Crossref / OpenAlex | Crossref is authoritative for publisher and journal container titles. Match/enrich `research_sources` via ISSN. |
| `publication_date` | Crossref (Authoritative) | Crossref provides exact print/online dates (`published-online`, `published-print`). Populate if existing is None or less specific. |
| `publication_year` | Crossref / OpenAlex | Retain valid year; fill if missing. |
| `work_type` | OpenAlex / Crossref | Map Crossref type (`journal-article`, `proceedings-article`, `book-chapter`) to standard classification. |
| `cited_by_count` | OpenAlex (Higher coverage) | Update if Crossref count is higher, or retain OpenAlex global count. |
| `is_oa` / `oa_status` | OpenAlex (Comprehensive) | Retain OpenAlex OA classification; enrich license URL in `raw_metadata`. |
| `landing_page_url` | Crossref / OpenAlex | Populate if existing is None. |
| `raw_metadata` | Merge | Append `crossref` payload under `raw_metadata["crossref"]` without overwriting OpenAlex metadata. |

---

## 5. Research Sources & Researcher Matching

### Sources (`research_sources`):
- Crossref provides `ISSN` (print/electronic) and `container-title`.
- Matching order:
  1. Exact ISSN match (`issn_l` or element in `issn` JSON list).
  2. Exact normalized container-title match.
- If matched: enrich missing fields (`issn`, `host_organization`/publisher, `homepage_url`).
- If no match: insert new `research_sources` row with `openalex_id = NULL` and Crossref metadata.

### Researchers (`researchers`):
- Crossref provides `author`: `given`, `family`, `ORCID`, `affiliation`.
- Matching order:
  1. Exact `orcid` match (e.g., `0000-0003-1613-5981`).
- Never fuzzy-merge solely on common names to prevent identity corruption.
- If no ORCID match: create new `researchers` record with `openalex_id = NULL`.

---

## 6. Provenance Strategy

- Add `"Crossref"` as a registered entry in `sources` (`source_type = "API"`, `base_url = "https://api.crossref.org"`).
- `research_works.ingestion_source_id` retains the original creator (e.g. OpenAlex or Crossref).
- `raw_metadata["provenance"]` records all contributing sources:
  ```json
  {
    "sources": ["OpenAlex", "Crossref"],
    "crossref_last_enriched_at": "2026-08-25T17:00:00Z",
    "crossref": { ... }
  }
  ```

---

## 7. Retry, Rate Limiting & Polite Pool

- **Polite Pool**: Crossref requires `User-Agent: ResearchConnect-AI/1.0 (mailto:user@example.com)` or `mailto` parameter in requests.
- **Rate Limit Handling**: Respect HTTP 429 and `X-Rate-Limit-Interval` / `X-Rate-Limit-Limit`. Implement exponential backoff (initial 5s, multiplier 2.0x, max 60s, 4 retries).
- **Transient Failures**: 500, 502, 503, 504 handled via `HttpClient` retry logic.
- **Polite Inter-request Delay**: 0.5s–1.0s between paginated queries.

---

## 8. Persistence & Ingestion Runs

- Reuse `IngestionRunModel` (`status`, `records_parsed`, `records_valid`, `records_inserted`, `records_updated` as enriched, `records_unchanged`).
- Lifecycle actions: `NEW`, `UPDATED` (enriched), `UNCHANGED`, `INVALID`, `POTENTIAL_MATCH`.
- Update `last_seen_at` on every touched record.

---

## 9. Database Migration (`0004_phase2_2b_crossref_integration.py`)

1. Make `openalex_id` nullable (`nullable=True`) on `research_works`, `researchers`, `research_sources`, and `institutions` so Crossref-native records can be inserted without dummy IDs.
2. Add index / unique constraint on `research_works.doi` to guarantee fast, collision-safe DOI lookup.
3. Full `upgrade()` and `downgrade()` support.

---

## 10. Testing Strategy

All unit and integration tests under `scrapers/tests/`:
- `test_crossref_doi.py`: Comprehensive DOI canonicalization.
- `test_crossref_client.py`: Mocked HTTP client (lookup, query, pagination, 429 backoff, 5xx retry).
- `test_crossref_normalizer.py`: Normalization of titles, JATS XML abstracts, authors, dates, ISSNs.
- `test_crossref_validator.py`: Validation rules (valid DOIs, required fields, non-negative numbers).
- `test_crossref_matching.py`: In-memory SQLite persistence tests for matching existing OpenAlex works, non-destructive enrichment, new work creation, author/source linking, and idempotency.
- `test_crossref_pipeline.py`: Dry-run CLI execution tests with mocked data.
