# ResearchConnect AI — Documentation

Setup, running the stack and configuration are in the [project README](../README.md). This page
lists everything under `docs/`.

## Start here

| Document | What it covers |
|---|---|
| [Development Roadmap](architecture/project-roadmap.md) | What each phase delivered, current status, and what remains |
| [Methodology](METHODOLOGY.md) ([Word export](METHODOLOGY.docx)) | Research methodology, design principles, known limitations |
| [PostgreSQL and pgvector](database/postgres-pgvector.md) | Database setup, migrations, tables, search indexes, backup |
| [Phase 6.6 — End-to-End Verification](../PHASE_6_6_E2E_VERIFICATION_REPORT.md) | The running platform verified as one system: API, browser, scheduler and restart suites, results, findings ([how to run](../e2e/README.md)) |
| [Phase 6.5 — Database and Migration Startup](architecture/phase6-5-database-startup.md) | Fresh-database startup order, readiness endpoint, production schema gate, migration lock and verification |
| [Phase 6.4 — Production Configuration](architecture/phase6-4-production-configuration.md) | Every setting, what production refuses, deployment checklist, secrets policy |
| [Phase 6.3 — Background Scheduler](architecture/phase6-3-scheduler.md) | The five maintenance jobs, locking, timeouts, how to enable it |

## Reading the phase documents

Each phase document records the design as it was built in that phase; later phases may have
extended it (the roadmap says where). Examples that identify the caller with an `X-User-ID`
header predate Phase 6. Since then the API authenticates with `Authorization: Bearer <token>`
from `/api/v1/auth/login`, and `X-User-ID` is accepted only in local development with
`AUTH_DEV_IDENTITY_ENABLED=true`.

## Data sources and ingestion

| Document | Phase |
|---|---|
| [Data Ingestion & Scraper Architecture](scraping/architecture.md) | 1–2.1 |
| [OpenAlex Integration](research-data/openalex.md) | 2.2A |
| [Crossref Integration](architecture/phase2-2b-crossref.md) | 2.2B |
| [Topic & Taxonomy Intelligence](architecture/phase2-3a-topic-intelligence.md) | 2.3A |
| [Semantic Embeddings + pgvector](architecture/phase2-3b-semantic-embeddings.md) | 2.3B |

## Discovery, search and ranking (Phase 2.4–2.5)

| Document | Phase |
|---|---|
| [Discovery & Intelligent Search Architecture](architecture/phase2-4-discovery-architecture.md) | 2.4 overview |
| [Vector Retrieval Foundation](architecture/phase2-4a-vector-retrieval.md) | 2.4A |
| [Hybrid Search & Candidate Fusion](architecture/phase2-4b-hybrid-search.md) | 2.4B |
| [Similar Research Retrieval](architecture/phase2-4c-similar-research.md) | 2.4C |
| [Research ↔ Opportunity Matching](architecture/phase2-4d-research-opportunity-matching.md) | 2.4D |
| [Hybrid Ranking Engine](architecture/phase2-4e-hybrid-ranking.md) | 2.4E |
| [Explainable Results](architecture/phase2-4f-explainable-results.md) | 2.4F |
| [FastAPI Discovery Layer](architecture/phase2-4g-fastapi-discovery-layer.md) | 2.4G |
| [Testing, Benchmarking & Evaluation](architecture/phase2-4h-testing-benchmarking.md) | 2.4H |
| [Full-Text Indexing & Query Intelligence](architecture/phase2-4i-fts-query-intelligence.md) | 2.4I |
| [Ranking Hardening & Quality Signals](architecture/phase2-4j-ranking-hardening.md) | 2.4J |
| [Frontend Discovery Experience](architecture/phase2-4k-frontend-hardening.md) | 2.4K |
| [Taxonomy Expansion & Venue Intelligence](architecture/phase2-4l-taxonomy-venue-intelligence.md) | 2.4L |
| [Empirical Evaluation & Reranking](architecture/phase2-4m-empirical-evaluation-reranking.md) | 2.4M |
| [Recommendation Ranking & Feature Engineering](architecture/phase2-5-ranking-architecture.md) | 2.5 |
| [Academic Relevance Annotation Guidelines](evaluation/academic-relevance-annotation-guidelines.md) | Evaluation |

## Trust and deadline intelligence (Phase 2.6–2.7)

| Document | Phase |
|---|---|
| [Venue & Publisher Intelligence](architecture/phase2-6d-venue-publisher-intelligence.md) | 2.6D |
| [Suspicious Pattern & Graph Intelligence](architecture/phase2-6e-suspicious-pattern-graph-intelligence.md) | 2.6E |
| [Risk Explainability, API & UI](architecture/phase2-6f-risk-explainability-api-ui.md) | 2.6F |
| [Risk Evaluation & False-Positive Hardening](architecture/phase2-6g-risk-evaluation-false-positive-hardening.md) | 2.6G |
| [Deadline Evidence Extraction](architecture/phase2-7b-deadline-evidence-extraction.md) | 2.7B |
| [Date & Timezone Normalization](architecture/phase2-7c-date-timezone-normalization.md) | 2.7C |
| [Deadline Intelligence & Urgency](architecture/phase2-7d-deadline-intelligence-urgency.md) | 2.7D |
| [Conflicts, Extensions & Multiple Deadlines](architecture/phase2-7e-conflict-extension-multi-deadline.md) | 2.7E |
| [Deadline Explainability, API & UI](architecture/phase2-7f-deadline-explainability-api-ui.md) | 2.7F |
| [Deadline Evaluation & Hardening](architecture/phase2-7g-deadline-evaluation-hardening.md) | 2.7G |

## Researcher intelligence (Phase 3)

| Document | Phase |
|---|---|
| [Researcher Profile Foundation](architecture/phase3-1-researcher-profile-foundation.md) | 3.1 |
| [Interest & Expertise Intelligence](architecture/phase3-2-researcher-interest-expertise.md) | 3.2 |
| [Personal Preference Intelligence](architecture/phase3-3-personal-preference-intelligence.md) | 3.3 |
| [Personalized Candidate Generation](architecture/phase3-4-personalized-candidate-generation.md) | 3.4 |
| [Personalization Ranking](architecture/phase3-5-personalization-ranking.md) | 3.5 |
| [Feedback & Recommendation Learning](architecture/phase3-6-feedback-learning.md) | 3.6 |
| [Recommendation History & Evaluation](architecture/phase3-7-recommendation-history-evaluation.md) | 3.7 |
| [Personalization Explainability & UI](architecture/phase3-8-personalization-explainability.md) | 3.8 |
| [Evaluation, Ablation & Hardening](architecture/phase3-9-evaluation-hardening.md) | 3.9 |

## Research management (Phase 4)

| Document | Phase |
|---|---|
| [Opportunity Workspace](architecture/phase4-1-opportunity-workspace.md) | 4.1 |
| [Submission Management & Tracking](architecture/phase4-2-research-submission-management.md) | 4.2 |
| [Submission Workflow & Documents](architecture/phase4-3-research-submission-workflow-document-management.md) | 4.3 |
| [Research Calendar & iCal Export](architecture/phase4-4-research-calendar-visual-deadline-planning-ical.md) | 4.4 |
| [Deadline Reminders & Notifications](architecture/phase4-5-deadline-reminders-notifications.md) | 4.5 |
| [Collaborative Research Management](architecture/phase4-6-collaborative-research-management.md) | 4.6 |
| [Research Intelligence Integration](architecture/phase4-7-research-intelligence-integration-hardening.md) | 4.7 |

## Personalization and collaboration (Phase 5)

| Document | Phase |
|---|---|
| [Researcher Preferences Foundation](architecture/phase5-1-researcher-preferences-foundation.md) | 5.1 |
| [Explicit Preference Interpretation](architecture/phase5-2-explicit-preference-interpretation.md) | 5.2 |
| [Personalization-Aware Scoring](architecture/phase5-3-personalization-aware-scoring.md) | 5.3 |
| [Feedback & Interaction Signals](architecture/phase5-4-researcher-feedback-interactions.md) | 5.4 |
| [Adaptive Preference Signals](architecture/phase5-5-adaptive-preference-signals.md) | 5.5 |
| [Personalization Calibration](architecture/phase5-6-personalization-calibration.md) | 5.6 |
| [Personalization Quality & Contextual Adaptation](architecture/phase5-7-personalization-quality.md) | 5.7 |
| [Personalization Governance & Drift Detection](architecture/phase5-8-personalization-governance.md) | 5.8 |
| [Transparency, Controls & Explanations](architecture/phase5-9-personalization-transparency-controls.md) | 5.9 |

Phases 5.10 to 5.12 (research postings, applications, peer discovery) and 6.1 to 6.2
(containers, browser sign-in) are documented in the roadmap and the project README.
