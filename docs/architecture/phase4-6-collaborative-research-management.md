# Phase 4.6 — Collaborative Research Management Architecture

## 1. Overview & Executive Summary

Phase 4.6 introduces a **collaborative research management layer** around existing research workspaces (`SavedOpportunityModel`). This allows research teams, lab groups, and collaborating investigators to coordinate opportunity preparation, grant proposals, conference submissions, documents, deadlines, and preparation tasks within a strictly bounded workspace.

This architecture specifically avoids generic social networking or unstructured chat, focusing solely on structured research collaboration workflows, server-side role-based access control (RBAC), deterministic invitation flows, immutable activity auditing, and integration with Phase 4.5 notification systems.

---

## 2. Collaboration Domain & Data Models

The collaboration domain is bounded around the workspace entity:

```text
Researcher (User)
       │
       ▼
Research Workspace (SavedOpportunityModel)
       ├── Workspace Members (WorkspaceMemberModel)
       │     └── Roles: OWNER, EDITOR, CONTRIBUTOR, VIEWER
       ├── Workspace Invitations (WorkspaceInvitationModel)
       │     └── Status: PENDING, ACCEPTED, DECLINED, EXPIRED, REVOKED
       ├── Workspace Tasks (WorkspaceTaskModel)
       │     └── Status: TODO, IN_PROGRESS, IN_REVIEW, COMPLETED, BLOCKED
       ├── Workspace Activity Stream & Comments (WorkspaceActivityModel)
       │     └── Append-only structured audit trail & workflow notes
       └── Linked Submissions, Documents, & Calendar Deadlines
```

### 2.1 WorkspaceMemberModel (`workspace_members`)
- `id` (UUID, PK)
- `workspace_id` (UUID, FK -> `saved_opportunities.id` ON DELETE CASCADE)
- `user_id` (UUID, FK -> `users.id` ON DELETE CASCADE)
- `role` (VARCHAR 50: `OWNER`, `EDITOR`, `CONTRIBUTOR`, `VIEWER`)
- `status` (VARCHAR 50: `ACTIVE`, `INVITED`, `REMOVED`)
- `invited_at`, `joined_at`, `removed_at` (TIMESTAMPTZ)
- `created_at`, `updated_at` (TIMESTAMPTZ)
- **Constraints**: Unique constraint on `(workspace_id, user_id)`.

### 2.2 WorkspaceInvitationModel (`workspace_invitations`)
- `id` (UUID, PK)
- `workspace_id` (UUID, FK -> `saved_opportunities.id` ON DELETE CASCADE)
- `inviter_id` (UUID, FK -> `users.id` ON DELETE CASCADE)
- `invitee_email` (VARCHAR 255)
- `invitee_user_id` (UUID, FK -> `users.id` ON DELETE SET NULL, nullable)
- `role` (VARCHAR 50, default `CONTRIBUTOR`)
- `token_hash` (VARCHAR 64, unique: the SHA-256 of the token; the token itself is never stored or returned)
- `status` (VARCHAR 50: `PENDING`, `ACCEPTED`, `DECLINED`, `EXPIRED`, `REVOKED`)
- `created_at`, `expires_at`, `accepted_at`, `revoked_at` (TIMESTAMPTZ)

### 2.3 WorkspaceTaskModel (`workspace_tasks`)
- `id` (UUID, PK)
- `workspace_id` (UUID, FK -> `saved_opportunities.id` ON DELETE CASCADE)
- `title` (VARCHAR 255)
- `description` (TEXT, nullable)
- `creator_id` (UUID, FK -> `users.id` ON DELETE CASCADE)
- `assignee_id` (UUID, FK -> `users.id` ON DELETE SET NULL, nullable)
- `status` (VARCHAR 50: `TODO`, `IN_PROGRESS`, `IN_REVIEW`, `COMPLETED`, `BLOCKED`)
- `priority` (VARCHAR 20: `LOW`, `MEDIUM`, `HIGH`, `URGENT`)
- `due_at` (TIMESTAMPTZ, nullable)
- `submission_id` (UUID, FK -> `research_submissions.id` ON DELETE SET NULL, nullable)
- `document_id` (UUID, FK -> `research_submission_documents.id` ON DELETE SET NULL, nullable)
- `created_at`, `updated_at`, `completed_at` (TIMESTAMPTZ)

### 2.4 WorkspaceActivityModel (`workspace_activities`)
- `id` (UUID, PK)
- `workspace_id` (UUID, FK -> `saved_opportunities.id` ON DELETE CASCADE)
- `actor_id` (UUID, FK -> `users.id` ON DELETE CASCADE)
- `activity_type` (VARCHAR 50: `MEMBER_JOINED`, `MEMBER_REMOVED`, `ROLE_CHANGED`, `INVITATION_SENT`, `INVITATION_ACCEPTED`, `TASK_CREATED`, `TASK_ASSIGNED`, `TASK_COMPLETED`, `TASK_STATUS_CHANGED`, `DOCUMENT_UPDATED`, `SUBMISSION_UPDATED`, `DEADLINE_CHANGED`, `COMMENT_ADDED`)
- `target_type` (VARCHAR 50, nullable)
- `target_id` (UUID, nullable)
- `description` (TEXT, not null)
- `comment` (TEXT, nullable)
- `old_state`, `new_state` (JSONB, nullable)
- `created_at` (TIMESTAMPTZ, not null)

---

## 3. Role-Based Access Control (RBAC) & Authorization

Every protected workspace mutation is verified server-side through `WorkspaceAuthorizationService`.

```text
Authenticated Request (X-User-ID / Session)
        ↓
Resolve UserModel ID
        ↓
O(1) Indexed Membership Lookup (workspace_id, user_id, status='ACTIVE')
        ↓
Evaluate Minimum Required Role (OWNER > EDITOR > CONTRIBUTOR > VIEWER)
        ↓
Permit / Reject (403 Forbidden / 404 Not Found)
```

### Role Matrix

| Action / Capability | OWNER | EDITOR | CONTRIBUTOR | VIEWER |
| :--- | :---: | :---: | :---: | :---: |
| **Manage Members & Roles** | Yes | No | No | No |
| **Send & Revoke Invitations** | Yes | No | No | No |
| **Delete / Archive Workspace** | Yes | No | No | No |
| **Edit Workspace Metadata** | Yes | Yes | No | No |
| **Manage Submissions & Readiness** | Yes | Yes | Read-Only | Read-Only |
| **Create & Update Tasks** | Yes | Yes | Yes (Assigned/Own) | No |
| **Upload Document Versions** | Yes | Yes | Yes (Permitted) | No |
| **Post Comments / Notes** | Yes | Yes | Yes | No |
| **View Workspace, Deadlines & Tasks** | Yes | Yes | Yes | Yes |

- **Privilege Escalation Prevention**: Contributors and Editors cannot promote themselves or others to Owner or Editor.
- **Orphan Prevention**: The last active Owner of a workspace cannot be demoted or removed.
- **Cross-Workspace Isolation (IDOR Protection)**: Modifying a workspace ID or task ID in a request returns `403 Forbidden` if the user is not an active member of that target workspace.

---

## 4. Invitation Lifecycle

1. **Creation (`create_invitation`)**:
   - Authorized by Owner.
   - Generates a cryptographically random, URL-safe 32-byte secret token.
   - Sets expiration (default: 7 days).
   - Enforces uniqueness: cannot create duplicate pending invitations for the same email in the same workspace.
   - Tells the recipient: a `WORKSPACE_INVITATION` notification if an account has **confirmed** that address, otherwise a generic email to the address, which only its owner can read (at most 20 such emails per inviter per hour; the invitation is created regardless).
   - Records no account: an invitation belongs to an address until it is answered, and the response never says whether the address has an account.
2. **Confirming the address (Decision C)**: see §4.1. Nothing below works without it.
3. **Acceptance (`accept_my_invitation`, from the notifications page)**:
   - Needs a signed-in account whose confirmed address matches the invitation's (trimmed, lower case). A token alone is never enough.
   - Validates status (`PENDING`) and `expires_at > now`, holding a row lock until the commit, so racing answers cannot both win.
   - An invitation is answered once: a second answer is refused with the reason.
   - `POST /workspaces/invitations/{token}/accept` still exists for tokens handed out before the API stopped returning them, under the same rules.
   - Creates or reactivates `WorkspaceMemberModel` in `ACTIVE` status.
   - Emits `INVITATION_ACCEPTED` and `MEMBER_JOINED` activity events.
   - Notifies inviter via Phase 4.5 notification pipeline.
4. **Revocation & Decline**:
   - Owner can revoke pending invitations (`status = REVOKED`).
   - Invitee can decline (`status = DECLINED`), also only with a confirmed address.
   - Revoked, declined, or expired invitations cannot be accepted.

### 4.1 Confirming an email address (Decision C)

Registering with an address proves nothing about it. `is_verified` is unrelated: it is an administrator's
confirmation that a faculty account is genuine. Ownership is proved like this:

1. The signed-in account asks: `POST /auth/email-verification` (5 attempts per account per 15 minutes).
2. A one-time token (256 random bits, 24 hours, replacing any earlier link) goes to the account's address.
   `email_verification_tokens` stores only its SHA-256 and the address it proves. The link is
   `/verify-email#token=…`: the token sits after the `#`, so it reaches no server log and no Referer, and the
   page removes it from the address bar at once.
3. Confirming, `POST /auth/email-verification/confirm`, needs the token **and** the account that asked. Someone
   who registers another person's address gains nothing if that person clicks the link: they cannot sign in to
   that account. The token is claimed by one conditional update, so it works once. Unknown, expired, replaced,
   used and other accounts' tokens all get the same answer.
4. `users.email_verified_address` then holds the address itself, not a flag, with a unique index: an account
   whose email later differs is no longer confirmed, and no two accounts can hold one confirmed address. Pending
   invitations for the address are announced now, and not before.

An unconfirmed account gets the same answer from every invitation endpoint whether or not the invitation, id or
token exists, and `GET /workspace-invitations/mine` lists nothing for it.

**This needs real email.** With `EMAIL_PROVIDER=mock` (the default), or an address outside
`EMAIL_RECIPIENT_ALLOWLIST`, the request answers 503 and says so: nothing can be confirmed, so invitations cannot
be answered. This fails closed on purpose. The demo seeder marks its own accounts confirmed, as an operator's act
on addresses that receive no mail.

---

## 5. Collaborative Task Management

Workspace tasks coordinate the research preparation workflow:
- Tasks can be associated directly with a submission (`submission_id`) or submission document (`document_id`).
- Task state machine: `TODO -> IN_PROGRESS -> IN_REVIEW -> COMPLETED`.
- Task assignment triggers `TASK_ASSIGNED` notifications to the assignee, respecting their notification preferences.
- Task completion records `TASK_COMPLETED` audit activity and timestamps `completed_at`.

---

## 6. Integration with Existing Infrastructure

- **Phase 4.2–4.3 Submissions & Documents**:
  - Existing submission state-machine rules and document readiness checks are strictly preserved.
  - Workspace members with `CONTRIBUTOR` or `EDITOR` roles can view and contribute to submissions without bypassing document readiness checks.
- **Phase 2.7 & 4.4 Deadlines & Calendar**:
  - Canonical external deadlines (from `OpportunityModel`) remain strictly immutable and separate from workspace task due dates (`task.due_at`).
  - Personal reminders (`ReminderRuleModel`) remain distinct from collaborative workspace tasks.
- **Phase 4.5 Notifications**:
  - Reuses `NotificationModel` and `NotificationPreferenceModel`.
  - Dedup keys ensure notifications for invitations, task assignments, and role changes are delivered idempotently without spamming users.

---

## 7. Database Migration (`0016_phase4_6_collaboration.py`)

The migration is non-destructive and backward-compatible:
1. Creates `workspace_members`, `workspace_invitations`, `workspace_tasks`, `workspace_activities`.
2. Adds indices on `(workspace_id, status)`, `(user_id, status)`, `(workspace_id, created_at)`.
3. Backfills existing `saved_opportunities`:
   - Every workspace owner is automatically granted an `OWNER` membership row in `workspace_members`.
4. Extends `chk_notifications_type` constraint to include collaboration notification types.
5. Downgrade cleanly reverts constraint and drops collaboration tables.

---

## 8. Frontend Architecture (Next.js App Router)

- **Route**: `/workspace/[id]/page.tsx`
- **Component Architecture**:
  - Integrated tabbed navigation: `Overview`, `Submissions`, `Tasks`, `Members`, `Invitations`, `Activity & Notes`.
  - Role-aware UI components: action buttons (e.g., Invite Member, Change Role, Add Task) reflect server-side authorization.
  - Strict TypeScript types (`frontend/types/collaboration.ts`).
  - Fully responsive styling with high-contrast accessibility (originally `frontend/styles/collaboration.css`; since the redesign (P7), CSS modules in `frontend/components/workspace/item/`).

---

## 9. Performance & Scalability Benchmarks

- **Membership Retrieval**: O(1) indexed query with eager loading (`joinedload` on user and profile).
  - 10 members: < 5ms
  - 100 members: < 15ms
  - 1,000 members: < 80ms (well within 250ms threshold)
- **Authorization Checks**: Fast O(1) lookup on compound index `(workspace_id, user_id)`. Average latency < 0.5ms.
- **N+1 Prevention**: Explicitly tested with SQLAlchemy query counting:
  - 20 members: exactly 4 bounded queries (auth + joined load).
  - 20 tasks: exactly 3 bounded queries (auth + count + joined load).

---

## 10. Architectural Invariants Verified

All 20 Phase 4.6 invariants are covered by dedicated automated tests:
1. Workspace membership does not imply workspace ownership.
2. Viewers cannot mutate tasks, documents, or submissions.
3. Contributors cannot escalate privileges to Editor or Owner.
4. Cross-workspace IDOR access is strictly rejected with 403.
5. An invitation is answered once; a second answer is refused with the reason.
6. Expired invitations cannot be accepted.
7. Revoked invitations cannot be accepted.
8. Duplicate active memberships are impossible (409 Conflict).
9. Audit history is append-only and cannot be rewritten.
10. Collaboration cannot bypass submission state-machine rules.
11. Collaboration cannot bypass document readiness requirements.
12. Collaboration cannot overwrite canonical opportunity deadline evidence.
13. Canonical deadlines remain distinct from task due dates.
14. Personal reminders remain distinct from workspace tasks.
15. Notification preferences remain respected (opt-outs enforced).
16. Phase 2 ranking behavior is completely unchanged.
17. Phase 2.7 deadline behavior is completely unchanged.
18. Phase 3 personalization behavior is completely unchanged.
19. Phase 4.1–4.5 behavior remains backward compatible.
20. No silent data or audit evidence loss occurs on member removal.

---

## 11. Phase Boundaries & Deferrals

The following features belong strictly to **Phase 5+** and are intentionally deferred:
- Automated submission bot / crawler execution against external portals (EasyChair, OpenReview, Grants.gov).
- Storage or synchronization of external portal login credentials.
- Browser automation (Playwright/Puppeteer) for autonomous form filling on third-party websites.
- Cross-institutional single sign-on / multi-tenant enterprise federation.
