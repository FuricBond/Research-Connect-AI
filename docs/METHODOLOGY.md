# ResearchConnect AI — System Methodology & Engineering Architecture

**Document Type:** Technical Methodology Specification  
**Project:** ResearchConnect AI (Academic Intelligence & Discovery Platform)  
**Target Audience:** Academic Reviewers, Examiners, Engineering Team  
**Status:** Validated against Repository Implementation (Phases 1–5)

---

## 1. Research Philosophy & Methodological Framework

### 1.1 Core Problem Statement
In scholarly communication, researchers face fragmented venue discovery, deceptive/predatory publishing venues, deadline timezone confusion (e.g., Anywhere on Earth vs. UTC), and generic recommendations detached from their actual publication history.

### 1.2 Methodological Principles
Rather than deploying unexplainable, black-box deep learning models that suffer from data sparsity and hallucinations, ResearchConnect AI adheres to four foundational engineering principles:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                      CORE METHODOLOGICAL PRINCIPLES                     │
├──────────────────────────┬──────────────────────────────────────────────┤
│ 1. Complete Separation   │ Actionable calls (opportunities) are strictly │
│    of Domains            │ separated from canonical literature (works). │
├──────────────────────────┼──────────────────────────────────────────────┤
│ 2. Relevance Dominance   │ Core academic relevance must always account  │
│    Invariant (>= 85%)    │ for >= 85% of total ranking weight.         │
├──────────────────────────┼──────────────────────────────────────────────┤
│ 3. Deterministic &       │ Every score, tie-break, and recommendation   │
│    Auditable Logic       │ has an explicit mathematical audit trail.    │
├──────────────────────────┼──────────────────────────────────────────────┤
│ 4. Governed Adaptation   │ Behavioral feedback cannot override explicit │
│    with Hysteresis       │ exclusions; 5-state FSM prevents drift.     │
└──────────────────────────┴──────────────────────────────────────────────┘
```

---

## 2. Data Acquisition & Knowledge Engineering Methodology

The platform ingests, normalizes, and disambiguates scholarly data from three distinct sources across two isolated functional layers:

```text
                               DATA ACQUISITION PIPELINE
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
       [WikiCFP]                     [OpenAlex]                     [Crossref]
  Call for Papers (HTML)       Scholarly Works & Authors      Authoritative DOIs & Dates
            │                             │                             │
            ▼                             ▼                             ▼
  BeautifulSoup4 Scraper        Abstract Reconstruction           DOI Canonicalizer
  (scrapers/wikicfp/)           (scrapers/openalex/)          (scrapers/crossref/)
            │                             │                             │
            ▼                             └──────────────┬──────────────┘
    [OPPORTUNITIES]                                      ▼
  opportunities table                        [RESEARCH KNOWLEDGE LAYER]
  - Conference tracks                        - research_works (DOI, vector)
  - Submission deadlines                     - researchers (ORCID, metrics)
  - Delivery modes                           - institutions (ROR, country)
                                             - research_work_authors
```

### 2.1 Domain Separation Methodology
- **`opportunities` Table**: Stores actionable future calls (conferences, journals, workshops) with deadlines, tracks, and submission guidelines.
- **`research_works` Table**: Stores past peer-reviewed publications. Literature and actionable calls are never mixed into the same relational table.

### 2.2 Entity Disambiguation & Canonicalization
1. **DOI Canonicalization Algorithm** (`scrapers/crossref/doi_utils.py`):
   - Strips HTTP schemes and resolver prefixes (`https://doi.org/`, `http://dx.doi.org/`, `doi:`).
   - URL-decodes safe entities (`%2F` $\rightarrow$ `/`).
   - Normalizes directory prefix (`10.xxxx/`) to lowercase while preserving case-sensitive suffix characters.
   - Cleans accidental trailing punctuation (dots, slashes, whitespace).
2. **Abstract Inverted Index Reconstruction** (`scrapers/openalex/abstract_utils.py`):
   - OpenAlex encodes abstracts as inverted index maps (`{"word": [pos1, pos2]}`).
   - The engine reconstructs these into clean, continuous prose for semantic embedding generation and full-text search indexing.
3. **Canonical Identifiers**:
   - **ORCID** (`0000-xxxx-xxxx-xxxx`): Used for globally unique author disambiguation, preventing homonym collisions.
   - **ROR** (`https://ror.org/...`): Standardizes institution identities, eliminating naming variants (e.g., "MIT" vs. "Massachusetts Institute of Technology").

### 2.3 4-Tier Researcher Identity Architecture
To support students, faculty, and administrators without duplicating author profiles:
$$\text{UserModel} \xrightarrow{\text{1:1}} \text{ResearchProfileModel} \xrightarrow{\text{N:1}} \begin{cases} \text{ResearcherModel (Canonical Author)} \\ \text{InstitutionModel (Canonical Institution)} \end{cases}$$

- `UserModel`: Manages login credentials, password hashing, and system roles (`STUDENT`, `FACULTY`, `ADMIN`).
- `ResearchProfileModel`: Stores user bio, academic status, and fallback strings.
- `ResearcherModel`: Maps to the global OpenAlex author record (`A...`) with verified citation counts.
- `InstitutionModel`: Maps to canonical ROR institutional registries.

---

## 3. Multi-Channel Retrieval Methodology

When a literature search or recommendation query is executed, the platform queries three orthogonal retrieval channels:

```text
                                  INPUT QUERY / RESEARCHER PROFILE
                                                 │
            ┌────────────────────────────────────┼────────────────────────────────────┐
            ▼                                    ▼                                    ▼
   [Channel 1: Dense Vector]           [Channel 2: Lexical FTS]           [Channel 3: Topic DAG]
- all-MiniLM-L6-v2 (384-dim)        - PostgreSQL tsvector              - Canonical Topic IDs
- L2-normalized embedding           - Weighted fields:                 - Taxonomy hierarchy proximity
- pgvector Cosine Distance (<=>)      Title (A: 1.0), Abstract (B: 0.4) - Alias expansion
            │                                    │                                    │
            └────────────────────────────────────┼────────────────────────────────────┘
                                                 │
                                                 ▼
                               [Reciprocal Rank Fusion (RRF)]
                                        k = 60 constant
                                                 │
                                                 ▼
                                      FUSED CANDIDATE POOL
```

### 3.1 Channel 1: Dense Vector Retrieval (pgvector)
- **Model**: `all-MiniLM-L6-v2` via `sentence-transformers` (384 dimensions, local CPU inference).
- **Storage**: Custom `Vector(384)` user-defined SQLAlchemy type mapped to native PostgreSQL `vector(384)`.
- **Distance Metric**: Cosine similarity via `<=>` operator:
  $$\text{Cosine Distance}(u, v) = 1 - \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
- **Change Detection**: Each work and opportunity maintains a `content_hash` (SHA-256 of title + abstract) to eliminate redundant embedding re-computations.

### 3.2 Channel 2: Full-Text Search (PostgreSQL GIN)
- **Engine**: Native PostgreSQL `tsvector` with GIN indexing (`0007_phase2_4i_fts_gin_indexes.py`).
- **Weighting**: Title terms are assigned weight **A** (1.0); abstract terms are assigned weight **B** (0.4).
- **Query Parsing**: Employs `websearch_to_tsquery` to support boolean operators, exact phrase quotes, and hyphenated exclusions.

### 3.3 Channel 3: Canonical Topic Taxonomy DAG
- **Graph Traversal**: Topics are organized in a Directed Acyclic Graph (DAG) with parent-child hierarchical relations.
- **Proximity Expansion**: Query terms expand across mapped aliases (`TopicAliasModel`) and immediate taxonomy parents/children to capture conceptual synonyms.

### 3.4 Candidate Fusion via Reciprocal Rank Fusion (RRF)
Candidates discovered across channels are fused into a unified pool using RRF with smoothing constant $k = 60$:
$$RRF(d) = \sum_{c \in \text{Channels}} \frac{1}{k + r_c(d)}$$
where $r_c(d)$ is the 1-based rank of candidate $d$ in channel $c$.

---

## 4. Trust, Predatory Risk, & Temporal Intelligence Methodology

Before opportunities enter the ranking engine, they pass through two specialized intelligence filters:

### 4.1 Predatory Risk Intelligence Engine (`RiskScoringEngine`)
The risk engine audits venue trustworthiness across four heuristic dimensions:
1. **Indexing Verification**: Checks inclusion in verified academic registries (DOAJ, Scopus, Web of Science, DBLP).
2. **Publisher & ISSN Integrity**: Audits linking ISSNs (`issn_l`) against flagged lists and hijacked domain databases.
3. **Editorial Timeline Plausibility**: Detects unrealistically rapid turnaround promises (e.g., *"peer review in 48 hours"*).
4. **Scoring Output**: Generates a continuous score $S_{\text{risk}} \in [0.0, 1.0]$ and categorizes candidates into:
   - `LOW_RISK` ($S_{\text{risk}} < 0.35$)
   - `MEDIUM_RISK` ($0.35 \le S_{\text{risk}} < 0.70$)
   - `HIGH_RISK` ($S_{\text{risk}} \ge 0.70$)
   - **Safety Invariant**: Any candidate with $S_{\text{risk}} \ge 0.70$ or `is_predatory_flag == True` receives **zero personalization adjustment** ($P_{\text{adj}} = 0.0$).

### 4.2 Deadline Intelligence & Urgency Engine (`DeadlineNormalizer`)
1. **Timezone Normalization**:
   - Academic CFPs frequently use *Anywhere on Earth* (AoE / UTC-12:00).
   - The normalizer detects timezone tokens, translates AoE, UTC, and regional offsets into ISO 8601 UTC timestamps, and prevents premature deadline expiration.
2. **Multi-Deadline Milestone Parsing**:
   - Separates abstract registration, full paper submission, author notification, and camera-ready deadlines.
3. **Temporal Urgency Curve**:
   $$\text{Urgency}(t) = \max\left(0.0, \min\left(1.0, 1.0 - \frac{\text{Days Remaining}}{90.0}\right)\right)$$
   Opportunities with deadlines within 90 days receive an urgency weight in ranking; expired opportunities ($\text{Days Remaining} < 0$) are filtered out.

---

## 5. Hybrid Ranking Methodology

The hybrid ranking engine (`backend/app/ranking/hybrid_ranker.py`) synthesizes candidate features into a single, deterministic score.

```text
[Candidate Pool] ──► [HybridRanker]
                           │
  ┌────────────────────────┴────────────────────────┐
  ▼                                                 ▼
Core Relevance Signals (>= 85%)           Secondary Signals (<= 15%)
- Semantic Embedding Match (0.40)         - Deadline Urgency (0.05)
- Full-Text Lexical Match (0.25)          - Publication Freshness (0.05)
- Topic DAG Overlap (0.20)                - Venue/Indexing Quality (0.05)
  │                                                 │
  └────────────────────────┬────────────────────────┘
                           │
                           ▼
                  Phase 2 Base Score (R0)
                           │
                           ▼
              [Relevance Damping Filter]
                           │
                           ▼
            Phase 3.5 Personalization Ranker
              Bounded Adjustment (<= 0.15)
                           │
                           ▼
              [Deterministic Tie-Breaking]
                           │
                           ▼
               Final Ranked Recommendations
```

### 5.1 Relevance Dominance Invariant
To prevent commercial, urgent, or popular calls from displacing academically relevant venues:
$$\sum w_{\text{relevance}} = w_{\text{semantic}} + w_{\text{lexical}} + w_{\text{topic}} \ge 0.85$$
$$\sum w_{\text{secondary}} = w_{\text{type}} + w_{\text{freshness}} + w_{\text{urgency}} + w_{\text{quality}} \le 0.15$$

### 5.2 Continuous Relevance Damping
To ensure that broad preferences cannot artificially boost irrelevant candidates:
$$\text{Damping}(S_{\text{base}}) = \begin{cases} 
1.0 & \text{if } S_{\text{base}} \ge 0.30 \\
0.20 + 0.80 \times \left(\frac{S_{\text{base}}}{0.30}\right) & \text{if } S_{\text{base}} < 0.30 
\end{cases}$$

### 5.3 Composite Scoring Formula
$$P_{\text{adjustment}} = \min(0.15, S_{\text{personalization\_raw}} \times 0.15 \times \text{Damping})$$
$$\text{Final Score} = \min(1.0, \max(0.0, S_{\text{base}} + P_{\text{adjustment}}))$$

### 5.4 Deterministic Tie-Breaking
Every list is sorted using an immutable tuple, ensuring 100% reproducibility:
$$\text{Sort Key} = \left(-\text{final\_score}, -\text{urgency\_score}, \text{str}(\text{opportunity\_id})\right)$$

---

## 6. Governed Personalization & Adaptive Telemetry Methodology (Phase 5)

Phase 5 establishes a complete, closed-loop personalization and safety architecture:

```text
                          PHASE 5 PERSONALIZATION CYCLE
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
   [5.1 & 5.2: Explicit]        [5.4: Telemetry]             [5.9: Controls]
  Researcher Preferences      Append-Only Interactions     Master / Adaptive Toggles
  PREFERRED / EXCLUDED /      VIEWED, SAVED, APPLIED,      Safe State Reset
  NEUTRAL                     DISMISSED                    (state_version += 1)
           │                            │                            │
           ▼                            ▼                            │
   [5.3: Scoring]               [5.5: Adaptive Signals]              │
  PersonalizationScorer       Exponential Time Decay       │
  Dimension breakdowns        Bounded in [-0.08, +0.08]              │
           │                            │                            │
           │                            ▼                            │
           │                    [5.6: Calibration]                   │
           │                  Outcome Attribution                    │
           │                  Bounded in [-0.05, +0.05]              │
           │                            │                            │
           │                            ▼                            │
           │                    [5.7: Quality Check]                 │
           │                  NDCG / MRR / Precision                 │
           │                  Contextual Modifiers                   │
           │                            │                            │
           └────────────────────────────┼────────────────────────────┘
                                        │
                                        ▼
                         [5.8: Governance Decision Gate]
                          5-State FSM with Hysteresis
                         ALLOW / BOUNDED / HOLD / REDUCE / SUSPEND
```

### 6.1 Telemetry Ingestion & Time Decay
Interactions are persisted in `researcher_interactions` with pre-assigned weights:
- `APPLIED`: $+1.0$ | `INTERESTED`: $+0.8$ | `SAVED`: $+0.6$ | `VIEWED`: $+0.05$
- `DISMISSED`: $-0.5$ | `NOT_INTERESTED`: $-0.7$ | `HIDDEN`: $-0.9$

Adaptive signal strength applies exponential half-life decay ($T_{1/2} = 30\text{ days}$):
$$\lambda = \frac{\ln(2)}{30} \approx 0.0231 \implies w(t) = w_0 \cdot e^{-\lambda \cdot \Delta t}$$

### 6.2 The 5-State Governance Finite State Machine (FSM)
To prevent algorithmic drift and echo chambers, the `PersonalizationGovernanceEngine` manages adaptation states:

```text
               ┌──────────────────────┐
               │        ALLOW         │ (100% adaptation)
               └──────────┬───────────┘
                          │ Drift detected
                          ▼
               ┌──────────────────────┐
               │    ALLOW_BOUNDED     │ (50% adaptation)
               └──────────┬───────────┘
                          │ Insufficient recent evidence (N < 3)
                          ▼
               ┌──────────────────────┐
               │         HOLD         │ (25% adaptation)
               └──────────┬───────────┘
                          │ Quality degradation detected
                          ▼
               ┌──────────────────────┐
               │        REDUCE        │ (10% adaptation)
               └──────────┬───────────┘
                          │ Critical conflict / persistent drift
                          ▼
               ┌──────────────────────┐
               │       SUSPEND        │ (0% adaptation; neutral fallback)
               └──────────────────────┘
```

- **Hysteresis Guarantee**: A single negative interaction cannot trigger `SUSPEND`. Recovery from `SUSPEND` requires at least 5 consecutive stable interactions ($N \ge 5$) and transitions to `ALLOW_BOUNDED`, never directly to `ALLOW`.

### 6.3 Safe State Reset Methodology
When a researcher resets personalization (`/personalization/reset`):
1. Increments `personalization_state_version` (e.g., $1 \rightarrow 2$).
2. Deletes derived tables: `adaptive_preference_signals`, `personalization_calibrations`, `personalization_contextual_adaptations`.
3. Preserves `UserModel`, `ResearchProfileModel`, `ResearcherPreferenceModel` (explicit rules), and historical audit logs.

---

## 7. Post-Discovery Research Workflow Methodology (Phase 4)

Once an opportunity is selected, the platform guides the researcher through proposal development:

```text
[Opportunity Discovered]
           │
           ▼
[4.1: Opportunity Workspace] ──► Kanban State: SAVED ──► IN_PROGRESS ──► SUBMITTED
           │
           ├──────────────────────────────────────────┐
           ▼                                          ▼
[4.2 & 4.3: Submission & Documents]         [4.4: Calendar Engine]
- ResearchSubmissionModel                  - ResearchCalendarModel
- SHA-256 versioned uploads                - Milestones: Abstract, Paper, Camera-Ready
- SubmissionReadinessEngine Audit          - RFC 5545 iCal Feed (.ics export)
           │                                          │
           ├──────────────────────────────────────────┘
           ▼
[4.5 & 4.6: Collaboration & Reminders]
- Role-Based Access Control (OWNER, EDITOR, VIEWER)
- Collaborative tasks & assignment
- Automated offset reminders (T-14d, T-7d, T-24h)
```

1. **Document Integrity**: Manuscript drafts uploaded to `submission_documents` generate a SHA-256 hash in `ResearchSubmissionDocumentVersionModel`, providing immutable provenance.
2. **Submission Readiness Gating**: The `SubmissionReadinessEngine` verifies that mandatory documents (blinded manuscript, author declaration) exist and meet size/format constraints before permitting state transition to `SUBMITTED`.
3. **iCalendar Engine**: Generates RFC 5545 compliant `.ics` feeds directly from database milestones for synchronization with external calendar clients.

---

## 8. Verification, Performance, & Testing Methodology

### 8.1 Zero N+1 Query Architecture
To guarantee bounded latency during large batch retrievals:
1. **SQLAlchemy `selectinload`**: Used for 1:N and M:N relationships (e.g., loading submissions and document versions), executing a single secondary `IN (...)` query.
2. **SQLAlchemy `joinedload`**: Used for N:1 relationships (e.g., loading parent opportunity topics).
3. **In-Memory Dictionary Indexing**: Loading all candidate entities in one SQL pass and mapping them into lookup dictionaries (`{id: entity}`) in Python memory.

### 8.2 In-Memory Caching & Rate Limiting
- **Cache**: `DiscoveryResponseCacheMiddleware` provides thread-safe, TTL-based (60s) LRU caching with standard `X-Cache: HIT/MISS` headers for read-only GET discovery requests.
- **Rate Limiting**: `DiscoveryRateLimitMiddleware` enforces token-bucket rate limiting (60 requests/minute per client IP) to prevent denial of service.

### 8.3 Invariant & Regression Testing Suite
The repository contains **87 Pytest test files** enforcing architectural invariants:

| Test Category | Target Module | Invariant Enforced |
|---|---|---|
| **Relevance Dominance** | `test_hybrid_ranker.py` | Relevance weights $\ge 0.85$; secondary $\le 0.15$. |
| **Personalization Cap** | `test_personalization_ranking.py` | Adjustment $\le 0.15$; relevance damping below $0.30$. |
| **Predatory Gate** | `test_phase2_6g_risk_evaluation.py` | Predatory flag forces adjustment to $0.0$. |
| **Timezone UTC** | `test_date_timezone_normalization.py` | AoE properly converted to UTC-12:00. |
| **Governance FSM** | `test_personalization_governance.py` | Hysteresis buffers; recovery requires $N \ge 5$. |
| **Submission Readiness**| `test_phase4_3_invariants.py` | State machine transitions blocked if documents missing. |
| **Zero N+1 Query** | `test_phase4_7_research_intelligence_integration.py` | Constant query count regardless of candidate batch size. |

---

## 9. Current Technical Limitations & Audit Evidence

In accordance with rigorous academic integrity standards, limitations are documented as they are found and struck through as they are resolved.

### 9.1 Resolved by the Phase 6 hardening pass

1. **Phase 5 Live Gateway Disconnect** — *Resolved.* `PersonalizationRankingService` now loads the researcher's Phase 5.9 control row, the Phase 5.8 governance gate, Phase 5.5 adaptive signals, Phase 5.6 calibrations and Phase 5.7 contextual adaptations, and passes all of them through `PersonalizationRanker` into `PersonalizationScorer`. Disabling personalization, or disabling adaptive learning, now changes live ranking, and the per-opportunity explanation endpoints receive the same control row so an explanation cannot claim influence the ranking did not apply.
2. **Development Header Authentication** — *Resolved.* Identity is established in one place (`app/api/deps.py`). A signed bearer token from `/api/v1/auth/login` is the production mechanism; the raw `X-User-ID` header is honoured only when `AUTH_DEV_IDENTITY_ENABLED=true`, which is refused at startup when `APP_ENV=production`. Missing credentials return `401`, credentials resolving to no account return `401`, and a mismatched owner returns `403`. There is no fallback identity.
3. **Reset Telemetry Windowing** — *Resolved.* A reset records `researcher_personalization_settings.personalization_reset_at` (migration `0025`). Interaction and feedback rows remain append-only for audit, but adaptive-signal recomputation and behavioural aggregation both exclude evidence at or before the cutoff, so a reset is a durable cold start rather than one that the next recompute undoes.
4. **Inert risk gate in personalized ranking** — *Resolved.* `opportunities.risk_score` is never written by ingestion, so the base quality signal's predatory penalty was reading a column fixed at `0.00`. The effective in-memory Phase 2.6 assessment computed during candidate generation is now what reaches the Phase 2 ranker, taking the stricter of the stored and assessed values.
5. **Governance and control lookups failing open** — *Resolved.* A failed read of the control row now disables personalization for that request, and a failed governance read damps to `HOLD` rather than granting the unrestricted `ALLOW` multiplier. A table that was never created is treated differently from a failed read: it means the feature is not deployed in that schema, so the documented defaults apply.
6. **Governance recomputed only on reads** — *Resolved.* Recomputing adaptive signals now also refreshes the governance evaluation, so the gate that damps live ranking tracks the behaviour it governs instead of waiting for somebody to open the health endpoint. A governance failure is logged and never discards a valid signal recomputation.
7. **Unvalidated identifier pass-through** — *Resolved.* `WorkspaceService.resolve_user_id` rejects an identifier matching no account and no profile instead of returning it unchanged, which previously allowed workspace rows owned by a non-existent account.
8. **No demo dataset** — *Resolved.* `backend/scripts/seed_demo_data.py` writes a deterministic, idempotent corpus: three accounts covering every platform role with bcrypt-hashed credentials, explicit preferences including one exclusion, and twelve opportunities spanning conferences, journals and workshops with deadlines from already-expired to months away, two of which carry the textual markers the Phase 2.6 engine independently scores as high risk.

### 9.2 Known remaining limitations

1. **Explicit exclusions suppress personalization but do not demote relevance**: an opportunity matching an `EXCLUDED` preference receives no personalization boost and its final score equals its base relevance score, so a highly relevant excluded venue can still appear in a ranked list. This is the behaviour the Phase 5 safety invariants specify and assert; changing exclusion to filter or demote is a deliberate product decision that would require re-specifying those invariants.
2. **Client-asserted identity in developer mode**: when `AUTH_DEV_IDENTITY_ENABLED=true`, knowing a UUID is sufficient to act as that user. This is intended for local development only and is refused in production configuration.
3. **Semantic embeddings are generated offline**: vector retrieval requires `python -m ml.embeddings.generate_embeddings` after ingestion or seeding; the seeder deliberately does not generate embeddings, as that requires a model download.
4. **No scheduled execution**: deadline reminders and governance recomputation are triggered by an administrator endpoint and by adaptive recomputation respectively. There is no background scheduler.
5. **Performance-budget tests are machine-sensitive**: a small number of wall-clock assertions (`test_ranking_execution_budget`, `test_performance_and_scaling_benchmarks`) can fail under CPU contention while passing on a quiet machine.

---

## 10. Summary Specification Table

| Architectural Feature | Implementation Specification in Repository |
|---|---|
| **Frontend Architecture** | Next.js 15.3.3 (App Router), React 19, TypeScript 5.7, Vanilla CSS Tokens |
| **Backend Architecture** | FastAPI 0.115.6, Python 3.12, Layered Domain Architecture |
| **Database & ORM** | PostgreSQL 16, pgvector 0.3.6, SQLAlchemy 2.0.36, Alembic 1.14 (23 revisions) |
| **Dense Embedding Model** | `all-MiniLM-L6-v2` (384 dimensions, sentence-transformers 3.3.1) |
| **Retrieval Fusion** | Reciprocal Rank Fusion (RRF, $k=60$) over Vector + Lexical (tsvector GIN) |
| **Core Ranking Law** | Relevance Dominance Invariant ($w_{\text{relevance}} \ge 0.85$, $w_{\text{secondary}} \le 0.15$) |
| **Personalization Cap** | Max adjustment $\le 0.15$, Damping threshold $S_{\text{base}} < 0.30$, Tie-breaking tuple |
| **Governance Machine** | 5-State FSM (`ALLOW`, `ALLOW_BOUNDED`, `HOLD`, `REDUCE`, `SUSPEND`) with Hysteresis |
| **Workflow Management** | Proposal Kanban, Document Versioning (SHA-256), Readiness Engine, RFC 5545 iCal |
| **Verification Suite** | 87 Pytest test suites enforcing unit correctness, security, and mathematical invariants |
