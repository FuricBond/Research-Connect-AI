# ResearchConnect AI — Codebase Reconstruction & Completion Audit

**Date:** 2026-09-24 · **Mode:** audit only, no repository changes · **Audited:** `D:\Project\researchconnect-ai` @ `2671e5b` (main)

---

## 0. How this audit was done (and its limits)

**Source of truth.** I read the code in your local folder. For test runs I used a byte-identical clone of `origin/main` (`7bad228`) in a cloud sandbox. `2671e5b` changes only `README.md` and one eval artifact. I checked "identical" by hashing 525 code, test and doc files with CRLF stripped, and every hash matched.

**What I executed:**

| Check | Environment | Result |
|---|---|---|
| Backend `pytest` (whole suite, SQLite in-memory fixtures) | Python 3.11, FastAPI 0.115.6, SQLAlchemy 2.0.36 (pure-python), taken from your `.venv` | **1235 passed, 4 failed, 8 skipped** |
| The 8 Postgres-gated tests, against a **real PostgreSQL 16 + pgvector 0.8.0** built in the sandbox | same | 6 now pass; 2 skip for lack of seeded embedding data |
| `alembic upgrade head` on a fresh Postgres | same | **FAILS at 0001→0002** (see P0-DB-1) |
| Live API smoke test on a migrated Postgres (TestClient, no mocks) | same | **Core recommendation endpoints return 500** (see P0-DB-3) |
| WikiCFP persistence (`OpportunityRepository.save_batch`) on migrated Postgres | same | **0 inserted, 1 error** (see P0-DB-2) |
| Authorization probe (anonymous / cross-user / spoofed requests) | TestClient + SQLite | Confirmed P0-SEC-1…4 |
| `scrapers/tests` | same | 380 passed, 9 failed (all need `sentence_transformers`, which isn't installed in the sandbox → environment issue) |
| Frontend `tsc --noEmit` | on your machine (copy of `frontend/` + your `node_modules`) | **0 errors** |
| Frontend `eslint` | same | 0 errors, 5 warnings (`react-hooks/exhaustive-deps`) |
| `next build` | — | **Not run.** Your `node_modules` only has `@next/swc-win32-x64-msvc`, and the npm/PyPI registries are blocked here |

**Housekeeping.** My first `git status` left a stale `.git/index.lock` in your repo. I also created two temporary dependency tarballs in `.venv/`. All three are deleted. I made no other changes to your folder.

---

## 1. Repository map

| Path | Contents | Subsystem | Kind | Connects to |
|---|---|---|---|---|
| `backend/app/main.py` | FastAPI app; CORS, correlation-ID, cache and rate-limit middleware; mounts 9 routers under **both** `/api/v1` and `/api` | API | Production | All routers |
| `backend/app/api/` | `health.py`, `opportunities.py` (legacy `/api/opportunities`), `v1/{discovery,researchers,workspace,submissions,calendar,notifications,workspace_collaboration}.py` — 167 route handlers | API | Production | services/* |
| `backend/app/core/` | `config.py` (pydantic-settings, `.env`), `cache.py`, `rate_limiter.py`. **No auth module.** | Infra | Production | main.py |
| `backend/app/db/` | `session.py` (engine/`get_db`), `types.py` (`Vector`, `TSVector`), `init.sql` (`CREATE EXTENSION vector`) | DB | Production | models, alembic, docker |
| `backend/app/models/` | 45 SQLAlchemy tables (users, profiles, opportunities, research works, topics, workspace, submissions, calendar, notifications, collaboration, Phase 5 tables) | DB | Production | services, alembic |
| `backend/alembic/versions/` | 23 linear migrations `0001`…`0023` | DB | Production | Postgres |
| `backend/app/repositories/` | `lexical_repository.py` (FTS `websearch_to_tsquery`), `vector_repository.py` (pgvector cosine) | Retrieval | Production | hybrid_search, matching |
| `backend/app/search/` | `rrf.py` (RRF, k=60), `query_intelligence.py` | Retrieval | Production | hybrid_search |
| `backend/app/ranking/` | `hybrid_ranker.py`, `features.py`, `signals.py`, `diversity.py`, `reranker.py`, `venue_intelligence.py`, `personalization_ranker.py`, `feedback_engine.py`, `recommendation_explainer.py`, `recommendation_evaluation_engine.py`, `risk/*` (11 files), `deadline/*` (7 files) | Ranking / risk / deadlines | Production | discovery API, personalization service |
| `backend/app/personalization/` | Phase 5 pure engines: `interpreter.py`, `scorer.py`, `adaptive_engine.py`, `calibration_engine.py`, `quality_engine.py`, `governance_engine.py`, `transparency_engine.py`, `models.py` | Personalization | Production | services, ranker |
| `backend/app/services/` | 28 orchestration services (DB + engines) | Business logic | Production | API |
| `backend/app/explainability/result_explainer.py` | Discovery explanation | Explainability | Production | discovery API |
| `backend/app/schemas/` | 25 Pydantic schema modules | API contracts | Production | API |
| `backend/app/evaluation/` | Benchmark, risk and deadline datasets and runners, metrics, `benchmark_results.json` | Evaluation | Tooling | artifacts/ |
| `backend/tests/` | 88 test modules (+ conftest), ~1247 tests | Tests | Testing | app |
| `scrapers/` | `sources/{wikicfp,openalex,crossref}.py`, parsers, normalizers, validators, dedup, change detection, freshness, expiration, persistence, `pipelines/collect_*.py`, 31 test files | Ingestion | Production + tooling (CLI) | backend models (imports `app.models`) |
| `ml/embeddings/` | `service.py` (sentence-transformers `all-MiniLM-L6-v2`, 384-dim), `text_builder.py`, `generate_embeddings.py` CLI | ML | Tooling + runtime (query embedding) | vector repo, hybrid search |
| `ml/topic_analysis/` | Taxonomy, extraction, normalization, assignment, `process_topics.py` CLI | Enrichment | Tooling | topics tables |
| `frontend/` | Next.js 15.5 App Router, React 19, TS 5.7. 13 pages, 35 components, `services/api.ts` (2,644 lines, 125 `fetchJson` calls) | Frontend | Production | backend over HTTP |
| `docs/` | 61 architecture docs (one per phase), `METHODOLOGY.md/.docx`, api/db/scraping/eval notes | Docs | Documentation | — |
| `artifacts/evaluation/` | 6 JSON results (2.4M, 2.5E/F/G, 2.6G risk, 2.7G deadline) | Evaluation output | Generated | — |
| `graphify-out/`, `.agents/` | Graphify / agent output (gitignored) | Tooling | Generated | — |
| `docker-compose.yml` | **Postgres only** (`pgvector/pgvector:pg16`) with `init.sql` | Infra | Config | backend via `DATABASE_URL` |
| `.env.example` | App, DB, API URL, OpenAlex, Crossref, embedding settings. **No `CORS_ORIGINS`.** No `.env` exists anywhere in the repo. | Config | — | config.py |
| CI/CD, Dockerfiles | **None** | — | — | — |

---

## 2. Git history and working tree

- **Branch:** `main`, HEAD `2671e5b`, 1 commit ahead of `origin/main` (README only), 65 commits total.
- **Uncommitted changes:** 23 modified files, all **line-ending (CRLF) only**. `git diff --ignore-all-space --ignore-cr-at-eol --stat` is empty, so there are no real partial edits. No untracked files.

**Timeline:**

| Date | Commits | Content |
|---|---|---|
| 08-23 → 08-24 | `7739d5f`, `26b1244` | Monorepo init; Phase 1 DB, opportunity API, WikiCFP pipeline |
| 08-25 | `fb755cd` `b559f4f` `7c9ff59` `147e394` | 2.1 ingestion hardening, 2.2A OpenAlex, 2.2B Crossref, 2.3A taxonomy |
| 08-26 → 09-01 | `6443672` … `fdd2b65` | 2.3B embeddings + pgvector, 2.4A–M vector, hybrid, RRF, matching, ranking, explainability, API, FTS, frontend discovery, reranker |
| 09-02 → 09-04 | `6bd8072` … `40249aa` | 2.5 academic ranking, 2.6 risk engine (B–G), 2.7 deadline intelligence (A–G) |
| 09-05 → 09-08 | `ba92a85`, `91edd05` | Vite→Next.js 15 migration; dead-code cleanup |
| 09-09 → 09-12 | `d2c4b39` … `4317067` | Phase 3.1–3.9 profile, interests, preferences, candidates, ranking layer, feedback (3.6), history (3.7), explainability, hardening |
| 09-18 → 09-19 | `d4842be` … `a1ca2d9` | Phase 4.0–4.7 workspace, submissions, documents, calendar/iCal, reminders, collaboration, integration |
| 09-19 → 09-20 | `2db1639` … `dfb0c5a` | **Phase 5.1–5.9** |
| 09-22 | `90042db` "Debugging" | **P0 remediation #1:** `personalization_ranker.py` (+440), `personalization_ranking_service.py` (governance, settings, adaptive loading), `test_p0_phase5.py`, `test_phase5_integration.py`, `docs/METHODOLOGY.md` |
| 09-24 | `7bad228` "Debugging" | **P0 remediation #2 (authz):** `researchers.py` refactored to one `_resolve_researcher_profile_auth` helper that now **requires** `X-User-ID` (before, ownership was checked only *if* the header was present); `PHASE_5_P0_BLOCKER_RESOLUTION_REPORT.md` deleted |
| 09-24 | `2671e5b` | README |

Notable: the Phase 3.6/3.7 commits (`78759d4`, `f4fab99`) added the models `researcher_feedback.py` and `recommendation_history.py` **but no Alembic migration** (see P0-DB-3).

---

## 3. Actual architecture (what the code really does)

There are **two separate ranking pipelines**, not the single pipeline in the concept diagram.

**Pipeline A — Discovery (research works; query-driven, public)**
```
GET /api/v1/discovery/research/search?q=…          discovery.py::search_research_works_route
 → HybridSearchService.search_research_works()       services/hybrid_search_service.py
    → QueryIntelligenceService.process(q)            search/query_intelligence.py  (normalized + expanded query)
    → LexicalRepository.search_research_works()      repositories/lexical_repository.py  (websearch_to_tsquery on research_works.fts_vector, GIN)
    → EmbeddingService.encode_one()                  ml/embeddings/service.py (all-MiniLM-L6-v2)
    → VectorRepository.search_research_works()       repositories/vector_repository.py (pgvector cosine, HNSW)
    → fuse_ranked_candidates(k=60)                   search/rrf.py  (RRF)
 → hybrid_ranker.rank(mode=…)                        ranking/hybrid_ranker.py
 → [optional] cross_encoder_reranker.rerank          ranking/reranker.py
 → [optional] diversity_reranker.rerank              ranking/diversity.py
 → [optional] result_explainer.explain_batch         explainability/result_explainer.py
 → ResearchSearchResponse
```
Opportunities reach users through `GET /discovery/research/{work_id}/opportunities` (`ResearchOpportunityMatchingService`: vector + lexical + topic + type → `hybrid_ranker`, with the risk and deadline explanations attached in `discovery.py` ~L702–708), and through `GET /api/opportunities?search=` (`opportunity_service.list_opportunities`, which is plain **`LIKE`**, not FTS or vectors). `HybridSearchService.search_opportunities()` exists but **no route calls it**.

If `sentence_transformers` is missing, the vector channel is caught and logged (`"Vector search … failed"`), and search quietly falls back to lexical-only.

**Pipeline B — Personalized recommendations (researcher-scoped)**
```
GET /api/v1/researchers/{id}/personalized-recommendations   researchers.py::get_personalized_recommendations (auth: _resolve_researcher_profile_auth)
 → PersonalizationRankingService.get_personalized_recommendations()   services/personalization_ranking_service.py
    L121-170  load profile, active prefs (EXPLICIT / INFERRED≥0.40), interests
    L172-199  ResearcherPersonalizationSettingsModel → personalization_enabled / adaptive_signals_enabled
    L201-222  PersonalizationGovernanceService.get_active_governance_state()  (SUSPEND ⇒ personalization off)
    L224-248  AdaptivePreferenceSignalModel rows (only if both flags on)
    L250-256  ResearcherFeedbackService.get_behavioral_profile()   (Phase 3.6 feedback → behavioral_signals + suppressed IDs)
    L266-284  ResearcherPersonalizationContext(... governance_state=…, adaptive_signals=…)
    L288-299  PersonalizedCandidateGenerationService.generate_personalized_candidates()  ← SQL topic/type/keyword joins, NOT hybrid retrieval
    L373-384  hybrid_ranker.rank(mode=RESEARCH_OPPORTUNITY) → base_scores
    L387-399  personalization_ranker.rank(...)          ranking/personalization_ranker.py
                 L745-783  PersonalizationScorer.score_opportunities_batch(prefs, adaptive; calibrations/contexts NOT passed; governance_state=None)
                 L857-890  exclusion detection (scorer + _matches_exclusion + legacy signals)
                 L965-990  p_adjustment = min(0.15, raw·0.15·damping) → governance multiplier
                 L994-1001 final_score
    L475      persist snapshot (recommendation history)
```
The architecture diagram's "hybrid retrieval → RRF → personalization" chain only exists in Pipeline A. Pipeline B's candidates come from preference/topic SQL, not from FTS + vector + RRF. That's a legitimate design, but it should be described that way in the viva.

---

## 4. Technology stack (verified)

- **Backend:** Python (your venv: CPython 3.13.9), FastAPI 0.115.6, Starlette 0.41.3, Pydantic 2.13, pydantic-settings 2.7.1, SQLAlchemy 2.0.36, Alembic 1.14.0, psycopg 3.2.3, pgvector 0.3.6, httpx, requests, BeautifulSoup 4.12.3, uvicorn 0.34.
- **ML:** sentence-transformers 3.3.1 (in `requirements.txt`) with torch 2.14 (in your `.venv`), model `all-MiniLM-L6-v2`, 384-dim; optional cross-encoder reranker.
- **DB:** PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`), HNSW `vector_cosine_ops` on `research_works.embedding` and `opportunities.embedding`, GIN on generated `fts_vector`.
- **Frontend:** Next.js 15.5.25, React 19, TypeScript 5.7, lucide-react. No auth library.
- **Infra:** Docker Compose (Postgres only). No Dockerfiles, no CI.

---

## 5. Phase-by-phase status

| Phase | Implemented | Integrated | Tested | E2E on real Postgres | Status |
|---|---|---|---|---|---|
| **1 Foundation** (models, migrations, config, API) | Yes | Yes | Yes (`test_models`, `test_health`, `test_opportunities`) | **No:** fresh `alembic upgrade head` fails (P0-DB-1) | **BROKEN (deployment)** |
| **2.1–2.2 Ingestion** (WikiCFP, OpenAlex, Crossref) | Yes | CLI pipelines | Yes (380 scraper tests pass) | **No:** ORM inserts fail on the generated `fts_vector` column (P0-DB-2) | **BROKEN on Postgres** |
| **2.3 Taxonomy + embeddings** | Yes | CLI (`ml/topic_analysis/process_topics.py`, `ml/embeddings/generate_embeddings.py`) | Yes (embedding tests need sentence-transformers) | Not verified | YELLOW |
| **2.4 Hybrid retrieval / RRF / matching / API** | Yes | Yes (discovery routes) | Yes + 6 PG tests pass on real pgvector | Search endpoint returns 200 on real PG (empty DB) | YELLOW (needs data) |
| **2.5 Academic ranking / diversity / explainability** | Yes | Yes | Yes | — | YELLOW |
| **2.6 Risk engine** | Yes | Partly: computed on demand in `/opportunities/{id}/risk-explanation` and in matching; `opportunities.risk_score` **never written** | Yes | — | YELLOW |
| **2.7 Deadline intelligence** | Yes | Yes (`/opportunities/{id}/deadlines`, matching, workspace) | Yes | — | YELLOW |
| **3.1–3.3 Profile / interests / preferences** | Yes | Yes | Yes | Profile create works; **routes unauthenticated** (P0-SEC-2) | RED (security) |
| **3.4–3.5 Candidates + personalization ranking** | Yes | Yes | Yes | **500 on real PG** (P0-DB-3) | BROKEN |
| **3.6 Feedback** / **3.7 History** | Yes | Yes | Yes (SQLite) | **Tables don't exist on PG** | BROKEN |
| **4.1–4.7 Workspace, submissions, docs, calendar, reminders, collaboration** | Yes | Yes | Yes | Fallback-identity P0 (P0-SEC-1); frontend write calls broken (P0-FE-2) | RED |
| **5.1 Preferences foundation** | Yes | Yes | Yes | CRUD requires `X-User-ID` ✔; list/structured GET are anonymous | RED (partial authz) |
| **5.2 Interpretation** | Yes (`personalization/interpreter.py`) | Yes (`test_p0_2_preference_interpreter_live_integration` passes) | Yes | — | GREEN (logic) |
| **5.3 Scorer** | Yes (`personalization/scorer.py`) | Yes (batch scorer is called from the ranker) | Yes | — | GREEN (logic) |
| **5.4 Interactions** | Yes | Yes (API + `OpportunityInteractionBar.tsx`) | Yes | Frontend POST broken (P0-FE-2) | YELLOW |
| **5.5 Adaptive signals** | Yes | Yes (loaded in ranking service L224-248); recompute is manual only | Yes | — | YELLOW |
| **5.6 Calibration** | Yes | **Not in live ranking.** Only used by the per-opportunity endpoints and transparency | Yes | — | YELLOW (implemented, not integrated) |
| **5.7 Quality / contextual** | Yes | **Not in live ranking** (same as 5.6) | Yes | — | YELLOW (implemented, not integrated) |
| **5.8 Governance** | Yes | **Yes, in the live path** (verified below) | Yes (`test_blocker2_*` pass) | — | GREEN (logic) |
| **5.9 Transparency + reset** | Yes | Yes (API + `PersonalizationSettingsCard`) | Yes | Reset returns 200 on real PG | YELLOW (semantics gaps, P1) |

---

## 6. Data collection and processing

| Source | Collector | Parser / normalizer | Persistence | Tests | Status |
|---|---|---|---|---|---|
| **WikiCFP** | `scrapers/sources/wikicfp.py`, `pipelines/collect_opportunities.py` | `parsers/wikicfp_parser.py`, `wikicfp_detail_parser.py`, `normalizers/opportunity_normalizer.py`, `validators/` | `persistence/opportunity_repo.py::_upsert_opportunity` (dedup via `deduplication/detector.py`, `change_detection/`, `freshness/`, `expiration/`) | pass | **RED on Postgres** (P0-DB-2, reproduced: `inserted=0 errors=1`) |
| **OpenAlex** | `openalex/client.py`, `sources/openalex.py`, `pipelines/collect_openalex.py` | `openalex/normalizer.py`, `openalex/validator.py` | `persistence/openalex_repo.py` → `ResearchWorkModel` | pass | **RED on Postgres** (same generated-column failure, reproduced on `ResearchWorkModel`) |
| **Crossref** | `crossref/client.py`, `sources/crossref.py`, `pipelines/collect_crossref.py` | `crossref/normalizer.py` | `persistence/crossref_repo.py` | pass | **RED on Postgres** (same model) |

Flow: `source.fetch_pages` → parser → validator → normalizer → dedup detector → change detection / expiration → `OpportunityRepository.save_batch` → `_upsert_opportunity` (ORM insert). Embeddings and topics are **separate offline CLIs** run after ingestion. Enrichment populates `opportunity_topics`/`research_work_topics` and `embedding`, `embedding_model`, `embedding_text_hash`, `embedded_at`. `risk_score` stays at its default of 0.00.

---

## 7. Ranking, personalization, governance (verified invariants)

- **Bound:** `MAX_PERSONALIZATION_CONTRIBUTION = 0.15` (`personalization_ranker.py` L49). Enforced in `__init__` (L261) and in `p_adjustment = min(max_contribution, raw·0.15·damping)` (L969). Relevance damping applies below base 0.50 (L68, L280). Final score is clamped to [0, 1] (L1001).
- **P0-1 exclusion safety:** ✔ Holds. An excluded opportunity gets `p_adjustment = 0` and `final_score = base_score` (L965–999), whatever the adaptive or behavioral evidence. Tests `test_p0_1_*` and `test_blocker1_case_a…e` pass. *Semantic caveat (P1-6):* an excluded item is not demoted or filtered, so it can still rank high on relevance alone.
- **Suppression** (Phase 3.6 DISMISS / NOT_INTERESTED): `final_score = base − 0.50` (L995).
- **High-risk gate:** `is_predatory_flag or risk_level=="HIGH_RISK" or risk_score≥0.70` (L959-961). `OpportunityModel` has no `risk_level` attribute and `risk_score` is never written, so in practice **only `is_predatory_flag` gates boosts** (P1-7).
- **P0-2 governance live path:** ✔ Verified end to end:
  `PersonalizationGovernanceService.get_active_governance_state()` (reads the latest `personalization_drift_evaluations.governance_state`, defaulting to ALLOW) → `personalization_ranking_service.py` L209 → `SUSPEND ⇒ enable_personalization=False` (L220-222) → `context.governance_state` (L281) and the `governance_state=` argument (L401) → `personalization_ranker.py` L978-990 single multiplier: SUSPEND 0.0, ALLOW_BOUNDED 0.50, HOLD 0.25, REDUCE 0.10, ALLOW 1.0. The scorer is called with `governance_state=None` (L780), so there is **no double damping**. Tests `test_blocker2_*` pass.
  *Caveats:* (a) governance and settings lookups are wrapped in `except Exception → None`, which **fails open** to ALLOW (L212-213, L188-189) (P1-5). (b) Governance state is only (re)computed when someone calls `/personalization/health`, `/drift` or `/health/recompute`. Nothing schedules it.
- **Settings:** the ranking service loads `ResearcherPersonalizationSettingsModel`, and `personalization_enabled=False` forces the baseline. `adaptive_signals_enabled=False` blocks the Phase 5.5 signals. **But** Phase 3.6 `behavioral_signals` from `researcher_recommendation_feedback` are still passed into the context (L275) and scored (`evaluate_personalization_signals` L588-632). So "adaptive disabled → no behavioral influence" is **only half true** (P1-3). `feedback_learning_enabled` is stored but **never enforced anywhere** (P1-4).
- **5.6/5.7 not in live ranking:** the ranker calls the scorer without `calibrations=` or `contextual_adaptations=` (L775-781). The per-opportunity endpoints `GET /{id}/opportunities/{opp}/personalization` and the batch version (researchers.py L1622-1636, L1666-1680) **do** pass them, and they also ignore `adaptive_signals_enabled`. The explanation the user sees can therefore differ from the ranking they get (P1-2).
- **Reset (5.9):** `PersonalizationTransparencyService.reset_personalization` deletes adaptive signals, calibrations and contextual adaptations; keeps explicit preferences and history; bumps `personalization_state_version`; writes an audit event. **Gaps (P1-1):** interactions stay (by design, append-only), and `recompute_adaptive_signals` reads *all* interactions without checking `personalization_state_version`, so the next recompute **restores the pre-reset state**. Phase 3.6 feedback and governance drift evaluations are not reset either. After a reset the researcher is therefore not truly cold-start.

---

## 8. Security audit

### 8.1 Authentication
- There is **no login, session, token, cookie or password verification.** `UserModel.hashed_password` is the literal `"auth_placeholder"` (`researcher_profile_service.py` L146).
- The only identity is the client-supplied **`X-User-ID` header** (a UUID). It is trusted as-is: anyone who knows or guesses a user's UUID *is* that user. Probe: sending `X-User-ID=<B>` gets full access to B's settings (200).
- **Fallback identity:** five routers each define their own copy of `resolve_current_user` (`workspace.py` L46, `submissions.py` L56, `calendar.py` L34, `notifications.py` L36, `workspace_collaboration.py` L61). **When the header is missing, it silently becomes the *oldest user in the database*.** This is not gated by `APP_ENV`. 87 handlers are affected.
- `WorkspaceService.resolve_user_id` returns the supplied UUID unchanged when no profile or user matches it (L112-127). Nonexistent identities are not rejected.

### 8.2 Endpoint inventory (researcher / user-scoped)

**Researchers router (`backend/app/api/v1/researchers.py`, mounted at `/api/v1/researchers` and `/api/researchers`)**

| Method + route | Auth dependency | Ownership | Status |
|---|---|---|---|
| `POST ""` create profile | none | n/a (creates or links a user by email) | ⚠ open registration (acceptable for a demo) |
| `GET /{id}` | **none** | **none** | **P0** (profile PII: email, bio) |
| `PATCH /{id}` | **none** | **none** | **P0 — anonymous write, reproduced** |
| `GET /{id}/works`, `/completeness`, `/interests`, `/expertise` | none | none | P0 (data exposure) |
| `GET /{id}/research-intelligence?refresh=true` | none | none | **P0** (anonymous recompute and persist) |
| `GET /{id}/preference-intelligence`, `/preferences`, `/preferences/structured` | **none** | **none** | **P0 — reproduced** (anonymous read of B's preferences) |
| 59 other routes: preferences POST/PUT/PATCH/DELETE, personalized-candidates, personalized-recommendations, feedback CRUD/summary/signals, recommendation-history (+snapshot, +explanations), recommendation-evaluation, personalization-summary, calendar(.ics), notifications (4), notification-preferences (2), reminder-rules (4), intelligence/unified, recommendations/unified (+intelligence), preference-match (2), personalization (2), interactions (3), adaptive-signals (4), calibration (3), quality (4), health/drift/governance (4), settings (2), reset, control-history, recommendation personalization | `_resolve_researcher_profile_auth` (L490): requires header, 401 if missing, 403 if `profile.user_id != X-User-ID` | Yes, at profile level | ✔ strict X-User-ID (still spoofable) |

Sub-resource IDs (`feedback_id`, `snapshot_id`, `signal_id`, `rule_id`, `notification_id`, `recommendation_id`) are resolved by services with a `profile_id` filter or check (e.g. `NotificationService.mark_as_read` L319-331, `get_reminder_rule` L205-216). The P0 suite `test_p0_3_all_18_endpoints_auth_matrix` and `test_blocker3_case_a…d` pass.

**Workspace / submissions / calendar / notifications / collaboration (`resolve_current_user` with fallback)**

| Router | Handlers | Ownership check in service | Status |
|---|---|---|---|
| `workspace.py` `/workspace` | 10 | ✔ `SavedOpportunityModel.user_id` or `WorkspaceAuthorizationService` membership | **P0: anonymous = oldest user** |
| `submissions.py` `/submissions` | 15 | ✔ `ResearchSubmissionService.get_submission` (PermissionError) | **P0: same** |
| `calendar.py` `/calendar` | 12 | ✔ `ResearchCalendarService.get_calendar` L218 | **P0: reproduced**. Anonymous `GET /calendar/default` returned the oldest user's calendar (and created it) |
| `notifications.py` `/notifications` | 10 | ✔ `profile_id` checks | **P0: reproduced** |
| `notifications.py` `POST /trigger-reminders` | 1 | none, no identity at all | **P0: reproduced** (anonymous 200; runs the global reminder dispatcher) |
| `workspace_collaboration.py` `/workspace(s)/{id}/…` | 40 (20 × 2 aliases) | ✔ role checks in `WorkspaceCollaborationService` / `WorkspaceAuthorizationService` | **P0: fallback identity** |

**Public by design (no user data):** `GET /api/health`, `/api/opportunities` (+`/{id}`, `/risk-explanation`, `/deadlines`), and 4 discovery routes.

**Probe transcript (reproduced against the current code):**
```
anon PATCH /researchers/{B}                       200  bio="HIJACKED by anonymous"  (persisted)
anon GET   /researchers/{B}/preferences           200  ['bob-hidden-pref']
anon GET   /researchers/{B}/preference-intelligence 200
anon GET   /researchers/{B}/personalized-recommendations 401 ✔
A    GET   /researchers/{B}/personalized-recommendations 403 ✔
spoofed X-User-ID=B GET settings(B)               200  (identity not verified)
anon GET   /workspace                             200  (as oldest user)
anon GET   /notifications                         200  (as oldest user)
anon GET   /calendar/default                      200  user_id=<oldest user>
anon POST  /notifications/trigger-reminders       200
```

---

## 9. Database audit

- 45 model tables. Migrations create 42 of them. HNSW vector indexes and GIN FTS indexes exist (0006, 0007). The chain is linear from 0001 to 0023.
- **Tables missing from migrations:** `researcher_recommendation_feedback`, `researcher_recommendation_snapshots`, `researcher_recommendation_items`. Confirmed with a live `inspect()` on a migrated DB. No other column drift.
- **Revision IDs longer than 32 characters:** 19 of 23 (longest: 47). Alembic's default `alembic_version.version_num` is `VARCHAR(32)`. Reproduced: `StringDataRightTruncation` on `0002_phase2_1_ingestion_hardening`, and the whole upgrade rolls back with 0 tables.
- **Generated-column conflict:** migration 0007 adds `fts_vector` as `GENERATED ALWAYS … STORED` on `opportunities` and `research_works`. The models (`opportunity.py` L138, `research_knowledge.py` L411) map it as an ordinary nullable column, so the ORM sends `NULL` on INSERT and Postgres rejects it.
- Why the tests don't catch any of this: every DB test uses `Base.metadata.create_all()` on SQLite, which never runs Alembic, never creates generated columns and *does* create the three unmigrated tables.
- **Your existing local DB** may have been patched by hand. To check, run `select * from alembic_version;` and `\d opportunities` in it. A **fresh** setup, which is what the demo machine needs, fails.

---

## 10. Docker and local execution

- `docker-compose.yml` is valid and defines **only `postgres`**, with the `init.sql` → `CREATE EXTENSION vector` hook. `docker compose config --services` → `postgres` is correct. If `docker compose up -d` failed because Docker Desktop was stopped, that's a **local environment issue**, not a repository bug.
- Repository issues that stop a working local run: P0-DB-1/2/3 and the CORS default (P0-FE-1). There are no backend/frontend containers or Dockerfiles, so the backend (`uvicorn app.main:app` from `backend/`) and the frontend (`npm run dev`) run on the host.
- Intended startup: `docker compose up -d` → `cd backend && alembic upgrade head` (**currently fails**) → run the scraper pipelines, then `ml/topic_analysis/process_topics.py`, then `ml/embeddings/generate_embeddings.py` (**inserts currently fail**) → `uvicorn` → `cd frontend && npm run dev` (port 3000; **CORS currently blocks it**).

---

## 11. Frontend audit

**Pages:** `/` (DiscoverySearch), `/browse`, `/opportunities`, `/similar`, `/researcher`, `/researcher/preferences`, `/workspace`, `/workspace/[id]`, `/workspace/[id]/submission`, `/calendar`, `/notifications`, `/settings/notifications`, plus `loading` and `not-found`. `tsc` is clean and lint is clean apart from warnings.

Blocking defects found by static analysis and backend reproduction:

1. **CORS (P0-FE-1).** `config.py` L12 defaults `cors_origins` to `localhost:5173/127.0.0.1:5173`, left over from Vite. Next.js runs on 3000, there's no `.env`, and `.env.example` has no `CORS_ORIGINS`. Reproduced: requests with `Origin: http://localhost:3000` get no `Access-Control-Allow-Origin` header, and preflight returns `400 Disallowed CORS origin`. **Every browser call from the Next app fails.**
2. **Lost Content-Type (P0-FE-2).** In `fetchJson` (`frontend/services/api.ts` L169-176), `{ headers: {"Content-Type": …, ...init.headers}, ...init }` is followed by `...init`, which overwrites `headers` whenever the caller passes any headers object. **35 of the 37 body-carrying calls** pass headers (e.g. `createResearcherPreference`, `recordOpportunityInteraction`, `updatePersonalizationSettings`, `addOpportunityToWorkspace`, `createSubmission`, calendar and collaboration writes). The browser then sends `text/plain` and FastAPI returns **422**. Reproduced on the backend: text/plain → 422, application/json → 201.
3. **No identity on 4 feature areas.** `app/workspace/page.tsx` L85-86, `workspace/[id]` L109, `workspace/[id]/submission` L185, `calendar/page.tsx` L86 and `notifications/page.tsx` L45 call the API without `userId`. They only work today *because of* the backend fallback, so fixing P0-SEC-1 will break them unless they're fixed together.
4. **Identity bootstrap.** `/researcher` reads `localStorage["researchconnect_active_profile_id"]`, loads the profile anonymously (`GET /researchers/{id}`, currently open), and uses `profile.user_id` as `X-User-ID`.
5. **Wrong collaboration and calendar paths (P1-9).** `revokeWorkspaceInvitation` calls `POST /workspaces/{id}/invitations/{inv}/revoke` (backend: `DELETE /workspaces/{id}/invitations/{inv}`). It's used in `workspace/[id]/page.tsx` L197. `acceptWorkspaceInvitation` and `declineWorkspaceInvitation` use `/workspaces/{id}/invitations/{inv}/accept|decline` (backend: `/workspaces/invitations/{token}/accept|decline`). `projectOpportunityToCalendar` uses `/calendar/{id}/project-opportunity` (backend: `/calendar/{id}/opportunities/{opp}/project`), though no page calls it.
6. **Display.** Risk and deadline are shown through `OpportunityCard` / `RiskWarning` / `DeadlineTimeline` / `ExplainabilityDrawer` using data embedded in the match responses. `WhyThisRecommendationModal` and the personalization cards show scorer and governance data. The standalone `fetch…/risk-explanation` and `/deadlines` helpers are unused.

| Feature | Page exists | Calls backend | Endpoint real | Identity sent | Server authz | Data displayed | Error handling | Workflow completes in browser |
|---|---|---|---|---|---|---|---|---|
| Discovery search | ✔ | ✔ | ✔ | n/a | n/a | ✔ | ✔ | ✖ CORS |
| Opportunity matches, risk, deadline | ✔ | ✔ | ✔ | n/a | n/a | ✔ | ✔ | ✖ CORS |
| Researcher profile / preferences | ✔ | ✔ | ✔ | partial | partial | ✔ | ✔ | ✖ CORS + 422 on writes |
| Personalized recs + explanation | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✖ CORS + 500 on PG |
| Interactions / adaptive / calibration / quality / governance / settings / reset | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✖ CORS + 422 on writes |
| Workspace / submissions / calendar / notifications | ✔ | ✔ | ✔ | ✖ | ✖ (fallback) | ✔ | ✔ | ✖ |
| Collaboration invitations | ✔ | ✔ | ✖ (3 wrong paths) | — | — | — | ✔ | ✖ |

---

## 12. Test audit

| Group | Files (examples) | Result |
|---|---|---|
| Security / authz / P0 | `test_p0_phase5.py` (27 tests), `test_workspace_authorization.py`, `test_phase5_integration.py` | **55/55 pass** (these three files) |
| Phase 5 | `test_phase5_1_*`, `test_preference_interpretation`, `test_personalization_{scoring,ranking,calibration,quality,governance,transparency,explainability}`, `test_researcher_interactions`, `test_adaptive_preference_signals` | pass except `test_personalization_transparency::test_transparency_performance_and_query_count` (timing) |
| Retrieval / ranking | `test_rrf`, `test_hybrid_ranker`, `test_hybrid_search`, `test_lexical_repository`, `test_vector_repository`, `test_reranker`, `test_diversity_novelty`, `test_query_intelligence`, `test_recommendation_ranker` | pass; 4 PG-gated pass on real PG |
| Risk | `test_risk_*`, `test_suspicious_graph_intelligence`, `test_venue_publisher_intelligence`, `test_phase2_6g_*` | pass except `test_risk_evidence_extraction::…test_batch_performance_zero_queries` (timing: 0.97 s vs 0.50 s) |
| Deadline | `test_deadline_*`, `test_date_timezone_normalization`, `test_phase2_7g_*` | pass |
| Phase 3 | `test_researcher_profile`, `test_feedback_learning`, `test_recommendation_history`, `test_phase3_9_hardening` | pass except `test_phase3_9_hardening::test_performance_benchmarks_zero_n_plus_one` (timing: 69.8 ms vs 50 ms) |
| Phase 4 | `test_workspace_*`, `test_research_submission_*`, `test_submission_document_*`, `test_research_calendar_*`, `test_notification_*`, `test_reminder_*`, `test_phase4_*` | pass except **`test_research_calendar_api::test_researcher_calendar_view_api`**, which is **obsolete**: its fixture hard-codes `submission_deadline=2026-09-22` (L140), now in the past |
| Scrapers | `scrapers/tests` (31 files) | 380 pass; 9 fail on missing `sentence_transformers` (environment) |
| Frontend / E2E | — | **None exist** |
| Migrations against real PG | — | **None exist** (this is the gap that hid P0-DB-1/2/3) |

The 3 timing failures are probably environmental: my sandbox runs SQLAlchemy without its C extensions. Re-run them on your machine before treating them as regressions.

---

## 13. Gap analysis

| Area | Status | Evidence | Missing | Severity |
|---|---|---|---|---|
| Authentication | RED | No login; `X-User-ID` trusted; 5× fallback-to-oldest-user | Real or signed identity; removal of the fallback | P0 |
| Authorization (researchers) | RED | 11 routes without auth, including anonymous PATCH | Owner checks on those routes | P0 |
| Authorization (P0-3 remediated routes) | GREEN* | 59 routes via `_resolve_researcher_profile_auth`; tests pass | *identity still spoofable | — |
| Migrations / fresh deploy | RED | version_num overflow; 3 missing tables | Fix + migration 0024 | P0 |
| Ingestion on Postgres | RED | generated `fts_vector` insert error | Model mapping fix | P0 |
| Frontend ↔ backend connectivity | RED | CORS 5173; Content-Type override | Config + one-line `fetchJson` fix | P0 (demo-blocking) |
| Hybrid retrieval (works) | YELLOW | Code + unit + PG tests pass | Seeded data with embeddings | P1 |
| Opportunity search | YELLOW | `LIKE` only; `search_opportunities` unused | Optional wiring | P2 |
| Personalization core (bound, exclusion, governance) | GREEN | Code and P0 tests | — | — |
| Calibration / quality in live ranking | YELLOW | Not passed at ranker L775 | Integration, or explicitly scope out | P1 |
| Settings semantics | YELLOW | Phase 3.6 behavioral bypasses the adaptive toggle; `feedback_learning_enabled` unused | Enforcement | P1 |
| Reset semantics | YELLOW | Recompute resurrects signals | Version/timestamp cut-off | P1 |
| Risk in ranking | YELLOW | `risk_score` never persisted | Persist or compute in ranking | P1 |
| Governance scheduling / fail-open | YELLOW | Computed only on API call; exceptions → ALLOW | Fail-closed or explicit state | P1 |
| Collaboration UI | RED | 3 wrong API paths | Path fixes | P1 |
| Docker | YELLOW | Postgres-only compose is fine | Docs for the run order; optional backend service | P2 |
| Tests | YELLOW | 1235 pass; 1 time-bomb; no migration or E2E tests | PG smoke test; data fix | P1/P2 |
| Docs | YELLOW | 61 phase docs + METHODOLOGY | Accurate "how to run" and a known-limitations section | P2 |

---

============================================================
A. WHAT IS DEFINITELY COMPLETE
============================================================

These are proven by code plus passing tests. "Complete" here means the logic, not deployment.

1. **Personalization bound ≤ 0.15** (`personalization_ranker.py` L49, L261, L969) and relevance damping (L68, L280).
2. **P0-1 exclusion safety:** excluded opportunities receive no positive adjustment, even with strong preference, adaptive or behavioral evidence (`L965-999`; `test_p0_1_*`, `test_blocker1_case_a…e` pass).
3. **P0-2 governance on the live path:** settings → governance → context → single multiplier (SUSPEND 0 / ALLOW_BOUNDED 0.5 / HOLD 0.25 / REDUCE 0.1 / ALLOW 1.0), with no double damping (`personalization_ranking_service.py` L201-222, L281, L401; ranker L978-990; `test_blocker2_*` pass).
4. **Adaptive-disabled and personalization-disabled flags** stop Phase 5.5 signal loading and zero the adjustment (`test_p0_4_adaptive_signals_disabled_flag`, `test_p0_4_personalization_disabled_flag` pass).
5. **Strict ownership on the 59 researcher routes** that use `_resolve_researcher_profile_auth` (401 without the header, 403 on mismatch; probe and `test_p0_3_*`, `test_blocker3_*` pass).
6. **Service-level ownership checks** for workspace items, submissions, documents, calendars, notifications, reminder rules and collaboration roles (`test_workspace_authorization.py` etc. pass).
7. **RRF fusion, lexical FTS repository, pgvector repository** work against real Postgres 16 + pgvector 0.8.0 (the previously skipped PG tests pass).
8. **Risk engine, deadline engine, discovery explainability, diversity, reranker, evaluation runners:** unit and evaluation suites pass.
9. **Scraper parsing / normalization / validation / dedup / change detection** for WikiCFP, OpenAlex and Crossref (380 tests pass).
10. **Frontend type-safety:** `tsc --noEmit` 0 errors; eslint 0 errors.
11. **Working tree:** no real uncommitted code changes (CRLF only).

============================================================
B. WHAT IS IMPLEMENTED BUT NOT VERIFIED
============================================================

1. End-to-end hybrid search with real embeddings. `sentence-transformers` is needed at query time, and no seeded DB exists.
2. `ml/embeddings/generate_embeddings.py` and `ml/topic_analysis/process_topics.py` runs on a real DB. They're blocked behind P0-DB-2 anyway.
3. Live scraping (network) for WikiCFP, OpenAlex and Crossref. Only fixture-based tests exist.
4. `next build` / production build of the frontend.
5. Every browser workflow. Nothing has been demo-verified, and CORS blocks all of them today.
6. Governance recomputation (`recompute_governance`) producing non-ALLOW states on real interaction data.
7. Reminder dispatch (`ReminderSchedulerService.run_scheduled_reminders`) in a real run. There's no scheduler; only the manual trigger route.
8. iCal export in a calendar client.
9. The 3 performance-threshold tests on your hardware.
10. Phase 5.6 calibration and 5.7 contextual adaptation. They work in the per-opportunity explanation endpoints, but **not in live ranking**.

============================================================
C. WHAT IS CURRENTLY BROKEN
============================================================

1. **Fresh `alembic upgrade head`**: `StringDataRightTruncation` on revision `0002_phase2_1_ingestion_hardening` (33 characters > VARCHAR(32)). Reproduced.
2. **All ORM inserts of `OpportunityModel` / `ResearchWorkModel` on a migrated Postgres**: `GeneratedAlways: cannot insert a non-DEFAULT value into column "fts_vector"`. Reproduced through `OpportunityRepository.save_batch` (inserted 0, errors 1). This breaks WikiCFP, OpenAlex and Crossref ingestion.
3. **HTTP 500 on a migrated Postgres** for `/personalized-candidates`, `/personalized-recommendations`, `/recommendation-history`, `/feedback`, `/recommendations/unified`. The tables `researcher_recommendation_feedback`, `_snapshots` and `_items` don't exist. Reproduced.
4. **Browser → API calls from `localhost:3000`** are blocked by CORS. Reproduced: preflight 400.
5. **35 frontend write calls** send `text/plain` → 422. The cause is in `fetchJson`; the backend side is reproduced.
6. **Collaboration invitation revoke/accept/decline** from the UI call nonexistent routes.
7. **`test_research_calendar_api.py::test_researcher_calendar_view_api`** fails because of a hard-coded date that has now passed (obsolete test data, not an app bug).

============================================================
D. WHAT IS MISSING
============================================================

1. Real authentication: login, verifiable token or session, and one shared `get_current_user` dependency. (`app/core` has no auth module.)
2. A migration for the three Phase 3.6/3.7 tables.
3. Any test that runs Alembic against Postgres, and any frontend or E2E test.
4. `CORS_ORIGINS` in `.env.example`, and a correct default.
5. A seed / demo-data script. There is no dataset in the repo to load for a demo.
6. A scheduled job for reminders and governance recomputation. Manual triggers only.
7. Persistence of the computed risk score or level on `opportunities` (the ranking gate reads a field nobody writes).
8. Opportunity-level hybrid search endpoint (the `HybridSearchService.search_opportunities` service exists but has no route).
9. Dockerfiles or compose services for the backend and frontend. Optional for the demo.

============================================================
E. ALL P0 BLOCKERS
============================================================

**P0-SEC-1 — Anonymous requests silently act as the oldest user**
- **Files:** `backend/app/api/v1/workspace.py::resolve_current_user` (L46-67), `submissions.py` (L56-76), `calendar.py` (L34-54), `notifications.py` (L36-62), `workspace_collaboration.py` (L61-78).
- **Bug:** with no `X-User-ID`, the code picks `select(UserModel).order_by(created_at).first()`. This is unconditional (not tied to `APP_ENV`).
- **Impact:** any anonymous caller reads and modifies the first user's workspace, submissions, documents, calendar, notifications and collaboration data (87 handlers).
- **Repro:** `GET /api/v1/calendar/default` with no headers → 200 with the oldest user's `user_id`; `GET /api/v1/workspace` → 200.
- **Expected:** 401. **Current:** 200 as another user.
- **Fix direction:** replace the five copies with one shared dependency (e.g. `app/api/deps.py::get_current_user_id`) that raises 401 when identity is missing and 401/404 when the user doesn't exist. Then update the frontend pages that rely on the fallback (see P0-FE-3) in the same change set.

**P0-SEC-2 — Unauthenticated researcher routes, including an anonymous write**
- **File:** `backend/app/api/v1/researchers.py`. Functions: `get_researcher_profile` (GET `/{id}`), **`update_researcher_profile` (PATCH `/{id}`)**, `get_researcher_publications`, `get_researcher_profile_completeness`, `get_researcher_intelligence` (with `refresh=true` it writes), `get_researcher_interests`, `get_researcher_expertise`, `get_preference_intelligence`, `list_researcher_preferences`, `get_structured_researcher_preferences`.
- **Impact:** anyone can overwrite any profile and read any researcher's email, bio, preferences and exclusions.
- **Repro:** `PATCH /api/v1/researchers/{B}` with `{"bio":"HIJACKED"}` and no headers → 200, and the change is persisted.
- **Expected:** 401/403. **Current:** 200.
- **Fix direction:** add `x_user_id` and call the existing `_resolve_researcher_profile_auth` in these 10 handlers (at minimum PATCH, the preference reads, and `refresh=true`). `POST ""` can stay open as registration. The frontend's `fetchResearcherProfile` must then send `X-User-ID`, which affects the `/researcher` bootstrap (P0-FE-3).

**P0-SEC-3 — Unauthenticated global job trigger**
- **File:** `backend/app/api/v1/notifications.py::trigger_reminders` (`POST /notifications/trigger-reminders`, L336-355).
- **Impact:** any anonymous caller can run the system-wide reminder dispatch and create notifications for everyone.
- **Repro:** anonymous POST → 200.
- **Fix direction:** require identity plus an admin role check (e.g. `UserModel.role == "ADMIN"`) or a server-side secret header. Alternatively, disable the route unless `APP_ENV == "development"`.

**P0-SEC-4 — Client-asserted identity (`X-User-ID`) is not authentication**
- **Files:** all 146 handlers that read `X-User-ID`; `researcher_profile_service.py` L146 (`hashed_password="auth_placeholder"`).
- **Impact:** knowing a UUID is enough to impersonate that user. UUIDs appear in API responses (e.g. `profile.user_id` from the currently open `GET /researchers/{id}`).
- **Repro:** `GET /researchers/{B}/personalization/settings` with `X-User-ID: <B's user_id>` → 200.
- **Fix direction (least invasive):** keep the single dependency from P0-SEC-1, but have it accept a **server-signed token** instead of a raw UUID. For example, a `POST /api/v1/auth/demo-login {email}` returns `HMAC(secret, user_id)` via stdlib `hmac`, the dependency verifies it, and routes keep receiving `user_id`. **This is a decision for you** (see H). If you run out of time, at minimum document it as a known limitation for the viva.

**P0-DB-1 — Fresh migrations cannot run**
- **Files:** `backend/alembic/versions/*.py` (19 revision IDs over 32 characters); `backend/alembic/env.py`.
- **Impact:** no new environment can be created, including the demo machine.
- **Repro:** empty Postgres + `alembic upgrade head` → `StringDataRightTruncation`, and the whole upgrade rolls back.
- **Fix direction:** **don't rename revisions**, since that would break existing DBs. Pre-create `alembic_version(version_num VARCHAR(255) PRIMARY KEY)`, either in `backend/app/db/init.sql` or in `env.py` before `context.run_migrations()`. Verified in the sandbox: with that pre-created table, all 23 migrations apply cleanly.

**P0-DB-2 — Ingestion cannot insert into Postgres (generated `fts_vector`)**
- **Files:** `backend/app/models/opportunity.py` L138-143, `backend/app/models/research_knowledge.py` L411-416 (vs migration `0007_phase2_4i_fts_gin_indexes.py`).
- **Impact:** WikiCFP, OpenAlex and Crossref pipelines insert nothing, so there's no data to demo.
- **Repro:** `OpportunityRepository.save_batch(...)` on a migrated DB → `inserted=0 errors=1 (GeneratedAlways)`.
- **Fix direction:** tell SQLAlchemy the DB owns the column, e.g. `server_default=FetchedValue(), server_onupdate=FetchedValue()` on the `mapped_column`. That's SQLite-safe because it emits no DDL. Avoid `Computed(...)`: it would emit `to_tsvector` DDL into the SQLite test schema and break ~all DB tests.

**P0-DB-3 — Three tables used by the live recommendation path have no migration**
- **Models:** `backend/app/models/researcher_feedback.py::ResearcherRecommendationFeedbackModel`, `backend/app/models/recommendation_history.py` (snapshots and items).
- **Impact:** the main demo feature (personalized recommendations) returns 500 on Postgres. So do feedback, history and unified recommendations.
- **Repro:** migrated DB → `GET /researchers/{id}/personalized-recommendations` → 500 `UndefinedTable researcher_recommendation_feedback`.
- **Fix direction:** add `0024_phase3_6_3_7_feedback_and_history.py` that creates the three tables exactly as the models define them (FKs, indexes). Then re-run the live `inspect()` drift check.

**P0-FE-1 — CORS blocks the Next.js frontend**
- **File:** `backend/app/core/config.py` L12 (`cors_origins` = 5173 only); `.env.example` (no `CORS_ORIGINS`).
- **Impact:** every browser request from `http://localhost:3000` fails.
- **Repro:** preflight from Origin 3000 → `400 Disallowed CORS origin`.
- **Fix direction:** default to `["http://localhost:3000","http://127.0.0.1:3000"]` (optionally keep 5173) and add `CORS_ORIGINS` to `.env.example`.

**P0-FE-2 — `fetchJson` drops `Content-Type` on 35 write calls**
- **File:** `frontend/services/api.ts::fetchJson` (L169-176).
- **Bug:** the trailing `...init` overwrites the merged `headers` object.
- **Impact:** preference create/update, interactions, feedback, settings, workspace, submission, calendar, notification and collaboration writes all return 422 in the browser.
- **Expected:** 201/200. **Current:** 422 (backend reproduced with `text/plain`).
- **Fix direction:** spread `...init` first, then set `headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }`.

**P0-FE-3 — Frontend pages rely on the insecure fallback identity** (must ship together with P0-SEC-1/2)
- **Files:** `frontend/app/workspace/page.tsx` L85-86, `app/workspace/[id]/page.tsx` L109, `app/workspace/[id]/submission/page.tsx` L185, `app/calendar/page.tsx` L86, `app/notifications/page.tsx` L45, `app/researcher/page.tsx` L182 (anonymous profile bootstrap).
- **Impact:** once the fallback is removed, these pages get 401.
- **Fix direction:** keep one "current identity" helper in the frontend (stored alongside `researchconnect_active_profile_id`) and pass `userId` (or the token from P0-SEC-4) into every `api.ts` call.

============================================================
F. ALL P1 ISSUES
============================================================

**P1-1 Reset isn't durable** — `services/personalization_transparency_service.py::reset_personalization` (L173-265), `services/adaptive_signal_service.py::recompute_adaptive_signals` (L87-98).
After a reset, `POST /adaptive-signals/recompute` rebuilds signals from *all* pre-reset interactions, because `personalization_state_version` isn't consulted. Phase 3.6 feedback and governance evaluations aren't reset either.
Expected: cold start after reset. Fix direction: store a `reset_at` (or reuse `updated_at` of the settings row at reset) and filter interactions/feedback with `created_at > reset_at` in recompute and in `get_behavioral_profile`.

**P1-2 Calibration (5.6) and contextual adaptation (5.7) aren't in live ranking; explanations diverge** — `ranking/personalization_ranker.py` L775-781 (no `calibrations=` / `contextual_adaptations=`); `api/v1/researchers.py::get_opportunity_personalization` / `batch_opportunity_personalization` (L1622-1680) pass them and ignore `adaptive_signals_enabled`.
Fix direction: either load and pass them in `PersonalizationRankingService` (gated by `adaptive_signals_enabled`), or state clearly that they're explanation-only. In both cases, make the per-opportunity endpoints respect the settings.

**P1-3 The adaptive toggle doesn't stop Phase 3.6 behavioral influence** — `personalization_ranking_service.py` L250-256, L275; `personalization_ranker.py::evaluate_personalization_signals` L588-632.
Fix direction: pass `behavioral_signals=()` when `adaptive_signals_enabled` (or `feedback_learning_enabled`) is off. Keep `suppressed_opportunity_ids`, since those express explicit negative intent.

**P1-4 `feedback_learning_enabled` is never enforced** — stored in `ResearcherPersonalizationSettingsModel` and only read inside `personalization_transparency_service.py`.
Fix direction: check it in `researcher_interaction_service.record_interaction` / `feedback_service.record_feedback` (store the event but mark it not-for-learning), or in the ranking service as in P1-3.

**P1-5 Governance and settings lookups fail open** — `personalization_ranking_service.py` L186-189, L205-213.
If the lookup raises, the result is ALLOW with personalization on. Fix direction: log it, and on exception fall back to `personalization_enabled=False` / `HOLD`.

**P1-6 Excluded opportunities aren't demoted** — ranker L996-999 (`final_score = base_score`).
An excluded item still ranks on relevance. Fix direction: apply a demotion like suppression (e.g. `base − 0.50`) or filter it out. This is a product decision; P0-1 as specified is already satisfied.

**P1-7 The risk gate in personalization is mostly inert** — ranker L957-961 reads `risk_level` (not a model attribute) and `risk_score` (never written; default 0.00, `models/opportunity.py` L102).
Fix direction: compute risk once per candidate in `PersonalizationRankingService` (the risk engine is already used by the matching route), or persist `risk_score` during ingestion or enrichment.

**P1-8 Governance is only computed on read calls, and GETs write** — `personalization_governance_service.py::get_health_response/get_drift_response` call `recompute_governance` (L335, L371); `calendar.py GET /default` creates a calendar.
Fix direction: acceptable for the demo; document it, or trigger recompute after interactions / adaptive recompute.

**P1-9 Wrong frontend API paths** — `frontend/services/api.ts`: `revokeWorkspaceInvitation` (L1955), `acceptWorkspaceInvitation` (L1927), `declineWorkspaceInvitation` (L1941), `projectOpportunityToCalendar` (L1624).
Fix direction: point them at `DELETE /api/v1/workspaces/{id}/invitations/{inv}`, `POST /api/v1/workspaces/invitations/{token}/accept|decline`, and `POST /api/v1/calendar/{id}/opportunities/{opp}/project`.

**P1-10 No demo data path** — there's no seed script, and embeddings need `sentence-transformers` plus a model download.
Fix direction: after the P0-DB fixes, run one real ingestion (WikiCFP plus a small OpenAlex topic), then topics, then embeddings. Keep the commands in a `scripts/` runbook, or write a small seed script that uses the existing repositories.

**P1-11 No Postgres regression test** — nothing catches P0-DB-1/2/3.
Fix direction: add one `postgres_integration` test that runs `alembic upgrade head` and inserts an opportunity, skipped when PG is unreachable. The `postgres_integration` mark is also unregistered in `pytest.ini`.

**P1-12 `resolve_user_id` accepts unknown IDs** — `services/workspace_service.py` L112-127 returns arbitrary UUIDs.
Fix direction: raise if neither a profile nor a user matches. This folds naturally into the P0-SEC-1 dependency.

============================================================
G. ALL P2 ISSUES
============================================================

1. `HybridSearchService.search_opportunities` has no route; `/api/opportunities?search=` uses `LIKE` (`services/opportunity_service.py` L61-68).
2. The duplicate `/workspace/...` and `/workspaces/...` route aliases (40 handlers) and every router mounted under both `/api` and `/api/v1` double the attack surface and the docs.
3. Obsolete test data: `tests/test_research_calendar_api.py` L140 hard-codes `2026-09-22`. It should use `now()+timedelta`. (Record it; don't "fix to pass" during the security task.)
4. Performance-threshold tests are machine-sensitive (`test_transparency_performance_and_query_count`, `test_performance_benchmarks_zero_n_plus_one`, `test_batch_performance_zero_queries`).
5. Five `react-hooks/exhaustive-deps` lint warnings.
6. `.env.example` has no `CORS_ORIGINS`, `APP_ENV` gating or auth secret. There's no backend/frontend service in compose and no Dockerfiles.
7. Unused frontend helpers (`fetchOpportunityRiskExplanation`/`…Deadlines`) and 49 backend routes with no UI (researcher-scoped notification/reminder aliases, collaboration tasks/activity).
8. `README.md` and `docs/METHODOLOGY.md` should state the real architecture (two pipelines, SQL-based candidate generation) and the known limitations.

============================================================
H. EXACT FIRST TASK
============================================================

**Task: "P0-SEC-1/2/3 — one identity dependency, no anonymous access" (backend only, with regression tests).**

1. Create one shared dependency, e.g. `backend/app/api/deps.py::get_current_user_id(x_user_id = Header(alias="X-User-ID"), db)`. It returns `user_id`, raises **401** when the header is missing and **401** when the UUID doesn't resolve to a user or profile, and **never falls back**.
2. Delete the five local `resolve_current_user` copies (workspace, submissions, calendar, notifications, workspace_collaboration) and use the dependency.
3. Put `_resolve_researcher_profile_auth` on the 10 open researcher routes listed in P0-SEC-2. Leave `POST /researchers` open.
4. Protect `POST /notifications/trigger-reminders` (admin role or dev-only).
5. Add `backend/tests/test_p0_security_regression.py` covering the probe matrix in §8.2: anonymous → 401, cross-user → 403, anonymous PATCH → 401, anonymous trigger → 401/403. Keep `test_p0_phase5.py`, `test_workspace_*` and `test_research_*_api.py` green. Some existing API tests may rely on the fallback. Update only their request headers, and list every one you change.

Make these two decisions before starting:

- **(a)** Should the dependency accept a signed token now (P0-SEC-4), or strict `X-User-ID` now and a token later? I recommend strict `X-User-ID` first: the dependency becomes the single place to swap in a token later.
- **(b)** Do P0-FE-3 and P0-FE-2 as the **immediately following** task on the same day. Otherwise workspace, calendar and notifications stop working in the UI.

After this, the recommended order is: P0-DB-1 → P0-DB-3 → P0-DB-2 (deployment P0s, verified with the live Postgres smoke test) → P0-FE-1/2/3 → P0 re-audit → P1.

**Why the DB and FE P0s sit inside Day 1–2, not Day 3.** Your plan puts deployment on Day 3. But P0-DB-1/2/3 and P0-FE-1/2 mean nothing can be verified end to end in a browser. Without them, the Day 2 "API/frontend integration" work can't be tested. They're small, isolated changes (a config line, a migration, two model columns and one TS function), so they fit on Day 1 after security.

============================================================
I. EXACT FILES LIKELY TO BE TOUCHED
============================================================

**P0 security**
- `backend/app/api/deps.py` (new) or `backend/app/core/auth.py` (new)
- `backend/app/api/v1/workspace.py`, `submissions.py`, `calendar.py`, `notifications.py`, `workspace_collaboration.py`, `researchers.py`
- `backend/app/services/workspace_service.py` (`resolve_user_id`, P1-12)
- `backend/tests/test_p0_security_regression.py` (new); header updates in existing API tests if they rely on the fallback

**P0 DB**
- `backend/app/db/init.sql` or `backend/alembic/env.py` (version table)
- `backend/alembic/versions/0024_*.py` (new: 3 tables)
- `backend/app/models/opportunity.py`, `backend/app/models/research_knowledge.py` (`fts_vector` mapping)

**P0 FE**
- `backend/app/core/config.py`, `.env.example` (CORS)
- `frontend/services/api.ts` (`fetchJson`, then P1-9 paths)
- `frontend/app/workspace/page.tsx`, `app/workspace/[id]/page.tsx`, `app/workspace/[id]/submission/page.tsx`, `app/calendar/page.tsx`, `app/notifications/page.tsx`, `app/settings/notifications/page.tsx`, `app/researcher/page.tsx`, `app/researcher/preferences/page.tsx`

**P1**
- `backend/app/services/personalization_ranking_service.py`, `backend/app/services/personalization_transparency_service.py`, `backend/app/services/adaptive_signal_service.py`, `backend/app/services/feedback_service.py`, `backend/app/services/researcher_interaction_service.py`, `backend/app/api/v1/researchers.py` (per-opportunity personalization endpoints)
- `backend/app/ranking/personalization_ranker.py` (small, local edits only: exclusion demotion, risk inputs)
- `backend/pytest.ini` (register the `postgres_integration` mark)

============================================================
J. THINGS WE MUST NOT TOUCH
============================================================

Stable, tested, and not implicated in any P0:

- `backend/app/personalization/{interpreter,scorer,adaptive_engine,calibration_engine,quality_engine,governance_engine,transparency_engine,models}.py`: pure engines, heavily tested.
- `backend/app/ranking/personalization_ranker.py`: **the 0.15 bound, damping, exclusion and governance blocks (L965-1001).** These are what the P0-1/P0-2 fixes made correct. P1 changes must be additive and local.
- `backend/app/ranking/{hybrid_ranker,features,signals,diversity,reranker,venue_intelligence,feedback_engine,recommendation_explainer,recommendation_evaluation_engine}.py`, `ranking/risk/*`, `ranking/deadline/*`
- `backend/app/search/rrf.py`, `search/query_intelligence.py`, `repositories/lexical_repository.py`, `repositories/vector_repository.py`
- `backend/app/explainability/result_explainer.py`, `backend/app/evaluation/*`, `artifacts/evaluation/*`
- **Existing migrations `0001`–`0023`.** Don't edit or rename them; add `0024` and handle the version table outside them.
- `scrapers/` parsers, normalizers, validators, dedup and change detection
- `ml/`
- Service-layer ownership logic in `workspace_service`, `research_submission_*`, `research_calendar_service`, `notification_service`, `workspace_collaboration_service`, `workspace_authorization_service`: correct once identity is trustworthy.
- `backend/tests/test_p0_phase5.py`, `test_phase5_integration.py`: keep them as the regression guard for P0-1/2/3.
- Frontend components under `components/discovery`, `components/personalization` and `components/researcher`. Only `services/api.ts` and the page-level identity wiring need to change.

============================================================
K. FINAL PROJECT READINESS
============================================================

- **Security readiness:** **RED.** Anonymous writes (PATCH profile), fallback-to-oldest-user on 87 handlers, an anonymous global job trigger, and spoofable identity. The Phase 5 researcher routes that were fixed in `7bad228` are correctly enforced.
- **Functional readiness:** **RED.** On a real Postgres the core recommendation endpoints return 500 and ingestion inserts nothing. The logic itself is sound on SQLite.
- **ML/recommendation readiness:** **YELLOW.** Retrieval, RRF, ranking, risk and deadline engines are implemented and tested; there's no embedded dataset to demonstrate them.
- **Personalization readiness:** **YELLOW.** Bound, exclusion and governance are correct. Calibration and quality aren't in live ranking; reset and toggle semantics have gaps (P1-1…4).
- **Governance readiness:** **GREEN for the live multiplier path, YELLOW overall.** It fails open and is only computed on read calls.
- **Frontend readiness:** **RED.** CORS and the `fetchJson` Content-Type bug block browser use; 4 feature areas send no identity; 3 wrong collaboration paths. It type-checks cleanly.
- **Backend readiness:** **YELLOW/RED.** 1235 tests pass, but the P0 security and DB issues above remain.
- **Database readiness:** **RED.** A fresh migration fails; 3 tables are unmigrated; the generated-column mapping breaks inserts.
- **Deployment readiness:** **RED.** Blocked by the DB P0s; there's no seed path, no backend/frontend containers, and no `.env`. Docker Desktop being stopped is a local issue, separate from these.
- **Testing readiness:** **YELLOW.** A large, mostly green suite, but SQLite-only: nothing tests migrations, Postgres, the frontend or E2E. One test is obsolete by date; 3 timing tests are machine-sensitive.
- **Demo readiness:** **RED.** No browser workflow completes today.
- **Documentation readiness:** **YELLOW.** 61 phase docs and a methodology doc exist, but they describe a single hybrid pipeline and don't cover the real run order or the known limitations.
