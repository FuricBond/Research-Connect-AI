# ResearchConnect AI

**ResearchConnect AI** is an intelligent full-stack platform designed to help students, researchers, and faculty discover, organize, and match with academic and research opportunities — including peer-reviewed conferences, academic journals, calls for papers (CFPs), workshops, research assistantships, and grants.

The project is built as a clean, maintainable monorepo for a collaborative final-year project team. It deliberately avoids unnecessary distributed systems, microservices, and MLOps overhead (no Kubernetes, Kafka, Airflow, or MLflow) in favor of a robust, readable, and thoroughly tested architecture.

---

## 🏛️ Architecture Overview

```text
┌──────────────────────────────────────────────────────────┐
│                 Next.js 15+ App Router                   │
│              (React 19 + TypeScript Frontend)            │
│         [SSR + Client Components + CSS Design Tokens]    │
└────────────────────────────┬─────────────────────────────┘
                             │ REST / JSON (FastAPI v1)
                             ▼
┌──────────────────────────────────────────────────────────┐
│                   FastAPI / Python                       │
│                   (Backend Service)                      │
│                                                          │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │  API Routes │ │ Ranking &    │ │  Deadline          │ │
│  │  (v1/)      │ │ Personalize  │ │  Intelligence      │ │
│  └──────┬──────┘ └──────┬───────┘ └────────┬───────────┘ │
│         │               │                  │             │
│         └───────────────┴──────────────────┘             │
│                         ▼                                │
│             SQLAlchemy 2.0 ORM + Alembic                 │
│             Pydantic v2 Schemas & Validation             │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│              PostgreSQL 16 + pgvector Extension          │
│         (Relational Data + Semantic Vectors)             │
└──────────────────────────────────────────────────────────┘
```

### Ranking & Intelligence Pipeline

```text
Raw Opportunity Data
        │
        ▼
[Evidence Extraction]  ─── deadline/extractors.py
        │                    risk/extractors.py
        ▼
[Normalization]        ─── deadline/normalizers.py
        │                    ranking/signals.py
        ▼
[Intelligence Engine]  ─── deadline/intelligence.py
        │                    risk/scoring.py, engine.py
        ▼
[Conflict/Revision]    ─── deadline/resolvers.py
        │                    risk/graph.py (AcademicTrustGraph)
        ▼
[Personalization]      ─── personalization/scorer.py
        │                    personalization/interpreter.py
        │                    services/personalization_ranking_service.py
        ▼
[Explainability]       ─── deadline/explainability.py
        │                    risk/explainability.py
        │                    personalization/transparency_engine.py
        │                    services/personalization_explanation_service.py
        ▼
[API + Frontend]       ─── api/v1/discovery.py, api/v1/researchers.py
                             Next.js App Router (app/opportunities, app/researcher)
```

The entire intelligence and ranking pipeline is **deterministic, in-memory, and zero-network** at request time — no LLM calls, no external API requests, and no database writes during ranking evaluation.

---

## 🛠️ Technology Stack

| Layer | Technology | Details |
|---|---|---|
| **Frontend** | Next.js 15.3+, React 19, TypeScript 5.7+ | Next.js App Router, SSR + Client Components, Vanilla CSS design tokens, Lucide React icons |
| **Backend** | Python 3.11+, FastAPI, Pydantic v2 | Versioned REST API (`/api/v1`), SQLAlchemy 2.0 ORM, Alembic migrations (0001–0023) |
| **Database** | PostgreSQL 16 + `pgvector` extension | Relational storage, HNSW vector indexes (cosine similarity), GIN full-text search indexes, Alembic migrations 0001–0028 |
| **Embeddings** | `sentence-transformers` · `all-MiniLM-L6-v2` | 384-dimensional dense semantic vectors with content-hash deduplication |
| **Scraping** | `requests`, `BeautifulSoup4` | Production WikiCFP connector, change detection, and data freshness pipelines |
| **IR / Evaluation** | `scikit-learn`, custom RRF & IR Metrics | P@K, R@K, MRR, NDCG, Kendall-τ rank correlation, HHI concentration, 16-scenario benchmark suite |
| **Personalization Engine** | Custom deterministic engine | Adaptive signals, calibration, governance, quality assurance, and transparency controls |
| **Containerization** | Docker Compose | Full stack: PostgreSQL 16 + `pgvector`, FastAPI backend and Next.js frontend images, one-shot Alembic migration |
| **Testing** | `pytest` | 95 test modules, 1,402 collected tests — zero-network, in-memory fixtures, plus opt-in PostgreSQL integration tests |
| **Knowledge Graph** | `graphify` | Navigable AST + semantic knowledge graph (`graphify-out/`) |

---

## 📁 Repository Structure

```text
researchconnect-ai/
├── backend/
│   ├── alembic/              # Database migration environment & versions (0001–0023)
│   ├── alembic.ini           # Alembic migration configuration
│   ├── app/
│   │   ├── api/              # FastAPI route endpoints
│   │   │   ├── health.py     # System health and liveness probe
│   │   │   ├── opportunities.py # Opportunity CRUD and direct intelligence endpoints
│   │   │   └── v1/           # Versioned REST API
│   │   │       ├── discovery.py          # Hybrid search & opportunity discovery
│   │   │       ├── researchers.py        # Researcher profile, preferences, recommendations
│   │   │       ├── submissions.py        # Manuscript submission tracking
│   │   │       ├── calendar.py           # Research calendar & iCal export
│   │   │       ├── notifications.py      # Notification center & delivery
│   │   │       ├── workspace.py          # Opportunity workspace CRUD
│   │   │       └── workspace_collaboration.py # RBAC, invitations, tasks, activity feed
│   │   ├── core/             # Configuration, cache middleware, rate limiter, security
│   │   ├── db/               # Database session, engine, custom pgvector/tsvector types
│   │   ├── evaluation/       # Benchmark runners, IR metrics, empirical datasets
│   │   │   ├── benchmark_dataset.py
│   │   │   ├── benchmark_runner.py
│   │   │   ├── deadline_dataset.py   # 43-fixture deadline evaluation corpus
│   │   │   ├── deadline_runner.py    # Deadline benchmark runner
│   │   │   ├── metrics.py            # P@K, R@K, MRR, NDCG, Kendall-τ, HHI
│   │   │   └── risk_runner.py        # Risk evaluation runner
│   │   ├── explainability/   # Result explainer (Phase 2.4F)
│   │   ├── models/           # SQLAlchemy ORM declarative models (25 model files)
│   │   │   ├── opportunity.py                  # OpportunityModel, OpportunityTopicModel
│   │   │   ├── research_profile.py             # ResearchProfileModel, AcademicStatus
│   │   │   ├── researcher_interest.py          # ResearcherInterestModel
│   │   │   ├── researcher_preference.py        # ResearcherPreferenceModel
│   │   │   ├── researcher_feedback.py          # ResearcherRecommendationFeedbackModel
│   │   │   ├── researcher_interaction.py       # ResearcherInteractionModel
│   │   │   ├── recommendation_history.py       # Snapshot & Item models
│   │   │   ├── saved_opportunity.py            # SavedOpportunityModel
│   │   │   ├── research_submission.py          # ResearchSubmissionModel
│   │   │   ├── submission_document.py          # SubmissionDocumentModel
│   │   │   ├── calendar.py                     # ResearchCalendarModel
│   │   │   ├── notification.py                 # NotificationModel, DeliveryChannel
│   │   │   ├── workspace_collaboration.py      # WorkspaceMemberModel, TaskModel, ActivityFeedModel
│   │   │   ├── adaptive_signal.py              # AdaptiveSignalModel
│   │   │   ├── personalization_calibration.py  # PersonalizationCalibrationModel
│   │   │   ├── personalization_governance.py   # PersonalizationGovernanceModel
│   │   │   ├── personalization_quality.py      # PersonalizationQualityModel
│   │   │   ├── personalization_transparency.py # PersonalizationTransparencyModel
│   │   │   └── user.py                         # UserModel
│   │   ├── personalization/  # Phase 5 — Advanced Personalization Engine (16 modules)
│   │   │   ├── scorer.py             # PersonalizationScorer (multi-signal weighted scoring)
│   │   │   ├── interpreter.py        # PreferenceInterpreter (explicit + inferred signals)
│   │   │   ├── adaptive_engine.py    # AdaptiveSignalEngine (behavioral drift detection)
│   │   │   ├── calibration_engine.py # CalibrationEngine (score normalization & bias correction)
│   │   │   ├── governance_engine.py  # GovernanceEngine (fairness, safety, audit trails)
│   │   │   ├── quality_engine.py     # QualityEngine (diversity, novelty, coverage metrics)
│   │   │   ├── transparency_engine.py # TransparencyEngine (user-facing controls & audit)
│   │   │   ├── models.py             # Internal domain models for personalization
│   │   │   └── *_config.py           # Per-engine configuration constants
│   │   ├── ranking/          # Core ranking & intelligence pipelines
│   │   │   ├── deadline/     # Phase 2.7 — Deadline Intelligence Engine
│   │   │   │   ├── extractors.py     # Evidence extraction from raw text/fields
│   │   │   │   ├── models.py         # DeadlineEvidence, NormalizedDeadline, CanonicalDeadlineView
│   │   │   │   ├── normalizers.py    # UTC normalization, timezone inference
│   │   │   │   ├── intelligence.py   # DeadlineIntelligence (urgency/status)
│   │   │   │   ├── resolvers.py      # DeadlineConflictResolver
│   │   │   │   └── explainability.py # DeadlineExplainabilityService
│   │   │   ├── risk/         # Phase 2.6 — Trust & Risk Detection
│   │   │   │   ├── engine.py         # Risk scoring orchestration
│   │   │   │   ├── extractors.py     # Evidence signal extraction
│   │   │   │   ├── graph.py          # AcademicTrustGraph (syndicate detection)
│   │   │   │   ├── models.py         # RiskEvidence, RiskAssessment
│   │   │   │   ├── scoring.py        # DeterministicRiskScoringEngine
│   │   │   │   ├── venue_intelligence.py # DOAJ, Crossref, OpenAlex verification
│   │   │   │   └── explainability.py # RiskExplainabilityService
│   │   │   ├── diversity.py          # DiversityReranker (MMR + HHI)
│   │   │   ├── hybrid_ranker.py      # HybridRanker (RRF + multi-signal)
│   │   │   └── signals.py            # RankingSignals, weight normalization
│   │   ├── repositories/     # Data access layer (vector, lexical)
│   │   ├── scheduler/        # Phase 6.3 — background scheduler and its five maintenance jobs
│   │   ├── schemas/          # Pydantic v2 schemas (opportunity, deadline, researcher, feedback)
│   │   ├── search/           # Query intelligence & GIN index integration
│   │   ├── services/         # Domain services (28 service modules)
│   │   └── main.py           # FastAPI entrypoint, CORS, router registration
│   ├── tests/                # Pytest suite — 95 modules, 1,402 collected tests
│   ├── .env.example          # Settings template for running the backend on the host
│   ├── Dockerfile            # Backend image (build context: repository root)
│   ├── Dockerfile.dockerignore # Allowlist for the backend build context
│   ├── pytest.ini            # Pytest configuration
│   └── requirements.txt      # Pinned Python dependencies
├── frontend/
│   ├── app/                  # Next.js 15 App Router routes
│   │   ├── browse/           # Browse opportunities directory
│   │   ├── peers/            # Peer & co-author discovery (5.12)
│   │   ├── postings/         # Faculty research postings & applications (5.10/5.11)
│   │   ├── calendar/         # Research calendar & deadline planning view
│   │   ├── notifications/    # Notification center
│   │   ├── opportunities/    # Opportunity details & deadline intelligence
│   │   ├── researcher/       # Researcher workspace, profiles & personalization view
│   │   ├── settings/         # User settings & personalization controls
│   │   ├── similar/          # Similar research works & matching
│   │   ├── workspace/        # Collaborative research workspace ([id]/ dynamic route)
│   │   ├── layout.tsx        # Root layout with navigation shell
│   │   ├── loading.tsx       # Root loading state
│   │   ├── not-found.tsx     # 404 handler
│   │   └── page.tsx          # Main landing & search view
│   ├── components/           # Reusable UI components
│   │   ├── discovery/        # Hybrid search, filtering, and result cards
│   │   ├── pages/            # Page-level composed views
│   │   ├── personalization/  # Personalization controls & transparency UI
│   │   └── researcher/       # Profile, Preferences, Recommendations, Explainability modals
│   ├── hooks/                # Custom React client hooks
│   ├── services/             # API client utilities (FastAPI v1 endpoints)
│   ├── styles/               # CSS design tokens, reset, and globals
│   ├── types/                # Pydantic-mirrored TypeScript schemas
│   ├── package.json          # Next.js, React, and TypeScript dependencies
│   ├── next.config.ts        # Next.js configuration
│   ├── Dockerfile            # Frontend image (Next.js standalone server)
│   ├── .dockerignore         # Frontend build-context filter
│   └── tsconfig.json         # TypeScript compiler configuration
├── scrapers/
│   ├── parsers/              # Raw data parsers and normalizers
│   ├── pipelines/            # Opportunity collection pipelines
│   └── sources/              # Data source connectors (WikiCFP, etc.)
├── docs/
│   ├── api/                  # API specification documentation
│   ├── architecture/         # System architecture, phase documentation & roadmap (61 docs)
│   └── scraping/             # Scraper design and lifecycle documentation
├── graphify-out/             # Knowledge graph (AST + semantic nodes, 26+ edge types)
├── .env.example              # Docker Compose configuration template
├── .gitignore                # Comprehensive Git ignore rules
├── docker-compose.yml        # Full stack: postgres, migrate, backend, frontend
└── README.md                 # Project documentation (this file)
```

---

## 📊 Current Implementation Status

### ✅ Phase 1 — Foundation *(Complete)*
- PostgreSQL 16 + pgvector database setup with Docker Compose
- SQLAlchemy 2.0 ORM with Alembic migration environment
- Core `OpportunityModel` and CRUD API
- Next.js 15+ App Router frontend foundation

### ✅ Phase 2 — Research Intelligence Engine *(Complete)*

| Sub-Phase | Description | Status |
|---|---|---|
| **2.1** | Ingestion Hardening (WikiCFP, deduplication, change detection, audit) | ✅ Complete |
| **2.2A** | Research Knowledge — OpenAlex API integration | ✅ Complete |
| **2.2B** | Research Knowledge — Crossref + DOI canonicalization | ✅ Complete |
| **2.3A** | Topic & Taxonomy Intelligence (canonical DAG, aliases, keyword extraction) | ✅ Complete |
| **2.3B** | Semantic Embeddings + pgvector (384-dim `all-MiniLM-L6-v2`, HNSW) | ✅ Complete |
| **2.4A** | Vector Retrieval Foundation (pgvector cosine, metadata filtering) | ✅ Complete |
| **2.4B** | Hybrid Search & Candidate Fusion (FTS + RRF dual-path) | ✅ Complete |
| **2.4C** | Similar Research Retrieval (multi-signal, taxonomy DAG proximity) | ✅ Complete |
| **2.4D** | Research ↔ Opportunity Matching (compatibility scoring, filter propagation) | ✅ Complete |
| **2.4E** | Hybrid Ranking Engine (`HybridRanker`, weight validation, tie-breaking) | ✅ Complete |
| **2.4F** | Explainable Results (`ResultExplainer`, signal attributions, qualitative summaries) | ✅ Complete |
| **2.4G** | FastAPI Discovery Layer (versioned REST, Pydantic v2, error mapping) | ✅ Complete |
| **2.4H** | Testing & Benchmarking (IR metrics, 16-scenario dataset, latency profiling) | ✅ Complete |
| **2.4I** | Full-Text GIN Indexing & Query Intelligence (stored tsvectors, acronym expansion) | ✅ Complete |
| **2.4J** | Ranking Hardening (indexing tier evaluation, predatory penalties, quality signals) | ✅ Complete |
| **2.4K** | Frontend Discovery Experience (Next.js discovery UI, explainability drawer, caching) | ✅ Complete |
| **2.5A–G** | Ranking & Recommendation Optimization (diversity, reranking, empirical eval) | ✅ Complete |
| **2.6A–G** | Predatory & Suspicious Detection (risk engine, trust graph, explainability, eval) | ✅ Complete |
| **2.7A–G** | Deadline Intelligence (evidence extraction → normalization → conflict resolution → explainability → evaluation) | ✅ Complete |

### ✅ Phase 3 — Personalized Researcher Intelligence & Recommendations *(Complete)*

| Sub-Phase | Description | Status |
|---|---|---|
| **3.1** | Researcher Profile Foundation (`ResearchProfileModel`, ORCID/OpenAlex linking, completeness) | ✅ Complete |
| **3.2** | Research Interest Intelligence (`ResearcherInterestModel`, topic strength, confidence scoring) | ✅ Complete |
| **3.3** | Personal Preference Intelligence (`ResearcherPreferenceModel`, explicit CRUD, activity-based inference) | ✅ Complete |
| **3.4** | Personalized Candidate Generation (multi-channel candidate retrieval, fallback guarantees) | ✅ Complete |
| **3.5** | Personalized Hybrid Ranking (bounded adjustment $\le 0.15$, relevance dominance, safety invariants) | ✅ Complete |
| **3.6** | Feedback & Recommendation Learning Loop (`ResearcherRecommendationFeedbackModel`, exponential decay, `SavedOpportunityModel` sync) | ✅ Complete |
| **3.7** | Recommendation History & Evaluation (`ResearcherRecommendationSnapshotModel`, point-in-time snapshots, offline IR metrics) | ✅ Complete |
| **3.8** | Personalization Explainability & Researcher UI (grounded attribution hierarchy, "Why this?" modal, summary view) | ✅ Complete |
| **3.9** | Evaluation, Ablation & Hardening (R0/R1/R2 IR evaluation, 10-state segmented evaluation, 6-signal ablation matrix, 15-scenario adversarial safety matrix, strict `X-User-ID` security) | ✅ Complete |

### ✅ Phase 4 — Research Management & Researcher Workflow *(Complete)*

| Sub-Phase | Description | Status |
|---|---|---|
| **4.0** | **Architecture & Roadmap Alignment** (Repository audit, Next.js baseline formalization, roadmap alignment) | ✅ Complete |
| **4.1** | **Opportunity Workspace** (Multi-stage tracking: SAVED → CONSIDERING → PLANNING → APPLIED → ACCEPTED/REJECTED/ARCHIVED; REST API, Next.js UI) | ✅ Complete |
| **4.2** | **Submission & Application Tracker** (`ResearchSubmissionModel`, manuscript lifecycle: DRAFT to DECISION/WITHDRAWN, target deadlines, milestones) | ✅ Complete |
| **4.3** | **Submission Documents & Readiness Engine** (Document lifecycle, immutable SHA-256 versioning, `SubmissionReadinessEngine` gating, audit events) | ✅ Complete |
| **4.4** | **Research Calendar & Deadline Planning** (`ResearchCalendarModel`, canonical deadline projection, custom planning events, RFC 5545 `.ics` export, visual calendar) | ✅ Complete |
| **4.5** | **Deadline Reminders, Notifications & Scheduled Alerts** (Multi-channel delivery, deterministic SHA-256 deduplication, zero N+1 scheduler, notification center & preferences) | ✅ Complete |
| **4.6** | **Collaborative Research Management** (Workspace members & RBAC, cryptographic invitations, collaborative tasks, append-only activity feed, Next.js `/workspace/[id]` UI) | ✅ Complete |
| **4.7** | **Research Intelligence Integration & Production Hardening** (Unified intelligence service, signal provenance, identity resolution, 6-tier explainability, unified recommendations, zero N+1 queries) | ✅ Complete |

### ✅ Phase 5 — Advanced Personalization & Academic Collaboration *(Complete)*

| Sub-Phase | Description | Status |
|---|---|---|
| **5.1** | **Researcher Preferences Foundation** (`ResearcherPreferenceModel` v2, preference schema versioning, migration 0017) | ✅ Complete |
| **5.2** | **Explicit Preference Interpretation** (`PreferenceInterpreter`, multi-dimensional signal parsing, conflict resolution) | ✅ Complete |
| **5.3** | **Personalization-Aware Scoring** (`PersonalizationScorer`, weighted multi-signal scoring, bounded adjustments) | ✅ Complete |
| **5.4** | **Researcher Feedback & Interactions** (`ResearcherInteractionModel`, interaction taxonomy, behavioral signal capture, migration 0018) | ✅ Complete |
| **5.5** | **Adaptive Preference Signals** (`AdaptiveSignalEngine`, behavioral drift detection, temporal decay, migration 0019) | ✅ Complete |
| **5.6** | **Personalization Calibration** (`CalibrationEngine`, score normalization, bias correction, fairness metrics, migration 0020) | ✅ Complete |
| **5.7** | **Personalization Quality** (`QualityEngine`, diversity, novelty, coverage, serendipity metrics, migration 0021) | ✅ Complete |
| **5.8** | **Personalization Governance** (`GovernanceEngine`, fairness auditing, safety invariants, compliance audit trails, migration 0022) | ✅ Complete |
| **5.9** | **Personalization Transparency & Controls** (`TransparencyEngine`, user-facing preference controls, data portability, audit log API, migration 0023) | ✅ Complete |
| **5.10** | **Faculty Research Postings** (`ResearchPostingModel`, 6-state lifecycle, FACULTY/ADMIN authorship, draft non-disclosure, taxonomy links, migration 0026, `/postings` UI) | ✅ Complete |
| **5.11** | **Internships, RA Openings & Applications** (structured appointment terms, `ResearchPostingApplicationModel` with role-partitioned transitions, author-private notes, append-only history, migration 0027) | ✅ Complete |
| **5.12** | **Peer & Co-Author Discovery** (`ResearcherDiscoverySettingsModel` opt-in consent, deterministic `PeerMatchingEngine` balancing shared vs complementary expertise, migration 0028, `/peers` UI) | ✅ Complete |

### 🚧 Phase 6 — Platform Infrastructure, Security & Correctness Hardening *(In Progress)*

| Area | Description | Status |
|---|---|---|
| **Authentication & Identity** | Signed HS256 bearer tokens (`/api/v1/auth/register`, `/login`, `/me`), bcrypt credentials with constant-work verification, one shared identity dependency, no fallback identity | Complete |
| **Authorization & RBAC** | `STUDENT` / `FACULTY` / `ADMIN` enforced per request, owner checks added to ten previously open researcher routes, admin-only reminder dispatch, `/api/v1/admin/users` | Complete |
| **API Protection & Observability** | Login rate limiting, security headers, proxy headers trusted only behind `TRUST_PROXY_HEADERS`, JSON/text structured logging with `X-Request-ID` correlation | Complete |
| **Database & Deployment Correctness** | Fresh `alembic upgrade head` fixed (long revision IDs), generated `fts_vector` mapping fixed so ingestion can insert, migration `0024` for the Phase 3.6/3.7 tables, opt-in PostgreSQL migration test | Complete |
| **Personalization Correctness** | Phase 5.6 calibration and 5.7 contextual adaptation wired into live ranking, researcher controls honoured in explanations, durable reset cutoff (migration `0025`), fail-closed governance, effective Phase 2.6 risk in base ranking | Complete |
| **Demo Data** | Deterministic idempotent seeder (`backend/scripts/seed_demo_data.py`) covering all roles, preferences, and a corpus exercising deadline and risk intelligence | Complete |
| **Containerization** | Backend and frontend images (non-root, pinned bases, no baked secrets), full-stack Compose with healthchecks and a one-shot migration step | Complete |
| **Frontend Auth UI** | Login / registration / administration pages and route guards | Deferred |
| **Scheduled Execution** | Background scheduler, off by default: deadline expiry, reminder dispatch, adaptive-signal and governance refresh, and opt-in WikiCFP ingestion, each calling its existing service under a PostgreSQL advisory lock ([design](docs/architecture/phase6-3-scheduler.md)) | Complete |

---

## 🏗️ Key Subsystems

### 1. Deadline Intelligence Pipeline (Phase 2.7)
- **`deadline/extractors.py`** — Extracts `DeadlineEvidence` from raw text fields using heuristic pattern matching.
- **`deadline/normalizers.py`** — `DeadlineNormalizer`: UTC normalization, timezone inference, precision classification.
- **`deadline/intelligence.py`** — `DeadlineIntelligence`: urgency scoring, temporal status, urgency tier assignment (`CRITICAL`, `URGENT`, `NORMAL`, `RELAXED`).
- **`deadline/resolvers.py`** — `DeadlineConflictResolver`: multi-source conflict resolution, revision classification.
- **`deadline/explainability.py`** — `DeadlineExplainabilityService`: structured, human-readable explanations.
- **`schemas/deadline.py`** — `OpportunityDeadlineSchema`, `CanonicalDeadlineView`, loss-aware serialization.

### 2. Trust & Risk Detection Pipeline (Phase 2.6)
- **`risk/extractors.py`** — Evidence signal extraction from opportunity metadata.
- **`risk/scoring.py`** — `DeterministicRiskScoringEngine`: calibrated composite risk ratings.
- **`risk/graph.py`** — `AcademicTrustGraph` + `SuspiciousGraphAnalyzer`: organizer syndicate and identity collision detection.
- **`risk/venue_intelligence.py`** — Cross-source indexing verification (DOAJ, Crossref, OpenAlex).
- **`risk/explainability.py`** — Provenance-backed risk explanations with progressive disclosure.

### 3. Researcher Intelligence & Personalization (Phase 3)
- **`services/researcher_profile_service.py`** — Profile management, external ID normalization, completeness computation.
- **`services/researcher_intelligence_service.py`** — Topic and expertise extraction from scholarly works.
- **`services/researcher_preference_service.py`** — Explicit preference CRUD, activity-based inferred preferences from `SavedOpportunityModel`.
- **`services/personalized_candidate_generation_service.py`** — Multi-channel candidate retrieval with fallback guarantees.
- **`services/personalization_ranking_service.py`** — Bounded personalization adjustments ($\le 0.15$) preserving base relevance dominance.
- **`services/feedback_service.py`** — Behavioral feedback logging (VIEW, SAVE, INTERESTED, APPLY, DISMISS, NOT_INTERESTED), decay, and `SavedOpportunityModel` synchronization.
- **`services/recommendation_history_service.py`** — Immutable point-in-time recommendation snapshot generation and offline IR evaluation.
- **`services/personalization_explanation_service.py`** — Grounded, attribution-based "Why this?" explanations.

### 4. Advanced Personalization Engine (Phase 5)
- **`personalization/scorer.py`** — `PersonalizationScorer`: multi-signal weighted scoring with configurable signal weights.
- **`personalization/interpreter.py`** — `PreferenceInterpreter`: explicit + inferred signal parsing, conflict resolution, and confidence scoring (largest module at 55 KB).
- **`personalization/adaptive_engine.py`** — `AdaptiveSignalEngine`: behavioral drift detection, temporal decay of stale signals.
- **`personalization/calibration_engine.py`** — `CalibrationEngine`: score normalization, bias correction, and per-researcher calibration.
- **`personalization/governance_engine.py`** — `GovernanceEngine`: fairness auditing, safety invariants, and compliance audit trail generation.
- **`personalization/quality_engine.py`** — `QualityEngine`: diversity, novelty, coverage, and serendipity metrics for recommendation sets.
- **`personalization/transparency_engine.py`** — `TransparencyEngine`: user-facing preference controls, data export, and audit log API.
- **`services/adaptive_signal_service.py`** — Persistence and retrieval of adaptive behavioral signals.
- **`services/personalization_calibration_service.py`** — Service layer for calibration workflows.
- **`services/personalization_governance_service.py`** — Governance audit orchestration and safety enforcement.
- **`services/personalization_quality_service.py`** — Quality metric computation and threshold enforcement.
- **`services/personalization_transparency_service.py`** — Transparency API operations (export, audit, control updates).

### 5. Research Management & Collaboration (Phase 4)
- **`services/workspace_service.py`** — Opportunity workspace state machine (SAVED → APPLIED → ACCEPTED etc.).
- **`services/research_submission_service.py`** — Manuscript lifecycle management from DRAFT to DECISION.
- **`services/research_submission_document_service.py`** — SHA-256 immutable document versioning, `SubmissionReadinessEngine`.
- **`services/research_calendar_service.py`** — Calendar event CRUD, canonical deadline projection, RFC 5545 `.ics` export.
- **`services/reminder_scheduler_service.py`** — Zero N+1 deadline reminder scheduler with deduplication.
- **`services/notification_service.py`** — Multi-channel notification delivery and preference management.
- **`services/workspace_collaboration_service.py`** — RBAC membership, cryptographic invitations, tasks, append-only activity feed.
- **`services/research_intelligence_integration_service.py`** — Unified intelligence service with signal provenance and 6-tier explainability.

---

## 🧪 Testing & Validation

The backend maintains a comprehensive test suite of **95 test modules** and **1,402 collected tests** (zero-network, in-memory fixtures):

```bash
# Run full backend test suite
cd backend
..\\.venv\\Scripts\\pytest.exe

# Run with verbose output
..\\.venv\\Scripts\\pytest.exe -v --tb=short

# Run specific intelligence test suites
..\\.venv\\Scripts\\pytest.exe tests/test_phase2_7g_deadline_evaluation.py
..\\.venv\\Scripts\\pytest.exe tests/test_phase3_9_hardening.py
..\\.venv\\Scripts\\pytest.exe tests/test_p0_phase5.py
..\\.venv\\Scripts\\pytest.exe tests/test_phase5_integration.py
```

Frontend verification:
```bash
cd frontend

# TypeScript type check
npm run type-check

# Next.js production build
npm run build
```

---

## 🐳 Running with Docker (full stack)

The whole application (PostgreSQL + pgvector, the FastAPI backend and the Next.js frontend)
runs with Docker Compose. Only Docker is needed on the host. Verified with Docker 29.8 and
Compose 5.5 (Docker Desktop on Windows).

### 1. Configure

```bash
cp .env.example .env
```

Open `.env` and set the two required values. Each can be generated with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.

| Variable | Required | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | yes | Database password. Use URL-safe characters only (letters, digits, `-` `_` `.` `~`): it is embedded in the backend's connection URL. It takes effect when the database volume is first created. |
| `AUTH_SECRET_KEY` | yes | Access-token signing secret, at least 32 characters. The backend runs with `APP_ENV=production` and refuses to start without it. Changing it signs everybody out. |
| `CORS_ORIGINS` | no | Browser origins allowed to call the API with credentials (JSON list). |
| `NEXT_PUBLIC_API_URL` | no | The API address **as seen from the browser**. It is compiled into the frontend at build time, so rebuild the frontend after changing it. |
| `SCHEDULER_ENABLED` | no | `true` runs the background maintenance jobs (deadline expiry, reminders, adaptive-signal and governance refresh) in the backend. Default `false`. See [Phase 6.3](docs/architecture/phase6-3-scheduler.md). |
| `SCHEDULER_OPPORTUNITY_REFRESH_ENABLED` | no | `true` also schedules WikiCFP ingestion, which makes outbound requests to a third-party site. Default `false`. |

`.env` is git-ignored. Compose refuses to run while either required value is missing. Both
must be set even when starting a single service, because Compose reads the whole file.

### 2. Start

```bash
docker compose up --build -d --wait
```

The first build downloads base images and dependencies and takes several minutes; later
starts take under half a minute. `--wait` returns once every service is healthy:

| Service | Role | Address |
|---|---|---|
| `postgres` | PostgreSQL 16 + pgvector; data kept in the `postgres_data` volume | `127.0.0.1:5432` |
| `migrate` | Waits for the database, runs `alembic upgrade head`, then exits | — |
| `backend` | FastAPI API; starts only after the migration succeeds | `http://localhost:8000` |
| `frontend` | Next.js web application | `http://localhost:3000` |

Migrations run on every start and do nothing when the schema is already current.

### 3. Load demo data (optional)

```bash
docker compose exec backend python -m scripts.seed_demo_data
```

Then sign in at `http://localhost:3000/login` as `demo.faculty@researchconnect.test`,
`demo.student@researchconnect.test` or `demo.admin@researchconnect.test`, all with the
password `DemoPass123!`.

### Everyday commands

| Task | Command |
|---|---|
| Status and health | `docker compose ps` |
| Logs of one service | `docker compose logs backend` (or `frontend`, `postgres`, `migrate`) |
| Restart everything | `docker compose restart` |
| Stop, keeping all data | `docker compose down` |
| Rebuild after code changes | `docker compose up --build -d --wait` |
| Rebuild only the frontend | `docker compose build frontend` |
| Reset the demo data | `docker compose exec backend python -m scripts.seed_demo_data --reset` |
| **Delete all data** and start clean | `docker compose down -v`, then `docker compose up --build -d --wait` |
| Scheduler runs (when enabled) | `docker compose logs backend`, lines starting `Scheduled job` |
| Database shell | `docker compose exec postgres psql -U researchconnect -d researchconnect` |

### Networking and security

- Every port is published on `127.0.0.1` only. The browser calls the API directly, so the
  backend port has to be reachable from wherever the browser runs. PostgreSQL stays
  host-local so the backend and its tests can also be run on the host.
- To serve other machines: change the published ports in `docker-compose.yml`, set
  `NEXT_PUBLIC_API_URL` to the address browsers use for the API, add the frontend's address
  to `CORS_ORIGINS`, and rebuild the frontend. Put TLS in front with a reverse proxy, and set
  `TRUST_PROXY_HEADERS=true` only if that proxy overwrites the forwarding headers.
- The backend and frontend run as unprivileged users, with every Linux capability dropped and
  `no-new-privileges`. No secret is built into any image: configuration arrives at runtime,
  and each container receives only the variables it needs.
- Semantic search downloads its embedding model on first use, which needs outbound internet.
  Without it, search falls back to lexical ranking.

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `required variable POSTGRES_PASSWORD is missing a value` (or `AUTH_SECRET_KEY`) | Create `.env` from `.env.example` and set both required values. |
| The database rejects the password after `POSTGRES_PASSWORD` was changed | The password is fixed when the volume is created. Restore the old value, or run `docker compose down -v` (deletes all data). |
| `backend` never becomes healthy | `docker compose logs migrate` and `docker compose logs backend` show the cause; the backend does not start until the migration succeeds. |
| The browser cannot reach the API | `NEXT_PUBLIC_API_URL` must be reachable from the browser and the page's origin must be listed in `CORS_ORIGINS`. Rebuild the frontend after changing the URL. |
| A port is already allocated | Another process (often a host-run backend or database) holds 3000, 8000 or 5432. Stop it, or change the published port. |

---

## 🚀 Local Development Setup

### Prerequisites

- **Python**: 3.11 or higher
- **Node.js**: 20.x or higher (with `npm` 10+)
- **Docker & Docker Compose**: (Recommended for PostgreSQL + pgvector) OR a local PostgreSQL 16 installation with the `pgvector` extension

---

### 1. Database Setup

To run the backend on the host, start only the PostgreSQL container. It uses the
repository-root `.env`, where both required values must be set (see
[Running with Docker](#-running-with-docker-full-stack)):

```bash
cp .env.example .env
docker compose up -d postgres
```

This starts PostgreSQL on `127.0.0.1:5432` with database and user `researchconnect`, the
password from `POSTGRES_PASSWORD`, and the `vector` extension.

---

### 2. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
# Windows (PowerShell):
.\\.venv\\Scripts\\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy the backend settings template, then set the password in DATABASE_URL
# to the POSTGRES_PASSWORD from the repository-root .env
cp .env.example .env

# Run database migrations (0001–0028)
alembic upgrade head

# Load a deterministic demo dataset: 3 accounts (faculty/student/admin), explicit
# preferences, and 12 opportunities including expired deadlines and predatory venues.
# Idempotent; supports --reset and --dry-run.
python -m scripts.seed_demo_data

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

API interactive documentation: `http://localhost:8000/docs`

Sign in with the seeded faculty account to obtain a bearer token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"email\":\"demo.faculty@researchconnect.test\",\"password\":\"DemoPass123!\"}"
```

Send the returned `access_token` as `Authorization: Bearer <token>` on protected routes. For
local work without tokens, set `AUTH_DEV_IDENTITY_ENABLED=true` to accept a raw `X-User-ID`
header instead; that setting is refused at startup when `APP_ENV=production`.

Semantic (vector) retrieval additionally needs embeddings, which are generated offline:

```bash
python -m ml.embeddings.generate_embeddings
```

---

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Next.js web application: `http://localhost:3000`

---

### 4. Running Validation

```bash
# Backend tests (1,402 tests, zero-network)
cd backend
..\\.venv\\Scripts\\pytest.exe

# Frontend type validation and production build
cd frontend
npm run type-check
npm run build
```

The PostgreSQL integration tests (live search, pgvector, migrations) run against the
database named by `DATABASE_URL` and are skipped when it is unreachable. To run them against
the Compose database, set `DATABASE_URL` to
`postgresql+psycopg://researchconnect:<POSTGRES_PASSWORD>@localhost:5432/researchconnect`.

---

## 🏛️ Architectural Invariants

1. **Deterministic over probabilistic** — All ranking, scoring, and personalization logic is fully deterministic. Given identical inputs, the system produces identical outputs. Zero LLM inference or random tie-breaking during ranking.
2. **Zero network at request time** — The entire ranking, risk, deadline, and personalization pipeline executes in-memory with zero external network calls or database writes at request time.
3. **Relevance and safety dominance** — Personalization adjustments are bounded ($|adj| \le 0.15$). High-risk venues ($risk \ge 0.70$ or $is\_predatory = True$) and expired deadlines ($deadline\_status = EXPIRED$) are strictly suppressed and cannot be boosted by personalization.
4. **Canonical source of truth** — Phase 4 Research Management and Phase 5 Personalization consume canonical outputs from Phase 2.6 (risk), Phase 2.7 (deadlines), and Phase 3 (researcher intelligence). No duplicate domain logic or shadow calculations.
5. **Strict user scoping & ownership** — All researcher workflows, saved opportunities, preferences, submission records, and personalization data enforce `X-User-ID` isolation to prevent cross-user data leakage.
6. **No premature scaling** — The architecture avoids Kafka, Celery, Kubernetes, and heavy MLOps overhead in favor of clean, modular, and maintainable services.
7. **Governance & fairness by design** — The Phase 5 governance engine enforces fairness invariants, maintains immutable audit trails, and provides transparency controls so researchers can understand and control their personalization.

---

## ⚠️ Current Scope Boundaries & Status

- **Authentication**: Implemented in Phase 6. `POST /api/v1/auth/register` and `/auth/login` issue signed HS256 bearer tokens over bcrypt-hashed credentials, and one shared dependency (`app/api/deps.py`) establishes identity for every protected route with no fallback identity. The raw `X-User-ID` header is accepted **only** when `AUTH_DEV_IDENTITY_ENABLED=true`, which is refused at startup under `APP_ENV=production`. There is not yet a login page in the web UI, so a browser session still bootstraps a developer identity.
- **Deployment**: `docker compose up --build -d --wait` runs the full stack (see [Running with Docker](#-running-with-docker-full-stack)). Ports are published on `127.0.0.1`; serving other machines needs the reverse-proxy, API-URL and CORS changes described there.
- **Scheduled Execution**: The background scheduler is off unless `SCHEDULER_ENABLED=true`, and WikiCFP ingestion additionally needs `SCHEDULER_OPPORTUNITY_REFRESH_ENABLED=true`. Enable it in one backend process: locks stop two processes from running a job at the same time, but each process schedules its own runs. Reminder dispatch also remains available as an `ADMIN`-only endpoint.
- **Embeddings Generation**: Semantic embeddings are calculated deterministically via local sentence-transformers and generated offline (`python -m ml.embeddings.generate_embeddings`); automated background ingestion daemons are planned for production hardening.
- **Scraper Ingestion**: WikiCFP is fully operational as a verified source connector; additional connectors (ACM, IEEE, Springer) are planned for ingestion scaling.
- **Explicit Exclusions**: An opportunity matching an `EXCLUDED` preference receives no personalization boost, but its score is not demoted below its base relevance, so a highly relevant excluded venue can still appear in a ranked list. This is what the Phase 5 safety invariants specify and assert; changing it is a product decision.

---

## 🌿 Git & Contribution Workflow

1. Ensure clean branch state before starting work (`git status`).
2. Keep `.env` and sensitive credentials untracked; update `.env.example` when new configuration keys are added.
3. Commit small, logical units of work with descriptive commit messages.
4. Run backend tests (`pytest`) and frontend builds (`npm run build`) before pushing to remote.

---

## 🤖 Development & AI Tooling

- **Primary Coding Model**: Antigravity with **Claude Sonnet** for core feature design, refactoring, and implementation.
- **Fallback / Alternative**: **Google Gemini** for specialized analysis or alternate reasoning.
- **Knowledge Graph**: `graphify` — full codebase AST + semantic graph (see `graphify-out/`).

---

For the full development roadmap and phase-by-phase feature breakdown, see [Development Roadmap](docs/architecture/project-roadmap.md) and [Phase 5.9 Personalization Transparency](docs/architecture/phase5-9-personalization-transparency-controls.md).
