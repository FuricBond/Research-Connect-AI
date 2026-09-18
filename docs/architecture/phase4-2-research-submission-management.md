# Phase 4.2 Architecture & Implementation: Research Submission Management & Tracking

## 1. Purpose

Phase 4.2 introduces **Research Submission Management & Tracking**, elevating ResearchConnect AI from opportunity discovery and workspace planning into a deterministic, production-grade manuscript submission and peer-review tracker.

By establishing a dedicated, foreign-keyed `ResearchSubmission` domain model linked directly to the Phase 4.1 workspace item (`SavedOpportunityModel`), researchers can record, update, track, and advance manuscript drafts, external submission portal identifiers, and review decisions throughout the academic publication lifecycle.

---

## 2. Scope

### In-Scope (Phase 4.2)
- **Canonical `ResearchSubmissionModel` Domain**: Dedicated table `research_submissions` foreign-keyed to `saved_opportunities.id` with cascade deletion.
- **Deterministic Submission State Machine**: Formal, non-cyclical lifecycle across 7 states: `DRAFT`, `READY`, `SUBMITTED`, `UNDER_REVIEW`, `ACCEPTED`, `REJECTED`, and `WITHDRAWN`.
- **Idempotency & Deterministic Validation**: Repeated identical transitions are idempotent; invalid transitions reject with detailed HTTP 400 Bad Request responses enumerating permitted targets.
- **Timestamp Lifecycle Triggers**: Automated timestamping (`submitted_at`, `decision_at`, `status_updated_at`) governed strictly by verified state transitions.
- **Documented Workspace Synchronization**: Explicit rule: transition to `SUBMITTED` promotes parent workspace opportunity to `APPLIED` (triggering Phase 3.6 recommendation feedback); transition to `ACCEPTED` promotes parent workspace opportunity to `ACCEPTED`.
- **Phase 2.7 Deadline Intelligence Grounding**: Submission views expose authoritative canonical deadline information (`submission_deadline`, `days_remaining`, `urgency_tier`, `is_aoe`, `has_extension`, `has_conflict`) directly from the Phase 2.7 explainability pipeline without client-side recalculation or date fabrication.
- **External Submission Portal Tracking**: Tracking external IDs (OpenReview, EasyChair, CMT, Editorial Manager) as opaque strings and portal URLs without vendor-specific schema constraints.
- **Strict Researcher Tenant Isolation**: Every submission operation is validated via `X-User-ID` against the parent workspace item's researcher ownership. Cross-tenant access is rejected with HTTP 403 Forbidden.
- **RESTful API Router**: Versioned endpoints under `/api/v1/submissions` and `/api/v1/workspace/{item_id}/submissions` supporting creation, pagination, filtering, metadata updates, state transitions, and deletion.
- **Zero N+1 Query Architecture**: Full eager loading (`joinedload`) across `submission -> workspace_item -> opportunity`.
- **Next.js 15+ App Router Frontend**: Interactive submission tracking UI at `/workspace/[id]/submission` featuring visual stepper pipelines, deadline alerts, editable manuscript fields, and transition controls.

### Out-of-Scope (Strict Phase Boundaries)
- Multi-party manuscript co-author collaboration and live document editing (*Deferred to Phase 4.3+*).
- File upload storage (AWS S3, Azure Blob, MinIO), PDF processing, or document extraction (*Deferred to Phase 4.3+*).
- Historical audit event log table and submission revision diffs (*Phase 4.3 Application History & Audit*).
- Google Calendar sync, iCal subscription feeds, and calendar agenda views (*Phase 4.4 Research Calendar*).
- Automated email digests, webhook notifications, and push alerts (*Phase 4.5 Notifications & Alerts*).
- Global executive research analytics dashboards (*Phase 4.6 Research Management Dashboard*).
- Modifications to core ranking, risk assessment, or ML recommendation scoring.

---

## 3. Architecture Overview

Phase 4.2 sits atop the foundation built across Phases 1 through 4.1:

```
┌─────────────────────────────────────────────────────────────┐
│                 Phase 1 & 2 Core Systems                    │
│    Opportunities • Deduplication • Deadline Intelligence     │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│             Phase 3 Researcher Personalization              │
│       Profiles • Preferences • Feedback Engine (3.6)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│           Phase 4.1 Opportunity Workspace                   │
│   SavedOpportunityModel (SAVED → PLANNING → APPLIED)        │
└──────────────────────────────┬──────────────────────────────┘
                               │ (1:N Foreign Key)
┌──────────────────────────────▼──────────────────────────────┐
│      Phase 4.2 Research Submission Management               │
│   ResearchSubmissionModel (DRAFT → SUBMITTED → ACCEPTED)    │
│   • Deterministic State Machine                             │
│   • Workspace Synchronization (SUBMITTED -> APPLIED)        │
│   • Portal URL & Tracking ID Storage                        │
│   • Next.js 15+ App Router Submission Workflow              │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Domain Model: `ResearchSubmissionModel`

### Table Schema (`research_submissions`)

```sql
CREATE TABLE research_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_item_id UUID NOT NULL REFERENCES saved_opportunities(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    abstract TEXT,
    submission_type VARCHAR(50) NOT NULL DEFAULT 'FULL_PAPER',
    status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
    external_submission_id VARCHAR(255),
    venue VARCHAR(255),
    submission_url VARCHAR(1000),
    notes TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    decision_at TIMESTAMP WITH TIME ZONE,
    status_updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_research_submissions_status CHECK (
        status IN ('DRAFT', 'READY', 'SUBMITTED', 'UNDER_REVIEW', 'ACCEPTED', 'REJECTED', 'WITHDRAWN')
    ),
    CONSTRAINT chk_research_submissions_type CHECK (
        submission_type IN ('FULL_PAPER', 'SHORT_PAPER', 'EXTENDED_ABSTRACT', 'POSTER', 'WORKSHOP_PAPER', 'GRANT_PROPOSAL', 'OTHER')
    )
);

CREATE INDEX idx_research_submissions_workspace_item ON research_submissions(workspace_item_id);
CREATE INDEX idx_research_submissions_status ON research_submissions(status);
CREATE INDEX idx_research_submissions_updated ON research_submissions(updated_at);
```

### Key Structural Decisions
1. **Direct Foreign Key to `saved_opportunities.id`**: Preserves single source of truth for researcher ownership. Researcher isolation is enforced through `workspace_item.user_id`.
2. **1:N Cardinality**: A workspace item can track multiple submission attempts (e.g. initial conference submission followed by a journal extension, or tracking multiple revisions) without artificial 1:1 constraints.
3. **Opaque External Tracking Identifiers**: `external_submission_id` and `submission_url` are validated for size and URL safety but treat external conference system identifiers as arbitrary opaque strings.
4. **Cascade Deletion**: When an opportunity is permanently removed from a workspace, its associated submission drafts and tracking records are cleanly cascade-deleted.

---

## 5. Submission State Machine

The submission lifecycle is deterministic, explicit, and non-bypassable.

```
       ┌────────────────────────┐
       │         DRAFT          │◄───────────┐
       └───────┬────────┬───────┘            │
               │        │                    │
         READY │        │ WITHDRAWN          │ DRAFT (Re-scoping)
               ▼        │                    │
       ┌────────────────▼───────┐            │
       │         READY          │            │
       └───────┬────────┬───────┘            │
               │        │                    │
     SUBMITTED │        │ WITHDRAWN          │
               ▼        │                    │
       ┌────────────────▼───────┐            │
       │       SUBMITTED        │            │
       └───────┬────────┬───────┘            │
               │        │                    │
  UNDER_REVIEW │        │ WITHDRAWN          │
               ▼        ▼                    │
       ┌────────────────────────┐            │
       │      UNDER_REVIEW      │            │
       └───┬────────┬───────┬───┘            │
           │        │       │                │
  ACCEPTED │        │       │ WITHDRAWN      │
           ▼        │       ▼                │
     ┌───────────┐  │  ┌───────────┐         │
     │ ACCEPTED  │  │  │ WITHDRAWN │         │
     └─────┬─────┘  │  └───────────┘         │
           │        │                        │
 WITHDRAWN │        │ REJECTED               │
           │        ▼                        │
           │  ┌───────────┐                  │
           └─►│ REJECTED  ├──────────────────┘
              └───────────┘
```

### Transition Matrix (`VALID_SUBMISSION_TRANSITIONS`)

| Current State | Permitted Target States | Side Effects / Rules |
| :--- | :--- | :--- |
| `DRAFT` | `READY`, `WITHDRAWN` | Editing metadata permitted. Deletion permitted. |
| `READY` | `DRAFT`, `SUBMITTED`, `WITHDRAWN` | Editing metadata permitted. |
| `SUBMITTED` | `UNDER_REVIEW`, `WITHDRAWN` | Sets `submitted_at = now()`. Synchronizes workspace item status to `APPLIED`. Triggers Phase 3.6 `APPLY` feedback signal. Deletion disallowed. |
| `UNDER_REVIEW` | `ACCEPTED`, `REJECTED`, `WITHDRAWN` | Peer review underway. Deletion disallowed. |
| `ACCEPTED` | `WITHDRAWN` | Sets `decision_at = now()`. Synchronizes workspace item status to `ACCEPTED`. Deletion disallowed. |
| `REJECTED` | `DRAFT` | Sets `decision_at = now()`. Allows transitioning back to `DRAFT` for re-targeting/revision. Deletion disallowed. |
| `WITHDRAWN` | *(Terminal, unless re-created)* | Marks submission cancelled/withdrawn. Deletion permitted. |

### Validation & Idempotency Rules
- **Idempotent Transitions**: A transition request where `current_status == target_status` succeeds idempotently without raising an error. If transition notes are supplied, they are recorded.
- **Deterministic Error Responses**: An invalid transition raises `InvalidSubmissionTransitionError`, translated by FastAPI to HTTP 400 Bad Request with a message detailing the current state, attempted state, and the list of permitted target states.
- **Deletion Safety**: Deleting an active submission in `SUBMITTED`, `UNDER_REVIEW`, `ACCEPTED`, or `REJECTED` status is blocked (HTTP 400). The researcher must explicitly withdraw the submission before deleting.

---

## 6. Workspace Synchronization Rules

The relationship between `SavedOpportunityModel` (workspace item) and `ResearchSubmissionModel` is governed by three strict invariants:

1. **Submission Does Not Imply Automatic Workspace Overwrite**:
   - Creating a submission draft does **not** alter the parent workspace status.
   - Transitioning between `DRAFT` and `READY` does **not** alter the parent workspace status.
2. **Explicit Forward Promotion on Submission**:
   - When a submission status changes to `SUBMITTED`: If the parent workspace item is in `SAVED`, `CONSIDERING`, or `PLANNING`, it is promoted to `APPLIED`.
   - Workspace promotion executes the Phase 3.6 `save_recommendation_feedback(..., feedback_type="APPLY")` hook, training personalized recommendation embeddings.
3. **Explicit Forward Promotion on Acceptance**:
   - When a submission status changes to `ACCEPTED`: If the parent workspace item is in `APPLIED`, it is promoted to `ACCEPTED`.
4. **No Reverse or Silent Workspace Mutation**:
   - Manually changing workspace status from the `/workspace` board never alters submission records.
   - Deleting a submission does not delete the workspace item or revert its status.

---

## 7. Deadline Intelligence Integration

Phase 4.2 consumes and exposes the canonical deadline assessments computed by the Phase 2.7 engine (`deadline_explainability_service`).

### Safety Invariants:
- **Zero Client-Side Recalculation**: The frontend renders deadline timestamps, urgency tiers, and remaining days computed authoritatively by the backend.
- **No Deadline Urgency Side Effects**: An impending or expired deadline never mutates a submission's status or workspace state automatically.
- **Handling Incomplete Temporal Evidence**:
  - Missing deadlines remain `None` (`days_remaining = null`, `urgency_tier = null`).
  - Anywhere-on-Earth deadlines preserve the `is_aoe: true` flag.
  - Extended deadlines preserve `has_extension: true` without resetting historical milestones.
  - Multi-source conflicts preserve `has_conflict: true` without fabricating artificial resolution dates.

---

## 8. REST API Contracts

All endpoints require authentication via `X-User-ID` header.

### Endpoints

| Method | Endpoint | Description | Status Codes |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/submissions` | Create a new research submission for a workspace opportunity | `201 Created`, `403 Forbidden`, `404 Not Found` |
| `GET` | `/api/v1/submissions` | List researcher submissions with status, type, workspace, and search filters | `200 OK` |
| `GET` | `/api/v1/submissions/summary` | Get aggregated submission metrics across lifecycle stages | `200 OK` |
| `GET` | `/api/v1/submissions/{id}` | Retrieve single submission with allowed transitions and deadline context | `200 OK`, `403 Forbidden`, `404 Not Found` |
| `PATCH` | `/api/v1/submissions/{id}` | Update metadata (title, abstract, tracking ID, URL, venue, notes) | `200 OK`, `403 Forbidden`, `404 Not Found` |
| `POST` | `/api/v1/submissions/{id}/transition` | Execute a deterministic state transition | `200 OK`, `400 Bad Request`, `403 Forbidden`, `404 Not Found` |
| `DELETE` | `/api/v1/submissions/{id}` | Permanently delete submission (allowed only in `DRAFT` or `WITHDRAWN`) | `204 No Content`, `400 Bad Request`, `403 Forbidden`, `404 Not Found` |
| `GET` | `/api/v1/workspace/{item_id}/submissions` | List all submissions linked to a specific workspace opportunity item | `200 OK`, `403 Forbidden`, `404 Not Found` |

---

## 9. Authorization & Tenant Isolation

Tenant isolation is verified at every entry point:

1. **Path-Based Ownership Validation**:
   ```python
   # ResearchSubmissionService.get_submission:
   if submission.workspace_item.user_id != resolved_user_id:
       raise PermissionError("Forbidden: You do not have permission to access this research submission.")
   ```
2. **Workspace Attachment Validation**:
   A researcher cannot attach a submission to another researcher's workspace item. Attempting to do so immediately raises `PermissionError` (HTTP 403).
3. **Scoped Listings & Summaries**:
   All list and summary queries join `SavedOpportunityModel` and filter strictly on `SavedOpportunityModel.user_id == resolved_user_id`.

---

## 10. Frontend Architecture (Next.js 15+ App Router)

The frontend implementation strictly adheres to the Next.js App Router and React 19 architecture:

- **Route**: `/workspace/[id]/submission` ([`frontend/app/workspace/[id]/submission/page.tsx`](file:///d:/Project/researchconnect-ai/frontend/app/workspace/%5Bid%5D/submission/page.tsx))
- **Parameter Resolution**: Utilizes `React.use(params)` to resolve route parameters asynchronously per React 19 standards.
- **Visual Stepper Component**: Visualizes progression across Draft, Ready, Submitted, Under Review, and Accepted/Rejected with distinct completion and active states.
- **Deadline Callout Card**: Renders authoritative countdowns, AoE indicators, extension banners, and urgency tiers.
- **Metadata Editing Form**: Synchronizes manuscript title, abstract, type selector, tracking ID, portal link, and notes.
- **Workspace Navigation Integration**: Cards on the `/workspace` board feature a direct "Submissions" link with icon badge.

---

## 11. Performance & Zero N+1 Queries

All submission queries use SQLAlchemy `joinedload` to eliminate N+1 queries:

```python
select(ResearchSubmissionModel)
.join(SavedOpportunityModel, ResearchSubmissionModel.workspace_item_id == SavedOpportunityModel.id)
.options(
    joinedload(ResearchSubmissionModel.workspace_item)
    .joinedload(SavedOpportunityModel.opportunity)
)
.where(SavedOpportunityModel.user_id == resolved_user_id)
```

- Query count for listing submissions is strictly $O(1)$ with respect to page size ($N$).
- Single-item retrieval executes bounded queries ($O(1)$) with zero secondary lazy loads.
- Indexed columns: `workspace_item_id`, `status`, `updated_at`.

---

## 12. Verification & Safety Invariants

| Invariant # | Invariant Description | Status |
| :--- | :--- | :--- |
| **INV-01** | Submission does not exist merely because a workspace item exists | **PASSED** |
| **INV-02** | Workspace status does not imply submission status | **PASSED** |
| **INV-03** | Submission status does not silently mutate workspace status | **PASSED** |
| **INV-04** | Deadline urgency does not mutate submission status | **PASSED** |
| **INV-05** | Deadline urgency does not mutate workspace status | **PASSED** |
| **INV-06** | Missing deadline is preserved as missing (`null`) | **PASSED** |
| **INV-07** | Unknown timezone is preserved as unknown | **PASSED** |
| **INV-08** | Ambiguous deadline never becomes fabricated | **PASSED** |
| **INV-09** | Event dates never become submission deadlines | **PASSED** |
| **INV-10** | Notification dates never become submission deadlines | **PASSED** |
| **INV-11** | Equal-authority deadline conflicts remain unresolved | **PASSED** |
| **INV-12** | Higher-authority deadline supersession follows Phase 2.7 rules | **PASSED** |
| **INV-13** | External submission IDs are never fabricated | **PASSED** |
| **INV-14** | `submitted_at` is only set through an explicit submission transition | **PASSED** |
| **INV-15** | `decision_at` is only set through accepted/rejected transitions | **PASSED** |
| **INV-16** | Invalid state transitions are rejected deterministically | **PASSED** |
| **INV-17** | Repeated identical transitions are idempotent | **PASSED** |
| **INV-18** | Cross-researcher access is rejected with HTTP 403 Forbidden | **PASSED** |
| **INV-19** | Existing ranking/relevance/risk behavior is unchanged | **PASSED** |
| **INV-20** | Frontend performs no independent deadline normalization or urgency calculation | **PASSED** |
| **INV-21** | No silent evidence loss in deadline intelligence | **PASSED** |
| **INV-22** | No hidden external submission or network action is performed | **PASSED** |
