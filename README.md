# ResearchConnect AI

ResearchConnect AI is a normal monorepo application for discovering, organizing, and recommending research opportunities such as conferences, journals, CFPs, workshops, grants, and publication venues.

The project intentionally starts simple:

- React frontend
- FastAPI/Python backend
- PostgreSQL with pgvector
- Scraping modules in the same repository
- AI/ML modules in the same repository

No Kubernetes, microservices, Airflow, MLflow, or distributed/MLOps setup is included unless explicitly added later.

## Project Structure

```text
researchconnect-ai/
  backend/      FastAPI API, database access, services, AI integration
  frontend/     React application
  scrapers/     Source collectors, parsers, scraping pipelines
  ml/           Embeddings, recommendation, topic analysis
  docs/         Architecture, API, and database notes
```

## Local Development

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Database:

Use PostgreSQL locally with the `pgvector` extension enabled. A lightweight local `docker-compose.yml` is included only to make local database setup easier.

## Coding Model Preference

Implementation work should use Antigravity with Claude Sonnet as the primary coding model. If Claude Sonnet is not enough for a specific issue, switch to a Google model for that task.
