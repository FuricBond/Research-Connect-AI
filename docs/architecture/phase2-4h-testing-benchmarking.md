# Phase 2.4H — Testing, Benchmarking & Evaluation Report

## 1. Overview & Objective

Phase 2.4H serves as the final testing, benchmarking, and validation closure phase for the entire **Phase 2.4 Discovery & Intelligent Search** system.

The objective is to:
1. Validate end-to-end multi-channel retrieval, candidate fusion, hybrid ranking, explainability, and FastAPI exposure.
2. Formulate reproducible Information Retrieval (IR) quality metrics (Precision@K, Recall@K, HitRate@K, MRR, NDCG@K).
3. Evaluate retrieval channels (Vector-only vs Lexical-only vs Hybrid/RRF).
4. Measure ranking accuracy, determinism, and tie-breaking consistency.
5. Validate explainability mathematical attribution precision.
6. Measure API latency, throughput, and concurrency profiles.
7. Test resilience across missing data and degraded signal scenarios.

---

## 2. Ground Truth & Evaluation Dataset Methodology

Relevance evaluation uses a version-controlled, deterministic benchmark dataset containing **16 representative scenarios** ([`backend/app/evaluation/benchmark_dataset.py`](file:///d:/Project/researchconnect-ai/backend/app/evaluation/benchmark_dataset.py)):

### 2.1. Ground Truth Categorization
- **`SYNTHETIC_FIXTURE`**: Constructive scenarios where relevance is mathematically defined (e.g. synonym queries, keyword acronyms, freshness decay, tie-breaking).
- **`HEURISTIC_METADATA`**: Deterministic scenarios where relevance is inferred from canonical taxonomy overlap, publication type compatibility, and lexical/semantic similarity.
- **Human-Labelled**: Not used in Phase 2.4H due to the absence of subjective crowd-worker annotations in the repository.

### 2.2. Evaluation Scenarios
1. Exact research-topic match
2. Strong semantic match with different terminology (synonym / paraphrase)
3. Strong lexical match with specific technical acronyms
4. Shared taxonomy ancestor without exact topic overlap (DAG hierarchical proximity)
5. Strong multi-topic canonical overlap
6. Similar research with recency decay evaluation (freshness half-life $t_{1/2}=5.0$ yr)
7. Strong research $\to$ conference opportunity match
8. Strong research $\to$ journal opportunity match
9. Weak opportunity compatibility rejection
10. Imminent opportunity deadline vs distant deadline ($< 14$ days vs $> 85$ days)
11. Distant deadline ($> 90$ days)
12. Missing vector embedding resilience (graceful degradation to lexical/topic)
13. Missing topic metadata resilience
14. Zero-relevance empty results
15. Multi-channel provenance (dual vector + lexical confirmation)
16. Tied candidate scores (UUID deterministic tie-breaking)

---

## 3. Retrieval Strategy Comparison

Evaluated across the benchmark dataset comparing:
- **Vector-only**: dense cosine similarity retrieval
- **Lexical-only**: PostgreSQL full-text search (`ts_rank_cd`)
- **Hybrid (Phase 2.4E/2.4G)**: Multi-channel candidate fusion with RRF + hybrid ranking

| Retrieval Strategy | Mean Precision@5 | Mean Recall@5 | Mean HitRate@5 | Mean NDCG@5 | MRR |
|---|---|---|---|---|---|
| **Vector-only** | 0.2400 | 1.0000 | 1.0000 | 0.9333 | 1.0000 |
| **Lexical-only** | 0.2400 | 1.0000 | 1.0000 | 0.9110 | 0.9667 |
| **Hybrid (Fused & Ranked)** | **0.2400** | **1.0000** | **1.0000** | **0.9333** | **1.0000** |

### Observations:
- Hybrid retrieval matches or exceeds individual single-channel metrics on every dimension.
- Lexical-only retrieval struggles on synonym-based semantic queries (MRR drops to 0.9667, NDCG@5 drops to 0.9110).
- Hybrid retrieval recovers full recall and top-rank accuracy when either channel experiences vocabulary mismatch.

---

## 4. Ranking Engine Evaluation (Phase 2.4E)

- **Determinism**: 10 repeated iterations of identical input produced 100% identical rank orderings.
- **Tie-Breaking**: Candidates with identical scores broken deterministically by entity UUID string.
- **Active Modes Tested**:
  - `GENERAL`: Semantic (0.50), Lexical (0.25), Topic (0.25)
  - `RESEARCH_SIMILARITY`: Semantic (0.50), Lexical (0.20), Topic (0.20), Freshness (0.10)
  - `RESEARCH_OPPORTUNITY`: Semantic (0.45), Lexical (0.15), Topic (0.20), Type (0.10), Urgency (0.10)
- **Score Validity**: 100% of composite scores bounded strictly within $[0.0, 1.0]$.

---

## 5. Explainability Engine Validation (Phase 2.4F)

- **Mathematical Contribution Alignment**:
  $$\text{contribution}_i = \text{round}(\text{score}_i \cdot \text{weight}_i, 6)$$
  - Total signal attributions verified: **106**
  - Mathematical alignments verified: **106**
  - Attribution accuracy rate: **100.0%**
- **Missing Data Handling**:
  - Missing embedding $\implies$ `is_available = False`, suppresses false semantic claims.
  - Missing topic associations $\implies$ descriptive note without false penalization.
  - Expired deadline $\implies$ urgency marked 0.0 without invalid boost.

---

## 6. API Latency & Performance Benchmarks (Phase 2.4G)

Measured over 30 iterations per endpoint (local test environment, Python 3.13.5 on Windows 11):

| Endpoint | p50 Latency (ms) | p95 Latency (ms) | p99 Latency (ms) | Mean Latency (ms) | Min (ms) | Max (ms) |
|---|---|---|---|---|---|---|
| `GET /research/search` | 2.174 | 2.641 | 6.678 | 2.360 | 1.996 | 6.678 |
| `GET /research/{id}/similar` | 2.135 | 2.393 | 2.633 | 2.165 | 2.002 | 2.633 |
| `GET /research/{id}/opportunities` | 2.237 | 3.126 | 4.444 | 2.352 | 2.027 | 4.444 |

---

## 7. Concurrency Profile

Simulated client concurrency levels:

| Concurrency Level | Total Requests | Successful Requests | Error Rate | Duration (s) | Throughput (QPS) |
|---|---|---|---|---|---|
| **1 Client** | 4 | 4 | 0.0% | 0.0096 | 414.6 |
| **5 Clients** | 20 | 20 | 0.0% | 0.0436 | 458.8 |
| **10 Clients** | 40 | 40 | 0.0% | 0.0863 | 463.5 |
| **25 Clients** | 100 | 100 | 0.0% | 0.2864 | 349.1 |

---

## 8. Database Performance & Indexing Analysis

- **pgvector HNSW Indexes**:
  - `idx_research_works_embedding_hnsw`: cosine distance on `research_works.embedding` (`m=16, ef_construction=64`).
  - `idx_opportunities_embedding_hnsw`: cosine distance on `opportunities.embedding`.
- **PostgreSQL Full-Text Search**:
  - `to_tsvector('english', title || ' ' || coalesce(abstract, ''))` used for lexical search.
- **Index Recommendations for Production**:
  - For production datasets exceeding $10^5$ research works, add stored generated `tsvector` columns with GIN indexes (`idx_research_works_fts_gin`) to avoid dynamic tsvector construction during queries.

---

## 9. Test Suite Summary

- **Total Tests Executed**: **573**
- **Passed**: **573 (100%)**
- **Skipped**: **8** (live external network tests)
- **Failures**: **0**
- **Regressions**: **0**
- **Execution Time**: **35.44s**
- **Alembic Migration Head**: `0006_phase2_3b_semantic_embeddings` (unchanged)
- **Frontend Build Status**: Clean build in 1.13s
