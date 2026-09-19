# Phase 5.3 — Personalization-Aware Opportunity Scoring & Explainability

## Overview & Background

Phase 5.3 introduces the **deterministic personalization scoring and explainability layer** for Research Connect AI.

Consuming the explicit preference interpretation signals established in Phase 5.2, this layer computes a bounded, dimension-aware personalization score ($0.0 \le s \le 1.0$) and generates structured, natural-language explanations of how explicit researcher preferences relate to each research opportunity.

```
Researcher Preferences (Phase 5.1)
        ↓
PreferenceInterpreter (Phase 5.2)
        ↓
PreferenceMatchSignal (9 Dimensions)
        ↓
PersonalizationScorer (Phase 5.3)
        ↓
PersonalizationAssessment (Score, Breakdown, Explanations)
```

---

## 1. Core Architecture

### 1.1 Domain Models (`backend/app/personalization/models.py`)

1. **`PersonalizationContribution`**:
   - Captures the signed contribution of an individual preference dimension.
   - Preserves dimension, match type, polarity, base weight, raw contribution, normalized contribution, evidence, and deterministic explanation.
2. **`PersonalizationDimensionScore`**:
   - Represents the aggregate score and match status for a single preference dimension in $[0.0, 1.0]$.
3. **`PersonalizationScoreBreakdown`**:
   - Partitions dimension contributions into:
     - `positive_contributions`: Preferred/partial matches boosting the score.
     - `negative_contributions`: Explicit exclusions applying negative penalties.
     - `neutral_contributions`: Unspecified or neutral dimensions.
     - `unresolved_contributions`: Conflicts or missing opportunity data (`INSUFFICIENT_EVIDENCE`).
   - Tracks total positive weight, total negative penalty, and active dimension counts.
4. **`PersonalizationExplanation`**:
   - Multi-faceted, deterministic natural language explanations:
     - `summary`: Executive summary of the score and match state.
     - `positive_reasons`: Explanations for positive contributions.
     - `negative_reasons`: Explanations for exclusion penalties.
     - `unresolved_reasons`: Explanations for conflicts.
     - `insufficient_evidence_reasons`: Explanations for missing opportunity metadata.
     - `neutral_reasons`: Explanations for unspecified dimensions.
5. **`PersonalizationScore`**:
   - `bounded_score`: Clamped authoritative score in $[0.0, 1.0]$.
   - `normalized_score`: Score relative to active configured preferences ($W_{\text{active}}$).
   - `absolute_score`: Score relative to all 9 dimensions ($\sum w_d = 1.00$).
   - `raw_score`: Signed net contribution ($W_{\text{pos}} - W_{\text{neg}}$).
   - `positive_contribution`: Sum of positive contributions.
   - `negative_penalty`: Sum of negative penalties.
   - `confidence`: Evidence coverage ratio in $[0.0, 1.0]$.
   - `match_state`: Overall match state (`PREFERRED_MATCH`, `EXCLUDED_MATCH`, `CONFLICT`, `INSUFFICIENT_EVIDENCE`, `NEUTRAL`).
6. **`PersonalizationAssessment`**:
   - Top-level assessment container combining score, breakdown, explanation, and underlying Phase 5.2 preference match signals.
7. **`BatchPersonalizationRequest` & `BatchPersonalizationResponse`**:
   - High-throughput batch schemas for evaluating up to 100 opportunities in a single API call.

---

## 2. Centralized Configuration (`backend/app/personalization/scoring_config.py`)

All scoring weights and multipliers are centralized in `PersonalizationScoringConfig` with documented defaults:

| Dimension | Weight | Rationale |
| :--- | :--- | :--- |
| `KEYWORD` | 0.20 | Direct lexical/topical alignment with researcher's specific research keywords. |
| `RESEARCH_DOMAIN` | 0.20 | Canonical discipline and topic alignment from verified academic taxonomy. |
| `OPPORTUNITY_TYPE` | 0.15 | Fundamental format preference (Conference, Grant, Fellowship, Workshop, etc.). |
| `COUNTRY` | 0.10 | Primary geographic mobility and eligibility constraint. |
| `REGION` | 0.05 | Broad geographic region alignment (e.g., Europe, North America). |
| `INSTITUTION` | 0.10 | Hosting or organizing institution preference. |
| `FUNDING` | 0.10 | Financial threshold or funding requirement alignment. |
| `ACADEMIC_LEVEL` | 0.05 | Target academic seniority (PhD, Postdoc, Faculty). |
| `CAREER_STAGE` | 0.05 | Career phase alignment (Early Career, Mid-Career, Senior). |
| **Sum** | **1.00** | Strictly normalized to 1.00. |

### Match State Multipliers:
- `PREFERRED_MATCH`: $+1.0 \times \text{weight} \times \text{confidence}$
- `PARTIAL_MATCH`: $+0.5 \times \text{weight} \times \text{confidence}$
- `EXCLUDED_MATCH`: $-1.0 \times \text{weight} \times \text{exclusion\_multiplier}$ (penalizes score)
- `CONFLICT`: $0.0$ (uncertainty preserved, no fabricated score)
- `INSUFFICIENT_EVIDENCE`: $0.0$ (missing opportunity data is safe, never penalized)
- `NEUTRAL`: $0.0$ (unspecified preference contributes zero)

---

## 3. Deterministic Scoring Logic (`backend/app/personalization/scorer.py`)

### 3.1 Scoring Algorithm
1. **Signal Ingestion**: Retrieves Phase 5.2 dimension signals from `PreferenceInterpreter`.
2. **Dimension Contribution**: Each dimension is evaluated and classified into positive, negative, neutral, or unresolved contributions.
3. **Weight Summation**:
   $$W_{\text{pos}} = \sum_{d \in \text{positive}} \text{contribution}_d$$
   $$W_{\text{neg}} = \sum_{d \in \text{negative}} |\text{contribution}_d|$$
   $$W_{\text{active}} = \sum_{d \in \text{active}} w_d$$
4. **Cold Start Safety**:
   If $W_{\text{active}} = 0$ (no preferences configured), $\text{bounded\_score} = 0.0$, $\text{confidence} = 0.0$, and state is `NEUTRAL`.
5. **Bounded Score Calculation**:
   $$\text{normalized\_score} = \max\left(0.0, \min\left(1.0, \frac{W_{\text{pos}} - W_{\text{neg}}}{W_{\text{active}}}\right)\right)$$
   $$\text{bounded\_score} = \text{round}(\text{normalized\_score}, 4)$$
   $$\text{absolute\_score} = \max(0.0, \min(1.0, W_{\text{pos}} - W_{\text{neg}}))$$

### 3.2 Missing Data Safety Invariant
Missing opportunity data (e.g. missing location, missing funding) strictly yields `INSUFFICIENT_EVIDENCE` and contributes $0.0$ to both $W_{\text{pos}}$ and $W_{\text{neg}}$. Missing data is never treated as negative evidence or an exclusion.

### 3.3 Conflict Handling Invariant
When an opportunity simultaneously matches preferred and excluded criteria, both are preserved under `CONFLICT` with `UNRESOLVED` polarity. The conflict is explicitly documented in the natural-language explanation.

---

## 4. REST API Endpoints (`backend/app/api/v1/researchers.py`)

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/researchers/{id}/opportunities/{opp_id}/personalization` | Evaluates an opportunity and returns a complete `PersonalizationAssessment`. |
| `POST` | `/api/v1/researchers/{id}/opportunities/personalization` | Evaluates a batch of up to 100 opportunities in memory with zero N+1 queries. |

Both endpoints enforce multi-tenant authorization (`X-User-ID` matching `research_profile.user_id`).

---

## 5. Next.js App Router Integration

1. **TypeScript Parity (`frontend/types/personalization.ts`)**:
   - Full 1:1 type parity with backend Pydantic models.
2. **API Methods (`frontend/services/api.ts`)**:
   - `fetchOpportunityPersonalization(researcherId, opportunityId)`
   - `fetchBatchOpportunityPersonalization(researcherId, opportunityIds)`
3. **UI Components (`frontend/components/personalization/`)**:
   - `PersonalizationScoreBadge.tsx`: Reusable score pill displaying percentage match, confidence, and match state.
   - Interactive popover modal displaying score breakdown, positive signals, negative penalties, conflicts, missing data, and natural language explanation.
4. **Recommendation Feed Integration (`UnifiedResearchIntelligenceView.tsx`)**:
   - Fetches batch personalization assessments in parallel with recommendations.
   - Displays `PersonalizationScoreBadge` alongside `PreferenceMatchBadge`, deadline intelligence, and risk indicators.
   - **Zero ranking reordering**: production ranking formulas and order remain completely unaltered.

---

## 6. Safety Invariants Verified

All 20 safety invariants have been implemented and verified:
1. No preference = neutral ($0.0$ score, `NEUTRAL` state).
2. Preferred $\neq$ required (preferred matches boost score without disqualifying other opportunities).
3. Excluded $\neq$ low relevance (exclusions incur explicit negative penalties and `EXCLUDED_MATCH` state).
4. Missing data $\neq$ exclusion (missing attributes contribute $0.0$, never negative).
5. Conflict $\neq$ fabricated resolution (both preferred and excluded evidence preserved).
6. Personalization score is bounded ($0.0 \le \text{personalization\_score} \le 1.0$).
7. Dimension contributions are bounded (each contribution $\in [-w_d, +w_d]$).
8. Identical inputs produce identical outputs (100% deterministic).
9. No LLM calls during scoring.
10. No network calls during scoring.
11. No N+1 queries (batch evaluation in memory).
12. Deadline intelligence preserved (deadlines and lifecycles unaffected).
13. Risk/trust scores preserved (predatory flags unaffected).
14. Academic quality scores preserved.
15. Researcher profile identity preserved (zero duplicate profiles).
16. Existing Phase 4 relevance dominance guarantees preserved.
17. Phase 5.1 preference semantics preserved.
18. Phase 5.2 interpretation semantics preserved.
19. Frontend performs no independent personalization calculations.
20. API serialization is lossless.

---

## 7. Phase Boundaries

Phase 5.3 strictly refrains from:
- Behavioral learning (click tracking, bookmark learning, dwell time, impression tracking)
- Implicit preference inference
- Collaborative filtering
- Embeddings or vector similarity personalization
- Black-box ML personalization
- Opaque ranking overrides or mutations to Phase 4 recommendation formulas

These capabilities belong to Phase 5.4+ according to the project roadmap.
