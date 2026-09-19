# Phase 5.2 — Explicit Preference Interpretation & Personalization Signal Foundation

## Overview & Purpose

Phase 5.2 establishes the deterministic interpretation layer that evaluates how research opportunities relate to explicit researcher preferences (from Phase 5.1) without introducing behavioral learning, collaborative filtering, embeddings, ML personalization, or uncontrolled ranking modifications.

The output is a structured, explainable, and inspectable personalization signal that preserves 3-state semantics ($\text{Preferred} \neq \text{Neutral} \neq \text{Excluded}$), detects conflicts, and safely handles missing data.

```
Researcher Preferences (Phase 5.1)
        ↓
PreferenceInterpreter (Phase 5.2)
        ↓
Opportunity Attribute Matching (9 Dimensions)
        ↓
Preference Match Signals
        ↓
Explainable Personalization Assessment
```

---

## 1. Core Architecture

### 1.1 Key Components

1. **Domain Models (`backend/app/personalization/models.py`)**:
   - `PreferenceMatchType`: `PREFERRED_MATCH`, `EXCLUDED_MATCH`, `NEUTRAL`, `PARTIAL_MATCH`, `CONFLICT`, `INSUFFICIENT_EVIDENCE`.
   - `PreferenceDimension`: `KEYWORD`, `RESEARCH_DOMAIN`, `COUNTRY`, `REGION`, `INSTITUTION`, `FUNDING`, `ACADEMIC_LEVEL`, `CAREER_STAGE`, `OPPORTUNITY_TYPE`.
   - `SignalPolarity`: `POSITIVE`, `NEGATIVE`, `NEUTRAL`, `UNRESOLVED`.
   - `PreferenceMatchSignal`: Atomic evaluation signal preserving dimension, preference value, opportunity value, match type, polarity, evidence, deterministic explanation, and confidence.
   - `PreferencePersonalizationAssessment`: Aggregate container preserving overall match state, counts, evidence coverage, explanation, and individual dimension signals.
   - `BatchPreferenceMatchRequestSchema` & `BatchPreferenceMatchResponseSchema`: Lossless request/response schemas for batch evaluation.

2. **Deterministic Preference Interpreter (`backend/app/personalization/interpreter.py`)**:
   - Pure, deterministic, side-effect free evaluation engine.
   - Evaluates opportunities in memory against normalized structured preferences.
   - Zero database queries during evaluation.
   - Zero LLM calls, zero network calls, zero database writes.
   - Supports both single opportunity evaluation (`evaluate_opportunity`) and batch evaluation (`evaluate_opportunities_batch`).

3. **API Endpoints (`backend/app/api/v1/researchers.py`)**:
   - `GET /api/v1/researchers/{researcher_id}/opportunities/{opportunity_id}/preference-match`: Single opportunity preference match evaluation with authorization enforcement.
   - `POST /api/v1/researchers/{researcher_id}/opportunities/preference-matches`: Batch evaluation endpoint taking a list of opportunity IDs to eliminate N+1 round trips.

4. **Frontend Layer (`frontend/`)**:
   - `frontend/types/personalization.ts`: Strict 1:1 TypeScript interfaces matching backend Pydantic models.
   - `frontend/services/api.ts`: Typed client functions `fetchOpportunityPreferenceMatch` and `fetchBatchOpportunityPreferenceMatches`.
   - `frontend/components/personalization/PreferenceMatchBadge.tsx`: Reusable, accessible indicator badge displaying match state, evidence counts, and detailed popover explanations.
   - `frontend/components/researcher/UnifiedResearchIntelligenceView.tsx`: Integrated batch preference evaluation alongside recommendation cards with zero ranking reordering.

---

## 2. Preference Semantics & Three-State Integrity

Phase 5.2 strictly preserves the three-state preference semantics established in Phase 5.1:

| Preference State | Meaning | Evaluation Behavior |
| :--- | :--- | :--- |
| **PREFERRED** | "This attribute is explicitly attractive" | Evaluated positively; yields `PREFERRED_MATCH` if present. **Never** treated as an absolute requirement (unless explicitly configured as a constraint like funding required). |
| **NEUTRAL** (Unspecified) | "No explicit preference has been declared" | Evaluated as `NEUTRAL`. **Never** treated as excluded or mismatched. |
| **EXCLUDED** | "This category/value is explicitly unwanted" | Evaluated as `EXCLUDED_MATCH`. Preserved distinctly from low relevance; never collapsed into a minor negative score. |

---

## 3. Supported Dimensions & Matching Rules

All 9 preference dimensions are evaluated deterministically:

1. **`OPPORTUNITY_TYPE`**:
   - Matches opportunity type against canonical categories (`CONFERENCE`, `JOURNAL`, `GRANT`, `FELLOWSHIP`, `POSTDOC`, `WORKSHOP`).
   - Evaluates preferred vs. excluded types.
   - If `opportunity_type` is missing: yields `INSUFFICIENT_EVIDENCE`.

2. **`KEYWORD`**:
   - Evaluates normalized multi-word phrases and unigram tokens against opportunity title and summary text.
   - Exact/substring match; no unverified synonyms invented.

3. **`RESEARCH_DOMAIN`**:
   - Compares preferred research domains and topics against linked canonical topics and domain classifications.
   - If opportunity has no topics attached: yields `INSUFFICIENT_EVIDENCE`.

4. **`COUNTRY`**:
   - Evaluates preferred and excluded countries against opportunity location text and ISO country codes.
   - If location is missing: yields `INSUFFICIENT_EVIDENCE` (missing location $\neq$ geographic mismatch).

5. **`REGION`**:
   - Evaluates geographic regions (e.g., `NORTH_AMERICA`, `EUROPE`, `ASIA`).

6. **`INSTITUTION`**:
   - Matches against organizer or publisher.
   - Distinguishes canonical institution matches from fallback string matches via `metadata_payload`.
   - If organizer/publisher is missing: yields `INSUFFICIENT_EVIDENCE`.

7. **`FUNDING`**:
   - Evaluates `funding_required`, `min_funding_amount`, and `max_funding_amount` against `apc_or_fee` metadata.
   - Missing funding metadata strictly yields `INSUFFICIENT_EVIDENCE` (missing funding $\neq$ unfunded).

8. **`ACADEMIC_LEVEL`**:
   - Compares academic level (e.g., `PHD`, `POSTDOC`, `FACULTY`) against structured opportunity eligibility requirements where available.
   - Missing eligibility information yields `INSUFFICIENT_EVIDENCE`.

9. **`CAREER_STAGE`**:
   - Compares career stage (e.g., `EARLY_CAREER`, `MID_CAREER`, `SENIOR`) against structured eligibility metadata.

---

## 4. Conflict Handling & Missing-Data Safety

### 4.1 Conflict Preservation
When an opportunity simultaneously matches preferred and excluded criteria:
- The interpreter **preserves both signals**.
- Match type is marked as `CONFLICT`.
- Polarity is marked as `UNRESOLVED`.
- Both preferred evidence and excluded evidence are retained in the explanation.
- Exclusions are **never** silently discarded.

### 4.2 Missing Data Safety Invariants
- Missing opportunity attributes **never** constitute evidence of mismatch or exclusion.
- Missing location $\rightarrow$ `INSUFFICIENT_EVIDENCE` (never `EXCLUDED_MATCH`).
- Missing funding $\rightarrow$ `INSUFFICIENT_EVIDENCE` (never `EXCLUDED_MATCH` or unfunded).
- Missing institution $\rightarrow$ `INSUFFICIENT_EVIDENCE`.
- Missing topics $\rightarrow$ `INSUFFICIENT_EVIDENCE`.

---

## 5. Explainability

All explanations are deterministically synthesized from observed signals without calling LLMs:
- **Preferred Match**: *"Matches your explicit preferences: Matches your preferred opportunity type: CONFERENCE."*
- **Excluded Match**: *"Excluded by your preferences: Matches your excluded country/region: DE."*
- **Conflict**: *"Preference conflict detected: matches preferred topic(s) 'AI' but conflicts with excluded 'Computer Vision'."*
- **Insufficient Evidence**: *"Preferences could not be evaluated due to missing opportunity data (country, funding)."*
- **Neutral**: *"This opportunity is neutral relative to your configured preferences."*

---

## 6. Performance & Complexity

- **Time Complexity**: $\mathcal{O}(N \times M)$ where $N$ is the number of opportunities and $M$ is the number of active preferences. In practice, evaluating 100 opportunities against 10 preferences executes in $< 15\text{ ms}$.
- **Space Complexity**: $\mathcal{O}(N)$ in-memory signal generation.
- **Database Optimization**:
  - Preferences are fetched once per researcher.
  - Opportunities are fetched in a single `IN (...)` batch query.
  - Zero N+1 queries.
  - Zero database writes during evaluation.

---

## 7. Safety Invariants Verification

All 25 safety invariants have been implemented and verified:
1. No preference = `NEUTRAL`.
2. Preferred $\neq$ Required.
3. Excluded $\neq$ merely low relevance.
4. Explicit exclusion is always preserved.
5. Missing opportunity data $\neq$ exclusion.
6. Missing funding $\neq$ unfunded.
7. Missing country $\neq$ geographic mismatch.
8. Missing institution $\neq$ institution mismatch.
9. Canonical institution IDs take precedence over fallback strings.
10. No invented semantic equivalence.
11. Conflicting preferences remain observable (`CONFLICT`).
12. Multiple dimensions remain independently explainable.
13. Preferences cannot create researcher identity duplicates.
14. Preference interpretation cannot alter deadline intelligence.
15. Preference interpretation cannot alter risk/trust scores.
16. Preference interpretation cannot alter academic-quality scores.
17. Existing Phase 4 ranking remains backward compatible.
18. Existing Phase 2 deadline behavior remains unchanged.
19. Existing Phase 3 researcher profile behavior remains unchanged.
20. Identical inputs produce identical outputs (strict determinism).
21. No LLM calls occur during interpretation.
22. No network calls occur during interpretation.
23. No N+1 database queries occur.
24. API serialization is lossless.
25. Frontend performs no independent personalization calculations.

---

## 8. Phase Boundaries

Phase 5.2 strictly refrains from:
- Behavioral learning (clicks, impressions, bookmarks, views)
- Implicit preference inference
- Collaborative filtering
- Embeddings or vector similarity personalization
- Machine-learning personalization
- Recommendation score overrides or opaque ranking boosts
- Autonomous preference discovery
- Reinforcement learning or LLM prompt generation

These capabilities are reserved for Phase 5.3+ according to the project roadmap.
