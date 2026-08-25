# Crossref Integration — Research Knowledge Layer (Phase 2.2B)

## 1. Overview & Rationale

Crossref is an official Digital Object Identifier (DOI) Registration Agency of the International DOI Foundation. It indexes metadata directly provided by academic publishers upon publication.

In **ResearchConnect AI**, Crossref operates as a complementary scholarly metadata provider in the **Research Knowledge Layer**. While OpenAlex provides broad open-catalog coverage with topics, open access classifications, and citation metrics, Crossref provides authoritative publisher metadata, clean DOI identifiers, container titles, exact publication dates (online vs print), volume/issue/page pagination, and license URLs.

---

## 2. Architecture & Layer Separation

ResearchConnect AI strictly separates **Opportunity Discovery** from **Research Knowledge**:

```
                         RESEARCH KNOWLEDGE
                                │
                  ┌─────────────┴─────────────┐
                  │                           │
               OpenAlex                    Crossref
                  │                           │
                  └─────────────┬─────────────┘
                                │
                         DOI / identifiers
                                │
                                ▼
                         research_works
                          /     |      \
                         /      |       \
                 researchers  sources  institutions

                         OPPORTUNITIES (Separate)
                              │
                           WikiCFP
                              │
                              ▼
                       opportunities
```

- **`opportunities` Table**: Stores actionable CFP dates, submission deadlines, and conference/journal tracks.
- **`research_works` Table**: Stores canonical scholarly works, connected to publication venues (`research_sources`), authors (`researchers`), and institutions (`institutions`).

Crossref records are never mixed into `opportunities`.

---

## 3. DOI Identity & Canonicalization

DOI is the primary linking key across all scholarly knowledge sources.

### Canonicalization Algorithm (`scrapers/crossref/doi_utils.py`):
1. Strips URL schemes and resolver prefixes (`https://doi.org/`, `http://dx.doi.org/`, `doi:`).
2. URL-decodes safe characters (`%2F` -> `/`).
3. Normalizes prefix (`10.xxxx/`) to lowercase.
4. Preserves suffix casing.
5. Cleans accidental punctuation (trailing dots, commas, slashes).

```
https://doi.org/10.7717/peerj.4375  ──┐
http://dx.doi.org/10.7717/peerj.4375 ──┼──►  10.7717/peerj.4375
doi:10.7717/peerj.4375              ──┘
```

---

## 4. Metadata Precedence & Enrichment Rules

When Crossref ingests a work whose canonical DOI matches an existing `research_works` record, it performs **non-destructive field enrichment**:

| Field | Source Authority | Enrichment Action |
|---|---|---|
| `doi` | Canonical Key | Primary match key. |
| `title` | OpenAlex / Crossref | Retains existing title; fills if missing. |
| `abstract` | OpenAlex / Crossref | JATS-cleaned Crossref abstract fills missing abstract; never replaces existing full abstract. |
| `volume`, `issue`, `page`, `article_number` | Crossref (Authoritative) | Enriched from Crossref. |
| `license_url`, `is_oa` | Crossref / OpenAlex | Enriched if declared in Crossref license list. |
| `publication_date`, `publication_year` | Crossref (Authoritative) | Uses exact `published-online` or `published-print`. |
| `publisher` / `host_organization` | Crossref | Enriched on related `research_sources`. |
| `raw_metadata` | Combined | Merges `crossref` payload into `raw_metadata` under `"crossref"` key. |

---

## 5. Entity Matching Strategies

### Research Sources (`research_sources`)
1. **ISSN Match**: Matches `issn_l` or any ISSN in the `issn` JSON array.
2. **Container Title Match**: Matches exact normalized journal/container title.
3. If no match is found, creates a new `research_sources` entry with `openalex_id = NULL`.

### Researchers (`researchers`)
1. **ORCID Match**: Strictly matches on bare 16-character ORCID (e.g. `0000-0003-1613-5981`).
2. Never automatically merges authors based solely on common names to prevent identity pollution.
3. If no ORCID match is found, creates a new `researchers` record with `openalex_id = NULL`.

---

## 6. Provenance Tracking

- **Origin Source**: The `"Crossref"` entry in the `sources` table (`source_type = "API"`, `base_url = "https://api.crossref.org"`).
- **Work Provenance**: New Crossref works link `ingestion_source_id -> sources.id`.
- **Enrichment Audit**: `raw_metadata` records the Crossref payload and `last_enriched_at` timestamp.

---

## 7. Rate Limiting, Retries & Polite Pool

- **Polite Pool**: Crossref requests include a polite `User-Agent` and `mailto:` parameter configured via `CROSSREF_EMAIL`.
- **HTTP 429 Backoff**: Exponential backoff (5s initial, 2.0x multiplier, 60s max, 4 retries).
- **Transient Failures (5xx)**: Handled automatically via `HttpClient` connection pooling and urllib3 retry adapters.
- **Polite Delay**: 0.5s pause between paginated API pages.

---

## 8. CLI Usage

The Crossref pipeline supports both single-DOI lookups and paginated search queries:

```bash
# 1. Enrich a single DOI in dry-run mode
python -m scrapers.pipelines.collect_crossref --doi "10.7717/peerj.4375" --dry-run

# 2. Ingest works by search query in dry-run mode
python -m scrapers.pipelines.collect_crossref --query "machine learning" --pages 2 --per-page 25 --dry-run

# 3. Live ingestion to database
python -m scrapers.pipelines.collect_crossref --query "deep learning" --pages 1 --per-page 10
```

---

## 9. Testing & Validation

All tests run locally with mocked HTTP and in-memory SQLite schemas:
- `scrapers/tests/test_crossref_doi.py`: DOI canonicalization and normalization edge cases.
- `scrapers/tests/test_crossref_normalizer.py`: JATS XML abstract cleaning, date parsing, author/source normalization.
- `scrapers/tests/test_crossref_validator.py`: Schema and value validation.
- `scrapers/tests/test_crossref_client.py`: Mocked HTTP client (lookups, 429 backoff, 404, 5xx retries).
- `scrapers/tests/test_crossref_matching.py`: In-memory SQLite DOI matching, non-destructive enrichment, author ORCID matching, source ISSN matching, idempotency.
- `scrapers/tests/test_crossref_pipeline.py`: End-to-end dry-run CLI execution.
