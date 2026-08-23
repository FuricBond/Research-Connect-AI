# Initial Architecture

ResearchConnect AI starts as a normal monorepo application.

## Application Shape

```text
React frontend
      |
FastAPI backend
      |
PostgreSQL + pgvector
```

Scraping and AI/ML code live in the same repository so the project is easy to understand and evolve during early implementation.

## Included Modules

- `frontend`: user interface for search, recommendations, saved opportunities, and profile matching
- `backend`: API, database access, auth later, opportunity services, and AI orchestration
- `scrapers`: collectors and parsers for conferences, journals, CFPs, workshops, and other opportunities
- `ml`: embeddings, topic analysis, and recommendation logic

## Explicitly Out Of Scope For Now

- Kubernetes
- Microservices
- Airflow
- MLflow
- Distributed queues
- Separate model-serving infrastructure

These can be introduced later only if the project genuinely needs them.
