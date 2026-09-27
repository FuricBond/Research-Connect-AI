# Phase 6.6 — End-to-End Verification Report

Date: 2026-09-27 · Branch: `main` (working tree; nothing committed) · Evidence run:
`e2e/results/20260927T131055Z/` (git-ignored; reproducible with `python e2e/run_e2e.py`)

## 1. Executive Summary

**Status: COMPLETE.**

The platform was verified as one system across service boundaries: the production Docker
images, PostgreSQL 16 with pgvector, migrations, the backend, the frontend and the scheduler.
Every check used real HTTP with bearer tokens, a real browser and SQL checks of stored state.
The final evidence run started from an empty database and passed every stage:

| Stage | Result |
|---|---|
| Clean startup | 20.9 s, every ordering and health check green |
| API workflows | 69 / 69 |
| Browser | 3 / 3 |
| Scheduler, restarts and persistence | 7 / 7 |
| Log scan (12 snapshots) | No leaked secret, no traceback, no 5xx |

The run found **one real integration defect**, which was fixed with a regression test:

- **F-1.** Saving an opportunity already in the workspace moved it back to `SAVED` and reset
  its priority. This was reachable from the recommendation "Save" button.

Three findings belong to later phases and are deferred without fixes:

- **F-2** (6.7): issued tokens outlive client-side logout.
- **F-3** (6.8/6.9): the first search on a new container downloads the embedding model,
  taking 30.4 s.
- **F-4** (6.8): one timing micro-benchmark is flaky.

No security control was weakened. The E2E stack ran with `APP_ENV=production` and unchanged
rate limits.

## 2. Environment

| Item | Version |
|---|---|
| OS | Windows 11 Home Single Language 10.0.26200 |
| Docker Engine / Compose | 29.8.0 / 5.5.1 |
| PostgreSQL / pgvector | 16.15 (Debian 16.15-1.pgdg12+2) / 0.8.6, image `pgvector/pgvector:0.8.6-pg16` |
| Python (host, suites) / backend image | 3.13.9 / `python:3.13.9-slim-bookworm` |
| Node / npm | 24.13.1 / 11.8.0 (frontend image `node:24.13.1-bookworm-slim`) |
| Browser | Google Chrome 154.0.8037.58 via Playwright 1.63.0 (`E2E_BROWSER_CHANNEL=chrome`) |

The E2E environment was isolated from the developer's stack, which kept running untouched
throughout:

- Compose project `rce2e`, with its own PostgreSQL container name.
- Ports 3300, 8300 and 5436.
- `:e2e` image tags.
- A fresh volume.
- Secrets generated for each run; the project `.env` was never read.

It was removed at the end (`down -v` and image removal).

## 3. Architecture Tested

- **PostgreSQL 16 + pgvector.** One database with HNSW vector indexes, `GENERATED ALWAYS`
  full-text columns and GIN indexes.
- **Migration layer.** The one-shot `migrate` service runs `wait_for_db`, then
  `alembic upgrade head` under the Phase 6.5 advisory lock.
- **Backend.** FastAPI with the Phase 6.5 production schema gate. `/api/health` is liveness;
  `/api/health/ready` is the Compose healthcheck.
- **Frontend.** The Next.js standalone production build, gated on backend readiness.
- **Scheduler.** The Phase 6.3 in-process scheduler, enabled for the scheduler stage through
  `e2e/compose.e2e-scheduler.yml` with 60 s intervals, as production would enable it.

The E2E harness consists of:

- `e2e/run_e2e.py`, the orchestrator;
- `e2e/api`, the pytest suite over HTTP and SQL;
- `frontend/e2e`, the Playwright suite.

## 4. Startup Verification

Measured from PostgreSQL's container start, in the evidence run (`summary.json` → `startup`):

| Component | Result | Evidence |
|---|---|---|
| PostgreSQL | PASS | Healthy, `migrate` started at +5.7 s, restart count 0 |
| Migrations | PASS | 28 revisions applied, exit 0 at +8.4 s; `alembic heads` and `alembic current` in the backend container both return `0028_phase5_12_peer_discovery (head)` |
| Backend | PASS | Started at +8.8 s after `migrate` finished. Log: `database schema check passed: database=ok schema=current`. Readiness `{"status":"ready","database":"ok","schema":"current"}` |
| Frontend | PASS | Started at +14.5 s after the backend was healthy, then healthy itself |
| Scheduler | PASS | Ships off (`SCHEDULER_ENABLED=false`) and verified off again after the scheduler stage (no `Scheduler started` line). With the override: `Scheduler started with 4 job(s)` (§13) |

Other checks passed as well:

- **Whole stack.** `up -d --wait` returned in 20.9 s after a 75.1 s build.
- **Crash loops.** No container restarted.
- **Logs.** No migration, connection or configuration errors were logged.

## 5. Authentication E2E

The API suite (`test_02_authentication.py`, 8 tests) and the browser suite (`auth.spec.ts`)
covered the following:

- **Registration.** `201` returns a bearer JWT with a future `expires_at` and a lower-cased
  email. The database stores only a bcrypt hash (`$2…`), never the password.
- **Refused registrations.**
  - A duplicate email is `409`, even when it differs only in case.
  - A password under the policy length is `422`.
  - Self-registering as `ADMIN` is `422`.
- **Login.** The right password returns `200`. A wrong password and an unknown email both
  return `401` with the same message, so accounts aren't disclosed.
- **JWT.**
  - `/auth/me` with the token returns the account.
  - No token, a garbage token, or a token whose payload was edited to name another user
    (signature mismatch) returns `401`.
  - `X-User-ID` alone returns `401` in production, and next to a real token it is ignored.
- **Protected routes.** Workspace, notifications, applications and preferences return `401`
  without a token.
- **Deactivation.** When an administrator deactivates an account, its live token gets `401`
  immediately. Reactivation restores it.
- **Browser.**
  - The landing page is public.
  - `/workspace` redirects a signed-out visitor to `/login?next=%2Fworkspace`.
  - The registration form signs the user in, and authenticated navigation works.
  - "Sign out" ends the browser session, and `/workspace` redirects again.
  - Signing in returns to `/workspace`.
  - A wrong password shows a readable error.
- **Logout.** Logout is client-side: there is no logout endpoint (`POST /auth/logout` is not
  a route). A discarded token still works until it expires (F-2).

## 6. Researcher Workflow

The researcher workflow was run through the API (`test_03`, `test_04`) and the browser
(`workflow.spec.ts`):

1. A researcher registers and the profile exists.
2. A profile update (keywords, target types, academic status) persists. It is read back
   through the API and in `research_profiles`.
3. Preferences are stored: a preferred topic and an excluded type (`JOURNAL`). The topic is
   normalized to the canonical slug `information-retrieval`.
4. Browse lists the 10 active opportunities. The 2 expired ones appear only with
   `status=EXPIRED`.
5. Literature search finds the seeded works through the generated full-text column and the
   vector channel.
6. Similar Research and venue matching return `200`. This is the live check of the
   float32/pgvector fix. The three IR venues rank in the top five, with risk and deadline
   explanations (`explain=true`, as the frontend always sends).
7. Personalized recommendations, their explanation, and unified recommendations work. The
   unified view carries evidence tiers and verified invariants.
8. Saving a recommendation in the browser creates a workspace item, which appears on
   `/workspace`.
9. A submission and an application follow (§8, §10), and a notification arrives (§10, §12).

The seeder creates no research works, and real embeddings need a model download. The suite
therefore inserts six works through the backend's own ORM, with fixed 384-dimensional topic
vectors, and sets vectors on eight seeded venues (`e2e/api/corpus.py`). This exercises the
pgvector channels deterministically. Embedding a free-text query uses the real model; see
F-3.

## 7. Personalization Workflow

Covered by `test_03_discovery_personalization.py`, 12 tests:

- **Relevance dominance.** Every `personalization_adjustment` is at most 0.15.
- **Excluded semantics.** Every journal gets `personalization_adjustment == 0.0`, and
  `matched_preferences` records `EXCLUDED …`.
- **Feedback.**
  - Five interactions produce 4 stored rows, because Phase 5.4 rapid-fire deduplication
    folds the repeated `NOT_INTERESTED` click into the same interaction ID.
  - Recomputing produces adaptive signals.
  - The ranking still answers with negative evidence present, and
    `inferred_preference_score` stays in [0, 1] (the earlier walkthrough fix).
- **Governance.** The governance history has an evaluation after the recompute.
  Switching personalization off makes every adjustment `0.0`, and each switch is written to
  the control audit history.
- **Reset.** Reset increments `personalization_state_version`. After a recompute there are 0
  adaptive signals, because pre-reset evidence is excluded, while explicit preferences
  (including the exclusion) stay.
- **Cross-researcher isolation.** Another researcher gets `403` on recommendations,
  preferences, adaptive signals, a profile patch, an interaction and a reset. The target's
  data was unchanged.

## 8. Workspace Workflow

Covered by `test_04_workspace_submissions.py`, 6 tests:

- **Save.** `201` on the first save, and the second save returns the same item. The stored
  row (`saved_opportunities`) matches.
- **Notes, tags and priority.** Updates persist on re-read.
- **Transitions.**
  - `SAVED → ACCEPTED` is refused with `400`.
  - `SAVED → CONSIDERING → PLANNING` succeeds.
  - Saving again keeps `PLANNING`/`URGENT`. This failed before the fix (F-1).
- **Collaboration.** A task (`TODO`, creator recorded) and a comment appear in the activity
  feed.
- **Submission.**
  - A new submission starts as `DRAFT` and is linked to the venue.
  - A required document still in `DRAFT` blocks readiness, and `→ READY` is refused with
    `400`.
  - Once the document is `READY`, readiness allows it: `READY → SUBMITTED`.
  - The audit history records `DRAFT→READY` and `READY→SUBMITTED`.
  - Submitting promoted the workspace item to `APPLIED` (Phase 4.2).
- **Ownership.** Researcher B gets `403/404` on eight probes: read, update, transition,
  tasks, comment, submission read, submission transition and delete. B's own lists are empty,
  and A's item is intact.

## 9. Faculty Workflow

Covered by `test_05_faculty_postings.py`, 4 tests:

- **Draft visibility.** A new posting is `DRAFT`. Its author can read it; a student and an
  anonymous caller get `404`, and it is absent from the public list.
- **Publish and update.** Publishing (`OPEN`) sets `published_at` and makes the posting
  visible to students. A title update reaches readers.
- **Lifecycle.**
  - `OPEN → CLOSED → OPEN` is allowed, then `→ FILLED`, whose only transition is `ARCHIVED`.
  - From `FILLED`, the transitions `OPEN`, `CLOSED` and `DRAFT` are `400`.
  - `ARCHIVED` is terminal.
  - `CANCELLED → OPEN` is `400`.
  - So a concluded search can't be reopened.
- **Authorization.**
  - A student can't author a posting (`403`).
  - Another faculty member can't edit, transition or delete it (`403/404`).
  - Only drafts can be deleted, and only by their author (`204`, then `404`).

## 10. Application Workflow

Covered by `test_06_applications.py` with two identities, plus the browser journey:

- **Discover and apply.** Faculty publishes a research assistantship with
  `accepts_applications`. The researcher discovers and applies: `SUBMITTED`, recorded as
  `viewer_application_id`. A duplicate is `409`.
- **Author view.** The author sees the application with the applicant's name and is
  notified.
- **Review.**
  - The applicant can't shortlist themselves (`400/403`).
  - The author moves the application to `UNDER_REVIEW` with a reviewer note, then
    `SHORTLISTED`.
  - The note is stored in `research_posting_applications.reviewer_note`.
- **Reviewer-note privacy.** The applicant's application detail, "my applications", the
  posting detail and all their notifications never contain the note, and `reviewer_note` is
  `null` for them. The browser check repeats this on `/postings/applications` and
  `/notifications`.
- **Applicant view.** The applicant sees `SHORTLISTED`, the status history, and a
  notification.
- **Third party.** A third researcher gets `403/404` on the application, the posting's
  applications and a transition.
- **Withdrawal.** After withdrawal the author can't make an offer (`400`). Re-applying
  reuses the same application ID with status `SUBMITTED`.

## 11. Peer Discovery

Covered by `test_07_peer_discovery.py`. The two researchers were given topic interest rows,
the same rows the seeder writes; in the product they come from linked publications via
OpenAlex. All consent actions went through the API:

- **No consent.** A candidate without consent is absent from the seeker's results, while
  consented demo researchers are found.
- **Searching creates no consent.** The seeker's settings still read
  `is_discoverable: false`, and no row was written to `researcher_discovery_settings`.
- **Opting in.** After opting in with institution and email withheld, the candidate appears
  with `institution: null` and `contact_email: null`. The match shows shared or
  complementary topics, explanation reasons and a score in (0, 1].
- **Disclosure controls.** `show_institution: true` reveals the institution only. Opting out
  removes the candidate again.
- **Isolation.** Another researcher gets `403` reading or changing someone's discovery
  settings or searching as them.

## 12. Notification Workflow

Covered by `test_08_notifications.py`, plus the application notifications in §10:

- **Settings.** Preferences persist (`email_enabled: false`). A custom reminder rule can be
  created, listed, paused and deleted.
- **Triggering.** Only an administrator can trigger the reminder pass: a researcher and
  faculty get `403`.
- **Generation.** A researcher tracking a deadline five days out gets 2 reminders, from the
  14-day and 7-day default rules. A second pass creates none: `created_notifications: 0`,
  `skipped_duplicates: 2`. The deduplication keys are unique.
- **Preferences enforced.** A researcher with deadline reminders off gets none.
- **Read state.** Reading one notification decrements the unread count, and mark-all-read
  brings it to 0.
- **Isolation.** Another researcher can't read or mark someone else's notifications.
- **Dismissal is not implemented.** The API and UI offer read and mark-all-read only. This
  is recorded, not faked.
- **Scheduler interaction.** Covered in §13: `reminder_dispatch` created the reminder on its
  own.

## 13. Scheduler Verification

`test_90_scheduler.py` recreated the running backend with `SCHEDULER_ENABLED=true` and 60 s
intervals. It waited for two runs of every job, checked each job's effect, then restored the
production default (scheduler off, verified).

| Job | Run 1 | Run 2 | Database effect verified |
|---|---|---|---|
| `deadline_expiry` | SUCCEEDED, records=1 | SUCCEEDED, records=0 | A prepared active call past its deadline became `EXPIRED` |
| `reminder_dispatch` | SUCCEEDED, records=1 | SUCCEEDED, records=0 | The researcher tracking a deadline 12 days out received the reminder with no request |
| `adaptive_signal_refresh` | SUCCEEDED, records=3 | SUCCEEDED, records=3 | Interactions became adaptive signals without a recompute request |
| `governance_refresh` | SUCCEEDED, records=4 | SUCCEEDED, records=4 | A current governance evaluation exists |

- **Idempotency.** The second runs of the expiry and reminder jobs changed nothing. The
  refresh jobs recompute deterministic state.
- **No overlap.** Parsing the `started` and completion log lines showed no job started while
  its previous run was open.
- **Failure isolation and transaction safety.** Every run `SUCCEEDED`, and the backend
  served meanwhile. The largest API latency across 32 requests during job runs was 0.099 s.
- **Not run.** `opportunity_refresh` (WikiCFP) is opt-in and depends on an external website,
  so it was not run.

## 14. Authorization Integration

`test_09_authorization.py` ran 16 tests, each with a positive control per role. Additional
boundaries were covered in the modules named below.

| Actor → target | Result |
|---|---|
| Researcher B → A's profile, preferences, recommendations, interactions, settings, notifications, calendar and workspace (11 probes) | Denied (`403/404`) |
| Researcher → faculty-only operation (create posting) | `403` |
| Researcher → admin operation (list or patch users, self-promote to `ADMIN`) | `403`, and the role remained `STUDENT` |
| Researcher → reminder trigger | `403` |
| Faculty → admin operations (list users, self-promote, deactivate others) | `403` |
| Faculty → a researcher's private workspace and preferences | Denied |
| Applicant → faculty reviewer note | Never returned (§10) |
| Non-consented researcher → peer data | Absent and settings denied (§11) |

## 15. Demo Environment

`test_00_demo_seed.py` ran on the fresh database, with the seeder executed inside the running
backend container using the documented production contract (`--password`):

- **P2-1 (the Phase 6.4 audit finding).**
  - `demo.admin@researchconnect.test` was first registered through the public API.
  - The seeder then exited `1`, naming the email, and wrote nothing: the user count was
    unchanged and there were 0 opportunities.
  - The account kept its role (`STUDENT`) and its own password, and the seed password was
    refused.
  - The seed password never appeared in the seeder's output.
- **`--reset`.** Reset replaced the foreign account, and all three demo accounts log in with
  the right roles.
- **Dataset.** 12 opportunities: 10 active and 2 already `EXPIRED`. 3 postings: 2 open, of
  which one accepts applications, and 1 draft visible only to its author. Faculty and
  student are discoverable.
- **Idempotency.** Reseeding changed no row counts.
- **Representative workflow.** The student finds the assistantship, the faculty member's
  personalized ranking has candidates, and the administrator lists the demo accounts.

## 16. Persistence / Recovery

`test_95_persistence_recovery.py` wrote the following across workflows:

- profile bio;
- a workspace item with priority and notes;
- a submission;
- a draft posting;
- a notification preference.

It then read all of it back unchanged after each step below. Existing bearer tokens kept
working throughout.

| Step | Result |
|---|---|
| Restart backend | Ready again; data intact |
| Restart frontend | `/login` served again; data intact |
| Restart PostgreSQL | Backend recovered without a restart (the connection pool re-validates); schema `current`; data intact |
| `down` then `up -d --wait`, keeping the volume | Ready in 19.4 s; `migrate` applied **0** revisions; no container restarting; data intact |

## 17. Test Results

All counts are exact from JUnit or pytest output.

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| P0 (`test_p0_security_regression`, `test_p0_phase5`) | 47 | 0 | 0 |
| P1 (`test_p1_hardening`, `test_workspace_authorization`) | 21 | 0 | 0 |
| Phase 5 (13 modules) | 244 | 0 | 0 |
| Phase 6.1 (Compose and deployment checks; plus the E2E clean startup, §4) | 20 | 0 | 0 |
| Phase 6.2 (frontend auth and session suites, 8 files) | 143 | 0 | 0 |
| Phase 6.3 (`test_scheduler`) | 39 | 0 | 1 (opt-in; passed below) |
| Phase 6.4 (`test_production_config`) | 76 | 0 | 0 |
| Phase 6.5 (`test_database_startup`, `test_health`) | 24 | 0 | 0 |
| Opt-in PostgreSQL (6.5 migrations ×6, 6.3 race ×1) | 7 | 0 | 0 |
| P2-1 (`test_seed_demo_account_takeover`, `test_seed_demo_data`) | 28 | 0 | 0 |
| Phase 6.6 backend regressions (workspace, discovery, ranking) | 25 | 0 | 0 |
| **Phase 6.6 E2E: API** | **69** | **0** | **0** |
| **Phase 6.6 E2E: browser** | **3** | **0** | **0** |
| **Phase 6.6 E2E: stack** | **7** | **0** | **0** |
| Backend full suite | 1,572 | 2 | 9 |
| Frontend unit (Vitest) | 169 | 0 | 0 |
| Frontend type-check / lint | 0 errors / 0 errors | | 1 pre-existing lint warning |

There were no `xfail` results in any suite.

The two failures in the full backend suite are timing micro-benchmarks, not functional
failures (F-4):

- **`test_ranking_execution_budget`.** Measured 2.061 ms against a 2.0 ms budget. On its own
  it passed on 4 of 6 attempts.
- **`test_performance_benchmarks_zero_n_plus_one`.** Failed only in the full run, while the
  E2E stack ran alongside. It passes on its own.

Neither test touches the code changed in this phase, and no budget was changed. The 9 skips
break down as 7 opt-in PostgreSQL tests (all passed when enabled, row above) and 2 that need
embeddings in the default database.

## 18. Issues Found

### F-1 — Saving again reset a workspace item's stage and priority · **Fixed in Phase 6.6**
- **Severity:** Medium (silent data change in a primary workflow).
- **Component:** backend `WorkspaceService.add_opportunity`.
- **Reproduction:**
  1. Save an opportunity with priority `HIGH`.
  2. Move it to `CONSIDERING`.
  3. `POST /api/v1/workspace {"opportunity_id": …}` again, which is what the recommendation
     "Save" button sends.

  The item returns as `SAVED` with priority `MEDIUM`.
- **Root cause:** for an existing item, the service applied `payload.status` and
  `payload.priority` whenever they were truthy. The create schema defaults them to `SAVED`
  and `MEDIUM`, and `CONSIDERING → SAVED` is a valid backward transition.
- **Resolution:** only fields the caller actually sent are applied (Pydantic
  `model_fields_set`). Re-saving an archived item still restores it. Explicit values still
  apply.
- **Regression tests:**
  - `backend/tests/test_workspace_api.py::test_api_saving_again_keeps_the_researchers_stage_and_priority`
    fails on the previous code (`('SAVED','MEDIUM')` instead of `('CONSIDERING','HIGH')`)
    and passes now.
  - E2E `test_04` checks the same behaviour on the deployed stack.

### F-2 — Issued tokens remain valid after sign-out · **Deferred to Phase 6.7**
- **Severity:** Low–Medium (session management).
- **Component:** authentication.
- **Reproduction:** sign in, sign out in the browser, then call `/auth/me` with the old
  token: `200`.
- **Root cause:** stateless JWTs with no revocation list or logout endpoint. The access-token
  lifetime defaults to 480 minutes. Deactivation does revoke immediately (verified in §5).
- **Resolution:** none here. Assess in the Phase 6.7 security audit (revocation, shorter
  lifetime, or refresh tokens).

### F-3 — First search on a new backend container downloads the embedding model · **Deferred to Phase 6.8 / 6.9**
- **Severity:** Medium for release readiness.
- **Component:** backend image and discovery search.
- **Reproduction:** on a freshly started stack, the first literature search took **30.4 s**
  (22.7 s in an earlier run). Later searches are fast.
- **Root cause:** `sentence-transformers` downloads `all-MiniLM-L6-v2` from Hugging Face at
  the first query. The backend container therefore needs outbound network access, and the
  cached model is lost whenever the container is recreated.
- **Resolution:** none here, and not a functional failure. Candidates for 6.8/6.9:
  - bake the model into the image;
  - warm it at startup;
  - mount a cache volume.

### F-4 — Timing micro-benchmark is flaky under load · **Deferred to Phase 6.8**
- **Severity:** Low (test reliability).
- **Component:** backend test suite.
- **Details:** `test_ranking_execution_budget` exceeds its 2 ms budget by about 3% under
  ambient load, and `test_performance_benchmarks_zero_n_plus_one` failed once under E2E load.
  Both are already documented as machine-sensitive (METHODOLOGY §9.2).
- **Resolution:** none. Budgets are not changed; the Phase 6.8 performance audit should set
  them from measurements.

### Observations (not defects)
- **Transition notes.** On the workspace transition endpoint, the optional `notes` replaces
  the item's notes. The UI never sends it, so the E2E suite mirrors the UI. Worth stating in
  the API documentation (6.9).
- **Notification dismissal is not implemented.** Read and mark-all-read are the supported
  operations.
- **Explanations are opt-in.** Venue matching omits risk and deadline explanations unless
  `explain=true`. The frontend always sends it.
- **Carried over from 6.5.** The models declare 37 indexes that no migration creates. This
  is not re-found here and stays with the 6.8 audit.
- **API↔frontend contracts.** No mismatch was found. The three browser specs visit every
  signed-in page and the discovery, save, apply and notify flows, and fail on any 4xx/5xx
  response or page error: none occurred.

## 19. Acceptance Criteria

| Criterion | Result |
|---|---|
| Clean environment starts successfully | PASS |
| PostgreSQL becomes healthy | PASS |
| Migrations reach head | PASS |
| Backend becomes healthy | PASS |
| Frontend becomes healthy | PASS |
| Registration works | PASS |
| Login works | PASS |
| JWT authentication works | PASS |
| Logout/protected-route behavior works | PASS (client-side logout; token revocation deferred, F-2) |
| Researcher workflow works end-to-end | PASS |
| Personalization workflow works end-to-end | PASS |
| Workspace workflow works end-to-end | PASS (after the F-1 fix) |
| Faculty posting workflow works end-to-end | PASS |
| Application workflow works end-to-end | PASS |
| Reviewer notes remain private | PASS |
| Peer discovery consent works | PASS |
| Notifications work | PASS (dismissal not implemented: NOT APPLICABLE) |
| Scheduler integration works where applicable | PASS (WikiCFP refresh: NOT APPLICABLE, external dependency) |
| Cross-user ownership is enforced | PASS |
| Demo seed works | PASS |
| P2-1 protection remains intact | PASS |
| Data persists across application restart | PASS |
| Relevant regression suites pass | PASS (2 flaky timing benchmarks, F-4; not functional) |
| Frontend typecheck passes | PASS |
| Frontend lint passes | PASS |
| No unexplained E2E failures remain | PASS |
| No production security control was weakened | PASS |
| Repository is clean except for intentional Phase 6.6 changes | PASS |

## 20. Repository Changes

Nothing is committed; all changes are in the working tree.

| File | Why |
|---|---|
| `backend/app/services/workspace_service.py` | F-1 fix: re-saving applies only the fields sent |
| `backend/tests/test_workspace_api.py` | F-1 regression test |
| `e2e/run_e2e.py` | Orchestrator: isolated build and start, startup verification, suites, log snapshots and secret/5xx scan, teardown |
| `e2e/compose.e2e.yml` | Isolation override: project ports, image tags, container name (no setting changed) |
| `e2e/compose.e2e-scheduler.yml` | Scheduler stage: `SCHEDULER_ENABLED=true`, 60 s intervals |
| `e2e/pytest.ini` | Suite configuration and the `stack` marker |
| `e2e/api/conftest.py` | HTTP client with auth pacing, accounts, database access, compose helper, demo seed |
| `e2e/api/corpus.py` | Deterministic literature corpus with fixed embeddings |
| `e2e/api/test_00` … `test_09`, `test_90`, `test_95` | The API and stack suites (76 tests) |
| `e2e/README.md` | How to run the suite, isolation, what each stage covers, evidence |
| `frontend/playwright.config.ts` | Browser suite configuration |
| `frontend/e2e/support.ts`, `auth.spec.ts`, `workflow.spec.ts`, `pages.spec.ts` | Browser suite (3 tests) with a contract watch |
| `frontend/package.json`, `package-lock.json` | Dev dependency `@playwright/test@^1.63.0` (3 packages, no browser download) |
| `frontend/.dockerignore` | Keep the browser suite out of the production image |
| `.gitignore` | Ignore `e2e/results/` and Playwright output |
| `PHASE_6_6_E2E_VERIFICATION_REPORT.md` | This report |
| `README.md`, `docs/README.md`, `docs/architecture/project-roadmap.md`, `docs/METHODOLOGY.md` (+ `.docx`) | Phase 6.6 status, the E2E suite and test counts |

**Why a browser framework.** The project had no browser E2E. The defects found in the
earlier walkthrough were all browser↔API integration failures that unit tests could not see,
which is what Step 15 asks this layer to catch. `@playwright/test` is dev-only, adds 3
packages, runs on an installed Chrome, and is excluded from the production image.

## 21. Final Verdict

**PHASE 6.6 — COMPLETE**

## 22. Recommended Next Step

**Phase 6.7 — Final Security Audit.** Start from F-2 (token lifetime and revocation), and use
`python e2e/run_e2e.py` as the regression gate for any change it makes. Phase 6.7 was not
implemented in this task.
