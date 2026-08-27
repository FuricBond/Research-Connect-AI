# Phase 2.4C — Similar Research Retrieval

## 1. Purpose

Phase 2.4C implements a dedicated, production-grade **Similar Research Retrieval** capability that answers:

> *"Given one research work, which other research works are most similar to it?"*

The system retrieves nearest candidate works by combining:
1. **Semantic Similarity**: Vector nearest-neighbor search via pgvector over 384-dimensional sentence embeddings.
2. **Lexical Similarity**: PostgreSQL full-text search (`ts_rank_cd`) using the source work's title as query context.
3. **Topic Overlap & Proximity**: Multi-evidence canonical topic overlap and taxonomy DAG hierarchical proximity.

> [!IMPORTANT]
> **Architectural Boundary**:
> Phase 2.4C is strictly a **Candidate Retrieval & Similarity** layer. It does **NOT** perform researcher preference modeling, personalized recommendation scoring, deadline scoring, natural-language explanation generation, or FastAPI exposure (which are scheduled for Phases 2.4D through 2.4G).

---

## 2. Architecture

```
                       Source ResearchWork (work_id)
                                      │
         ┌────────────────────────────┴────────────────────────────┐
         ▼                                                         ▼
 [ Semantic Vector Channel ]                               [ Lexical Channel ]
  VectorRepository.search_research_works                    LexicalRepository.search_research_works
  Query: source_work.embedding                              Query: source_work.title
  Exclude: source_work.id                                   Exclude: source_work.id
  Metadata Filters                                          Metadata Filters
         │                                                         │
         └────────────────────────────┬────────────────────────────┘
                                      │
                                      ▼
                      Candidate Works Deduplication
                                      │
                                      ▼
                        [ Topic Overlap Engine ]
                   Canonical Topic ID Overlap
                   Confidence-weighted Intersection
                   Taxonomy DAG Hierarchical Ancestors
                                      │
                                      ▼
                       [ Composite Similarity Scoring ]
           combined_similarity = w_sem * S_sem + w_lex * S_lex + w_top * S_top
           (Default weights: 0.60 semantic, 0.20 lexical, 0.20 topic)
                                      │
                                      ▼
                        [ Deterministic Ranking ]
           Order by: combined_sim DESC -> sem_sim DESC -> lex_sim DESC -> topic_sim DESC -> UUID ASC
                                      │
                                      ▼
                         list[SimilarResearchResult]
```

---

## 3. Data Flow

1. Caller invokes `similar_research_service.get_similar_research(session, work_id, limit=..., **filters)`.
2. Service fetches source `ResearchWorkModel` and validates its 384-dimensional embedding vector.
3. Service calculates oversampled candidate retrieval limit ($L_{\text{cand}} = \min(L_{\text{max}}, \max(20, \lfloor L \times 2.5 \rfloor))$).
4. Service queries `VectorRepository` with query embedding and `exclude_work_id=work_id`.
5. Service queries `LexicalRepository` with query string from source title and `exclude_work_id=work_id`.
6. Candidate sets are merged and deduplicated by candidate work UUID.
7. Topic associations for source and candidates are resolved (from preloaded models or batch SQL query).
8. Topic overlap and DAG hierarchical proximity scores are calculated.
9. Multi-signal similarities are normalized into $[0.0, 1.0]$ and combined into `combined_similarity`.
10. Candidates are deterministically sorted and 1-based ranks are assigned.
11. Results are truncated to requested limit and returned as `list[SimilarResearchResult]`.

---

## 4. Source Work Handling

- **Existence Check**: If `work_id` is not present in the database, `ResearchWorkNotFoundError` is raised.
- **Embedding Check**: If the work exists but `embedding` is `None`, `MissingEmbeddingError` is raised.
- **Vector Validation**: Vector dimensionality, finiteness, and non-null values are validated using `validate_query_vector`.

---

## 5. Vector Retrieval

Reuses `backend/app/repositories/vector_repository.py`:
- Cosine distance operator (`<=>`) backed by the HNSW index on `research_works.embedding`.
- Distance-to-similarity conversion: $\text{similarity} = \text{round}(1.0 - \text{distance}, 6)$.
- Bounded in $[0.0, 1.0]$. Candidates discovered only via lexical channel default to $0.0$ semantic similarity if no vector is present.

---

## 6. Lexical Retrieval

Reuses `backend/app/repositories/lexical_repository.py`:
- Cover Density ranking (`ts_rank_cd`) over weighted tsvectors (Weight A: title, Weight B: abstract, Weight C: work_type/language).
- Lexical score normalization:
  $$S_{\text{lex}} = \frac{\text{raw\_score}}{\text{raw\_score} + 1.0}$$
  Monotonically maps $[0, \infty) \to [0.0, 1.0)$. Candidates not discovered lexically receive $0.0$.

---

## 7. Topic Similarity & Taxonomy Proximity

Reuses the canonical taxonomy DAG and `ResearchWorkTopicModel` associations:
1. **Exact Shared Topics**: For each topic ID $t \in T_S \cap T_C$, base overlap is $\min(\text{conf}(S, t), \text{conf}(C, t))$.
2. **Primary Topic Bonus**: If topic $t$ is designated `is_primary` for both source and candidate, its match weight is boosted by $+20\%$.
3. **Hierarchical Proximity**: For non-identical topics, the taxonomy DAG is traversed via `TaxonomyService.get_ancestors(slug)`. If source and candidate topics share common parent/ancestor concepts, partial credit ($+0.15 \times \min(\text{conf}_S, \text{conf}_C)$) is awarded.
4. **Normalization**: Total overlap weight is normalized by the union topic weight sum and clamped to $[0.0, 1.0]$.

---

## 8. Combined Similarity Scoring

$$S_{\text{comb}} = w_{\text{sem}} \cdot S_{\text{sem}} + w_{\text{lex}} \cdot S_{\text{lex}} + w_{\text{top}} \cdot S_{\text{top}}$$

### Configuration Defaults

| Parameter | Configuration Setting | Default | Description |
|---|---|---|---|
| Semantic Weight ($w_{\text{sem}}$) | `settings.similar_research_semantic_weight` | `0.60` | Primary semantic concept weight |
| Lexical Weight ($w_{\text{lex}}$) | `settings.similar_research_lexical_weight` | `0.20` | Full-text title/keyword match weight |
| Topic Weight ($w_{\text{top}}$) | `settings.similar_research_topic_weight` | `0.20` | Canonical topic overlap weight |
| Default Limit | `settings.similar_research_default_limit` | `20` | Default results count |
| Max Limit | `settings.similar_research_max_limit` | `100` | Hard retrieval limit ceiling |
| Multiplier | `settings.similar_research_candidate_multiplier` | `2.5` | Candidate oversampling multiplier |

All component scores ($S_{\text{sem}}, S_{\text{lex}}, S_{\text{top}}$) are strictly normalized into $[0.0, 1.0]$ before combination.

---

## 9. Self-Exclusion Behavior

The source work is **strictly excluded** from its own similar research results:
1. `exclude_work_id=work_id` is passed to the SQL queries in both `VectorRepository` and `LexicalRepository`.
2. Post-retrieval validation ensures no candidate matches `source_work_id`.

---

## 10. Filter Support

All database-level metadata filters supported in `VectorRepository` and `LexicalRepository` are propagated:
- `publication_year`: Exact year match
- `min_year`, `max_year`: Publication year range
- `work_type`: Scholarly work classification (`article`, `preprint`, etc.)
- `language`: ISO language code (`en`, `de`, etc.)
- `primary_source_id`: Publication venue UUID (`research_sources.id`)
- `is_oa`: Open access boolean flag
- `min_citations`: Citation count threshold (`cited_by_count >= min_citations`)

---

## 11. Limits & Validation

- `limit` parameter is sanitized using `sanitize_candidate_limit`.
- Values $\le 0$ raise `VectorValidationError`.
- Values exceeding `max_limit` are clamped safely to `max_limit` (default 100).

---

## 12. Deterministic Ranking & Tie-Breaking

To guarantee reproducible rankings across environments, candidate ordering follows a strict 5-level tie-breaking tuple:
1. `combined_similarity` (Descending)
2. `semantic_similarity` (Descending)
3. `lexical_similarity` (Descending)
4. `topic_similarity` (Descending)
5. `str(candidate_work_id)` (Ascending lexicographical UUID)

---

## 13. Missing Embedding Behavior

| Scenario | Behavior | Exception Raised |
|---|---|---|
| Source work does not exist | Abort query | `ResearchWorkNotFoundError` |
| Source work has `embedding = None` | Abort query | `MissingEmbeddingError` |
| Source work has invalid vector dim | Abort query | `VectorValidationError` |
| Candidate work missing embedding | Include via lexical/topic signals | Semantic sim defaults to `0.0` |
| Source work missing title | Skip lexical retrieval | Lexical sim defaults to `0.0` |
| Source/Candidate missing topics | Skip topic overlap | Topic sim defaults to `0.0` |

---

## 14. Result Model

```python
@dataclass(frozen=True)
class SimilarResearchResult:
    source_work_id: uuid.UUID
    candidate_work_id: uuid.UUID
    combined_similarity: float
    semantic_similarity: float
    lexical_similarity: float
    topic_similarity: float
    rank: int
    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    retrieval_sources: list[str] = field(default_factory=list)
    candidate_work: Any | None = None
```

This model captures full score provenance, allowing Phase 2.4F (Explainable Recommendations) to easily generate human-readable rationales (e.g. *"91% similarity: shares topic 'Machine Learning' and similar abstract embeddings"*).

---

## 15. Testing Strategy

1. **Unit Tests** (`backend/tests/test_similar_research_service.py`):
   - Score normalization math and monotonicity
   - Topic similarity calculation (exact match, primary match bonus, DAG hierarchical ancestor)
   - Source work retrieval exceptions (`ResearchWorkNotFoundError`, `MissingEmbeddingError`, `VectorValidationError`)
   - Strict self-exclusion regression test
   - Multi-channel retrieval and fusion scoring
   - Metadata filter propagation
   - Deterministic tie-breaking verification
   - Custom weights and limit clamping
2. **Integration Tests**:
   - Conditional PostgreSQL integration tests executing end-to-end against live database fixtures.

---

## 16. Database Migration Status

> [!NOTE]
> **No database schema migration was required for Phase 2.4C.**
> All necessary database tables (`research_works`, `topics`, `research_work_topics`) and vector HNSW indexes were established in Phases 2.3A, 2.3B, and 2.4A.
> The Alembic migration head remains at `0006_phase2_3b_semantic_embeddings`.

---

## 17. Future Integration with Phase 2.4D

In **Phase 2.4D** (Research $\leftrightarrow$ Opportunity Matching), this retrieval architecture will be extended to match research works directly with actionable calls for papers and journal opportunities (`OpportunityModel`), bridging scholar research profiles with relevant academic venues.
