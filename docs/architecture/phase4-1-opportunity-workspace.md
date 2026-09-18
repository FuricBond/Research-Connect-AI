# Phase 4.1 Architecture & Implementation: Opportunity Workspace

## 1. Objective

Phase 4.1 delivers the **Opportunity Workspace**, transitioning ResearchConnect AI from an exploratory discovery and recommendation platform (Phases 1–3) into an actionable, researcher-controlled research management system. The workspace enables authenticated researchers to organize, prioritize, tag, annotate, and track saved academic opportunities through a deterministic workflow lifecycle.

---

## 2. Scope

### In-Scope (Phase 4.1)
- **Unified Workspace & Saved Opportunity Domain**: Extending the existing bookmarking system to function as a full workflow state machine.
- **Deterministic State Machine**: Explicit transitions across 7 states: `SAVED`, `CONSIDERING`, `PLANNING`, `APPLIED`, `ACCEPTED`, `REJECTED`, and `ARCHIVED`.
- **Researcher Ownership & Isolation**: Strict tenant isolation enforced at the database and service layer via `X-User-ID`. Cross-user access returns HTTP 403 Forbidden.
- **Enriched Metadata**: Workflow priorities (`LOW`, `MEDIUM`, `HIGH`, `URGENT`), user notes, and arbitrary string tags.
- **RESTful API**: Nine endpoints under `/api/v1/workspace` supporting listing, creation, single retrieval, metadata patching, state transitions, archiving, unarchiving, and deletion.
- **Zero N+1 Query Architecture**: Eager relationship loading (`joinedload`) coupling workspace items to canonical opportunity entities with integrated deadline and risk summaries.
- **Next.js 15+ App Router Frontend**: Interactive workspace UI at `/workspace` with pipeline tabs, stats strip, filter bar, card controls, editable notes, tag chips, and canonical intelligence display.
- **Phase 3.6 Backward Compatibility**: Full bidirectional synchronization with the feedback engine (`SAVE` on workspace add, `APPLY` on status transition to `APPLIED`).

### Out-of-Scope (Deferred to Later Phases)
- Submission tracking, manuscript files, co-author lists, and tracking IDs (*Phase 4.2*).
- Historical audit event log and submission version history (*Phase 4.3*).
- Calendar views, Google Calendar sync, and iCal exports (*Phase 4.4*).
- Notification dispatch, email digests, and automated deadline reminders (*Phase 4.5*).
- Executive management analytics dashboards (*Phase 4.6*).
- Ranking algorithm adjustments or ML personalization changes.

---

## 3. Architecture Decision: Option A vs Option B

Phase 4.0 identified an architectural fork for Phase 4.1:

| Dimension | Option A: Extend `SavedOpportunityModel` | Option B: Dedicated `ResearchOpportunityWorkspaceModel` |
| :--- | :--- | :--- |
| **Data Redundancy** | **Zero redundancy**. Single row per researcher-opportunity pair. | High redundancy. Separate bookmark and workspace records, requiring synchronization. |
| **Phase 3.6 Feedback Sync** | **Native**. `SAVE` and `APPLY` feedback hooks map 1:1 to existing model semantics without foreign-key indirection. | Complex. Requires multi-table event listeners or duplicate feedback hooks. |
| **Query Performance** | **Single joined query**. Zero join overhead between "saved" and "workspace" states. | Requires multi-table joins or dual-query hydration to determine if a saved item is in the workspace. |
| **User Mental Model** | **Unified**. Saving an opportunity places it into the researcher's workflow pipeline at `SAVED`. | Fragmented. Researcher must "save" an opportunity, then separately "add to workspace". |
| **Migration Safety** | **Non-destructive additive migration**. Adds nullable/defaulted columns (`status`, `priority`, `tags`, `updated_at`, `status_updated_at`, `archived_at`). | Requires creating a new table and backfilling historical saved opportunities. |
| **Future Extensibility** | **Clean anchor point**. Phase 4.2 `ResearchSubmission` can easily declare a Foreign Key to `saved_opportunities.id`. | Equivalent extensibility. |

### Decision
**Option A was selected and implemented.**

To maintain clean domain boundaries and domain-driven design, `SavedOpportunityModel` was augmented with workflow fields, and the alias `ResearchOpportunityWorkspaceModel = SavedOpportunityModel` was exported from `app.models`. This delivers seamless backward compatibility with all Phase 3 recommendation and feedback services while establishing a robust foundation for Phase 4.2+ tracking.

---

## 4. Data Model

### Database Schema (`saved_opportunities`)

```sql
ALTER TABLE saved_opportunities
    ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'SAVED',
    ADD COLUMN priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    ADD COLUMN tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ADD COLUMN status_updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ADD COLUMN archived_at TIMESTAMP WITH TIME ZONE;

-- Constraints
ALTER TABLE saved_opportunities
    ADD CONSTRAINT chk_saved_opp_status CHECK (
        status IN ('SAVED', 'CONSIDERING', 'PLANNING', 'APPLIED', 'ACCEPTED', 'REJECTED', 'ARCHIVED')
    ),
    ADD CONSTRAINT chk_saved_opp_priority CHECK (
        priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')
    );

-- Indexes for efficient researcher-scoped queries
CREATE INDEX ix_saved_opp_user_status ON saved_opportunities (user_id, status);
CREATE INDEX ix_saved_opp_user_priority ON saved_opportunities (user_id, priority);
CREATE INDEX ix_saved_opp_user_updated_at ON saved_opportunities (user_id, updated_at DESC);
```

### Alembic Migration
- **Revision ID**: `0011_phase4_1_opportunity_workspace`
- **Revises**: `0010_phase3_3_personal_preference_intelligence`
- **Characteristics**: Explicit, non-destructive, reversible (`upgrade` and `downgrade` fully implemented), safe for both PostgreSQL and SQLite.

---

## 5. Workflow State Machine

The workspace enforces a deterministic, validated state machine. Arbitrary status jumps are rejected with HTTP 400 Bad Request.

```
                  ┌──────────────┐
                  │    SAVED     │
                  └──────┬───────┘
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
    ┌──────────────┐            ┌──────────────┐
    │ CONSIDERING  ├───────────►│   PLANNING   │
    └──────┬───────┘            └──────┬───────┘
           │                           │
           │                           ▼
           │                    ┌──────────────┐
           │                    │   APPLIED    │
           │                    └──────┬───────┘
           │                           │
           │             ┌─────────────┴─────────────┐
           │             ▼                           ▼
           │      ┌──────────────┐            ┌──────────────┐
           │      │   ACCEPTED   │            │   REJECTED   │
           │      └──────┬───────┘            └──────┬───────┘
           │             │                           │
           └─────────────┼─────────────┬─────────────┘
                         │             │
                         ▼             ▼
                  ┌────────────────────────────┐
                  │          ARCHIVED          │
                  └────────────────────────────┘
```

### Valid State Transitions

| From Status | Allowed Target Statuses | Semantic Meaning |
| :--- | :--- | :--- |
| `SAVED` | `CONSIDERING`, `PLANNING`, `ARCHIVED` | Initial bookmarking; researcher chooses to evaluate or plan submission. |
| `CONSIDERING` | `PLANNING`, `SAVED`, `ARCHIVED` | Actively reviewing CFP requirements; demote back to Saved or promote to Planning. |
| `PLANNING` | `APPLIED`, `CONSIDERING`, `SAVED`, `ARCHIVED` | Preparing draft; finalize by applying or stepping back. |
| `APPLIED` | `ACCEPTED`, `REJECTED`, `PLANNING`, `ARCHIVED` | Under peer review; record decision or revert to Planning if un-submitted. |
| `ACCEPTED` | `ARCHIVED`, `APPLIED` | Terminal success; can be archived or reverted to Applied (admin correction). |
| `REJECTED` | `ARCHIVED`, `PLANNING` | Terminal rejection; can be archived or reverted to Planning for revised re-targeting. |
| `ARCHIVED` | `SAVED`, `CONSIDERING`, `PLANNING`, `APPLIED` | Restoring archived opportunities back to the active research workflow. |

### State Machine Rules
1. **Idempotency**: Transitioning from `S -> S` is a deterministic no-op returning the current record without error.
2. **Invalid Transitions**: Any transition not in the transition table raises `InvalidTransitionError` and returns HTTP 400 with a detailed error listing allowed target states.
3. **No Hidden Transitions**: Deadlines, risk ratings, or recommendation updates never modify workspace status automatically. Status changes are strictly researcher-initiated.
4. **Timestamp Invariants**:
   - `created_at`: Set once upon creation, immutable.
   - `updated_at`: Refreshed on any metadata change (notes, priority, tags) or status change.
   - `status_updated_at`: Updated exclusively when `status` transitions.
   - `archived_at`: Populated when status becomes `ARCHIVED`; set to `NULL` upon unarchive.

---

## 6. Ownership & Authorization Model

Researcher isolation is strictly enforced at every layer:
1. **Header Identification**: The authenticated researcher identity is passed via the `X-User-ID` header.
2. **Dual-Key Resolution**: Supports both `UserModel.id` and `ResearchProfileModel.id` by resolving profile keys to canonical user IDs automatically via `WorkspaceService.resolve_user_id`.
3. **Cross-Tenant Prevention**: Every operation queries by `SavedOpportunityModel.id`. If the record belongs to another user, `WorkspaceService.get_workspace_item` raises `PermissionError`, returning HTTP 403 Forbidden.
4. **Tenant-Scoped Writes**: All insert, update, archive, and delete operations use the resolved `user_id`, preventing researchers from spoofing workspace items.

---

## 7. API Contracts (`/api/v1/workspace`)

| Method | Path | Status Code | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/workspace` | `201 Created` / `200 OK` | Add opportunity to workspace (idempotent: returns 200 if already exists). |
| `GET` | `/api/v1/workspace` | `200 OK` | List researcher workspace opportunities with filters and pagination. |
| `GET` | `/api/v1/workspace/summary` | `200 OK` | Aggregated statistics (active, archived, by status, by priority). |
| `GET` | `/api/v1/workspace/{id}` | `200 OK` | Retrieve single workspace opportunity with `allowed_transitions`. |
| `PATCH` | `/api/v1/workspace/{id}` | `200 OK` | Partially update metadata (priority, notes, tags). |
| `POST` | `/api/v1/workspace/{id}/transition` | `200 OK` / `400 Bad Request` | Deterministically transition workflow status. |
| `POST` | `/api/v1/workspace/{id}/archive` | `200 OK` | Move opportunity to `ARCHIVED` state. |
| `POST` | `/api/v1/workspace/{id}/unarchive` | `200 OK` | Restore opportunity from `ARCHIVED` to active workflow state. |
| `DELETE` | `/api/v1/workspace/{id}` | `204 No Content` | Remove opportunity from workspace. |

### Query Parameters for `GET /api/v1/workspace`
- `status`: Filter by `WorkspaceStatus`.
- `priority`: Filter by `WorkspacePriority`.
- `tag`: Case-insensitive substring match on tags.
- `search`: Lexical search across opportunity title and user notes.
- `include_archived`: Boolean flag (default `false`) controlling visibility of archived items.
- `sort_by`: `updated_at` (default), `created_at`, `deadline`, `priority`, `status`.
- `sort_order`: `desc` (default) or `asc`.
- `limit` (max 100) & `offset` for pagination.

---

## 8. Frontend Architecture (Next.js 15 App Router)

- **Route**: `frontend/app/workspace/page.tsx`
- **Framework**: Next.js 15+ App Router with React 19 and TypeScript.
- **Styling**: `frontend/styles/workspace.css` utilizing system CSS variables and modern card aesthetics.
- **Navigation**: Integrated into `DiscoveryNavbar.tsx` with a dedicated "Opportunity Workspace" link.

### Key UI Capabilities
1. **Summary Statistics Strip**: Real-time display of Active Pipeline, Considering/Planning, Applied, Accepted, and Archived counts.
2. **Pipeline Tabs**: Instant tabbed filtering by `ALL`, `SAVED`, `CONSIDERING`, `PLANNING`, `APPLIED`, `ACCEPTED`, `REJECTED`, and `ARCHIVED`.
3. **Filter Bar**: Full-text search, priority dropdown, and tag filter.
4. **Canonical Opportunity Intelligence Strip**: Displays backend-computed deadline status, days remaining, urgency tier, and predatory risk level without performing client-side recalculations.
5. **Interactive Controls**:
   - Status transition buttons dynamically rendered based on the item's `allowed_transitions`.
   - Priority selector dropdown.
   - Inline notes editor with autosave/manual save.
   - Interactive tag chips with inline addition (`+ Add tag`) and deletion (`x`).
   - Quick archive and restore actions.
   - Deletion confirmation dialog.

---

## 9. Query & Performance Strategy

- **Zero N+1 Queries**: List and detail queries use SQLAlchemy `joinedload(SavedOpportunityModel.opportunity)` to fetch workspace items and their associated opportunity in a single query.
- **Server-Side Aggregations**: The summary endpoint aggregates status and priority counts directly in the database without serializing entire objects.
- **Compound Database Indexes**:
  - `(user_id, status)` optimizes status filtering and tab switching.
  - `(user_id, priority)` optimizes priority-based triage.
  - `(user_id, updated_at DESC)` ensures efficient chronological sorting.

---

## 10. Backward Compatibility

Phase 4.1 guarantees 100% backward compatibility with all prior phases:
- **Phase 1 Foundation**: Unaltered.
- **Phase 2.5 Hybrid Ranking**: Ranking algorithms, RRF fusion, and scoring functions remain untouched. Workspace status does not alter search or recommendation relevance scores.
- **Phase 2.6 Predatory Risk Intelligence**: Risk scoring, evidence extraction, and explainability remain canonical.
- **Phase 2.7 Deadline Intelligence**: Deadline normalization, AoE handling, and conflict resolution remain canonical.
- **Phase 3.3 Preference Intelligence**: Inferred and explicit preference models continue to operate normally.
- **Phase 3.6 Feedback Synchronization**: Adding an item to the workspace synchronizes a `SAVE` feedback signal; moving an item to `APPLIED` synchronizes an `APPLY` feedback signal.
- **Existing Saved Opportunity API**: Existing `/api/v1/opportunities/{id}/save` calls remain functional, defaulting newly saved items to `status=SAVED`, `priority=MEDIUM`.

---

## 11. Security & Authorization

- **No Implicit Trust**: Client-supplied user IDs in request bodies are ignored. Authenticated identity is resolved exclusively from `X-User-ID`.
- **403 Forbidden on Unauthorized Access**: Attempting to read, patch, transition, archive, or delete another researcher's workspace item returns HTTP 403 Forbidden.
- **Input Sanitization**: Pydantic v2 schemas strip extraneous whitespace and validate enum constraints prior to database execution.
- **Tag Normalization**: Tags are sanitized and deduplicated before persistence.

---

## 12. Testing & Verification Results

### Test Execution Summary
- **Workspace Service Suite** (`tests/test_workspace_service.py`): 8 tests passed.
- **Workspace API Suite** (`tests/test_workspace_api.py`): 8 tests passed.
- **Regression Suites**:
  - `test_opportunities.py`: 10 passed.
  - `test_feedback_learning.py`: 17 passed.
  - `test_researcher_profile.py`: 29 passed.
  - `test_deadline_api.py`: 14 passed.
  - **Total Focused Regression Tests**: 76 passed.
- **Full Backend Suite**: 883 tests passed.
- **Frontend Type-Check**: `npm run type-check` exited with code 0 (zero errors).
- **Frontend Production Build**: `npm run build` compiled successfully, statically prerendering `/workspace` (5.48 kB).

---

## 13. Limitations

- **Single Researcher Ownership**: Phase 4.1 does not support collaborative or shared workspace folders across multiple researchers.
- **No File Uploads**: Manuscript attachments, supplementary files, and submission PDFs are deferred to Phase 4.2.
- **No Background Push Notifications**: Automated deadline alerts are deferred to Phase 4.5.

---

## 14. Future Compatibility with Phases 4.2–4.7

Phase 4.1 was architected with explicit foreign key extension points:
- **Phase 4.2 (Submission Tracker)**: `ResearchSubmissionModel` will reference `saved_opportunity_id` (foreign key to `SavedOpportunityModel.id`), linking submissions directly to workspace items.
- **Phase 4.3 (Application History & Audit)**: Audit events will record `workspace_id`, `from_status`, `to_status`, and `timestamp` upon state machine transitions.
- **Phase 4.4 (Research Calendar)**: Calendar views will query workspace opportunities with active submission deadlines (`status IN ('SAVED', 'CONSIDERING', 'PLANNING')`).
- **Phase 4.5 (Notifications & Alerts)**: Alert engine will monitor approaching deadlines for items in `PLANNING` or `CONSIDERING`.
- **Phase 4.6 (Management Dashboard)**: Dashboard metrics will aggregate `counts_by_status` and `counts_by_priority` directly from `WorkspaceService.get_summary`.
