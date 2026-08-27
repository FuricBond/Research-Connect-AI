# Phase 2.4D — Research ↔ Opportunity Matching

## 1. Objective

Phase 2.4D implements a dedicated, multi-signal **Research $\leftrightarrow$ Opportunity Matching** engine that answers:

> *"Given a research work (article, preprint, manuscript, or proposal), which academic opportunities (conferences, journals, workshops, CFPs, special issues) are most suitable for submission or dissemination?"*

The system discovers and ranks opportunity candidates by orchestrating:
1. **Semantic Similarity**: Cosine distance nearest-neighbor search via pgvector over 384-dimensional embeddings.
2. **Lexical Relevance**: PostgreSQL full-text search (`ts_rank_cd`) over opportunity titles, summaries, descriptions, and venues.
3. **Topic Compatibility**: Multi-evidence canonical topic overlap and taxonomy DAG hierarchical proximity.
4. **Opportunity Type Compatibility**: Deterministic compatibility matrix between the research work classification and the opportunity category.

> [!IMPORTANT]
> **Architectural Boundary**:
> Phase 2.4D is strictly a **Matching & Retrieval** layer. It does **NOT** build personalized researcher profiles, collaborative filtering models, deadline urgency biases, natural-language explanation generation (Phase 2.4F), or FastAPI endpoints (Phase 2.4G).

---

## 2. Architecture

```
                       Research Work (work_id)
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
  [ Vector Channel ]       [ Lexical Channel ]       [ Topic Associations ]
  VectorRepository         LexicalRepository         Canonical Topics (DAG)
  Query: work.embedding    Query: work.title         ResearchWorkTopicModel
  Opportunity Filters      Opportunity Filters       OpportunityTopicModel
         │                        │                        │
         └────────────────────────┬────────────────────────┘
                                  │
                                  ▼
                   Candidate Opportunities Union
                    (Deduplicated by UUID)
                                  │
                                  ▼
                 [ Multi-Signal Match Evaluation ]
         - Semantic Similarity (cosine in [0.0, 1.0])
         - Lexical Similarity (normalized in [0.0, 1.0])
         - Topic Compatibility (DAG overlap in [0.0, 1.0])
         - Type Compatibility (matrix mapping in [0.0, 1.0])
                                  │
                                  ▼
                 [ Composite Match Score Calculation ]
         match_score = w_sem * S_sem + w_lex * S_lex + w_top * S_top + w_typ * S_typ
         (Default weights: 0.50 semantic, 0.20 lexical, 0.20 topic, 0.10 type)
                                  │
                                  ▼
                     [ Deterministic Ranking ]
         Order by: match_score DESC -> S_sem DESC -> S_top DESC -> S_lex DESC -> S_typ DESC -> UUID ASC
                                  │
                                  ▼
                    list[ResearchOpportunityMatch]
```

---

## 3. Candidate Retrieval Channels

### A. Semantic Channel
- Consumes the research work's pre-computed 384-dimensional embedding (`all-MiniLM-L6-v2`).
- Calls `VectorRepository.search_opportunities` using pgvector cosine distance (`<=>`).
- Filters out NULL embeddings natively. Distance is converted to similarity: $\text{similarity} = \text{round}(1.0 - \text{distance}, 6) \in [0.0, 1.0]$.

### B. Lexical Channel
- Consumes the research work's title (and available textual metadata).
- Calls `LexicalRepository.search_opportunities` using PostgreSQL `ts_rank_cd` over weighted tsvectors.
- Raw scores are mapped to $[0.0, 1.0)$ via the monotonic saturating transform:
  $$S_{\text{lex}} = \frac{\text{raw\_score}}{\text{raw\_score} + 1.0}$$

### C. Topic Channel
- Utilizes the canonical academic taxonomy tree ([`ml/topic_analysis/taxonomy.py`](file:///d:/Project/researchconnect-ai/ml/topic_analysis/taxonomy.py)).
- Compares canonical topic assignments between `ResearchWorkTopicModel` and `OpportunityTopicModel`.
- Evaluates exact matches, primary topic bonuses ($+20\%$), and taxonomy DAG ancestor/descendant relationships ($+15\%$).

---

## 4. Opportunity Type Compatibility Matrix

A conservative, deterministic mapping reflects natural academic dissemination targets:

| Research Work Type (`work_type`) | Target Opportunity Type (`opportunity_type`) | Compatibility Score ($S_{\text{type}}$) |
|---|---|---|
| `article`, `journal-article`, `review` | `JOURNAL` | `1.00` |
| `article`, `journal-article`, `review` | `SPECIAL_ISSUE` | `0.95` |
| `article`, `journal-article`, `review` | `CALL_FOR_PAPERS` | `0.85` |
| `article`, `journal-article` | `CONFERENCE` | `0.70` |
| `article`, `journal-article` | `WORKSHOP` | `0.60` |
| `proceedings-article`, `conference-paper` | `CONFERENCE` | `1.00` |
| `proceedings-article`, `conference-paper` | `WORKSHOP` | `0.90` |
| `proceedings-article`, `conference-paper` | `CALL_FOR_PAPERS` | `0.85` |
| `proceedings-article`, `conference-paper` | `JOURNAL` | `0.65` |
| `workshop-paper` | `WORKSHOP` | `1.00` |
| `workshop-paper` | `CONFERENCE` | `0.85` |
| `preprint`, `manuscript`, `draft` | `CONFERENCE`, `JOURNAL`, `CALL_FOR_PAPERS` | `0.90` |
| `preprint`, `manuscript`, `draft` | `WORKSHOP`, `SPECIAL_ISSUE` | `0.85` |
| `book-chapter`, `book` | `CALL_FOR_PAPERS`, `SPECIAL_ISSUE` | `0.80` |
| Unspecified / Default | Any | `0.70` |

---

## 5. Scoring Formula & Configuration

$$\text{match\_score} = w_{\text{semantic}} \cdot S_{\text{sem}} + w_{\text{lexical}} \cdot S_{\text{lex}} + w_{\text{topic}} \cdot S_{\text{top}} + w_{\text{type}} \cdot S_{\text{type}}$$

### Configuration Defaults

| Setting | Default | Description |
|---|---|---|
| `settings.research_opportunity_semantic_weight` | `0.50` | Primary semantic concept weight |
| `settings.research_opportunity_lexical_weight` | `0.20` | Full-text keyword match weight |
| `settings.research_opportunity_topic_weight` | `0.20` | Canonical topic compatibility weight |
| `settings.research_opportunity_type_weight` | `0.10` | Publication type compatibility weight |
| `settings.research_opportunity_default_limit` | `20` | Default matches returned |
| `settings.research_opportunity_max_limit` | `100` | Maximum retrieval limit ceiling |
| `settings.research_opportunity_candidate_multiplier` | `2.5` | Candidate oversampling multiplier |

---

## 6. Hard Filters

Candidate opportunities can be filtered at the database level before multi-signal evaluation:
- `status`: Lifecycle status (`ACTIVE`, `EXPIRED`, etc.).
- `opportunity_type`: Type filter (`CONFERENCE`, `JOURNAL`, `WORKSHOP`, `CALL_FOR_PAPERS`, `SPECIAL_ISSUE`).
- `delivery_mode`: Delivery mode (`ONLINE`, `OFFLINE`, `HYBRID`).
- `source_id`: Origin ingestion source UUID.
- `upcoming_only`: Restricts to `submission_deadline >= now()`.
- `submission_deadline_after`: Restricts to `submission_deadline >= specified_datetime`.

---

## 7. Missing Data Behavior

| Scenario | Service Behavior | Result / Error |
|---|---|---|
| Research work does not exist | Abort query | Raises `ResearchWorkNotFoundError` |
| Research work missing embedding (`require_embedding=True`) | Abort query | Raises `MissingEmbeddingError` |
| Research work missing embedding (`require_embedding=False`) | Degrade gracefully | $S_{\text{sem}} = 0.0$, matches via lexical & topic |
| Opportunity missing embedding | Graceful match | $S_{\text{sem}} = 0.0$, discovered via lexical/topic |
| Missing topic associations | Skip topic overlap | $S_{\text{top}} = 0.0$ |
| Missing abstract or body text | Fallback to title | Lexical channel uses title |

---

## 8. Result Model

```python
@dataclass(frozen=True)
class ResearchOpportunityMatch:
    research_work_id: uuid.UUID
    opportunity_id: uuid.UUID
    match_score: float
    semantic_similarity: float
    lexical_similarity: float
    topic_similarity: float
    type_compatibility: float
    rank: int
    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    retrieval_sources: list[str] = field(default_factory=list)
    opportunity: Any | None = None
```

---

## 9. Performance & Scalability Considerations

- **Oversampled Candidate Retrieval**: Avoids full-table cross joins ($O(N \times M)$) by retrieving the top candidate pool ($O(K)$) via indexed pgvector HNSW and PostgreSQL FTS.
- **Batch Topic Resolution**: Opportunity topic associations are batch-loaded in a single query using `where(OpportunityTopicModel.opportunity_id.in_(candidate_ids))` to eliminate N+1 database queries.
- **Cycle-Safe Taxonomy**: Traversal in `TaxonomyService` is bounded with cycle validation.

---

## 10. Database Migration Status

> [!NOTE]
> **No database schema migration was required for Phase 2.4D.**
> All necessary database tables (`research_works`, `opportunities`, `topics`, `research_work_topics`, `opportunity_topics`) and vector HNSW indexes were established in previous phases.
> The Alembic migration head remains at `0006_phase2_3b_semantic_embeddings`.
