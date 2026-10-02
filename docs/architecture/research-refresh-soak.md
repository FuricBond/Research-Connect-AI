# Research Refresh — 72-Hour Soak

The scheduled `research_refresh` job was switched on in the Docker stack for a 72-hour soak
after the end-to-end verification below. This page records how it was started, what was
verified first, and what to check when the soak ends. Background on the job is in
[OpenAlex: Scheduled refresh](../research-data/openalex.md#scheduled-refresh) and
[Phase 6.3](phase6-3-scheduler.md).

## Start

- **Soak start:** 2026-10-02 17:15:53 UTC (backend restarted on the 8-hour schedule). Its
  first run, `77cda70f` at 17:17:53, SUCCEEDED in 10.4 s; the next are due about every 8 hours
  from then (01:18, 09:18, 17:18 UTC).
- **Check at:** 2026-10-05 17:16 UTC or later.
- **Configuration** (root `.env`; no values from it are recorded here beyond these switches):
  `SCHEDULER_ENABLED=true`, `SCHEDULER_RESEARCH_REFRESH_ENABLED=true`,
  `SCHEDULER_RESEARCH_REFRESH_INTERVAL_SECONDS=28800`, `RESEARCH_REFRESH_MAX_WORKS=100000`
  (raised from the 50,000 default because the corpus already held 54,998 works; at the cap the
  refresh adds nothing). Subfield `1702`, one 200-work page per lane, windows 14 and 365 days.
  No OpenAlex email or API key is configured, so the job runs on the keyless daily budget
  (each run spends about 2 calls). WikiCFP ingestion stays off.
- **Evaluation snapshot:** saved by the project owner before the job was switched on.

## Baseline

Before the first live run (2026-10-02 17:08 UTC): 54,998 research works, 0 without an
embedding, `research_works` 543 MB in total.

## Verification before the soak

Every suite green on the branch: backend, scrapers, the opt-in PostgreSQL tests (the job
against a temporary database, and the scheduler's advisory-lock tests), Vitest, type-check,
lint and the production build. The two known wall-clock benchmarks failed once under load and
passed when rerun alone.

The review fixed two defects, each with a test:

1. **API key in urllib3 logs.** Besides the request lines already filtered, urllib3 writes
   the full request URL, query string and key included, from `urllib3.connection` (a response
   with malformed headers, at WARNING), `urllib3.util.retry` (every retry, at DEBUG) and
   `urllib3.poolmanager` (redirects, at INFO). All four URL-writing loggers are now redacted.
2. **Topic processing re-examined every untagged work on every run.** 21,045 works in this
   corpus match no topic and stay untagged, so each refresh would have spent about 7 minutes
   (19 ms a work, measured) re-examining them. Topic assignment in a refresh now covers only
   works created since the refresh started (less a 5-minute clock margin).

Live run in Docker with a 120-second interval (2026-10-02, UTC):

| Run | Started | Status | Inserted | Updated | Topics examined | Embedded | Duration |
|---|---|---|---|---|---|---|---|
| `0a69807b` | 17:10:39 | SUCCEEDED | 381 (200 newest, 181 rising) | 12 | 381 | 381 | 24.2 s |
| `4761b106` | 17:12:39 | SUCCEEDED | 0 | 0 (400 unchanged) | 110 | 0 | 9.9 s |
| `1aa24166` | 17:14:39 | SUCCEEDED | 0 | 0 (400 unchanged) | 110 | 0 | 10.1 s |

Runs two and three fetched the same top pages two minutes later, so every work was unchanged.
The 110 works they examined for topics were the first run's works that match no topic, still
inside the 5-minute clock margin because the test interval was 2 minutes; on the 8-hour
schedule that overlap does not occur. After the three runs: 55,379 works, 55,379 distinct
OpenAlex ids (no duplicates), 0 without an embedding, 549 MB (about 16 KB a work).

## Checks at the end of the soak

Run these from the repository root (they read only):

```bash
docker exec researchconnect-postgres psql -U researchconnect -d researchconnect -c "SELECT status, count(*) FROM ingestion_runs WHERE topic LIKE 'research_refresh:%' AND started_at > now() - interval '72 hours' GROUP BY status;"
```

```bash
docker exec researchconnect-postgres psql -U researchconnect -d researchconnect -c "SELECT pg_size_pretty(pg_total_relation_size('research_works'));"
```

```bash
docker exec researchconnect-postgres psql -U researchconnect -d researchconnect -c "SELECT count(*) AS works, count(DISTINCT openalex_id) AS distinct_ids, count(*) FILTER (WHERE embedding IS NULL) AS missing_embeddings FROM research_works;"
```

```bash
docker compose logs backend --since 73h | Select-String "Scheduled job research_refresh run"
```

**Expected:**

- About 9 runs in 72 hours (one about 2 minutes after each backend start, then every 8 hours).
  The status query counts passes, two per run, so about 18, all `COMPLETED`. A `FAILED` pass
  is acceptable only with a stated reason (a spent budget or a failed request); two runs in a
  row in which every pass failed raise an in-app alert to the admins.
- Storage growth near 13 MB a day, so `research_works` around 590 MB after 72 hours.
- `works` equal to `distinct_ids` (no duplicates) and `missing_embeddings` at 0.
- No `TIMED_OUT` or `FAILED` job runs in the backend log.
- The admin page's Data freshness card shows the scheduled refresh on, every 8 h, the last
  run, papers added in the last 24 hours and the next run.

## Stopping or rolling back

- **Pause:** set `SCHEDULER_RESEARCH_REFRESH_ENABLED=false` in the root `.env`, then
  `docker compose up -d backend`. The other maintenance jobs keep running while
  `SCHEDULER_ENABLED=true`.
- **Roll back the corpus:** restore the evaluation snapshot taken before the soak (see Backup
  and restore in [the database guide](../database/postgres-pgvector.md)).
