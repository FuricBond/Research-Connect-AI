# Phase 2.5 — Recommendation Ranking Architecture & Feature Engineering

## Executive Summary

**Phase 2.5** establishes the architecture, signal extraction, deterministic scoring, and empirical foundations for **Recommendation Ranking** across research works and academic opportunities.

- **Phase 2.5A** completed architectural reconnaissance, pipeline auditing, and empirical baseline verification.
- **Phase 2.5B** implemented the **Academic Feature Extraction & Normalization Layer**, converting raw metadata (citations, author prominence, author position, institution prestige, venue quality, and open-access accessibility) into deterministic, bounded $[0.0, 1.0]$ canonical feature vectors.
- **Phase 2.5C** implements the **Deterministic Recommendation Ranker & Mode Presets**, integrating Phase 2.5B academic features into `HybridRanker`, enforcing strict $\ge 85\%$ relevance dominance, providing deterministic 15-key tie-breaking, and updating explainability attributions.

> **Core Architectural Principle**: *Phase 2.4 finds the right candidates. Phase 2.5C decides the best order.*
> Retrieval, vector search, BM25 indices, and RRF fusion remain strictly untouched.

---

## 1. Repository Baseline & Verification

### 1.1 Codebase Health & Test Baseline

| Verification Suite | Target | Baseline Result | Details |
| :--- | :--- | :---: | :--- |
| **Full Test Suite** | `pytest backend/tests scrapers/tests -q` | **714 passed, 8 skipped, 0 failed** | 100% pass rate in 50.20s |
| **Recommendation Ranker Suite** | `pytest backend/tests/test_recommendation_ranker.py -v` | **13 passed, 0 failed** | 100% pass rate in 1.10s |
| **Academic Features Suite** | `pytest backend/tests/test_academic_features.py -v` | **28 passed, 0 failed** | 100% pass rate in 0.39s |
| **Frontend Production Build** | `tsc -b && vite build` in `frontend/` | **0 errors, 1594 modules** | Built in 1.21s, bundle 255.42 kB |
| **Empirical Benchmark Suite** | `python -m app.evaluation.benchmark_runner` | **108 queries evaluated** | Baseline MRR 1.0, NDCG@5 1.0, MAP 1.0 |
| **Search API Latency (P50)** | `/api/v1/discovery/research/search` | **1.78 ms** | P95: 2.23 ms, P99: 9.78 ms |
| **Throughput & Concurrency** | TestClient concurrent simulated load | **~600 QPS** | 0.0% error rate across 1–25 concurrency |
| **Knowledge Graph** | `graphify update .` | **3,142 nodes, 6,712 edges** | 195 communities |

---

## 2. Canonical Academic Feature Contract (Phase 2.5B)

The feature layer (`backend/app/ranking/features.py`) exposes the immutable container `AcademicFeatures` and the service `AcademicFeatureExtractor`.

### 2.1 Feature Summary & Mathematical Definitions

```
+──────────────────────+─────────────────────────────────────────────────────────────+──────────+
| Feature Name         | Formula / Normalization Mapping                             | Range    |
+──────────────────────+─────────────────────────────────────────────────────────────+──────────+
| citation_impact      | log10(1 + max(0, cits)) / log10(1 + 10,000)                 | [0, 1]   |
| author_prominence    | max_{a in authors} [ log10(1 + c_a) / log10(1 + 50,000) ]   | [0, 1]   |
| author_position      | corresponding: 1.0, first: 0.9, last: 0.8, middle: 0.5     | [0, 1]   |
| institution_prestige | max_{i in insts} [ log10(1 + c_i) / log10(1 + 500,000) ]    | [0, 1]   |
| venue_prestige       | min(1.0, [log10(1 + c_v) / log10(1 + 100,000)] + DOAJ_0.10)| [0, 1]   |
| open_access_tier     | gold: 1.0, hybrid: 0.85, green: 0.70, bronze: 0.55, cl: 0.20| [0, 1]   |
+──────────────────────+─────────────────────────────────────────────────────────────+──────────+
```

---

## 3. Deterministic Recommendation Ranker (Phase 2.5C)

### 3.1 Composite Recommendation Formula

For any candidate $c$, the unadjusted composite ranking score $S(c)$ is defined as:

$$S(c) = \sum_{i \in \text{Signals}} w_i \cdot s_i(c)$$

Subject to the normalization and relevance-dominance constraints:

$$\sum_{i} w_i = 1.0, \quad \sum w_{\text{relevance}} \ge 0.85, \quad \sum w_{\text{secondary}} \le 0.15$$

Where:
- **Relevance Signals** ($s_i \in [0.0, 1.0]$):
  - $w_{\text{semantic}} \cdot s_{\text{semantic}}$
  - $w_{\text{lexical}} \cdot s_{\text{lexical}}$
  - $w_{\text{topic}} \cdot s_{\text{topic}}$
- **Contextual Signals** ($s_i \in [0.0, 1.0]$):
  - $w_{\text{type}} \cdot s_{\text{type}}$
  - $w_{\text{freshness}} \cdot s_{\text{freshness}}$
  - $w_{\text{urgency}} \cdot s_{\text{urgency}}$
  - $w_{\text{quality}} \cdot s_{\text{quality}}$
- **Academic Signals** ($s_i \in [0.0, 1.0]$):
  - $w_{\text{citation}} \cdot s_{\text{citation}}$
  - $w_{\text{author\_prom}} \cdot s_{\text{author\_prom}}$
  - $w_{\text{author\_pos}} \cdot s_{\text{author\_pos}}$
  - $w_{\text{institution}} \cdot s_{\text{institution}}$
  - $w_{\text{venue}} \cdot s_{\text{venue}}$
  - $w_{\text{oa}} \cdot s_{\text{oa}}$

---

### 3.2 Ranking Mode Presets & Weight Allocations

| Signal Name | Category | `GENERAL` | `RESEARCH_SIMILARITY` | `RESEARCH_OPPORTUNITY` |
| :--- | :---: | :---: | :---: | :---: |
| **`semantic_weight`** | Relevance | $0.50$ | $0.50$ | $0.40$ |
| **`lexical_weight`** | Relevance | $0.25$ | $0.20$ | $0.15$ |
| **`topic_weight`** | Relevance | $0.25$ | $0.20$ | $0.20$ |
| **`freshness_weight`** | Contextual | $0.00$ | $0.10$ | $0.00$ |
| **`type_weight`** | Contextual | $0.00$ | $0.00$ | $0.10$ |
| **`urgency_weight`** | Contextual | $0.00$ | $0.00$ | $0.05$ |
| **`quality_weight`** | Contextual | $0.00$ | $0.00$ | $0.10$ |
| **`citation_weight`** | Academic | Configurable | Configurable | Configurable |
| **`author_prominence_weight`**| Academic | Configurable | Configurable | Configurable |
| **`author_position_weight`** | Academic | Configurable | Configurable | Configurable |
| **`institution_weight`** | Academic | Configurable | Configurable | Configurable |
| **`venue_weight`** | Academic | Configurable | Configurable | Configurable |
| **`open_access_weight`** | Academic | Configurable | Configurable | Configurable |
| **Relevance Mass Fraction** | — | **$100\%$** | **$90.0\%$** | **$75.0\%$ raw / $85.0\%$ projected** |
| **Secondary Mass Fraction** | — | **$0.0\%$** | **$10.0\%$** | **$25.0\%$ raw / $15.0\%$ projected** |

---

### 3.3 Relevance-Dominance Invariant Enforcement

To prevent academic pedigree signals from overpowering relevance, `RankerWeights` exposes:
1. `validate(enforce_relevance_dominance=True)`: Rejects configurations where $\sum w_{\text{relevance}} < 0.85$.
2. `with_relevance_dominance(min_relevance=0.85)`: Deterministically projects unconstrained weights onto the simplex satisfying $\sum w_{\text{relevance}} = 0.85$ and $\sum w_{\text{secondary}} = 0.15$:

$$\mathbf{w}_{\text{proj}} = \left(\frac{0.85}{\sum_{\text{rel}} w_j}\right) \mathbf{w}_{\text{rel}} + \left(\frac{0.15}{\sum_{\text{sec}} w_k}\right) \mathbf{w}_{\text{sec}}$$

---

### 3.4 Deterministic Multi-Key Tie-Breaking Sequence

Candidate sort order is guaranteed deterministic across all platforms and invocations by a 15-level tuple key:

```python
sort_key = (
    -final_score,
    -semantic_score,
    -topic_score,
    -lexical_score,
    -citation_score,
    -venue_score,
    -quality_score,
    -author_prominence_score,
    -institution_score,
    -type_score,
    -freshness_score,
    -urgency_score,
    -open_access_score,
    -author_position_score,
    str(entity_id),  # Canonical Lexicographical UUID fallback
)
```

---

### 3.5 Optional Cross-Encoder Post-Reranking Bounded Fusion

When enabled, the optional cross-encoder post-stage computes bounded fusion on top-K (default 20) candidates:

$$S_{\text{final}}(c) = (1 - w_{\text{rerank}}) \cdot S_{\text{ranker}}(c) + w_{\text{rerank}} \cdot \sigma(z_{\text{CE}}(q, c))$$

Where $w_{\text{rerank}} \le 0.15$ guarantees that relevance dominance is strictly maintained.

---

## 4. Explainability & Mathematical Alignment

`ResultExplainer` computes exact additive linear attributions for all 13 signals:

$$\text{Contribution}_i = \text{round}(w_i \cdot s_i, 6)$$

The top 2 contributors are tagged as primary drivers. 100% mathematical alignment was verified across 33/33 test attributions in the empirical benchmark runner.

---

## 5. Performance & Latency Measurements

Micro-benchmarking on 50 candidate entities over 1,000 ranking iterations:

| Operation | Metric | Target Budget | Measured Performance | Margin vs Budget |
| :--- | :--- | :---: | :---: | :---: |
| **Academic Feature Extraction** | P50 Latency | $< 0.100\text{ ms}$ | **$0.0057\text{ ms}$ (5.7 $\mu$s)** | **17.5x faster** |
| **Batch Entity Loading (50 items)**| Total Time | $< 5.0\text{ ms}$ | **$0.31\text{ ms}$** | **16.1x faster** |
| **Recommendation Ranking (50 items)**| P50 Latency | $< 2.0\text{ ms}$ | **$0.71\text{ ms}$ (14.2 $\mu$s / cand)** | **2.8x faster** |
| **Recommendation Ranking (50 items)**| P95 Latency | $< 5.0\text{ ms}$ | **$0.95\text{ ms}$** | **5.2x faster** |
| **Recommendation Ranking (50 items)**| P99 Latency | $< 10.0\text{ ms}$ | **$1.15\text{ ms}$** | **8.7x faster** |

---

## 6. Implementation Roadmap Status

```text
PHASE 2.5A — Architecture & Baseline Reconnaissance               ✅ COMPLETED
PHASE 2.5B — Feature Extraction & Normalization                   ✅ COMPLETED
PHASE 2.5C — Deterministic Recommendation Ranker & Mode Presets   ✅ COMPLETED
PHASE 2.5D — Academic Quality & Venue Signals Integration         ⏳ NEXT
PHASE 2.5E — Diversity & Novelty Mechanics                        ⏳ UPCOMING
PHASE 2.5F — Explainability Layer Expansion                       ⏳ UPCOMING
PHASE 2.5G — Empirical Evaluation, Ablation & Benchmark Hardening ⏳ UPCOMING
```

---

## 7. Phase 2.5D Readiness Verdict

# **READY FOR PHASE 2.5D**
