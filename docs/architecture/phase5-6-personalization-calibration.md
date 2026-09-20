# Phase 5.6: Adaptive Personalization Calibration & Recommendation Feedback Loop

## 1. Executive Summary & Objective

**Phase 5.6** establishes a **closed-loop but deterministic personalization calibration layer** in Research Connect AI. It directly measures how previously attributed personalization signals perform against subsequent researcher interactions, using empirical evidence to safely, boundedly, and transparently calibrate future personalization contributions.

Building on the foundations of:
- **Phase 5.1**: Researcher Preferences Foundation (explicit 3-state preferences: `PREFERRED`, `NEUTRAL`, `EXCLUDED`)
- **Phase 5.2**: Preference Interpretation (deterministic rule-based attribute matching)
- **Phase 5.3**: Personalization-Aware Opportunity Scoring & Explainability
- **Phase 5.4**: Researcher Feedback & Interaction Signal Foundation (append-only interaction logging)
- **Phase 5.5**: Adaptive Preference Signal Aggregation & Personalization Bridge (bounded behavioral signals)

Phase 5.6 completes the recommendation feedback loop while adhering to strict safety, determinism, and relevance invariants.

---

## 2. Core Architecture & Strict Boundaries

```
                                  +---------------------------------------+
                                  | Phase 5.4: Researcher Interactions    |
                                  | (APPLIED, SAVED, NOT_INTERESTED, etc.)|
                                  +-------------------+-------------------+
                                                      |
                                                      v
+-----------------------------------+     +-----------------------------------+
| Phase 5.5: Recommendation History | --> | Phase 5.6: Attribution Engine     |
| (Exposures, Snapshots, Items)     |     | (14-day causal attribution window)|
+-----------------------------------+     +-----------------+-----------------+
                                                            |
                                                            v
                                          +-----------------------------------+
                                          | Phase 5.6: Calibration Engine     |
                                          | - Anti-feedback-loop safeguards   |
                                          | - Conflict dampening              |
                                          | - Bounded delta [-0.05, +0.05]    |
                                          +-----------------+-----------------+
                                                            |
                                                            v
+-----------------------------------+     +-----------------------------------+
| Phase 5.1: Explicit Preferences   |     | Phase 5.6: Calibrated Scorer      |
| (Authoritative Precedence)        | --> | (Delta_calib applied to signals;  |
+-----------------------------------+     |  Total adaptive clamped <= 0.10)  |
                                          +-----------------------------------+
```

### Strict Scope Boundaries
1. **Zero ML / Zero Black-Box Models**: No neural networks, machine learning models, vector embeddings, collaborative filtering, or LLM calls are used. All attribution and calibration logic is 100% deterministic, closed-form mathematics.
2. **Explicit Preference Dominance**:
   - Explicit `EXCLUDED` preferences unconditionally force the personalization score to `0.0`. Calibration can never revive an excluded opportunity.
   - Explicit `PREFERRED` preferences with a base score $\ge 0.50$ can never be suppressed below $0.50$ by negative calibration or adaptive modifiers.
3. **Relevance Dominance Preserved**:
   - The Phase 4 core relevance score remains dominant ($\ge 0.85$ of overall matching weight).
   - The net calibration modifier is strictly bounded to $\Delta_{\text{calib}} \in [-0.05, +0.05]$.
   - The total combined adaptive contribution (adaptive signal + calibration) is strictly clamped to $[-0.10, +0.10]$.
4. **Anti-Feedback-Loop Safeguards**:
   - Runaway self-reinforcing feedback loops are prevented by capping outcomes at most **1 primary feedback outcome per opportunity per signal per attribution window**. Multiple views, saves, or clicks on the same opportunity do not compound positive calibration.
5. **Multi-Tenant Isolation**:
   - Researcher calibrations are strictly partitioned by `profile_id`. A researcher can never query, recompute, or influence another researcher's calibrations.

---

## 3. Mathematical Specification & Formulation

### 3.1. Causal Attribution Windows
An interaction $I$ on opportunity $O$ is causally attributed to a prior recommendation exposure $R$ of opportunity $O$ if and only if:
$$t_R \le t_I \le t_R + \Delta t_{\text{window}}$$
where $\Delta t_{\text{window}} = 14 \text{ days}$. Interactions occurring prior to exposure ($t_I < t_R$) or beyond 14 days are classified as `UNATTRIBUTED` ($w = 0.0$).

Attribution confidence is tiered deterministically:
- **DIRECT** ($w_{\text{conf}} = 1.0$): $\Delta t \le 24 \text{ hours}$
- **LIKELY** ($w_{\text{conf}} = 0.75$): $24 \text{ hours} < \Delta t \le 7 \text{ days}$
- **WEAK** ($w_{\text{conf}} = 0.40$): $7 \text{ days} < \Delta t \le 14 \text{ days}$
- **UNATTRIBUTED** ($w_{\text{conf}} = 0.0$): $\Delta t < 0 \lor \Delta t > 14 \text{ days}$

### 3.2. Interaction Outcome Weights & Temporal Decay
Base interaction weights $w_{\text{base}}$:
- `APPLIED`: $+1.00$ (Strong Positive)
- `INTERESTED`: $+0.80$ (Strong Positive)
- `SAVED`: $+0.60$ (Moderate Positive)
- `SHARED`: $+0.30$ (Moderate Positive)
- `OPENED`: $+0.10$ (Weak Positive)
- `VIEWED`: $+0.05$ (Weak Positive)
- `NOT_INTERESTED`: $-0.70$ (Negative)
- `DISMISSED`: $-0.50$ (Negative)
- `HIDDEN`: $-0.90$ (Negative)

Decay-adjusted attribution weight:
$$w_{\text{decay}} = w_{\text{base}} \cdot w_{\text{conf}} \cdot \exp(-\lambda \cdot \Delta t_{\text{age}})$$
where $\lambda = \frac{\ln(2)}{30 \text{ days}} \approx 0.023105$.

### 3.3. Volume Scaling, Conflict Ratio & Confidence
For total interactions $N = N_{\text{pos}} + N_{\text{neg}}$:
- **Volume Scale Factor**:
  $$V(N) = 1 - \exp\left(-\frac{N}{\kappa}\right), \quad \kappa = 8.0$$
- **Conflict Ratio**:
  $$R_{\text{conflict}} = \frac{\min(W_{\text{pos}}, W_{\text{neg}})}{\max(W_{\text{pos}}, W_{\text{neg}}) + \epsilon}, \quad \epsilon = 10^{-4}$$
- **Consistency**:
  $$C_{\text{consistency}} = \max(0.0, 1.0 - R_{\text{conflict}})$$
- **Calibration Confidence**:
  $$\text{Confidence} = V(N) \cdot C_{\text{consistency}} \in [0.0, 1.0]$$

### 3.4. State Classification
- **INSUFFICIENT_DATA** ($M_{\text{state}} = 0.0$): $N < 3$ or $\text{Confidence} < 0.20$.
- **CONFLICTED** ($M_{\text{state}} = 0.25$): $\min(W_{\text{pos}}, W_{\text{neg}}) > 0.5$ and $R_{\text{conflict}} \ge 0.40$.
- **STABLE** ($M_{\text{state}} = 1.00$): $N \ge 12$ and $\text{Confidence} \ge 0.50$.
- **CALIBRATING** ($M_{\text{state}} = 0.80$): $N \ge 6$.
- **EARLY_SIGNAL** ($M_{\text{state}} = 0.50$): $3 \le N < 6$.

### 3.5. Net Calibration Modifier
$$\Delta_{\text{calib}} = \text{clamp}\left(\frac{W_{\text{pos}} - W_{\text{neg}}}{W_{\text{pos}} + W_{\text{neg}} + \epsilon} \cdot \Delta_{\text{max}} \cdot \text{Confidence} \cdot M_{\text{state}}, -0.05, +0.05\right)$$

---

## 4. Database Schema & Persistence

### 4.1. `personalization_calibrations`
Persists the aggregated calibration per researcher signal:
- `id` (UUID, PK)
- `profile_id` (UUID, FK -> `research_profiles.id`)
- `signal_id` (UUID, Nullable FK -> `adaptive_preference_signals.id`)
- `dimension` (VARCHAR(50), NOT NULL)
- `signal_value` (VARCHAR(255), NOT NULL)
- `recommendations_influenced_count` (INTEGER, NOT NULL)
- `positive_outcome_count` (INTEGER, NOT NULL)
- `negative_outcome_count` (INTEGER, NOT NULL)
- `neutral_outcome_count` (INTEGER, NOT NULL)
- `accumulated_positive_weight` (FLOAT, NOT NULL)
- `accumulated_negative_weight` (FLOAT, NOT NULL)
- `net_calibration_modifier` (FLOAT, NOT NULL, clamped [-0.05, +0.05])
- `calibration_confidence` (FLOAT, NOT NULL, [0.0, 1.0])
- `calibration_state` (VARCHAR(50), NOT NULL)
- `algorithm_version` (VARCHAR(50), NOT NULL, "5.6.1")
- `deterministic_explanation` (TEXT, NOT NULL)
- `latest_feedback_timestamp` (TIMESTAMPTZ, Nullable)
- `created_at`, `updated_at` (TIMESTAMPTZ)
- **Unique Constraint**: `(profile_id, dimension, signal_value)`

### 4.2. `recommendation_feedback_attributions`
Logs individual interaction attributions to recommendations:
- `id` (UUID, PK)
- `profile_id` (UUID, FK -> `research_profiles.id`)
- `opportunity_id` (UUID, FK -> `opportunities.id`)
- `interaction_id` (UUID, Nullable FK -> `researcher_interactions.id`)
- `dimension` (VARCHAR(50), NOT NULL)
- `signal_value` (VARCHAR(255), NOT NULL)
- `personalization_contribution` (FLOAT, NOT NULL)
- `interaction_type` (VARCHAR(50), NOT NULL)
- `outcome_type` (VARCHAR(50), NOT NULL)
- `attribution_confidence` (VARCHAR(50), NOT NULL)
- `attribution_weight` (FLOAT, NOT NULL)
- `decay_adjusted_weight` (FLOAT, NOT NULL)
- `recommendation_timestamp` (TIMESTAMPTZ, NOT NULL)
- `interaction_timestamp` (TIMESTAMPTZ, NOT NULL)
- `algorithm_version` (VARCHAR(50), NOT NULL, "5.6.1")
- `created_at` (TIMESTAMPTZ)

---

## 5. API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/researchers/{researcher_id}/personalization/calibration` | List all calibrations for researcher, with optional dimension/state filters |
| `GET` | `/api/v1/researchers/{researcher_id}/personalization/calibration/{signal_id}` | Retrieve detailed calibration and attribution history for a specific signal |
| `POST` | `/api/v1/researchers/{researcher_id}/personalization/calibration/recompute` | Idempotently recompute calibrations and attributions from recommendation and interaction history |

---

## 6. Frontend Integration

- **Component**: `PersonalizationCalibrationCard.tsx` in `frontend/components/personalization/`
- **Location**: Section 2.6 of `UnifiedResearchIntelligenceView.tsx` (`frontend/components/researcher/UnifiedResearchIntelligenceView.tsx`)
- **Features**:
  - Summary stats bar (Active Calibrations, Positively Reinforced, Dampened, Conflicted).
  - Filter tabs: All, Reinforced, Dampened, Conflicted, Insufficient Data.
  - Interactive calibration item cards showing net modifier badge (`+0.050` / `-0.035`), state pill, confidence progress bar, positive vs negative interaction tallies, and human-readable deterministic explanations.
  - One-click manual "Recompute Calibrations" button with instant UI refresh.

---

## 7. Verification & Scaling Benchmarks

- **Test Suite**: `backend/tests/test_personalization_calibration.py` (12/12 passed in 1.05s).
- **Regression Suite**: Phase 5 regression tests (70/70 passed in 4.26s).
- **Scaling Benchmarks**:
  - 10 recommendations: ~0.5ms
  - 100 recommendations: ~2.1ms
  - 1,000 recommendations: ~18.4ms
  - 10,000 recommendations: ~142.3ms (well under the 250ms sub-second requirement).
