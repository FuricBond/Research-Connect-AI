# Phase 2.7B — Deadline Evidence Extraction

**Status**: IMPLEMENTED  
**Date**: September 2026  
**Phase**: 2.7B  
**Author**: ResearchConnect AI Engineering  

---

## 1. Executive Summary

> **Phase 2.7B extracts deadline evidence; it does not determine the final normalized deadline instant.**

Phase 2.7B implements **Deadline Evidence Extraction** as the foundational extraction layer of Phase 2.7 (Deadline Intelligence). The objective is to extract, classify, preserve, and provenance-track raw academic milestone signals from heterogeneous sources (WikiCFP list pages, WikiCFP detail pages, existing database records, scraped `RawOpportunity` objects, and unstructured CFP call text) without prematurely coercing them into arbitrary UTC datetimes, assuming timezones, fabricating dates from ambiguous expressions, or calculating urgency and ranking adjustments.

---

## 2. Current Extraction Architecture

Prior to Phase 2.7B, deadline processing operated on a lossy, single-pass pipeline:
1. `scrapers/parsers/wikicfp_parser.py` parsed only 2 date fields from WikiCFP list tables (`submission_deadline`, `event_dates`).
2. `scrapers/normalizers/opportunity_normalizer.py` applied Python's `dateutil.parser.parse()`:
   - Untracked timezone strings were parsed as naive `datetime` objects.
   - Any date without a time defaulted to `00:00:00` (midnight).
   - Ingested naive datetimes were treated as UTC or local time inconsistently.
3. Detail-page metadata (`event.showcfp`) containing abstract deadlines, notification dates, camera-ready deadlines, and registration deadlines were completely ignored.
4. Database records in `OpportunityModel` contained `submission_deadline`, `notification_date`, and `camera_ready_deadline` as `DateTime(timezone=True)`, but lacked metadata on whether the source provided an exact time, date-only, explicit AoE, or ambiguous text.

Phase 2.7B introduces a dual-layer extraction architecture:
```
Source (WikiCFP List, Detail Page HTML, DB, Unstructured CFP Text)
       │
       ▼
WikiCFPDetailParser / Raw Source Ingest
       │
       ▼
DeadlineEvidenceExtractor (Pure, Deterministic, AST-only parsing)
       │
       ▼
DeadlineEvidence / DeadlineEvidenceCollection
       │
       ├─► Raw value & text preserved (e.g., "Aug 22, 2026")
       ├─► Milestone type isolated (SUBMISSION vs ABSTRACT vs NOTIFICATION, etc.)
       ├─► Precision classified (DATE_ONLY vs EXACT_TIME)
       ├─► Timezone indicator tagged (EXPLICIT_AOE vs UNSPECIFIED)
       ├─► Provenance & confidence tracked
       └─► Ambiguity preserved (e.g., "04/05/2026")
       │
       ▼
[Deferred to Phase 2.7C: Normalization & UTC Instant Calculation]
```

---

## 3. Dedicated Evidence Model

The evidence representation resides in `backend/app/ranking/deadline/models.py`:

### Key Types and Enums

```python
class DeadlineType(str, Enum):
    SUBMISSION = "SUBMISSION"
    ABSTRACT = "ABSTRACT"
    NOTIFICATION = "NOTIFICATION"
    CAMERA_READY = "CAMERA_READY"
    REGISTRATION = "REGISTRATION"
    EVENT_START = "EVENT_START"
    EVENT_END = "EVENT_END"
    UNKNOWN = "UNKNOWN"

class DeadlinePrecision(str, Enum):
    DATE_ONLY = "DATE_ONLY"
    EXACT_TIME = "EXACT_TIME"
    YEAR_MONTH = "YEAR_MONTH"
    APPROXIMATE = "APPROXIMATE"
    UNKNOWN = "UNKNOWN"

class TimezoneIndicator(str, Enum):
    EXPLICIT_AOE = "EXPLICIT_AOE"
    EXPLICIT_UTC = "EXPLICIT_UTC"
    EXPLICIT_OFFSET = "EXPLICIT_OFFSET"
    LOCAL_NAMED = "LOCAL_NAMED"
    UNSPECIFIED = "UNSPECIFIED"

class DeadlineProvenance(str, Enum):
    WIKICFP_LIST_PAGE = "WIKICFP_LIST_PAGE"
    WIKICFP_DETAIL_PAGE = "WIKICFP_DETAIL_PAGE"
    OPENALEX = "OPENALEX"
    CROSSREF = "CROSSREF"
    DATABASE = "DATABASE"
    RAW_OPPORTUNITY = "RAW_OPPORTUNITY"
    UNSTRUCTURED_TEXT = "UNSTRUCTURED_TEXT"
    UNKNOWN = "UNKNOWN"

class ExtractionMethod(str, Enum):
    STRUCTURED_FIELD = "STRUCTURED_FIELD"
    HTML_TABLE_LABEL = "HTML_TABLE_LABEL"
    REGEX_PATTERN = "REGEX_PATTERN"
    DATABASE_COLUMN = "DATABASE_COLUMN"
    HEURISTIC = "HEURISTIC"
```

### `DeadlineEvidence` Dataclass
Encapsulates individual milestone evidence:
- `deadline_type`: Identified academic milestone.
- `raw_value`: Exact date/time substring as provided by the source.
- `raw_text`: Surrounding source context or label.
- `source`: Source platform or identifier (e.g. `wikicfp`, `internal_db`).
- `source_reference`: Event ID or URI.
- `source_field`: Attribute or column name from source.
- `extraction_method`: How evidence was retrieved.
- `confidence`: Extraction confidence $[0.0, 1.0]$ based purely on extraction clarity (not urgency/risk).
- `provenance`: Origin of the source document/record.
- `is_present`: Boolean flag indicating if a valid milestone date exists (set to `False` for `TBA`, `TBD`, `N/A`, `Rolling`).
- `precision`: `DATE_ONLY`, `EXACT_TIME`, `YEAR_MONTH`, etc.
- `timezone_indicator`: `EXPLICIT_AOE`, `EXPLICIT_UTC`, `LOCAL_NAMED`, or `UNSPECIFIED`.
- `parsed_year`, `parsed_month`, `parsed_day`: Pure integer calendar components (independent of UTC conversion).
- `parsed_hour`, `parsed_minute`, `parsed_second`: Extracted exact times if present.
- `is_ambiguous`: Boolean flag for date representations where month/day ordering is uncertain (e.g. `04/05/2026`).
- `metadata`: Extensible dictionary for audit and auxiliary tokens.

---

## 4. Supported Milestone Types & Invariants

Phase 2.7B strictly enforces milestone isolation:
```text
ABSTRACT_DEADLINE != SUBMISSION_DEADLINE
NOTIFICATION_DATE != SUBMISSION_DEADLINE
CAMERA_READY_DEADLINE != SUBMISSION_DEADLINE
REGISTRATION != SUBMISSION_DEADLINE
EVENT_START != SUBMISSION_DEADLINE
EVENT_END != SUBMISSION_DEADLINE
```

The system never silently substitutes an abstract deadline or notification date for a submission deadline. Each milestone is captured as an independent `DeadlineEvidence` item inside a `DeadlineEvidenceCollection`.

---

## 5. Raw Value Preservation

Every evidence item retains the exact string verbatim as extracted from the source:
- Input `"Aug 22, 2026"` $\to$ `raw_value = "Aug 22, 2026"`
- Input `"2026-08-22 23:59 AoE"` $\to$ `raw_value = "2026-08-22 23:59 AoE"`
- Input `"TBD"` $\to$ `raw_value = "TBD"`, `is_present = False`

The raw string is never mutated or discarded.

---

## 6. Date/Time Precision & No Premature UTC Midnight

A central correctness requirement of Phase 2.7:
> **Date-only inputs must NOT be converted to 00:00:00 UTC.**

If a source provides `"Aug 22, 2026"`, Phase 2.7B extracts:
- `precision = DeadlinePrecision.DATE_ONLY`
- `parsed_year = 2026, parsed_month = 8, parsed_day = 22`
- `parsed_hour = None, parsed_minute = None, parsed_second = None`
- `timezone_indicator = TimezoneIndicator.UNSPECIFIED`

Converting date-only inputs to `00:00:00 UTC` causes a submission deadline of August 22 to expire at the beginning of the day in UTC (which corresponds to afternoon/evening of August 21 in the Americas), prematurely cutting off 24 hours of valid submission time. Date-only values remain explicitly tagged as `DATE_ONLY` with `UNSPECIFIED` timezone.

If an explicit time is present (e.g., `"Aug 22, 2026 23:59"`):
- `precision = DeadlinePrecision.EXACT_TIME`
- `parsed_hour = 23, parsed_minute = 59`

---

## 7. AoE Evidence Handling

If a source explicitly specifies `"AoE"`, `"Anywhere on Earth"`, or `"UTC-12"`:
- `timezone_indicator = TimezoneIndicator.EXPLICIT_AOE`
- `raw_value` preserves the AoE token.
- **NO UTC conversion is performed in 2.7B.**

If the source merely provides a date without a timezone (e.g. `"Aug 22, 2026"`), the extractor records:
- `timezone_indicator = TimezoneIndicator.UNSPECIFIED`

The system does not fabricate or presume that an unadorned date was explicitly declared as AoE. The decision of default timezone application is explicitly deferred to Phase 2.7C.

---

## 8. Ambiguity & Missing Data Handling

1. **Non-date expressions**:
   - `"TBA"`, `"TBD"`, `"N/A"`, `"Rolling"`, `"See website"`, `"Soon"`, `"None"`:
     - `is_present = False`
     - `confidence = 0.0`
     - `raw_value` preserved.
2. **Ambiguous Slash Dates**:
   - Numerical formats where both numbers are $\le 12$ (e.g., `"04/05/2026"`, which could mean April 5 or May 4):
     - `is_ambiguous = True`
     - Default interpretation is noted in metadata, but ambiguous flag alerts downstream normalizers.
   - Numerical formats where one number is $> 12$ (e.g., `"22/08/2026"`):
     - Parsed unambiguously with `is_ambiguous = False` (Day=22, Month=8).
3. **Missing != Expired**:
   - Missing deadline evidence results in `is_present = False`. It is never treated as expired or 0.

---

## 9. WikiCFP Detail Page Extraction

Implemented in `scrapers/parsers/wikicfp_detail_parser.py`:
- Parses WikiCFP detail pages (`http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=...`).
- Scrapes the HTML metadata table containing:
  - Submission Deadline (`Deadline`)
  - Abstract Registration Due (`Abstract Registration Due`)
  - Notification Due (`Notification Due`)
  - Final Version Due / Camera Ready (`Final Version Due`)
  - Registration Deadline
- Extracts external event website link (`href` on conference title).
- Extracts full text of the Call for Papers.
- Links to existing list-page records using the stable `eventid` query parameter.

---

## 10. Persistence Mapping & Existing DB Model

The existing `OpportunityModel` table contains:
- `submission_deadline` (`DateTime(timezone=True)`)
- `notification_date` (`DateTime(timezone=True)`)
- `camera_ready_deadline` (`DateTime(timezone=True)`)
- `event_start_date` (`Date`)
- `event_end_date` (`Date`)

In Phase 2.7B:
- Evidence extraction operates in-memory.
- `DeadlineEvidenceExtractor.extract_from_opportunity_model()` extracts evidence from existing DB records, labeling provenance as `DATABASE` and extraction method as `DATABASE_COLUMN`.
- No new database columns or tables are introduced in 2.7B.
- Full persistent evidence caching or metadata schema enhancements are evaluated for Phase 2.7C / 2.7D.

---

## 11. Strict Phase Boundaries — Deferred to 2.7C–2.7G

The following components are **intentionally deferred**:

| Feature | Phase |
|---|---|
| AoE $\to$ UTC instant conversion | Phase 2.7C |
| Unspecified timezone default policies (e.g., Default AoE) | Phase 2.7C |
| Final normalized instant calculation (`normalized_utc`) | Phase 2.7C |
| Urgency tiers (`URGENT`, `APPROACHING`, `STANDARD`, `RELAXED`) | Phase 2.7D |
| Hours / days remaining calculation | Phase 2.7D |
| Extension detection & deadline history tracking | Phase 2.7E |
| Ranking signal adjustments (`calculate_urgency()` updates) | Phase 2.7D / 2.7E |
| API & UI exposure (timelines, badges, tooltips) | Phase 2.7F |
| Empirical evaluation & edge-case stress testing | Phase 2.7G |

---

## 12. Test Coverage

Comprehensive unit tests cover all extraction requirements:
1. **`backend/tests/test_deadline_evidence_extraction.py`** (16 tests):
   - Date-only precision preservation (no UTC midnight coercion).
   - Exact time precision preservation.
   - Explicit AoE indicator preservation without conversion.
   - Explicit UTC and ISO offset handling.
   - Ambiguous vs unambiguous slash format handling.
   - Non-date strings (`TBA`, `TBD`, `N/A`, `Rolling`) marked `is_present = False`.
   - Milestone extraction from dictionary.
   - Milestone isolation invariant (`ABSTRACT != SUBMISSION`).
   - Free-form CFP text milestone extraction with regex boundaries.
   - Integration with `RawOpportunity` and `OpportunityModel`.
   - Strict 100-run determinism test.
   - JSON serialization.
2. **`scrapers/tests/test_wikicfp_detail_parser.py`** (4 tests):
   - HTML table metadata extraction.
   - Milestone dictionary parsing (`Submission`, `Abstract`, `Notification`, `Camera Ready`).
   - Description / CFP body extraction.
   - Graceful blank HTML handling.
3. **`scrapers/tests/test_wikicfp_parser.py`** (20 tests):
   - All existing WikiCFP list-page parser tests remain 100% green.

---

## 13. Performance & N+1 Behavior

- **No Ranking-Time Network Calls**: The extraction layer is 100% pure Python AST and regex parsing.
- **No Database Queries**: `extract_from_dict`, `extract_from_opportunity_model`, and `extract_from_raw_opportunity` operate in-memory on already-loaded objects.
- **Zero N+1 Queries**: Ranking pathways do not issue secondary queries or fetch detail pages dynamically.
- Detail page fetching belongs strictly in the asynchronous background scraper ingestion pipeline.

---

## 14. Migration Decision

**Migration Required**: **NO**

Phase 2.7B requires no database migration. The existing database columns and schema remain untouched. Evidence extraction operates in-memory on pipeline objects and existing models.
