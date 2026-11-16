# ResearchConnect AI Project Guide

## What This Project Does

ResearchConnect AI helps students and early-career researchers find where to publish and what to read. It
collects calls for papers (conferences, journals, workshops, special issues) and scholarly papers, ranks them for a
person, and explains every result: why a paper matches, why a venue fits, how risky a venue looks, and how much time
is left before each deadline in the reader's own time zone. It also gives researchers a workspace to track
submissions, a calendar with reminders, a reading list, and a place where faculty post projects and positions that
students can apply to.

The core idea is that nothing is a black box. Every score can be broken down into its parts, a venue is called
risky only when there is enough evidence, and a date the system cannot read with confidence is shown as *unknown*,
*invalid* or *ambiguous* instead of being guessed.

## How the Parts Fit Together

1. **Collect.** Scrapers in `scrapers/` fetch calls for papers from WikiCFP and paper metadata from OpenAlex and
   Crossref, clean them, remove duplicates and store them in PostgreSQL.
2. **Understand.** `ml/` tags each paper and call with topics from a fixed taxonomy and turns its title and abstract
   into a 384-number embedding, so meaning can be compared, not only words.
3. **Search and rank.** When someone searches, the backend runs two searches at once, a keyword search (PostgreSQL
   full text) and a meaning search (pgvector), merges them with Reciprocal Rank Fusion, then scores the merged list
   with a weighted, explainable formula.
4. **Assess.** For each call, the backend works out venue risk from evidence (indexing, publisher, wording,
   suspicious patterns) and reads its deadlines, including Anywhere on Earth dates and time-zone changes.
5. **Personalize.** Signed-in users get recommendations shaped by their stated preferences and by what they save,
   dismiss or open. The personal part is capped, so relevance always dominates, and it switches off for risky or
   expired calls.
6. **Serve.** FastAPI in `backend/app/` returns all of this as JSON. The Next.js app in `frontend/` shows it in the
   browser, with a bearer token for signed-in requests.
7. **Run in the background.** An optional scheduler refreshes papers and calls, expires old ones, sends reminders
   and emails, with a lock so two backend copies never run the same job twice.

Docker Compose starts the database, runs the migrations, then starts the API and the web app, in that order.

## File Guide

### Project Root

- `README.md`: overview, features, architecture, setup commands, configuration, testing, deployment and known
  limitations.
- `.env.example`: sample settings for Docker Compose. The two secrets (`POSTGRES_PASSWORD`, `AUTH_SECRET_KEY`) are
  empty on purpose; you generate your own.
- `docker-compose.yml`: the full local stack: PostgreSQL with pgvector, a one-off migration step, the backend and
  the frontend. Containers run as non-root users with reduced privileges, and ports are bound to localhost only.
- `.gitignore`: keeps `.env` files, virtual environments, `node_modules`, build output and caches out of Git.
- `LICENSE`: MIT licence.
- `pyrightconfig.json`: Python type-checker settings for editors.
- `.github/workflows/ci.yml`: GitHub Actions. On every push it migrates a fresh database and runs the backend and
  scraper tests, then type-checks, lints, tests and builds the frontend and checks its bundle size.

### Backend (`backend/`)

- `Dockerfile`: builds the API image. It installs the CPU-only PyTorch, downloads the embedding model at build time
  and runs as a non-root user.
- `requirements.txt`: exact Python package versions.
- `alembic.ini`, `alembic/`: database migrations. `alembic/versions/` holds 35 numbered migrations, from the
  initial schema to the latest; `alembic upgrade head` applies any that are missing.
- `pytest.ini`: test settings. Wall-clock performance budgets carry the `perf` marker and are left out of the
  normal run, because their timing depends on the machine.
- `.env.example`: settings for running the backend directly on your computer.
- `scripts/seed_demo_data.py`: creates three demo accounts (student, faculty, admin), twelve calls for papers,
  preferences and research postings. Safe to run again; it updates rather than duplicates.
- `scripts/seed_community.py`: adds sixty fictional researchers so the platform looks in use.
- `scripts/wait_for_db.py`: waits until PostgreSQL accepts connections (used at container start).
- `scripts/report_unsafe_urls.py`: lists stored links that are not safe to show.

**Application (`backend/app/`)**

- `main.py`: creates the FastAPI app, adds security headers, CORS, rate limiting and request IDs, and connects
  every route.
- `api/`: the HTTP endpoints.
  - `health.py`: `/api/health` and `/api/health/ready`, which also reports whether the database schema matches the
    code.
  - `opportunities.py`: calls for papers: list, filter and read one.
  - `deps.py`: shared request helpers, mainly "who is the signed-in user".
  - `v1/auth.py`: register, sign in, sign out, email confirmation.
  - `v1/discovery.py`: literature search, similar papers, venue matching for a paper, recommendations and their
    explanations.
  - `v1/researchers.py`: researcher profile, interests and preferences.
  - `v1/workspace.py`, `v1/workspace_collaboration.py`: saved calls, statuses, notes, shared workspaces and
    invitations.
  - `v1/submissions.py`: submissions and their documents and history.
  - `v1/calendar.py`: research calendar and the iCal feed.
  - `v1/notifications.py`: in-app notifications and notification settings.
  - `v1/postings.py`: faculty research postings and student applications.
  - `v1/reading_list.py`: saved papers with To read / Reading / Done status.
  - `v1/admin.py`: account management and platform health for administrators.
- `core/`: settings and protection.
  - `config.py`: every setting with its default; production mode refuses unsafe values at startup.
  - `security.py`: password hashing (bcrypt), token signing (JWT) and token revocation.
  - `middleware.py`: security headers and request IDs.
  - `rate_limiter.py`: limits on sign-in and other sensitive requests.
  - `url_safety.py`: refuses links that could be used to attack users.
  - `cache.py`, `logging_config.py`: small in-memory cache and structured logs.
- `db/`: database connection (`session.py`), the pgvector and full-text column types (`types.py`), the schema
  version check (`schema_status.py`) and `init.sql`, which enables the `vector` extension.
- `models/`: the database tables (about thirty files), grouped by area: users and profiles, calls and sources,
  papers with authors, institutions and topics (`research_knowledge.py`), workspace and submissions, calendar and
  notifications, postings and applications, and the personalization records.
- `schemas/`: what each request and response looks like, validated with Pydantic.
- `repositories/`: the two search queries: `lexical_repository.py` (keyword search) and `vector_repository.py`
  (meaning search).
- `search/`: `query_intelligence.py` expands academic acronyms such as *NLP* before searching, and `rrf.py` merges
  the two result lists.
- `ranking/`: scoring.
  - `hybrid_ranker.py`, `features.py`, `signals.py`: the weighted scoring formula and its inputs.
  - `recommendation_explainer.py`, `diagnostics.py`: exact per-signal explanations.
  - `personalization_ranker.py`, `feedback_engine.py`: the capped personal boost and learning from feedback.
  - `diversity.py`, `reranker.py`: optional diversity re-ranking and cross-encoder reranking (off by default).
  - `risk/`: venue risk: evidence extraction, pattern and graph checks, publisher and indexing registries, scoring
    with diminishing returns, and plain-language explanations.
  - `deadline/`: deadline reading: date and time-zone normalization, Anywhere on Earth, multiple milestones,
    extensions, conflicting sources and urgency.
- `personalization/`: preference interpretation, adaptive signals, calibration, quality checks, the governance gate
  that can scale personalization down or suspend it, transparency, and peer and supervisor matching.
- `services/`: the business logic behind each route (about forty files): hybrid search, similar research, venue
  matching, recommendations, workspace, submissions, calendar, reminders, notifications, email sending (SMTP or a
  mock), postings and applications, reading list, and peer and supervisor discovery.
- `explainability/result_explainer.py`: turns search scores into "Why this result?" explanations.
- `scheduler/`: the background jobs, their database locks, timeouts and metrics; it starts only when
  `SCHEDULER_ENABLED=true`.
- `evaluation/`: offline benchmark datasets and runners for retrieval, venue risk and deadlines; results are saved
  in `artifacts/evaluation/`.

**Tests (`backend/tests/`)**: about 125 test files covering every area above: API behaviour, security and
permissions, ranking maths, risk safety rules, deadline edge cases, personalization limits, migrations and
production configuration. The normal run has about 2,800 tests.

### Machine Learning (`ml/`)

- `embeddings/service.py`: loads the `all-MiniLM-L6-v2` model and turns text into embeddings.
- `embeddings/text_builder.py`: chooses which text of a paper or call to embed.
- `embeddings/generate_embeddings.py`: command that embeds everything not yet embedded.
- `embeddings/hash_utils.py`: a content fingerprint, so unchanged items are not embedded again.
- `embeddings/config.py`: model name, size and batch settings.
- `topic_analysis/taxonomy.py`: the topic tree (228 topics under nine disciplines).
- `topic_analysis/extraction.py`, `normalization.py`, `assignment.py`: find and clean topic terms and attach topics
  with a confidence.
- `topic_analysis/process_topics.py`: command that tags every paper and call.

### Data Collection (`scrapers/`)

- `pipelines/collect_opportunities.py`: collects calls for papers from WikiCFP for a topic.
- `pipelines/collect_openalex.py`: bulk-loads papers from OpenAlex (resumable with a cursor).
- `pipelines/collect_crossref.py`: fills in metadata from Crossref by DOI.
- `pipelines/refresh_research.py`: the scheduled refresh of new and rising papers.
- `pipelines/load_lock.py`: stops two loads from running at once.
- `sources/`, `parsers/`: WikiCFP list and detail page parsing, and the OpenAlex and Crossref source adapters.
- `openalex/`, `crossref/`: API clients, response models, normalizers and validators.
- `normalizers/`, `validators/`: clean and check a call for papers before it is stored.
- `deduplication/`, `change_detection/`, `freshness/`, `expiration/`: find duplicates, detect changed calls, track
  when each was last seen and expire old ones.
- `persistence/`: write calls and papers to the database.
- `http_client.py`: polite HTTP with retries, timeouts and a contact address.
- `tests/`: about 480 scraper tests, using saved HTML and JSON fixtures, so no network is needed.

### Frontend (`frontend/`)

- `package.json`, `package-lock.json`: scripts and exact package versions.
- `next.config.ts`: Next.js settings: the API address compiled into the bundle (validated), security headers and
  shorter CSS class names.
- `middleware.ts`: adds a fresh Content-Security-Policy with a nonce to every page.
- `Dockerfile`: builds a small standalone Next.js server image.
- `tsconfig.json`, `eslint.config.mjs`, `tailwind.config.ts`, `postcss.config.mjs`: TypeScript, lint and CSS
  settings.
- `vitest.config.ts`, `vitest.setup.ts`: unit and component test settings.
- `playwright.config.ts`: browser test settings.
- `scripts/check-bundle-budget.mjs`: fails the build check if page JavaScript grows past its budget.
- `app/`: the pages (Next.js App Router). Main ones:
  - `/` literature search; `/similar` similar papers; `/opportunities` find venues for a paper.
  - `/browse` and `/calls/[id]` calls for papers and one call with its risk and deadline details.
  - `/dashboard` home; `/recommendations` personal recommendations.
  - `/workspace` and `/workspace/[id]` saved calls; `/workspace/[id]/submission` and `/submissions` submissions.
  - `/calendar`, `/notifications`, `/reading-list`.
  - `/postings` and `/postings/[id]` research postings; `/postings/new` and `/postings/[id]/edit` for faculty;
    `/postings/applications` and `/postings/applicants` for students and faculty.
  - `/peers`, `/supervisors` people discovery; `/researcher` and `/researcher/preferences` profile.
  - `/settings`, `/settings/notifications`; `/login`, `/register`, `/verify-email`.
  - `/admin`, `/admin/users`, `/admin/research-data` for administrators.
- `components/`: the building blocks, by area.
  - `ui/`: the design system: buttons, fields, dialogs, menus, tabs, toasts, pagination, theme switcher.
  - `shell/`: header, navigation, global search, account menu and notification bell.
  - `research/`: paper and call cards, deadline countdown and milestones, risk indicator and details, match and fit
    scores, evidence panels.
  - `discovery/`, `recommendations/`, `workspace/`, `postings/`, `dashboard/`, `calendar/`, `notifications/`,
    `reading-list/`, `people/`, `profile/`, `preferences/`, `settings/`, `admin/`, `auth/`: the parts of each page.
- `services/api/`: one file per backend area, each sending authenticated requests (`client.ts` handles the token,
  errors and expired sessions); `services/auth.ts` handles signing in and out.
- `hooks/`: shared React hooks (loading data, unread notification count, the chosen paper).
- `utils/`: small helpers: dates and time zones, risk labels, search state, safe links, the CSP builder, theme.
- `styles/`: design tokens, base and global styles.
- `types/`: TypeScript descriptions of the API's data.
- `tests/`: about 60 Vitest files (around 800 tests) for components and helpers.
- `e2e/`: Playwright browser journeys, accessibility scans with axe, performance checks and visual comparisons;
  `visual.spec.ts-snapshots/` holds the reference screenshots also used in the README.

### End-to-End and Demonstration (`e2e/`, `demo/`)

- `e2e/run_e2e.py`: builds the production images, starts an isolated stack on its own ports and runs the API,
  browser, scheduler and restart suites against it.
- `e2e/api/`: API workflow tests numbered in order (demo seed, database, authentication, discovery, workspace,
  postings, applications, peers, notifications, authorization, scheduler, persistence after restart).
- `e2e/compose.e2e.yml`, `compose.e2e-scheduler.yml`, `mailsink.py`: the test stack and a fake mail server.
- `demo/demo.py`, `demo/compose.demo.yml`: a second, separate stack (ports 3400 and 8400, with a mail sink) for
  demonstrations next to a development stack. `demo/README.md` explains its accounts and limits.

### Evaluation Results (`artifacts/evaluation/`)

JSON results of the offline benchmarks: retrieval and reranking (phases 2.4M to 2.5G), venue risk (2.6G) and
deadlines (2.7G). The README and methodology quote them.

### Supporting Documents (`docs/`)

- `README.md`: index of every document.
- `METHODOLOGY.md`: research approach, design rationale and limitations.
- `PROJECT_GUIDE.md`: this file.
- `architecture/`: one document per development phase (data collection, search, ranking, risk, deadlines,
  personalization, workspace, collaboration, email, scheduler, production configuration, database startup), plus
  `project-roadmap.md` and the end-to-end verification report.
- `database/postgres-pgvector.md`: schema, migrations, search indexes and backups.
- `scraping/architecture.md`, `research-data/openalex.md`: ingestion pipelines and bulk loading.
- `evaluation/academic-relevance-annotation-guidelines.md`: how to collect relevance judgements.
- `design/DESIGN_SYSTEM.md`, `FRONTEND_REDESIGN_PLAN.md`, `MANUAL_VERIFICATION.md`: interface design, the redesign
  plan and manual checks; `design/audit/` holds the redesign's review evidence.

## Libraries in Simple Terms

### Python Backend

- **FastAPI**: receives HTTP requests and returns JSON responses; also validates input automatically.
- **Uvicorn**: the web server that runs FastAPI.
- **Pydantic / pydantic-settings**: check request data and read settings from environment variables.
- **SQLAlchemy**: maps Python classes to database tables and builds queries.
- **Alembic**: versioned database migrations.
- **psycopg**: the PostgreSQL driver.
- **pgvector (Python)**: lets SQLAlchemy store and compare embedding vectors.
- **sentence-transformers** (with **PyTorch**): the model that turns text into embeddings.
- **bcrypt**: password hashing.
- **PyJWT**: signs and checks sign-in tokens.
- **requests / httpx**: HTTP clients for the scrapers and tests.
- **Beautiful Soup**: reads WikiCFP's HTML pages.
- **python-dotenv**: loads settings from `.env` files.
- **pytest**: runs the tests.

### Frontend

- **Next.js**: the React framework: pages, routing, server rendering and the production build.
- **React / React DOM**: build the interactive interface.
- **TypeScript**: catches many mistakes before the code runs.
- **Tailwind CSS / PostCSS / Autoprefixer**: styling, alongside CSS Modules and design tokens.
- **Lucide React**: icons.
- **Vitest / Testing Library / jsdom**: component and unit tests without a real browser.
- **Playwright**: real-browser tests and screenshots.
- **axe-core** (through Playwright): automatic accessibility checks.
- **ESLint**: code style and common-bug checks.

### Database and Infrastructure

- **PostgreSQL 16**: the database, including full-text search.
- **pgvector 0.8**: vector columns and HNSW indexes for meaning search.
- **Docker / Docker Compose**: run every part the same way on any machine.
- **GitHub Actions**: runs the checks on every push.
- **Vercel** and **Railway**: host the public showcase (frontend, and backend with database).

## Run It Locally on Windows

You need Docker Desktop running. From the project root, in PowerShell:

1. First time only: `copy .env.example .env`, then set `POSTGRES_PASSWORD` and `AUTH_SECRET_KEY` in `.env`.
   Generate each value with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Start everything: `docker compose up --build -d --wait`. The first build takes several minutes.
3. Check it: `curl http://localhost:8000/api/health/ready` should report `"schema":"current"`.
4. Optional demo data: `docker compose exec backend python -m scripts.seed_demo_data --password "<your password>"`.
5. Open `http://localhost:3000`. The API is at `http://localhost:8000`.

Stop with `docker compose stop` and start again with `docker compose start`; both keep the data. Never run
`docker compose down -v`, which deletes the database.

Demo accounts (after step 4): `demo.student@researchconnect.test`, `demo.faculty@researchconnect.test` and
`demo.admin@researchconnect.test`, all with the password you chose. The demo seed adds no papers; the README's
"Loading research papers" section loads them from OpenAlex. No paid API key is needed. Running the backend and
frontend directly on your computer, for fast reloads, is described in the README's "Local development" section.

The live showcase is at https://research-connect-ai-abcd-bcd6.vercel.app (frontend on Vercel, backend and database
on Railway).

## What Is Demonstrated, and What Is Not

The project demonstrates hybrid literature search with explanations, similar papers, venue matching for a paper,
calls for papers with evidence-based venue risk and time-zone-correct deadlines, governed personal recommendations,
a research workspace with submissions, calendar, reminders and collaboration, faculty postings with applications,
peer and supervisor discovery, a reading list, administration, and email delivery through SMTP. The latest checked
status was about 2,800 passing backend tests, 476 scraper tests and about 800 frontend tests in CI, plus the
end-to-end, accessibility and visual suites run locally.

It is a working research prototype, not a commercial service. The evaluation is offline and uses fixtures written
by the team; there has been no user study. WikiCFP is the only live source of calls. Embeddings must be generated
before meaning search works. The platform tracks documents as records but does not store files. There is no
password recovery. Email needs a real SMTP server, and the scheduler is off by default. The public showcase holds
20,000 of the roughly 58,000 papers because its database runs on a 0.5 GB free tier; the full corpus runs locally.
The README's "Known limitations" section lists every point in detail.
