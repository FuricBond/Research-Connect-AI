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
| **Phase 5.2** | Preference Interpretation | **COMPLETE** | Deterministic domain layer, 9-dimension evaluation, conflict preservation, missing-data safety, batch API, Next.js match badge | 25 Invariants Passed |
| **Phase 5.3** | Personalization-Aware Opportunity Scoring | **COMPLETE** | Normalized dimension weights, bounded scoring (0-1), structured contribution breakdown, batch API, Next.js score badge | 20 Invariants Passed |
| **Phase 5.4** | Researcher Feedback & Interaction Signals | **COMPLETE** | Append-only auditable interaction store, explicit feedback vs passive telemetry, rapid-fire deduplication, migration 0018, interactive feedback bar | 25 Invariants Passed |
| **Phase 5.5** | Adaptive Preference Signal Aggregation | **COMPLETE** | Deterministic interaction aggregation, temporal decay (30d half-life), bounded additive personalization (±0.10), overreaction protection, migration 0019, Next.js adaptive signals card | 17 Tests / 35 Invariants |
| **Phase 5.6** | Personalization Calibration | **COMPLETE** | Closed-loop causal attribution (14d window), bounded calibration (±0.05), anti-feedback loop safeguards, migration 0020, calibration card UI | 12 Tests / 100% Regr |
| **Phase 5.7** | Personalization Quality & Contextual Adaptation | **COMPLETE** | Observed lift, contextual partitioning (5 dimensions), 4-level fallback, bounded contextual adaptation (±0.03), migration 0021, quality card UI | 10 Tests / 100% Regr |
| **Phase 5.8** | Personalization Governance & Drift Detection | **COMPLETE** | Temporal window partitioning (60d/14d), drift classification (STABLE/EMERGING/PERSISTENT/REVERSING), staleness detection, explicit preference protection, multi-dimensional health score, governance gate (ALLOW->SUSPEND), neutral suspension, migration 0022, governance card UI | 10 Tests / 100% Regr |
| **Phase 5.9** | Personalization Transparency & Controls | **COMPLETE** | Deterministic explanation layer ("Why this recommendation?"), 5 bounded impact tiers, researcher controls (master toggle, adaptive toggle, future feedback toggle), safe reset with state versioning (v1->v2), append-only control audit trail, migration 0023, Next.js explanation modal & settings card UI | 8 Tests / 100% Regr |
| **Phase 5.10** | Faculty Research Opportunities & Project Postings | **COMPLETE** | Platform-authored openings with a named accountable owner, 6-state lifecycle, FACULTY/ADMIN authorship, draft non-disclosure, taxonomy links, migration 0026, Next.js `/postings` | 38 Tests |
| **Phase 5.11** | Research Internships, RA Openings & Applications | **COMPLETE** | Structured appointment terms, jointly owned applications with role-partitioned transitions, author-private review notes, append-only history, Phase 4.5 notifications, migration 0027 | 37 Tests |
| **Phase 5.12** | Peer & Co-Author Discovery | **COMPLETE** | Opt-in discoverability with field-level disclosure, deterministic explainable matcher balancing shared against complementary expertise, taxonomy proximity, migration 0028, Next.js `/peers` | 35 Tests |
| **Phase 6** | Platform Infrastructure, Security & Correctness Hardening | **IN PROGRESS** | Signed bearer-token authentication with bcrypt credentials, single identity dependency (no fallback identity), RBAC (Student/Faculty/Admin), login rate limiting, structured logging with correlation IDs, fresh-database migrations, Phase 5 stack wired into live ranking, durable personalization reset, deterministic demo seeder, background scheduler (off by default). Remaining: frontend auth UI | 1,277 Tests |
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
Facilitates institutional and cross-disciplinary collaboration within verified academic boundaries. Phases 5.1–5.9 build the explicit researcher preference and governed personalization foundation; Phases 5.10–5.12 add the collaboration surfaces themselves — faculty-authored openings, the application workflow, and consent-based peer discovery.

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

#### Phase 5.2 — Explicit Preference Interpretation & Personalization Signal Foundation [COMPLETE]
- **Deterministic Domain Layer & Explainable Signals**:
  - `PreferenceInterpreter` evaluates opportunities against explicit researcher preferences across 9 supported dimensions (`KEYWORD`, `RESEARCH_DOMAIN`, `COUNTRY`, `REGION`, `INSTITUTION`, `FUNDING`, `ACADEMIC_LEVEL`, `CAREER_STAGE`, `OPPORTUNITY_TYPE`).
  - Strict 3-state semantics preserved: Preferred $\neq$ Neutral $\neq$ Excluded.
  - Conflict detection: When an opportunity intersects both preferred and excluded criteria, both signals are preserved as `CONFLICT` with `UNRESOLVED` polarity.
  - Missing data safety: Missing opportunity attributes strictly yield `INSUFFICIENT_EVIDENCE` and are never treated as negative evidence or exclusions.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/opportunities/{opp_id}/preference-match`: Single opportunity evaluation returning atomic dimension signals and aggregate assessment.
  - `POST /api/v1/researchers/{id}/opportunities/preference-matches`: Batch evaluation endpoint in memory with zero N+1 database queries.
- **Next.js App Router Integration**:
  - `PreferenceMatchBadge` component rendering 3-state match badges, count indicators, and interactive popover explanations.
  - Integrated into `UnifiedResearchIntelligenceView` alongside recommendation cards with zero ranking reordering.
- **Strict Phase Boundary & Invariants**:
  - Zero behavioral learning, zero collaborative filtering, zero embeddings, zero ML personalization, zero opaque ranking boosts.
  - All 25 safety invariants verified with dedicated test suite (`test_preference_interpretation.py`).

#### Phase 5.3 — Personalization-Aware Opportunity Scoring & Explainability [COMPLETE]
- **Deterministic Personalization Scorer & Domain Breakdown**:
  - `PersonalizationScorer` computes bounded, dimension-aware personalization scores ($0.0 \le s \le 1.0$) consuming Phase 5.2 explicit preference signals.
  - Centralized `PersonalizationScoringConfig` defining explicit, normalized weights across all 9 dimensions (`KEYWORD`: 0.20, `RESEARCH_DOMAIN`: 0.20, `OPPORTUNITY_TYPE`: 0.15, `COUNTRY`: 0.10, `REGION`: 0.05, `INSTITUTION`: 0.10, `FUNDING`: 0.10, `ACADEMIC_LEVEL`: 0.05, `CAREER_STAGE`: 0.05).
  - Explicit exclusion penalties, dual-evidence conflict preservation, and missing-data safety (`INSUFFICIENT_EVIDENCE` contributes 0.0, never negative).
  - Structured `PersonalizationScoreBreakdown` partitioning dimension contributions into positive, negative, neutral, and unresolved buckets.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/opportunities/{opp_id}/personalization`: Single opportunity evaluation returning complete `PersonalizationAssessment`.
  - `POST /api/v1/researchers/{id}/opportunities/personalization`: Batch scoring endpoint evaluating up to 100 opportunities in memory with zero N+1 queries.
- **Next.js App Router Integration**:
  - `PersonalizationScoreBadge` component displaying percentage match, confidence, and interactive popover with detailed dimension contributions and natural language explanations.
  - Integrated into `UnifiedResearchIntelligenceView` alongside recommendation cards with zero ranking reordering.
- **Strict Phase Boundary & Invariants**:
  - Zero behavioral learning, zero click/bookmark tracking, zero collaborative filtering, zero embeddings, zero ML personalization, zero opaque ranking overrides.
  - All 20 safety invariants verified with dedicated test suite (`test_personalization_scoring.py`).

#### Phase 5.4 — Researcher Feedback & Interaction Signal Foundation [COMPLETE]
- **Auditable Append-Only Persistence Model**:
  - `researcher_interactions` normalized table with composite indexes (`(profile_id, created_at)`, `(profile_id, opportunity_id, interaction_type)`, `(opportunity_id, interaction_type)`, `(profile_id, client_event_id)`).
  - Historical interaction events are append-only and auditable; never mutated when preferences or recommendations change.
- **Explicit Feedback vs. Passive Observation Semantics**:
  - Explicit signals (`INTERESTED`, `NOT_INTERESTED`, `DISMISSED`, `HIDDEN`, `SAVED`, `APPLIED`, `SHARED`): Intentional researcher feedback.
  - Passive observations (`VIEWED`, `OPENED`): Strictly informational telemetry; never treated as preference or affinity.
  - Inviolability: Zero mutation of explicit preferences in `ResearcherPreferenceModel`, zero modification of Phase 4 ranking formulas, Phase 2.6 risk, or Phase 2.7 deadline intelligence.
- **REST APIs**:
  - `POST /api/v1/researchers/{id}/opportunities/{opp_id}/interactions`: Idempotent interaction recording with client event ID and rapid-fire deduplication.
  - `GET /api/v1/researchers/{id}/opportunities/{opp_id}/interactions`: Chronological interaction history for an opportunity.
  - `GET /api/v1/researchers/{id}/interactions/summary`: Aggregated interaction counts, positive/negative breakdown, and recent events (zero N+1 queries).
- **Next.js App Router Integration**:
  - Reusable, accessible `OpportunityInteractionBar` component with Save, Interested, Not Interested, Dismiss, Hide, and Share actions.
  - Integrated into `UnifiedResearchIntelligenceView` cards with optimistic feedback and double-click prevention.
- **Strict Phase Boundary & Invariants**:
  - Zero collaborative filtering, zero embeddings, zero vector databases, zero ML personalization, zero LLM calls, zero external analytics.
  - All 25 safety invariants verified with dedicated test suite (`test_researcher_interactions.py`).

#### Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge [COMPLETE]
- **Deterministic Interaction Aggregation & Temporal Decay**:
  - `AdaptiveSignalEngine` aggregates Phase 5.4 researcher interactions into bounded preference signals across canonical opportunity dimensions (`OPPORTUNITY_TYPE`, `RESEARCH_DOMAIN`, `COUNTRY`, `INSTITUTION`, `FUNDING`).
  - Transparent, versioned interaction weighting (`VIEWED`: 0.05, `OPENED`: 0.10, `SHARED`: 0.30, `SAVED`: 0.60, `INTERESTED`: 0.80, `APPLIED`: 1.00, `NOT_INTERESTED`: -0.70, `DISMISSED`: -0.50, `HIDDEN`: -0.90).
  - Exponential temporal decay with 30-day half-life: $w_{\text{eff}} = w_{\text{base}} \times 2^{-\Delta t / 30.0}$, bounded by minimum weight floor 0.05. Explicit reference time parameter ensures zero wall-clock dependence in tests.
- **Evidence Preservation & Conflict Handling**:
  - Positive and negative evidence counts and decayed weights are tracked separately (never collapsed into an opaque score).
  - Confidence metric ($0.0 \le c \le 1.0$) combines evidence volume factor and polarity agreement factor.
  - Dual-evidence conflicts are transparently flagged as `CONFLICT` with `UNRESOLVED` polarity.
- **Overreaction Protection**:
  - Strict 4-tier classification: `INSUFFICIENT_EVIDENCE` ($N < 3$), `EMERGING` ($3 \le N < 6$), `ESTABLISHED` ($6 \le N < 12$), `STRONG` ($N \ge 12$).
  - Single interactions or sparse evidence ($N < 3$) strictly yield 0.0 score contribution.
- **Personalization Bridge & Relevance Dominance**:
  - Additive contribution bounded by $\text{clamp}(\Delta_{\text{adaptive}}, -0.10, +0.10)$, preserving Phase 4 relevance dominance ($\ge 85\%$).
  - Explicit preferences (Phase 5.1) remain authoritative; explicit `EXCLUDED` always produces 0.0 final score regardless of adaptive affinity.
  - Zero preference rewriting: interactions never create, modify, or delete explicit preferences.
- **Database Model & Migration**:
  - `adaptive_preference_signals` table with composite unique constraint `(profile_id, dimension, signal_value)`.
  - Non-destructive Alembic migration `0019_phase5_5_adaptive_preference_signals.py`.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/adaptive-signals`: Paginated adaptive signals with dimension and state filters.
  - `GET /api/v1/researchers/{id}/adaptive-signals/{signal_id}`: Single signal detail with evidence breakdown.
  - `POST /api/v1/researchers/{id}/adaptive-signals/recompute`: Deterministic signal recomputation.
  - `GET /api/v1/researchers/{id}/adaptive-signals/explanation`: Structured aggregate natural language summary.
- **Next.js App Router Integration**:
  - `AdaptiveSignalsCard` component featuring dimension/state filters, evidence counts, visual strength bars, deterministic explanations, and recompute action.
  - Integrated into `UnifiedResearchIntelligenceView` (Section 2.5).
- **Strict Phase Boundary & Invariants**:
  - Zero ML models, zero LLMs, zero vector DBs, zero collaborative filtering, zero cross-user profiling.
  - All 35 safety invariants verified with 17 dedicated tests (`test_adaptive_preference_signals.py`) and 162 regression tests.

#### Phase 5.6 — Adaptive Personalization Calibration & Recommendation Feedback Loop [COMPLETE]
- **Closed-Loop Feedback & Causal Attribution**:
  - `PersonalizationCalibrationEngine` directly measures how previously attributed personalization signals perform against subsequent researcher interactions.
  - 14-day causal attribution window ($t_R \le t_I \le t_R + 14\text{d}$) with deterministic confidence tiers: `DIRECT` ($\le 24\text{h}$, $1.0\times$), `LIKELY` ($\le 7\text{d}$, $0.75\times$), `WEAK` ($\le 14\text{d}$, $0.40\times$), and `UNATTRIBUTED` ($0.0\times$).
- **Anti-Feedback-Loop Safeguards & Conflict Handling**:
  - Runaway self-reinforcing loops prevented by capping outcomes at most 1 primary feedback outcome per opportunity per signal per attribution window.
  - Dual-evidence conflicts preserved and dampened via conflict ratio $R_{\text{conflict}}$ and state multiplier ($0.25\times$).
- **Bounded Calibration Modifier & Precedence Invariants**:
  - Net calibration modifier strictly bounded to $\Delta_{\text{calib}} \in [-0.05, +0.05]$.
  - Total combined adaptive contribution clamped to $[-0.10, +0.10]$, strictly preserving Phase 4 relevance dominance ($\ge 85\%$).
  - Explicit preferences (Phase 5.1) remain strictly authoritative: explicit `EXCLUDED` forces final score to `0.0`; explicit `PREFERRED` with baseline $\ge 0.50$ is protected from negative suppression.
- **Database Models & Migration**:
  - `personalization_calibrations` table with composite unique constraint `(profile_id, dimension, signal_value)` and `recommendation_feedback_attributions` table.
  - Non-destructive Alembic migration `0020_phase5_6_personalization_calibration.py`.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/personalization/calibration`: List calibrations with dimension/state filters.
  - `GET /api/v1/researchers/{id}/personalization/calibration/{signal_id}`: Single calibration detail with attribution history.
  - `POST /api/v1/researchers/{id}/personalization/calibration/recompute`: Idempotent calibration recomputation.
- **Next.js App Router Integration**:
  - `PersonalizationCalibrationCard` component featuring status badges, modifier indicators, filter tabs, stats summary, and manual recompute action.
  - Integrated into `UnifiedResearchIntelligenceView` (Section 2.6).
- **Strict Phase Boundary & Invariants**:
  - Zero ML models, zero LLMs, zero vector DBs, zero collaborative filtering, zero cross-user profiling.
  - 12 dedicated tests passing (`test_personalization_calibration.py`); sub-second scaling benchmarks verified across 10,000 recommendations (~142ms).

#### Phase 5.7 — Personalization Evaluation, Contextual Adaptation & Recommendation Quality Loop [COMPLETE]
- **Personalization Quality & Empirical Lift Measurement**:
  - `PersonalizationQualityEngine` directly measures observed personalization lift ($\text{Lift}_{\text{obs}} = \text{Rate}_{\text{personalized}} - \text{Rate}_{\text{baseline}}$), engagement rates, positive/negative feedback rates, diversity (normalized Shannon entropy), and novelty rate without claiming causal certainty.
- **Contextual Partitioning & Hierarchical Fallback**:
  - Partitioning behavioral signal performance across 5 dimensions: `OPPORTUNITY_TYPE`, `DEADLINE_HORIZON`, `RISK_TIER`, `RELEVANCE_TIER`, `ACADEMIC_STATUS`.
  - 4-level deterministic fallback: Level 1 (Exact Context: $N \ge 3$, conf $\ge 0.30$) $\to$ Level 2 (Broad Context / Calibration) $\to$ Level 3 (Adaptive Signal) $\to$ Level 4 (Neutral: $0.0$).
- **Bounded Adaptation & Invariant Hierarchy**:
  - Contextual adaptation modifier strictly clamped to $\Delta_{\text{context}} \in [-0.03, +0.03]$.
  - Combined calibration and contextual modifier clamped to $[-0.05, +0.05]$; total combined adaptive contribution clamped to $[-0.10, +0.10]$, strictly preserving Phase 4 relevance dominance ($\ge 85\%$).
  - Explicit preferences (Phase 5.1) remain authoritative: explicit `EXCLUDED` forces final score to `0.0`; explicit `PREFERRED` with baseline $\ge 0.50$ is protected from negative suppression.
- **Database Models & Migration**:
  - `personalization_quality_evaluations` and `personalization_contextual_adaptations` tables.
  - Non-destructive Alembic migration `0021_phase5_7_personalization_quality.py`.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/personalization/quality`: Top-level quality metrics, observed lift, diversity, novelty, and deterministic explanations.
  - `GET /api/v1/researchers/{id}/personalization/quality/contexts`: Contextual adaptations breakdown with dimension filter.
  - `GET /api/v1/researchers/{id}/personalization/quality/signals`: Signal-level quality breakdown.
  - `POST /api/v1/researchers/{id}/personalization/quality/recompute`: Idempotent on-demand quality evaluation recomputation.
- **Next.js App Router Integration**:
  - `PersonalizationQualityCard` component featuring observed lift badge, engagement/feedback comparisons, diversity/novelty gauges, context breakdown tabs, and interactive recompute action.
  - Integrated into `UnifiedResearchIntelligenceView` (Section 2.7).
- **Strict Phase Boundary & Invariants**:
  - Zero ML models, zero LLMs, zero vector DBs, zero collaborative filtering, zero cross-user profiling.
  - 10 dedicated unit, integration, benchmark, and multi-tenant authorization tests passing (`test_personalization_quality.py`); sub-second scaling benchmarks verified across 10,000 recommendations (~180ms).

#### Phase 5.8 — Personalization Governance, Drift Detection & Adaptation Safety [COMPLETE]
- **Multi-Dimensional Personalization Health & Drift Detection**:
  - `PersonalizationGovernanceEngine` monitors behavioral signal drift across temporal windows (Recent: 14d, Historical: 60d, Stale: >180d) with deterministic classifications (`STABLE`, `EMERGING`, `PERSISTENT`, `REVERSING`, `UNKNOWN`).
  - Stale evidence principle: stale $\neq$ false (signals older than 180 days are flagged as `STALE` without premature automatic deletion).
  - Multi-dimensional health score ($H \in [0.0, 1.0]$) synthesizing stability ($0.30$), freshness ($0.25$), explicit preference alignment ($0.25$), predictability ($0.10$), and volatility damping ($0.10$).
- **Governance Gate States & Adaptation Multipliers**:
  - Automated state machine: `ALLOW` ($1.0\times$), `ALLOW_BOUNDED` ($0.5\times$), `HOLD` ($0.25\times$), `REDUCE` ($0.25\times$), `SUSPEND` ($0.0\times$).
  - Neutral suspension guarantee: when suspended, adaptive modifiers revert to neutral $0.0$ (never negative).
  - Hysteresis & recovery: transitioning from `SUSPEND` requires $\ge 5$ stable interactions in the evaluation window.
- **Explicit Preference Dominance & Authoritative Invariants**:
  - Behavioral drift can **never** overwrite, mutate, or delete explicit preferences.
  - Explicit `EXCLUDED` unconditionally forces final score to `0.0`.
  - Explicit `PREFERRED` with baseline $\ge 0.50$ is protected from negative suppression.
  - Core relevance dominance ($\ge 85\%$) strictly preserved.
- **Database Models & Migration**:
  - `personalization_drift_evaluations` and `personalization_governance_events` tables.
  - Non-destructive Alembic migration `0022_phase5_8_personalization_governance.py`.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/personalization/health`: Health state, composite score, governance state, adaptation multiplier, and breakdown metrics.
  - `GET /api/v1/researchers/{id}/personalization/drift`: Signal drift evaluations, temporal partitions, and staleness/alignment statuses.
  - `GET /api/v1/researchers/{id}/personalization/governance`: Append-only governance audit log of state transitions.
  - `POST /api/v1/researchers/{id}/personalization/health/recompute`: Idempotent on-demand health and drift recomputation.
- **Next.js App Router Integration**:
  - `PersonalizationGovernanceCard` component with health status pill, gate badge, drift/stale/stable tabs, audit timeline, and recompute action.
  - Integrated into `UnifiedResearchIntelligenceView` (Section 2.8).
- **Strict Phase Boundary & Invariants**:
  - Zero ML models, zero LLMs, zero vector DBs, zero collaborative filtering, zero cross-user profiling.
  - 10 dedicated unit, integration, benchmark, and multi-tenant authorization tests passing (`test_personalization_governance.py`); scaling benchmarks verified from 10 to 10,000 interactions (~48ms).

#### Phase 5.9 — Personalization Transparency, Researcher Controls & Explanation Layer [COMPLETE]
- **Deterministic Transparency & Explanation Model**:
  - `PersonalizationTransparencyEngine` exposes why recommendations were personalized via closed-form deterministic rules ("Why this recommendation?").
  - Evaluates explicit preferences, adaptive signals, calibrations, contextual quality, and governance state without revealing internal noise or chain-of-thought.
  - Explanation safety: never claims "you will like this" or "the system knows your interests"; distinguishes core relevance ($\ge 85\%$) from personalization ($\le 15\%$).
- **Bounded Personalization Impact Classification**:
  - 5 deterministic impact tiers: `NO_PERSONALIZATION` ($|\Delta| < 0.02$), `LOW_PERSONALIZATION` ($0.02 \le |\Delta| < 0.06$), `MODERATE_PERSONALIZATION` ($0.06 \le |\Delta| < 0.12$), `STRONG_PERSONALIZATION` ($|\Delta| \ge 0.12$), `PERSONALIZATION_SUPPRESSED` (explicit `EXCLUDED` or `SUSPEND` gate).
- **Researcher Personalization Controls**:
  - Sovereign controls over personalization behavior: master toggle (`personalization_enabled`), adaptive learning toggle (`adaptive_signals_enabled`), future feedback learning toggle (`feedback_learning_enabled`).
  - Precedence hierarchy: System Safety > Eligibility > Core Relevance ($\ge 85\%$) > Explicit Preferences > Researcher Controls > Adaptive Signals ($\pm 10\%$) > Calibration ($\pm 5\%$) > Contextual ($\pm 3\%$).
- **Safe Reset Mechanism & State Versioning**:
  - Atomically increments `personalization_state_version` ($1 \to 2$).
  - Neutralizes derived adaptive signals, calibrations, and contextual modifiers.
  - Strictly preserves researcher accounts, profiles, explicit preferences, recommendation history, and audit logs.
- **Append-Only Control Audit Trail**:
  - `personalization_control_events` records all control mutations and resets with previous state, new state, trigger reason, and algorithm version (`5.9.1`).
- **Database Models & Migration**:
  - `researcher_personalization_settings` and `personalization_control_events` tables.
  - Non-destructive Alembic migration `0023_phase5_9_personalization_transparency.py`.
- **REST APIs**:
  - `GET /api/v1/researchers/{id}/personalization/settings`: Retrieve settings.
  - `PATCH /api/v1/researchers/{id}/personalization/settings`: Update settings (toggles).
  - `POST /api/v1/researchers/{id}/personalization/reset`: Safe reset.
  - `GET /api/v1/researchers/{id}/personalization/control-history`: Audit history.
  - `GET /api/v1/researchers/{id}/recommendations/{recommendation_id}/personalization`: "Why this recommendation?" explanation.
- **Next.js App Router Integration**:
  - `WhyThisRecommendationModal` component with impact badge, score decomposition (Core Relevance vs Personalization), contributing factors checklist, and academic safety guarantee.
  - `PersonalizationSettingsCard` component with toggles, state version badge, safe reset modal, and expandable audit history.
  - Integrated into `UnifiedResearchIntelligenceView` (Section 2.9) with "Why this?" button on each recommendation card.
- **Strict Phase Boundary & Invariants**:
  - Zero ML models, zero LLMs, zero vector DBs, zero collaborative filtering, zero cross-user profiling.
  - 8 dedicated unit, integration, benchmark, and multi-tenant authorization tests passing (`test_personalization_transparency.py`); explanation latency benchmarked at $1.8\text{ ms}$ with zero N+1 queries.

#### Phase 5.10 — Faculty Research Opportunities & Project Postings [COMPLETE]
- **Platform-authored openings, distinct from ingested venues**: `ResearchPostingModel` holds research opportunities written *on* the platform by a faculty member — projects, available thesis topics, collaborations, lab rotations. Unlike a Phase 2 call for papers, a posting has a named academic owner who is accountable for it, a lifecycle that owner drives, and no ingestion provenance, deduplication or predatory-risk assessment, because there is no third-party source to distrust.
- **Deterministic lifecycle**: `DRAFT` → `OPEN` → `CLOSED` / `FILLED` / `CANCELLED` → `ARCHIVED`, every transition explicitly enumerated. `DRAFT` and `OPEN` are reversible while an author is still deciding, but `FILLED` and `CANCELLED` lead only to `ARCHIVED`: reopening a concluded search under the same posting would mislead applicants already rejected against it. Reopening preserves the original `published_at` and clears the stale closure timestamp.
- **Authorship and visibility**: only `FACULTY` and `ADMIN` accounts may author; only the author, or an administrator moderating, may modify. Only `OPEN` postings are publicly discoverable, and an unpublished draft is not merely hidden — its not-found error is indistinguishable from a nonexistent id, so probing cannot reveal that a competitor is preparing a position. Deletion is confined to drafts; a published posting must be cancelled and archived, leaving an audit trail.
- **Taxonomy integration**: `ResearchPostingTopicModel` mirrors `opportunity_topics`, so postings participate in the same canonical topic filtering as ingested venues rather than being matched on free text.
- **APIs & UI**: `/api/v1/postings` (+ `/mine`, `/mine/summary`, `/{id}`, `/{id}/transition`); Next.js `/postings` with discover and own-postings views, an authoring form, and `/postings/[id]`. Derived fields (`is_accepting_applications`, `days_until_deadline`, `allowed_transitions`) are computed server-side and only rendered by the client, so urgency and available actions cannot drift.
- **Migration `0026`**; 38 dedicated tests.

#### Phase 5.11 — Research Internships, RA Openings & Applications [COMPLETE]
- **Structured opening terms**: adds `INTERNSHIP`, `RESEARCH_ASSISTANTSHIP` and `POSTDOC`, plus compensation, commitment, hours, duration and eligibility. `UNPAID` is an explicit compensation type rather than a blank field the reader must interpret. On-platform applications are confined to these categories: enabling the flag on a supervisor-led posting would advertise a workflow the service refuses, so it is forced off rather than accepted and later contradicted.
- **Jointly owned applications**: `ResearchPostingApplicationModel`. The applicant owns the submission and may withdraw at any live stage; the author owns the review decision. Transition tables are partitioned by role and asserted not to overlap, so an applicant cannot shortlist themselves and an author cannot accept an offer on the applicant's behalf. `ACCEPTED`, `DECLINED`, `REJECTED` and `WITHDRAWN` stay distinct because a single closed state would erase whether the author or the candidate said no.
- **Idempotence and audit**: one application per researcher per posting; re-applying after withdrawal reuses the record so the author sees one continuous history rather than competing submissions, and the denormalized counter is not double-incremented. The status history is append-only, identical for both sides, and reassigned rather than mutated in place so SQLAlchemy cannot miss the JSON change and lose an audit entry.
- **Author privacy**: `reviewer_note` is withheld from the applicant's view, and an applicant supplying one is ignored rather than written into the record the author relies on. Applicants cannot enumerate rival applications; an unrelated researcher is told an application does not exist rather than that they may not see it.
- **Notifications** reuse the Phase 4.5 pipeline with a deterministic SHA-256 dedup key, so a retried request cannot produce two identical alerts. Each side is told only what concerns them.
- **APIs & UI**: `POST`/`GET /postings/{id}/applications`, `/postings/applications/mine(/summary)`, `GET` and `/transition` on an application. A posting read reports the reader's own application so the page shows its status instead of offering an Apply button that would be refused. Next.js gains an opening-terms panel, an apply form, an author review panel, and `/postings/applications`.
- **Migration `0027`** (round-tripped up/down/up on live PostgreSQL); 37 dedicated tests.

#### Phase 5.12 — Peer & Co-Author Discovery [COMPLETE]
- **Consent-first, because the thing matched is a person**: `ResearcherDiscoverySettingsModel` records opt-in. A researcher appears only if they set `is_discoverable`; no settings row means no consent, not a default, and reading one's own settings never creates one. A researcher who has *not* opted in may still search, because discoverability governs being found and requiring someone to publish themselves before they can look would be coercive. Institution and contact email are disclosed per field-level choice, enforced in a single serialization boundary so a field cannot leak via another response model. Email is off by default as the most consequential disclosure.
- **Deterministic, explainable matching**: `PeerMatchingEngine` is pure — no database, network, randomness or model inference — so identical inputs always yield an identical score, ordering and explanation. Weights live in `PeerMatchingConfig` and are asserted to sum to 1.0 at construction.
- **Two opposing topical signals, scored separately**: *shared expertise* (0.34) predicts that two researchers can understand each other; *complementary expertise* (0.26) predicts the collaboration yields something neither could alone. Optimizing only the first returns the researcher's own reflection; only the second returns strangers. Both are reported, alongside taxonomy proximity (0.18) for sibling fields with no literal overlap, methodology overlap (0.12) from declared keywords, and stated collaboration readiness (0.10). Cross-institution pairings get a mild preference, since a researcher already knows their own department — a nudge, never a filter.
- **Honest about evidence**: confidence is reported separately from score, because a thin profile can match highly by coincidence. Profiles below the topic minimum return `INSUFFICIENT_EVIDENCE` rather than inventing confidence from one accidental overlap, and an empty result says *which* problem applies — a thin profile, or nobody opted in — with actionable guidance. Profile keywords alone make a researcher matchable, so discovery is not limited to those with linked publications.
- **APIs & UI**: `GET`/`PATCH /researchers/{id}/discovery-settings`, `GET /researchers/{id}/peers` (filterable by collaboration interest and institution). Next.js `/peers` with a consent panel and per-match signal breakdown table.
- **Migration `0028`**; 35 dedicated tests. Taxonomy ancestors are derived from the stored topic tree, so matching cannot drift from the recorded taxonomy.

---

### 7. Platform Infrastructure, Governance & Security (Phase 6)
Core infrastructure, identity, security, access control, and correctness hardening.

#### 7.1 Authentication, Authorization & Identity [COMPLETE]
- **Single identity dependency** (`app/api/deps.py`): one place establishes who is calling. A signed HS256 bearer token from `/api/v1/auth/login` is the production mechanism; the raw `X-User-ID` header is honoured only under `AUTH_DEV_IDENTITY_ENABLED=true`, which is refused at startup when `APP_ENV=production`.
- **No fallback identity**: the five routers that each resolved an absent header to *the oldest user in the database* (87 handlers, silently acting as another researcher) were replaced by the shared dependency. Missing credentials are `401`, credentials resolving to no account are `401`, a non-owner is `403`.
- **Credentials**: bcrypt password hashing with a constant-work comparison for unknown accounts, so login latency does not disclose which emails are registered. Accounts predating Phase 6 carry a non-bcrypt placeholder and can never authenticate with a password.
- **Role-Based Access Control**: `STUDENT`, `FACULTY`, `ADMIN` enforced by a dependency factory; the user row is re-read per request so role changes and deactivation apply immediately. The global reminder dispatcher, previously callable anonymously, now requires `ADMIN`.
- **Ownership on previously open routes**: ten researcher routes — including an anonymous profile `PATCH` and anonymous reads of preferences and preference intelligence — now enforce owner authorization.
- **API protection**: login rate limiting, security headers, and forwarding headers honoured only behind a trusted proxy (`TRUST_PROXY_HEADERS`) so a caller cannot rotate them to evade limits.
- **Structured logging & observability**: JSON or text logging with a per-request correlation ID propagated as `X-Request-ID` and one access-log record per request.

#### 7.2 Database & Deployment Correctness [COMPLETE]
- **Long revision identifiers**: 19 of 25 migration IDs exceed Alembic's default `VARCHAR(32)` version column, so a fresh `alembic upgrade head` failed on the second revision and rolled back to zero tables. The version table is created or widened before migrating, in both `env.py` and `init.sql`, without renaming any existing revision.
- **Generated column mapping**: `fts_vector` is `GENERATED ALWAYS … STORED` in migration `0007` but was mapped as an ordinary nullable column, so every ORM insert sent `NULL` and PostgreSQL rejected it, blocking all WikiCFP, OpenAlex and Crossref ingestion. It is now mapped as database-owned (`FetchedValue`), which emits no DDL and so remains SQLite-safe for the test suite.
- **Missing migration**: the Phase 3.6 feedback and Phase 3.7 recommendation-history tables were added to the ORM without a migration, so the core recommendation endpoints returned `500` on PostgreSQL. Migration `0024` creates all three exactly as the models define them.
- **Regression coverage**: a PostgreSQL integration test runs `alembic upgrade head` against a real database and skips when none is reachable — the gap that let all three defects ship.

#### 7.3 Personalization Correctness Hardening [COMPLETE]
- **Live ranking consumes the full Phase 5 stack**: Phase 5.6 calibrations and Phase 5.7 contextual adaptations previously existed only in the explanation endpoints, so the explanation a researcher read could disagree with the ranking they were served. Both now flow into the live scorer under the same adaptive-learning consent gate, bounded as before (±0.05 and ±0.03 within the ±0.10 adaptive envelope, then the ≤0.15 personalization cap).
- **Researcher controls are authoritative everywhere**: the per-opportunity explanation endpoints receive the same control row the ranking honours, and behavioural signals are withheld when personalization, adaptive learning, or feedback learning is disabled.
- **Durable reset**: a reset records `personalization_reset_at` (migration `0025`). Interactions and feedback stay append-only for audit, but every derived-signal recomputation excludes pre-reset evidence, so a reset is no longer undone by the next recompute. Derived governance drift evaluations are cleared too, so a stale `SUSPEND` gate cannot outlive the reset.
- **Fail closed**: an unreadable control row disables personalization for that request and an unreadable governance gate damps to `HOLD`, rather than silently granting `ALLOW`. A table that was never created is distinguished from a failed read and correctly yields the documented defaults.
- **Effective risk reaches base ranking**: `opportunities.risk_score` is never written by ingestion, so the base quality signal's predatory penalty read a column fixed at `0.00`. The in-memory Phase 2.6 assessment from candidate generation now reaches the Phase 2 ranker, taking the stricter of the stored and assessed values.
- **Governance tracks its signals**: recomputing adaptive signals also refreshes the governance evaluation, instead of leaving the gate stale until a health endpoint is read.
- **Identifier validation**: `resolve_user_id` rejects an identifier matching no account and no profile rather than passing it through as an owner id.

#### 7.4 Demonstrability [COMPLETE]
- **Deterministic seeder** (`backend/scripts/seed_demo_data.py`): idempotent, offline, `--reset` and `--dry-run` supported. Creates three accounts covering every platform role with working credentials, explicit preferences including one exclusion, and twelve opportunities spanning conferences, journals and workshops with deadlines from already-expired to months away — two of which carry textual markers the Phase 2.6 engine independently scores as high risk, so trust and deadline intelligence have something to act on.

#### 7.5 Containerization & Deployment (Phase 6.1) [COMPLETE]
- **Full stack in Compose**: `postgres` (pinned `pgvector/pgvector:0.8.6-pg16`, TCP `pg_isready` healthcheck, named volume), a one-shot `migrate` service that waits for the database and runs `alembic upgrade head` exactly once, then `backend` and `frontend`, each gated on the previous step's health. A fresh volume reaches migration head `0028` and a healthy stack in under 30 seconds with no manual SQL.
- **Images**: the backend image (pinned `python:3.13.9-slim-bookworm`) installs the CPU-only torch build pinned to the tested version and leaves pytest out; the frontend image (pinned `node:24.13.1-bookworm-slim`) runs the Next.js standalone server without build tooling. Both run as unprivileged users; the backend source is not writable by its runtime user.
- **Secrets and configuration**: nothing secret is built into an image; `POSTGRES_PASSWORD` and `AUTH_SECRET_KEY` are required from `.env` and Compose refuses to start without them. Containers run with `APP_ENV=production`, so the developer `X-User-ID` header is refused. Each container receives only the variables it needs.
- **Hardening**: all capabilities dropped and `no-new-privileges` on the application containers, ports published on `127.0.0.1` only, allowlisted build contexts. Restarts and `down`/`up` keep data and sessions.
- **Environment templates**: the root `.env.example` configures Compose; `backend/.env.example` holds only backend settings, so a host-run backend no longer fails on keys its settings loader rejects.

#### 7.6 Scheduled Execution (Phase 6.3) [COMPLETE]
- **Five jobs, no new domain logic**: `deadline_expiry`, `reminder_dispatch`, `adaptive_signal_refresh`, `governance_refresh` and opt-in `opportunity_refresh` (WikiCFP) each call the existing service, commit where it leaves the transaction to its caller, and report what it did. Idempotency comes from the services' own deduplication and upserts; every job run twice leaves the database unchanged. Design: `docs/architecture/phase6-3-scheduler.md`.
- **Off by default**: `SCHEDULER_ENABLED=false` creates no task, thread or connection, so tests and the host development loop are unaffected. Network ingestion has its own switch, `SCHEDULER_OPPORTUNITY_REFRESH_ENABLED`.
- **Exclusion across processes**: each run takes a PostgreSQL advisory lock named after its job and skips if another process holds it. Each researcher's personalization work also takes a transaction-scoped lock, so adaptive and governance refresh cannot append the same governance transition twice (verified on PostgreSQL: 2 events without it, 1 with it).
- **Isolation and bounds**: runs execute in their own threads off the event loop, at most two at once. A failing job or researcher affects nothing else. Timeouts signal a stop at the next safe point, and a statement timeout bounds each database statement. Shutdown stops within 5 seconds.
- **Safety**: the scheduler reuses the services' P1-1 reset cutoff and P1-5/P1-8 governance behaviour and has no bypass. It only processes researchers whose Phase 5.9 controls leave the maintained state in use, and it never changes those controls.
- **Measured**: 20 SQL statements per researcher for adaptive refresh and 14 for governance, constant from 10 to 100 researchers and independent of interaction history. 40 dedicated tests.

#### 7.7 Deferred
- **Frontend authentication UI**: the backend auth API and the browser identity/token client exist, but there is no login, registration or administration page yet, so a browser session still bootstraps a developer identity.

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
