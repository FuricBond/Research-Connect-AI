# Phase 2.6F — Risk Explainability + API/UI Integration

**Status:** Completed  
**Branch:** `main`  
**Phase:** 2.6F  
**Architecture Layer:** Explainability & Presentation Layer  
**Upstream Modules:** Phase 2.6B (Evidence), Phase 2.6C (Scoring), Phase 2.6D (Venue Intelligence), Phase 2.6E (Suspicious Graph Intelligence)  

---

## 1. Executive Summary & Architectural Objective

Phase 2.6F exposes the multi-layered trust and risk intelligence constructed across Phases 2.6B–2.6E in a deterministic, transparent, provenance-backed, and user-facing manner through backend API schemas/endpoints and the frontend discovery UI.

Crucially:
- **Phase 2.6C remains the sole composite deterministic risk scorer**. Phase 2.6F introduces **zero duplicate scoring math** and zero hidden heuristics.
- It translates `(RiskAssessment, RiskEvidenceCollection)` into transparent, human-readable rationales, structured signal breakdowns, and provenance summaries.
- It strictly enforces **`UNKNOWN != PREDATORY`**: missing or incomplete metadata is treated as neutral and presented as an informational limitation, never as evidence of predatory practices.
- It uses conservative, non-defamatory academic wording (e.g. *"Potentially suspicious signal detected"*, *"High risk based on multiple corroborating signals"*).
- It provides **progressive disclosure** in the UI: default opportunity cards remain clean and compact with subtle badges and indicators, while deep-dive evidence, mathematical score decomposition, and source provenance are progressively disclosed via an interactive slide-over drawer.

---

## 2. Architectural Data Flow

```text
Opportunity / Venue Scraped Metadata
        ↓
Phase 2.6B: Risk Evidence Extraction (Domain, Trust, Editorial, Payment, Completeness)
        ↓
Phase 2.6D: Venue / Publisher Intelligence & Entity Resolution (DOAJ, Crossref, OpenAlex)
        ↓
Phase 2.6E: Suspicious Pattern & Graph Intelligence (AcademicTrustGraph)
        ↓
RiskEvidenceCollection
        ↓
Phase 2.6C: DeterministicRiskScoringEngine (SOLE COMPOSITE SCORER)
        ↓
RiskAssessment
        ↓
Phase 2.6F: RiskExplainabilityService (THIS PHASE)
        ↓
Backend API:
  - Dedicated Endpoint: GET /api/opportunities/{id}/risk-explanation
  - Discovery Matching: POST /api/v1/discovery/opportunities/match (with explain=True)
  - Opportunity Schemas: OpportunityRead, OpportunityMatchItem
        ↓
Frontend UI:
  - OpportunityCard: Compact status badge & contextual RiskWarning
  - RiskWarning: High / Moderate / Insufficient Evidence callouts with "Why? Inspect Evidence"
  - ExplainabilityDrawer: Dedicated "Trust & Publication Safety" tab with score decomposition & provenance tags
```

---

## 3. Core Models & Representations

### 3.1 `RiskEvidenceExplanation`
Represents an individual atomic evidence item with attribution and provenance:
- `signal`: Controlled vocabulary identifier (from `EvidenceSignal`).
- `category`: `POSITIVE_TRUST`, `NEGATIVE_SUSPICIOUS`, `NEUTRAL_UNKNOWN`.
- `strength`: `STRONG`, `MODERATE`, `WEAK`, `NONE`.
- `confidence`: `HIGH`, `MEDIUM`, `LOW`.
- `provenance`: Origin of evidence (`STATIC_TRUST_REGISTRY`, `EXTERNAL_VERIFICATION`, `GRAPH_ANALYSIS`, `SCRAPED_METADATA`, `NORMALIZED_METADATA`, `DERIVED`, `UNKNOWN`).
- `source_field`: Originating field (e.g. `publisher`, `website_url`, `description`).
- `matched_value`: Normalized token or phrase matched.
- `explanation`: Conservative, factual human-readable explanation.
- `is_present`: True for affirmative observations; False for missing metadata.
- `contribution`: Calculated effective score contribution from Phase 2.6C formulation (`base_weight * strength_multiplier * confidence_multiplier`).
- `severity`: Visual severity tier (`TRUST`, `HIGH`, `MODERATE`, `LOW`, `NEUTRAL`).
- `evidence_type`: Source category (`DIRECT_METADATA`, `VENUE_INTELLIGENCE`, `GRAPH_ANALYSIS`).
- `metadata`: Additional contextual attributes (e.g. cluster ID, regex pattern name).

### 3.2 `RiskExplanation`
The canonical explanation container derived from `RiskAssessment`:
- `opportunity_id`: UUID string of target opportunity.
- `risk_score`: Final calibrated risk score [0.00, 1.00].
- `risk_level`: `LOW_RISK`, `MODERATE_RISK`, `HIGH_RISK`, `INSUFFICIENT_EVIDENCE`.
- `risk_confidence`: Reliability score [0.00, 1.00].
- `evidence_sufficiency`: `SUFFICIENT`, `INSUFFICIENT`, `MINIMAL`.
- `is_predatory_flag`: Boolean flag from Phase 2.6C.
- `summary`: Deterministic, non-defamatory synthesis of findings.
- `positive_trust_signals`: Sorted list of affirmative trust evidence.
- `suspicious_signals`: Sorted list of suspicious indicators.
- `neutral_signals`: Sorted list of missing or unverified metadata observations.
- `graph_signals`: Sub-list of signals originating from graph topology.
- `venue_signals`: Sub-list of signals relating to venue/journal identity.
- `publisher_signals`: Sub-list of signals relating to publisher/organizer identity.
- `evidence_items`: Master list of all evidence items deterministically ordered.
- `risk_reasons`: Consolidated human-readable justifications.
- `provenance_summary`: Count of evidence items grouped by provenance source.
- `limitations`: Neutrality disclaimers and screening advisory scope statements.
- `gross_negative_score`: Gross suspicious score before trust mitigation.
- `trust_mitigation_score`: Positive trust score deducted from gross negative.
- `resolved_entity`: Serialized cross-source academic entity resolution data.

---

## 4. Semantic Rules & Academic Safety

1. **Unknown is Never Predatory**:
   - Missing fields (e.g. missing ISSN, missing publisher) produce `NEUTRAL_UNKNOWN` evidence items with 0.0 score contribution.
   - When evidence is sparse and uncorroborated, the venue is classified as `INSUFFICIENT_EVIDENCE` (Score: 0.00).
   - Limitations explicitly state: *"Missing metadata is neutral and does not indicate predatory behavior."*
2. **Defamation Safeguards**:
   - The system avoids absolute accusations such as "fraudulent", "scam", or "predatory conference".
   - It refers to "questionable editorial practices", "substandard review turnaround claims", or "cautionary domain characteristics".
3. **Anti-Correlation Single Presentation**:
   - When multiple graph paths detect the same underlying fact (e.g., an organizer cluster shared across 10 conferences), the explanation presents the underlying fact once with a consolidated topological note: *"Correlated graph topology signals consolidated; anti-correlation limits applied."*
4. **Mathematical Reconcilability**:
   - The UI and API expose the exact score arithmetic:
     $$\text{Final Risk Score} = \max(0.00, \min(1.00, \text{Gross Negative Score} - \text{Trust Mitigation}))$$

---

## 5. API Changes (Additive & Backward-Compatible)

### 5.1 Dedicated Endpoint
- **`GET /api/opportunities/{opportunity_id}/risk-explanation`**
  - **Response:** `RiskExplanationSchema` (HTTP 200)
  - **Error:** HTTP 404 if opportunity not found.
  - **Characteristics:** 100% in-memory, deterministic, zero external network calls, zero N+1 queries.

### 5.2 Schema Enhancements
- `OpportunityRead`: Additive optional fields `risk_level: str | None`, `risk_confidence: float | None`, `risk_explanation: RiskExplanationSchema | None`.
- `OpportunityListItem`: Additive optional fields `risk_level: str | None`, `risk_confidence: float | None`.
- `OpportunityMatchItem`: Additive optional field `risk_explanation: RiskExplanationSchema | None` populated when `explain=True`.

---

## 6. Frontend Progressive Disclosure

### 6.1 `RiskWarning.tsx`
- **High Risk:** Red banner with AlertTriangle icon, score percentage, ranking penalty badge (-80%), key justifications, and an interactive button: *"Why? Inspect Evidence"*.
- **Moderate Risk:** Amber banner with AlertCircle icon, score percentage, inline reasons, and an interactive button: *"Inspect Evidence"*.
- **Insufficient Evidence:** Neutral slate callout with HelpCircle icon: *"Limited Metadata Available (Neutral Assessment) — Insufficient evidence to establish verified trust or elevated risk."* with *"Details"* button.

### 6.2 `ExplainabilityDrawer.tsx`
- Adds a dedicated tab bar for opportunities:
  - **Matching Relevance (Phase 2.5F)**
  - **Trust & Publication Safety (Phase 2.6F)** with active risk level badge
- Trust & Publication Safety tab features:
  1. Overview card with Risk Level, Calibrated Risk Score, Assessment Confidence, and Evidence Sufficiency pill.
  2. Natural language assessment synthesis.
  3. Exact mathematical attribution: Gross Suspicious Score vs Trust Mitigation Deducted vs Final Bounded Score.
  4. Categorized evidence cards with explicit provenance pills (`[STATIC_TRUST_REGISTRY]`, `[GRAPH_ANALYSIS]`, `[SCRAPED_METADATA]`), strength, confidence, and score contributions.
  5. Cross-source resolved entity details (canonical venue name, publisher, ISSN-L).
  6. Provenance distribution breakdown and advisory limitations list.

---

## 7. Verification & Benchmark Results

- **Focused Tests (`backend/tests/test_risk_explainability.py`):** 32 / 32 passed (100%).
- **Full Risk Test Suite (2.6B, 2.6C, 2.6D, 2.6E, 2.6F):** 133 / 133 passed (100%).
- **Full Backend Suite (`backend/tests/`):** 526 passed, 8 skipped (100%).
- **Frontend Production Build (`npm run build`):** Clean compilation and bundling in 1.17s.
- **In-Memory Explanation Overhead:**
  - $N=10$: $< 5 \text{ ms}$
  - $N=50$: $< 20 \text{ ms}$
  - $N=100$: $< 45 \text{ ms}$
  - Zero database queries during explanation generation.
