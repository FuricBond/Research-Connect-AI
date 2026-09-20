# Phase 5.7: Personalization Evaluation, Contextual Adaptation & Recommendation Quality Loop

## 1. Executive Summary & Objective

**Phase 5.7** establishes the **personalization quality evaluation and contextual adaptation layer** in Research Connect AI. It directly answers the critical operational and algorithmic questions:
> *"Is personalization actually improving the usefulness of recommendations for this researcher, and under what contexts does it perform well or poorly?"*

Building upon:
- **Phase 5.1**: Researcher Preferences Foundation (explicit 3-state preferences: `PREFERRED`, `NEUTRAL`, `EXCLUDED`)
- **Phase 5.2**: Preference Interpretation (deterministic rule-based attribute matching)
- **Phase 5.3**: Personalization-Aware Opportunity Scoring & Explainability
- **Phase 5.4**: Researcher Feedback & Interaction Signal Foundation (append-only interaction logging)
- **Phase 5.5**: Adaptive Preference Signal Aggregation & Personalization Bridge (bounded behavioral signals)
- **Phase 5.6**: Adaptive Personalization Calibration & Recommendation Feedback Loop (closed-loop signal-level calibration)

Phase 5.7 closes the higher-level quality loop by deterministically measuring observed recommendation lift, partitioning behavioral performance across contextual facets (opportunity type, deadline urgency, risk tier, relevance tier, academic status), applying bounded contextual adaptation modifiers ($\Delta_{\text{context}} \in [-0.03, +0.03]$), and exposing comprehensive quality metrics, diversity, novelty, and deterministic explanations to both researchers and administrative interfaces.

---

## 2. Core Architecture & Strict Invariants

```
                                  +---------------------------------------+
                                  | Phase 5.4: Researcher Interactions    |
                                  | (APPLIED, SAVED, DISMISSED, etc.)     |
                                  +-------------------+-------------------+
                                                      |
                                                      v
+-----------------------------------+     +-----------------------------------+
| Phase 5.5: Recommendation History | --> | Phase 5.6: Attribution Engine     |
| (Snapshots, Candidates, Items)    |     | (14-day causal attribution window)|
+-----------------------------------+     +-----------------+-----------------+
                                                            |
                                                            v
                                          +-----------------------------------+
                                          | Phase 5.7: Quality Engine         |
                                          | - Observed Personalization Lift   |
                                          | - Contextual Partitioning         |
                                          | - Hierarchical Fallback (L1->L4)  |
                                          | - Diversity & Novelty Metrics     |
                                          | - Bounded Modifier [-0.03, +0.03] |
                                          +-----------------+-----------------+
                                                            |
                                                            v
+-----------------------------------+     +-----------------------------------+
| Phase 5.1: Explicit Preferences   |     | Phase 5.7: Context-Adapted Scorer |
| (Authoritative Precedence)        | --> | (Delta_context + Delta_calib      |
+-----------------------------------+     |  Clamped to [-0.05, +0.05];       |
                                          |  Total adaptive <= 0.10)          |
                                          +-----------------------------------+
```

### Strict Scope Boundaries & Precedence Hierarchy
1. **Zero ML / Zero Black-Box Models**: No neural networks, vector embeddings, collaborative filtering, online learning, or LLM calls are used. All metrics, contextual partitions, and adaptations are computed using 100% deterministic, closed-form mathematics and rule-based logic.
2. **Precedence Hierarchy**:
   $$\text{Core Relevance } (\ge 0.85) > \text{Explicit Preferences} > \text{Adaptive Signals } (\pm 0.10) > \text{Calibration } (\pm 0.05) > \text{Contextual Adaptation } (\pm 0.03)$$
3. **Explicit Preference Dominance**:
   - Explicit `EXCLUDED` preferences unconditionally force the final score to `0.0`. Contextual adaptation or calibration can never revive an excluded opportunity.
   - Explicit `PREFERRED` preferences with a base score $\ge 0.50$ are protected from negative suppression below $0.50$ by negative calibration or contextual modifiers.
4. **Bounded Adaptation & Clamping**:
   - Contextual adaptation modifier $\Delta_{\text{context}}$ is strictly clamped to $[-0.03, +0.03]$.
   - The combined calibration and contextual modifier ($\Delta_{\text{calib}} + \Delta_{\text{context}}$) is clamped to $[-0.05, +0.05]$.
   - The total combined adaptive contribution (adaptive signal + calibration + contextual adaptation) is clamped to $[-0.10, +0.10]$.
5. **Observed Personalization Lift**:
   - Evaluates empirical differences between personalized and baseline recommendations without claiming causal proof or counterfactual certainty.
6. **Anti-Feedback-Loop Safeguards**:
   - Runaway reinforcement is prevented by capping outcomes at most **1 primary feedback outcome per opportunity per context per evaluation window**.
7. **Overreaction Protection**:
   - Sample sizes $N < 3$ strictly yield `INSUFFICIENT_DATA` with a contextual modifier of `0.0`.
8. **Multi-Tenant Isolation**:
   - Evaluations and contextual adaptations are strictly partitioned by `profile_id`. A researcher can never query, recompute, or influence another researcher's quality metrics or adaptations.

---

## 3. Mathematical Specification & Formulation

### 3.1. Engagement and Feedback Rates
For a set of evaluated recommendations $\mathcal{R}$ presented within an evaluation window (default 30 days) and attributed interaction outcomes $\mathcal{O}$:
- **Observed Engagement Rate**:
  $$\text{Rate}_{\text{eng}} = \frac{|\{r \in \mathcal{R} \mid \exists o \in \mathcal{O} \text{ on } r\}|}{|\mathcal{R}|}$$
- **Observed Positive Rate**:
  $$\text{Rate}_{\text{pos}} = \frac{|\{o \in \mathcal{O} \mid \text{outcome}(o) \in \{\text{STRONG\_POS}, \text{MOD\_POS}, \text{WEAK\_POS}\}\}|}{|\mathcal{R}|}$$
- **Observed Negative Rate**:
  $$\text{Rate}_{\text{neg}} = \frac{|\{o \in \mathcal{O} \mid \text{outcome}(o) == \text{NEGATIVE}\}|}{|\mathcal{R}|}$$

### 3.2. Observed Personalization Lift
Recommendations are partitioned into:
- $\mathcal{R}_{\text{personalized}}$: items where $|\text{personalization\_score}| > 0.0$ or $|\text{behavioral\_adjustment}| > 0.0$.
- $\mathcal{R}_{\text{baseline}}$: items without personalization adjustments.

The observed empirical lift is defined as:
$$\text{Lift}_{\text{obs}} = \text{Rate}_{\text{personalized}} - \text{Rate}_{\text{baseline}}$$
clamped strictly to $[-1.0, +1.0]$. This is an observational metric comparing cohorts, explicitly avoiding causal overclaims.

### 3.3. Contextual Partitioning Dimensions
Interactions and recommendations are partitioned along 5 primary contextual dimensions:
1. `OPPORTUNITY_TYPE`: `GRANT`, `FELLOWSHIP`, `CALL_FOR_PAPERS`, `CONFERENCE`, `JOURNAL`, `WORKSHOP`, `OTHER`.
2. `DEADLINE_HORIZON`:
   - `URGENT`: $< 14$ days
   - `MEDIUM`: $14 - 60$ days
   - `FAR`: $> 60$ days
   - `UNKNOWN`: No deadline specified
3. `RISK_TIER`:
   - `HIGH`: Risk score $\ge 0.70$
   - `MEDIUM`: Risk score $0.30 - 0.69$
   - `LOW`: Risk score $< 0.30$
4. `RELEVANCE_TIER`:
   - `HIGH`: Base relevance $\ge 0.70$
   - `MEDIUM`: Base relevance $0.40 - 0.69$
   - `LOW`: Base relevance $< 0.40$
5. `ACADEMIC_STATUS`: Researcher's career stage (e.g. `EARLY_CAREER`, `MID_CAREER`, `SENIOR`, `FACULTY`, `POSTDOC`, `STUDENT`).

### 3.4. Hierarchical Context Fallback
When adapting a signal in a specific context:
- **Level 1 (Exact Context)**: Matches researcher + signal + exact context. Requires $N \ge 3$ interactions and confidence $\ge 0.30$.
- **Level 2 (Broad Context)**: If Level 1 has insufficient data, falls back to signal-level calibration modifier ($\Delta_{\text{calib}}$).
- **Level 3 (Signal Level)**: If signal-level calibration has insufficient data, falls back to raw adaptive signal modifier.
- **Level 4 (Neutral Fallback)**: If no signal data exists, yields $\Delta_{\text{context}} = 0.0$.

### 3.5. Bounded Contextual Modifier
For a context with sample size $N$, positive count $N_{\text{pos}}$, negative count $N_{\text{neg}}$, and context lift $\text{Lift}_{\text{ctx}}$:
$$\Delta_{\text{context}} = \operatorname{sign}(\text{Lift}_{\text{ctx}}) \cdot \min\left(|\text{Lift}_{\text{ctx}}| \cdot \text{Confidence}_{\text{ctx}}, 0.03\right)$$
where:
$$\text{Confidence}_{\text{ctx}} = \left(1 - \exp\left(-\frac{N}{4.0}\right)\right) \cdot \left(1.0 - \frac{\min(N_{\text{pos}}, N_{\text{neg}})}{\max(N_{\text{pos}}, N_{\text{neg}}) + 10^{-4}}\right)$$
If $N < 3$, $\Delta_{\text{context}} \equiv 0.0$.

### 3.6. Diversity and Novelty Metrics
- **Recommendation Diversity Score**: Shannon entropy over opportunity types and delivery modes normalized by the maximum theoretical entropy:
  $$H_{\text{norm}} = \frac{-\sum_{i=1}^K p_i \ln p_i}{\ln K}$$
- **Novelty Rate**: Fraction of recommended opportunities that have not been previously presented to the researcher in earlier recommendation windows:
  $$\text{Rate}_{\text{novel}} = \frac{|\{r \in \mathcal{R} \mid r \notin \mathcal{R}_{\text{prior}}\}|}{|\mathcal{R}|}$$

---

## 4. Database Schema Specifications

### 4.1. Table: `personalization_quality_evaluations`
```sql
CREATE TABLE personalization_quality_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES research_profiles(id) ON DELETE CASCADE,
    evaluation_period_days DOUBLE PRECISION NOT NULL DEFAULT 30.0,
    recommendations_evaluated_count INTEGER NOT NULL DEFAULT 0,
    attributed_interactions_count INTEGER NOT NULL DEFAULT 0,
    positive_outcomes_count INTEGER NOT NULL DEFAULT 0,
    negative_outcomes_count INTEGER NOT NULL DEFAULT 0,
    neutral_outcomes_count INTEGER NOT NULL DEFAULT 0,
    observed_engagement_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observed_positive_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observed_negative_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    baseline_engagement_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    baseline_positive_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    observed_personalization_lift DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    evaluation_state VARCHAR(50) NOT NULL DEFAULT 'INSUFFICIENT_DATA',
    diversity_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    novelty_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    contextual_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    deterministic_explanation TEXT NOT NULL,
    algorithm_version VARCHAR(50) NOT NULL DEFAULT '5.7.1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.2. Table: `personalization_contextual_adaptations`
```sql
CREATE TABLE personalization_contextual_adaptations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES research_profiles(id) ON DELETE CASCADE,
    dimension VARCHAR(50) NOT NULL,
    signal_value VARCHAR(255) NOT NULL,
    context_dimension VARCHAR(50) NOT NULL,
    context_value VARCHAR(255) NOT NULL,
    sample_size INTEGER NOT NULL DEFAULT 0,
    positive_count INTEGER NOT NULL DEFAULT 0,
    negative_count INTEGER NOT NULL DEFAULT 0,
    observed_lift DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    contextual_modifier DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    adaptation_state VARCHAR(50) NOT NULL DEFAULT 'INSUFFICIENT_DATA',
    fallback_level VARCHAR(50) NOT NULL DEFAULT 'NEUTRAL',
    explanation TEXT NOT NULL,
    algorithm_version VARCHAR(50) NOT NULL DEFAULT '5.7.1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 5. REST API Specifications

| Method | Endpoint | Summary | Response Model | Auth |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/researchers/{id}/personalization/quality` | Get researcher personalization quality & lift | `PersonalizationQualityResponse` | `X-User-ID` |
| `GET` | `/api/v1/researchers/{id}/personalization/quality/contexts` | Get contextual adaptation breakdowns | `ContextualAdaptationsResponse` | `X-User-ID` |
| `GET` | `/api/v1/researchers/{id}/personalization/quality/signals` | Get signal-level quality breakdowns | `SignalQualityResponse` | `X-User-ID` |
| `POST` | `/api/v1/researchers/{id}/personalization/quality/recompute` | Trigger on-demand quality recomputation | `PersonalizationQualityResponse` | `X-User-ID` |

---

## 6. Frontend Integration

### 6.1. Component: `PersonalizationQualityCard.tsx`
Located in `frontend/components/personalization/PersonalizationQualityCard.tsx` and embedded in `frontend/components/researcher/UnifiedResearchIntelligenceView.tsx` under Section 2.7.
Features:
- **Observed Lift Hero Badge**: Color-coded pill with positive/neutral/negative lift indicators.
- **Engagement & Feedback Metrics**: Progress bars comparing personalized vs baseline engagement rates.
- **Diversity & Novelty Indicators**: Visual gauges for candidate variety and novelty rate.
- **Context Breakdown Tabs**: Interactive filters across opportunity types, deadline horizons, and risk tiers.
- **Interactive Recompute**: Allows researchers to re-evaluate their recommendations with zero page reload.

---

## 7. Verification & Benchmarking Results

1. **Test Suite**: `backend/tests/test_personalization_quality.py`
   - 10 comprehensive tests covering metrics calculation, lift computation, minimum evidence thresholds, contextual partitioning, hierarchical fallback, bounded adaptation, diversity/novelty, anti-feedback-loop deduplication, service idempotency, scaling benchmarks, and multi-tenant authorization.
   - **Result**: 10 passed in 2.62s.
2. **Performance Benchmark**:
   - Evaluated scaling across $N \in \{10, 100, 1000, 10000\}$ recommendations.
   - 10,000 recommendations evaluated in under 0.50s (0.18s observed).
   - Zero N+1 query overhead via eager bulk loading.
3. **Regression Status**:
   - Phase 5.1–5.6: 114 tests passing.
   - Core invariants and security isolation fully preserved.
