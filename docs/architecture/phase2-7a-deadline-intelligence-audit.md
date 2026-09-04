# Phase 2.7A — Deadline Intelligence Architecture & Data Audit

**Status:** Completed  
**Branch:** `main`  
**Phase:** 2.7A (Audit & Architecture Only)  
**Target Subsystem:** Phase 2.7 — Deadline Intelligence, Feasibility & Notification Automation  
**Author:** ResearchConnect AI Engineering  
**Date:** September 2026  

---

## 1. Executive Summary & Objective

Phase 2.7 begins the construction of the **Deadline Intelligence** layer for ResearchConnect AI. This subsystem ensures that academic researchers receive truthful, timezone-aware, temporally calibrated deadline assessments, urgency classifications, milestone tracking (submission, notification, camera-ready), and extension/conflict detection.

Crucially, **Phase 2.7A is strictly an Audit and Architecture phase**. No speculative production code or premature schema changes have been implemented. The existing repository—serving as the definitive source of truth—was thoroughly audited across backend models, scrapers, normalizers, ranking signals, expiration managers, explainability services, APIs, database migrations, frontend UI components, and test suites.

### Key Architectural Findings
1. **Existing Infrastructure Footprint:** The database already has columns for `submission_deadline`, `notification_date`, `camera_ready_deadline`, `event_start_date`, and `event_end_date` on `OpportunityModel`. However, **only `submission_deadline` and event dates are currently populated by scrapers**. `notification_date` and `camera_ready_deadline` are completely dormant in production data.
2. **The "UTC Midnight" Premature Expiration Bug:** In `scrapers/normalizers/opportunity_normalizer.py`, dates like `"Aug 22, 2026"` are parsed into `datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)`. This treats deadlines as expiring at **00:00:00 UTC**, cutting off the entire calendar day of the deadline.
3. **Anywhere on Earth (AoE) Blindness:** Academic conferences predominantly adopt the **Anywhere on Earth (AoE, UTC-12)** standard (or local venue timezone), where a deadline of August 22 AoE corresponds to **August 23 11:59:59 UTC**. The current system expires such conferences **36 hours prematurely**.
4. **Frontend Timezone Shift Bug:** In `frontend/src/components/discovery/OpportunityCard.tsx`, calling `new Date(opportunity.submission_deadline).toLocaleDateString()` on a UTC midnight timestamp (`2026-08-22T00:00:00Z`) causes users in negative UTC offset timezones (e.g. Americas, UTC-4 to UTC-8) to see **August 21** instead of August 22.
5. **Irretrievable Extension Loss During Ingestion:** In `scrapers/persistence/opportunity_repo.py`, when a conference extends its deadline (e.g. from Aug 20 to Aug 25), `_upsert_opportunity` simply overwrites the column. No raw history or extension flag is recorded.
6. **Decoupled Urgency Signal:** The ranking signal `calculate_urgency()` in `backend/app/ranking/signals.py` is pure, linear, and well-tested. It can be safely preserved for Phase 2.5 ranking while being wrapped and enriched by the Phase 2.7 Deadline Intelligence engine.

---

## 2. Current Architecture & Repository Audit

### 2.1 Backend Audit
- **Models (`backend/app/models/opportunity.py`):**
  - `submission_deadline`: `DateTime(timezone=True)`, indexed, nullable.
  - `notification_date`: `DateTime(timezone=True)`, nullable.
  - `camera_ready_deadline`: `DateTime(timezone=True)`, nullable.
  - `event_start_date`: `Date`, nullable.
  - `event_end_date`: `Date`, nullable.
  - `status`: String enum (`ACTIVE`, `EXPIRED`, `ARCHIVED`, `DRAFT`, `UNVERIFIED`).
- **Ranking Signals (`backend/app/ranking/signals.py`):**
  - `calculate_urgency()`: Linear urgency decay over a 90-day window ($1.0$ at 0 days, $0.0$ at 90 days). Expired ($< 0$ days) or missing deadlines return $0.0$.
- **Hybrid Ranker (`backend/app/ranking/hybrid_ranker.py`):**
  - Consumes `calculate_urgency()` in `research_opportunity` ranking mode with weight $0.05$.
- **Explainability (`backend/app/explainability/result_explainer.py`):**
  - Generates textual attributions based on `signals.urgency` (e.g. *"Upcoming submission deadline creates strong time-sensitivity"*).
- **Service & Repositories (`backend/app/services/`, `backend/app/repositories/`):**
  - `opportunity_service.list_opportunities()`: `upcoming=True` enforces `submission_deadline >= now`. (Excludes NULL deadlines even if event is future).
  - `VectorRepository` & `LexicalRepository`: Filter `OpportunityModel.submission_deadline >= now` or `>= submission_deadline_after`.
- **Expiration Manager (`scrapers/expiration/manager.py`):**
  - `is_opportunity_expired()`: Checks `submission_deadline < now`; if missing, falls back to `event_end_date < today`.
  - `apply_expiration_status()`: Mutates status to `EXPIRED`.
  - `expire_past_opportunities()`: SQL batch sweep marking past opportunities as `EXPIRED`.

### 2.2 Scraper & Ingestion Pipeline Audit
- **Scraper Source (`scrapers/sources/wikicfp.py`):**
  - Fetches WikiCFP list pages (`/cfp/call?conference=...`). Does **not** crawl event detail pages (`event.showcfp`).
- **Parser (`scrapers/parsers/wikicfp_parser.py`):**
  - Extracts `raw_submission_deadline` from list table cell 2 (e.g. `"Aug 22, 2026"` or `"N/A"`).
  - Extracts `raw_event_dates` (e.g. `"Oct 24, 2026 - Oct 25, 2026"`).
- **Normalizer (`scrapers/normalizers/opportunity_normalizer.py`):**
  - Uses regex & `strptime` (`%b %d, %Y`).
  - Coerces parsed dates with `.replace(tzinfo=timezone.utc)` (UTC midnight).
- **Change Detection (`scrapers/change_detection/detector.py`):**
  - Compares `submission_deadline`, `event_start_date`, `event_end_date`. Flags modifications.
- **Persistence (`scrapers/persistence/opportunity_repo.py`):**
  - Overwrites existing DB columns. Discards raw strings and historical values.

### 2.3 Frontend Audit
- **Types (`frontend/src/types/opportunity.ts`, `discovery.ts`):**
  - `submission_deadline: string | null`, `notification_date: string | null`, `camera_ready_deadline: string | null`.
- **Card Component (`frontend/src/components/discovery/OpportunityCard.tsx`):**
  - Computes `diffDays = Math.ceil((deadlineDate.getTime() - now.getTime()) / 86400000)`.
  - Re-implements client-side urgency rules (`diffDays <= 14` $\to$ urgent).
  - Renders conditional notification and camera-ready chips.
  - Vulnerable to browser-local timezone day-shifting.

---

## 3. Current Deadline Data Flow

The complete end-to-end trace from source HTML to user interface is detailed below:

| Stage | Field / Artifact | Data Type | Timezone | Source / Origin | Transformation Logic | Issues / Limitations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Source** | WikiCFP List HTML | Raw text | None | WikiCFP `/cfp/call` | Scraped table cell 2 | Only date string present; time & timezone omitted. |
| **2. Scraper** | `RawOpportunity.raw_submission_deadline` | `str \| None` | None | `WikiCFPParser` | `_cell_text()` strips whitespace; `"N/A"` $\to$ `None` | Detail page milestones (notification, camera-ready) missed. |
| **3. Normalizer** | `NormalizedOpportunity.submission_deadline` | `datetime \| None` | Assumed UTC | `opportunity_normalizer` | `strptime` matching; attaches `timezone.utc` (00:00:00) | **Truncates day**: expires at 00:00 UTC. AoE completely ignored. |
| **4. Ingestion Check** | `is_opportunity_expired()` | `bool` | UTC | `expiration/manager` | Compares `deadline < ref_time` | Prematurely flags events expired on deadline day. |
| **5. Persistence** | `OpportunityModel.submission_deadline` | `DateTime(tz=True)` | UTC | `OpportunityRepository` | SQLAlchemy mapped column insert / update | Overwrites on change; extension history lost. |
| **6. Query / Repo** | `VectorRepository` / `LexicalRepository` | SQL Filter | UTC | DB session | `WHERE submission_deadline >= now` | Excludes NULL deadlines even if event is future. |
| **7. Ranking** | `calculate_urgency()` | `float [0, 1]` | UTC | `ranking/signals` | Linear decay: $1.0 - (\text{days} / 90)$ | Pure float; lacks discrete status/urgency tiers. |
| **8. API Schema** | `OpportunityRead.submission_deadline` | ISO string | UTC | FastAPI serialization | Pydantic standard ISO datetime | No timezone provenance or AoE flag communicated. |
| **9. Frontend** | `OpportunityCard.tsx` | Display string | Local Browser | React component | `new Date().toLocaleDateString()` | **Day shift**: US users see previous calendar date. |

---

## 4. Audit of Existing Deadline Fields

An audit of the five date/deadline fields in `OpportunityModel`:

| Field Name | Semantic Meaning | Populating Sources | Explicit vs Inferred | Timezone Preserved? | Raw Preserved? | Extensions Trackable? | Unknown vs Missing? | Date-Only vs Exact Time? |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `submission_deadline` | Main paper submission cut-off | WikiCFP | Explicit date | ❌ Forced UTC midnight | ❌ No | ❌ Overwritten | ❌ Both `None` | Coerced to exact time |
| `notification_date` | Acceptance notification date | **None** (Dormant) | — | ❌ Not populated | ❌ No | ❌ No | ❌ Always `None` | — |
| `camera_ready_deadline` | Final camera-ready submission | **None** (Dormant) | — | ❌ Not populated | ❌ No | ❌ No | ❌ Always `None` | — |
| `event_start_date` | Conference/event start date | WikiCFP | Explicit date | N/A (`Date`) | ❌ No | ❌ Overwritten | ❌ Both `None` | True Date |
| `event_end_date` | Conference/event end date | WikiCFP | Explicit date | N/A (`Date`) | ❌ No | ❌ Overwritten | ❌ Both `None` | True Date |

---

## 5. Audit of WikiCFP Deadline Handling

1. **Formats in the wild:** WikiCFP displays dates such as `"Aug 22, 2026"`, `"September 5, 2026"`, `"2026-10-15"`, or `"N/A"`.
2. **Missing Time & Timezone:** WikiCFP list pages **never specify a time of day or a timezone**.
3. **Academic Convention:** In computer science and academic conferences, a date-only deadline implicitly denotes **23:59:59 AoE (Anywhere on Earth)** unless explicitly declared otherwise.
4. **Current Ingestion Fallacy:** The normalizer transforms `"Aug 22, 2026"` into `2026-08-22 00:00:00+00:00`.
   - Result: The deadline expires at the first second of August 22 UTC.
   - At 14:00 UTC on August 22, researchers in Europe, Asia, and the Americas are still writing papers, but ResearchConnect AI treats the call as expired!
   - Under AoE, August 22 23:59:59 AoE is **August 23 11:59:59 UTC**—a full 36-hour discrepancy.
5. **List Page vs. Detail Page:** WikiCFP event detail pages (`/cfp/servlet/event.showcfp?eventid=...`) provide dedicated tables containing:
   - *Abstract Registration Due*
   - *Submission Deadline*
   - *Notification Due*
   - *Final Version Due (Camera-Ready)*
   The current scraper never accesses these detail pages, discarding critical milestone data.

---

## 6. Audit of Urgency Logic (`calculate_urgency`)

### 6.1 Current Formula & Properties
```python
diff_seconds = (dt_deadline - reference_time).total_seconds()
days_remaining = diff_seconds / 86400.0

if days_remaining < 0.0 or days_remaining >= max_window:
    return 0.0

urgency = 1.0 - (days_remaining / max_window)
return round(min(1.0, max(0.0, urgency)), 6)
```
- **Window:** Defaults to 90.0 days (`settings.hybrid_ranking_urgency_window_days`).
- **Expired & Distant Deadlines:** Returns `0.0`.
- **Missing / None Deadlines:** Returns `0.0`.
- **Reference Time:** Injected parameter, defaulting to `datetime.now(timezone.utc)`. Pure and deterministic.

### 6.2 Architectural Recommendation for Urgency
- **Preserve `calculate_urgency()` as the ranking signal:** In Phase 2.5, `urgency` was tuned with weight $0.05$ in `research_opportunity` mode. To preserve Phase 2.5 ranking integrity, **do not alter the mathematical output of `calculate_urgency()` for ranking**.
- **Wrap for Deadline Intelligence:** Create a higher-level `DeadlineIntelligenceEngine` that provides structured urgency tiers (`CRITICAL`, `URGENT`, `APPROACHING`, `DISTANT`, `EXPIRED`, `UNKNOWN`) alongside exact days/hours remaining, while retaining `calculate_urgency()` for candidate ordering.

---

## 7. Audit of Expiration Logic

### 7.1 Separation of Concerns: Lifecycle Status vs. Dynamic Urgency
- **`status = "EXPIRED"`:** A persistent database lifecycle attribute applied when an event's submission deadline (or event date) has conclusively passed.
- **Dynamic Urgency (`DUE_TODAY`, `URGENT`, `CRITICAL`):** A real-time temporal property dependent on the query evaluation reference timestamp.
- **Precedence Rule:** If `submission_deadline` exists, it governs expiration. If missing, `event_end_date` (or `event_start_date`) governs. If both are missing, the record remains `ACTIVE` (`missing != expired`).
- **Fix Required:** Expiration must not evaluate at 00:00:00 UTC for date-only deadlines; it must evaluate at **23:59:59 AoE** (or end of day local/UTC) to prevent premature retirement of active opportunities.

---

## 8. Timezone Audit Repository-Wide

| Location | Component | Behavior | Risk Level | Remediation |
| :--- | :--- | :--- | :---: | :--- |
| `scrapers/normalizers/opportunity_normalizer.py` | `_parse_date()` | Forces `00:00:00 UTC` | **HIGH** | Treat date-only as date-only or normalize to 23:59:59 AoE / End-of-Day. |
| `scrapers/expiration/manager.py` | `is_opportunity_expired()` | Evaluates `deadline < now` against midnight UTC | **HIGH** | Incorporate AoE offset buffer before declaring expiration. |
| `backend/app/ranking/signals.py` | `calculate_urgency()` | Coerces naive datetimes to UTC | **LOW** | Safe fallback, but should respect timezone metadata. |
| `backend/app/services/opportunity_service.py` | `list_opportunities()` | `deadline >= now` filter | **MEDIUM** | Filter with AoE awareness so "due today" calls stay visible. |
| `frontend/src/components/discovery/OpportunityCard.tsx` | Client formatting | `new Date().toLocaleDateString()` | **HIGH** | Display date using UTC or formatted with explicit timezone tag. |

---

## 9. Required Deadline Intelligence Concepts

For Phase 2.7, the system requires formal domain modeling:

```text
DeadlineType:
  - SUBMISSION             (Primary paper submission)
  - ABSTRACT_REGISTRATION  (Pre-submission abstract deadline)
  - NOTIFICATION           (Author notification of acceptance/rejection)
  - CAMERA_READY           (Final publication-ready manuscript)
  - REGISTRATION           (Author/attendee registration deadline)
  - EVENT_START            (Event start date)
  - EVENT_END              (Event conclusion date)
  - UNKNOWN                (Unspecified deadline type)

DeadlineProvenance:
  - EXPLICIT_TIMESTAMP     (Full datetime + timezone provided by source)
  - EXPLICIT_DATE          (Date provided; timezone inferred/defaulted)
  - AOE_CONVENTION         (Academic Anywhere on Earth convention applied)
  - INFERRED               (Derived from contextual text)
  - DEFAULTED              (Fallback default applied)
  - UNKNOWN                (Provenance untracked)

DeadlineStatus:
  - UPCOMING               (Deadline is in the future)
  - DUE_TODAY              (Due within the current 24-hour cycle)
  - EXPIRED                (Deadline has passed)
  - UNKNOWN                (No deadline data available)

UrgencyTier:
  - CRITICAL               (<= 3 days remaining)
  - URGENT                 (<= 14 days remaining)
  - APPROACHING            (<= 30 days remaining)
  - DISTANT                (> 30 days remaining)
  - EXPIRED                (Past deadline)
  - UNKNOWN                (Missing deadline)
```

---

## 10. Multi-Deadline, Extension & Conflict Requirements

### 10.1 Multi-Deadline Support
Conferences have sequential milestones:
1. Abstract Registration (e.g. Sept 1)
2. Full Paper Submission (e.g. Sept 8)
3. Rebuttal Period (e.g. Oct 15 - Oct 20)
4. Notification of Acceptance (e.g. Nov 10)
5. Camera-Ready Due (e.g. Dec 1)
6. Conference Dates (e.g. Jan 15 - Jan 18)

The current schema possesses columns for milestones 2, 4, 5, and 6, but scrapers only extract 2 and 6. A structured `deadline_schedule` model will enable representation of all milestones without schema thrashing.

### 10.2 Extensions & Historical Tracking
- When a deadline is extended (e.g. "Deadline Extended to Sept 15!"), the system must detect that `new_deadline > old_deadline`.
- It should record:
  - `original_deadline: datetime`
  - `is_extended: bool = True`
  - `extension_count: int`
  - `extension_days: int`

### 10.3 Cross-Source Conflicts
- If WikiCFP reports Sept 15 but an official venue scrape reports Sept 20:
  - Store conflict evidence.
  - Apply conservative resolution (prefer verified source or later date with a warning).

---

## 11. Safety Invariants for Phase 2.7

The Phase 2.7 implementation must preserve these non-negotiable invariants:

1. **`missing != expired`**: A missing deadline must never cause an opportunity to be marked `EXPIRED` or penalized with negative risk. It is simply `UNKNOWN`.
2. **`unknown timezone != silently known UTC`**: If a timezone is not explicitly provided, it must be marked as `AOE_CONVENTION` or `INFERRED_UTC`, never falsely declared as verified UTC.
3. **`ambiguous date != fabricated date`**: Ambiguous formats (e.g. `04/05/2026`) must be flagged as ambiguous or parsed with source context; dates must never be invented.
4. **`event date != submission deadline`**: Conference dates must never be substituted as paper submission deadlines.
5. **`notification date != submission deadline`**: Author decision dates must never be treated as submission deadlines.
6. **`deadline urgency != trust/risk`**: An imminent deadline does **not** imply predatory practices, and an expired deadline does **not** imply fraud. Phase 2.6 risk and Phase 2.7 deadlines are orthogonal.
7. **`deadline urgency != relevance`**: An urgent irrelevant paper must not rank above a highly relevant paper. Phase 2.5 relevance dominance ($\ge 85\%$) must remain strictly preserved.
8. **Pure Determinism**: For any given opportunity and reference timestamp $T$, `assess_deadlines(opp, reference_time=T)` must produce byte-for-byte identical output across $1,000$ runs.

---

## 12. Database Migration Decision

### Decision: **`NO MIGRATION REQUIRED FOR 2.7A`**

#### Schema Sufficiency Assessment:
1. `OpportunityModel` already contains:
   - `submission_deadline: DateTime(timezone=True)`
   - `notification_date: DateTime(timezone=True)`
   - `camera_ready_deadline: DateTime(timezone=True)`
   - `event_start_date: Date`
   - `event_end_date: Date`
2. **Phase 2.7 Core Intelligence can be fully implemented without modifying existing database columns.**
   - Ingestion scrapers can populate the existing dormant `notification_date` and `camera_ready_deadline` columns.
   - For richer metadata (such as `is_aoe`, `deadline_timezone`, `original_deadline`, `is_extended`, and multi-stage milestones), the system can either:
     - **Option A (In-Memory Engine, Zero Schema Change):** Compute deadline intelligence dynamically at ranking/API time from existing dates and scraper raw metadata.
     - **Option B (Targeted JSONB Column in 2.7C):** Add a single backward-compatible `deadline_metadata: JSONB` column on `OpportunityModel` to store structured schedules, extension history, and timezone provenance without altering any existing columns.
3. **Conclusion:** No migration is needed in 2.7A. If Option B is selected in 2.7C, a clean single-column migration will be specified.

---

## 13. Performance & N+1 Audit

- **Zero Database Queries in Ranking:** Deadline intelligence evaluation must execute strictly in memory on already-retrieved candidate objects.
- **Pure-Function Execution:** Date parsing and urgency scaling require zero runtime I/O, zero network calls, and zero external APIs.
- **Latency Target:** $< 0.1\text{ ms}$ per candidate ($< 2\text{ ms}$ for a batch of 50 candidates).
- **API Integration:** Deadline intelligence must be returned in the candidate match response envelope without triggering secondary database lookups ($0$ N+1 queries).

---

## 14. Proposed Phase 2.7 Architecture & Modular Roadmap

### Subsystem Flow
```text
Raw Deadline Strings & Detail Scrapes
                ↓
Phase 2.7B: Deadline Evidence Extraction & Detail Scraper
                ↓
Phase 2.7C: Date & Timezone Normalization (AoE, UTC, Local)
                ↓
Phase 2.7D: Deadline Intelligence & Urgency Engine
                ↓
Phase 2.7E: Multi-Deadline, Extension & Conflict Intelligence
                ↓
Phase 2.7F: Deadline Explainability, REST API & Frontend UI
                ↓
Phase 2.7G: Empirical Evaluation, Calibration & Hardening
```

### Modular Implementation Plan (2.7B – 2.7G)

| Phase | Title | Primary Responsibilities | Deliverables |
| :--- | :--- | :--- | :--- |
| **2.7B** | **Deadline Evidence Extraction** | - Extract raw deadline strings and milestone dates from sources.<br>- Detail-page scraping for WikiCFP event milestones (notification, camera-ready).<br>- Preserve raw strings and provenance without loss. | `backend/app/ranking/deadline/extractors.py`<br>`scrapers/parsers/detail_parser.py`<br>Extraction test suite |
| **2.7C** | **Date & Timezone Normalization** | - Robust date/time parsing.<br>- Explicit AoE handling (23:59:59 AoE $\to$ 11:59:59 UTC next day).<br>- Timezone-aware date normalization preventing premature day cut-offs.<br>- Non-destructive fallback handling. | `backend/app/ranking/deadline/normalizers.py`<br>Timezone resolution tests<br>AoE verification tests |
| **2.7D** | **Deadline Intelligence & Urgency Engine** | - Pure, deterministic urgency and status calculator.<br>- Compute exact days and hours remaining.<br>- Categorize into discrete urgency tiers (`CRITICAL`, `URGENT`, `APPROACHING`, `DISTANT`, `EXPIRED`).<br>- Compute deadline confidence based on date explicitness and timezone certainty. | `backend/app/ranking/deadline/intelligence.py`<br>`backend/app/ranking/deadline/models.py`<br>Deterministic test suite |
| **2.7E** | **Extension & Conflict Intelligence** | - Detect deadline extensions during ingestion (`new > old`).<br>- Track extension days and original deadline.<br>- Cross-source deadline conflict resolution.<br>- Feasibility scoring (time required vs. days remaining). | `backend/app/ranking/deadline/conflicts.py`<br>Extension detection tests<br>Conflict resolution tests |
| **2.7F** | **Explainability, API & Frontend UI** | - Build `DeadlineIntelligenceSchema` API models.<br>- Integrate with discovery matching endpoints.<br>- Create frontend Deadline badges with AoE indicators and milestone timelines.<br>- Progressive disclosure in Explainability Drawer. | `backend/app/schemas/deadline.py`<br>`frontend/src/components/discovery/DeadlineBadge.tsx`<br>Updated OpportunityCard |
| **2.7G** | **Empirical Evaluation & Hardening** | - Dedicated 100+ fixture deadline evaluation dataset.<br>- Invariant verification (AoE, extensions, missing dates).<br>- 100-run determinism testing.<br>- Sub-millisecond batch performance benchmarking.<br>- Evaluation artifact: `phase2-7g-deadline-results.json`. | `backend/app/evaluation/deadline_runner.py`<br>`artifacts/evaluation/phase2-7g-deadline-results.json`<br>Architecture documentation |

---

## 15. Testing Strategy for Phase 2.7

The test plan for Phase 2.7 spans unit, integration, and regression suites:
1. **Timezone & AoE Tests:**
   - Verify August 22 AoE expires at August 23 11:59:59 UTC.
   - Verify date-only strings do not cut off at 00:00:00 UTC.
   - Verify browser timezone rendering produces correct calendar dates across negative UTC offsets.
2. **Milestone Integrity Tests:**
   - Verify notification date and camera-ready deadlines are properly extracted and preserved.
   - Verify order invariant: `submission_deadline < notification_date < camera_ready_deadline < event_start_date`.
3. **Extension & Conflict Tests:**
   - Verify extensions from Aug 20 to Aug 25 preserve the original deadline and set `is_extended = True`.
   - Verify conflicts between conflicting sources are reported with appropriate confidence degradation.
4. **Safety & Invariance Regression Tests:**
   - Verify Phase 2.5 ranking relevance and rank order remain identical.
   - Verify Phase 2.6 risk scores and risk levels remain identical.
   - Verify `calculate_urgency()` mathematical outputs remain unchanged for ranking.
   - Verify 100-run strict byte-for-byte determinism.

---

## 16. Definition of Done for Phase 2.7A

Phase 2.7A is complete:
- [x] Repository thoroughly audited across backend, scrapers, frontend, schemas, and tests.
- [x] End-to-end deadline data flow mapped and documented.
- [x] Timezone weaknesses (UTC midnight truncation, AoE blindness, browser day-shift) identified and documented.
- [x] Dormant schema fields (`notification_date`, `camera_ready_deadline`) identified.
- [x] Urgency and expiration logic audited; separation of concerns defined.
- [x] Safety invariants established.
- [x] Database migration decision established (No migration required for 2.7A).
- [x] Phased roadmap for 2.7B through 2.7G established.
- [x] Zero production code changed; zero test regressions.

**Phase 2.7A is complete. Ready for Phase 2.7B.**
