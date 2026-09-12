# Phase 3.6 — Feedback & Recommendation Learning Architecture

## 1. Executive Summary

**Phase 3.6: Feedback & Recommendation Learning** establishes a deterministic, bounded behavioral feedback loop for ResearchConnect AI. It observes how researchers interact with recommended academic opportunities (CFPs, journal issues, conferences, funding calls) and converts those interactions into normalized behavioral preferences without relying on opaque machine learning models, collaborative filtering, or black-box rerankers.

The overarching recommendation pipeline with Phase 3.6 integrated operates as follows:

```text
Researcher Profile & Publications (Phase 3.1 & 3.2)
       ↓
Explicit Preferences (Phase 3.3) — Authoritative Ground Truth
       ↓
Phase 2 Base Relevance & Discovery (HybridRanker / Semantic Search)
       ↓
Phase 2.6 Trust & Safety Classification (Authoritative Predatory Gate)
       ↓
Phase 2.7 Deadline Intelligence (Authoritative Temporal Lifecycle)
       ↓
Phase 3.6 Interaction Feedback Capture (VIEW, SAVE, INTERESTED, NOT_INTERESTED, DISMISS, APPLY)
       ↓
Phase 3.6 Deterministic Aggregation Engine (Decay, Saturation, Confidence, Conflict Dampening)
       ↓
Phase 3.4 Personalized Candidate Generation (Negative Suppression Filtered Pool)
       ↓
Phase 3.5 Personalization Ranking Layer (Re-ranking with Bounded Behavioral Component)
       ↓
Final Ranked Recommendations (Max Personalization Contribution ≤ 0.15)
```

### The Core Architectural Principles
1. **Zero Machine Learning in Feedback**: No stochastic optimization, gradient descent, matrix factorization, or user-user collaborative filtering is used. All feedback accumulation, decay, diminishing returns, and confidence calculations are closed-form, deterministic mathematical functions.
2. **Explicit Preference Dominance**: Explicit preferences (Phase 3.3) represent conscious researcher declarations and must never be silently overwritten, deleted, or inverted by behavioral inferences.
3. **Relevance Dominance**: Strong base relevance (Phase 2) strictly dominates weak relevance boosted by positive feedback.
4. **Authoritative Trust & Deadline Invariance**: Phase 2.6 risk evaluations and Phase 2.7 deadline gates remain completely uncompromised. Interactions never teach the system that predatory conferences are safe or resurrect expired deadlines.

---

## 2. Feedback Model & Event Semantics

### 2.1 Supported Feedback Types & Semantics

Every feedback event recorded in the system belongs to one of six supported types with well-defined semantics:

| Feedback Type | Direction | Base Weight ($w_e$) | Semantics |
| :--- | :--- | :--- | :--- |
| `VIEW` | Neutral / Weak Positive | $+0.05$ | Researcher inspected opportunity details; minor discovery interest. |
| `SAVE` | Strong Positive | $+0.25$ | Researcher bookmarked opportunity for future reference. Synchronized with `SavedOpportunityModel`. |
| `INTERESTED` | Strong Positive | $+0.30$ | Explicit positive assessment ("Like"); strong signal for topic and venue alignment. |
| `APPLY` | Maximum Positive | $+0.40$ | High-intent engagement: clicked external submission or portal link. |
| `DISMISS` | Moderate Negative | $-0.20$ | Explicitly dismissed from feed; immediately triggers candidate suppression. |
| `NOT_INTERESTED` | Strong Negative | $-0.30$ | Strong negative signal ("Dislike"); heavily dampens matching attribute preferences. |

### 2.2 Data Model: `ResearcherRecommendationFeedbackModel`

Feedback is persisted in the relational database (`researcher_recommendation_feedback`) using the following schema:

- `id` (`UUID`): Primary key.
- `researcher_id` (`UUID`, FK `research_profiles.id`): Associated researcher profile. Indexed.
- `opportunity_id` (`UUID`, FK `opportunities.id`): Associated academic opportunity. Indexed.
- `feedback_type` (`VARCHAR(32)`): One of `VIEW`, `SAVE`, `DISMISS`, `INTERESTED`, `NOT_INTERESTED`, `APPLY`.
- `source` (`VARCHAR(32)`): Origin context (`RECOMMENDATION_FEED`, `SEARCH_RESULT`, `OPPORTUNITY_DETAIL`, `SAVED_LIST`, `MANUAL_ACTION`).
- `notes` (`TEXT`, optional): Optional researcher notes.
- `rank_position` (`INT`, optional): Position in recommendation list when interaction occurred.
- `recommendation_session_id` (`VARCHAR(64)`, optional): Provenance session tracking.
- `metadata_snapshot` (`JSONB`): Snapshot of opportunity attributes (topics, type, mode, venue) at interaction time.
- `created_at` / `updated_at` (`TIMESTAMPTZ`): Event timestamps.

#### Idempotency & Constraint Guarantee
A unique constraint `uq_researcher_feedback_type` spans `(researcher_id, opportunity_id, feedback_type)`. Repeating the same feedback action on an opportunity updates timestamps and metadata rather than compounding weight linearly.

---

## 3. Mathematical Formulations

### 3.1 Exponential Temporal Decay

Historical interactions naturally lose relevance over time. The decay of an event with age $\Delta t$ (in days) is governed by continuous exponential decay:

$$\lambda = \frac{\ln(2)}{T_{\text{half}}} = \frac{\ln(2)}{30.0} \approx 0.023105$$

$$\text{decay}(\Delta t) = \exp(-\lambda \cdot \Delta t)$$

- **Half-Life ($T_{\text{half}}$)**: Configured at 30 days.
- **Horizon ($T_{\text{max}}$)**: Capped at 180 days. Events older than 180 days evaluate to 0.0.
- **Properties**: $\text{decay}(0) = 1.0$, $\text{decay}(30) = 0.50$, $\text{decay}(60) = 0.25$. Strictly monotonic and continuous.

### 3.2 Diminishing Returns & Saturation

Repeated interactions with identical or similar attributes must not produce unbounded score inflation. Cumulative decayed weights for an attribute are saturated using hyperbolic tangent compression:

$$S_{\text{raw}} = \sum_{i} w_{e, i} \cdot \text{decay}(\Delta t_i)$$

$$S_{\text{saturated}} = \tanh(\gamma \cdot S_{\text{raw}})$$

Where $\gamma = 0.50$ is the saturation curvature constant.
- For small weights ($S_{\text{raw}} \approx 0.25$), $\tanh(0.50 \cdot 0.25) \approx 0.124$ (nearly linear).
- For large weights ($S_{\text{raw}} \ge 5.0$), $\tanh(0.50 \cdot S_{\text{raw}}) \to 1.0$ (asymptotically bounded).

### 3.3 Behavioral Confidence Metric

Confidence reflects whether observed behavior is statistically robust, consistent, and recent:

$$\text{Confidence} = C_{\text{volume}} \cdot C_{\text{consistency}} \cdot C_{\text{recency}}$$

1. **Volume Factor**:
   $$C_{\text{volume}} = 1 - \exp\left(-\frac{N}{N_0}\right) \quad (N_0 = 5.0)$$
   A single interaction ($N=1$) yields $C_{\text{volume}} = 1 - e^{-0.2} \approx 0.1813$, preventing immediate overconfidence. At $N=5$, $C_{\text{volume}} \approx 0.6321$; at $N \ge 10$, $C_{\text{volume}} > 0.86$.
2. **Consistency Factor**:
   $$C_{\text{consistency}} = \frac{\left|\sum_i w_i\right|}{\sum_i |w_i|}$$
   Measures unanimity. If a researcher has 3 saves (+0.75) and 3 dismisses (-0.60), $C_{\text{consistency}} = \frac{0.15}{1.35} \approx 0.111$, drastically dampening confidence in conflicting areas.
3. **Recency Factor**:
   $$C_{\text{recency}} = \frac{1}{N}\sum_{i=1}^N \text{decay}(\Delta t_i)$$
   Fresh actions keep confidence high; stale historical clusters reduce confidence.

$$\text{Confidence} \in [0.0, 1.0]$$

---

## 4. Attribute-Grounded Learning & Explicit Preference Protection

### 4.1 Grounded Learning Scope
Behavioral learning updates only preference signals explicitly supported by verified opportunity metadata:
- **Topics**: Extracted from associated `TopicModel` records (`name` and `slug`).
- **Opportunity Types**: `CONFERENCE`, `JOURNAL`, `WORKSHOP`, `BOOK_SERIES`, etc.
- **Delivery Modes**: `ONLINE`, `HYBRID`, `OFFLINE`.
- **Locations & Venues**: Extracted country/city and publisher/organizer.

Unsupported or unobserved attributes are never hallucinated or derived.

### 4.2 Explicit Preference Protection & Conflict Resolution

When behavioral negative signals conflict with an active, user-declared explicit preference:
1. **Explicit Preference Inviolability**: Explicit preferences in `ResearcherPreferenceModel` are never deleted, disabled, or overwritten.
2. **Dampened Behavioral Adjustment**: Negative behavioral signals for explicitly preferred attributes are clamped to a conservative dominance floor:

$$S_{\text{behavioral, constrained}} = \max\left(S_{\text{behavioral}}, -\text{EXPLICIT\_PREFERENCE\_DOMINANCE\_FLOOR}\right)$$

Where $\text{EXPLICIT\_PREFERENCE\_DOMINANCE\_FLOOR} = 0.05$. Thus, negative behavior can at most reduce the explicit preference boost from $+0.40$ to $+0.35$; it can **never flip an explicit preference negative**.

---

## 5. Integration with Phase 3.5 Personalization Ranking

Phase 3.6 behavioral signals feed directly into `PersonalizationRanker` without altering Phase 3.5's bounding invariants:

$$\Delta_{\text{personalization}}(C) = \min\left(\text{MAX\_PERSONALIZATION\_CONTRIBUTION}, \text{RawPersonalizationScore} \cdot D(R_{\text{base}})\right)$$

Where:
- $\text{MAX\_PERSONALIZATION\_CONTRIBUTION} = 0.15$ (Inviolable 15% cap).
- $\text{BehavioralScore} \in [-0.15, +0.08]$: Bounded behavioral contribution.
- When $\text{BehavioralScore} < 0$, it penalizes opportunities matching negative behavioral signals.
- When an opportunity is in the active negative suppression set (`DISMISS` or `NOT_INTERESTED` within 30 days), it is omitted from Phase 3.4 candidate generation entirely. If manually presented, it receives a severe negative damping penalty of $-0.15$.

### 5.1 Invariant Protections
- **Relevance Dominance**: Strong relevance ($R_A = 0.85$) strictly defeats weak relevance ($R_B = 0.40$) regardless of maximal positive behavioral signals on $B$.
- **Predatory Safety Gate**: Any candidate flagged as `HIGH_RISK` or `is_predatory_flag=True` receives zero positive personalization and zero positive behavioral boost.
- **Deadline Gate**: Any opportunity classified as `EXPIRED` by Phase 2.7 deadline intelligence is filtered and cannot be recommended.
- **Cold Start Fallback**: With 0 feedback events, behavioral adjustment is identically $0.0000$, and the system falls back to pure Phase 3.5 + Phase 3.4 + Phase 2 ranking.

---

## 6. Zero N+1 Query Architecture

All feedback loading and aggregation queries are structured for constant $O(1)$ database execution:
- **Eager Joined Batching**: `joinedload(ResearcherRecommendationFeedbackModel.opportunity)` combined with `selectinload(OpportunityModel.topic_associations).joinedload(OpportunityTopicModel.topic)`.
- **Negative Suppression Lookup**: Single direct query with TTL filtering against indexed columns `(researcher_id, feedback_type, created_at)`.
- **Query Count**: Constant $\le 5$ queries regardless of candidate pool size (verified by dedicated regression benchmark `test_zero_n_plus_one_query_performance`).

---

## 7. REST API Endpoints

All feedback endpoints enforce strict `X-User-ID` ownership verification. Researchers can never submit or view feedback belonging to another user.

| HTTP Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/researchers/{researcher_id}/feedback` | Record or update interaction feedback (Idempotent). |
| `GET` | `/api/v1/researchers/{researcher_id}/feedback` | Retrieve paginated feedback event history. |
| `DELETE` | `/api/v1/researchers/{researcher_id}/feedback/{feedback_id}` | Delete a feedback entry (synchronously cleans up saved opportunity bookmarks). |
| `GET` | `/api/v1/researchers/{researcher_id}/feedback/summary` | Retrieve summary statistics, cold-start status, and top learned topics. |
| `GET` | `/api/v1/researchers/{researcher_id}/feedback/signals` | Retrieve raw learned behavioral signals with confidence and decay factors. |

---

## 8. Limitations & Scope Boundaries

In accordance with Phase 3.6 specifications:
- **Phase 3.7 Recommendation History & Evaluation**: Persistent recommendation snapshots and NDCG evaluation metrics are deferred to Phase 3.7.
- **Phase 3.8 Personalization Explainability UI**: Complete UI explanation dialogues are deferred to Phase 3.8.
- **No Collaborative Filtering**: Signals are computed strictly within each individual researcher's profile. No user-to-user similarity graphs or item-item collaborative matrices are constructed.
