# Phase 2.4G — FastAPI Discovery Layer Architecture

## 1. Overview

Phase 2.4G implements the **FastAPI Discovery Layer** for ResearchConnect AI. It exposes the capabilities developed across Phases 2.4A through 2.4F as a clean, versioned, high-performance REST API.

The discovery layer unifies:
1. **Hybrid Research Search** (Phase 2.4B `HybridSearchService` via dense pgvector embeddings + PostgreSQL full-text RRF fusion)
2. **Similar Research Retrieval** (Phase 2.4C `SimilarResearchService` via multi-signal similarity, topic overlap, and DAG proximity)
3. **Research ↔ Opportunity Matching** (Phase 2.4D `ResearchOpportunityMatchingService` via type compatibility, topic alignment, and urgency)
4. **Hybrid Candidate Ranking** (Phase 2.4E `HybridRanker` with configurable modes and deterministic tie-breaking)
5. **Explainable Results** (Phase 2.4F `ResultExplainer` delivering deterministic signal attributions and qualitative reasoning)

---

## 2. API Architecture & Layer Separation

```
[Client / Frontend Application]
               │
               ▼ (HTTP / JSON)
┌─────────────────────────────────────────────────────────────┐
│                 FastAPI Discovery Router                    │
│                 (/api/v1/discovery/...)                     │
│  - Parameter Validation (Pydantic / FastAPI Query)         │
│  - Error Normalization & Domain Error Mapping               │
│  - Pagination (limit / offset / has_more)                   │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│   Retrieval & Matching       │ │   Hybrid Ranker & Explainer│
│   - HybridSearchService      │ │   - HybridRanker (2.4E)    │
│   - SimilarResearchService   │ │   - ResultExplainer (2.4F) │
│   - MatchingService          │ │                            │
└──────────────┬───────────────┘ └────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Database & Storage Repositories             │
│   - VectorRepository (HNSW 384d Cosine Distance)            │
│   - LexicalRepository (PostgreSQL tsvector / ts_rank_cd)    │
│   - TaxonomyService (Directed Acyclic Graph)                │
└─────────────────────────────────────────────────────────────┘
```

The router contains **no business logic or SQL queries**. It acts strictly as an orchestration and presentation layer that delegates candidate generation to retrieval services, passes candidates through the `HybridRanker`, generates optional explanations via `ResultExplainer`, and maps domain entities to validated Pydantic response models.

---

## 3. Route Structure & Endpoints

Base path: `/api/v1/discovery` (also mounted at `/api/discovery` for backward compatibility).

| Method | Path | Summary | Description |
|---|---|---|---|
| `GET` | `/api/v1/discovery/research/search` | Search Research Works | Multi-channel hybrid retrieval (dense embeddings + lexical text) over research works with hybrid ranking and explainability. |
| `GET` | `/api/v1/discovery/research/{work_id}/similar` | Retrieve Similar Research | Retrieve scholarly works similar to a source paper using vector similarity, lexical keywords, and taxonomy DAG proximity. |
| `GET` | `/api/v1/discovery/research/{work_id}/opportunities` | Match Opportunities for Work | Match academic CFPs/journals/conferences to a source research work using semantic relevance, topic compatibility, publication type matching, and deadline urgency. |

---

## 4. Request Parameters & Filter Specifications

### 4.1. Research Search (`/research/search`)
- `q`: `str` (required, min length: 1) — natural language search query.
- `limit`: `int` (1..100, default: 20) — maximum items returned.
- `offset`: `int` ($\ge 0$, default: 0) — items skipped for pagination.
- `publication_year`: `int | None` — filter exact publication year.
- `min_year`: `int | None` — filter minimum publication year ($year \ge min\_year$).
- `max_year`: `int | None` — filter maximum publication year ($year \le max\_year$).
- `work_type`: `str | None` — filter work type (`article`, `preprint`, `book-chapter`, `dataset`).
- `language`: `str | None` — filter two-letter language code (`en`, `fr`, etc.).
- `primary_source_id`: `UUID | None` — filter primary publication venue UUID.
- `is_oa`: `bool | None` — filter open-access status.
- `min_citations`: `int | None` ($\ge 0$) — filter minimum citation count.
- `exclude_work_id`: `UUID | None` — exclude specific research work UUID.
- `ranking_mode`: `RankingMode` (default: `general`) — ranking mode (`general`, `research_similarity`, `research_opportunity`).
- `explain`: `bool` (default: `false`) — attach structured explainability rationale to each result.

### 4.2. Similar Research (`/research/{work_id}/similar`)
- `work_id`: `UUID` (path parameter) — source research work UUID.
- `limit`, `offset`, `publication_year`, `min_year`, `max_year`, `work_type`, `language`, `primary_source_id`, `is_oa`, `min_citations` — same standard filters.
- `ranking_mode`: `RankingMode` (default: `research_similarity`).
- `explain`: `bool` (default: `false`).
- `require_embedding`: `bool` (default: `false`) — if `true` and source paper lacks vector embedding, aborts with HTTP 422 instead of degrading gracefully to lexical/topic channels.

### 4.3. Opportunity Matching (`/research/{work_id}/opportunities`)
- `work_id`: `UUID` (path parameter) — source research work UUID.
- `limit`, `offset` — pagination.
- `opportunity_type`: `OpportunityType | None` (`CONFERENCE`, `JOURNAL`, `WORKSHOP`, `CALL_FOR_PAPERS`, `GRANT_FELLOWSHIP`).
- `status`: `OpportunityStatus | None` (`ACTIVE`, `VERIFIED`, `EXPIRED`, `UNVERIFIED`).
- `delivery_mode`: `DeliveryMode | None` (`ONLINE`, `OFFLINE`, `HYBRID`).
- `source_id`: `UUID | None` — origin ingestion source UUID.
- `upcoming_only`: `bool` (default: `false`) — enforce `submission_deadline >= now()`.
- `submission_deadline_after`: `datetime | None` — filter deadlines after datetime.
- `ranking_mode`: `RankingMode` (default: `research_opportunity`).
- `explain`: `bool` (default: `false`).
- `require_embedding`: `bool` (default: `false`).

---

## 5. Response Schemas

### 5.1. Research Search Response (`ResearchSearchResponse`)
```json
{
  "query": "residual networks",
  "total": 1,
  "limit": 10,
  "offset": 0,
  "has_more": false,
  "ranking_mode": "general",
  "items": [
    {
      "work": {
        "id": "11111111-1111-1111-1111-111111111111",
        "openalex_id": "W2964344444",
        "doi": "10.1109/CVPR.2016.90",
        "title": "Deep Residual Learning for Image Recognition",
        "abstract": "Deeper neural networks are more difficult to train...",
        "publication_year": 2016,
        "publication_date": "2016-06-27",
        "work_type": "article",
        "language": "en",
        "cited_by_count": 50000,
        "is_oa": true,
        "oa_status": "gold",
        "landing_page_url": "https://doi.org/10.1109/CVPR.2016.90",
        "volume": null,
        "issue": null,
        "page": "770-778",
        "article_number": null,
        "license_url": null,
        "primary_source_id": null,
        "ingestion_source_id": null,
        "created_at": "2026-08-30T18:00:00Z",
        "updated_at": "2026-08-30T18:00:00Z"
      },
      "rank": 1,
      "final_score": 0.884,
      "semantic_score": 0.92,
      "lexical_score": 1.5,
      "topic_score": 0.0,
      "freshness_score": 0.25,
      "retrieval_sources": ["vector", "lexical"],
      "explanation": null
    }
  ]
}
```

### 5.2. Explanation Schema (`ExplanationSchema`)
When `explain=true`, every item includes a full deterministic audit trail:
```json
{
  "summary": "Ranked based primarily on strong semantic similarity and moderate lexical matching.",
  "strengths": [
    "Strong semantic similarity (0.9200) reflecting deep conceptual and contextual alignment",
    "Independent confirmation across multiple retrieval channels (vector, lexical)"
  ],
  "limitations": [
    "Older publication (2016) with lower recency weight (0.2500)"
  ],
  "signal_contributions": {
    "semantic_similarity": {
      "signal_name": "semantic_similarity",
      "score": 0.92,
      "weight": 0.60,
      "contribution": 0.552,
      "qualitative_assessment": "Very Strong",
      "is_available": true,
      "is_primary_driver": true
    },
    "lexical_relevance": {
      "signal_name": "lexical_relevance",
      "score": 0.75,
      "weight": 0.30,
      "contribution": 0.225,
      "qualitative_assessment": "Moderate",
      "is_available": true,
      "is_primary_driver": false
    }
  },
  "topic_evidence": {
    "shared_topic_ids": ["22222222-2222-2222-2222-222222222222"],
    "shared_topic_names": ["Computer Vision", "Deep Learning"],
    "topic_similarity": 0.85,
    "description": "Shared 2 topic(s): Computer Vision, Deep Learning with 85.0% topic compatibility."
  },
  "provenance_evidence": {
    "retrieval_sources": ["vector", "lexical"],
    "description": "Retrieved independently via multiple channels: vector, lexical."
  },
  "primary_factors": [
    "semantic_similarity (score: 0.9200, weight: 0.6000, contribution: 0.5520)"
  ],
  "final_score": 0.884,
  "rank": 1
}
```

---

## 6. Error Handling & HTTP Status Codes

The API maps domain conditions to clean, standard HTTP responses:

| Condition | Status Code | Detail Format |
|---|---|---|
| Invalid query parameter (e.g. limit > 100, empty query, malformed UUID) | `422 Unprocessable Entity` | Standard FastAPI validation payload |
| Research work not found | `404 Not Found` | `{"detail": "Research work '{work_id}' was not found."}` |
| Missing embedding with `require_embedding=true` | `422 Unprocessable Entity` | `{"detail": "Source research work '{work_id}' does not have a vector embedding."}` |
| Internal database / unexpected processing error | `500 Internal Server Error` | `{"detail": "An error occurred while executing research search."}` (internal stack traces suppressed) |

---

## 7. Pagination and Limit Protection

- `limit` is strictly bounded via FastAPI `Query(ge=1, le=100)`.
- `offset` is validated via `Query(ge=0)`.
- Slicing and `has_more` calculation:
  $$\text{has\_more} = (\text{offset} + \text{limit}) < \text{total}$$
- Candidates fetched from upstream services are capped at $\min(100, \text{limit} + \text{offset})$, preventing runaway memory allocation.

---

## 8. Dependency Injection & Service Integration

- Database sessions are injected using FastAPI's `Depends(get_db)`.
- Retrieval services (`hybrid_search_service`, `similar_research_service`, `research_opportunity_matching_service`), ranker (`hybrid_ranker`), and explainer (`result_explainer`) are consumed as singletons, maintaining testability via dependency overriding or `unittest.mock.patch`.

---

## 9. Testing Strategy

1. **Unit & Route Tests** (`backend/tests/test_discovery_api.py`):
   - 12 dedicated tests validating:
     - Hybrid research search with and without `explain`.
     - Similar research retrieval with 404, 422, and successful mapping.
     - Opportunity matching with filters (`CONFERENCE`, `HYBRID`, `upcoming_only`).
     - OpenAPI schema registration.
2. **Full Regression Suite**:
   - 561 tests passed across backend and scrapers with 0 regressions.
3. **Frontend Build Check**:
   - `tsc -b && vite build` builds cleanly.

---

## 10. Known Limitations & Future Extension Points

- **Phase 2.4H**: Benchmarking, quality evaluation, and load testing will be conducted in the next phase.
- **Phase 3**: User profile personalization, collaborative filtering, and saved search alerts will be added in Phase 3.
- **No LLM dependencies**: Explanations remain 100% deterministic and derived from statistical signals and metadata.
