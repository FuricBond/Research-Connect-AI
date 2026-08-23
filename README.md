# ResearchConnect AI

**ResearchConnect AI** is an intelligent full-stack platform designed to help students, researchers, and faculty discover, organize, and match with academic and research opportunities — including peer-reviewed conferences, academic journals, calls for papers (CFPs), workshops, research assistantships, and grants.

The project is built as a clean, maintainable monorepo application for a student final-year project. It avoids unnecessary distributed systems, microservices, and complex MLOps overhead (e.g., no Kubernetes, Kafka, Airflow, or MLflow) in favor of a straightforward, robust architecture.

---

## 🏛️ Architecture Overview

```text
┌──────────────────────────────────────────────────────────┐
│                   React + TypeScript                     │
│                    (Vite Frontend)                       │
└────────────────────────────┬─────────────────────────────┘
                             │ REST / JSON
                             ▼
┌──────────────────────────────────────────────────────────┐
│                   FastAPI / Python                       │
│                   (Backend Service)                      │
│                                                          │
│  ┌─────────────────┐ ┌─────────────────┐ ┌────────────┐  │
│  │   API Routes    │ │ Opportunity Svc │ │ Recommender│  │
│  └────────┬────────┘ └────────┬────────┘ └─────┬──────┘  │
│           │                   │                │         │
│           └───────────────┐   │   ┌────────────┘         │
│                           ▼   ▼   ▼                      │
│                   SQLAlchemy 2.0 ORM                     │
│                   Alembic Migrations                     │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│              PostgreSQL + pgvector Engine                │
│         (Relational Data + Semantic Vectors)             │
└──────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

- **Frontend**: React 19, TypeScript, Vite, Vanilla CSS / modern semantic layout, Lucide React icons
- **Backend**: Python 3.11+, FastAPI, Pydantic v2 / Settings, SQLAlchemy 2.0, Alembic
- **Database**: PostgreSQL 16 with `pgvector` extension
- **Scraping**: Requests, BeautifulSoup4 (with Playwright reserved for dynamic rendering when needed)
- **AI & NLP**: Sentence Transformers, scikit-learn, XGBoost (to be integrated cleanly as modules)
- **Containerization**: Lightweight Docker Compose for local PostgreSQL + pgvector setup
- **Version Control**: Git & GitHub

---

## 📁 Repository Structure

```text
researchconnect-ai/
├── backend/
│   ├── alembic/              # Database migration environment & versions
│   ├── alembic.ini           # Alembic migration configuration
│   ├── app/
│   │   ├── ai/               # Recommender logic and ML integrations
│   │   ├── api/              # FastAPI route endpoints (health, opportunities)
│   │   ├── core/             # Configuration and environment settings
│   │   ├── db/               # Database session, engine, and init SQL
│   │   ├── models/           # SQLAlchemy ORM declarative models
│   │   ├── schemas/          # Pydantic validation schemas
│   │   ├── services/         # Business logic and opportunity services
│   │   └── main.py           # FastAPI entrypoint and CORS middleware
│   ├── tests/                # Pytest test suite
│   ├── pytest.ini            # Pytest configuration
│   └── requirements.txt      # Pinned Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/       # UI components (OpportunityList, etc.)
│   │   ├── pages/            # Application views
│   │   ├── services/         # API client utilities
│   │   ├── types/            # TypeScript type definitions
│   │   ├── App.tsx           # Main application shell
│   │   ├── main.tsx          # React root render
│   │   └── styles.css        # Core design styles and tokens
│   ├── index.html            # HTML entrypoint
│   ├── package.json          # Frontend dependencies and scripts
│   └── tsconfig.json         # TypeScript compiler configuration
├── scrapers/
│   ├── parsers/              # Raw data parsers and normalizers
│   ├── pipelines/            # Opportunity collection pipelines
│   └── sources/              # Data source connectors
├── ml/
│   ├── embeddings/           # Text embedding generators and vector utilities
│   ├── recommendation/       # Opportunity scoring and ranking algorithms
│   └── topic_analysis/       # Topic and keyword extraction modules
├── docs/
│   ├── api/                  # API specification documentation
│   ├── architecture/         # System architecture & project roadmap
│   └── database/             # Schema design and pgvector documentation
├── .env.example              # Environment variables template
├── .gitignore                # Comprehensive Git ignore rules
├── docker-compose.yml        # PostgreSQL with pgvector container setup
└── README.md                 # Project documentation
```

---

## 🚀 Local Development Setup

### Prerequisites

- **Python**: 3.11 or higher
- **Node.js**: 20.x or higher (with `npm` 10+)
- **Docker & Docker Compose**: (Recommended for PostgreSQL + pgvector) OR a local PostgreSQL installation with `pgvector`

---

### 1. Database Setup

Start the PostgreSQL container with pgvector using Docker Compose:

```bash
docker compose up -d
```

This starts PostgreSQL on `localhost:5432` with database `researchconnect`, user `researchconnect`, password `researchconnect`, and initializes the `vector` extension.

---

### 2. Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment file:
   ```bash
   cp ../.env.example .env
   ```
5. Run database migrations (when ready):
   ```bash
   alembic upgrade head
   ```
6. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   API interactive documentation is available at `http://localhost:8000/docs`.

---

### 3. Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The web application will be accessible at `http://localhost:5173`.

---

### 4. Running Tests

- **Backend Tests**:
  ```bash
  cd backend
  pytest
  ```
- **Frontend Build Validation**:
  ```bash
  cd frontend
  npm run build
  ```

---

## 🌿 Git & Contribution Workflow

1. Ensure clean branch state before starting work (`git status`).
2. Keep `.env` and sensitive credentials untracked; update `.env.example` when new configuration keys are added.
3. Commit small, logical units of work with descriptive commit messages.
4. Run backend tests (`pytest`) and frontend builds (`npm run build`) before pushing changes to remote.

---

## 🤖 Development & Coding Model Workflow

For AI-assisted development across the team:
- **Primary Coding Model**: Use Antigravity with **Claude Sonnet** for core feature design, refactoring, and general implementation.
- **Fallback / Alternative**: Switch to a **Google Gemini model** if specialized analysis or alternate reasoning is required.
*(Note: These preferences govern IDE/tooling workflows only and are not runtime application dependencies.)*

---

## 📊 Current Implementation Status

- [x] Repository structure initialized with clean module separation
- [x] Backend FastAPI app with health check and opportunity endpoints
- [x] Database configuration and Alembic migration structure wired
- [x] Frontend React + TypeScript + Vite app with OpportunityList view
- [x] Scraper and ML package structure prepared for module expansion
- [x] Comprehensive `.gitignore` and sanitized `.env.example`
- [ ] Database schema expansion and live database integration *(Next)*
- [ ] Scraper pipeline implementation for academic sources
- [ ] ML embedding and vector search integration with pgvector
- [ ] User profile matching and personalized recommendations

For the full breakdown of planned features, see [Development Roadmap](file:///d:/Project/researchconnect-ai/docs/architecture/project-roadmap.md).
