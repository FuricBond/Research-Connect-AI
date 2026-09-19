# ResearchConnect AI — Development Roadmap & System Architecture

This document provides the authoritative, comprehensive architectural roadmap and implementation log for **ResearchConnect AI**. The platform is built with a modular, clean-architecture design suited for high-impact research discovery, academic intelligence, and lifecycle management—avoiding speculative distributed systems or MLOps overhead while maintaining uncompromising code quality, deterministic mathematical guarantees, and strict separation of concerns.

---

## Executive Implementation Status

| Phase | Subsystem / Focus | Status | Key Deliverables & Capabilities | Verification |
| :--- | :--- | :---: | :--- | :---: |
| **Phase 1** | Foundation & Core Storage | **COMPLETE** | PostgreSQL + pgvector, SQLAlchemy 2.0, Alembic migrations, Opportunity & User models, REST API CRUD, Docker Compose | Verified |
| **Phase 2.1** | Ingestion Hardening | **COMPLETE** | WikiCFP scrapers, schema validation, deduplication, change detection, audit tracking, error recovery | Verified |
| **Phase 2.2** | Academic Knowledge Integration | **COMPLETE** | OpenAlex & Crossref ingestion, relational entities (`research_works`, `researchers`, `institutions`), DOI canonicalization | Verified |
| **Phase 2.3** | Taxonomy & Semantic Embeddings | **COMPLETE** | 36-node canonical CS taxonomy DAG, deterministic keyword extraction, 384-dim `all-MiniLM-L6-v2` embeddings, HNSW index | Verified |
| **Phase 2.4** | Discovery & Intelligent Search | **COMPLETE** | Hybrid FTS + pgvector HNSW retrieval, Reciprocal Rank Fusion ($k=60$), similar research, match engine, zero-LLM explainer | 634 Tests |
| **Phase 2.5** | Recommendation Ranking & Features | **COMPLETE** | Academic feature extraction, $\ge 85\%$ relevance dominance, mode presets, diversity/novelty (MMR/HHI), 108-query benchmark | 714 Tests |
| **Phase 2.6** | Trust & Predatory Detection | **COMPLETE** | Heuristic evidence extractors, deterministic 0–100 risk scoring, publisher verification (DOAJ/Crossref), academic trust graph | 100% Reputable Precision |
| **Phase 2.7** | Deadline Intelligence & Urgency | **COMPLETE** | Multi-milestone taxonomy, UTC/AoE normalization, authority hierarchy conflict resolution, revision tracking, urgency decay | 20 Invariants Passed |
| **Phase 3** | Personalized Researcher Intelligence | **COMPLETE** | Researcher profile foundation, interest/expertise extraction, preference inference, personalized candidate gen, feedback loop | 845 Tests |
| **Phase 4.0** | Workflow Architecture & Alignment | **COMPLETE** | Comprehensive codebase audit, Next.js App Router baseline, domain boundary specifications, lifecycle state machines | Verified |
| **Phase 4.1** | Opportunity Workspace | **COMPLETE** | 7 workspace lifecycle states, notes/tags, X-User-ID tenant isolation, Alembic migration 0011, `/workspace` UI | 16 Tests |
| **Phase 4.2** | Submission & Application Tracker | **COMPLETE** | Canonical `ResearchSubmissionModel` (1:N), 7-state lifecycle machine, Phase 2.7 deadline grounding, migration 0012, visual stepper UI | 20 Tests |
| **Phase 4.3** | Document Workflow & Readiness | **COMPLETE** | Document lifecycle & categories, immutable SHA-256 versioning, Submission Readiness Engine, audit trails, migration 0013, doc console UI | 26 Tests |
| **Phase 4.4** | Research Calendar & iCal Export | **COMPLETE** | Calendar & event models, Phase 2.7 canonical deadline projection, user planning events, deterministic RFC 5545 `.ics` export, migration 0014, `/calendar` UI | 28 Tests |
| **Phase 4.5** | Deadline Reminders & Alerts | **COMPLETE** | Preference & reminder models, in-app & email providers, SHA-256 deduplication, zero N+1 scheduler (0.73ms/user), migration 0015, `/notifications` UI | 39 Tests |
| **Phase 4.6** | Collaborative Research Management | **COMPLETE** | Multi-user workspaces, RBAC (`OWNER`/`EDITOR`/`CONTRIBUTOR`/`VIEWER`), secure invitations, task tracking, activity trail, migration 0016 | 56 Tests |
| **Phase 4.7** | Research Intelligence Integration | **COMPLETE** | Authoritative unified integration service connecting Phases 2, 3, 4; signal provenance, canonical identity resolution, 6-tier explainability | 14 Tests |
| **Phase 5.1** | Researcher Preferences Foundation | **COMPLETE** | Explicit preference foundation, 3-state semantics (Preferred/Neutral/Excluded), extended categories, bulk sync, Next.js `/researcher/preferences` UI, migration 0017 | 14 Tests / 100% Regr |
| **Phase 5.2** | Community & Collaboration Features | **PLANNED** | Faculty research slots, collaborative project postings, research internships, RA openings, peer discovery | Planned |
| **Phase 6** | Platform Infrastructure & Governance | **IN PROGRESS** | Role-Based Access Control (Student/Faculty/Admin), JWT/OAuth, rate limiting, structured logging, Docker production specs | Continuous |
| **Phase 7** | Comprehensive System Evaluation | **CONTINUOUS** | Empirical IR benchmarks (NDCG@10, MAP, MRR), risk false-positive benchmarks, deadline normalization stress tests | 1,008+ Passing Tests |

---

## Detailed Implementation Directory

### Phase 1: Foundation & Core Storage Architecture
- **Scope & Objectives**: Establish the relational and vector database foundation, containerized local development environment, core data models, Alembic migration pipeline, and baseline REST endpoints.
- **Data Models & Migrations**:
  - `OpportunityModel`: Core academic venue entity (conferences, journals, workshops) with title, acronym, venue type, submission URL, deadlines, location, and metadata JSON.
  - `UserModel`: Base user account entity with role support (`STUDENT`, `FACULTY`, `ADMIN`).
  - Migration `0001_initial`: Initialized PostgreSQL schema with UUID primary keys, timestamp mixins, and indexing.
- **Infrastructure & Services**:
  - PostgreSQL 16 with native `pgvector` extension enabled via Docker Compose.
  - SQLAlchemy 2.0 declarative base with async-compatible session management and connection pooling.
  - Initial FastAPI application with health check and CRUD endpoints for opportunities under `/api/v1/opportunities`.
- **Verification**: Database migrations applied cleanly; CRUD unit tests verified entity persistence and schema serialization.

---

### Phase 2.1: Ingestion Hardening & Pipeline Resilience
- **Scope & Objectives**: Build resilient scrapers for academic calls for papers (WikiCFP), enforcing strict schema validation, deduplication, change detection, and audit logging.
- **Architecture & Scrapers**:
  - `scrapers/wikicfp`: Modular scraper targeting WikiCFP categories with rate limiting, retries, and backoff.
  - `DataCleaner`: HTML entity stripping, whitespace normalization, and encoding fixes.
  - `SchemaValidator`: Pydantic-based validation rejecting incomplete or malformed opportunities before database insertion.
  - `Deduplicator`: Content-hash deduplication across acronyms, titles, and submission URLs.
  - `ChangeDetector`: Compares incoming data with existing records to flag deadline modifications or venue updates.
- **Verification**: 389 scraper unit and integration tests passing; zero unhandled network exceptions on malformed HTML fixtures.

---

### Phase 2.2: Academic Knowledge Integration (OpenAlex & Crossref)
- **Phase 2.2A (OpenAlex Ingestion)**:
  - Ingested rich bibliometric data from OpenAlex API.
  - Introduced relational models: `ResearchWorkModel`, `ResearcherModel`, `ResearchSourceModel`, and `InstitutionModel`.
  - Stored author affiliations, concept tags, citation counts, publication dates, and Open Access statuses.
- **Phase 2.2B (Crossref Ingestion & Canonicalization)**:
  - Ingested publisher-authoritative metadata via Crossref REST API.
  - Non-destructive record enrichment: unified DOI canonicalization (`https://doi.org/...`), funder metadata, license tracking, and citation counts.
  - Established cross-source entity linking between OpenAlex concepts and Crossref publication venues.
- **Verification**: Verified zero data loss during multi-source reconciliation; idempotency verified across re-ingestion passes.

---

### Phase 2.3: Topic Taxonomy & Semantic Embeddings
- **Phase 2.3A (Canonical Topic & Taxonomy Intelligence)**:
  - Designed a 36-node canonical Computer Science taxonomy Directed Acyclic Graph (DAG) covering AI, Systems, Security, Theory, HCI, and Data Engineering.
  - Implemented ancestor/descendant traversal, lowest common ancestor (LCA) calculations, and cycle detection.
  - Mapped OpenAlex/Crossref concepts and aliases to canonical taxonomy nodes using multi-evidence scoring and deterministic keyword extraction.
- **Phase 2.3B (Semantic Embeddings with pgvector)**:
  - Integrated local 384-dimensional dense embedding model (`sentence-transformers/all-MiniLM-L6-v2`).
  - Implemented deterministic content hashing (`SHA-256`) to ensure incremental, idempotent embedding updates without redundant re-computation.
  - Alembic migration `0006_phase2_3b`: Added `Vector(384)` columns and created HNSW indexes (`m=16`, `ef_construction=64`) for cosine distance retrieval (`<=>`).
- **Verification**: Embedding extraction verified; HNSW index creation confirmed in PostgreSQL; sub-millisecond nearest-neighbor lookups verified.

---

### Phase 2.4: Discovery & Intelligent Search Subsystem
- **Phase 2.4A (Vector Retrieval Foundation)**: `VectorRepository` with pgvector HNSW cosine distance search, candidate limits, metadata filtering, and entity exclusion.
- **Phase 2.4B (Hybrid Search & Candidate Fusion)**: PostgreSQL weighted Full-Text Search (`ts_rank_cd`) combined with vector retrieval via Reciprocal Rank Fusion (RRF, $k=60$).
- **Phase 2.4C (Similar Research Retrieval)**: `SimilarResearchService` calculating dense semantic similarity, exact topic overlap, taxonomy DAG proximity, and source work self-exclusion.
- **Phase 2.4D (Research ↔ Opportunity Matching)**: `ResearchOpportunityMatchingService` evaluating research paper abstracts against open calls, enforcing publication type compatibility matrices (e.g. `article` $\to$ `JOURNAL`) and 90-day linear deadline urgency.
- **Phase 2.4E (Hybrid Ranking Engine)**: Reusable `HybridRanker` supporting `GENERAL`, `RESEARCH_SIMILARITY`, and `RESEARCH_OPPORTUNITY` modes with exponential freshness decay and deterministic 15-key tie-breaking.
- **Phase 2.4F (Explainable Results)**: Deterministic, zero-LLM `ResultExplainer` producing machine-readable feature attributions, qualitative summaries, and trade-off highlights ($100\%$ score-weight mathematical alignment).
- **Phase 2.4G (FastAPI Discovery Layer)**: REST endpoints under `/api/v1/discovery` for unified research search, similar paper discovery, and opportunity matching with Pydantic validation.
- **Phase 2.4H (Testing & Benchmarking)**: 16-scenario IR benchmark dataset evaluating NDCG, MAP, and MRR across Vector, Lexical, and Hybrid retrieval paths; latency profiling under concurrency.
- **Phase 2.4I (Full-Text GIN Indexing & Query Intelligence)**: Stored `tsvector` columns with PostgreSQL GIN indexes and academic acronym expansion (e.g., "NLP" $\to$ "Natural Language Processing").
- **Phase 2.4J (Ranking Hardening & Opportunity Quality Signals)**: Indexing tier evaluation, predatory risk penalties, venue status reliability, and mathematical relevance dominance.
- **Phase 2.4K (Frontend Discovery Experience & Hardening)**: React discovery interface with search bar, similar research explorer, opportunity matcher, explainability drawer, and API rate-limiting/caching.
- **Verification**: 634 passing tests across discovery subphases.

---

### Phase 2.5: Recommendation Ranking & Feature Engineering
- **Phase 2.5A (Architecture & Baseline Reconnaissance)**: Pipeline audit, baseline verification, and zero-regression gate.
- **Phase 2.5B (Feature Extraction & Normalization)**: `AcademicFeatureExtractor` producing normalized $[0.0, 1.0]$ canonical features:
  - `citation_impact`: Log-scaled citations normalized to 10,000 threshold.
  - `author_prominence`: Maximum author citation prominence log-scaled to 50,000.
  - `author_position`: Discrete weights for corresponding (1.0), first (0.9), last (0.8), and middle (0.5) authors.
  - `institution_prestige`: Maximum institutional citation footprint log-scaled to 500,000.
  - `venue_prestige`: Venue citation footprint plus DOAJ indexing bonus (+0.10).
  - `open_access_tier`: Tiered weighting (gold: 1.0, hybrid: 0.85, green: 0.70, bronze: 0.55, closed: 0.20).
- **Phase 2.5C (Deterministic Recommendation Ranker & Mode Presets)**: Integrated features into `HybridRanker`; enforced strict $\ge 85\%$ relevance dominance constraint to prevent prestige bias from hijacking relevance; 15-key deterministic tie-breaker.
- **Phase 2.5D (Academic Quality & Venue Signals Integration)**: Graph entity traversal connecting works to authors, institutions, and verified venue indexing sources.
- **Phase 2.5E (Diversity & Novelty Mechanics)**: Deterministic list-aware reranker applying Maximal Marginal Relevance (MMR), author/venue/institution penalty damping, and Herfindahl-Hirschman Index (HHI) concentration control.
- **Phase 2.5F (Explainability Layer Expansion)**: Mathematical explainability engine detailing secondary feature attributions and trade-offs without external LLM calls.
- **Phase 2.5G (Empirical Evaluation & Benchmark Hardening)**: 108-query benchmark suite measuring NDCG@5, MAP, and MRR; full 6-signal ablation study and cross-disciplinary sensitivity analysis.
- **Verification**: 714 passing tests in the full suite; verified 0.0% ranking divergence across platforms.

---

### Phase 2.6: Trust, Safety & Predatory Detection Subsystem
- **Phase 2.6A (Architecture & Data Audit)**: Predatory risk taxonomy, risk feature schemas, baseline criteria, and data source audit.
- **Phase 2.6B (Risk Evidence Extraction & Pattern Matchers)**: Heuristic pattern matchers detecting predatory payment channels (Western Union, MoneyGram), fake impact factors, unrealistic review turnarounds (<48 hours), hijacked domains, and aggressive solicitation keywords.
- **Phase 2.6C (Deterministic Risk Scoring Engine)**: Composite calibrated 0–100 risk score with categorical tiers (`VERY_LOW`, `LOW`, `MODERATE`, `HIGH`, `CRITICAL`) and mathematical invariant bounds.
- **Phase 2.6D (Venue / Publisher Intelligence & Cross-Source Resolution)**: Entity resolution cross-referencing DOAJ indexing, Crossref member status, and OpenAlex sources; ISSN/publisher normalization.
- **Phase 2.6E (Suspicious Pattern & Graph Signals)**: Academic trust graph detecting organizer/domain syndicates, contact email/phone collisions, shell conferences, and co-located predatory venues.
- **Phase 2.6F (Risk Explainability & Discovery UI Integration)**: Transparent risk badges, warning banners, and progressive disclosure drawers integrated into `ExplainabilityDrawer.tsx`.
- **Phase 2.6G (Empirical Evaluation & False-Positive Hardening)**: 108-fixture curated risk evaluation dataset across 4 strata; achieved $100\%$ precision on reputable venues and $0\%$ false-positive rate on high-tier venues across 20 safety invariants.
- **Verification**: All 21 risk evaluation tests passing; zero false positives on reputable academic venues.

---

### Phase 2.7: Deadline Intelligence & Urgency Engine
- **Phase 2.7A (Architecture & Deadline Taxonomy)**: Multi-milestone taxonomy supporting `ABSTRACT`, `SUBMISSION`, `NOTIFICATION`, `CAMERA_READY`, `REGISTRATION`, `EVENT_START`, and `EVENT_END`; temporal states (`UPCOMING`, `DUE_TODAY`, `EXPIRED`, `MISSING`, `TBD`).
- **Phase 2.7B (Multi-Evidence Deadline Extraction)**: `DeadlineEvidenceExtractor` extracting structured temporal markers and dates from unstructured CFP text with confidence scoring.
- **Phase 2.7C (Date & Timezone Normalization)**: `DeadlineNormalizer` enforcing strict UTC normalization, Anywhere on Earth (AoE, UTC-12) semantics, explicit timezone offsets, and date-only 23:59:59 end-of-day handling.
- **Phase 2.7D (Deadline Urgency Engine)**: `UrgencyEngine` implementing non-linear exponential and sigmoid decay; urgency tiers (`CRITICAL`, `URGENT`, `APPROACHING`, `NORMAL`, `RELAXED`); preserves Phase 2.5 0.05 ranking weight compatibility.
- **Phase 2.7E (Multi-Source Conflict Resolution & Revision Tracking)**: `DeadlineConflictResolver` with canonical source hierarchy (`OFFICIAL_WEBSITE` > `CFP_SERVICE` > `AGGREGATOR`); equal-authority conflict preservation (`SOURCE_CONFLICT`); revision history tracking extensions (`EXTENDED`) and preponements (`MOVED_EARLIER`).
- **Phase 2.7F (Deadline Explainability & Discovery UI Integration)**: `DeadlineExplainabilityService` producing structured timeline badges, countdown timers, and provenance data integrated into `ExplainabilityDrawer.tsx`.
- **Phase 2.7G (Empirical Evaluation & Hardening)**: Rigorous verification across 20 mathematical invariants; sub-millisecond execution ($0.41\text{ ms}$ per candidate); zero per-candidate database queries; complete orthogonality with Phase 2.5 ranking and Phase 2.6 risk scoring.
- **Verification**: All 20 invariants verified; zero regression across full test suite.

---

### Phase 3: Personalized Researcher Intelligence & Recommendations
- **Phase 3.1 (Researcher Profile Foundation)**: Canonical `ResearcherProfileModel`, external identifier normalization (ORCID, Google Scholar, Semantic Scholar), institution affiliation linking, profile completeness scoring ($0.0$–$1.0$), CRUD service, REST API, and Next.js UI.
- **Phase 3.2 (Research Interest Intelligence)**: Structured interests and expertise extraction from past works, deterministic strength ($0.0$–$1.0$) and confidence scoring, bounded recency signal, zero N+1 queries, provenance tracking, REST API, and Next.js UI.
- **Phase 3.3 (Personal Preference Intelligence)**: Canonical `ResearcherPreferenceModel`, explicit preference CRUD (topics, venue types, open access, deadline windows), activity-based inference from saved opportunities, contradiction detection, completeness scoring, zero N+1 queries, REST API, and Next.js UI.
- **Phase 3.4 (Personalized Candidate Generation)**: Multi-channel candidate retrieval across explicit preferences, learned topics, and author expertise; fallback guarantees; provenance tracing; strict exclusion of Phase 2.7 `EXPIRED` opportunities and preservation of Phase 2.6 risk flags; REST API and Next.js UI.
- **Phase 3.5 (Personalized Hybrid Ranking)**: Dedicated personalization ranking layer with bounded adjustment ($\le 0.15$), relevance dominance and damping, Phase 2.6 risk and Phase 2.7 deadline preservation, multi-key deterministic tie-breaking, R0 vs R1 ablation diagnostics, REST API, and Next.js diagnostic preview UI.
- **Phase 3.6 (Feedback & Recommendation Learning Loop)**: Controlled feedback loop capturing user interactions (`SAVE`, `DISMISS`, `CLICK`), bounded deterministic preference/interest adjustments, exponential decay, reversible signals, REST API, and Next.js feedback UI.
- **Phase 3.7 (Recommendation History & Evaluation)**: `RecommendationSnapshotModel` capturing reproducible recommendation snapshots, deterministic ranking versioning, offline IR evaluation metrics (NDCG@K, MAP, MRR), data sufficiency classifications, REST API, and Next.js history & evaluation UI.
- **Phase 3.8 (Personalization Explainability & Researcher UI)**: Grounded recommendation explanations, 8-level signal priority hierarchy, score consistency invariants, safety dominance, historical snapshot explanation immutability, researcher personalization summary, "Why this?" modal, and Next.js UI.
- **Phase 3.9 (Evaluation, Ablation & Hardening)**: Offline R0/R1/R2 IR evaluation, 10-state segmented evaluation, deterministic 6-signal ablation matrix, parameter sensitivity stability, 15-scenario adversarial safety matrix (Scenarios A–O), mathematical system invariants, strict `X-User-ID` ownership security across all 16 endpoints, 10–200 candidate performance benchmarks with zero N+1 queries.
- **Verification**: 845 passing tests across Phase 3 subsystems.

---

### Phase 4: Research Management & Researcher Workflow
- **Phase 4.0 (Architecture & Roadmap Alignment)**:
  - Comprehensive repository audit confirming Next.js App Router baseline and domain boundaries.
  - Canonical roadmap alignment establishing that Research Management consumes—rather than duplicates or competes with—Phase 2.6 risk, Phase 2.7 deadlines, and Phase 3 personalization.
  - Invariant specifications preventing state machine bypass, date manipulation, or tenant leakage.
- **Phase 4.1 (Opportunity Workspace)**:
  - `SavedOpportunityModel` supporting 7 researcher-scoped lifecycle states: `SAVED`, `CONSIDERING`, `PLANNING`, `APPLIED`, `ACCEPTED`, `REJECTED`, and `ARCHIVED`.
  - Deterministic state machine transitions, custom notes, priority tags, and strict `X-User-ID` researcher isolation.
  - Alembic migration `0011_phase4_1_workspace`.
  - REST API under `/api/v1/workspace` and Next.js App Router UI at `/workspace`.
  - 16 dedicated unit and API tests; zero N+1 queries; backward compatibility with Phase 3.6 feedback loop.
- **Phase 4.2 (Submission & Application Tracker)**:
  - Canonical `ResearchSubmissionModel` with a 1:N relationship to `SavedOpportunityModel`.
  - Deterministic 7-state submission lifecycle: `DRAFT` $\to$ `READY` $\to$ `SUBMITTED` $\to$ `UNDER_REVIEW` $\to$ `ACCEPTED` / `REJECTED`, with terminal `WITHDRAWN` state.
  - Automatic workspace status synchronization rules (e.g. transitioning submission to `SUBMITTED` advances workspace item to `APPLIED`).
  - Read-only grounding in Phase 2.7 canonical deadline intelligence (days remaining, AoE status, extension status, urgency tier).
  - Alembic migration `0012_phase4_2_submissions`.
  - REST API under `/api/v1/submissions` and `/api/v1/workspace/{id}/submissions`.
  - Next.js App Router UI at `/workspace/[id]/submission` with visual pipeline stepper and external tracking links.
  - 20 dedicated unit and API tests.
- **Phase 4.3 (Research Submission Workflow & Document Management)**:
  - `SubmissionDocumentModel`, `SubmissionDocumentVersionModel`, and `SubmissionEventModel`.
  - Deterministic manuscript document lifecycle: `REQUIRED`, `MISSING`, `DRAFT`, `READY`, `REJECTED`, and `ARCHIVED`.
  - Strongly-typed artifact categories: `MANUSCRIPT`, `COVER_LETTER`, `SUPPLEMENTARY`, `ETHICS_STATEMENT`, `SOURCE_CODE`, and `DATA_AVAILABILITY`.
  - Immutable version snapshotting tracking content hash (`SHA-256`), byte size, and upload metadata.
  - Deterministic `SubmissionReadinessEngine` gating submission transition to `READY` until all required documents exist in `READY` status.
  - Comprehensive chronological audit trail logging of all stage transitions, document uploads, and status changes.
  - Alembic migration `0013_phase4_3_documents`.
  - REST API under `/api/v1/submissions/{id}/documents`, `/readiness`, and `/audit-trail`.
  - Next.js App Router document manager and readiness console at `/workspace/[id]/submission`.
  - 26 dedicated unit and API tests.
- **Phase 4.4 (Research Calendar & Visual Deadline Planning)**:
  - `ResearchCalendarModel` and `ResearchCalendarEventModel`.
  - Researcher-owned planning calendar projection layer consuming Phase 2.7 canonical deadline intelligence.
  - Deterministic milestone isolation for all 7 Phase 2.7 milestone types (`ABSTRACT`, `SUBMISSION`, `NOTIFICATION`, etc.).
  - Support for user-created planning events (`TASK`, `MEETING`, `MILESTONE`, `REMINDER`).
  - Idempotent opportunity projection updating existing calendar events if canonical deadlines are revised or extended.
  - Deterministic RFC 5545 `.ics` export with byte-level determinism and strict 75-octet line folding.
  - Alembic migration `0014_phase4_4_calendar`.
  - REST API under `/api/v1/calendar`, `/events`, `/project-opportunity`, and `/export/ical`.
  - Next.js App Router visual calendar at `/calendar` with Month and Agenda views, event filters, and quick-add planning tasks.
  - 28 dedicated unit and API tests.
- **Phase 4.5 (Deadline Reminders, Notifications & Scheduled Alerts)**:
  - `NotificationPreferenceModel`, `ReminderRuleModel`, `NotificationModel`, and `NotificationDeliveryAttemptModel`.
  - Production-ready reminder and alert system grounded in Phase 2.7 canonical deadlines and Phase 4.4 calendar events.
  - Multi-milestone isolation and extension/revision-aware recalculation.
  - Provider-agnostic delivery abstraction (`BaseNotificationDeliveryProvider`) with `InAppDeliveryProvider` and `MockEmailDeliveryProvider`.
  - Deterministic `SHA-256` deduplication key ensuring zero duplicate alerts across repeated scheduler runs.
  - Background `ReminderSchedulerService` with batch chunking ($N=50$) and zero N+1 database queries, benchmarked at $728\text{ ms}$ for 1,000 researchers ($0.73\text{ ms}$ per user).
  - User notification preferences (channel toggles, quiet hours, minimum urgency thresholds) and customizable reminder offset rules (e.g. 14 days, 7 days, 1 day before deadline).
  - Alembic migration `0015_phase4_5_notifications`.
  - REST API under `/api/v1/notifications`, `/read`, `/dismiss`, `/mark-all-read`, and `/api/v1/researchers/me/notification-preferences`.
  - Next.js App Router Notification Center at `/notifications` and Preferences at `/settings/notifications`.
  - 39 dedicated unit, API, invariant, and performance tests.
- **Phase 4.6 (Collaborative Research Management — Completed)**:
  - Bounded collaboration model around research workspaces (`SavedOpportunityModel`).
  - `WorkspaceMemberModel`, `WorkspaceInvitationModel`, `WorkspaceTaskModel`, and `WorkspaceActivityModel`.
  - Server-side Role-Based Access Control (RBAC) via `WorkspaceAuthorizationService` (`OWNER`, `EDITOR`, `CONTRIBUTOR`, `VIEWER`).
  - Cryptographic URL-safe invitation lifecycle (create, accept, decline, revoke, expiration) with idempotent acceptance and zero secret leakage.
  - Workspace-scoped task management with assignment, status, priority, and submission/document linkage.
  - Append-only structured activity trail and workflow comments.
  - Phase 4.5 notification pipeline integration for invitations, role changes, and task assignments.
  - Next.js App Router UI at `/workspace/[id]` with tabbed panels (Overview, Submissions, Tasks, Members, Invitations, Activity & Notes).
  - 56 dedicated unit, integration, invariant, and performance tests with verified zero N+1 queries.
  - Non-destructive Alembic migration `0016_phase4_6_collaboration.py`.
- **Phase 4.7 (Evaluation & Production Hardening — Planned)**:
  - End-to-end workflow verification across multi-user workspaces.
  - Tenant isolation security penetration testing verifying complete separation under concurrent `X-User-ID` requests.
  - Audit trail immutability and tamper-resistance verification.
  - High-concurrency database connection pool stress testing and index query plan validation.
  - Final production readiness audit.

---

## Thematic Architecture Deep-Dives

### 1. Data & Discovery Architecture
Focuses on acquiring, sanitizing, indexing, and retrieving research opportunities and academic literature with high precision and low latency.

```
Incoming CFP / Paper ──► Clean & Validate ──► Hash Deduplication ──► Canonical Taxonomy DAG
                              │                     │                         │
                              ▼                     ▼                         ▼
                        SQL Storage ◄────── 384d Dense Embedding ◄── GIN tsvector Columns
```

- **Conference, Journal & CFP Discovery**: Automated ingestion via WikiCFP scrapers, OpenAlex bibliometrics, and Crossref DOIs *(Phases 1, 2.1, 2.2A, 2.2B)*.
- **Data Cleaning & Schema Normalization**: Normalizing heterogeneous venue metadata, dates, URLs, and publisher strings into validated Pydantic schemas *(Phases 2.1, 2.2B)*.
- **Change Detection & Audit Tracking**: Detecting deadline revisions, venue venue moves, and call cancellations *(Phases 2.1, 2.7E)*.
- **Hybrid Retrieval & RRF Fusion**: Merging pgvector HNSW cosine similarity with PostgreSQL weighted full-text search (`ts_rank_cd`) via Reciprocal Rank Fusion ($k=60$) *(Phases 2.4A, 2.4B, 2.4I)*.
- **Specialized Matching Pipelines**:
  - Similar Research Explorer: Semantic nearest neighbors, exact topic overlap, and taxonomy DAG hierarchical proximity *(Phase 2.4C)*.
  - Research-to-Opportunity Matcher: Evaluating manuscript abstracts against open CFPs using publication type compatibility matrices and deadline windows *(Phase 2.4D)*.
- **Zero-LLM Explainability**: Fully transparent, machine-readable signal attributions ($100\%$ aligned with mathematical weights) explaining exactly why items are retrieved and ranked *(Phase 2.4F)*.

---

### 2. Research Intelligence & Taxonomy Engine
Extracts contextual, semantic, and structural understanding from user manuscripts, research profiles, and academic taxonomies.

- **Canonical Computer Science Taxonomy**: 36-node curated DAG modeling hierarchical parent-child relationships, transitive ancestor/descendant closure, and lowest common ancestor distances *(Phase 2.3A)*.
- **Deterministic Keyword & Concept Extraction**: Mapping author-provided keywords, unstructured abstract text, and external concept tags to canonical taxonomy nodes *(Phase 2.3A)*.
- **Researcher Profile Representation**: Canonical researcher profile tracking ORCIDs, Google Scholar IDs, institutional affiliations, and profile completeness *(Phase 3.1)*.
- **Research Interest & Expertise Scoring**: Inferring topic strengths ($0.0$–$1.0$) and confidence scores from historical publications with exponential recency decay *(Phase 3.2)*.
- **Personal Preference Modeling**: Storing explicit researcher preferences (topics, venue types, open access, deadline notice) and inferring latent preferences from workspace behavior *(Phase 3.3)*.

---

### 3. AI Recommendation & Multi-Stage Ranking
Provides explainable, personalized, and mathematically bounded recommendations matching researchers to venues.

```
Candidate Generation (Phase 3.4)
        │
        ▼
Base Hybrid Ranking (Phase 2.5) ──► Relevance Dominance (≥85%) ──► Diversity & Novelty (MMR)
        │
        ▼
Personalized Ranking (Phase 3.5) ──► Bounded Adjustment (≤0.15) ──► Safety & Deadline Preservation
        │
        ▼
Deterministic 15-Key Tie-Breaker ──► Explainable Output (Phase 3.8)
```

- **Academic Feature Layer**: 6 normalized canonical signals: citation impact, author prominence, author position, institution prestige, venue prestige, and open access tier *(Phase 2.5B)*.
- **Relevance Dominance Invariant**: Mathematical constraint guaranteeing that relevance signals always constitute $\ge 85\%$ of the total ranking mass, preventing high-prestige but irrelevant venues from ranking high *(Phase 2.5C)*.
- **Diversity & Novelty Reranking**: Maximal Marginal Relevance (MMR) and Herfindahl-Hirschman Index (HHI) concentration limits preventing author, venue, or topic monopolies in recommendation lists *(Phase 2.5E)*.
- **Personalized Candidate Retrieval**: Multi-channel generation across explicit preferences, learned topics, and author expertise *(Phase 3.4)*.
- **Personalized Hybrid Ranking**: Bounded personalization adjustments ($\le 0.15$) preserving base relevance, Phase 2.6 risk flags, and Phase 2.7 deadline status *(Phase 3.5)*.
- **Closed-Loop Feedback**: Controlled learning from user saves, dismissals, and clicks with reversible weights and decay *(Phase 3.6)*.
- **Recommendation Snapshotting & Offline IR**: Capturing immutable recommendation histories and evaluating NDCG@K, MAP, and MRR across 10-state segmented datasets *(Phases 3.7, 3.9)*.

---

### 4. Trust, Safety & Deadline Intelligence
Protects researchers from predatory publication venues and provides authoritative temporal lifecycle tracking.

#### Trust & Predatory Detection (Phase 2.6)
- **Heuristic Risk Extraction**: Pattern matching for predatory fee mechanisms (Western Union/MoneyGram), fake impact factors, sub-48-hour peer review, and hijacked domains *(Phase 2.6B)*.
- **Deterministic Risk Scoring**: Calibrated 0–100 risk score and 5 categorical tiers (`VERY_LOW`, `LOW`, `MODERATE`, `HIGH`, `CRITICAL`) *(Phase 2.6C)*.
- **Publisher & Indexing Verification**: Resolving ISSNs and publishers against DOAJ, Crossref, and OpenAlex indexing records *(Phase 2.6D)*.
- **Academic Trust Graph**: Detecting organizer/domain syndicates, contact email/phone collisions, and shell conferences *(Phase 2.6E)*.
- **Risk Transparency & UI Badges**: Provenance-backed risk explanations and warning banners with progressive disclosure *(Phase 2.6F)*.
- **Empirical Hardening**: $100\%$ precision on reputable venues and $0\%$ false positives on top-tier venues across 20 safety invariants *(Phase 2.6G)*.

#### Deadline Intelligence & Urgency Engine (Phase 2.7)
- **Multi-Milestone Taxonomy**: Independent tracking of 7 milestone types (`ABSTRACT`, `SUBMISSION`, `NOTIFICATION`, `CAMERA_READY`, `REGISTRATION`, `EVENT_START`, `EVENT_END`) *(Phase 2.7A)*.
- **Timezone Normalization & AoE Semantics**: Canonical UTC conversion handling Anywhere on Earth (AoE, UTC-12) and date-only 23:59:59 end-of-day conventions *(Phase 2.7C)*.
- **Authority Hierarchy & Conflict Resolution**: Canonical source hierarchy (`OFFICIAL_WEBSITE` > `CFP_SERVICE` > `AGGREGATOR`) with equal-authority conflict preservation (`SOURCE_CONFLICT`) *(Phase 2.7E)*.
- **Revision & Extension Tracking**: Full lineage tracking of extended deadlines (`EXTENDED`) or preponed dates (`MOVED_EARLIER`) *(Phase 2.7E)*.
- **Non-Linear Urgency Engine**: Exponential and sigmoid decay scoring mapping deadlines to urgency tiers without distorting Phase 2.5 relevance *(Phase 2.7D)*.
- **Deadline Explainability**: Real-time visual timeline badges and countdowns in the UI *(Phase 2.7F)*.

---

### 5. Research Management & Workflow Lifecycle
Directly empowers researchers to manage their submissions, documents, milestones, calendars, and alerts across the research lifecycle.

```
Saved Opportunity (Phase 4.1) ──► Research Submission (Phase 4.2)
       │                                     │
       ▼                                     ▼
Preparation Milestones               Document Versioning & Readiness (Phase 4.3)
       │                                     │
       ▼                                     ▼
Research Calendar (Phase 4.4) ──────► Advance Reminders & Alerts (Phase 4.5)
       │                                     │
       └──────────────────┬──────────────────┘
                          ▼
            Unified Dashboard (Phase 4.6)
```

#### Completed Subsystems (Phases 4.0–4.7)
1. **Phase 4.1 — Opportunity Workspace**:
   - Researcher-scoped tracking across 7 stages: `SAVED`, `CONSIDERING`, `PLANNING`, `APPLIED`, `ACCEPTED`, `REJECTED`, `ARCHIVED`.
   - Private custom notes, priority tags, and strict tenant isolation via `X-User-ID`.
   - Accessible via `/api/v1/workspace` and `/workspace`.
2. **Phase 4.2 — Submission & Application Tracker**:
   - `ResearchSubmissionModel` (1:N with saved opportunities) managing manuscripts through a 7-state lifecycle: `DRAFT` $\to$ `READY` $\to$ `SUBMITTED` $\to$ `UNDER_REVIEW` $\to$ `ACCEPTED` / `REJECTED`, plus `WITHDRAWN`.
   - Bidirectional workspace synchronization; read-only grounding in Phase 2.7 canonical deadline intelligence.
   - Accessible via `/api/v1/submissions` and `/workspace/[id]/submission`.
3. **Phase 4.3 — Research Submission Workflow & Document Management**:
   - Document lifecycle: `REQUIRED`, `MISSING`, `DRAFT`, `READY`, `REJECTED`, `ARCHIVED`.
   - Strongly-typed artifact categories: `MANUSCRIPT`, `COVER_LETTER`, `SUPPLEMENTARY`, `ETHICS_STATEMENT`, `SOURCE_CODE`, `DATA_AVAILABILITY`.
   - Immutable version snapshotting with SHA-256 hashes and byte sizes.
   - Deterministic `SubmissionReadinessEngine` gating submission transition to `READY` until all required documents are satisfied.
   - Complete chronological audit logging with `SubmissionEventModel`.
   - Accessible via `/api/v1/submissions/{id}/documents` and `/workspace/[id]/submission`.
4. **Phase 4.4 — Research Calendar & Visual Deadline Planning**:
   - `ResearchCalendarModel` and `ResearchCalendarEventModel`.
   - Automatic projection of Phase 2.7 canonical deadlines with milestone isolation and revision/extension synchronization.
   - User-created planning events (`TASK`, `MEETING`, `MILESTONE`, `REMINDER`).
   - Deterministic RFC 5545 `.ics` export with 75-octet line folding and byte-level determinism.
   - Accessible via `/api/v1/calendar` and `/calendar` with Month and Agenda views.
5. **Phase 4.5 — Deadline Reminders, Notifications & Scheduled Alerts**:
   - Production-ready alert system grounded in Phase 2.7 canonical deadlines and Phase 4.4 planning events.
   - Provider abstraction (`InAppDeliveryProvider`, `MockEmailDeliveryProvider`).
   - Idempotent alert generation via deterministic SHA-256 deduplication keys.
   - Zero N+1 scheduled reminder engine ($0.73\text{ ms}$ per user across 1,000 researchers).
   - User notification preferences (channels, quiet hours, urgency thresholds) and custom reminder rules (e.g. 14d, 7d, 1d).
   - Accessible via `/api/v1/notifications`, `/notifications`, and `/settings/notifications`.
6. **Phase 4.6 — Collaborative Research Management**:
   - Bounded collaboration model around research workspaces (`SavedOpportunityModel`).
   - `WorkspaceMemberModel`, `WorkspaceInvitationModel`, `WorkspaceTaskModel`, and `WorkspaceActivityModel`.
   - Server-side RBAC (`OWNER`, `EDITOR`, `CONTRIBUTOR`, `VIEWER`) via `WorkspaceAuthorizationService`.
   - Secure invitation lifecycle with expiration, revocation, and idempotent token-based acceptance.
   - Workspace tasks with assignment, status tracking, and linked submission/document artifacts.
   - Append-only structured activity trail and workflow notes.
   - Phase 4.5 notification integration for invitations, role changes, and task assignments.
   - Accessible via `/api/v1/workspaces/{id}/members`, `/invitations`, `/tasks`, `/activity` and `/workspace/[id]`.
7. **Phase 4.7 — Research Intelligence Integration & Production Hardening [COMPLETE]**:
   - Authoritative unified integration service (`ResearchIntelligenceIntegrationService`) connecting Phases 2, 3, and 4.
   - Structured signal provenance (`ResearchIntelligenceSignalSchema`) tracking explicit vs inferred, confidence, strength, and evidence.
   - Canonical researcher identity resolution (`RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`, `SELF_DECLARED_ONLY`) with zero attribute fabrication.
   - 6-tier explainability framework (Relevance, Researcher, Interest, Preference, Deadline, Risk, Workspace Context).
   - Unified recommendation pipeline preserving Phase 2.5 relevance dominance ($\ge 85\%$) and Phase 3.5 bounded personalization ($\le 15\%$).
   - Dedicated APIs (`/intelligence/unified`, `/recommendations/unified`, `/recommendations/unified/{id}/intelligence`).
   - Next.js UI integration (`UnifiedResearchIntelligenceView`, `ExplainabilityDrawer`, `/researcher`).
   - Zero N+1 query patterns; zero database migrations required (`Migration Required: NO`).
   - 100% test pass rate across all 14 integration tests and full regression suites.

---

### 6. Community & Academic Collaboration (Phase 5)
Facilitates institutional and cross-disciplinary collaboration within verified academic boundaries, powered by an explicit researcher preference foundation.

#### Phase 5.1 — Researcher Preferences Foundation [COMPLETE]
- **Explicit Domain Model & 3-State Semantics**:
  - `ResearcherPreferenceModel` extended with `preference_type` (`PREFERRED`, `EXCLUDED`).
  - Strict 3-state distinction: Preferred $\neq$ Neutral (unspecified) $\neq$ Excluded. Absence of preference is strictly neutral and never treated as negative.
  - Deleting or omitting preferences safely resets to Neutral without profile deletion or data loss.
- **Categorical Normalization & Validation**:
  - Structured preference categories: `TOPIC`, `KEYWORD`, `RESEARCH_DOMAIN`, `OPPORTUNITY_TYPE`, `VENUE_TYPE`, `LOCATION`, `COUNTRY`, `REGION`, `INSTITUTION`, `FUNDING`, `ACADEMIC_LEVEL`, `CAREER_STAGE`.
  - Canonical opportunity types: `CONFERENCE`, `JOURNAL`, `WORKSHOP`, `SYMPOSIUM`, `FELLOWSHIP`, `GRANT`, `INTERNSHIP`.
  - Uppercase ISO country code normalization, trimmed whitespace, keyword deduplication, and deterministic conflict detection between `PREFERRED` and `EXCLUDED`.
- **Database Migration & Safety**:
  - Non-destructive Alembic migration `0017_phase5_1_researcher_preferences_foundation.py` adding `preference_type` with server default `'PREFERRED'` and check constraint `chk_researcher_preferences_type`.
  - Composite unique constraint `(profile_id, category, preference_value)` guaranteeing idempotent in-place updates without record duplication.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/preferences` (with optional `preference_type` filter)
  - `GET /api/v1/researchers/{id}/preferences/structured` (organized by domain categories and exclusions)
  - `PUT /api/v1/researchers/{id}/preferences` (atomic bulk synchronization with optional `replace_existing`)
  - `POST /api/v1/researchers/{id}/preferences`
  - `PATCH /api/v1/researchers/{id}/preferences/{pref_id}`
  - `DELETE /api/v1/researchers/{id}/preferences/{pref_id}`
- **Next.js App Router UI**:
  - Dedicated full-page preference center at `/researcher/preferences` with interactive 3-state controls, academic level & career stage selectors, funding toggles, and explicit exclusions management.
  - Linked directly from existing `/researcher` overview via `ResearcherPreferencesView.tsx`.
- **Phase Boundary & Mathematical Invariants**:
  - 20 safety invariants verified: zero N+1 queries, zero alteration of Phase 2.5/3.5/4 recommendation ranking scores, zero behavioral tracking, collaborative filtering, or ML personalization in Phase 5.1.
  - 14 dedicated backend tests passed; 100% pass rate on all regression test suites.

#### Future Phase 5 Modules (Planned)
- **Phase 5.2 — Faculty Research Opportunities**: Structured listings posted by faculty members for open research slots, thesis topics, and specialized projects.
- **Phase 5.3 — Collaborative Project Postings**: Multi-student or inter-departmental research project announcements seeking collaborators.
- **Phase 5.4 — Research Internships & RA Openings**: Curated academic and industrial research internships, research assistantships, and post-doctoral openings.
- **Phase 5.5 — Peer & Co-Author Discovery**: Matching researchers based on complementary skill sets, shared taxonomy interests, and compatible methodologies.

---

### 7. Platform Infrastructure, Governance & Security (Phase 6)
Core infrastructure, identity, security, access control, and deployment operations.

- **Authentication & Identity**: JWT/OAuth2 authentication with bcrypt password hashing and session management.
- **Role-Based Access Control (RBAC)**: Strict separation of permissions across `STUDENT`, `FACULTY`, and `ADMIN` roles.
- **Multi-Tenant Isolation**: Hardened tenant scoping via `X-User-ID` headers across all user-facing services and database queries.
- **API Protection**: Strict Pydantic input validation, CORS protection, sliding-window rate limiting, and secure environment configuration.
- **Structured Logging & Observability**: Formatted JSON logging with correlation IDs and audit trails for compliance.
- **Containerization & Deployment**: Docker Compose local development and lightweight multi-stage Dockerfiles for cloud deployment.

---

### 8. Evaluation Framework & Mathematical Invariants (Phase 7 / Continuous)
Continuous quantitative validation of AI, scraping, ranking, and lifecycle systems.

- **Offline IR Evaluation**: Automated benchmarking of NDCG@K, MAP, and MRR across Vector, Lexical, Hybrid, and Personalized ranking configurations.
- **Safety Invariants**:
  - *Relevance Dominance*: $\sum w_{\text{relevance}} \ge 0.85$ (prestige signals cannot overpower topical match).
  - *Trust Orthogonality*: Predatory risk scoring is independent of ranking urgency and cannot be bypassed by personalization.
  - *Deadline Integrity*: Expired opportunities (`EXPIRED`) are strictly excluded from recommendation feeds and cannot be resurrected.
  - *Readiness Gating*: Submissions cannot transition to `READY` without all required documents in `READY` status.
  - *Deduplication Idempotency*: Notification and calendar projection engines use deterministic SHA-256 keys to guarantee zero duplicates.
- **Test Coverage**: 1,008+ backend unit, integration, invariant, and performance tests plus 389 scraper tests passing continuously.
