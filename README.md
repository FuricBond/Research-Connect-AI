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
| **Database** | PostgreSQL 16 + `pgvector` extension | Relational storage, HNSW vector indexes (cosine similarity), GIN full-text search indexes |
| **Embeddings** | `sentence-transformers` · `all-MiniLM-L6-v2` | 384-dimensional dense semantic vectors with content-hash deduplication |
| **Scraping** | `requests`, `BeautifulSoup4` | Production WikiCFP connector, change detection, and data freshness pipelines |
| **IR / Evaluation** | `scikit-learn`, custom RRF & IR Metrics | P@K, R@K, MRR, NDCG, Kendall-τ rank correlation, HHI concentration, 16-scenario benchmark suite |
| **Personalization Engine** | Custom deterministic engine | Adaptive signals, calibration, governance, quality assurance, and transparency controls |
| **Containerization** | Docker Compose | Local PostgreSQL 16 with pre-configured `pgvector` extension |
| **Testing** | `pytest` | 88 test modules, 1,247 collected tests — all zero-network, in-memory fixtures |
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
│   │   ├── schemas/          # Pydantic v2 schemas (opportunity, deadline, researcher, feedback)
│   │   ├── search/           # Query intelligence & GIN index integration
│   │   ├── services/         # Domain services (28 service modules)
│   │   └── main.py           # FastAPI entrypoint, CORS, router registration
│   ├── tests/                # Pytest suite — 88 modules, 1,247 collected tests
│   ├── pytest.ini            # Pytest configuration
│   └── requirements.txt      # Pinned Python dependencies
├── frontend/
│   ├── app/                  # Next.js 15 App Router routes
│   │   ├── browse/           # Browse opportunities directory
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
├── .env.example              # Environment variables template
├── .gitignore                # Comprehensive Git ignore rules
├── docker-compose.yml        # PostgreSQL + pgvector container setup
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

### ✅ Phase 5 — Advanced Personalization Engine *(Complete)*

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

The backend maintains a comprehensive test suite of **88 test modules** and **1,247 collected tests** (all zero-network, in-memory):

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

## 🚀 Local Development Setup

### Prerequisites

- **Python**: 3.11 or higher
- **Node.js**: 20.x or higher (with `npm` 10+)
- **Docker & Docker Compose**: (Recommended for PostgreSQL + pgvector) OR a local PostgreSQL 16 installation with the `pgvector` extension

---

### 1. Database Setup

Start the PostgreSQL container with pgvector:

```bash
docker compose up -d
```

This starts PostgreSQL on `localhost:5432` with database `researchconnect`, user `researchconnect`, password `researchconnect`, and initializes the `vector` extension.

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

# Copy environment file
cp ../.env.example .env

# Run database migrations (0001–0023)
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

API interactive documentation: `http://localhost:8000/docs`

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
# Backend tests (1,247 tests, zero-network)
cd backend
..\\.venv\\Scripts\\pytest.exe

# Frontend type validation and production build
cd frontend
npm run type-check
npm run build
```

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

- **Authentication Infrastructure**: Researcher operations currently use explicit `X-User-ID` header matching and user verification. Full session cookies / OAuth2 login flows are planned for platform hardening.
- **Embeddings Generation**: Semantic embeddings are calculated deterministically via local sentence-transformers; automated background ingestion daemons are planned for production hardening.
- **Scraper Ingestion**: WikiCFP is fully operational as a verified source connector; additional connectors (ACM, IEEE, Springer) are planned for ingestion scaling.

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
