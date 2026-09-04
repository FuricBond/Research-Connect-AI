# Phase 2.7C — Date & Timezone Normalization

**Status**: IMPLEMENTED  
**Date**: September 2026  
**Phase**: 2.7C  
**Author**: ResearchConnect AI Engineering  

---

## 1. Executive Summary

> **Phase 2.7C normalizes deadline evidence into safe temporal representations. It does not calculate urgency tiers or change recommendation ranking.**

Phase 2.7C builds upon the structured evidence extracted in Phase 2.7B to establish an authoritative, deterministic date and timezone normalization layer for ResearchConnect AI. It replaces the legacy lossy parsing pipeline where date-only strings were arbitrarily coerced into UTC midnight (`00:00:00Z`). It resolves academic Anywhere on Earth (AoE) deadlines to their exact UTC instants ($T_{\text{UTC}} = T_{\text{local}} + 12\text{ hours}$), preserves calendar dates without browser timezone rollback, distinguishes explicit from inferred timezones, conservatively rejects ambiguous date formats, and integrates seamlessly with scraper normalization and expiration management without database schema changes.

---

## 2. Normalization Architecture

The deadline processing pipeline progresses cleanly through distinct architectural stages:

```text
Raw Source (WikiCFP List/Detail HTML, DB, Unstructured CFP)
                    │
                    ▼
[Phase 2.7B] DeadlineEvidenceExtractor
                    │
                    ▼
          DeadlineEvidence
          ├─ raw_value: "Aug 22, 2026"
          ├─ precision: DATE_ONLY
          ├─ timezone_indicator: UNSPECIFIED
          └─ milestone: SUBMISSION
                    │
                    ▼
[Phase 2.7C] DeadlineNormalizer (Authoritative, In-Memory Engine)
                    │
                    ▼
          NormalizedDeadline
          ├─ local_date: date(2026, 8, 22)
          ├─ local_time: time(23, 59, 59)
          ├─ timezone_name: "AoE"
          ├─ timezone_offset: "-12:00"
          ├─ normalized_utc: datetime(2026, 8, 23, 11, 59, 59, tzinfo=UTC)
          ├─ precision: DATE_ONLY
          ├─ timezone_source: TimezoneSource.INFERRED
          ├─ normalization_confidence: 0.85
          ├─ normalization_status: NormalizationStatus.INFERRED_TIMEZONE
          └─ is_end_of_day_inferred: True
                    │
                    ▼
[Phase 2.7D] Deadline Intelligence & Urgency (Future)
```

The system provides a single canonical normalization entry point:
- `DeadlineNormalizer.normalize_evidence()`: Normalizes a single `DeadlineEvidence` item.
- `DeadlineNormalizer.normalize_collection()`: Normalizes a `DeadlineEvidenceCollection`.
- `DeadlineNormalizer.normalize_raw_string()`: Direct string extraction and normalization for ingestion pipelines.
- `DeadlineNormalizer.normalize_opportunity_model()`: Normalizes from existing DB entities.
- `DeadlineNormalizer.normalize_raw_opportunity()`: Normalizes from scraper raw payloads.

---

## 3. Supported Date Formats

The normalization layer supports all standard academic date representations:
- **ISO Formats**: `2026-08-22`, `2026-08-22T23:59:00Z`, `2026-08-22 17:00:00+05:30`
- **Natural Language Dates**: `Aug 22, 2026`, `August 22, 2026`, `22 Aug 2026`, `22 August 2026`
- **Natural Language Datetimes**: `Aug 22, 2026 23:59`, `Aug 22, 2026 11:59 PM`, `Aug 22, 2026 09:30 AM`
- **Granular Precision**: Handles dates with explicit seconds (`23:59:59`) and without seconds (`23:59:00`).

---

## 4. Supported Timezone Formats

- **Coordinated Universal Time**: `UTC`, `GMT`, `Z`, `+00:00`
- **Numeric Offsets**: Parses explicit numeric offsets with positive/negative signs: `+05:30` (IST), `-04:00` (EDT), `+02:00` (CEST), `-08:00` (PST), etc.
- **Anywhere on Earth (AoE)**: Explicit tokens `AoE`, `Anywhere on Earth`, `UTC-12`, `GMT-12` mapped directly to fixed offset `-12:00`.
- **Standard Abbreviations**: Recognizes `EST`, `EDT`, `CST`, `CDT`, `MST`, `MDT`, `PST`, `PDT`, `CET`, `CEST`, `BST`, `JST`, `KST`, `IST`, `AEST`, `SAST`.
- **IANA Timezones & Daylight Saving Time (DST)**: Uses standard library `zoneinfo.ZoneInfo` (e.g. `America/New_York`, `Europe/London`, `Asia/Tokyo`). Calculates exact seasonal offsets at the specified local date and time:
  - `July 15, 2026 15:00 America/New_York` $\to$ EDT (`-04:00`) $\to$ `19:00:00 UTC`
  - `January 15, 2026 15:00 America/New_York` $\to$ EST (`-05:00`) $\to$ `20:00:00 UTC`
- **Invalid Timezones**: Unrecognized or invalid timezone names fail explicitly with `normalization_status = NormalizationStatus.INVALID` and `normalized_utc = None`. **The system never silently falls back to UTC.**

---

## 5. Anywhere on Earth (AoE) Handling

AoE is defined as standard offset UTC-12.
Conversion to UTC instant:
$$T_{\text{UTC}} = T_{\text{local}} - (-12\text{ hours}) = T_{\text{local}} + 12\text{ hours}$$

Examples:
- `2026-08-22 23:59:59 AoE` $\to$ `2026-08-23 11:59:59 UTC`
- **Month Rollover**: `2026-08-31 23:59:59 AoE` $\to$ `2026-09-01 11:59:59 UTC`
- **Year Rollover**: `2026-12-31 23:59:59 AoE` $\to$ `2027-01-01 11:59:59 UTC`

Conversions are performed via Python's standard `timezone(timedelta(hours=-12))` and `.astimezone(timezone.utc)`, guaranteeing exact leap year, month, and day calculations without custom date arithmetic.

---

## 6. Academic Date-Only Submission Deadline Policy

### The Inherent Problem
In academic conferences and journals, CFPs commonly state deadlines as calendar dates (e.g. `"Aug 22, 2026"`). Coercing this date to `2026-08-22 00:00:00 UTC` causes the deadline to expire at the very beginning of the day in UTC, cutting off submissions for authors in the Americas while it is still afternoon or evening of the preceding day.

### The Canonical Policy
Under the authoritative academic convention (`DefaultTimezonePolicy.INFERRED_AOE`):
1. For `DeadlineType.SUBMISSION`:
   - Submissions are accepted until the conclusion of the calendar date anywhere on earth (23:59:59 AoE).
   - `local_date`: `date(2026, 8, 22)` (source fact preserved)
   - `local_time`: `time(23, 59, 59)`
   - `timezone_name`: `"AoE"`
   - `timezone_offset`: `"-12:00"`
   - `normalized_utc`: `datetime(2026, 8, 23, 11, 59, 59, tzinfo=timezone.utc)`
   - `precision`: `DeadlinePrecision.DATE_ONLY`
   - `timezone_source`: `TimezoneSource.INFERRED` (preserving provenance)
   - `normalization_status`: `NormalizationStatus.INFERRED_TIMEZONE`
   - `normalization_confidence`: `0.85`
   - `is_end_of_day_inferred`: `True`
2. For Non-Submission Milestones (e.g. `EVENT_START`, `EVENT_END`):
   - Physical conference convening dates are calendar dates, not AoE submission deadlines.
   - `local_date`: `date(2026, 10, 24)`
   - `precision`: `DeadlinePrecision.DATE_ONLY`
   - `timezone_source`: `TimezoneSource.UNKNOWN`
   - `normalization_status`: `NormalizationStatus.DATE_ONLY`
   - `normalized_utc`: `None`
   - `normalization_confidence`: `0.90` (confidence in the calendar date, zero instant fabrication).

---

## 7. Explicit vs Inferred Timezones

Phase 2.7C enforces strict separation between source fact and inference:

| Dimension | Explicit Timezone | Inferred Timezone (Policy) | Unknown Timezone |
|---|---|---|---|
| Example | `"Aug 22, 2026 23:59 AoE"` | `"Aug 22, 2026"` | `"Aug 22, 2026"` (strict policy) |
| `timezone_source` | `TimezoneSource.EXPLICIT` | `TimezoneSource.INFERRED` | `TimezoneSource.UNKNOWN` |
| `normalization_status` | `EXPLICIT_TIMEZONE` | `INFERRED_TIMEZONE` | `DATE_ONLY` |
| `normalization_confidence` | `0.95` – `1.00` | `0.85` | `0.50` – `0.90` |
| `is_end_of_day_inferred` | `False` (or `True` if date-only AoE) | `True` | `False` |

---

## 8. Ambiguous and Missing Date Handling

- **Ambiguous Numeric Formats**:
  - Expressions such as `04/05/2026` where both numbers are $\le 12$ cannot be unambiguously resolved without guessing whether month or day comes first.
  - Returns `normalization_status = NormalizationStatus.AMBIGUOUS`, `normalized_utc = None`, `local_date = None`, `confidence = 0.0`.
  - Unambiguous formats such as `22/08/2026` (where day $22 > 12$) resolve deterministically to `2026-08-22`.
- **Missing / Non-Date Expressions**:
  - `None`, `""`, `"TBA"`, `"TBD"`, `"N/A"`, `"Rolling"`, `"See website"`, `"Soon"`:
  - Returns `normalization_status = NormalizationStatus.MISSING`, `normalized_utc = None`, `confidence = 0.0`.
  - **Invariants preserved**: `missing != expired`, `ambiguous != guessed`.

---

## 9. Scraper & Expiration Integration

1. **`scrapers/normalizers/opportunity_normalizer.py`**:
   - `normalize_opportunity()` routes `raw.raw_submission_deadline` through `DeadlineNormalizer.normalize_raw_string()`.
   - `NormalizedOpportunity.submission_deadline` receives `norm_deadline.normalized_utc`.
   - Legacy `_parse_date` is preserved for calendar event dates (`_parse_event_dates`).
2. **`scrapers/expiration/manager.py`**:
   - `is_opportunity_expired()` supports `NormalizedDeadline` directly via `deadline.is_expired(ref_time)`.
   - For legacy database records stored at exact UTC midnight (`00:00:00Z`), expiration is suppressed on the calendar day of the deadline itself (`ref_time.date() == deadline.date()`), preventing premature same-day expiration.

---

## 10. Frontend Date-Shift Correction

### The Browser Date Shift Bug
When an ISO timestamp such as `2026-08-22T00:00:00Z` or `2026-08-23T11:59:59Z` is parsed by browser JavaScript via `new Date(iso).toLocaleDateString()`:
- In timezones west of UTC (e.g. America/New_York at UTC-4), `2026-08-22T00:00:00Z` is 8:00 PM on August 21, causing the card to display **August 21**.
- For normalized AoE (`2026-08-23T11:59:59Z`), browser conversion displayed **August 23** instead of the intended calendar submission date **August 22**.

### The Solution (`frontend/src/utils/date.ts`)
A dedicated, timezone-safe date utility `formatDeadlineDate`:
- Detects normalized AoE timestamps (`T11:59:59` / `T12:00:00`) and subtracts 1 calendar day in UTC, formatting the intended AoE calendar date.
- Detects date-only and UTC-midnight timestamps (`T00:00:00`) and formats using `timeZone: "UTC"`, eliminating local timezone rollback.
- Integrated into `OpportunityCard.tsx` (submission deadline, notification date, camera-ready deadline) and `OpportunityList.tsx`.

---

## 11. Database Integration & Migration Decision

**Migration Decision**: **NO MIGRATION REQUIRED**
- The existing `OpportunityModel` columns `submission_deadline`, `notification_date`, and `camera_ready_deadline` are already `DateTime(timezone=True)`.
- `normalized_utc` populates these columns directly with accurate, timezone-aware UTC instants.
- No schema alterations, new tables, or database migrations are introduced.

---

## 12. Backward Compatibility

- **Ranking Signals**: `calculate_urgency()` remains untouched and backward compatible with timezone-aware datetime instances.
- **Phase 2.5 Academic Signals**: All relevance weights, diversity, novelty, and quality signals remain unchanged.
- **Phase 2.6 Trust/Risk Signals**: Risk scoring, evidence extraction, and thresholds remain completely unaffected.

---

## 13. Test Coverage

- **`backend/tests/test_date_timezone_normalization.py`** (28 tests):
  - ISO dates, ISO datetimes, natural language dates, 12-hour AM/PM times, seconds.
  - Positive numeric offsets (`+05:30`), negative offsets (`-04:00`).
  - Strict AoE formula verification, phrasing variations (`Anywhere on Earth`, `UTC-12`), month-end rollover, year-end rollover.
  - Academic submission date-only convention (`INFERRED_AOE`).
  - Event date-only milestone preservation (`EVENT_START` remains `DATE_ONLY` without synthesized instant).
  - Ambiguous slash format rejection (`04/05/2026`).
  - Unambiguous slash format acceptance (`22/08/2026`).
  - Missing/TBA/TBD/Rolling non-fabrication.
  - IANA timezones and DST transitions (`America/New_York` in summer EDT vs winter EST).
  - Invalid timezone rejection without fallback.
  - Milestone collection normalization and serialization.
  - 100-run determinism test.
  - Latency benchmarks across batch sizes 10, 50, 100, 200, 1000.
- **`backend/tests/test_deadline_evidence_extraction.py`**: 16/16 passed.
- **`scrapers/tests/test_normalizer.py` & `test_expiration.py`**: 41/41 passed.
- **`scrapers/tests/test_wikicfp_parser.py` & `test_wikicfp_detail_parser.py`**: 24/24 passed.
- **`backend/tests/test_ranking_signals.py` & `test_opportunities.py`**: 37/37 passed.

---

## 14. Performance & N+1 Assessment

- **Zero DB Queries**: Normalization is 100% in-memory pure AST/regex parsing.
- **Zero Network Calls**: No runtime HTTP, DNS, WHOIS, or calendar lookups.
- **N+1 Behavior**: None.
- **Measured Latency**:
  - In-memory normalization takes **$\approx 15$ to $25$ microseconds per item**.
  - A batch of 1,000 items normalizes in less than **25 milliseconds**.

---

## 15. Limitations & Deferred Scope

| Feature | Phase |
|---|---|
| Urgency tiers (`CRITICAL`, `URGENT`, `APPROACHING`, `DISTANT`) | Phase 2.7D |
| Hours / days remaining ranking signal | Phase 2.7D |
| Ranking weight updates | Phase 2.7D |
| Extension detection & deadline history tracking | Phase 2.7E |
| Cross-source conflict resolution | Phase 2.7E |
| Interactive deadline timelines and badges | Phase 2.7F |
| Empirical evaluation framework & stress testing | Phase 2.7G |
