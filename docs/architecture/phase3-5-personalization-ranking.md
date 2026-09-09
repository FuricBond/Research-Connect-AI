# Phase 3.5 — Personalization Ranking Layer Architecture

## 1. Executive Summary

**Phase 3.5: Personalization Ranking Layer** introduces the first point where researcher-specific personalization is allowed to influence the ordering of academic and research opportunities.

The overarching recommendation architecture operates as a strict pipeline:

```text
User Query / Discovery
       ↓
Phase 2.2 Ingestion & Knowledge
       ↓
Phase 2.3 Research Understanding & Embeddings
       ↓
Phase 2.4 Semantic Matching
       ↓
Phase 2.5 Base Recommendation Ranking (HybridRanker / Base Relevance)
       ↓
Phase 2.6 Trust / Risk Assessment (Authoritative Gate)
       ↓
Phase 2.7 Deadline Intelligence (Authoritative Lifecycle)
       ↓
Phase 3.4 Personalized Candidate Generation (Unranked Pool with Provenance)
       ↓
PHASE 3.5 PERSONALIZATION RANKING LAYER (Deterministic Bounded Re-ranking)
       ↓
Personalized Ranked Results
```

### The Core Invariant
> **Personalization may reorder relevant candidates, but it must never manufacture relevance or override safety, trust, or deadline constraints.**

Relevance dominates large score differentials; personalization resolves smaller differentials among similarly relevant opportunities.

---

## 2. Core Architecture & Mathematical Model

The personalization ranking layer wraps the Phase 2 base ranker without altering its internal logic:

$$\text{FinalScore}(C) = \text{BaseRelevanceScore}(C) + \Delta_{\text{personalization}}(C)$$

Where:
- $\text{BaseRelevanceScore}(C) \in [0.0, 1.0]$: Established by Phase 2 ranking or semantic matching.
- $\Delta_{\text{personalization}}(C) \in [0.0, \text{MAX\_PERSONALIZATION\_CONTRIBUTION}]$: Bounded non-negative adjustment.
- $\text{MAX\_PERSONALIZATION\_CONTRIBUTION} = 0.15$: Hard conservative upper bound (15%).

### 2.1 Signal Weighting Hierarchy

Personalization signals derived from Phases 3.1–3.4 are combined through an explainable hierarchy:

| Signal Component | Category / Origin | Weight ($w_i$) | Rationale |
| :--- | :--- | :--- | :--- |
| **Explicit Preference Match** | Phase 3.3 (`source="EXPLICIT"`) | $0.40$ | Highest intent: researcher explicitly asked for this type, mode, or topic |
| **Scholarly Expertise Match** | Phase 3.2 (`PRIMARY_EXPERTISE`, `SECONDARY_EXPERTISE`) | $0.25$ | High confidence: substantiated by researcher's historical publication record |
| **Inferred Preference Match** | Phase 3.3 (`source="INFERRED"`, platform saves) | $0.15$ | Moderate intent: inferred from behavior, subject to confidence threshold |
| **Profile Keyword / Target Match** | Phase 3.1 (`ResearchProfileModel.keywords`, target types) | $0.10$ | Contextual baseline: stated institutional and academic interests |
| **Candidate Retrieval Provenance** | Phase 3.4 (`retrieval_channels`, `sources`) | $0.10$ | Multi-channel discovery confidence bonus |

$$\text{RawPersonalizationScore}(C) = \sum_{i} w_i \cdot s_i(C) \in [0.0, 1.0]$$

Where:
- $s_{\text{explicit}} = \max_{\text{matches}} (\text{strength} \times \text{confidence} \times \text{recency})$
- $s_{\text{inferred}} = \max_{\text{matches}} (\text{strength} \times \text{confidence} \times \text{recency})$
- $s_{\text{expertise}} = \max_{\text{matches}} (m_{\text{class}} \times \text{strength} \times \text{confidence} \times \text{recency})$, with $m_{\text{PRIMARY}}=1.0$, $m_{\text{SECONDARY}}=0.75$, $m_{\text{EMERGING}}=0.50$, $m_{\text{PAST}}=0.30$
- $s_{\text{profile}} = \text{overlap\_ratio}(\text{opportunity\_topics}, \text{profile\_keywords})$
- $s_{\text{provenance}} = \min(1.0, 0.2 \times |\text{sources}| + 0.1 \times |\text{channels}|)$

### 2.2 Relevance Guardrail & Damping

To ensure that personalization **never manufactures relevance** for unrelated opportunities:

$$\text{DampingFactor}(C) = \begin{cases} 1.0 & \text{if } \text{BaseScore}(C) \ge 0.50 \\ \frac{\text{BaseScore}(C)}{0.50} & \text{if } \text{BaseScore}(C) < 0.50 \end{cases}$$

$$\Delta_{\text{personalization}}(C) = \min(0.15, \text{RawPersonalizationScore}(C) \times 0.15 \times \text{DampingFactor}(C))$$

**Proof of Relevance Dominance:**
- Maximum possible personalization boost is $0.15$.
- If $\text{BaseScore}(A) - \text{BaseScore}(B) > 0.15$, Candidate $B$ can *never* surpass Candidate $A$, regardless of perfect personalization ($s=1.0$).
- If Candidate $B$ has low base relevance ($\text{BaseScore}(B) = 0.20$), its effective maximum boost is clamped to $0.15 \times (0.20 / 0.50) = 0.060$, resulting in a final score of $0.260$.

---

## 3. Authoritative Safety & Deadline Invariants

### 3.1 Phase 2.6 Trust & Risk Dominance
- **High Risk & Predatory Suppression**: If an opportunity is flagged as `is_predatory_flag = True` or has `risk_level == "HIGH_RISK"` or `risk_score >= 0.70`, the personalization adjustment is strictly forced to **$0.00$**.
- **No Override**: Personalization can never downgrade risk severity, bypass risk flags, or promote predatory venues.

### 3.2 Phase 2.7 Deadline Intelligence Dominance
- **Expired Opportunity Exclusion**: Expired opportunities (`days_remaining < 0` or status `EXPIRED`) remain strictly excluded from ranking pools.
- **Approaching Urgency Weight**: Opportunities closing within active submission windows retain appropriate Phase 2.7 urgency indicators.

### 3.3 Deterministic Multi-Key Tie-Breaking
Ranking order is 100% deterministic and contains zero randomness, database-order dependency, or unstable hash iterations:
1. `final_score` (Descending)
2. `base_relevance_score` (Descending)
3. `urgency_score` (Descending)
4. `opportunity_id` string representation (Ascending lexicographical tie-break)

---

## 4. Cold-Start Behavior

The ranking layer operates cleanly across all levels of cold-start:

1. **Profile-Only Cold Start**: Evaluates profile keywords and target opportunity types ($w_{\text{profile}}=0.10$).
2. **Interests/Expertise-Only Cold Start**: Evaluates scholarly publications and extracted research domains ($w_{\text{expertise}}=0.25$).
3. **Explicit-Preferences-Only Cold Start**: Evaluates declared categories and delivery modes ($w_{\text{explicit}}=0.40$).
4. **Complete Cold Start (Zero History & Data)**: Zero personalization adjustment ($\Delta = 0.00$). The ranker outputs pure Phase 2 base relevance ($R_0$) without errors or empty result sets.

---

## 5. API Specification

### Endpoint: `GET /api/v1/researchers/{researcher_id}/personalized-recommendations`

#### Query Parameters:
- `limit` (int, default=20, max=100): Number of ranked recommendations to return.
- `enable_personalization` (bool, default=true): When false, returns pure Phase 2 base ranking ($R_0$) for ablation testing.
- `min_relevance_floor` (float, default=0.20): Minimum base relevance threshold.
- `exclude_predatory` (bool, default=true): Exclude predatory opportunities.
- `max_risk_level` (str, default="HIGH_RISK"): Maximum allowable risk level.

#### Header:
- `X-User-ID`: Enforces profile ownership (403 Forbidden on mismatch).

#### Response Schema: `PersonalizedRankingResponse`
```json
{
  "researcher_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "ranked_count": 10,
  "enable_personalization": true,
  "max_personalization_contribution": 0.15,
  "recommendations": [
    {
      "opportunity_id": "09b96c29-a46a-4828-baad-5135ccbd1cac",
      "rank": 1,
      "base_rank": 2,
      "rank_delta": 1,
      "final_score": 0.825,
      "base_relevance_score": 0.700,
      "personalization_score": 0.833,
      "personalization_adjustment": 0.125,
      "score_breakdown": {
        "explicit_preference_score": 1.0,
        "inferred_preference_score": 0.0,
        "expertise_match_score": 0.75,
        "profile_match_score": 0.50,
        "provenance_score": 0.30,
        "raw_personalization_score": 0.833,
        "relevance_damping": 1.0
      },
      "matched_signals": {
        "matched_preferences": ["OPPORTUNITY_TYPE:CONFERENCE", "DELIVERY_MODE:HYBRID"],
        "matched_expertise": ["Machine Learning"],
        "matched_topics": ["Machine Learning", "Neural Networks"],
        "matched_types": ["CONFERENCE"]
      },
      "provenance": { ... },
      "opportunity": { ... }
    }
  ],
  "ablation_summary": {
    "total_candidates": 10,
    "reordered_count": 3,
    "avg_personalization_adjustment": 0.072,
    "max_personalization_adjustment": 0.145,
    "max_rank_gain": 2,
    "max_rank_loss": -1,
    "invariants_verified": true
  }
}
```

---

## 6. Performance & Database Query Guarantees

- **Zero N+1 Queries**: All candidate generation, profile, preferences, and interests are loaded in bounded batch queries ($O(1)$ database trips).
- **In-Memory Computation**: All scoring, signal matching, damping, clamping, and tie-breaking execute in-memory via Python vectorization and dataclasses.
- **Empirical Query Budget**:
  - Profile lookup: 1 query
  - Preferences lookup: 1 query
  - Interests lookup: 1 query
  - Phase 3.4 candidate generation: 5–8 queries
  - Opportunity hydration batch: 1 query
  - Total queries for 30+ candidates: $\le 13$ queries (independent of candidate pool size).

---

## 7. Verification & Empirical Evaluation

The Phase 3.5 suite includes 18 unit, integration, and ablation tests in `backend/tests/test_personalization_ranking.py`:

| Evaluation Scenario | R0 (Phase 2 Base) | R1 (Phase 3.5 Personalization) | Verification Outcome |
| :--- | :--- | :--- | :--- |
| **Large Relevance Gap** ($0.90$ vs $0.60$) | Rank 1: A ($0.90$), Rank 2: B ($0.60$) | Rank 1: A ($0.90$), Rank 2: B ($0.75$) | **Relevance Invariant Preserved**: Large gap not inverted |
| **Close Base Relevance** ($0.70$ vs $0.68$) | Rank 1: A ($0.70$), Rank 2: B ($0.68$) | Rank 1: B ($0.80$), Rank 2: A ($0.70$) | **Legitimate Reordering**: Personalization resolves small delta |
| **Explicit vs Inferred Preference** | Both match ($0.70$ base) | Explicit match ($+0.060$) beats Inferred ($+0.022$) | **Signal Hierarchy Verified**: Explicit > Inferred |
| **Primary vs Secondary Expertise** | Both match ($0.70$ base) | Primary ($1.00$ mult) beats Secondary ($0.75$ mult) | **Scholarly Hierarchy Verified**: Primary > Secondary |
| **Personalization Cap** | Arbitrary high weights ($s=10.0$) | $\Delta \le 0.150$ | **Hard Cap Enforced**: Adjustment never exceeds $0.15$ |
| **Relevance Damping** | Low base ($0.20$), max signals | $\Delta = 0.060$, Final $= 0.260$ | **Relevance Floor Enforced**: Irrelevant candidate remains low |
| **High Risk Candidate** | High base ($0.80$), High Risk | $\Delta = 0.000$, Final $= 0.800$ | **Safety Enforced**: Zero personalization boost |
| **Expired Opportunity** | Perfect personalization | Candidate excluded by Phase 3.4 / Phase 2.7 | **Deadline Enforced**: Zero resurrection |
| **Cold Start** | Zero profile, interests, prefs | $\Delta = 0.000$, Identical to $R_0$ | **Clean Fallback**: Pure Phase 2 output |
| **Determinism (10 Consecutive Runs)** | Arbitrary candidate set | Identical ordering in all 10 runs | **100% Deterministic Ordering** |

---

## 8. Known Scope Boundaries & Next Phases

- **Phase 3.5 does NOT implement ML ranking**: No Learning-to-Rank (LTR), XGBoost rankers, or neural reranking. Logic is deterministic and explainable.
- **Phase 3.5 does NOT implement collaborative filtering**: No user-user or item-item interaction matrices.
- **Phase 3.5 does NOT mutate historical interactions**: Feedback loops belong to **Phase 3.6**.
- **Phase 3.5 does NOT build final user-facing explanation UI**: Full UX belongs to **Phase 3.8**.
