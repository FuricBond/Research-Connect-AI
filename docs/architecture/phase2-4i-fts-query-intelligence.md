# Phase 2.4I — Full-Text GIN Indexing & Academic Query Intelligence

**Status**: Completed & Verified  
**Date**: September 1, 2026  
**Scope**: Database FTS Optimization, PostgreSQL GIN Indexing, Deterministic Academic Query Intelligence, Acronym Expansion, FastAPI Discovery Layer Integration  

---

## 1. Executive Overview

Phase 2.4I addresses the two most urgent weaknesses identified in the Phase 2.4 comprehensive audit:

1. **Full-Text Search Scalability**: Replaces dynamic, per-query evaluation of `to_tsvector('english', ...)` with PostgreSQL `GENERATED ALWAYS AS (...) STORED` `tsvector` columns indexed with GIN (`idx_research_works_fts_gin` and `idx_opportunities_fts_gin`).
2. **Academic Query Intelligence**: Introduces a deterministic, zero-LLM query intelligence service that normalizes user queries and expands recognized academic acronyms (e.g. `GNN` $\to$ `Graph Neural Networks`, `LLM` $\to$ `Large Language Models`, `RAG` $\to$ `Retrieval-Augmented Generation`) before dispatching to retrieval channels.

The existing vector retrieval (`VectorRepository`), reciprocal rank fusion (RRF), hybrid ranker (`HybridRanker`), and deterministic explainability (`ResultExplainer`) remain 100% compatible.

---

## 2. Full-Text Search Bottleneck & TSVECTOR Architecture

### 2.1. The Pre-2.4I Bottleneck
Prior to Phase 2.4I, `LexicalRepository` dynamically constructed weighted tsvector expressions during SQL query execution:
```sql
SELECT * FROM research_works 
WHERE (
  setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(abstract, '')), 'B') ||
  setweight(to_tsvector('english', coalesce(work_type, '') || ' ' || coalesce(language, '')), 'C')
) @@ websearch_to_tsquery('english', :query)
```
**Impact**: Because PostgreSQL cannot use a standard index on a dynamically evaluated function without a functional index, this caused a sequential scan over the entire table on every lexical query. Beyond 50,000 records, lexical query latency degraded from milliseconds to seconds.

### 2.2. The Stored TSVECTOR & GIN Index Architecture
Phase 2.4I adds generated stored columns directly to the tables, managed by PostgreSQL at the database engine level:

#### `research_works.fts_vector`:
```sql
ALTER TABLE research_works
ADD COLUMN fts_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(abstract, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(work_type, '') || ' ' || coalesce(language, '')), 'C')
) STORED;

CREATE INDEX idx_research_works_fts_gin ON research_works USING gin (fts_vector);
```

#### `opportunities.fts_vector`:
```sql
ALTER TABLE opportunities
ADD COLUMN fts_vector tsvector
GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(summary, '') || ' ' || coalesce(description, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(publisher, '') || ' ' || coalesce(organizer, '') || ' ' || coalesce(series_name, '') || ' ' || coalesce(location, '')), 'C')
) STORED;

CREATE INDEX idx_opportunities_fts_gin ON opportunities USING gin (fts_vector);
```

### 2.3. Query Execution After Phase 2.4I
`LexicalRepository` now targets the indexed column directly:
```sql
SELECT research_works.*, ts_rank_cd(research_works.fts_vector, websearch_to_tsquery('english', :query)) AS lexical_score
FROM research_works
WHERE research_works.fts_vector @@ websearch_to_tsquery('english', :query)
ORDER BY lexical_score DESC
LIMIT :limit;
```
**Query Plan**: PostgreSQL utilizes a **Bitmap Index Scan** on `idx_research_works_fts_gin` / `idx_opportunities_fts_gin`, avoiding sequential scans and achieving $O(\log N)$ term lookup.

---

## 3. Migration Details

- **Alembic Revision ID**: `0007_phase2_4i_fts_gin_indexes`
- **Down Revision**: `0006_phase2_3b_semantic_embeddings`
- **File**: `backend/alembic/versions/0007_phase2_4i_fts_gin_indexes.py`
- **Verification**: `python -m alembic heads` confirmed linear head status.

---

## 4. Academic Query Intelligence Layer

### 4.1. Design Principles
The `QueryIntelligenceService` (`backend/app/search/query_intelligence.py`) was designed with strict constraints:
- **Zero LLM dependency**: Strictly deterministic regex and dictionary lookup.
- **Microsecond execution time**: $< 0.1$ ms processing overhead per query.
- **Original query preservation**: Client input is never lost or mutated for display.
- **False-positive protection**: Case sensitivity boundaries and stopword filters prevent expanding ordinary English words (e.g. `A`, `IN`, `ON`, `FOR`, `US`).

### 4.2. Acronym Registry (Seed Set)
The registry includes 35+ core computer science, AI, systems, and interdisciplinary acronyms:

| Acronym | Canonical Expansion | Domain |
|---|---|---|
| `GNN` | Graph Neural Networks | Machine Learning |
| `CNN` | Convolutional Neural Networks | Deep Learning |
| `RNN` | Recurrent Neural Networks | Deep Learning |
| `LSTM` | Long Short-Term Memory | Sequence Modeling |
| `GAN` | Generative Adversarial Networks | Generative AI |
| `VAE` | Variational Autoencoder | Generative AI |
| `NLP` | Natural Language Processing | AI / NLP |
| `LLM` / `LLMs` | Large Language Models | AI / NLP |
| `RAG` | Retrieval-Augmented Generation | Information Retrieval |
| `RL` | Reinforcement Learning | Machine Learning |
| `DRL` | Deep Reinforcement Learning | Machine Learning |
| `CV` | Computer Vision | Computer Vision |
| `ML` / `DL` | Machine Learning / Deep Learning | AI Core |
| `IR` | Information Retrieval | Information Retrieval |
| `KG` / `KGs` | Knowledge Graphs | Knowledge Engineering |
| `QA` | Question Answering | AI / NLP |
| `BERT` / `GPT` / `ViT` / `CLIP` | Foundational Model Architectures | AI Architectures |
| `IoT` / `CPS` / `SDN` / `WSN` | Internet of Things & Networks | Systems & Networking |
| `AR` / `VR` / `XR` | Augmented / Virtual / Extended Reality | Graphics & Interaction |

### 4.3. Data Flow & Retrieval Integration

```
                 [ User Search Query: "GNN for molecular prediction" ]
                                        │
                                        ▼
                      ┌───────────────────────────────────┐
                      │    QueryIntelligenceService       │
                      │  - Normalizes whitespace          │
                      │  - Detects "GNN"                  │
                      │  - Expands to "Graph Neural Nets" │
                      └─────────────────┬─────────────────┘
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
┌───────────────────────────────┐               ┌───────────────────────────────────┐
│     Lexical Retrieval         │               │     Semantic Dense Embedding      │
│ (Uses expanded query for FTS) │               │ (Uses normalized query to avoid   │
│ "GNN for molecular prediction │               │  centroid distortion in vectors)  │
│  Graph Neural Networks"       │               │ "GNN for molecular prediction"    │
└──────────────┬────────────────┘               └─────────────────┬─────────────────┘
               │                                                  │
               └────────────────────────┬─────────────────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │    Candidate Fusion (RRF)     │
                        │    Hybrid Ranking (2.4E)      │
                        │    Explainability (2.4F)      │
                        └───────────────────────────────┘
```

#### Why Separate Queries for Lexical and Vector Channels?
- **Lexical FTS**: Benefits directly from additional relevant search terms because PostgreSQL Cover Density (`ts_rank_cd`) matches words against stored document fields. Papers containing "Graph Neural Networks" but not "GNN" are now successfully retrieved!
- **Semantic Dense Embedding**: `sentence-transformers/all-MiniLM-L6-v2` encodes entire semantic phrases. Concatenating appended phrases at the end of a sentence can dilute the vector representation and shift the embedding away from the query intent. Keeping the semantic query clean and normalized preserves optimal vector similarity.

---

## 5. API Compatibility & Schema Updates

### 5.1. Backward Compatible Schema
In `backend/app/schemas/discovery.py`:
```python
class QueryIntelligenceSchema(BaseModel):
    original_query: str
    normalized_query: str
    expanded_query: str
    was_expanded: bool = False
    detected_acronyms: list[str] = Field(default_factory=list)
    detected_terms: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)

class ResearchSearchResponse(BaseModel):
    query: str
    items: list[ResearchSearchResultItem]
    total: int
    limit: int
    offset: int
    has_more: bool
    ranking_mode: str
    query_intelligence: QueryIntelligenceSchema | None = None
```

### 5.2. Query Parameter
- `GET /api/v1/discovery/research/search?q=GNN&include_query_intelligence=true`
- Defaults to `include_query_intelligence=false` for existing clients, returning `query_intelligence: null`.

---

## 6. Verification & Test Results

### 6.1. Test Coverage
- **Total Tests Passed**: **589 passed, 8 skipped, 3 warnings** across backend and scrapers.
- **Dedicated Phase 2.4I Tests**:
  - `backend/tests/test_query_intelligence.py` (normalization, acronym expansion, multi-acronym handling, stopword false-positive prevention, custom registry registration, deterministic repeatability).
  - `backend/tests/test_lexical_repository.py` (stored tsvector SQL compilation, toggle behavior, filter clauses).
  - `backend/tests/test_phase2_4i_integration.py` (hybrid search dispatch, query routing, API schema serialization, backward compatibility).

### 6.2. Frontend Build
- `npm run build` in `frontend/`: Verified with exit code 0 (`✓ built in 15.97s`).

### 6.3. Database Migration Status
- `python -m alembic heads`: Head is at `0007_phase2_4i_fts_gin_indexes`.

---

## 7. Next Steps in Phase 2.4+ Roadmap

With Phase 2.4I complete, the remaining targeted improvements prior to Phase 3 are:
1. **Phase 2.4J — Ranking Hardening & Opportunity Quality Signals**:
   - Activate `is_predatory_flag` penalties and `indexing` tier boosts (Scopus, SCI, EI) in `ResearchOpportunityMatchingService`.
   - Incorporate venue prestige/citation count signals into candidate ranking.
2. **Phase 2.4K — Frontend Discovery Experience & Production Hardening**:
   - Build React UI for Discovery Search, Similar Research explorer, and Opportunity Matcher.
   - Implement client-side API hooks and public endpoint rate limiting.
