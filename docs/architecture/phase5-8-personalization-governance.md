# Phase 5.8: Personalization Governance, Drift Detection & Adaptation Safety

## 1. Executive Summary & Objective

**Phase 5.8** establishes the **governance, drift detection, and adaptation safety layer** for the personalization subsystem in Research Connect AI. It provides the definitive answer to the mission-critical question:

> *"How do we detect when personalization is becoming unreliable, drifting away from the researcher's current interests, over-adapting to noisy behavior, or producing unsafe recommendation behavior?"*

Building upon:
- **Phase 5.1**: Researcher Preferences Foundation (explicit 3-state preferences: `PREFERRED`, `NEUTRAL`, `EXCLUDED`)
- **Phase 5.2**: Preference Interpretation (deterministic rule-based attribute matching)
- **Phase 5.3**: Personalization-Aware Opportunity Scoring & Explainability
- **Phase 5.4**: Researcher Feedback & Interaction Signal Foundation (append-only interaction logging)
- **Phase 5.5**: Adaptive Preference Signal Aggregation & Personalization Bridge (bounded behavioral signals)
- **Phase 5.6**: Adaptive Personalization Calibration & Recommendation Feedback Loop (closed-loop calibration)
- **Phase 5.7**: Personalization Evaluation, Contextual Adaptation & Recommendation Quality Loop

Phase 5.8 introduces continuous, deterministic safety monitoring that monitors signal drift across temporal windows, detects stale evidence, enforces explicit preference protection, computes a multi-dimensional personalization health score, and governs adaptation through an automated gate (`ALLOW`, `ALLOW_BOUNDED`, `HOLD`, `REDUCE`, `SUSPEND`) with strict hysteresis and recovery guarantees.

---

## 2. Core Architecture & Strict Invariants

```
                                  +---------------------------------------+
                                  | Phase 5.4: Researcher Interactions    |
                                  | (APPLIED, SAVED, DISMISSED, etc.)     |
                                  +-------------------+-------------------+
                                                      |
                                                      v
+-----------------------------------+     +---------------------------------------+
| Phase 5.1: Explicit Preferences   | --> | Phase 5.8: Governance Engine          |
| (Authoritative Dominance)         |     | - Temporal Windowing (Recent/Hist)    |
+-----------------------------------+     | - Drift Detection (STABLE->REVERSING) |
                                          | - Staleness & Freshness Analysis      |
+-----------------------------------+     | - Explicit Preference Protection      |
| Phase 5.5 - 5.7: Adaptive Signals | --> | - Multi-Dimensional Health Score      |
| (Modifiers, Calibration, Context) |     | - Governance Gate (ALLOW -> SUSPEND)  |
+-----------------------------------+     +-------------------+-------------------+
                                                              |
                                                              v
                                          +---------------------------------------+
                                          | Phase 5.8: Personalization Scorer     |
                                          | - Multiplier: ALLOW=1.0, BOUNDED=0.5, |
                                          |   HOLD=0.25, REDUCE=0.25, SUSPEND=0.0 |
                                          | - Neutral suspension fallback (0.0)   |
                                          | - Explicit EXCLUDED => 0.0 always     |
                                          +---------------------------------------+
```

### Strict Scope Boundaries & Precedence Hierarchy
1. **Zero ML / Zero Black-Box Models**: No neural networks, vector databases, collaborative filtering, online learning, model training, or LLM calls are used. All metrics, drift classifications, health scores, and gate transitions are computed using 100% deterministic, closed-form mathematics and rule-based logic.
2. **Precedence Hierarchy**:
   $$\text{Core Relevance } (\ge 0.85) > \text{Explicit Preferences} > \text{Adaptive Signals } (\pm 0.10) > \text{Calibration } (\pm 0.05) > \text{Contextual Adaptation } (\pm 0.03)$$
3. **Explicit Preference Dominance**:
   - Explicit `EXCLUDED` preferences unconditionally force the final score to `0.0`. Behavioral drift or adaptive signals can never revive an excluded opportunity.
   - Explicit `PREFERRED` preferences with a base score $\ge 0.50$ are protected from negative suppression below $0.50$ by behavioral drift or adaptive penalties.
   - Behavioral drift can **never** overwrite, mutate, or delete explicit preferences.
4. **Neutral Suspension Guarantee**:
   - When the governance gate transitions to `SUSPEND`, adaptive modifiers revert strictly to **neutral `0.0`** (never negative). Core relevance, deadline urgency, and risk tiers remain dominant.
5. **Hysteresis & Recovery Safeguards**:
   - Recovery from `SUSPEND` strictly requires at least **5 stable interactions** within the evaluation window to prevent rapid flip-flopping or oscillation between gate states.
6. **Stale Evidence Principle**:
   - Stale evidence $\neq$ false evidence. Signals older than 180 days are classified as `STALE`, but are not automatically deleted or negated without explicit researcher action.
7. **Multi-Tenant Isolation**:
   - All drift evaluations, health scores, and governance events are strictly scoped to `profile_id`. A researcher can never view, recompute, or influence another researcher's governance state.
8. **Client-Side Decoupling**:
   - The Next.js frontend is strictly display-only. All governance calculations, health scores, drift classifications, and audit logs originate from the backend API.

---

## 3. Mathematical Specification & Formulation

### 3.1. Temporal Window Partitioning
Evaluations operate over two deterministic temporal windows relative to a deterministic `reference_time` $t_{\text{ref}}$:
- **Recent Window**: $[t_{\text{ref}} - 14\text{d}, t_{\text{ref}}]$
- **Historical Window**: $[t_{\text{ref}} - 60\text{d}, t_{\text{ref}} - 14\text{d})$
- **Stale Cutoff**: $t < t_{\text{ref}} - 180\text{d}$

### 3.2. Signal Drift Detection & Classification
For each behavioral signal dimension $s$, the net signal strength in a window $W$ is:
$$S(W) = \frac{\sum_{i \in W} w_i \cdot \text{sign}(i)}{\sum_{i \in W} w_i}$$
where $w_i$ is the interaction weight and $\text{sign}(i) \in \{+1.0, -1.0\}$.

The drift magnitude is:
$$\Delta_{\text{drift}}(s) = |S(\text{recent}) - S(\text{historical})|$$

A signal is classified into one of 5 deterministic types:
1. `STABLE`: $\Delta_{\text{drift}} < 0.20$ and recent interaction count $\ge 3$.
2. `EMERGING`: Historical count $= 0$ and recent count $\ge 3$.
3. `PERSISTENT`: $\Delta_{\text{drift}} \ge 0.20$, and recent and historical signals maintain the same sign for $\ge 30$ days.
4. `REVERSING`: Intermediate signal strength drifted from historical by $\ge 0.20$, and recent interactions move back toward historical by $\ge 0.15$.
5. `UNKNOWN`: Insufficient data ($< 3$ interactions across both windows).

### 3.3. Staleness & Freshness Classification
Based on the timestamp of the most recent interaction $t_{\text{latest}}$:
- `FRESH`: $t_{\text{latest}} \ge t_{\text{ref}} - 14\text{d}$
- `AGING`: $t_{\text{ref}} - 60\text{d} \le t_{\text{latest}} < t_{\text{ref}} - 14\text{d}$
- `STALE`: $t_{\text{latest}} < t_{\text{ref}} - 180\text{d}$
- `UNKNOWN`: No interactions recorded.

### 3.4. Explicit Preference Alignment
Comparing inferred behavioral direction with explicit preferences:
- `ALIGNED`: Behavioral signals reinforce explicit `PREFERRED` or `EXCLUDED` settings.
- `NEUTRAL`: Behavioral signals apply to facets without explicit preferences.
- `CONFLICTING`: Behavioral signals exhibit strong negative interaction with an explicit `PREFERRED` facet, or positive engagement with an explicit `EXCLUDED` facet.
- `UNKNOWN`: Insufficient evidence to determine alignment.

### 3.5. Multi-Dimensional Personalization Health Model
The overall personalization health score $H \in [0.0, 1.0]$ is computed as a weighted combination of 5 sub-metrics:
$$H = 0.30 \cdot S_{\text{stability}} + 0.25 \cdot S_{\text{freshness}} + 0.25 \cdot S_{\text{alignment}} + 0.10 \cdot S_{\text{predictability}} + 0.10 \cdot (1.0 - S_{\text{volatility}})$$

where:
- **Stability Score** ($S_{\text{stability}}$): Proportion of signals classified as `STABLE` or `PERSISTENT` vs. total active signals.
- **Freshness Score** ($S_{\text{freshness}}$): Ratio of active signals that are `FRESH` or `AGING` with exponential decay beyond 60 days.
- **Alignment Score** ($S_{\text{alignment}}$): Ratio of non-conflicting signals to total signals evaluated against explicit preferences.
- **Predictability Score** ($S_{\text{predictability}}$): Consistency of interaction outcomes with predicted recommendation scores.
- **Volatility Score** ($S_{\text{volatility}}$): Standard deviation of recent adaptive modifier adjustments.

#### Health State Mapping
- `HEALTHY`: $H \ge 0.75$ and no conflicting explicit preferences.
- `DEGRADED`: $0.55 \le H < 0.75$ or presence of aging signals.
- `DRIFTING`: $0.40 \le H < 0.55$ or $\ge 2$ signals exhibiting active drift ($\Delta_{\text{drift}} \ge 0.20$).
- `UNRELIABLE`: $H < 0.40$ or presence of critical explicit preference conflicts.

### 3.6. Governance Gate States & Adaptation Multipliers
The governance gate controls how adaptive signals modify recommendation scores:

| Gate State | Condition | Adaptation Multiplier | Behavior |
| :--- | :--- | :---: | :--- |
| `ALLOW` | $H \ge 0.75$ (`HEALTHY`) | `1.0` | Normal adaptation; full adaptive modifiers applied. |
| `ALLOW_BOUNDED` | $0.55 \le H < 0.75$ (`DEGRADED`) | `0.5` | 50% bounded damping applied to all adaptive modifiers. |
| `HOLD` | $0.40 \le H < 0.55$ (`DRIFTING`) | `0.25` | Adaptive updates frozen; 25% damping applied. |
| `REDUCE` | Persistent degradation | `0.25` | Progressive reduction of adaptive influence. |
| `SUSPEND` | $H < 0.40$ (`UNRELIABLE`) | `0.0` | Strict neutral reversion; modifiers set to `0.0`. |

### 3.7. Hysteresis & Recovery Mechanics
To transition from `SUSPEND` back to `ALLOW_BOUNDED` or `ALLOW`:
1. The researcher must accumulate at least **5 stable interactions** in the evaluation window.
2. The health score $H$ must exceed the recovery threshold ($H \ge 0.60$).
3. All conflicting signals against explicit preferences must be resolved.

---

## 4. Database Schema & Migration

### Migration `0022_phase5_8_personalization_governance.py`
Two new append-friendly tables are introduced:

```sql
CREATE TABLE personalization_drift_evaluations (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
    evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    health_score NUMERIC(5, 4) NOT NULL,
    health_state VARCHAR(32) NOT NULL,
    governance_state VARCHAR(32) NOT NULL,
    adaptation_multiplier NUMERIC(4, 3) NOT NULL,
    active_signals_count INTEGER NOT NULL,
    drifting_signals_count INTEGER NOT NULL,
    stale_signals_count INTEGER NOT NULL,
    conflicting_signals_count INTEGER NOT NULL,
    drift_metrics JSONB NOT NULL,
    health_breakdown JSONB NOT NULL,
    explanations JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE personalization_governance_events (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    previous_state VARCHAR(32) NOT NULL,
    new_state VARCHAR(32) NOT NULL,
    trigger_reason TEXT NOT NULL,
    metrics_snapshot JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

---

## 5. REST API Specifications

All endpoints require authentication via `X-User-ID` matching the target profile.

### 5.1. `GET /api/v1/researchers/{researcher_id}/personalization/health`
Returns the current multi-dimensional personalization health state, composite health score, governance gate state, adaptation multiplier, and breakdown metrics.

### 5.2. `GET /api/v1/researchers/{researcher_id}/personalization/drift`
Returns detailed signal drift evaluations across all behavioral dimensions, including temporal window partitioning, drift magnitude, drift classification (`STABLE`, `EMERGING`, `PERSISTENT`, `REVERSING`, `UNKNOWN`), staleness status, and explicit preference alignment.

### 5.3. `GET /api/v1/researchers/{researcher_id}/personalization/governance`
Returns the append-only governance audit log, detailing all gate state transitions, trigger reasons, and timestamped metric snapshots.

### 5.4. `POST /api/v1/researchers/{researcher_id}/personalization/health/recompute`
Forces a deterministic recomputation of drift evaluations and health scores for the specified researcher.

---

## 6. Frontend Architecture

### 6.1. Component Hierarchy
- `frontend/components/personalization/PersonalizationGovernanceCard.tsx`: Primary UI component presenting:
  - Overall health score gauge and status pill (`HEALTHY`, `DEGRADED`, `DRIFTING`, `UNRELIABLE`)
  - Governance gate badge with adaptation multiplier (`ALLOW` 1.0x $\to$ `SUSPEND` 0.0x)
  - Tabbed signal inspector (Drifting Signals, Stale Evidence, Stable Signals)
  - Multi-dimensional health breakdown bars (Stability, Freshness, Alignment, Predictability, Volatility)
  - Append-only governance audit timeline with trigger reasons
  - Manual "Recompute Health" action with real-time feedback
- `frontend/components/researcher/UnifiedResearchIntelligenceView.tsx`: Integrated in Section 2.8 alongside quality and calibration dashboards.

---

## 7. Verification & Benchmarking Summary

### Test Suite Execution
- **Phase 5.8 Specific Tests** (`backend/tests/test_personalization_governance.py`):
  - `test_drift_classification_stable_and_emerging`: Validates thresholding for stable and emerging signals.
  - `test_drift_classification_reversing_and_persistent`: Validates directional drift reversal and persistence.
  - `test_staleness_detection_principle`: Confirms stale signals are detected without premature deletion.
  - `test_explicit_preference_protection_hierarchy`: Proves explicit `EXCLUDED` always yields `0.0` and `PREFERRED` is shielded.
  - `test_hysteresis_and_recovery_from_suspension`: Proves $\ge 5$ stable interactions required for recovery.
  - `test_neutral_suspension_guarantee`: Validates that `SUSPEND` reverts modifiers to neutral `0.0` (never negative).
  - `test_governance_audit_event_logging`: Validates append-only state transition logging.
  - `test_governance_endpoints_authorization`: Enforces multi-tenant security via `X-User-ID`.
  - `test_governance_engine_scaling_benchmark`: Validates sub-50ms deterministic execution across 10 to 10,000 interactions.
  - **Result: 10/10 PASSED**.

- **Personalization Regression Suite** (Phases 5.1 through 5.7):
  - **Result: 92/92 PASSED** (Total 102/102 personalization tests pass).
- **Core Platform Regression Suite** (Phases 2.5G, 2.6G, 2.7G, 4.7, researcher profile, ranker):
  - **Result: 122/122 PASSED**.
- **Frontend Verification**:
  - `npm run type-check`: Passed (0 errors).
  - `npm run lint`: Passed (0 errors).
  - `npm run build`: Production build succeeded (13/13 static routes generated).
