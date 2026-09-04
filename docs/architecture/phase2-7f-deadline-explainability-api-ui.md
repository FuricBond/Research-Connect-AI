# Phase 2.7F — Deadline Explainability + API + UI

**Status:** Completed  
**Branch:** `main`  
**Phase:** 2.7F  
**Architecture Layer:** Explainability, API, UI & Presentation Layer  
**Upstream Modules:** Phase 2.7B (Evidence Extraction), Phase 2.7C (Date & Timezone Normalization), Phase 2.7D (Urgency Engine), Phase 2.7E (Conflict, Extension & Multi-Deadline Intelligence)  

---

## 1. Executive Summary & Architectural Objective

Phase 2.7F integrates and exposes the academic deadline intelligence built across Phases 2.7B–2.7E through the complete application stack:
1. **Loss-Aware API Schemas**: Structured, strongly typed Pydantic models in `backend/app/schemas/deadline.py`.
2. **Deterministic Backend Explainability**: Zero-LLM, zero-database synthesis in `backend/app/ranking/deadline/explainability.py`.
3. **Backend API Endpoints**: Dedicated `GET /api/opportunities/{id}/deadlines` endpoint along with additive enrichments to `OpportunityRead` and `OpportunityMatchItem`.
4. **Frontend TypeScript Domain**: Lossless type mirrors in `frontend/src/types/opportunity.ts` and `frontend/src/types/discovery.ts`.
5. **Accessible Frontend Components**: Reusable `DeadlineBadge.tsx` and `DeadlineTimeline.tsx`.
6. **Unified Explainability Interface**: An integrated third tab within `ExplainabilityDrawer.tsx` alongside Ranking Relevance (Phase 2.5F) and Trust & Publication Safety (Phase 2.6F).

### Core Invariants & Design Principles
- **No Duplicate Logic**: The backend domain layer (`backend/app/ranking/deadline/`) remains the single source of truth. The frontend contains **zero** urgency scoring, **zero** temporal calculations, and **zero** conflict resolution heuristics.
- **Loss-Aware Serialization**: The API never collapses missing, ambiguous, invalid, expired, upcoming, due today, or disputed states into an uninformative `null`.
- **Zero Timezone Shifting**: Explicit timezone semantics (such as Anywhere on Earth / AoE) are faithfully preserved without silent conversion into local browser dates.
- **Zero N+1 Queries**: All endpoints evaluate deadlines in-memory from loaded opportunity models without triggering secondary database calls.
- **Strict Backward Compatibility**: Existing clients expecting `submission_deadline: string | null` continue to operate without disruption.

---

## 2. Architectural Data Flow

```text
Opportunity Model / Scraped Detail Data
                  │
                  ▼
Phase 2.7B: Deadline Evidence Extraction
  - Extracts raw strings, fields, sources, authority tiers
                  │
                  ▼
Phase 2.7C: Date & Timezone Normalization
  - Resolves ISO dates, AoE formulas, offsets, and IANA zones
                  │
                  ▼
Phase 2.7D: Deadline Intelligence & Urgency Engine
  - Calculates temporal status, seconds/days remaining, urgency tiers
                  │
                  ▼
Phase 2.7E: Multi-Source Conflict & Extension Engine
  - Discovers extensions, detects conflicts, resolves authoritative sources
                  │
                  ▼
Phase 2.7F: DeadlineExplainabilityService
  - Deterministic natural language synthesis & rationale attribution
                  │
                  ▼
Backend API Layer
  ├── Dedicated Route: GET /api/opportunities/{id}/deadlines
  ├── Entity Read: GET /api/opportunities/{id} (adds deadline_intelligence)
  └── Match Discovery: GET /api/v1/discovery/research/{id}/opportunities (adds deadline_explanation)
                  │
                  ▼
Frontend UI Layer
  ├── DeadlineBadge (compact, accessible status on cards)
  ├── DeadlineTimeline (multi-milestone academic lifecycle stepper)
  ├── OpportunityCard (integrated footer badge with 1-click timeline inspection)
  └── ExplainabilityDrawer ("Deadline Intelligence" tab with full breakdown)
```

---

## 3. Loss-Aware API Schemas

Located in `backend/app/schemas/deadline.py`, the schemas expose domain intelligence without data loss:

### 3.1 `NormalizedDeadlineSchema`
- `deadline_type`: Canonical milestone category (`SUBMISSION`, `NOTIFICATION`, `CAMERA_READY`, etc.).
- `local_date`: Standardized ISO date (`YYYY-MM-DD`).
- `local_time`: Time of day if specified.
- `timezone_name`: Explicit timezone name (e.g. `AoE`, `America/New_York`, `UTC`).
- `normalized_utc`: UTC timestamp corresponding to the absolute cutoff instant.
- `precision`: Temporal granularity (`DATE_ONLY`, `DATE_TIME`, `YEAR_MONTH`, etc.).
- `normalization_confidence`: Metric between 0.0 and 1.0 indicating confidence.

### 3.2 `DeadlineAssessmentSchema`
- `status`: Discrete temporal state (`UPCOMING`, `DUE_TODAY`, `EXPIRED`, `MISSING`, `INVALID`, `AMBIGUOUS`).
- `urgency_tier`: Semantic urgency class (`CRITICAL`, `URGENT`, `APPROACHING`, `DISTANT`, `DUE_TODAY`, `EXPIRED`, `UNKNOWN`).
- `urgency_score`: Continuous [0.0, 1.0] proximity value.
- `days_remaining`, `hours_remaining`, `minutes_remaining`: Authoritatively computed time deltas.

### 3.3 `DeadlineRevisionSchema`
- `classification`: Revision type (`INITIAL`, `UNCHANGED`, `EXTENDED`, `MOVED_EARLIER`, `REPLACED`, `RETRACTED`, `CONFLICTING`, `EQUIVALENT`).
- `days_diff`: Number of days the deadline shifted.
- `previous_observation`, `current_observation`: Observations tracing the revision lineage.
- `explanation`: Deterministic rationale describing the shift.

### 3.4 `CanonicalDeadlineViewSchema`
- `conflict_state`: Resolution state (`NO_CONFLICT`, `EQUIVALENT_SOURCES`, `SOURCE_CONFLICT`, `SUPERSEDED`, `INSUFFICIENT_EVIDENCE`).
- `selected_source`: Originating source chosen as authoritative.
- `confidence`: Composite confidence score.
- `deterministic_explanation`: Natural language rationale explaining status, urgency, and selection.
- `extension_reason`, `conflict_reason`, `source_selection_reason`: Attribution strings.
- `all_observations`: List of all competing/corroborating observations.

### 3.5 `OpportunityDeadlineSchema`
Composite container bundling all milestones for an academic venue:
- `primary_milestone`: Primary focus milestone (typically `SUBMISSION`).
- `primary_view`: Synthesized view for the primary milestone.
- `milestone_views`: Map of all individual milestone canonical views.
- `summary`: Multi-milestone deterministic synthesis.
- `has_extension`: Boolean flag indicating deadline extension.
- `has_conflict`: Boolean flag indicating unresolved or resolved source conflict.

---

## 4. Deterministic Explainability Engine

Located in `backend/app/ranking/deadline/explainability.py`, the `DeadlineExplainabilityService` generates precise natural language rationales with:
- **0 LLM calls**: 100% deterministic template formulation ensures constant-time execution (< 1ms).
- **0 Database queries**: Evaluates in-memory structures exclusively.
- **Attribution Coverage**:
  - Upcoming / Due Today / Expired temporal states with remaining day/hour countdowns.
  - Extension narratives detailing previous vs. current dates and the shift magnitude.
  - Conflict narratives identifying competing sources and explaining whether an authoritative source safely supersedes an older aggregator.
  - Absence / Ambiguity explanations clearly distinguishing lack of data from parsing ambiguity.

---

## 5. API Endpoints

### 5.1 Dedicated Endpoint
- **Route**: `GET /api/opportunities/{opportunity_id}/deadlines`
- **Response**: `OpportunityDeadlineSchema`
- **Behavior**: Retrieves the opportunity by ID and evaluates all milestone deadlines, returning the complete canonical view.

### 5.2 Opportunity Detail Enrichment
- **Route**: `GET /api/opportunities/{opportunity_id}`
- **Response**: `OpportunityRead`
- **Behavior**: Additively includes `deadline_intelligence: OpportunityDeadlineSchema | null`.

### 5.3 Research Opportunity Matching
- **Route**: `GET /api/v1/discovery/research/{work_id}/opportunities?explain=true`
- **Response**: `OpportunityMatchResponse`
- **Behavior**: Each `OpportunityMatchItem` includes `deadline_explanation: OpportunityDeadlineSchema | null`.

---

## 6. Frontend Presentation & UI Components

### 6.1 `DeadlineBadge.tsx`
Reusable component for displaying deadline status across lists and cards:
- **Urgency Tiers**: Dedicated styling for `CRITICAL` (crimson), `URGENT` (amber), `APPROACHING` (indigo), `DISTANT` (emerald), `DUE_TODAY` (violet), and `EXPIRED` (slate).
- **Special Badges**:
  - `+7d Extended`: Visual pill highlighting verified extensions.
  - `Verified`: Pill indicating authoritative source supersession.
  - `Conflicting sources`: Alert pill distinguishing disputed dates from missing dates.
- **Accessibility**: ARIA labels, semantic roles, keyboard navigation (`Enter` / `Space` triggers inspection), and high-contrast text.

### 6.2 `DeadlineTimeline.tsx`
Multi-milestone academic lifecycle stepper:
- Canonical ordering: `ABSTRACT` $\to$ `SUBMISSION` $\to$ `NOTIFICATION` $\to$ `CAMERA_READY` $\to$ `REGISTRATION` $\to$ `EVENT_START` $\to$ `EVENT_END`.
- Primary milestone indicator badge.
- Explicit timezone display (e.g. `2026-08-27 AoE`).
- Source badges and confidence ratings.
- Revision chips showing extension shifts.

### 6.3 `OpportunityCard.tsx`
- Replaced client-side date calculations with `<DeadlineBadge>`.
- Displays authoritative remaining time and status.
- Provides one-click action to inspect deadlines in the slide-over drawer.

### 6.4 `ExplainabilityDrawer.tsx`
Integrated third tab **"Deadline Intelligence"**:
- **Overview Card**: Primary milestone, temporal status tag, urgency tier with percentage score, remaining time, assessment confidence, and extension/conflict indicator.
- **Assessment Synthesis**: Natural language explanation generated by the backend.
- **Primary Deadline Details**: Localized deadline, UTC normalized cutoff, authoritative source, and source selection rationale.
- **Extension Breakdown**: Previous deadline, extended current deadline, shift in days, and extension notes.
- **Source Conflict & Precedence**: Disputed sources, raw extracted values, parsed dates, and conflict analysis.
- **Lifecycle Timeline**: Full `<DeadlineTimeline>` embedded seamlessly.

---

## 7. Verification & Test Suite

### Automated Backend Tests
- `backend/tests/test_deadline_api.py` (14 tests):
  - Loss-aware serialization across upcoming, due today, expired, missing, invalid, ambiguous, conflicting, and extended states.
  - Parity between domain model calculations and API serialization.
  - Dedicated endpoint integration (`GET /api/opportunities/{id}/deadlines`).
  - Additive detail endpoint verification (`GET /api/opportunities/{id}`).
  - Discovery matching integration with `explain=True`.
- Regression test suite:
  - `test_deadline_conflict_resolution.py` (26 tests)
  - `test_deadline_intelligence.py` (42 tests)
  - `test_date_timezone_normalization.py` (33 tests)
  - `test_deadline_evidence_extraction.py` (18 tests)
  - `test_ranking_signals.py` (21 tests)
  - **All 154 tests passing (100%)**.

### Frontend Validation
- `npm run build` (`tsc -b && vite build`):
  - 1,597 modules transformed.
  - Built cleanly in 1.17s with 0 TypeScript errors and 0 bundling warnings.

---

## 8. Summary of Completed Deliverables

| Deliverable | File Path | Status |
| :--- | :--- | :--- |
| **API Schemas** | `backend/app/schemas/deadline.py` | Complete |
| **Explainability Service** | `backend/app/ranking/deadline/explainability.py` | Complete |
| **Module Exports** | `backend/app/ranking/deadline/__init__.py` | Complete |
| **Extractor Enhancements** | `backend/app/ranking/deadline/extractors.py` | Complete |
| **Opportunity Schemas** | `backend/app/schemas/opportunity.py` | Complete |
| **Discovery Schemas** | `backend/app/schemas/discovery.py` | Complete |
| **Dedicated API Endpoints** | `backend/app/api/opportunities.py` | Complete |
| **Discovery Route Integration**| `backend/app/api/v1/discovery.py` | Complete |
| **API & Explainability Tests**| `backend/tests/test_deadline_api.py` | Complete (14/14 passed) |
| **Frontend TypeScript Types** | `frontend/src/types/opportunity.ts`, `discovery.ts` | Complete |
| **Frontend API Client** | `frontend/src/services/api.ts` | Complete |
| **Deadline Badge Component** | `frontend/src/components/discovery/DeadlineBadge.tsx` | Complete |
| **Deadline Timeline Component**| `frontend/src/components/discovery/DeadlineTimeline.tsx`| Complete |
| **Opportunity Card UI** | `frontend/src/components/discovery/OpportunityCard.tsx` | Complete |
| **Explainability Drawer Tab** | `frontend/src/components/discovery/ExplainabilityDrawer.tsx` | Complete |
| **Matching Page Wiring** | `frontend/src/pages/OpportunityMatches.tsx` | Complete |
| **UI Styles & Tokens** | `frontend/src/styles.css` | Complete |
