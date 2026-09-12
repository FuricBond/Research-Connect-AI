# Phase 3.7 — Recommendation History & Evaluation

**Status**: COMPLETE  
**Commit**: Phase 3.7  
**Scope**: Recommendation Snapshots, Deterministic Ranking Versioning, Feedback Linkage, Offline Information Retrieval Evaluation Metrics, Data Sufficiency Classifications, and Observability APIs.

---

## 1. Overview & Purpose

ResearchConnect AI previously implemented:
- **Phase 3.1**: Canonical Researcher Identity & Profile Foundation
- **Phase 3.2**: Scholarly Interests & Expertise Intelligence
- **Phase 3.3**: Personal Preference Intelligence
- **Phase 3.4**: Multi-Channel Personalized Candidate Generation
- **Phase 3.5**: Bounded Personalization Ranking Layer ($\le 0.15$)
- **Phase 3.6**: Feedback & Recommendation Learning Loop

**Phase 3.7 introduces recommendation history, reproducible recommendation snapshots, and offline evaluation metrics.**

The architectural purpose of this phase is to answer:
> *"What did the system recommend to this researcher, when, using which ranking version/signals, and how good were those recommendations?"*

### Core Architectural Guarantees
1. **Strictly Read-Only Evaluation**: Evaluation metrics are purely observational. They **never** modify ranking weights, candidate pools, or preferences automatically. No online learning, reinforcement learning, or automated weight tuning.
2. **Snapshot Immutability**: Historical snapshots represent what was actually recommended at that point in time. They never mutate when researcher profiles, preferences, feedback, ranking weights, or opportunity metadata change later.
3. **Deterministic Versioning**: Every snapshot stores an explicit, deterministic `ranking_version` (`phase3.7-v1`, `phase3.5-personalized`, `phase2-baseline`) allowing historical segmentation and comparative evaluation across algorithm evolutions ($R_0$ vs $R_1$ vs $R_2$).
4. **Grounded Feedback Semantics**: Outcome metrics reuse Phase 3.6 feedback definitions (`APPLY` = 4, `INTERESTED` = 3, `SAVE` = 2, `VIEW` = 1, `DISMISS` / `NOT_INTERESTED` = 0) rather than inventing arbitrary or hidden labels.
5. **Explicit Data Sufficiency Reporting**: Metrics declare their evidence state (`SUFFICIENT_DATA`, `INSUFFICIENT_DATA`, `NO_FEEDBACK`, `NO_HISTORY`). When insufficient ground truth exists (e.g. 0 positive interactions for Recall@K), the system returns `null` with `INSUFFICIENT_DATA` rather than fabricating `0.0`.
6. **Zero N+1 Query Performance**: Snapshot retrieval uses indexed foreign keys and pagination. Batch evaluation aggregates feedback across all candidate items in exactly **2 queries** (1 for snapshots/items, 1 for batched feedback lookup).

---

## 2. Recommendation History Architecture

### Data Models (`backend/app/models/recommendation_history.py`)

A normalized 2-table model is utilized to eliminate redundant opportunity record cloning while preserving exact ranking order, score attributions, and point-in-time trust/deadline status:

#### 1. `ResearcherRecommendationSnapshotModel` (`researcher_recommendation_snapshots`)
- `id` (`UUID`, Primary Key)
- `researcher_id` (`UUID`, ForeignKey `research_profiles.id`, ondelete="CASCADE", indexed)
- `ranking_version` (`String(50)`, indexed): Deterministic version identifier (`phase3.7-v1`, `phase3.5-personalized`, `phase2-baseline`).
- `candidate_count` (`Integer`): Total candidates considered in the pool before ranking/slicing.
- `returned_count` (`Integer`): Number of recommendations returned in this snapshot.
- `request_context` (`JSONB`): Query parameters, filter options, limit, offset, and ablation settings.
- `request_hash` (`String(64)`, indexed): SHA-256 hash of `(researcher_id, ranking_version, tuple(opportunity_ids))` for idempotency and polling deduplication.
- `session_id` (`String(100)`, indexed): Optional client-supplied recommendation session tracking token.
- `created_at` (`DateTime(timezone=True)`, indexed)

#### 2. `ResearcherRecommendationItemModel` (`researcher_recommendation_items`)
- `id` (`UUID`, Primary Key)
- `snapshot_id` (`UUID`, ForeignKey `researcher_recommendation_snapshots.id`, ondelete="CASCADE", indexed)
- `opportunity_id` (`UUID`, ForeignKey `opportunities.id`, ondelete="CASCADE", indexed)
- `rank` (`Integer`): 1-indexed position in the presented recommendation list.
- `base_relevance_score` (`Float`): Phase 2 HybridRanker base relevance score.
- `personalization_score` (`Float`): Phase 3.5 personalization score.
- `behavioral_adjustment` (`Float`): Phase 3.6 behavioral contribution.
- `final_score` (`Float`): Composite recommendation score.
- `risk_level` (`String(50)`): Phase 2.6 risk classification at recommendation time (`LOW_RISK`, `MODERATE_RISK`, `HIGH_RISK`).
- `deadline_status` (`String(50)`): Phase 2.7 deadline status at recommendation time (`UPCOMING`, `DUE_TODAY`, `EXPIRED`, `MISSING`).
- Constraints:
  - `UniqueConstraint("snapshot_id", "opportunity_id", name="uq_snapshot_opportunity")`
  - `UniqueConstraint("snapshot_id", "rank", name="uq_snapshot_rank")`

---

## 3. Snapshot Idempotency & Polling Deduplication

To prevent frontend polling loops or rapid page re-renders from generating duplicate snapshots:
1. **Request Hashing**: A deterministic SHA-256 hash is computed over `(researcher_id, ranking_version, tuple(ordered_opportunity_ids))`.
2. **Cooldown Window**: If an identical snapshot was recorded for this researcher within `DEFAULT_COOLDOWN_MINUTES` (5 minutes), the existing snapshot is returned instead of inserting duplicate rows.
3. **Session ID Matching**: If an explicit `session_id` is passed and already exists for this researcher, the existing snapshot is returned.
4. **Bypass Flag**: Clients can pass `persist_snapshot=False` when running dry-run ranking or preview diagnostics without mutating history.

---

## 4. Grounded Offline Evaluation Metrics

Offline evaluation connects recommendation snapshots with Phase 3.6 feedback events without duplicating feedback data.

### Relevance Definitions
Relevance is defined explicitly from observed researcher interactions:
- **Graded Relevance (for NDCG@K)**:
  - `APPLY`: $4.0$ (Highest relevance — tracked manuscript submission / grant application)
  - `INTERESTED`: $3.0$ (High relevance — explicit thumbs up)
  - `SAVE`: $2.0$ (Positive relevance — bookmarked for future action)
  - `VIEW`: $1.0$ (Weak positive — inspected opportunity details)
  - `DISMISS` / `NOT_INTERESTED` / None: $0.0$ (Negative / not relevant)
- **Binary Relevance (for Precision@K, Recall@K, HitRate@K)**:
  - Positively endorsed items: `SAVE`, `INTERESTED`, `APPLY`.

### Mathematical Metric Formulations
1. **Precision@K**:
   $$\text{Precision@K} = \frac{|\text{Relevant recommendations in top } K|}{K}$$
2. **Recall@K**:
   $$\text{Recall@K} = \frac{|\text{Relevant recommendations in top } K|}{|\text{All known relevant opportunities for researcher}|}$$
   *Note: If $|\text{All known relevant opportunities}| = 0$, returns `null` with `INSUFFICIENT_DATA` rather than fabricating `0.0`.*
3. **HitRate@K**:
   $$\text{HitRate@K} = \begin{cases} 1.0 & \text{if at least one relevant recommendation in top } K \\ 0.0 & \text{otherwise} \end{cases}$$
4. **NDCG@K (Normalized Discounted Cumulative Gain)**:
   $$\text{DCG@K} = \sum_{i=1}^K \frac{2^{rel_i} - 1}{\log_2(i + 1)}, \quad \text{NDCG@K} = \frac{\text{DCG@K}}{\text{IDCG@K}}$$
   *Normalized strictly to $0.0 \le \text{NDCG@K} \le 1.0$.*
5. **Save Rate**:
   $$\text{Save Rate} = \frac{|\text{Saved recommended opportunities}|}{|\text{Unique recommended opportunities shown}|}$$
6. **Engagement Rate**:
   $$\text{Engagement Rate} = \frac{|\text{Opportunities with VIEW, SAVE, INTERESTED, or APPLY}|}{|\text{Unique recommended opportunities shown}|}$$
7. **Dismissal Rate**:
   $$\text{Dismissal Rate} = \frac{|\text{Opportunities with DISMISS or NOT\_INTERESTED}|}{|\text{Unique recommended opportunities shown}|}$$

---

## 5. Data Sufficiency Classifications

To prevent misleading evaluation scores when little or no data exists, every evaluation response reports an explicit `data_status`:

| Status | Condition | Metric Behavior |
| :--- | :--- | :--- |
| `NO_HISTORY` | 0 recommendation snapshots exist | Sample size = 0, all IR metrics = `null`, all rates = `null`. |
| `NO_FEEDBACK` | Snapshots exist, but 0 interaction events | Sample size > 0, rates = $0.0$, all IR metrics = `null` (never returns 0.0!). |
| `INSUFFICIENT_DATA` | Sample size < 5 items OR 0 positive items | Precision/NDCG calculated with caveat notes; Recall = `null`. |
| `SUFFICIENT_DATA` | $\ge 5$ items evaluated AND $\ge 1$ positive item | Full suite of IR metrics and outcome rates computed. |

---

## 6. Algorithm Version Comparison ($R_0$ vs $R_1$ vs $R_2$)

The evaluation engine aggregates historical snapshots across different ranking algorithm evolutions:
- **$R_0$ Baseline**: `phase2-baseline` (Pure Phase 2 HybridRanker base relevance)
- **$R_1$ Personalized**: `phase3.5-personalized` (Phase 3.5 bounded personalization without behavioral adjustments)
- **$R_2$ Behavioral**: `phase3.7-v1` (Full Phase 3.5 personalization + Phase 3.6 learned behavioral adjustments)

The evaluation endpoint automatically groups snapshots by `ranking_version` and outputs an independent `ranking_comparison` map, allowing direct historical verification of whether behavioral signals improve Precision@K, NDCG@K, or Save Rate.

---

## 7. API Specification

All endpoints enforce strict `X-User-ID` header validation: researchers cannot access another researcher's recommendation history or evaluation.

### 1. List Recommendation History
`GET /api/v1/researchers/{researcher_id}/recommendation-history`
- **Query Parameters**: `limit` (default 20), `offset` (default 0), `ranking_version` (optional), `from_date` (optional), `to_date` (optional).
- **Response**: `RecommendationHistoryListResponse` (snapshots list, total, limit, offset).

### 2. Get Snapshot Detail
`GET /api/v1/researchers/{researcher_id}/recommendation-history/{snapshot_id}`
- **Response**: `RecommendationSnapshotResponseSchema` (snapshot metadata, ordered items with original scores, risk level, deadline status, and active user feedback).

### 3. Recommendation Evaluation
`GET /api/v1/researchers/{researcher_id}/recommendation-evaluation`
- **Query Parameters**: `ranking_version` (optional), `from_date` (optional), `to_date` (optional), `include_comparison` (default true).
- **Response**: `RecommendationEvaluationResponse` (sample size, data status, primary metrics, algorithm version comparison).

---

## 8. Frontend Implementation

Integrated cleanly into the Next.js 15 App Router at `frontend/components/researcher/RecommendationHistoryView.tsx`:
- **Offline Quality Dashboard**: Displays data sufficiency badge, Precision@5/10, Recall@10, NDCG@10, Hit Rate@5, Save Rate, Engagement Rate, and Dismissal Rate.
- **Algorithm Comparison Cards**: Side-by-side cards comparing $R_0$, $R_1$, and $R_2$.
- **Snapshot Timeline**: Chronological table showing timestamp, ranking version, candidate counts, and top recommendations preview.
- **Inspection Modal**: Opens point-in-time recommendation ranking with original score breakdown and feedback badges.

---

## 9. Boundaries & Limitations

1. **No Online Learning**: Phase 3.7 does not alter ranking weights automatically based on evaluation results.
2. **No Collaborative Filtering**: Evaluation and history are isolated strictly per researcher.
3. **No Machine Learning Rerankers**: All metrics are calculated deterministically via standard Information Retrieval formulations.
4. **Phase 3.8 / 3.9 Deferred**: Deep personalization explainability UI (3.8) and automated ablation hardening (3.9) remain separate future phases.
