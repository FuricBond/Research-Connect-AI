# Phase 2.4 — Discovery & Intelligent Search Architecture

## 1. Executive Summary

Phase 2.4 delivers the **Discovery & Intelligent Search** subsystem for ResearchConnect AI. It bridges raw academic data and structured opportunity ingestion with high-precision semantic retrieval, multi-channel candidate fusion, deterministic hybrid ranking, explainable attribution, and a unified FastAPI discovery layer.

The complete subsystem consists of 8 modular layers:

```text
2.4A: Vector Retrieval Foundation (pgvector HNSW Cosine Search)
  │
  ▼
2.4B: Hybrid Research Search & Candidate Fusion (Vector + Lexical RRF)
  │
  ▼
2.4C: Similar Research Retrieval (Semantic + Lexical + Taxonomy DAG Overlap)
  │
  ▼
2.4D: Research ↔ Opportunity Matching (Semantic + Topic + Type + Deadline)
  │
  ▼
2.4E: Hybrid Candidate Ranking Engine (Normalized Signals & Mode Weights)
  │
  ▼
2.4F: Explainable Results Layer (Deterministic Signal Attributions & Narratives)
  │
  ▼
2.4G: FastAPI Discovery REST API (/api/v1/discovery/...)
  │
  ▼
2.4H: Testing, Benchmarking & IR Quality Evaluation
```

---

## 2. Component Architecture & Data Flow

```
                                [ Client / React Frontend ]
                                             │
                                             ▼ HTTP / JSON
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Discovery Layer (Phase 2.4G)                            │
│  - GET /api/v1/discovery/research/search                                               │
│  - GET /api/v1/discovery/research/{work_id}/similar                                    │
│  - GET /api/v1/discovery/research/{work_id}/opportunities                              │
│  - Bounded Pagination (limit: 1..100, offset >= 0) & Filter Validation                 │
└────────────────────────────────────────────┬───────────────────────────────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
┌──────────────────────────────────────────┐    ┌────────────────────────────────────────┐
│      Retrieval & Matching Services       │    │      Hybrid Ranking & Explainability   │
│                                          │    │                                        │
│ 1. HybridSearchService (2.4B)            │    │ 1. HybridRanker (2.4E)                 │
│    - Vector Search + Lexical FTS + RRF   │───▶│    - GENERAL Mode                      │
│                                          │    │    - RESEARCH_SIMILARITY Mode          │
│ 2. SimilarResearchService (2.4C)         │    │    - RESEARCH_OPPORTUNITY Mode         │
│    - Vector + Lexical + Taxonomy DAG     │    │    - Deterministic UUID Tie-Breaking   │
│                                          │    │                                        │
│ 3. MatchingService (2.4D)                │    │ 2. ResultExplainer (2.4F)              │
│    - Semantic + Topic + Type + Deadline  │    │    - Machine Signal Contributions      │
│                                          │    │    - Human Summaries, Strengths, Limits│
└──────────────────────┬───────────────────┘    └───────────────────┬────────────────────┘
                       │                                            │
                       ▼                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                             Storage & Database Repositories                            │
│                                                                                        │
│ 1. VectorRepository (Phase 2.4A)                                                       │
│    - pgvector 384d cosine distance (<=>) with HNSW indexes                             │
│ 2. LexicalRepository (Phase 2.4B)                                                      │
│    - PostgreSQL Full-Text Search (ts_rank_cd over title + abstract)                    │
│ 3. TaxonomyService (Phase 2.3A)                                                        │
│    - Canonical taxonomy DAG, alias mapping, and hierarchical distance                  │
│ 4. PostgreSQL Relational Models                                                        │
│    - research_works, opportunities, topics, research_work_topics, opportunity_topics    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Breakdown

### 3.1. Phase 2.4A — Vector Retrieval Foundation
- **Core Abstraction**: `VectorRepository` ([`backend/app/repositories/vector_repository.py`](file:///d:/Project/researchconnect-ai/backend/app/repositories/vector_repository.py)).
- **Indexing**: pgvector HNSW index on 384-dimensional dense embeddings (`sentence-transformers/all-MiniLM-L6-v2`).
- **Retrieval Metric**: Cosine distance operator (`<=>`). Cosine similarity computed as $1.0 - \text{distance}$.
- **Safety**: Safe candidate limits ($\min(100, \text{limit})$) and metadata filtering (year, work type, language, source venue, open access).

### 3.2. Phase 2.4B — Hybrid Search & Candidate Fusion
- **Core Abstraction**: `LexicalRepository`, `HybridSearchService`, `reciprocal_rank_fusion` ([`backend/app/services/hybrid_search_service.py`](file:///d:/Project/researchconnect-ai/backend/app/services/hybrid_search_service.py)).
- **Dual-Path Ingestion**: Dispatches lexical full-text query (`to_tsvector`) and dense embedding vector search concurrently.
- **RRF Algorithm**:
  $$\text{RRF Score}(d) = \sum_{c \in \{\text{vector}, \text{lexical}\}} \frac{1}{k + r_c(d)}, \quad k = 60$$
- **Deduplication**: Merges multi-channel candidate appearances into a single `HybridSearchResult` with provenance tracking (`retrieval_sources`).

### 3.3. Phase 2.4C — Similar Research Retrieval
- **Core Abstraction**: `SimilarResearchService` ([`backend/app/services/similar_research_service.py`](file:///d:/Project/researchconnect-ai/backend/app/services/similar_research_service.py)).
- **Multi-Signal Similarity**:
  $$\text{Similarity} = w_{\text{sem}} \cdot S_{\text{sem}} + w_{\text{lex}} \cdot S_{\text{lex}} + w_{\text{topic}} \cdot S_{\text{topic}}$$
- **Taxonomy DAG Proximity**: Explores canonical topic graph relationships and common taxonomy ancestor depth for non-identical topics.
- **Self-Exclusion**: Guarantees source paper UUID is excluded from candidate results.

### 3.4. Phase 2.4D — Research ↔ Opportunity Matching
- **Core Abstraction**: `ResearchOpportunityMatchingService` ([`backend/app/services/research_opportunity_matching_service.py`](file:///d:/Project/researchconnect-ai/backend/app/services/research_opportunity_matching_service.py)).
- **Multi-Signal Match**:
  $$\text{Match} = w_{\text{sem}} S_{\text{sem}} + w_{\text{lex}} S_{\text{lex}} + w_{\text{topic}} S_{\text{topic}} + w_{\text{type}} S_{\text{type}}$$
- **Publication Type Matrix**: Deterministic compatibility mapping (e.g. `article` $\to$ `JOURNAL`, `preprint` $\to$ `CONFERENCE`).
- **Urgency Modeling**: Linear deadline proximity within an active 90-day window.

### 3.5. Phase 2.4E — Hybrid Candidate Ranking Engine
- **Core Abstraction**: `HybridRanker` ([`backend/app/ranking/hybrid_ranker.py`](file:///d:/Project/researchconnect-ai/backend/app/ranking/hybrid_ranker.py)).
- **Normalized Composite Scoring**:
  $$\text{Final Score} = \sum_{i=1}^M w_i \cdot S_i, \quad \sum w_i = 1.0, \quad S_i \in [0.0, 1.0]$$
- **Freshness Half-Life Decay**:
  $$\text{Freshness} = \exp\left(-\frac{\ln(2)}{t_{1/2}} \cdot \Delta t\right), \quad t_{1/2} = 5.0 \text{ years}$$
- **Deterministic Tie-Breaking**: Primary sort descending by score; secondary sort ascending by candidate UUID string.

### 3.6. Phase 2.4F — Explainable Results Layer
- **Core Abstraction**: `ResultExplainer` ([`backend/app/explainability/result_explainer.py`](file:///d:/Project/researchconnect-ai/backend/app/explainability/result_explainer.py)).
- **Deterministic Attributions**:
  $$\text{contribution}_i = \text{round}(\text{score}_i \cdot \text{weight}_i, 6)$$
- **Zero LLM Reliance**: Generates concise human-readable summaries, positive strengths, and limiting factors without external API dependencies.
- **Data Absence vs Negative Signal**: Suppresses false negative claims when metadata (publication year, topic tags, vector embedding) is absent.

### 3.7. Phase 2.4G — FastAPI Discovery REST Layer
- **Core Abstraction**: `discovery_router` ([`backend/app/api/v1/discovery.py`](file:///d:/Project/researchconnect-ai/backend/app/api/v1/discovery.py)).
- **Endpoints**:
  - `GET /api/v1/discovery/research/search`
  - `GET /api/v1/discovery/research/{work_id}/similar`
  - `GET /api/v1/discovery/research/{work_id}/opportunities`
- **Output Schemas**: Clean Pydantic schemas separating external API representations from internal ORM models and embeddings.

### 3.8. Phase 2.4H — Testing, Benchmarking & Evaluation
- **Benchmark Suite**: 16 deterministic scenarios ([`backend/app/evaluation/benchmark_dataset.py`](file:///d:/Project/researchconnect-ai/backend/app/evaluation/benchmark_dataset.py)).
- **IR Metrics**: Precision@K, Recall@K, HitRate@K, MRR, NDCG@K ([`backend/app/evaluation/metrics.py`](file:///d:/Project/researchconnect-ai/backend/app/evaluation/metrics.py)).
- **Verification**: 573 automated tests passing with 0 regressions.

---

## 4. Production Readiness & Next Phase

With the completion of Phase 2.4H, the entire **Discovery & Intelligent Search** subsystem is fully implemented, mathematically verified, benchmarked, and documented.

The repository is ready to transition to **Phase 3 — Personalized Researcher Intelligence & Recommendations**.
