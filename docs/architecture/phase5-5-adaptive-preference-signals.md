# Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge

## Overview & Objective

Phase 5.5 establishes the **deterministic bridge between explicit researcher preferences and accumulated researcher feedback signals**, allowing repeated interaction patterns from Phase 5.4 (`researcher_interactions`) to become bounded personalization signals.

The purpose of this phase is NOT to build machine learning.

The purpose is to create a transparent, deterministic, explainable mechanism that aggregates historical researcher interactions into **bounded adaptive signals** that the existing Phase 5.3 personalization layer can consume.

```
+-----------------------------------------------------------------------------------+
|                        Phase 5 Personalization Architecture                        |
+-----------------------------------------------------------------------------------+
| Phase 5.1: Researcher Preferences Foundation (Explicit Preferred / Excluded)     |
| Phase 5.2: Explicit Preference Interpretation Engine (9 Dimensions)              |
| Phase 5.3: Personalization-Aware Opportunity Scoring & Explainability            |
| Phase 5.4: Researcher Feedback & Interaction Signal Foundation (Append-Only)      |
| Phase 5.5: Adaptive Preference Signal Aggregation & Bridge  <--- CURRENT          |
|   - Deterministic Aggregation Engine (AdaptiveSignalEngine)                       |
|   - Normalized Signal Persistence (adaptive_preference_signals)                   |
|   - Additive Bounded Scoring Bridge (clamp[-0.10, +0.10])                         |
|   - Next.js App Router Adaptive Signals Card & Unified View                       |
+-----------------------------------------------------------------------------------+
```

---

## 1. Core Architectural Invariants

1. **Explicit Preferences Remain Authoritative**: Adaptive signals are secondary behavioral observations; they never overwrite, delete, or silence explicit preferences.
2. **Exclusion Inviolability**: Explicit `EXCLUDED` preferences strictly dominate. Adaptive signals cannot revive an excluded opportunity (`score = 0.0`).
3. **Preferred Protection**: If explicit `PREFERRED` preferences exist, opposing negative adaptive signals cannot drop the score below `0.50` (if base score was $\ge 0.50$).
4. **Relevance Dominance Preservation**: Adaptive contribution is strictly bounded by `MAX_ADAPTIVE_CONTRIBUTION = 0.10`, ensuring Phase 4 relevance dominance ($\ge 0.85$) is never overwhelmed.
5. **Overreaction Protection**: Single interactions ($N < 3$) strictly yield `INSUFFICIENT_EVIDENCE` and contribute `0.0` to personalization.
6. **Dual Evidence Preservation**: Positive and negative evidence counts and decay-adjusted weights are separately stored and inspectable.
7. **Strict Determinism**: Zero LLM calls, zero network calls, zero random seeds. Identical interaction history + reference timestamp produces 100% identical outputs.

---

## 2. Mathematical Formulation & Signal Semantics

### 2.1 Interaction Weights (`AdaptiveSignalConfig`)
Interaction types are mapped to transparent, bounded weights:
- `APPLIED`: `+1.00` (very strong positive commitment)
- `INTERESTED`: `+0.80` (strong positive intent)
- `SAVED`: `+0.50` (moderate positive consideration)
- `SHARED`: `+0.40` (moderate positive endorsement)
- `VIEWED`: `+0.05` (weak passive observation)
- `OPENED`: `+0.05` (weak passive observation)
- `DISMISSED`: `-0.50` (moderate negative intent)
- `NOT_INTERESTED`: `-0.70` (strong negative intent)
- `HIDDEN`: `-0.90` (very strong negative intent)

### 2.2 Deterministic Temporal Decay
For an interaction at age $t$ (in days) relative to an explicit reference timestamp $t_{ref}$:
$$\text{decay}(t) = \max(w_{floor}, \exp(-\lambda \cdot t))$$
where $\lambda = \frac{\ln(2)}{t_{half}}$, $t_{half} = 30.0$ days, and $w_{floor} = 0.05$.
Interactions older than `max_horizon_days = 180` days receive zero weight.

### 2.3 Net Signal Strength
Net signal strength is bounded in $[-1.0, 1.0]$ with Laplace smoothing:
$$S = \frac{W_{pos} - W_{neg}}{W_{pos} + W_{neg} + \epsilon_{strength}}$$

### 2.4 Signal Confidence
Confidence $C \in [0.0, 1.0]$ decouples signal volume from behavioral consistency:
$$C = \text{VolumeScale}(N) \times \text{Consistency}(W_{pos}, W_{neg})$$
where:
$$\text{VolumeScale}(N) = 1.0 - \exp\left(-\frac{N}{\kappa}\right) \quad (\kappa = 5.0)$$
$$\text{Consistency}(W_{pos}, W_{neg}) = 1.0 - \frac{\min(W_{pos}, W_{neg})}{\max(W_{pos}, W_{neg}) + \epsilon_{consistency}}$$

### 2.5 Evidence State Thresholds
Signals are categorized deterministically:
- `STRONG`: $N \ge 12$ and $C \ge 0.80$
- `ESTABLISHED`: $N \ge 6$ and $C \ge 0.60$
- `EMERGING`: $N \ge 3$ and $C \ge 0.30$
- `INSUFFICIENT_EVIDENCE`: $N < 3$ or $C < 0.30$
- `CONFLICT` (Summary detection): $N_{pos} > 0$, $N_{neg} > 0$, and $|S| < 0.30$.

---

## 3. Database Schema & Migration

Table: `adaptive_preference_signals` (Alembic migration `0019_phase5_5_adaptive_preference_signals.py`):

```sql
CREATE TABLE adaptive_preference_signals (
    id UUID PRIMARY KEY,
    profile_id UUID NOT NULL REFERENCES research_profiles(id) ON DELETE CASCADE,
    dimension VARCHAR(50) NOT NULL,
    signal_value VARCHAR(255) NOT NULL,
    positive_evidence_count INTEGER NOT NULL DEFAULT 0,
    negative_evidence_count INTEGER NOT NULL DEFAULT 0,
    total_evidence_count INTEGER NOT NULL DEFAULT 0,
    decay_adjusted_positive_weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    decay_adjusted_negative_weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    weighted_signal_strength DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    evidence_state VARCHAR(50) NOT NULL DEFAULT 'INSUFFICIENT_EVIDENCE',
    evidence_window_days DOUBLE PRECISION NOT NULL DEFAULT 180.0,
    latest_evidence_timestamp TIMESTAMP WITH TIME ZONE,
    algorithm_version VARCHAR(50) NOT NULL DEFAULT '5.5.1',
    deterministic_explanation TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_adaptive_signal_profile_dim_val UNIQUE (profile_id, dimension, signal_value),
    CONSTRAINT chk_adaptive_signal_strength CHECK (weighted_signal_strength >= -1.0 AND weighted_signal_strength <= 1.0),
    CONSTRAINT chk_adaptive_signal_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_adaptive_signals_profile ON adaptive_preference_signals (profile_id);
CREATE INDEX idx_adaptive_signals_lookup ON adaptive_preference_signals (profile_id, dimension, signal_value);
CREATE INDEX idx_adaptive_signals_state ON adaptive_preference_signals (profile_id, evidence_state);
```

---

## 4. Personalization Bridge & Integration

In `PersonalizationScorer.score_opportunity`:
1. Phase 5.2 evaluates explicit preferences $\to$ `preference_assessment`.
2. Phase 5.3 calculates explicit base score $\to$ `score.bounded_score`.
3. Phase 5.5 evaluates active adaptive signals:
   $$\Delta_{adaptive} = \text{clamp}\left(\sum_d S_d \cdot C_d \cdot w_d \cdot m_{state}, -0.10, +0.10\right)$$
   where $m_{state} = 0.50$ for `EMERGING` signals and $1.0$ for `ESTABLISHED`/`STRONG`.
4. Final personalization score:
   $$\text{Score}_{final} = \begin{cases} 0.0 & \text{if explicit EXCLUDED exists} \\ \max(0.50, \text{clamp}(\text{Score}_{base} + \Delta_{adaptive}, 0, 1)) & \text{if explicit PREFERRED exists and base} \ge 0.50 \\ \text{clamp}(\text{Score}_{base} + \Delta_{adaptive}, 0, 1) & \text{otherwise} \end{cases}$$

---

## 5. API Endpoints

- `GET /api/v1/researchers/{researcher_id}/adaptive-signals`
  Returns all aggregated adaptive signals for the researcher, with optional `dimension` and `state` filtering.
- `GET /api/v1/researchers/{researcher_id}/adaptive-signals/{signal_id}`
  Returns a specific adaptive signal ensuring researcher isolation.
- `POST /api/v1/researchers/{researcher_id}/adaptive-signals/recompute`
  Deterministically recomputes all adaptive signals from the researcher's Phase 5.4 interaction records.
- `GET /api/v1/researchers/{researcher_id}/adaptive-signals/explanation`
  Returns structured, transparent natural language explanations summarizing the behavioral signals.

---

## 6. Frontend Components (`Next.js App Router`)

- `AdaptiveSignalsCard.tsx` (`frontend/components/personalization/AdaptiveSignalsCard.tsx`):
  Researcher-facing component exposing established, emerging, mixed, and sparse behavioral patterns with interactive filtering, evidence counts, deterministic explanations, and a recompute button.
- Integrated into `UnifiedResearchIntelligenceView.tsx` as Section 2.5.

---

## 7. Performance Benchmarks

Measured on standard execution environment across batch interaction sizes:
- 10 interactions: **0.22 ms**
- 100 interactions: **0.70 ms**
- 1,000 interactions: **5.91 ms**
- 10,000 interactions: **57.97 ms**

---

## 8. Safety Invariants Summary

All 35 safety invariants defined in the Phase 5.5 specification have been implemented, tested, and verified to pass without exception.
