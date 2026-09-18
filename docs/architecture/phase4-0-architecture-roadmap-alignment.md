# Phase 4.0 — Architecture & Roadmap Alignment

## 1. Executive Summary

ResearchConnect AI is an intelligent platform empowering researchers, students, and faculty to discover, match, and organize academic research opportunities (conferences, journals, workshops, CFPs, and grants). 

Following the successful completion of **Phases 1 through 3** (culminating in Phase 2.5 ranking optimization, Phase 2.6 risk/trust intelligence, Phase 2.7 deadline intelligence, and Phase 3 personalized researcher intelligence), the platform enters **Phase 4: Research Management & Researcher Workflow**.

The primary objective of **Phase 4.0 (Architecture & Roadmap Alignment)** is to establish a rigorous, authoritative architectural baseline before any Research Management code is implemented. This document audits the actual implemented codebase, resolves documentation contradictions, confirms the canonical Next.js App Router frontend architecture, codifies the authoritative product roadmap, and specifies the domain boundaries, invariants, and integration contracts governing Phase 4.

---

## 2. Current Repository State

A comprehensive audit of the repository reveals the following verified state:

| Subsystem | Actual State | Details |
| :--- | :--- | :--- |
| **Backend Framework** | Fully Implemented | FastAPI, Python 3.11+, Pydantic v2 schemas, SQLAlchemy 2.0 ORM, Alembic migrations. |
| **Database & Vector Store** | Fully Implemented | PostgreSQL 16 with `pgvector` extension (384-dimensional `all-MiniLM-L6-v2` embeddings, HNSW index, cosine similarity). |
| **Test Suite** | Fully Passing | 867 passed, 8 skipped across 54 test modules; zero-network, fully deterministic in-memory testing. |
| **Frontend Architecture** | Fully Implemented | Next.js 15.3+ (App Router), React 19, TypeScript 5.7+, Vanilla CSS tokens, Lucide React icons. |
| **Alembic Migrations** | Active (10 versions) | Migrations up to `0010_phase3_3_personal_preference_intelligence.py`. Models for Phase 3.6 (`researcher_recommendation_feedback`) and Phase 3.7 (`researcher_recommendation_snapshots`) registered in ORM `Base`. |
| **Opportunity Discovery & Search** | Fully Implemented | Hybrid lexical (PostgreSQL GIN tsvector) + semantic vector search fused via Reciprocal Rank Fusion (RRF). |
| **Risk / Predatory Detection** | Fully Implemented | Deterministic scoring engine, academic trust graph (`AcademicTrustGraph`), venue/publisher verification, explainable risk evidence. |
| **Deadline Intelligence** | Fully Implemented | Multi-source evidence extraction, UTC & timezone inference, urgency scoring, conflict resolution, loss-aware canonical deadline views, structured explainability. |
| **Researcher Intelligence** | Fully Implemented | Canonical researcher profile (`ResearchProfileModel`), interest/expertise extraction (`ResearcherInterestModel`), explicit & inferred preferences (`ResearcherPreferenceModel`), multi-channel candidate generation (`PersonalizedCandidateGenerationService`). |
| **Personalized Ranking** | Fully Implemented | Bounded personalization adjustments ($|adj| \le 0.15$), strict relevance dominance, risk/deadline safety invariants, tie-breaking, ablation diagnostics. |
| **Feedback Learning Loop** | Fully Implemented | Behavioral interaction tracking (VIEW, SAVE, INTERESTED, APPLY, DISMISS, NOT_INTERESTED) with exponential decay, saturation, and `SavedOpportunityModel` synchronization. |
| **Recommendation History & Evaluation** | Fully Implemented | Point-in-time immutable recommendation snapshots (`ResearcherRecommendationSnapshotModel`), IR metrics evaluation (P@K, R@K, MRR, NDCG, HitRate). |
| **Saved Opportunities** | Partially Implemented | Simple bookmark model (`SavedOpportunityModel` with `user_id`, `opportunity_id`, `notes`, `created_at`). No workflow states, stages, or kanban lifecycles. |
| **Research Management** | Not Implemented | Phase 4.1–4.7 features (Workspaces, Submission Tracker, Application History Audit, Calendar/iCal, Notifications, Dashboard) do not yet exist. |

---

## 3. Completed Phases

The repository has completed all planned foundations across Phases 1, 2, and 3:

### Phase 1 — Foundation
- PostgreSQL 16 + pgvector setup, SQLAlchemy 2.0 ORM, Alembic migration environment.
- Core `OpportunityModel` and CRUD API.
- Initial frontend scaffold.

### Phase 2 — Research Intelligence Engine
- **Phase 2.1**: Ingestion Hardening (WikiCFP source, deduplication, change detection, audit tracking).
- **Phase 2.2A & 2.2B**: Research Knowledge Integration (OpenAlex & Crossref API, canonical DOI resolution, citation enrichment).
- **Phase 2.3A & 2.3B**: Topic & Taxonomy Intelligence (canonical DAG, keyword extraction, 384-dim semantic embeddings, HNSW vector indexing).
- **Phase 2.4A–2.4K**: Hybrid Search & Intelligent Discovery (pgvector cosine retrieval, PostgreSQL GIN full-text search, RRF fusion, similar research retrieval, research-to-opportunity matching, hybrid ranking, explainability drawer, frontend discovery).
- **Phase 2.5A–2.5G**: Ranking Optimization (MMR diversity reranking, HHI concentration control, empirical evaluation).
- **Phase 2.6A–2.6G**: Trust & Predatory Detection (risk evidence extraction, deterministic scoring engine, publisher intelligence, academic trust graph, provenance-backed risk explainability, false-positive hardening).
- **Phase 2.7A–2.7G**: Deadline Intelligence & Urgency Engine (evidence extraction, UTC/timezone normalization, urgency tiers, multi-source conflict resolution, canonical deadline views, deadline explainability service).

### Phase 3 — Personalized Researcher Intelligence & Recommendations
- **Phase 3.1**: Researcher Profile Foundation (`ResearchProfileModel`, ORCID/OpenAlex linking, completeness scoring, REST API, Next.js UI).
- **Phase 3.2**: Research Interest Intelligence (`ResearcherInterestModel`, topic strength, confidence scoring, publication recency, REST API, Next.js UI).
- **Phase 3.3**: Personal Preference Intelligence (`ResearcherPreferenceModel`, explicit preference CRUD, activity-based inference from `SavedOpportunityModel`, contradiction checks, REST API, Next.js UI).
- **Phase 3.4**: Personalized Candidate Generation (multi-channel retrieval across explicit preferences, learned topics, and author expertise, REST API, Next.js UI).
- **Phase 3.5**: Personalized Hybrid Ranking (bounded personalization layer $\le 0.15$, relevance dominance, safety invariants, R0 vs R1 diagnostics, REST API, Next.js UI).
- **Phase 3.6**: Feedback & Recommendation Learning Loop (`ResearcherRecommendationFeedbackModel`, exponential decay, reversible signals, `SavedOpportunityModel` synchronization, REST API, Next.js UI).
- **Phase 3.7**: Recommendation History & Evaluation (`ResearcherRecommendationSnapshotModel`, reproducible point-in-time snapshots, offline IR metrics, REST API, Next.js UI).
- **Phase 3.8**: Personalization Explainability & Researcher UI (grounded attribution hierarchy, safety dominance, "Why this?" modal, personalization summary, Next.js UI).
- **Phase 3.9**: Evaluation, Ablation & Hardening (R0/R1/R2 IR evaluation, 10-state segmented evaluation, deterministic 6-signal ablation matrix, 15-scenario adversarial safety matrix A–O, strict `X-User-ID` ownership security across all 16 endpoints, performance benchmarks).

---

## 4. Frontend Architecture Decision

The frontend architecture decision is final and authoritative:

**NEXT.JS + APP ROUTER (Next.js 15.3+, React 19, TypeScript)**

- **Framework**: Next.js 15.3+ utilizing the App Router (`frontend/app/`).
- **Rendering Model**: Server-rendered foundations with targeted Client Components (`"use client"`) for interactive data visualizers and stateful modals.
- **Routing Structure**:
  - `/` — Discovery, Hybrid Search, and Filtering Home.
  - `/browse` — Categorized Opportunity Directory.
  - `/opportunities` — Opportunity Details, Deadline Intelligence, and Risk Explainability.
  - `/researcher` — Complete Researcher Workspace (Profile, Interests, Preferences, Candidate Preview, Ranking Preview, Feedback History, Recommendation History, Personalization Summary).
  - `/similar` — Similar Research Works Explorer.
- **Components**: Reusable, token-driven components located in `frontend/components/` (`discovery/`, `researcher/`, `pages/`).
- **Styling**: Native CSS tokens and modular stylesheets (`frontend/styles/`). TailwindCSS is not used in accordance with project constraints.
- **Type Safety**: Pydantic-mirrored TypeScript schemas in `frontend/types/`.

*Note*: Any historical documentation stating that the frontend is React + Vite or that Next.js is "planned for a future phase" is deprecated and hereby superseded.

---

## 5. Phase 4 Objective & Product Evolution Chain

Phase 4 introduces **Research Management & Researcher Workflow**. 

Crucially, Phase 4 does **not** replace or alter the discovery and recommendation engines. Instead, it builds the researcher productivity and workflow layer directly on top of the existing intelligence systems.

### Product Evolution Chain

```text
Opportunity Discovery (Phase 1, 2.1–2.4)
        ↓
Opportunity Intelligence: Trust & Deadlines (Phase 2.6, 2.7)
        ↓
Researcher Intelligence & Preferences (Phase 3.1–3.3)
        ↓
Personalized Recommendations (Phase 3.4–3.9)
        ↓
Research Management & Opportunity Workspace (Phase 4.1)
        ↓
Submission & Application Workflow (Phase 4.2–4.3)
        ↓
Research Calendar & Deadline Planning (Phase 4.4)
        ↓
Notifications & Proactive Alerts (Phase 4.5)
        ↓
Unified Research Management Dashboard (Phase 4.6)
```

The existing systems remain solely authoritative for:
- Opportunity discovery and candidate generation.
- Relevance scoring and hybrid ranking.
- Risk scoring, predatory detection, and trust explanations.
- Deadline extraction, timezone normalization, conflict resolution, and urgency classification.
- Researcher identity, academic expertise, and personal preferences.

Phase 4 consumes these capabilities as upstream inputs. It must never create competing or shadow versions of them.

---

## 6. Research Management Architecture

Research Management bridges the gap between *discovering* an opportunity and *tracking the end-to-end execution* of preparing, submitting, revising, and archiving research work.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Existing Intelligence Systems                         │
│   ┌──────────────────────┐ ┌──────────────────────┐ ┌────────────────────┐   │
│   │ Phase 2.7 Canonical  │ │   Phase 2.6 Trust    │ │  Phase 3 Profile & │   │
│   │ Deadline Engine      │ │   & Risk Detection   │ │  Personalization   │   │
│   └──────────┬───────────┘ └──────────┬───────────┘ └─────────┬──────────┘   │
└──────────────┼────────────────────────┼───────────────────────┼──────────────┘
               │                        │                       │
               ▼                        ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Phase 4: Research Management                           │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Phase 4.1 Opportunity Workspace                                       │  │
│  │ (Researcher-scoped states: SAVED, CONSIDERING, PLANNING, ARCHIVED)    │  │
│  └──────────────────────────────────┬────────────────────────────────────┘  │
│                                     │                                       │
│  ┌──────────────────────────────────▼────────────────────────────────────┐  │
│  │ Phase 4.2 & 4.3 Submission & Application Tracker                      │  │
│  │ (DRAFT → PREPARING → SUBMITTED → UNDER_REVIEW → DECISION)             │  │
│  │ (Immutable audit trail & history logging)                             │  │
│  └──────────────────┬────────────────────────────────┬───────────────────┘  │
│                     │                                │                      │
│  ┌──────────────────▼──────────────────┐ ┌───────────▼───────────────────┐  │
│  │ Phase 4.4 Research Calendar         │ │ Phase 4.5 Notifications       │  │
│  │ (Canonical milestones, iCal/Google) │ │ (Proactive alerts, digests)   │  │
│  └──────────────────┬──────────────────┘ └───────────┬───────────────────┘  │
│                     │                                │                      │
│  ┌──────────────────▼────────────────────────────────▼───────────────────┐  │
│  │ Phase 4.6 Unified Research Management Dashboard (Next.js App Router)  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Canonical Phase 4 Roadmap

The canonical roadmap for Phase 4 is structured as follows:

| Milestone | Subphase Title | Status | Scope & Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 4.0** | **Architecture & Roadmap Alignment** | **CURRENT / IN PROGRESS** | Full repository audit, documentation alignment, Next.js architecture formalization, roadmap codification, domain model decision criteria, invariant specification. |
| **Phase 4.1** | **Opportunity Workspace** | PLANNED / NOT IMPLEMENTED | Decision on `SavedOpportunityModel` vs `ResearchOpportunityWorkspace`, workflow stage transitions, researcher-scoped opportunity status management, REST API, Next.js Workspace view. |
| **Phase 4.2** | **Submission & Application Tracker** | PLANNED / NOT IMPLEMENTED | `ResearchSubmission` model, submission lifecycle tracking (DRAFT to DECISION), paper titles/abstract references, target deadlines, submission milestones, REST API, Next.js Tracker UI. |
| **Phase 4.3** | **Application History & Audit** | PLANNED / NOT IMPLEMENTED | Immutable audit logging of submission events, state transition history, outcome tracking, personal reporting analytics, data export. |
| **Phase 4.4** | **Research Calendar & Deadline Planning** | PLANNED / NOT IMPLEMENTED | Timeline visualization powered strictly by Phase 2.7 Deadline Intelligence, preparation milestones, iCal feed generation, Google Calendar integration. |
| **Phase 4.5** | **Notifications & Alerts** | PLANNED / NOT IMPLEMENTED | Event-driven and scheduled alert engine (approaching deadlines, deadline revisions, new matches), notification preferences, in-app notification center. |
| **Phase 4.6** | **Research Management Dashboard** | PLANNED / NOT IMPLEMENTED | Unified Next.js command center combining upcoming deadlines, active submissions, saved opportunities, personalized recommendations, and workflow summaries. |
| **Phase 4.7** | **Evaluation & Production Hardening** | PLANNED / NOT IMPLEMENTED | E2E workflow testing, multi-user isolation verification, audit trail verification, database query performance, stress testing, production readiness audit. |

---

## 8. Existing Domain Models Audit

The existing data models relevant to Research Management include:

### `OpportunityModel` (`app/models/opportunity.py`)
- **Role**: Authoritative catalog record for academic calls, conferences, and journals.
- **Fields**: `id`, `title`, `opportunity_type`, `submission_deadline`, `notification_date`, `camera_ready_deadline`, `event_start_date`, `event_end_date`, `indexing`, `risk_score`, `is_predatory_flag`, `status` (`ACTIVE`, `EXPIRED`, `ARCHIVED`, `DRAFT`, `UNVERIFIED`).
- **Invariant**: `OpportunityModel.status` represents the **ingestion and lifecycle state of the external opportunity itself**, never the user's personal workflow state.

### `UserModel` (`app/models/user.py`)
- **Role**: Platform user account model.
- **Fields**: `id`, `email`, `full_name`, `role` (`STUDENT`, `FACULTY`, `ADMIN`), `is_active`, `is_verified`.
- **Relationships**: 1:1 with `ResearchProfileModel`, 1:N with `SavedOpportunityModel`.

### `ResearchProfileModel` (`app/models/research_profile.py`)
- **Role**: Canonical researcher profile bridging platform user identity to academic knowledge graphs.
- **Fields**: `id`, `user_id`, `institution_id`, `academic_status`, `bio`, `canonical_researcher_id`, `orcid`, `openalex_id`, `keywords`.
- **Relationships**: 1:N with `ResearcherInterestModel`, `ResearcherPreferenceModel`, `ResearcherRecommendationFeedbackModel`, `ResearcherRecommendationSnapshotModel`.

### `SavedOpportunityModel` (`app/models/saved_opportunity.py`)
- **Role**: Minimal bookmarking entity.
- **Fields**:
  - `id`: UUID primary key.
  - `user_id`: Foreign key to `users.id` (CASCADE).
  - `opportunity_id`: Foreign key to `opportunities.id` (CASCADE).
  - `notes`: Optional user text note.
  - `created_at`: Timestamp (timezone-aware).
- **Constraints**: `UniqueConstraint("user_id", "opportunity_id")`.
- **Current Integrations**:
  - Phase 3.3 uses `SavedOpportunityModel` to derive `INFERRED` researcher preferences from platform activity.
  - Phase 3.6 `feedback_service.py` synchronizes `SavedOpportunityModel` when feedback of type `SAVE` is created or deleted.

---

## 9. Future Domain Models Direction

Phase 4 will introduce formal domain models for managing researcher workflows.

### Phase 4.1 Decision Criteria: `SavedOpportunityModel` Evolution vs Dedicated Workspace Model

A pivotal architectural decision in Phase 4.1 is whether to:
- **Option A: Extend `SavedOpportunityModel`** by adding workflow state fields (`workflow_state`, `priority`, `tags`, `updated_at`).
- **Option B: Introduce `ResearchOpportunityWorkspace` / `ResearchOpportunityStateModel`** as a dedicated workflow entity, keeping `SavedOpportunityModel` as a lightweight bookmarking primitive or refactoring it.

#### Decision Evaluation Matrix

| Evaluation Criteria | Option A: Extend `SavedOpportunityModel` | Option B: Dedicated `ResearchOpportunityWorkspace` |
| :--- | :--- | :--- |
| **Complexity** | Low. Single table modification via Alembic migration. | Moderate. Requires new table and migration. |
| **Phase 3 Compatibility** | High. Phase 3.3 and Phase 3.6 already reference `SavedOpportunityModel`. | Requires translation layer or migration to ensure Phase 3.3/3.6 behavioral signals remain intact. |
| **Separation of Concerns** | Moderate. Combines a simple bookmark with complex multi-stage workflow state. | Clean. Decouples lightweight bookmarking/signals from rich researcher project workflows. |
| **Workflow State Richness** | Bounded. May become cluttered if milestones, custom deadlines, and priority are attached. | Extensible. Accommodates rich metadata, custom tags, stage history, and submission links. |

**Phase 4.0 Recommendation**: The decision will be finalized in Phase 4.1 based on migration complexity and backward compatibility with Phase 3 feedback synchronization. If Option B is chosen, `SavedOpportunityModel` must either remain as the lightweight interaction primitive or be mapped cleanly to the initial `SAVED` workspace state.

#### Target Opportunity Workflow States (Phase 4.1)
Regardless of the model chosen, the future workspace will support the following discrete states:
- `SAVED` — Bookmarked for future consideration.
- `CONSIDERING` — Under active review or evaluation.
- `PLANNING` — Target opportunity selected; preparation in progress.
- `APPLIED` — Submission completed (linked to a `ResearchSubmission`).
- `ACCEPTED` — Manuscript or application accepted by the venue.
- `REJECTED` — Application not accepted.
- `ARCHIVED` — Removed from active workflow without losing history.

### Phase 4.2 Submission Model: `ResearchSubmission`
To support formal manuscript and grant application tracking, Phase 4.2 will introduce a dedicated submission model:

```text
Researcher (User/Profile)
    └── ResearchSubmission
            ├── opportunity_id (FK to OpportunityModel)
            ├── title (Manuscript / Grant / Paper Title)
            ├── abstract_ref (Abstract text or reference link)
            ├── status (SubmissionLifecycleState)
            ├── target_deadline (Timestamp from Phase 2.7)
            ├── submitted_at (Timestamp)
            ├── decision_at (Timestamp)
            ├── notes (Researcher annotations)
            └── created_at / updated_at
```

#### Submission Lifecycle States
- `DRAFT` — Paper idea / draft being outlined.
- `PREPARING` — Manuscript actively being drafted for this venue.
- `READY_TO_SUBMIT` — Final draft prepared, co-author approved.
- `SUBMITTED` — Officially submitted to the publisher / conference portal.
- `UNDER_REVIEW` — Under peer review / committee evaluation.
- `REVISION_REQUIRED` — Major/minor revisions requested.
- `ACCEPTED` — Formally accepted.
- `REJECTED` — Rejected.
- `WITHDRAWN` — Withdrawn by researcher.

### Phase 4.3 Application History & Audit
An immutable audit log (`ApplicationHistoryAuditModel` or event stream) recording every state transition, submission timestamp, and outcome for historical reporting and personal academic productivity analytics.

### Phase 4.4 & 4.5 Calendar & Notification Entities
- `ResearchCalendarEvent` (in-memory or cached view derived from Phase 2.7 deadlines + Phase 4.2 submission milestones).
- `NotificationRecord` / `NotificationPreference` (capturing alert channels, trigger criteria, and delivery status).

---

## 10. Integration & System Boundaries

Phase 4 enforces strict modular boundaries:

```text
[Phase 4: Research Management]
       │
       ├── Reads Opportunity Data ──────► [Phase 1 & 2 Core Models]
       ├── Reads Trust & Risk Flags ────► [Phase 2.6 Trust & Risk Engine]
       ├── Reads Deadlines & Urgency ───► [Phase 2.7 Canonical Deadline Views]
       ├── Reads Profile & Preferences ─► [Phase 3 Researcher Services]
       └── Syncs Interaction Feedback ──► [Phase 3.6 Feedback Service]
```

1. **No Duplicate Scraping**: Phase 4 never fetches or modifies source CFP data.
2. **No Duplicate Ranking**: Phase 4 displays recommendations using `PersonalizationRankingService` and never runs custom ranking algorithms.
3. **No Duplicate Risk Logic**: Phase 4 displays risk flags from `assess_opportunity_risk` / `risk_explainability_service`.
4. **No Duplicate Deadline Calculations**: Phase 4 consumes canonical deadlines from `deadline_explainability_service` and `OpportunityDeadlineSchema`.

---

## 11. Security & Ownership Boundaries

Research management data is private to the individual researcher.

1. **Strict User Scoping**: All workspace records, saved opportunities, submissions, and calendar milestones must be explicitly scoped to `user_id` / `researcher_id`.
2. **Mandatory Header Verification**: All Phase 4 endpoints must enforce `X-User-ID` authentication headers, matching the pattern established in Phase 3.9:
   ```python
   if str(profile.user_id) != x_user_id and str(profile.id) != x_user_id:
       raise HTTPException(
           status_code=status.HTTP_403_FORBIDDEN,
           detail="Forbidden: You do not have permission to access this researcher workflow",
       )
   ```
3. **Zero Cross-User Leakage**: A researcher can never view, mutate, or delete another researcher's workspace, submission drafts, or application history.
4. **Cascade Integrity**: Deleting a user account cascades to delete their workspace and submission records without compromising the global `OpportunityModel` catalog.

---

## 12. Deadline Intelligence Integration

Phase 4.4 (Calendar) and Phase 4.5 (Notifications) depend directly on the Phase 2.7 Deadline Intelligence engine.

### Integration Invariants
1. **Canonical Source of Truth**: `backend/app/ranking/deadline/` is the sole authority for deadline calculations.
2. **No Independent Parsing**: Neither the backend services nor the Next.js frontend may parse raw deadline strings or calculate urgency metrics independently.
3. **Canonical Deadline Consumption**: Workflow and calendar components must consume `OpportunityDeadlineSchema` / `CanonicalDeadlineView`:
   - `canonical_deadline_utc`: Absolute UTC timestamp for milestone scheduling.
   - `timezone_name` / `inferred_timezone`: Used for localized display.
   - `urgency_tier` (`CRITICAL`, `URGENT`, `NORMAL`, `RELAXED`): Used for calendar coloring and notification triggers.
   - `temporal_status` (`CURRENT`, `APPROACHING`, `PASSED`, `UNKNOWN`): Used for active vs expired filtering.
4. **Conflict Lineage Preservation**: When multi-source conflicts or deadline extensions occur, the calendar and notification views must expose the resolution reasons provided by `DeadlineConflictResolver`.

---

## 13. Ranking & Risk Intelligence Integration

Phase 4 interfaces seamlessly with existing ranking and risk engines:

1. **Risk Dominance in Workspaces**: If a saved opportunity is subsequently flagged as predatory ($is\_predatory = True$ or $risk\_score \ge 0.70$), the Opportunity Workspace must prominently display the trust warning and prevent accidental submission tracking without explicit user acknowledgment.
2. **Feedback Loop Continuity**: When an opportunity transitions to `SAVED` or `APPLIED` in Phase 4.1/4.2, a corresponding `ResearcherRecommendationFeedbackModel` event (`SAVE` or `APPLY`) is emitted to ensure Phase 3.6 behavioral learning stays current.
3. **Explicit Preferences Respected**: Personalization adjustments in recommendations within the workspace must remain bounded ($\le 0.15$) and subordinate to explicit user filters.

---

## 14. Next.js App Router Architecture

All Phase 4 user interfaces will be developed natively in Next.js:

- **Directory Layout**:
  - `frontend/app/workspace/page.tsx` — Opportunity Workspace & Kanban View.
  - `frontend/app/submissions/page.tsx` — Submission & Application Tracker.
  - `frontend/app/calendar/page.tsx` — Research Calendar & Deadline Planning.
  - `frontend/app/dashboard/page.tsx` — Unified Research Management Dashboard.
- **Component Design**:
  - Modular Client Components for interactive drag-and-drop workflow boards.
  - Reusable deadline and risk badges consuming existing API schemas (`OpportunityDeadlineSchema`, `RiskExplanationSchema`).
  - No client-side deadline math or timezone guessing; client components strictly format API-provided ISO timestamps.
- **Design Consistency**:
  - Retain dark/light tokens from `frontend/styles/tokens.css` and `frontend/styles/globals.css`.
  - Zero external CSS utility frameworks (no TailwindCSS).

---

## 15. Backward Compatibility Requirements

Phase 4 development must maintain full backward compatibility:

1. **Existing Endpoints**:
   - `/api/opportunities` and `/api/v1/discovery` must remain unchanged in request/response contracts.
   - `/api/v1/researchers` endpoints must retain their current behavior.
2. **Database Integrity**:
   - Existing records in `opportunities`, `users`, `research_profiles`, and `saved_opportunities` must not be corrupted or invalidated.
   - Any modifications to `saved_opportunities` must be performed via non-destructive Alembic migrations.
3. **Test Suite Invariant**:
   - All 867 existing backend unit and regression tests must continue to pass without alteration.
   - Frontend type-checking and Next.js production builds must remain error-free.

---

## 16. Deferred Functionality (Explicitly Excluded from Phase 4.0)

To avoid scope creep, the following capabilities are explicitly deferred and must **NOT** be implemented during Phase 4.0:

- No database tables or migrations for `ResearchSubmission`, `ResearchOpportunityWorkspace`, or `NotificationRecord`.
- No new API endpoints under `/api/v1/workspace`, `/api/v1/submissions`, or `/api/v1/calendar`.
- No background workers, Celery/Redis queues, or cron schedulers for notification delivery.
- No iCal `.ics` generation or Google Calendar OAuth integration.
- No collaborative multi-user editing or team workspaces.
- No machine learning or neural recommendation algorithms.

---

## 17. Phase 4.1 Entry Criteria

Phase 4.1 (Opportunity Workspace) may commence only when the following criteria are verified:

1. [x] Phase 4.0 Architecture & Roadmap document approved and committed.
2. [x] `README.md` updated to accurately reflect the Next.js App Router frontend and completed Phases 1–3.
3. [x] `docs/architecture/project-roadmap.md` updated with the authoritative Phase 4 breakdown.
4. [x] Backend test suite passing (867 tests).
5. [x] Frontend type-checking and Next.js build clean.
6. [x] Graphify knowledge graph updated.
7. [ ] Architectural sign-off on Option A (extend `SavedOpportunityModel`) vs Option B (new `ResearchOpportunityWorkspace` model).

---

## 18. Risks & Architectural Considerations

1. **State Synchronization Complexity**: If both `SavedOpportunityModel` and a separate workspace model exist simultaneously, state drift could occur between a "bookmark" and a "workspace item". *Mitigation*: Unify them or provide strict bi-directional synchronization in Phase 4.1.
2. **Timezone Misalignment in Calendar Views**: Calendars rendering deadlines in the user's local browser timezone could misinterpret "Anywhere on Earth" (AoE) deadlines. *Mitigation*: Always rely on `canonical_deadline_utc` and explicit timezone identifiers produced by Phase 2.7 `DeadlineNormalizer`.
3. **Notification Storms**: Poorly configured notification rules could generate duplicate alerts for deadline changes. *Mitigation*: Enforce deduplication hashes and rate limits on alert generation in Phase 4.5.
