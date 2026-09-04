# ResearchConnect AI

**ResearchConnect AI** is an intelligent full-stack platform designed to help students, researchers, and faculty discover, organize, and match with academic and research opportunities — including peer-reviewed conferences, academic journals, calls for papers (CFPs), workshops, research assistantships, and grants.

The project is built as a clean, maintainable monorepo for a collaborative final-year project team. It deliberately avoids unnecessary distributed systems, microservices, and MLOps overhead (no Kubernetes, Kafka, Airflow, or MLflow) in favor of a robust, readable, and well-tested architecture.

---

## 🏛️ Architecture Overview

```text
┌──────────────────────────────────────────────────────────┐
│                   React + TypeScript                     │
│                    (Vite Frontend)                       │
│          [Next.js migration planned for Phase 3]         │
└────────────────────────────┬─────────────────────────────┘
                             │ REST / JSON
                             ▼
┌──────────────────────────────────────────────────────────┐
│                   FastAPI / Python                       │
│                   (Backend Service)                      │
│                                                          │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │  API Routes │ │ Ranking &    │ │  Deadline          │ │
│  │  (v1/)      │ │ Discovery    │ │  Intelligence      │ │
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
        │                    risk/engine.py, scoring.py
        ▼
[Conflict/Revision]    ─── deadline/resolvers.py
        │                    risk/graph.py (AcademicTrustGraph)
        ▼
[Explainability]       ─── deadline/explainability.py
        │                    risk/explainability.py
        │                    explainability/result_explainer.py
        ▼
[API + Frontend]       ─── api/v1/discovery.py
                             schemas/deadline.py, opportunity.py
```

The full pipeline is **deterministic, in-memory, and zero-network** at ranking time — no LLM calls, no external API requests, no database writes during ranking.

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, Vanilla CSS, Lucide React *(Next.js migration planned)* |
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| **Database** | PostgreSQL 16 with `pgvector` extension (HNSW indexes, cosine similarity) |
| **Embeddings** | `sentence-transformers` · `all-MiniLM-L6-v2` (384-dim vectors) |
| **Scraping** | `requests`, `BeautifulSoup4` (Playwright reserved for JS-heavy pages) |
| **IR / ML** | `scikit-learn`, `XGBoost`, custom Reciprocal Rank Fusion, NDCG/MRR/P@K |
| **Containerization** | Docker Compose (local PostgreSQL + pgvector) |
| **Testing** | `pytest` — 44 test modules, 640+ passing tests |
| **Version Control** | Git & GitHub |

---

## 📁 Repository Structure

```text
researchconnect-ai/
├── backend/
│   ├── alembic/              # Database migration environment & versions
│   ├── alembic.ini           # Alembic migration configuration
│   ├── app/
│   │   ├── ai/               # Recommender logic and ML integrations
│   │   ├── api/              # FastAPI route endpoints
│   │   │   └── v1/           # Versioned REST API (discovery, opportunities)
│   │   ├── core/             # Configuration, rate limiting, environment settings
│   │   ├── db/               # Database session, engine, and init SQL
│   │   ├── evaluation/       # Benchmarking, IR metrics, empirical datasets
│   │   │   ├── benchmark_dataset.py
│   │   │   ├── benchmark_runner.py
│   │   │   ├── deadline_dataset.py   # 43-fixture deadline evaluation corpus
│   │   │   ├── deadline_runner.py    # Deadline benchmark runner
│   │   │   ├── metrics.py            # P@K, R@K, MRR, NDCG, Kendall-τ, HHI
│   │   │   └── risk_runner.py        # Risk evaluation runner
│   │   ├── explainability/   # Result explainer (Phase 2.4F)
│   │   ├── models/           # SQLAlchemy ORM declarative models
│   │   ├── ranking/          # Core ranking & intelligence pipeline
│   │   │   ├── deadline/     # Phase 2.7 — Deadline Intelligence
│   │   │   │   ├── __init__.py
│   │   │   │   ├── extractors.py     # Evidence extraction from raw text/fields
│   │   │   │   ├── models.py         # DeadlineEvidence, NormalizedDeadline, etc.
│   │   │   │   ├── normalizers.py    # UTC normalization, timezone inference
│   │   │   │   ├── intelligence.py   # DeadlineIntelligence (urgency/status)
│   │   │   │   ├── resolvers.py      # DeadlineConflictResolver
│   │   │   │   └── explainability.py # DeadlineExplainabilityService
│   │   │   ├── risk/         # Phase 2.6 — Trust & Risk Detection
│   │   │   │   ├── engine.py         # Risk scoring orchestration
│   │   │   │   ├── extractors.py     # Evidence signal extraction
│   │   │   │   ├── graph.py          # AcademicTrustGraph (syndicate detection)
│   │   │   │   ├── models.py         # RiskEvidence, RiskAssessment, etc.
│   │   │   │   ├── scoring.py        # DeterministicRiskScoringEngine
│   │   │   │   ├── venue_intelligence.py
│   │   │   │   └── explainability.py
│   │   │   ├── diagnostics.py        # AcademicCoverageDiagnostics
│   │   │   ├── diversity.py          # DiversityReranker (MMR + HHI)
│   │   │   ├── features.py           # AcademicFeatures extraction
│   │   │   ├── hybrid_ranker.py      # HybridRanker (RRF + multi-signal)
│   │   │   ├── reranker.py           # Post-processing re-ranker
│   │   │   ├── signals.py            # RankingSignals, weight normalization
│   │   │   └── venue_intelligence.py
│   │   ├── repositories/     # Data access layer (vector, lexical)
│   │   ├── schemas/          # Pydantic schemas (opportunity, deadline, discovery)
│   │   ├── search/           # Query intelligence & GIN index integration
│   │   ├── services/         # Business logic (opportunity, similarity, matching)
│   │   └── main.py           # FastAPI entrypoint, CORS, router registration
│   ├── tests/                # Pytest suite — 44 modules, 640+ tests
│   ├── pytest.ini            # Pytest configuration
│   └── requirements.txt      # Pinned Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/       # UI components (OpportunityList, ExplainabilityDrawer, etc.)
│   │   ├── pages/            # Application views (Discovery, Opportunity, Explore)
│   │   ├── services/         # API client utilities
│   │   ├── types/            # TypeScript type definitions (deadline, risk, opportunity)
│   │   ├── App.tsx           # Main application shell
│   │   ├── main.tsx          # React root render
│   │   └── styles.css        # Core design styles and tokens
│   ├── index.html            # HTML entrypoint
│   ├── package.json          # Frontend dependencies and scripts
│   └── tsconfig.json         # TypeScript compiler configuration
├── scrapers/
│   ├── parsers/              # Raw data parsers and normalizers
│   ├── pipelines/            # Opportunity collection pipelines
│   └── sources/              # Data source connectors (WikiCFP, etc.)
├── docs/
│   ├── api/                  # API specification documentation
│   ├── architecture/         # System architecture, phase documentation & roadmap
│   └── scraping/             # Scraper design and lifecycle documentation
├── graphify-out/             # Knowledge graph (5,051 nodes, 10,878 edges)
├── .env.example              # Environment variables template
├── .gitignore                # Comprehensive Git ignore rules
├── docker-compose.yml        # PostgreSQL + pgvector container setup
└── README.md                 # Project documentation (this file)
```

---

## 📊 Current Implementation Status

### ✅ Phase 1 — Foundation
- PostgreSQL 16 + pgvector database setup
- SQLAlchemy 2.0 ORM with Alembic migration environment
- Core `Opportunity` model and basic CRUD API
- React + TypeScript + Vite frontend scaffold

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
| **2.4K** | Frontend Discovery Experience (React UI, explainability drawer, rate limiting, caching) | ✅ Complete |
| **2.5A–G** | Ranking & Recommendation Optimization (diversity, reranking, empirical eval) | ✅ Complete |
| **2.6A–G** | Predatory & Suspicious Detection (risk engine, trust graph, explainability) | ✅ Complete |
| **2.7A–G** | Deadline Intelligence (evidence extraction → normalization → conflict resolution → explainability → evaluation) | ✅ Complete |

### 🔜 Phase 3 — Personalized Researcher Intelligence & Recommendations *(Next)*
- Researcher profile modeling and preference learning
- Personalized opportunity ranking
- Submission tracking, calendar integration, deadline notifications
- Frontend migration to Next.js (App Router, SSR)

---

## 🏗️ Key Subsystems

### Deadline Intelligence Pipeline (Phase 2.7)

The deadline intelligence pipeline extracts, normalizes, validates, and explains submission deadline data with no network calls at ranking time:

- **`deadline/extractors.py`** — Extracts `DeadlineEvidence` from raw text fields using pattern matching + heuristics
- **`deadline/normalizers.py`** — `DeadlineNormalizer`: UTC normalization, timezone inference, precision classification
- **`deadline/intelligence.py`** — `DeadlineIntelligence`: urgency scoring, temporal status, urgency tier assignment
- **`deadline/resolvers.py`** — `DeadlineConflictResolver`: revision classification, multi-source conflict resolution
- **`deadline/explainability.py`** — `DeadlineExplainabilityService`: structured human-readable explanations
- **`schemas/deadline.py`** — `OpportunityDeadlineSchema`, `CanonicalDeadlineView`, loss-aware serialization
- **Evaluation**: 43-fixture empirical dataset, 20/20 safety invariants passing, `DeadlineBenchmarkRunner`

### Trust & Risk Detection Pipeline (Phase 2.6)

- **`risk/extractors.py`** — Evidence signal extraction from opportunity fields
- **`risk/scoring.py`** — `DeterministicRiskScoringEngine`: calibrated composite risk scores
- **`risk/graph.py`** — `AcademicTrustGraph` + `SuspiciousGraphAnalyzer`: organizer syndicate and identity-collision detection
- **`risk/venue_intelligence.py`** — Cross-source indexing verification (DOAJ, Crossref, OpenAlex)
- **`risk/explainability.py`** — Provenance-backed risk explanations with progressive disclosure

### Hybrid Ranking Engine (Phase 2.4–2.5)

- **`hybrid_ranker.py`** — `HybridRanker`: Reciprocal Rank Fusion, multi-signal weighted scoring, deterministic tie-breaking
- **`signals.py`** — `RankingSignals`: feature extraction, normalization, weight validation
- **`diversity.py`** — `DiversityReranker`: MMR diversity, HHI concentration control
- **`features.py`** — `AcademicFeatures`: citation, venue tier, recency, submission compatibility

### Evaluation Framework

- **`evaluation/metrics.py`** — P@K, R@K, MRR, NDCG, Kendall-τ, HHI concentration
- **`evaluation/benchmark_runner.py`** — `BenchmarkRunner`: 16-scenario IR evaluation harness
- **`evaluation/deadline_runner.py`** — `DeadlineBenchmarkRunner`: end-to-end deadline pipeline evaluation
- **`evaluation/risk_runner.py`** — Risk classification benchmark harness

---

## 🧪 Testing

The project maintains a comprehensive test suite with **44 test modules** and **640+ passing tests** (all zero-network, in-memory):

```bash
cd backend
pytest                    # Run full suite
pytest -v --tb=short      # Verbose with short tracebacks
pytest tests/test_phase2_7g_deadline_evaluation.py  # Phase-specific tests
pytest tests/test_risk_scoring_engine.py             # Risk engine tests
```

Key test modules:

| Module | Coverage |
|---|---|
| `test_phase2_7g_deadline_evaluation.py` | Deadline pipeline: 43 fixtures, 20 safety invariants |
| `test_phase2_6g_risk_evaluation.py` | Risk pipeline: classification accuracy, false-positive hardening |
| `test_phase2_5g_evaluation.py` | Ranking optimization: diversity, MRR, NDCG |
| `test_risk_explainability.py` | Risk explainability: provenance, signal attribution |
| `test_deadline_conflict_resolution.py` | Conflict resolver: revision classification, authority tiers |
| `test_suspicious_graph_intelligence.py` | Trust graph: syndicate detection, identity collision |
| `test_hybrid_ranker.py` | HybridRanker: RRF fusion, weight validation |
| `test_result_explainer.py` | Result explainer: signal attributions, qualitative summaries |

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
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp ../.env.example .env

# Run database migrations
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

API interactive docs: `http://localhost:8000/docs`

---

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Web app: `http://localhost:5173`

---

### 4. Running Tests

```bash
# Backend test suite (640+ tests, all in-memory)
cd backend
pytest

# Frontend build validation
cd frontend
npm run build
```

---

## 🏛️ Architectural Principles

1. **Deterministic over probabilistic** — All ranking and scoring logic is fully deterministic. Given identical input, the pipeline always produces identical output. No LLM inference, no random seeds, no non-deterministic tie-breaking.

2. **Zero network at ranking time** — The entire ranking, risk, and deadline pipeline runs with zero network calls, zero database writes, and zero external API requests at request time.

3. **Evidence-backed explanations** — Every risk score, deadline status, and ranking decision carries structured provenance: which signals fired, which sources contributed, and what the confidence basis is.

4. **In-memory, composable pipeline** — Each pipeline stage (extraction → normalization → scoring → conflict resolution → explainability) is independently testable and can be composed or short-circuited without side effects.

5. **No premature scaling** — The architecture deliberately avoids Kubernetes, Kafka, Celery workers, MLflow, and Airflow. Complexity is introduced only when empirically required.

---

## ⚠️ Current Limitations

- **No live user authentication** — The platform does not yet implement user accounts, sessions, or JWT/OAuth. This is planned for Phase 3.
- **No persistent submission tracking** — Submission tracker and calendar integration are Phase 3 features.
- **Frontend pre-migration** — The current frontend uses React + Vite. A migration to **Next.js App Router** is planned for Phase 3 to support SSR and improved SEO.
- **Scraper coverage** — Currently only WikiCFP is a production-grade source connector. Additional source integrations (ACM, IEEE, Springer) are pending.
- **Embeddings not auto-generated** — Semantic embeddings require a manual pipeline trigger; no background scheduler is yet active.
- **No live notifications** — Deadline notification emails and in-app alerts are planned for Phase 3.

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
- **Knowledge Graph**: `graphify` — 5,051 nodes, 10,878 edges across the full codebase (see `graphify-out/`).

*(These preferences govern IDE and tooling workflows only; they are not runtime application dependencies.)*

---

For the full development roadmap and phase-by-phase feature breakdown, see [Development Roadmap](docs/architecture/project-roadmap.md).
