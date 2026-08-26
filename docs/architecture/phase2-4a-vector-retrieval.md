# Phase 2.4A — Vector Retrieval Foundation

## Summary

Phase 2.4A implements the core vector retrieval layer for ResearchConnect AI in [`backend/app/repositories/vector_repository.py`](file:///D:/Project/researchconnect-ai/backend/app/repositories/vector_repository.py).

It provides a database-level, nearest-neighbor semantic search capability over:
1. `research_works` (`ResearchWorkModel`)
2. `opportunities` (`OpportunityModel`)

This layer consumes the 384-dimensional L2-normalized embeddings generated in Phase 2.3B using `all-MiniLM-L6-v2`.

---

## Architectural Boundary

```
Phase 2.3B                         Phase 2.4A                           Future Phase 2.4B+
Embedding Generation               Vector Retrieval Foundation          Recommendation & Ranking
┌────────────────────┐            ┌──────────────────────┐             ┌──────────────────────┐
│  all-MiniLM-L6-v2  │            │   VectorRepository   │             │   Candidate Scoring  │
│  384-dim Vectors   │ ─────────► │   pgvector (<=>)     │ ──────────► │   Topic Weights      │
│  L2-Normalized     │            │   HNSW Index Search  │             │   Freshness / Trust  │
│  Content Hash      │            │   Metadata Filters   │             │   LLM Reranking      │
└────────────────────┘            └──────────────────────┘             └──────────────────────┘
                                             │
                                    Candidate Results
                                   (VectorSearchResult)
```

> [!IMPORTANT]
> **Phase 2.4A is strictly a candidate retrieval engine.**
> It does **NOT** rank recommendations, perform hybrid search, apply personalization, calculate trust/freshness weights, or execute LLM reranking. Its sole responsibility is retrieving the top-$K$ nearest semantic neighbors from PostgreSQL + pgvector.

---

## Key Components

### 1. `VectorRepository`
Located at [`backend/app/repositories/vector_repository.py`](file:///D:/Project/researchconnect-ai/backend/app/repositories/vector_repository.py).

- **Candidate Limits**: Default 20, maximum capped at 100 to prevent accidental massive database operations.
- **Dimensionality**: Configured via `settings.embedding_dim` (default 384).
- **Public API**:
  - `search_research_works(session, query_embedding, *, limit, exclude_work_id, publication_year, min_year, max_year, work_type, language, primary_source_id, is_oa, min_citations)`
  - `find_similar_research_works(session, work_id, *, limit, ...)`
  - `search_opportunities(session, query_embedding, *, limit, exclude_opportunity_id, opportunity_type, status, delivery_mode, source_id, upcoming_only, submission_deadline_after)`
  - `find_similar_opportunities(session, opportunity_id, *, limit, ...)`

### 2. Query Vector Validation
Before any query reaches PostgreSQL, `validate_query_vector()` checks:
- **Presence**: Rejects `None` or empty lists.
- **Type**: Rejects strings, dicts, byte arrays, and non-numeric types (including `bool`).
- **Dimensions**: Enforces exact match to `384` (rejects 383, 385, etc.).
- **Value Integrity**: Rejects `NaN`, `+Inf`, and `-Inf`.

On violation, a controlled `VectorValidationError` is raised.

### 3. Cosine Similarity Conversion
pgvector's `<=>` operator computes the cosine distance $d \in [0, 2]$:
$$d = 1 - \cos(\theta)$$

Because embeddings are L2-normalized in Phase 2.3B, cosine similarity $s$ is computed directly as:
$$\text{similarity} = 1.0 - \text{distance}$$

The output is presented as `VectorSearchResult`:
- `entity_id: uuid.UUID`
- `similarity: float`
- `distance: float`
- `entity_type: str`
- `entity: Any | None` (the loaded ORM model)

### 4. NULL Embeddings & Source Exclusion
- **NULL Embeddings**: Filtered out in SQL via `WHERE embedding IS NOT NULL`. The retrieval layer never automatically triggers embedding generation (which remains the job of `ml/embeddings/generate_embeddings.py`).
- **Source Entity Exclusion**: Filtered out in SQL via `WHERE id != exclude_id` so that an entity is not returned as its own nearest neighbor.

### 5. HNSW Index Integration
Created in migration `0006_phase2_3b_semantic_embeddings`:
- `CREATE INDEX idx_research_works_embedding_hnsw ON research_works USING hnsw (embedding vector_cosine_ops)`
- `CREATE INDEX idx_opportunities_embedding_hnsw ON opportunities USING hnsw (embedding vector_cosine_ops)`

These enable sub-linear approximate nearest neighbor (ANN) retrieval using cosine distance.

---

## Database Schema & Migration Status

> [!NOTE]
> **No database migrations were required for Phase 2.4A.**
> Migration `0006_phase2_3b_semantic_embeddings` already established:
> - `research_works.embedding` (`vector(384)`)
> - `opportunities.embedding` (`vector(384)`)
> - HNSW indexes on both tables with `vector_cosine_ops`.

---

## Testing Strategy

### Unit Tests
Covers all non-database logic and SQL expression structure:
- Vector validation (384-dim, empty, None, NaN, Inf, bad types)
- Limit sanitization (default 20, max 100, zero/negative rejection)
- Distance-to-similarity conversion
- `VectorSearchResult` immutability
- SQL compilation check (verifies `IS NOT NULL`, `<=>`, `ORDER BY`, `LIMIT`, and all WHERE filter clauses)
- Session mock execution (research works, opportunities, similar-by-ID, source exclusion, empty results)

### PostgreSQL Integration Tests
- Real pgvector queries against live PostgreSQL
- Verifies exact `<=>` operator execution and HNSW index traversal
- Gracefully skipped when PostgreSQL is not running in the current environment

---

## Verification Commands

```bash
# Run vector repository tests
python -m pytest backend/tests/test_vector_repository.py -v

# Run full backend + scrapers regression test suite
python -m pytest backend/tests/ scrapers/tests/ -q
```
