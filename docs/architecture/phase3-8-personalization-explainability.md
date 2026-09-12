# Phase 3.8 — Personalization Explainability & Researcher UI

**Status**: COMPLETE  
**Commit**: Phase 3.8  
**Scope**: Grounded Recommendation Explanations, Signal Priority Ordering, Score Consistency Invariants, Safety Dominance, Historical Snapshot Immutability, Researcher Personalization Summary, and Accessible Next.js UI.

---

## 1. Overview & Purpose

The recommendation stack in ResearchConnect AI operates across progressive layers:
```
Phase 3.4 Candidate Generation
       ↓
Phase 3.5 Personalization Ranking
       ↓
Phase 3.6 Behavioral Learning (Feedback Loop)
       ↓
Phase 3.7 Recommendation History & Evaluation
       ↓
PHASE 3.8 EXPLANATION LAYER
       ↓
Researcher UI (Why this? + Personalization Summary)
```

**Phase 3.8 introduces an explainability layer over existing ranking decisions.**

The core architectural purpose is to answer:
1. *"Why am I seeing this opportunity?"*
2. *"Which of my preferences, expertise, interests, and behavior influenced this ranking?"*

### Core Principles
1. **Strictly Grounded Explanations**: Explanations are derived exclusively from actual ranking factors, matched preferences, scholarly expertise, and logged feedback signals. No hallucinated reasons or speculative claims are generated.
2. **Score Consistency Invariants**: Reported base relevance score, personalization contribution, and final composite score strictly match the actual values within mathematical floating-point tolerance ($1\times 10^{-4}$).
3. **Safety Dominance**: Safety signals (predatory flags, high-risk status) take immediate precedence over personalization fit. An unsafe opportunity is never praised as a "great match" without prominently displaying safety warnings.
4. **Historical Immutability**: Historical recommendation items from Phase 3.7 are explained using point-in-time snapshot records. Historical explanations are never recomputed using today's evolving preferences.
5. **Human-Readable Transparency**: Researchers see intuitive, categorized explanations (e.g. "Matches your primary research expertise", "Matches your preferred opportunity type") rather than mathematical hyper-parameters ($\gamma=0.50, \lambda=0.02$). Technical score decompositions remain available via an accessible diagnostic toggle.

---

## 2. Explanation Signal Hierarchy & Priority Ordering

When synthesizing the primary reasons for a recommendation, signals are evaluated and prioritized deterministically according to their causal influence:

| Priority | Signal Category | Source / Phase | Example Researcher-Facing Reason |
| :---: | :--- | :--- | :--- |
| **1** | **Safety / Risk Alert** | Phase 2.6 Trust Engine | *"Warning: Flagged for high publication risk or non-standard review practices."* |
| **2** | **Explicit Preference** | Phase 3.3 Researcher Preferences | *"Matches your explicit preference for Conference opportunities."* |
| **3** | **Scholarly Expertise** | Phase 3.2 Author Knowledge Graph | *"Matches your primary research expertise in Reinforcement Learning."* |
| **4** | **Learned Behavioral** | Phase 3.6 Behavioral Profile | *"Similar to opportunities you saved or marked as interested."* |
| **5** | **Profile Keywords** | Phase 3.1 Researcher Profile | *"Matches declared profile focus keywords."* |
| **6** | **Domain Relevance** | Phase 2 Hybrid Retrieval | *"Strong semantic relevance to your broader academic focus."* |
| **7** | **Timeline & Urgency** | Phase 2.7 Deadline Intelligence | *"Submission deadline approaching in 14 days."* |

### Positive vs. Negative Signals
- **Positive Driver**: Boosts recommendation position (e.g., explicit type match, primary expertise overlap, saved topic).
- **Negative Driver**: Explains rank demotions or penalties (e.g., *"Lowered because you previously dismissed similar workshops"*).

---

## 3. Score Consistency & Invariants

The explanation engine (`RecommendationExplainer`) verifies mathematical consistency before emitting any explanation:
$$\text{final\_score} = \text{base\_relevance\_score} + \text{personalization\_contribution}$$

- Invariant Check: $|\text{final\_score} - (\text{base\_relevance\_score} + \text{personalization\_contribution})| \le 1\times 10^{-4}$
- Personalization Contribution Bound:
  $$\text{personalization\_contribution} \in [-0.15, +0.15]$$
- Reported scores in the UI match the underlying database/API payload exactly.

---

## 4. Personalization Strength Classification

To provide a human-friendly indicator of how heavily personalization influenced a candidate's position, the system computes `personalization_strength`:

- **Highly personalized** ($\ge 0.08$ adjustment or both explicit preference and primary expertise matched).
- **Personalized** ($\ge 0.04$ adjustment).
- **Some personalization** ($> 0.00$ adjustment or partial keyword/topic match).
- **General recommendation** (baseline discovery; $0.00$ adjustment or high-risk override).

---

## 5. Safety & Trust Explanation Guarantee

When an opportunity has risk indicators:
1. `trust_status` is marked as `"High Risk"`.
2. A prominent alert is placed at the top of the explanation factor list.
3. The explanation explicitly states: *"Personalization relevance does not override or endorse safety checks."*
4. `personalization_strength` is constrained to `"General recommendation"` so predatory venues cannot be portrayed as tailored recommendations.

---

## 6. Cold-Start & No-Feedback Behaviors

The explainability layer accurately conveys the state of researcher data:
- **Cold Start** (0 interests, 0 preferences, 0 feedback):
  - Informs the researcher: *"Your recommendations are currently based mainly on research relevance."*
  - Exposes actionable next steps: Add research interests, configure preferences, or explore candidate streams.
  - Confidence label: `"Cold Start"` (0% confidence).
- **No Feedback** (Preferences configured, but 0 interaction events):
  - Informs the researcher: *"We're still learning your preferences. Save or dismiss opportunities to improve future recommendations."*
  - Does not pretend the system has learned behavioral preferences.

---

## 7. Historical Explanation Immutability

Historical snapshot explanations adhere to strict immutability:
- Fetched via:
  `GET /api/v1/researchers/{researcher_id}/recommendation-history/{snapshot_id}/items/{opportunity_id}/explanation`
- Uses frozen metrics stored in `ResearcherRecommendationItemModel` (`base_relevance_score`, `personalization_score`, `behavioral_adjustment`, `final_score`, `risk_level`, `deadline_status`).
- Does **not** re-execute the ranking pipeline with current researcher preferences.
- Displays a prominent `"Historical Snapshot"` banner stating when the recommendation was recorded and which ranking version was used.

---

## 8. API Specifications

All endpoints require `X-User-ID` matching the owner of the researcher profile, returning `403 Forbidden` on ownership mismatches.

### 1. Personalization Summary
`GET /api/v1/researchers/{researcher_id}/personalization-summary`
- Returns: Active interests count, strong expertise count, explicit preferences count, behavioral signals count, confidence tier, learned topics, learned types, learned delivery modes, and top positive/negative drivers.

### 2. Live Recommendation Explanation
`GET /api/v1/researchers/{researcher_id}/personalized-recommendations/{opportunity_id}/explanation`
- Returns: `RecommendationExplanationSchema` with grounded primary reasons, categorized factor breakdowns, safety status, deadline context, and score breakdown.

### 3. Historical Recommendation Explanation
`GET /api/v1/researchers/{researcher_id}/recommendation-history/{snapshot_id}/items/{opportunity_id}/explanation`
- Returns: Point-in-time frozen explanation from snapshot items.

---

## 9. Frontend Architecture & Accessibility

### Next.js Components
1. **`RecommendationExplanationModal.tsx`**:
   - Accessible dialog (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`, Escape key handling, backdrop click dismiss).
   - Progressive disclosure: High-level reasons displayed first; diagnostic mathematical breakdown toggleable on demand.
   - Non-reliance on color alone: Combines distinct icons (`CheckCircle2`, `AlertTriangle`, `TrendingUp`, `Sparkles`) with explicit text labels.
2. **`PersonalizationSummaryView.tsx`**:
   - Executive dashboard presenting total active signals, confidence level, and cold-start guidance.
   - Explicit vs. Learned comparison panels clearly distinguishing user-managed settings from Phase 3.6 inferences.
3. **`PersonalizedRankingPreview.tsx`**:
   - Enhanced recommendation cards featuring personalization strength badges, risk alerts, and a `[ Why this? ]` trigger.
   - Embedded Phase 3.6 feedback controls (`Save`, `Like`, `Dislike`, `Dismiss`).
4. **`RecommendationHistoryView.tsx`**:
   - Integrated snapshot item table with a `[ Why? ]` action button opening the historical explanation modal.

---

## 10. Known Boundaries & Limitations

1. **Phase 3.9 Boundary**: No machine learning, automated weight optimization, or collaborative filtering is implemented. Ranking remains strictly deterministic and bounded by Phase 3.5.
2. **Read-Only Explanations**: The explanation service does not mutate feedback, delete preferences, or alter recommendation records. Adjustments must be performed through Phase 3.3 preferences or Phase 3.6 feedback APIs.
