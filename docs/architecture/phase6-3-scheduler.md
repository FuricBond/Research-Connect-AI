# Phase 6.3 — Background Scheduler & Scheduled Jobs

Phase 6.3 runs the platform's maintenance work on a schedule instead of relying on an
administrator or a page view to trigger it. The scheduler is deliberately small: an asyncio
loop per job inside the backend process, PostgreSQL advisory locks for cross-process
exclusion, and five thin job adapters over services that already existed. There is no
Celery, Redis, broker or separate worker image.

**It is off by default.** With `SCHEDULER_ENABLED=false` (the default everywhere: the settings
class, both `.env.example` files and `docker-compose.yml`) the application creates no task,
no thread and no database connection for scheduling, so tests and the host development loop
behave exactly as before.

Code: `backend/app/scheduler/` (`scheduler.py`, `jobs.py`, `locks.py`, `metrics.py`,
`lifecycle.py`). Tests: `backend/tests/test_scheduler.py`.

---

## 1. Job matrix

The jobs are rows 17–21 of the Phase 6 job matrix, and no others.

| Job | Existing entry point | Default interval | Budget | Network | Scope | Transaction |
|---|---|---|---|---|---|---|
| `deadline_expiry` | `scrapers.expiration.manager.expire_past_opportunities(session)` | 1 h | 300 s | no | global | the sweep flushes; the adapter commits |
| `reminder_dispatch` | `ReminderSchedulerService.run_scheduled_reminders(db)` | 5 min | 600 s | no | global | the service commits its own pass |
| `adaptive_signal_refresh` | `AdaptivePreferenceSignalService.recompute_adaptive_signals(db, profile_id)` | 6 h | 1,800 s | no | per researcher | one committed unit per researcher |
| `governance_refresh` | `PersonalizationGovernanceService.recompute_governance(db, profile_id)` | 12 h | 1,800 s | no | per researcher | one committed unit per researcher |
| `opportunity_refresh` | `scrapers.pipelines.collect_opportunities.run_pipeline(...)` | 24 h | 1,800 s | **yes (WikiCFP)** | global | the pipeline opens and commits its own session |

**Idempotency** comes from the services, not from the scheduler:

- `deadline_expiry` only selects `ACTIVE`/`UNVERIFIED` records past their deadline, so a second
  run expires nothing.
- `reminder_dispatch` deduplicates on each notification's SHA-256 `deduplication_key`, which is
  also a unique constraint, so repeating a pass (or racing an administrator-triggered pass)
  cannot create a notification twice.
- `adaptive_signal_refresh` upserts on `(profile_id, dimension, signal_value)` and deletes
  signals that lost their evidence.
- `governance_refresh` upserts one evaluation per `(profile_id, algorithm_version)` and appends
  a governance event only when the gate state actually changes.
- `opportunity_refresh` goes through the pipeline's own deduplication and persistence.

**Failure behaviour.** A job that raises is recorded as `FAILED` and nothing else is affected.
In the per-researcher jobs a researcher whose unit fails is rolled back, counted and skipped,
and the run finishes as `PARTIAL`. A failed governance evaluation leaves the previous gate in
force; it never falls back to a more permissive state.

The opportunity pipeline's `--sweep-expired` path is not used, because expiry has its own
job. (In that pipeline the sweep runs after the batch commit and is never committed itself;
that is pre-existing and outside this phase.)

## 2. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SCHEDULER_ENABLED` | `false` | Starts the scheduler in the backend process. |
| `SCHEDULER_OPPORTUNITY_REFRESH_ENABLED` | `false` | Also schedules WikiCFP ingestion. It is the only job that makes outbound requests, so enabling local maintenance never starts third-party scraping. |
| `SCHEDULER_OPPORTUNITY_REFRESH_TOPIC` | `artificial intelligence` | Passed to the pipeline. |
| `SCHEDULER_OPPORTUNITY_REFRESH_MAX_PAGES` | `1` | Passed to the pipeline (1–20). |
| `SCHEDULER_DEADLINE_EXPIRY_INTERVAL_SECONDS` | `3600` | Seconds between run starts (minimum 60, as for all intervals). |
| `SCHEDULER_REMINDER_INTERVAL_SECONDS` | `300` | The default reminder rules are 14 d / 7 d / 3 d / 24 h, so five minutes is well inside every due window. |
| `SCHEDULER_ADAPTIVE_REFRESH_INTERVAL_SECONDS` | `21600` | |
| `SCHEDULER_GOVERNANCE_REFRESH_INTERVAL_SECONDS` | `43200` | Governance windows are 14 and 60 days. |
| `SCHEDULER_OPPORTUNITY_REFRESH_INTERVAL_SECONDS` | `86400` | |

In Docker Compose the backend receives `SCHEDULER_ENABLED` and
`SCHEDULER_OPPORTUNITY_REFRESH_ENABLED` from the root `.env` (both default to `false`). The
interval, topic and page settings keep their defaults there; add them to the backend's
`environment` in `docker-compose.yml` to change them.

**Run the scheduler in one process.** Every process with `SCHEDULER_ENABLED=true` runs its own
scheduler. The locks below guarantee that two processes never run the same job at the same
time, but with N processes an idempotent job can run up to N times per interval. That is
harmless for the four local jobs; for `opportunity_refresh` it multiplies requests to
WikiCFP. The Compose backend runs a single uvicorn worker.

## 3. How it works

**Lifecycle.** The FastAPI lifespan (`app/scheduler/lifecycle.py`) builds the scheduler only
when `SCHEDULER_ENABLED` is true, starts it once, and stops it at shutdown. Each job gets an
asyncio task that waits for its first due time (60 s after startup, then 15 s apart per job so
they do not all start together), dispatches a run, and repeats every interval measured from
start to start. A run that overruns its interval is followed immediately by the next one,
never by several at once.

**Execution boundary.** The services are synchronous SQLAlchemy code. Each run executes in its
own daemon thread and the event loop only awaits a future, so request handling is never
blocked by a job. At most two runs execute at once.

**Database scope.** Every run opens its own sessions through `JobContext.session()`, never a
request's session. Each session is rolled back if its block raises and is always closed.
Commits are explicit, in the adapters, exactly where the service leaves the transaction to its
caller. The per-researcher jobs load researchers in keyset-paginated batches of 100 and close
the session after each batch, so memory stays bounded.

**Job locks.** Before any work a run takes a lock named after its job, without waiting:

- On PostgreSQL this is a session-level advisory lock (`pg_try_advisory_lock`) with a key derived
  from the job name by SHA-256, so it is the same in every process and after every restart.
  The lock is held on a connection dedicated to the run, and the run's sessions are bound to
  that same connection, so a `statement_timeout` equal to the job's budget bounds every
  statement it issues. On release the timeout is reset, the lock is released and the
  connection returns to the pool; if that fails the connection is discarded, which makes the
  server drop the lock. If the process dies, PostgreSQL releases the lock with the connection.
- On any other database (the SQLite test databases, which only one process uses) an in-process
  lock gives the same semantics.

If the lock is taken the run is recorded as `SKIPPED_LOCKED` and nothing waits. A run whose
previous run in the same process has not finished is recorded as `SKIPPED_RUNNING`.

**Per-researcher lock.** `adaptive_signal_refresh` recomputes governance too (P1-8), so both
personalization jobs can evaluate the same researcher at the same moment. Each would then read
the old gate state and append the same transition event. Each researcher's unit of work
therefore takes a transaction-scoped advisory lock (`pg_advisory_xact_lock`) on that researcher
first, so the second evaluation reads the first one's committed result. With the two
evaluations forced to line up, this was verified on PostgreSQL: 2 identical events without the
lock and 1 with it.

**Timeouts.** A run that exceeds its budget is recorded as `TIMED_OUT` and signalled to stop.
Jobs check for that signal between units of work (between researchers, and before each
single-call job starts); the unit in progress is rolled back and the lock is released as the
run unwinds. The lock is taken and released by the worker itself, so a run that is stuck
inside a single call keeps its lock until the call returns. Later runs are then skipped rather
than overlapped. Statement timeouts (PostgreSQL) and the ingestion HTTP client's 10 s connect /
20 s read timeouts bound those calls.

**Failure isolation.** Every outcome of a run is recorded without leaving the dispatcher, so a
failing job stops neither its own loop nor any other. A job that raises `SystemExit` or
`KeyboardInterrupt` is recorded as an ordinary failure rather than stopping the server.

**Graceful shutdown.** On shutdown the loops stop, running jobs are signalled, and the
scheduler waits at most 5 s for them (inside Docker's default 10 s stop grace period). Job
threads are daemon threads and cannot hold the process open; any lock they still hold is
released by PostgreSQL when the process exits. Verified in the container: `docker compose stop
backend` completes in about a second with `Scheduler stopped` and `Application shutdown
complete` in the log.

## 4. Personalization safety

The jobs call the same service functions as the on-demand endpoints, so every Phase 5 and P1
rule those functions enforce applies unchanged, with no bypass:

- **Reset boundary (P1-1).** `recompute_adaptive_signals` excludes interactions at or before the
  researcher's last reset; a scheduled refresh after a reset builds nothing from pre-reset
  evidence.
- **Governance (P1-5, P1-8).** Governance failures leave the previous gate in force. A failed
  governance step after a signal refresh does not discard the refreshed signals.
- **Exclusions, relevance dominance, the personalization cap and cross-researcher isolation**
  live in ranking, which the scheduler does not touch. Each unit of work is scoped to one
  researcher's own data.

**Which researchers are processed.** Scheduled work is proactive, so it only touches a
researcher when the state it maintains is in use under their own Phase 5.9 controls.
Researchers without a settings row have the documented defaults, with every control on.

| Job | Processes a researcher when |
|---|---|
| `adaptive_signal_refresh` | they have interactions or signals, **and** personalization, adaptive signals and feedback learning are all on. "Feedback learning off" means new behaviour must not be aggregated, so their signals are left exactly as they are. |
| `governance_refresh` | they have signals or a governance evaluation, **and** personalization and adaptive signals are on. The gate is refreshed even when feedback learning is off, because it damps the signals that still apply. |

These are selection rules only. The controls are still enforced where personalization is
applied, the jobs never modify a researcher's settings, and the on-demand recompute endpoints
behave exactly as before.

## 5. Observability

Every dispatch gets a unique `run_id`. A run that takes its lock logs a `started` line. Every
run, including skips, ends with one summary line carrying `job_name`, `run_id`, `trigger`,
`status`, `started_at`, `finished_at`, `duration_seconds`, `records_processed`, `items_failed`,
`error_type` and job-specific counts (`LOG_FORMAT=json` emits them as fields). While a run
executes, the run id also fills the log correlation slot that HTTP requests fill with
`X-Request-ID`, so every line the job's services log can be traced to the run.

Errors are logged as a type plus the first line of the message. A database error's full text
carries the SQL statement, its parameters and the driver's `DETAIL` line, so those are not
logged. Nothing logs credentials or tokens.

`Scheduler.metrics` keeps per-job counters in process memory: executions, successes, partial
successes, failures, timeouts, cancellations, lock skips, total and last duration, last
records processed, and last success and failure times. There is no metrics server, matching
the rest of the backend.

## 6. Testing

`backend/tests/test_scheduler.py` triggers jobs with `Scheduler.run_job_now()` and coordinates
blocking with threading events, so no test waits out an interval.

- **Lifecycle:** off by default, starts once when enabled, graceful shutdown with no leaked tasks,
  threads or locks.
- **Registry:** exactly the approved jobs; the network job only when its flag is set.
- **Adapters:** each job calls its service and nothing else, with spies at the service boundary;
  a syntax-level check confirms the scheduler code references no engine, reset-cutoff,
  deduplication, expiry or scraping internals.
- **Failure handling:** isolation, `SystemExit` containment, overlap prevention, lock release
  after failure and after timeout, and a stuck run keeping its lock.
- **Idempotency:** every local job run twice on real services.
- **Safety:** reset boundary, consent selection, governance failure.
- **Scaling:** query counts at 10 / 50 / 100 researchers, and independence from interaction
  history.
- **Network:** no network access by default, and the application does not import the scraping
  pipeline at startup.
- **Observability:** run ids and log correlation, metrics and log fields, sanitized database
  errors.
- **Sessions and concurrency:** new session per run, closed, rolled back on error; work off the
  event loop; bounded concurrency.
- **PostgreSQL (when reachable):** two scheduler instances contending for one advisory lock;
  release after failure and timeout; the run's session on the lock-holding connection with its
  statement timeout reset afterwards; per-researcher serialization.
- **Opt-in** with `RUN_POSTGRES_MIGRATION_TESTS=1`: the concurrent adaptive/governance race on an
  isolated database.

Measured SQL statements per run (SQLite, batches of 25). Both jobs spend exactly the same
statements on every researcher, plus one keyset query per batch; an interaction history of 2
or 16 events per researcher makes no difference. On PostgreSQL each researcher adds one
statement for the per-researcher lock.

| Researchers | `adaptive_signal_refresh` | `governance_refresh` |
|---|---|---|
| 10 | 201 (20 each + 1) | 141 (14 each + 1) |
| 50 | 1,003 (20 each + 3) | 703 (14 each + 3) |
| 100 | 2,005 (20 each + 5) | 1,405 (14 each + 5) |

The per-researcher cost is the service's own. `adaptive_signal_refresh` includes the governance
recomputation that follows every signal refresh.

## 7. Limitations

- **Multiple processes:** with the scheduler enabled in N processes, an idempotent job can run up
  to N times per interval (never concurrently). Enable it in one process.
- **Reminder retries:** `run_scheduled_reminders` re-attempts a notification whose delivery
  failed on every pass while its reminder is due, and has no attempt cap. Scheduled every five
  minutes, a permanently failing delivery is retried at most once per pass until its deadline
  passes, and each attempt is recorded. The default email provider is the in-memory mock, so
  in practice only a missing or invalid address fails. Capping attempts would change Phase 4.5
  delivery behaviour and is left for a follow-up.
- **Single-call jobs:** `reminder_dispatch`, `deadline_expiry` and `opportunity_refresh` are a
  single service call each, so a timeout stops them only when that call returns. Statement
  timeouts and HTTP timeouts bound them.
- **Large first sweeps:** `run_scheduled_reminders` and `expire_past_opportunities` load their
  working sets in one pass (the reminder engine in chunks of 400 ids). Both are the existing
  services' behaviour.
- **Metrics are per process and in memory;** they are not persisted or exposed over HTTP.
