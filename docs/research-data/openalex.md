# OpenAlex Integration — Research Knowledge Layer (Phase 2.2A)

## Overview

OpenAlex is an open, comprehensive index of the global research system. It
provides structured metadata on scholarly works, authors, publication venues,
and institutions via a free, rate-limit-friendly REST API.

**Why OpenAlex?**

ResearchConnect AI uses OpenAlex to build a *research knowledge layer* — a
structured graph of scholarly context that enriches the platform's
recommendations. This is fundamentally different from the *opportunities layer*
(conferences, journals, call-for-papers), which is served by WikiCFP and
similar sources.

The two layers are intentionally separate and are never merged.

---

## Entities

OpenAlex defines four core entity types, all of which are stored in separate
tables:

| Entity | Table | OpenAlex ID Prefix |
|---|---|---|
| Research Work (article, preprint, …) | `research_works` | `W` |
| Researcher / Author | `researchers` | `A` |
| Publication Venue | `research_sources` | `S` |
| Institution | `institutions` | `I` |

Additionally, two junction tables link works to their authors and institutions:
- `research_work_authors` (work ↔ researcher, with `author_position` and `is_corresponding`)
- `research_work_institutions` (work ↔ institution, via authorship)

---

## Data Model

### `research_works`

Stores individual scholarly works (articles, preprints, datasets, book chapters, …).

Key columns:
- `openalex_id` — compact OpenAlex ID, e.g. `W2741809807` (unique, indexed)
- `doi` — bare DOI without resolver, e.g. `10.7717/peerj.4375`
- `title`, `abstract` — core content
- `publication_year`, `publication_date`
- `work_type` — `article`, `preprint`, `book-chapter`, `dataset`, etc.
- `cited_by_count`, `is_oa`, `oa_status` — metrics and open-access information
- `primary_source_id` — FK → `research_sources.id` (publication venue)
- `ingestion_source_id` — FK → `sources.id` (points to the `"OpenAlex"` row in the provenance table)
- `raw_metadata` (JSONB) — topics, keywords, concepts, citation counts by year

Abstracts are reconstructed from OpenAlex's *inverted index* format (a mapping of
word → positions) using `scrapers/openalex/abstract_utils.py`.

OpenAlex topics (hierarchical: domain → field → subfield → topic) and keywords
are stored inside `raw_metadata` JSONB rather than in the existing `topics` table.
A future migration can reconcile them once the mapping strategy is decided.

### `researchers`

Individual authors. Keyed on `openalex_id` (compact `A\d+` form).

- ORCID is stored in plain form (no URL prefix), e.g. `0000-0003-1613-5981`
- `works_count`, `cited_by_count` — refreshed on each ingestion run

### `research_sources`

Publication venues (journals, repositories, conference series, …).

- `issn_l` — linking ISSN
- `is_oa`, `is_in_doaj` — open-access classification
- `source_type` — `journal`, `repository`, `conference`, etc.

### `institutions`

Universities, research labs, companies, government bodies.

- `ror` — ROR (Research Organization Registry) compact ID
- `country_code`, `institution_type`

---

## Provenance

Every `research_works` record has:
- `openalex_id` — the source's own unique, stable identifier
- `ingestion_source_id` — FK to the `sources` table row where `name = 'OpenAlex'`
- `last_seen_at` — timestamp of the last ingestion run that encountered this record

This provides a complete chain of custody: every record is traceable back to
OpenAlex with a timestamp.

---

## Deduplication

All entities use `openalex_id` as the identity key for deduplication. This is
the most reliable approach because:

1. OpenAlex assigns stable, globally unique IDs
2. Titles are not reliable (preprints and published versions have slightly different titles)
3. DOIs are not always present (especially for preprints)

Deduplication is three-tier by entity:

| Entity | Identity Key |
|---|---|
| Work | `openalex_id` (`W\d+`) |
| Researcher | `openalex_id` (`A\d+`) |
| Source | `openalex_id` (`S\d+`) |
| Institution | `openalex_id` (`I\d+`) |

---

## Freshness Tracking

Each entity has a `last_seen_at` timestamp that is updated on every ingestion
run that encounters it, even if no fields have changed. This allows the system
to identify stale records that have not been seen in recent runs.

Change detection compares a small set of tracked fields per entity type. If any
tracked field changes (e.g., `cited_by_count` for a work), the record is marked
`UPDATED` and the fields are overwritten.

---

## API Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `OPENALEX_API_BASE_URL` | `https://api.openalex.org` | API base URL |
| `OPENALEX_EMAIL` | *(empty)* | Contact email for polite pool access |

**Polite pool**: OpenAlex provides a faster, more stable API tier for users who
identify themselves with a valid email address via the `?mailto=` query parameter.
Setting `OPENALEX_EMAIL` enables this automatically.

---

## Ingestion Flow

```
OpenAlexSource.fetch_works_pages()
    │
    ▼ (raw dict pages)
normalizer.normalize_work()        ← also normalizes embedded
    │                                  researchers, sources, institutions
    ▼ (NormalizedWork)
validator.validate_work()
    │
    ▼ (valid only)
OpenAlexRepository.upsert_work()
    ├── upsert_research_source()    ← primary venue
    ├── upsert_researcher()         ← per authorship
    ├── upsert_institution()        ← per institution in authorship
    └── junction tables
    │
    ▼
IngestionRunModel.status = COMPLETED
SourceModel.last_scraped_at = now
```

---

## CLI Usage

```bash
# Dry run (no DB required)
python -m scrapers.pipelines.collect_openalex \
    --search "machine learning" \
    --pages 1 \
    --per-page 25 \
    --dry-run

# Live ingestion
python -m scrapers.pipelines.collect_openalex \
    --search "open access" \
    --pages 3 \
    --per-page 50 \
    --year 2024 \
    --type article

# All options
python -m scrapers.pipelines.collect_openalex --help
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--search` | `"artificial intelligence"` | Full-text search query |
| `--pages` | `1` | Number of pages to fetch |
| `--per-page` | `25` | Works per page (max 200) |
| `--dry-run` | off | Parse/validate only, no DB write |
| `--year` | all years | Filter by publication year |
| `--type` | all types | Filter by work type |

---

## Pagination

The pipeline uses **cursor-based pagination** (`?cursor=*` then advancing via
`meta.next_cursor`), which is OpenAlex's recommended approach. This is more
reliable than offset-based pagination for large result sets.

---

## Rate Limiting

The `OpenAlexClient` handles HTTP 429 (Too Many Requests) with exponential
back-off:

- Initial wait: **10 seconds**
- Multiplier: **2×** per retry
- Max wait: **120 seconds**
- Max retries: **4**

Transport-level errors (500/502/503) are retried by the underlying `HttpClient`
via `urllib3` retry logic.

A 1-second polite delay is applied between paginated requests.

---

## Testing

All tests are located in `scrapers/tests/`:

| File | Coverage |
|---|---|
| `test_openalex_abstract.py` | Abstract inverted-index reconstruction |
| `test_openalex_normalizer.py` | All four normalisers + ID helpers |
| `test_openalex_validator.py` | All four validators |
| `test_openalex_client.py` | API client: pagination, 429, lookups |
| `test_openalex_persistence.py` | SQLite-backed upsert lifecycle |
| `test_openalex_pipeline.py` | End-to-end dry-run pipeline |

Run all tests (including existing 142+):

```bash
cd researchconnect-ai
pytest scrapers/tests/ -v
```

Tests never make live API calls. All HTTP is mocked. Persistence tests use
SQLite in-memory (no PostgreSQL required).

---

## Limitations (Phase 2.2A)

- **Topics not reconciled**: OpenAlex topics are stored in `raw_metadata` JSONB.
  They are not linked to the existing `topics` table taxonomy yet.
- **No citation graph**: `referenced_works` and `related_works` are not stored
  (they are excluded from `raw_metadata` to keep payload size bounded).
- **No full-text indexing**: Abstracts are stored as plain text, not vectorised
  yet. Phase 2.2B or later will add pgvector embeddings.
- **Search-based ingestion only**: Phase 2.2A ingests works via keyword search.
  Seeded ingestion (e.g., by faculty profile) is planned for Phase 2.2B.

---

## Future: Crossref Relationship

OpenAlex and Crossref have significant overlap (both index DOIs). Phase 2.3 will
add Crossref as a complementary source. At that point, the `doi` column in
`research_works` will serve as the join key between the two sources' data.
