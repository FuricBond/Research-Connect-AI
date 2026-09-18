# Phase 4.3 Architecture — Research Submission Workflow & Document Management

## 1. Executive Overview

**Phase 4.3** evolves the submission management baseline established in Phase 4.2 into a comprehensive, researcher-owned preparation workflow. It provides strongly-typed artifact categorization, deterministic document lifecycle states, immutable version snapshots, a rules-based **Submission Readiness Engine**, chronological audit logging, and Next.js App Router UI integration.

Importantly, Phase 4.3 maintains strict boundary separation:
1. **Preparation Management vs. External Submission**: Phase 4.3 manages the researcher's local preparation checklist and readiness. It **never** executes external conference submissions, sends emails, calls third-party CFP APIs, or fabricates submission confirmations.
2. **Readiness vs. Submission Status**: Document readiness and submission status remain distinct concepts. A submission with all documents marked `READY` does not automatically become `SUBMITTED`, nor does reaching `READY` imply acceptance.
3. **Read-Only Deadline Intelligence**: Deadline intelligence from Phase 2.7 is consumed strictly in a read-only manner to provide urgency context and warnings; deadline urgency **never** mutates submission or document lifecycle states.
4. **Metadata & Reference Storage**: Cloud binary storage SDKs are deliberately decoupled. Document records track metadata (MIME type, size in bytes, SHA-256 checksum) and opaque storage reference identifiers (`s3://...`, `drive://...`, `file://...`), preventing vendor lock-in.

---

## 2. Domain Data Model

```
 ┌────────────────────────┐
 │ SavedOpportunityModel  │ (Workspace Item)
 └───────────┬────────────┘
             │ 1:N
             ▼
 ┌────────────────────────┐
 │ ResearchSubmissionModel│ (Submission Attempt)
 └─────┬────────────┬─────┘
       │ 1:N        │ 1:N
       ▼            ▼
 ┌───────────────┐ ┌──────────────────────────────┐
 │ DocumentModel │ │ ResearchSubmissionEventModel │ (Chronological Audit Trail)
 └───────┬───────┘ └──────────────────────────────┘
         │ 1:N
         ▼
 ┌─────────────────────────────┐
 │ DocumentVersionModel        │ (Immutable Snapshots)
 └─────────────────────────────┘
```

### 2.1 ResearchSubmissionDocumentModel
Table: `research_submission_documents`
- `id` (UUID, Primary Key)
- `submission_id` (UUID, FK -> `research_submissions.id` with `CASCADE` delete)
- `document_type` (Enum: `ABSTRACT`, `FULL_PAPER`, `COVER_LETTER`, `AUTHOR_BIO`, `CV`, `SUPPLEMENTARY`, `FIGURES`, `DATASET`, `CODE`, `DISCLOSURE`, `OTHER`)
- `title` (String 255)
- `description` (Text, optional)
- `status` (Enum: `REQUIRED`, `MISSING`, `DRAFT`, `READY`, `REJECTED`, `ARCHIVED`)
- `is_required` (Boolean, default `False`)
- `current_version` (Integer, default `1`)
- `file_metadata` (JSONB / JSON dict storing MIME type, file size, SHA-256 checksum, custom tags)
- `storage_reference` (String 500, optional URI / path)
- `completed_at` (DateTime with timezone, optional — timestamp when marked `READY`)
- `created_at` (DateTime with timezone)
- `updated_at` (DateTime with timezone)

### 2.2 ResearchSubmissionDocumentVersionModel
Table: `research_submission_document_versions`
- `id` (UUID, Primary Key)
- `document_id` (UUID, FK -> `research_submission_documents.id` with `CASCADE` delete)
- `version_number` (Integer)
- `title` (String 255)
- `file_metadata` (JSONB / JSON dict snapshot)
- `storage_reference` (String 500, optional)
- `checksum` (String 128, optional SHA-256 hash)
- `status` (String 50)
- `created_at` (DateTime with timezone)
- `created_by_id` (UUID, optional FK -> `users.id`)

### 2.3 ResearchSubmissionEventModel
Table: `research_submission_events`
- `id` (UUID, Primary Key)
- `submission_id` (UUID, FK -> `research_submissions.id` with `CASCADE` delete)
- `event_type` (Enum: `SUBMISSION_CREATED`, `METADATA_UPDATED`, `STATUS_TRANSITIONED`, `DOCUMENT_ADDED`, `DOCUMENT_UPDATED`, `DOCUMENT_VERSION_CREATED`, `DOCUMENT_STATUS_CHANGED`, `DOCUMENT_ARCHIVED`, `DOCUMENT_DELETED`, `READINESS_EVALUATED`)
- `document_id` (UUID, optional FK -> `research_submission_documents.id` with `SET NULL`)
- `description` (Text summary)
- `old_state` (JSONB / JSON dict, optional)
- `new_state` (JSONB / JSON dict, optional)
- `created_at` (DateTime with timezone)
- `created_by_id` (UUID, optional FK -> `users.id`)

---

## 3. Deterministic Readiness Engine

The Readiness Engine (`ResearchSubmissionDocumentService.evaluate_readiness`) calculates submission completeness and determines whether a submission may be advanced to `READY`.

### 3.1 Gated Transition Rule
```
Transition to READY is STRICTLY REJECTED with InvalidSubmissionTransitionError
if can_mark_submission_ready is False (i.e. len(blocking_issues) > 0).
```

### 3.2 Evaluation Outputs
- `overall_readiness`: `"READY"`, `"NOT_READY"`, `"BLOCKED"`, or `"UNKNOWN"`
- `can_mark_submission_ready`: Boolean (strictly `True` when 0 blocking issues exist)
- `readiness_percentage`: 0-100% completion of required documents and metadata
- `metadata_completeness`: 0.0-1.0 weighted completeness of core fields (`title`, `submission_type`, `abstract`, `venue`, `external_submission_id` or `submission_url`)
- `blocking_issues`: List of `SubmissionReadinessIssue` (`code`, `message`, `is_blocking=True`, `document_id`, `field`)
- `warnings`: List of non-blocking `SubmissionReadinessIssue` (`is_blocking=False`)
- `readiness_explanation`: Human-readable summary
- `deadline_context`: Grounded read-only Phase 2.7 deadline context

### 3.3 Readiness Rule Matrix
| Condition | Severity | Code | Overall State Impact |
|:---|:---|:---|:---|
| Required document status = `REJECTED` | Blocker | `REQUIRED_DOCUMENT_REJECTED` | `BLOCKED` |
| Required document status = `MISSING` or `REQUIRED` | Blocker | `MISSING_REQUIRED_DOCUMENT` | `NOT_READY` |
| Required document status = `DRAFT` | Blocker | `REQUIRED_DOCUMENT_IN_DRAFT` | `NOT_READY` |
| Empty submission title | Blocker | `EMPTY_TITLE` | `NOT_READY` |
| Deadline urgency `CRITICAL` or `URGENT` | Warning | `APPROACHING_DEADLINE` | Non-blocking |
| Deadline passed | Warning | `DEADLINE_PASSED` | Non-blocking |
| Optional document in `DRAFT` | Warning | `OPTIONAL_DOCUMENT_IN_DRAFT` | Non-blocking |
| Missing external submission tracking ID | Warning | `MISSING_EXTERNAL_TRACKING_ID` | Non-blocking |
| Zero document artifacts attached | Warning | `NO_DOCUMENTS_ADDED` | Non-blocking |

---

## 4. REST API Endpoints

All endpoints require researcher authentication (`X-User-ID` or JWT). Cross-researcher access attempts return `HTTP 403 Forbidden`.

| Method | Path | Description |
|:---|:---|:---|
| `POST` | `/api/v1/submissions/{id}/documents` | Create document artifact (creates initial v1 snapshot & audit event) |
| `GET` | `/api/v1/submissions/{id}/documents` | List documents with filtering (`status`, `document_type`, `is_required`) |
| `GET` | `/api/v1/submissions/{id}/documents/{doc_id}` | Retrieve single document with version history |
| `PATCH` | `/api/v1/submissions/{id}/documents/{doc_id}` | Update document; if `create_new_version=True`, snapshots previous version |
| `DELETE` | `/api/v1/submissions/{id}/documents/{doc_id}` | Permanently delete document artifact and all historical version snapshots |
| `GET` | `/api/v1/submissions/{id}/documents/{doc_id}/versions` | Retrieve immutable version snapshots for a document |
| `GET` | `/api/v1/submissions/{id}/readiness` | Evaluate deterministic readiness, blockers, warnings, and deadline context |
| `GET` | `/api/v1/submissions/{id}/history` | Retrieve chronological submission workflow audit trail |

---

## 5. Next.js App Router Frontend

The submission interface at `/workspace/[id]/submission` provides a unified tabbed workflow:

1. **Overview & Lifecycle**:
   - Visual 5-step lifecycle pipeline (`Draft`, `Ready`, `Submitted`, `Under Review`, `Decision`).
   - Grounded deadline alert badge with AoE indicator and remaining days.
   - Metadata editor with submission format, venue, external tracking ID, and rebuttal strategy.
   - Gated workflow transition controls preventing movement to `READY` when blockers exist.
2. **Documents & Checklist**:
   - Required vs. optional document categorization with visual badges.
   - Status chips (`REQUIRED`, `MISSING`, `DRAFT`, `READY`, `REJECTED`, `ARCHIVED`).
   - Fast "Mark Ready" toggle and "New Version" snapshot trigger.
   - Version history drawer detailing timestamps, SHA-256 hashes, and changelogs.
3. **Readiness Evaluation**:
   - Readiness score progress bar and status indicator pill.
   - Interactive blocker alerts explaining exact unsatisfied constraints.
   - Advisory warnings (e.g. approaching deadline, unentered portal IDs).
4. **Audit History**:
   - Chronological event timeline recording every creation, update, version advance, and status transition with actor IDs and change snapshots.

---

## 6. Safety Invariants Enforced

All 30 Phase 4.3 safety invariants are verified by the automated test suite (`backend/tests/test_phase4_3_invariants.py`):

1. Workspace existence does not imply document existence.
2. Submission existence does not imply document completion.
3. Document existence does not imply document readiness.
4. Optional documents do not become mandatory automatically.
5. Missing document != rejected document.
6. Rejected document != deleted document.
7. Archived document != missing document.
8. Version creation does not silently destroy previous versions.
9. Identical updates are idempotent where applicable.
10. Deadline urgency does not mutate document state.
11. Deadline urgency does not mutate submission state.
12. Deadline conflicts do not fabricate a canonical deadline.
13. Unknown timezone remains unknown.
14. Event dates cannot become submission deadlines.
15. Submission deadline cannot become document deadline.
16. Document readiness does not imply external submission.
17. READY preparation state does not imply SUBMITTED.
18. SUBMITTED does not imply ACCEPTED.
19. Cross-researcher document access is forbidden.
20. Cross-researcher readiness access is forbidden.
21. Audit events cannot be fabricated by read operations.
22. No external network requests occur.
23. No LLM calls occur.
24. Frontend performs no independent deadline calculations.
25. Existing ranking/relevance/risk behavior remains unchanged.
26. Existing Phase 2.7 deadline behavior remains unchanged.
27. Existing Phase 3 personalization/feedback behavior remains unchanged.
28. Existing Phase 4.1 workspace behavior remains unchanged.
29. Existing Phase 4.2 submission state machine remains unchanged.
30. No silent evidence/document metadata loss occurs.

---

## 7. Performance & Query Efficiency

- **Zero N+1 Queries**: Document listing and version snapshot fetching use eager joins (`joinedload`) and indexed foreign keys.
- **Bounded Query Execution**: Verified via `test_zero_n_plus_one_document_queries`; document listing execution requires $O(1)$ database round-trips regardless of document count.
- **No LLM Overhead**: All readiness scoring, rule evaluations, and version diffing operate via deterministic pure-Python algorithms.
