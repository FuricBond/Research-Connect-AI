# End-to-end verification (Phase 6.6)

This directory proves that the platform works as one system: the production Docker images,
PostgreSQL with pgvector, migrations, the backend, the frontend, authentication, every major
workflow, the scheduler, and restarts. It runs against a real stack, never mocks.

## Running it

From the repository root, with the backend virtualenv (Python 3.11+) and Docker:

```bash
python e2e/run_e2e.py
```

That builds the images, starts a **separate** Compose project (`rce2e`) from an empty
database, runs the three suites below, collects logs, and removes the project again
(`down -v` and its images). A full run takes about 15 minutes, most of it the scheduler
stage waiting for jobs and the suite pacing itself under the sign-in rate limit.

| Option | Effect |
|---|---|
| `--keep` | Leave the stack running afterwards |
| `--reuse e2e/results/<run>` | Rerun the suites against a stack left by `--keep` |
| `--suites api,browser,stack` | Run a subset |
| `--skip-build` | Reuse the `:e2e` images from a previous run |
| `-- <pytest args>` | Passed to pytest, e.g. `-- -k applications` |

The browser suite needs Chrome or Edge (`E2E_BROWSER_CHANNEL=chrome`) or Playwright's own
Chromium (`cd frontend && npx playwright install chromium`).

## Isolation

The E2E project never touches a developer's stack or data:

- **Own identity.** The project name, published ports (`3300`, `8300`, `5436`), image tags
  (`:e2e`) and PostgreSQL container name are all separate.
- **Fresh secrets.** `POSTGRES_PASSWORD`, `AUTH_SECRET_KEY` and the demo password are
  generated for each run. The env file holding them is deleted at teardown, and the project
  `.env` is never read.
- **Production settings.** The services run with `APP_ENV=production`, so there is no
  developer identity. Rate limits and every other control are unchanged; the suite paces its
  own sign-ins instead of raising the limit.

## What runs

1. **Clean startup.** PostgreSQL → `migrate` → backend (ready) → frontend. The runner checks
   the order, health, restart counts and schema readiness, and records the timings.
2. **API suite** (`e2e/api`, pytest). Real HTTP with bearer tokens, plus SQL checks of the
   stored state.

   | Module | Covers |
   |---|---|
   | `test_00` | Demo seed and the P2-1 account-takeover guard |
   | `test_01` | Database: Alembic head, pgvector, generated columns, indexes |
   | `test_02` | Authentication |
   | `test_03` | Discovery and personalization |
   | `test_04` | Workspace and submissions |
   | `test_05` | Faculty postings |
   | `test_06` | Applications and reviewer-note privacy |
   | `test_07` | Peer consent |
   | `test_08` | Notifications |
   | `test_09` | Authorization matrix |

3. **Browser suite** (`frontend/e2e`, Playwright) against the production build:
   - the sign-in lifecycle;
   - the main researcher journey: discover, save, apply, get notified;
   - every signed-in page, with no failed API call or page error, which checks the
     frontend and backend contracts.
4. **Stack suite** (`-m stack`):
   - `test_90`: runs the scheduler inside the backend and verifies each job's effect,
     idempotency and non-overlap;
   - `test_95`: restarts each service and the whole stack, and checks that the data
     persists.

## Evidence

Each run writes `e2e/results/<UTC timestamp>/` (git-ignored). It contains:

- `summary.json`, with the environment, startup timeline, suite counts and log scan;
- JUnit files for each suite;
- `observations.json`, with measured facts the suites record without asserting;
- container logs, snapshotted after startup, after the workflows, and at the end.

The runner fails if any container log contains a generated secret, a token the suites used,
a JWT-shaped string or a 5xx response.

The results of the Phase 6.6 verification are in
[`PHASE_6_6_E2E_VERIFICATION_REPORT.md`](../PHASE_6_6_E2E_VERIFICATION_REPORT.md).
