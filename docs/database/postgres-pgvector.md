# PostgreSQL and pgvector

ResearchConnect AI stores everything in one PostgreSQL 16 database with the `pgvector`
extension: relational data for every subsystem, 384-dimensional embeddings
(`all-MiniLM-L6-v2`) for semantic search, and stored `tsvector` columns for full-text search.
The schema is managed by Alembic and currently has 28 migrations and 49 tables.

## Configuration

| Item | Value |
|---|---|
| Engine | PostgreSQL 16 with pgvector; Compose runs `pgvector/pgvector:0.8.6-pg16` |
| Driver | SQLAlchemy 2.0 with psycopg 3 (`postgresql+psycopg://…`) |
| Connection | `DATABASE_URL`. Compose builds it from `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` in the root `.env`; a host-run backend reads it from `backend/.env`. |
| Development default | `postgresql+psycopg://researchconnect:researchconnect@localhost:5432/researchconnect`, refused at startup when `APP_ENV=production` ([Phase 6.4](../architecture/phase6-4-production-configuration.md)) |
| Storage | The `postgres_data` Compose volume. The port is published on `127.0.0.1:5432` only. |

`POSTGRES_PASSWORD` is fixed when the volume is first created; changing it later needs
`docker compose down -v`, which deletes all data.

## Initialization and migrations

On first start of an empty volume, `backend/app/db/init.sql` enables the `vector` extension and
creates the `alembic_version` table with a `VARCHAR(255)` column, because most revision IDs are
longer than Alembic's default of 32 characters. Neither step depends on it: migration `0001`
creates the extension and `alembic/env.py` widens the version table, so any empty PostgreSQL
database with pgvector available migrates correctly. On a managed service, the migration role
needs permission to create the `vector` extension, or it must be enabled beforehand.

The schema itself comes only from Alembic migrations (`backend/alembic/versions`, `0001` to
`0028`):

- **Compose:** the one-shot `migrate` service waits for the database
  (`python -m scripts.wait_for_db`), runs `alembic upgrade head`, and exits. The backend starts
  only after it succeeds.
- **Host:** `cd backend && alembic upgrade head`, with `DATABASE_URL` pointing at the database.
- **Concurrent runs** are serialized by a PostgreSQL advisory lock held for the whole run. A
  second run waits, then finds the database at head and does nothing.
- **Readiness:** `GET /api/health/ready` returns 200 only when the database answers and its
  schema is the build's head, and 503 naming the state otherwise (`behind`, `unrecognized`,
  `uninitialized`, `unreachable`). In production the backend refuses to start unless the schema
  is current. See [Phase 6.5](../architecture/phase6-5-database-startup.md).

| Migrations | Phase | Adds |
|---|---|---|
| 0001 | 1 | Users, research profiles, sources, opportunities, topics, saved opportunities |
| 0002 | 2.1 | Ingestion hardening and run metrics (`ingestion_runs`) |
| 0003–0004 | 2.2 | OpenAlex and Crossref research knowledge |
| 0005 | 2.3A | Topic taxonomy and aliases |
| 0006 | 2.3B | Embedding columns and HNSW indexes |
| 0007 | 2.4I | Full-text `fts_vector` columns and GIN indexes |
| 0008–0010 | 3.1–3.3 | Researcher profile, interests and preferences |
| 0011–0016 | 4.1–4.6 | Workspace, submissions, documents, calendar, reminders and notifications, collaboration |
| 0017–0023 | 5.1–5.9 | Personalization: preferences, interactions, adaptive signals, calibration, quality, governance, transparency controls |
| 0024–0025 | 6 | Feedback and recommendation-history tables; the personalization reset cutoff |
| 0026–0028 | 5.10–5.12 | Research postings, applications, peer discovery |

## Tables

| Area | Tables |
|---|---|
| Accounts and profiles | `users`, `research_profiles`, `researcher_interests`, `researcher_preferences`, `researcher_discovery_settings` |
| Opportunities and ingestion | `sources`, `opportunities`, `opportunity_topics`, `saved_opportunities` (also the Phase 4.1 workspace lifecycle), `ingestion_runs` |
| Research knowledge | `research_works`, `research_sources`, `researchers`, `institutions`, `research_work_authors`, `research_work_institutions`, `research_work_topics` |
| Taxonomy | `topics`, `topic_aliases` |
| Research management | `research_submissions`, `research_submission_documents`, `research_submission_document_versions`, `research_submission_events`, `research_calendars`, `research_calendar_events`, `workspace_members`, `workspace_invitations`, `workspace_tasks`, `workspace_activities` |
| Notifications | `notifications`, `notification_delivery_attempts`, `reminder_rules`, `researcher_notification_preferences` |
| Recommendation history | `researcher_recommendation_feedback`, `researcher_recommendation_snapshots`, `researcher_recommendation_items` |
| Personalization | `researcher_interactions`, `adaptive_preference_signals`, `personalization_calibrations`, `recommendation_feedback_attributions`, `personalization_contextual_adaptations`, `personalization_quality_evaluations`, `personalization_drift_evaluations`, `personalization_governance_events`, `researcher_personalization_settings`, `personalization_control_events` |
| Research postings | `research_postings`, `research_posting_topics`, `research_posting_applications` |

## Search columns

- **Vectors:** `opportunities.embedding` and `research_works.embedding` are `vector(384)` with
  HNSW indexes on `vector_cosine_ops`. Embeddings are generated offline with
  `python -m ml.embeddings.generate_embeddings`; the demo seeder does not create them.
- **Full text:** `opportunities.fts_vector` and `research_works.fts_vector` are
  `GENERATED ALWAYS … STORED` `tsvector` columns with GIN indexes. The database computes them,
  so the ORM maps them as database-owned and never writes them.

## Backup and restore

```bash
docker compose exec -T postgres pg_dump -U researchconnect -Fc researchconnect > researchconnect.dump
```

```bash
docker compose exec -T postgres pg_restore -U researchconnect -d researchconnect --clean --if-exists < researchconnect.dump
```

## Tests

Most backend tests use in-memory SQLite. `tests/test_database_startup.py` checks the migration
chain itself (one head, linear, every revision reversible) without a database server. Tests
that need PostgreSQL (the scheduler's advisory locks, and the opt-in migration and concurrency
tests enabled with `RUN_POSTGRES_MIGRATION_TESTS=1`) use the database in `DATABASE_URL` and
skip when it is unreachable. The opt-in tests create and drop their own temporary databases.
They cover a fresh upgrade to head, idempotency, parity with the ORM models, a full downgrade
and upgrade round trip, and concurrent runs.
