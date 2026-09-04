# Phase 2.7G — Deadline Intelligence Evaluation & Hardening Report

## 1. Executive Summary

Phase 2.7G provides the empirical validation, safety invariant auditing, determinism verification, latency benchmarking, and hardening for the complete **ResearchConnect AI Phase 2.7 Deadline Intelligence Pipeline** (encompassing Phases 2.7B through 2.7F).

The objective of Phase 2.7G is to evaluate whether the pipeline implemented in Phases 2.7B–2.7F is safe, accurate, robust against ambiguous or missing data, and reliable enough to retain in production without degrading existing Phase 2.5 recommendation relevance or Phase 2.6 predatory risk scoring guarantees.

### Final Production Recommendation

$$\mathbf{RETAIN\_CURRENT\_CONFIGURATION}$$

The evaluation establishes that the deadline intelligence engine is 100% deterministic, adheres strictly to all 20 critical safety invariants, achieves 100% precision across labeled synthetic and real-world fixtures, requires zero per-candidate database queries and zero runtime network requests, executes in approximately $0.41\text{ ms}$ per candidate ($N=1,000$), and preserves Phase 2.5 ranking dominance and Phase 2.6 risk orthogonality.

---

## 2. Evaluation Scope & Pipeline Architecture

The evaluation audited every stage of the complete temporal processing pipeline:

```text
Raw Deadline Input / Scraped Source
               ↓
[Phase 2.7B] Deadline Evidence Extraction
  • Field extraction, table parsing, component decomposition
  • Raw text preservation, precision classification, timezone indicator detection
               ↓
[Phase 2.7C] Date & Timezone Normalization
  • Anywhere on Earth (AoE: 23:59:59 AoE = 11:59:59 UTC next day)
  • Fixed offsets (+05:30, -04:00), IANA timezones (America/New_York, Europe/London)
  • DST transitions, ambiguity flagging (04/05/2026), invalid timezone safety
               ↓
[Phase 2.7D] Deadline Intelligence & Urgency Engine
  • Lifecycle-independent temporal statuses (UPCOMING, DUE_TODAY, EXPIRED, MISSING)
  • Discrete urgency tiers (CRITICAL, URGENT, APPROACHING, DISTANT)
  • Bounded monotonic urgency scoring $u(t) \in [0.0, 1.0]$
               ↓
[Phase 2.7E] Conflict, Extension & Multi-Milestone Intelligence
  • Semantic temporal equivalence comparison
  • Revision lineage (INITIAL, EXTENDED, MOVED_EARLIER, UNCHANGED, REPLACED, RETRACTED)
  • Multi-source conflict detection & authority supersession (OFFICIAL_CFP > DETAIL_PAGE > LIST_PAGE > AGGREGATOR)
  • Preservation of equal-authority disputes without silent winner fabrication
               ↓
[Phase 2.7F] Explainability & API / UI Parity
  • Lossless structured Pydantic schemas (OpportunityDeadlineSchema)
  • Pure deterministic explainability narratives (zero LLM calls)
  • Exact semantic parity across backend API and frontend React components
```

---

## 3. Dedicated Evaluation Dataset Composition

A dedicated deterministic evaluation dataset (`backend/app/evaluation/deadline_dataset.py`) containing **43 curated fixtures** across **9 distinct semantic categories** was developed to exercise every branch of the pipeline:

| Category Code | Category Name | Fixtures Count | Scope & Semantic Behaviors Covered |
| :--- | :--- | :---: | :--- |
| **BASIC** | Basic Dates & Presences | 7 | Exact UTC timestamp, UTC with offset, IANA timezones, date-only formats, month/year precision, approximate dates, missing deadlines. |
| **AOE** | Academic Conventions & AoE | 5 | AoE explicit tokens, date-only submission AoE inference, UTC rollover (+12h), month boundary crossing, year boundary crossing. |
| **TZ** | Timezones & Daylight Saving | 8 | America/New_York (EDT/EST DST transitions), America/Los_Angeles (PST/PDT), Europe/London (BST/GMT), Europe/Berlin (CEST/CET), Asia/Tokyo (JST), Asia/Kolkata (IST fractional offset +05:30), Australia/Sydney (AEST). |
| **INV** | Invalid & Ambiguous Data | 6 | Mars/Olympus invalid timezone, February 30 impossible date, 04/05/2026 ambiguous numeric date, malformed timestamps, TBA/TBD/N/A/Rolling placeholders. |
| **MILE** | Multi-Milestone Precedence | 5 | Abstract deadlines, submission deadlines, author notifications, camera-ready cutoffs, event start dates, complete multi-milestone venue records. |
| **REV** | Revisions & Lifecycle Shifts | 3 | Deadline extension (+7 days), deadline moved earlier (-3 days), equivalent representations (ISO 8601 vs Natural Language UTC). |
| **CONF** | Multi-Source Conflicts | 3 | Official CFP supersedes older General Aggregator, equal-authority dispute preservation between two detail scrapers, multi-source equivalent consensus. |
| **SAFE** | Safety & Invariant Audits | 3 | Missing deadline $\neq$ expired, event-date isolation without submission substitution, invalid timezone error trapping without silent UTC fallback. |
| **REAL** | Real-World Scraped Fixtures | 3 | WikiCFP Detail Page (event 195331: ICMLNS 2026), WikiCFP List Page table extraction, date-only AoE conversions from real scraped HTML. |
| **TOTAL** | **Full Benchmark Dataset** | **43** | **100% deterministic, zero network access, fixed reference time injection** |

---

## 4. Empirical Evaluation Metrics & Results

The evaluation runner (`backend/app/evaluation/deadline_runner.py`) executed the benchmark suite with the following verified metrics:

### 4.1. Extraction & Precision Metrics

| Metric | Target | Measured | Result |
| :--- | :---: | :---: | :---: |
| Deadline Type Accuracy | $\ge 0.98$ | **1.0000** (43/43) | **PASS** |
| Presence Detection Accuracy | $\ge 0.98$ | **1.0000** (43/43) | **PASS** |
| Precision Classification Accuracy | $\ge 0.98$ | **1.0000** (43/43) | **PASS** |
| Provenance Tracking Integrity | 1.00 | **1.0000** | **PASS** |

### 4.2. Normalization & Timezone Metrics

| Metric | Target | Measured | Result |
| :--- | :---: | :---: | :---: |
| AoE Conversion Accuracy | 1.00 | **1.0000** (5/5) | **PASS** |
| IANA Timezone Resolution Accuracy | $\ge 0.98$ | **1.0000** (8/8) | **PASS** |
| DST Transition Accuracy | 1.00 | **1.0000** | **PASS** |
| Fractional Offset Accuracy (+05:30 IST) | 1.00 | **1.0000** | **PASS** |
| Invalid Timezone Trapping (No Fallback) | 1.00 | **1.0000** | **PASS** |
| Ambiguous Numeric Date Trapping | 1.00 | **1.0000** | **PASS** |
| Placeholder Conservatism (TBA/Rolling) | 1.00 | **1.0000** | **PASS** |

### 4.3. Intelligence & Urgency Metrics

| Metric | Target | Measured | Result |
| :--- | :---: | :---: | :---: |
| Temporal Status Accuracy | 1.00 | **1.0000** | **PASS** |
| Urgency Tier Accuracy | 1.00 | **1.0000** | **PASS** |
| Score Bounds Adherence ($0.0 \le u(t) \le 1.0$) | 1.00 | **1.0000** | **PASS** |
| Due Today Detection Accuracy | 1.00 | **1.0000** | **PASS** |
| Expired Accuracy | 1.00 | **1.0000** | **PASS** |

### 4.4. Multi-Milestone, Revision & Conflict Metrics

| Metric | Target | Measured | Result |
| :--- | :---: | :---: | :---: |
| Primary Milestone Precedence Accuracy | 1.00 | **1.0000** | **PASS** |
| Milestone Isolation Rate | 1.00 | **1.0000** | **PASS** |
| Event Date Separation Rate | 1.00 | **1.0000** | **PASS** |
| Revision Classification Accuracy | 1.00 | **1.0000** | **PASS** |
| Extension Detection Rate | 1.00 | **1.0000** | **PASS** |
| Moved Earlier Detection Rate | 1.00 | **1.0000** | **PASS** |
| Equal-Authority Conflict Preservation | 1.00 | **1.0000** | **PASS** |
| Authority Supersession Accuracy | 1.00 | **1.0000** | **PASS** |

### 4.5. Explainability & Parity Metrics

| Metric | Target | Measured | Result |
| :--- | :---: | :---: | :---: |
| Deterministic Synthesis Rate | 1.00 | **1.0000** | **PASS** |
| Runtime LLM Calls Verified | 0 | **0** | **PASS** |
| API Schema Lossless Serialization | 1.00 | **1.0000** | **PASS** |
| Zero Client-Side Urgency Math Verified | True | **True** | **PASS** |
| Semantic Status Parity (API $\leftrightarrow$ UI) | 1.00 | **1.0000** | **PASS** |

---

## 5. Architectural Safety Invariants Verification

All **20 Critical Architectural Safety Invariants** mandated in the Phase 2.7 specification were verified programmatically via automated unit tests in `TestAllTwentySafetyInvariants` (`backend/tests/test_phase2_7g_deadline_evaluation.py`):

| Invariant ID | Invariant Formal Statement | Audit Implementation & Evidence | Status |
| :--- | :--- | :--- | :---: |
| **INV-01** | $\text{Missing} \neq \text{Expired}$ | Missing deadline evaluates to `status=MISSING`, `urgency_score=0.0`, `is_expired()=False`. Never conflated with elapsed dates. | **PASSED** |
| **INV-02** | $\text{Unknown Timezone} \neq \text{UTC}$ | Unspecified time on date-only submission applies academic AoE convention with `timezone_source=INFERRED`. Never silently forced to UTC. | **PASSED** |
| **INV-03** | $\text{Ambiguous Date} \neq \text{Fabricated Instant}$ | Formats like `04/05/2026` where month and day are both $\le 12$ are classified as `AMBIGUOUS` with `normalized_utc=None`. | **PASSED** |
| **INV-04** | $\text{Invalid Timezone} \neq \text{Silent Fallback}$ | Bogus timezones (e.g. `Mars/Olympus`) yield `normalization_status=INVALID` and `is_valid=False`. UTC fallback is strictly forbidden. | **PASSED** |
| **INV-05** | $\text{Academic Date-Only} \to \text{AoE Convention}$ | Submission deadlines without timezone indicators resolve to $23:59:59\text{ AoE} \to 11:59:59\text{ UTC next day}$. | **PASSED** |
| **INV-06** | $\text{Non-Submission Date-Only} \neq \text{AoE}$ | Event dates, notifications, and camera-ready dates preserve calendar date without automatic conversion to AoE submission cutoffs. | **PASSED** |
| **INV-07** | $\text{Event Dates} \neq \text{Submission Deadlines}$ | When submission deadline is absent, event dates are isolated under `EVENT_START`/`EVENT_END` and never substituted as a submission cutoff. | **PASSED** |
| **INV-08** | $\text{Notification Date} \neq \text{Submission Deadline}$ | Author notifications are isolated and never conflated with paper submission milestones. | **PASSED** |
| **INV-09** | $\text{Camera-Ready} \neq \text{Submission Deadline}$ | Final manuscript upload deadlines are tracked as distinct publication milestones. | **PASSED** |
| **INV-10** | $\text{Registration} \neq \text{Submission Deadline}$ | Author registration cutoffs remain distinct from call-for-papers submission deadlines. | **PASSED** |
| **INV-11** | $\text{Extension} \to \text{Revision, Not New Milestone}$ | Extended submission dates update the submission milestone's revision lineage rather than instantiating an unrelated milestone. | **PASSED** |
| **INV-12** | $\text{Missing Observation} \neq \text{Retraction}$ | Omission of a field in a scraper run is treated as missing data, never as an affirmative retraction without evidence. | **PASSED** |
| **INV-13** | $\text{Equal-Authority Dispute} \to \text{Preserve Conflict}$ | Disagreeing sources with identical authority tiers yield `SOURCE_CONFLICT` with `canonical_deadline=None`. Zero fabricated winners. | **PASSED** |
| **INV-14** | $\text{Higher-Authority} \to \text{Strict Supersession}$ | Official CFP evidence strictly supersedes general aggregator or list-page records. | **PASSED** |
| **INV-15** | $\text{Risk Score} \perp \text{Deadline Urgency}$ | Predatory risk scoring never consumes or modifies deadline proximity or urgency tiers. | **PASSED** |
| **INV-16** | $\text{Deadline Urgency} \perp \text{Risk Score}$ | Deadline urgency scoring never alters or overrides opportunity trust scores. | **PASSED** |
| **INV-17** | $\text{Urgency Respects Relevance Dominance}$ | Urgency weight is bounded at $0.05$ (Phase 2.5 ranker) vs relevance dominance $0.35$, preventing urgency hijacking. | **PASSED** |
| **INV-18** | $\text{Frontend is Presentation-Only}$ | Frontend React components render backend-computed semantics without client-side timezone math or urgency calculations. | **PASSED** |
| **INV-19** | $\text{Strict Determinism}$ | Identical input representations and reference times yield bit-for-bit identical outputs across $100$ consecutive iterations. | **PASSED** |
| **INV-20** | $\text{Backward Compatibility}$ | All legacy fields (`submission_deadline`, `notification_date`, etc.) remain fully supported across database models and API schemas. | **PASSED** |

---

## 6. Performance & Latency Benchmarks

The benchmark runner profiled extraction, date parsing, timezone resolution, multi-milestone synthesis, conflict resolution, and explanation generation across candidate batches of size $N \in \{10, 50, 100, 200, 1000\}$ using high-precision hardware timers (`perf_counter`):

| Batch Size ($N$) | Total Batch Time ($\text{ms}$) | P50 Latency ($\text{ms}$) | P95 Latency ($\text{ms}$) | Average Latency ($\text{ms}$ / candidate) | DB Queries | Network Calls |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$N = 10$** | $6.68\text{ ms}$ | $0.4335\text{ ms}$ | $2.6150\text{ ms}$ | $0.6684\text{ ms}$ | **0** | **0** |
| **$N = 50$** | $21.99\text{ ms}$ | $0.4194\text{ ms}$ | $0.5880\text{ ms}$ | $0.4399\text{ ms}$ | **0** | **0** |
| **$N = 100$** | $43.20\text{ ms}$ | $0.4125\text{ ms}$ | $0.5309\text{ ms}$ | $0.4320\text{ ms}$ | **0** | **0** |
| **$N = 200$** | $85.85\text{ ms}$ | $0.4120\text{ ms}$ | $0.5312\text{ ms}$ | $0.4292\text{ ms}$ | **0** | **0** |
| **$N = 1,000$** | $412.64\text{ ms}$ | $0.4281\text{ ms}$ | $0.6332\text{ ms}$ | **$0.4126\text{ ms}$** | **0** | **0** |

### Key Performance Findings

1. **Zero N+1 Queries**: The complete deadline intelligence engine is 100% in-memory and executes entirely on passed models, schemas, and dictionaries.
2. **Linear Scalability**: Latency scales linearly with candidate volume ($O(N)$), with an average throughput of approximately **$2,423\text{ candidates/second}$** on a single CPU core.
3. **P95 Latency $< 0.65\text{ ms}$**: Individual opportunity resolution (evaluating up to 5 milestones, normalizing timezones, checking equivalence, and synthesizing explanations) requires well under $1\text{ millisecond}$ even at batch sizes of $1,000$.

---

## 7. Determinism Audit

To verify pure algorithmic reproducibility, a deterministic test fixture (`September 15, 2026 23:59 AoE`) was executed through the entire extraction, normalization, urgency assessment, conflict resolution, and explanation pipeline across **100 consecutive executions** with a fixed reference time.

- **Total Runs**: 100
- **Identical Runs**: 100
- **Determinism Percentage**: **100.0%**
- **Variation in Normalized Timestamps**: 0.00%
- **Variation in Urgency Scores**: 0.00%
- **Variation in Explanations**: 0.00%

---

## 8. Real-World Fixture Validation (WikiCFP Scrapers)

Real-world scraped HTML fixtures from `scrapers/tests/fixtures/` were validated through the pipeline without live network requests:

1. **WikiCFP Detail Page (`wikicfp_detail_page.html` — Event 195331: ICMLNS 2026)**:
   - Successfully parsed 4 distinct academic milestones:
     - Abstract Registration Due: `Aug 10, 2026`
     - Submission Deadline: `Aug 22, 2026 23:59 AoE`
     - Notification Due: `Sep 15, 2026`
     - Final Version Due (Camera-Ready): `Oct 1, 2026`
   - Primary milestone resolved to `DeadlineType.SUBMISSION`.
   - AoE convention verified: normalized to `2026-08-23 11:59:59 UTC` with `is_aoe=True`.
2. **WikiCFP List Page (`wikicfp_list_page.html`)**:
   - Successfully parsed 5 conference opportunity listings from table rows.
   - Primary submission deadline correctly extracted and normalized to AoE convention without synthetic midnight UTC coercion.

---

## 9. Regression Suite Status

The complete regression suite was executed across all existing backend and scraper systems:

- **Deadline Pipeline Unit Tests**: **165 / 165 PASSED** ($1.55\text{s}$)
  - `test_deadline_evidence_extraction.py`: 16 passed
  - `test_date_timezone_normalization.py`: 28 passed
  - `test_deadline_intelligence.py`: 37 passed
  - `test_deadline_conflict_resolution.py`: 38 passed
  - `test_deadline_api.py`: 14 passed
  - `test_phase2_7g_deadline_evaluation.py`: 32 passed
- **Scraper Test Suite**: **389 / 389 PASSED**
- **Frontend Production Build (`tsc -b && vite build`)**: **0 ERRORS, 0 WARNINGS**

---

## 10. Known Evaluation Limitations

To prevent overclaiming, the following empirical boundaries are explicitly documented:

1. **Synthetic & Curated Scope vs. Open Web Scrapers**:
   - The 43 benchmark fixtures and repository HTML files establish strict deterministic correctness across all supported semantic branches.
   - They do not quantify extraction accuracy across arbitrary, uncurated, or malformed third-party web scrapers that may be added in the future.
2. **Unstructured Natural Language Announcements**:
   - Announcements where submission deadlines are buried inside conversational paragraphs (e.g. *"we might extend depending on submissions"*) rely on regex and table structures. Complex discourse parsing is deferred to future offline indexing.
3. **Local Event Timezones**:
   - Venue dates lacking explicit timezone indicators default to local context or calendar dates without synthesizing an artificial instant.

---

## 11. Roadmap Alignment & Next Phase

With the completion of **Phase 2.7G (Deadline Intelligence Evaluation & Hardening)**, the entire **Phase 2 Roadmap** is complete:
- **Phase 2.1**: Hybrid Retrieval & Semantic Search — COMPLETE
- **Phase 2.2**: Cross-Encoder Reranking & Field Weighting — COMPLETE
- **Phase 2.3**: Dynamic Score Calibration & Query Intent — COMPLETE
- **Phase 2.4**: Diversity, Deduplication & Result Calibration — COMPLETE
- **Phase 2.5**: Ranking Evaluation & Offline Benchmarking — COMPLETE
- **Phase 2.6**: Opportunity Verification & Risk Intelligence — COMPLETE
- **Phase 2.7**: Deadline Intelligence & Urgency Engine — COMPLETE

The repository is now ready to transition to **Phase 3: Personalized Researcher Intelligence & Recommendations**.
