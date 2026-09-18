# ResearchConnect AI — Development Roadmap

This document outlines the planned architecture and modular development roadmap for **ResearchConnect AI**. The project follows a clean, maintainable modular structure designed for a collaborative final-year project team, avoiding unnecessary distributed systems or MLOps overhead while maintaining high code quality and clear separation of concerns.

### Implementation Status:
- **Phase 1 (Foundation)**: COMPLETE (PostgreSQL + pgvector, core models, opportunity API)
- **Phase 2.1 (Ingestion Hardening)**: COMPLETE (WikiCFP source, validation, deduplication, change detection, audit tracking)
- **Phase 2.2A (Research Knowledge - OpenAlex)**: COMPLETE (OpenAlex API, research_works, researchers, research_sources, institutions)
- **Phase 2.2B (Research Knowledge - Crossref)**: COMPLETE (Crossref API, DOI canonicalization, non-destructive matching & enrichment, citation fields)
- **Phase 2.3A (Topic & Taxonomy Intelligence)**: COMPLETE (Canonical taxonomy DAG, aliases, OpenAlex/Crossref mapping, deterministic keyword extraction, multi-evidence scoring)
- **Phase 2.3B (Semantic Embeddings + pgvector)**: COMPLETE (384-dim all-MiniLM-L6-v2 embeddings, content hashing, HNSW vector indexes)
- **Phase 2.4A (Vector Retrieval Foundation)**: COMPLETE (pgvector cosine retrieval, candidate limits, metadata filtering, entity exclusion)
- **Phase 2.4B (Hybrid Search & Candidate Fusion)**: COMPLETE (PostgreSQL weighted FTS, Reciprocal Rank Fusion, dual-path candidate merging)
- **Phase 2.4C (Similar Research Retrieval)**: COMPLETE (Multi-signal similarity, topic overlap, taxonomy DAG proximity, deterministic ranking, self-exclusion)
- **Phase 2.4D (Research ↔ Opportunity Matching)**: COMPLETE (Multi-signal matching, publication type compatibility, taxonomy DAG proximity, deterministic ranking, filter propagation)
- **Phase 2.4E (Hybrid Ranking Engine)**: COMPLETE (Reusable multi-signal ranker, publication recency freshness, deadline urgency, weight validation, deterministic tie-breaking)
- **Phase 2.4F (Explainable Results)**: COMPLETE (Structured machine-readable signal attributions, qualitative summaries, strengths and limitations, deterministic zero-LLM reasoning)
- **Phase 2.4G (FastAPI Discovery Layer)**: COMPLETE (Versioned REST API, Pydantic schemas, parameter validation, error mapping, hybrid ranking & explainability integration)
- **Phase 2.4H (Testing, Benchmarking & Documentation)**: COMPLETE (IR metrics, 16-scenario benchmark dataset, Vector vs Lexical vs Hybrid evaluation, latency & concurrency profiling, discovery architecture documentation)
- **Phase 2.4 (Discovery & Intelligent Search)**: **COMPLETE** (All 8 subphases 2.4A–2.4H implemented, tested with 573 passing tests, and documented)
- **Phase 2.4+ Advancement**:
  - **Phase 2.4I (Full-Text GIN Indexing & Query Intelligence)**: COMPLETE (Stored tsvectors, GIN indexes, academic acronym expansion, 589 tests)
  - **Phase 2.4J (Ranking Hardening & Opportunity Quality Signals)**: COMPLETE (Indexing tier evaluation, predatory risk penalties, status reliability, relevance dominance, 630 tests)
  - **Phase 2.4K (Frontend Discovery Experience & Production Hardening)**: COMPLETE (React discovery UI, similar research explorer, opportunity matcher, explainability drawer, rate limiting, caching, 634 tests)
- **Phase 2.5 (Ranking & Recommendation Optimization)**: **COMPLETE** (All subphases 2.5A–2.5G implemented, tested, and empirically evaluated)
- **Phase 2.6 (Predatory & Suspicious Detection)**: **COMPLETE**
  - **Phase 2.6A (Architecture & Data Audit)**: COMPLETE
  - **Phase 2.6B (Risk Evidence Extraction & Pattern Matchers)**: COMPLETE
  - **Phase 2.6C (Deterministic Risk Scoring Engine)**: COMPLETE
  - **Phase 2.6D (Venue / Publisher Intelligence & Cross-Source Resolution)**: COMPLETE
  - **Phase 2.6E (Suspicious Pattern & Graph Signals)**: COMPLETE
  - **Phase 2.6F (Explainability & Discovery UI Integration)**: COMPLETE
  - **Phase 2.6G (Evaluation & False-Positive Hardening)**: COMPLETE
- **Phase 2.7 (Deadline Intelligence & Urgency Engine)**: **COMPLETE** (Subphases 2.7A–2.7G implemented, tested, and empirically evaluated)
- **Phase 3 (Personalized Researcher Intelligence & Recommendations)**:
  - **Phase 3.1 (Researcher Profile Foundation)**: **COMPLETE** (Canonical profile model, external identifier normalization, institution linking, profile completeness, service, REST API, Next.js UI)
  - **Phase 3.2 (Research Interest Intelligence)**: **COMPLETE** (Structured interests and expertise extraction, deterministic strength and confidence scoring, bounded recency signal, zero N+1 queries, provenance, REST API, Next.js UI)
  - **Phase 3.3 (Personal Preference Intelligence)**: **COMPLETE** (Canonical preference model, explicit preferences CRUD, activity-based inference from saved opportunities, derived expertise candidates, contradiction detection, completeness scoring, zero N+1 queries, provenance, REST API, Next.js UI)
  - **Phase 3.4 (Personalized Candidate Generation)**: **COMPLETE** (Multi-channel candidate retrieval across explicit preferences, learned topics, and author expertise, fallback guarantees, provenance tracing, REST API, Next.js UI)
  - **Phase 3.5 (Personalized Hybrid Ranking)**: **COMPLETE** (Dedicated personalization ranking layer, bounded adjustment <= 0.15, relevance dominance and damping, Phase 2.6 risk & Phase 2.7 deadline preservation, multi-key deterministic tie-breaking, R0 vs R1 ablation diagnostics, zero N+1 queries, REST API, Next.js diagnostic preview UI)
  - **Phase 3.6 (Feedback & Recommendation Learning Loop)**: **COMPLETE** (Controlled feedback loop, bounded deterministic preference/interest adjustments, exponential decay, reversible signals, REST API, Next.js feedback UI)
  - **Phase 3.7 (Recommendation History & Evaluation)**: **COMPLETE** (Reproducible recommendation snapshots, deterministic ranking versioning, offline IR evaluation metrics, data sufficiency classifications, zero N+1 queries, REST API, Next.js history & evaluation UI)
  - **Phase 3.8 (Personalization Explainability & Researcher UI)**: **COMPLETE** (Grounded recommendation explanations, signal priority hierarchy, score consistency invariants, safety dominance, historical snapshot explanation immutability, researcher personalization summary, Why this? modal, Next.js UI)
  - **Phase 3.9 (Evaluation, Ablation & Hardening)**: **COMPLETE** (Offline R0/R1/R2 IR evaluation, 10-state segmented evaluation, deterministic 6-signal ablation matrix, parameter sensitivity stability, 15-scenario adversarial safety matrix A–O, mathematical system invariants, strict X-User-ID ownership security across all 16 endpoints, 10–200 candidate performance benchmarks with zero N+1 queries, full architecture documentation)
- **Phase 4 (Research Management & Researcher Workflow)**:
  - **Phase 4.0 (Architecture & Roadmap Alignment)**: **COMPLETE** (Full repository audit, Next.js App Router baseline confirmation, canonical roadmap alignment, domain model decision criteria, invariant specification)
  - **Phase 4.1 (Opportunity Workspace)**: **COMPLETE** (Researcher-scoped workspace states: SAVED, CONSIDERING, PLANNING, APPLIED, ACCEPTED, REJECTED, ARCHIVED; deterministic state machine transitions, strict X-User-ID researcher isolation, Alembic migration 0011, REST API under /api/v1/workspace, Next.js App Router UI at /workspace, 16 unit & API tests, zero N+1 queries, backward compatibility with Phase 3.6 feedback)
  - **Phase 4.2 (Submission & Application Tracker)**: PLANNED / NOT IMPLEMENTED (Submission lifecycle: DRAFT, PREPARING, READY_TO_SUBMIT, SUBMITTED, UNDER_REVIEW, REVISION_REQUIRED, ACCEPTED, REJECTED, WITHDRAWN; target deadlines, REST API, Next.js UI)
  - **Phase 4.3 (Application History & Audit)**: PLANNED / NOT IMPLEMENTED (Immutable event logging, stage transition audit trail, personal academic productivity analytics)
  - **Phase 4.4 (Research Calendar & Deadline Planning)**: PLANNED / NOT IMPLEMENTED (Powered strictly by Phase 2.7 canonical deadlines, milestone scheduling, iCal feed export, Google Calendar integration)
  - **Phase 4.5 (Notifications & Alerts)**: PLANNED / NOT IMPLEMENTED (Canonical deadline alert triggers, deadline revision alerts, notification preferences, in-app notification center)
  - **Phase 4.6 (Research Management Dashboard)**: PLANNED / NOT IMPLEMENTED (Unified Next.js App Router command center combining deadlines, active submissions, saved opportunities, personalized recommendations)
  - **Phase 4.7 (Evaluation & Production Hardening)**: PLANNED / NOT IMPLEMENTED (E2E workflow testing, multi-user isolation verification, audit trail verification, database query performance, stress testing)

---

## 1. Data & Discovery
Focuses on acquiring, sanitizing, and maintaining accurate, fresh data on academic and research opportunities across various publication venues.

- **Conference Discovery**: Automated discovery and indexing of peer-reviewed conferences across disciplines.
- **Journal Discovery**: Identification of academic journals with verified indexing details and publication cycles.
- **CFP & Workshop Discovery**: Tracking of special calls for papers (CFPs), symposiums, and workshop deadlines.
- **Web Scraping**: Resilient data scrapers using `Requests` and `BeautifulSoup` (with `Playwright` reserved for JavaScript-heavy pages).
- **Data Cleaning**: Stripping formatting artifacts, noise, invalid HTML, and normalizing date/text formats.
- **Normalization**: Standardizing opportunity metadata (dates, topics, venue types, submission URLs) into consistent schemas.
- **Validation**: Schema-level validation and completeness checks before ingestion into the primary database.
- **Duplicate Detection**: Identifying overlapping submissions or duplicate listings across multiple feeds.
- **Change Detection**: Detecting revisions in deadlines, venue locations, or submission guidelines.
- **Data Freshness**: Routine checks and TTL management to archive expired opportunities.
- **Source Reliability**: Tracking and rating the historical accuracy and uptime of source feeds.

---

## 2. Research Intelligence
Extracts contextual understanding from user inputs (abstracts, drafts, profiles) and research domain taxonomies.

- **Research Profile**: Structured user profile capturing current domains, methodologies, publications, and interests.
- **Research Topic Extraction**: Semantic topic identification from uploaded abstracts or research summaries.
- **Abstract Analysis**: Deep parsing of manuscript drafts or abstracts to extract core themes and contributions.
- **Keyword Extraction**: Automated extraction of domain-specific keywords and phrases.
- **Domain/Sub-Domain Classification**: Hierarchical categorization of research areas (e.g., Computer Science -> NLP -> Information Retrieval).
- **Literature Discovery**: Contextual suggestions of relevant prior work and foundational literature.
- **Research Trend Analysis**: Identifying trending research topics and emerging themes across venues.
- **Research Gap Suggestions**: Identifying under-explored niches and potential intersections in chosen topics.
- **Research Roadmap**: Generating step-by-step milestones for manuscript preparation and targeted submission.

---

## 3. AI Recommendation
Provides explainable, ranked recommendations matching research profiles to appropriate venues and opportunities.

- **Semantic Recommendation**: Vector similarity search using `pgvector` and domain-tuned embedding models.
- **Conference Recommendation**: Matching manuscript topics and readiness to appropriate conference tracks.
- **Journal Recommendation**: Matching paper scope, turnaround time, and impact factor expectations to journal profiles.
- **Best Venue Recommendation**: Multi-criteria ranking identifying optimal submission targets.
- **Recommendation Ranking**: Combining semantic similarity, deadline proximity, and domain match into a unified score.
- **Personalized Recommendation**: Adapting results to individual researcher stage, past submissions, and preferences *(Phases 3.1–3.5 completed)*.
- **Opportunity Comparison**: Side-by-side comparative analysis of candidate venues (acceptance rates, indexing, deadlines).
- **Recommendation Feedback**: Capturing explicit user feedback (save, dismiss, irrelevant) to refine future rankings *(Phase 3.6 completed)*.
- **Explainable Recommendations**: Transparent rationales detailing *why* a specific venue or opportunity was recommended.

---

## 4. Trust & Quality
Ensures students and researchers avoid predatory or substandard publication venues through transparent risk analysis.

- **Predatory/Suspicious Opportunity Detection**: Heuristic and pattern-based identification of predatory conferences and journals *(Phase 2.6B completed)*.
- **Deterministic Risk Scoring**: Composite calibrated risk ratings and trust mitigation *(Phase 2.6C completed)*.
- **Publisher/Indexing Verification & Resolution**: Cross-referencing indexing claims (DOAJ, Crossref, OpenAlex) and entity resolution *(Phase 2.6D completed)*.
- **Suspicious Graph & Topology Intelligence**: Academic trust graph analysis detecting organizer/domain syndicates and identity collisions *(Phase 2.6E completed)*.
- **Risk Explainability & API/UI Integration**: Deterministic, transparent, provenance-backed trust/risk explanations with progressive disclosure across API and frontend *(Phase 2.6F completed)*.
- **Risk Model Evaluation & False-Positive Hardening**: Benchmarks and calibration against ground-truth sets *(Phase 2.6G completed)*.

---

## 5. Research Management
Empowers researchers to organize deadlines, track submissions, and manage applications seamlessly across the research lifecycle.

> [!NOTE]
> **Architectural Purpose of Phase 4**: Research Management does **NOT** replace or compete with the Opportunity Discovery, Ranking, or Recommendation engines. Rather, it builds the researcher workflow layer directly on top of the existing intelligence systems (consuming Phase 2.6 risk signals, Phase 2.7 canonical deadlines, and Phase 3 personalized profiles).

### Product Evolution Flow
```text
Opportunity Discovery (Phases 1, 2.1–2.4)
        ↓
Opportunity Intelligence: Trust & Deadlines (Phases 2.6, 2.7)
        ↓
Researcher Intelligence & Preferences (Phases 3.1–3.3)
        ↓
Personalized Recommendations (Phases 3.4–3.9)
        ↓
Research Management & Opportunity Workspace (Phase 4.1)
        ↓
Submission & Application Workflow (Phases 4.2–4.3)
        ↓
Research Calendar & Deadline Planning (Phase 4.4)
        ↓
Notifications & Proactive Alerts (Phase 4.5)
        ↓
Unified Research Management Dashboard (Phase 4.6)
```

### Planned Subphases (4.0–4.7)
- **Phase 4.0 (Architecture & Roadmap Alignment)**: *(Current / In Progress)* Complete repository audit, Next.js App Router baseline confirmation, canonical roadmap alignment, domain model decision criteria, and invariant specifications.
- **Phase 4.1 (Opportunity Workspace)**: *(Planned)* Multi-stage researcher-scoped opportunity tracking (`SAVED`, `CONSIDERING`, `PLANNING`, `APPLIED`, `ACCEPTED`, `REJECTED`, `ARCHIVED`), custom notes, priority tags, REST API, Next.js Workspace UI.
- **Phase 4.2 (Submission & Application Tracker)**: *(Planned)* Dedicated `ResearchSubmission` model tracking paper manuscripts through the full submission lifecycle (`DRAFT`, `PREPARING`, `READY_TO_SUBMIT`, `SUBMITTED`, `UNDER_REVIEW`, `REVISION_REQUIRED`, `ACCEPTED`, `REJECTED`, `WITHDRAWN`), target deadlines, REST API, Next.js Tracker UI.
- **Phase 4.3 (Application History & Audit)**: *(Planned)* Immutable event-driven audit logging for all submission transitions, milestone completions, and outcomes for personal reporting and analytics.
- **Phase 4.4 (Research Calendar & Deadline Planning)**: *(Planned)* Timeline visualizer powered strictly by Phase 2.7 canonical deadline views, preparation milestones, iCal export feed, and Google Calendar integration.
- **Phase 4.5 (Notifications & Alerts)**: *(Planned)* Canonical deadline alert triggers, deadline revision notifications, and user notification preference controls.
- **Phase 4.6 (Research Management Dashboard)**: *(Planned)* Unified Next.js App Router command center aggregating upcoming deadlines, active submissions, saved opportunities, and personalized recommendations.
- **Phase 4.7 (Evaluation & Production Hardening)**: *(Planned)* Multi-user isolation verification, audit trail verification, database query performance, stress testing, and production readiness audit.

---

## 6. Community
Facilitates institutional and cross-disciplinary academic collaboration within the platform.

- **Faculty Opportunities**: Listings posted by university faculty for open research slots.
- **Research Projects**: Collaborative multi-student or inter-departmental project postings.
- **Research Internships**: Curated industry and academic research internship openings.
- **Research Assistant Opportunities**: Formal RA openings for undergraduate and postgraduate students.

---

## 7. Platform
Core system infrastructure, user interfaces, access control, and deployment operations.

- **Student Portal**: Tailored view for undergraduate and postgraduate student discovery, tracking, and profile matching.
- **Faculty Portal**: Administrative tools for faculty to post opportunities and review applicant matches.
- **Admin Portal**: System moderation, manual data review, feed management, and user governance.
- **Admin Verification**: Verification workflows for faculty credentials and institutional affiliations.
- **Analytics**: Usage insights, opportunity trends, search metrics, and match effectiveness.
- **Authentication**: Secure user authentication (JWT/OAuth) with password hashing.
- **Authorization**: Role-Based Access Control (RBAC) separating Student, Faculty, and Admin permissions.
- **Security**: Strict input validation, CORS protection, rate limiting, and secure environment configuration.
- **Logging**: Structured application logging for debugging and audit trails.
- **Deployment**: Lightweight Docker configuration for production containerization on standard cloud/VPS hosts.

---

## 8. Evaluation
Rigorous testing and quantitative validation of AI, scraping, and ranking systems.

- **Recommendation Evaluation**: Offline and online metrics (Precision@K, Recall@K, MRR, NDCG) for opportunity ranking *(Phase 3.7 completed)*.
- **Risk Model Evaluation**: Classification accuracy, precision, and recall against known predatory venue benchmarks.
- **Data Quality Evaluation**: Validation rates, duplicate reduction efficiency, and parsing completeness metrics.
