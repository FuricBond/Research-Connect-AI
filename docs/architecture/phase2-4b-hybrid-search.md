# Phase 2.4B — Hybrid Search & Candidate Fusion

## Summary

Phase 2.4B builds a production-oriented hybrid retrieval layer that combines:
1. **PostgreSQL Lexical / Full-Text Search (FTS)** with section weighting (`ts_rank_cd`)
2. **pgvector Semantic Vector Retrieval** (`VectorRepository` from Phase 2.4A)
3. **Reciprocal Rank Fusion (RRF)** for rank-based candidate merging

The hybrid search orchestrator ([`backend/app/services/hybrid_search_service.py`](file:///D:/Project/researchconnect-ai/backend/app/services/hybrid_search_service.py)) retrieves candidate sets across both lexical and semantic channels, applies identical metadata filters and source entity exclusions, and fuses them into a unified list of [`HybridSearchResult`](file:///D:/Project/researchconnect-ai/backend/app/services/hybrid_search_service.py).

---

## Architectural Boundary

```
User Search Query
       │
       ├─────────────────────────────────────────┐
       │                                         │
       ▼                                         ▼
Lexical Channel                           Vector Channel
PostgreSQL FTS (`websearch_to_tsquery`)   Query Embedding (`EmbeddingService`)
Weighted `to_tsvector` (A, B, C)          pgvector `<=>` Cosine Distance + HNSW
       │                                         │
       ▼                                         ▼
Lexical Candidates (Top N)                Vector Candidates (Top N)
       │                                         │
       └────────────────────┬────────────────────┘
                            │
                            ▼
               [ Reciprocal Rank Fusion (RRF) ]
               RRF_score(d) = Σ 1 / (k + rank_i(d))
                            │
                            ▼
              Deduplicated Candidates
               (HybridSearchResult)
                            │
                            ▼
              Future Recommendation Phases
              (Ranking / Personalization / LLM)
```

> [!IMPORTANT]
> **Phase 2.4B is strictly a Candidate Retrieval & Fusion layer.**
> It does **NOT** rank recommendations, perform user personalization, apply research profile matching, compute freshness/trust scores, or run LLM rerankers. Its sole responsibility is retrieving and fusing candidate items from lexical and vector channels.

---

## Terminology & Score Distinctions

It is critical to distinguish between the various scores in the platform:

| Metric | Origin | Range | Meaning |
|---|---|---|---|
| **Lexical Score** (`lexical_score`) | PostgreSQL `ts_rank_cd` | $[0, \infty)$ | Keyword match density and term proximity. |
| **Vector Similarity** (`vector_similarity`) | pgvector $1.0 - \text{distance}$ | $[-1, 1]$, typ. $[0, 1]$ | Semantic concept similarity between query embedding and record embedding. |
| **RRF Score** (`hybrid_score`) | Reciprocal Rank Fusion | $(0, 1)$ | Combined rank position across retrieval channels. |
| **Recommendation Score** *(Future)* | Recommendation Pipeline | $[0, 1]$ | Personalized score combining topics, user profile, trust, deadlines, etc. |

---

## Searchable Content & FTS Weighting

Lexical retrieval ([`backend/app/repositories/lexical_repository.py`](file:///D:/Project/researchconnect-ai/backend/app/repositories/lexical_repository.py)) constructs weighted document vectors directly in SQL without altering database tables:

### 1. Research Works (`research_works`)
- **Weight A (1.0)**: `title` (primary relevance anchor)
- **Weight B (0.4)**: `abstract` (main content text)
- **Weight C (0.2)**: `work_type`, `language` (metadata categorization)

### 2. Opportunities (`opportunities`)
- **Weight A (1.0)**: `title` (conference/journal name)
- **Weight B (0.4)**: `summary`, `description` (call-for-papers scope)
- **Weight C (0.2)**: `publisher`, `organizer`, `series_name`, `location` (organizer & venue metadata)

---

## Reciprocal Rank Fusion (RRF)

Located at [`backend/app/search/rrf.py`](file:///D:/Project/researchconnect-ai/backend/app/search/rrf.py).

### Formula
For document $d$ across retrieval systems $M$:
$$RRF\_score(d) = \sum_{i \in M} \frac{1}{k + rank_i(d)}$$

Where:
- $rank_i(d)$ is the 1-based rank of candidate $d$ in system $i$.
- $k$ is the smoothing constant (default $k=60$, configurable via `settings.hybrid_search_rrf_k`).

### Why RRF?
1. **Scale-Invariant**: Eliminates the need to normalize or calibrate raw lexical scores (`ts_rank_cd`) against cosine similarities.
2. **Robust**: Candidates appearing high in multiple retrieval lists naturally receive high fused scores.
3. **Inclusive**: Candidates discovered in only one channel still receive a proportional score and are preserved.

### Entity Type Segregation
Candidate identity in fusion is keyed on the pair `(entity_type, entity_id)` to prevent accidental cross-entity ID collisions.

---

## Candidate Oversampling Strategy

When a user requests $L$ final results (e.g. $L = 20$):
$$\text{candidate\_limit} = \min(\text{max\_limit}, \max(\text{min\_candidates}, \lfloor L \times \text{multiplier} \rfloor))$$

- **Default multiplier**: $2.5\times$ (configured in `settings.hybrid_search_candidate_multiplier`).
- **Example**: Target $L = 20 \implies$ retrieve 50 candidates from Lexical and 50 candidates from Vector.
- **Rationale**: Oversampling ensures that items ranked 25th in Lexical but 5th in Vector are retrieved from both channels and properly boosted during RRF fusion.

---

## Metadata Filtering & Source Exclusion

The exact same database-level filters are applied to both retrieval paths in SQL before candidate limit truncation:

### Research Works Filters
- `publication_year`, `min_year`, `max_year`
- `work_type`, `language`
- `primary_source_id`, `is_oa`, `min_citations`
- `exclude_work_id` (source exclusion)

### Opportunities Filters
- `opportunity_type`, `status`
- `delivery_mode`, `source_id`
- `upcoming_only`, `submission_deadline_after`
- `exclude_opportunity_id` (source exclusion)

---

## Unified Result Schema (`HybridSearchResult`)

```python
@dataclass(frozen=True)
class HybridSearchResult:
    entity_id: uuid.UUID
    entity_type: str
    hybrid_score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None
    lexical_score: float | None = None
    vector_similarity: float | None = None
    retrieval_sources: list[str] = field(default_factory=list)
    entity: Any | None = None
```

---

## Database Migration Status

> [!NOTE]
> **No database schema migration was required for Phase 2.4B.**
> PostgreSQL expression-based full-text search (`to_tsvector` + `websearch_to_tsquery` + `ts_rank_cd`) executes natively over the existing database columns without modifying schema definitions.
> The Alembic migration head remains at `0006_phase2_3b_semantic_embeddings`.

---

## Testing & Verification

### Unit Tests
- `backend/tests/test_rrf.py`: 8 test suites covering fusion math, overlapping candidates, disjoint candidates, $k$ tuning, limit capping, entity type segregation, and tie-breaking.
- `backend/tests/test_lexical_repository.py`: 11 test suites covering query sanitization, document vector weights, SQL AST generation, metadata filtering, and rank mapping.
- `backend/tests/test_hybrid_search.py`: 10 test suites covering candidate oversampling, dual-path fusion, filter propagation, and error fallback.

### Integration Tests
- PostgreSQL integration tests are implemented across all repositories and search services, marked with `@pytest.mark.postgres_integration`, and dynamically skipped when live PostgreSQL is offline.
