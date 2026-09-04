"""
Deadline evidence extractors for ResearchConnect AI (Phase 2.7B).

Provides deterministic, pure extraction of deadline evidence from:
1. Database OpportunityModel entities
2. Scraped RawOpportunity payloads
3. WikiCFP detail-page structured tables
4. Unstructured CFP / announcement text

CRITICAL INVARIANTS:
1. Exact raw strings are ALWAYS preserved.
2. Date-only evidence is never coerced to midnight UTC.
3. Explicit AoE indicators are preserved as TimezoneIndicator.EXPLICIT_AOE without conversion.
4. Missing, TBA, or ambiguous dates are preserved conservatively without fabrication.
"""
from __future__ import annotations

from datetime import date, datetime
import logging
import re
from typing import Any

from app.ranking.deadline.models import (
    DeadlineEvidence,
    DeadlineEvidenceCollection,
    DeadlinePrecision,
    DeadlineProvenance,
    DeadlineType,
    ExtractionMethod,
    TimezoneIndicator,
)

logger = logging.getLogger(__name__)

# ── Pattern matching for date & timezone attributes ───────────────────────────

_AOE_PATTERN = re.compile(
    r"\b(aoe|anywhere\s+on\s+earth|utc\s*-\s*12(?::00)?)\b", re.IGNORECASE
)
_UTC_PATTERN = re.compile(
    r"(?:\b(?:utc|gmt)\b|(?<=\d)z\b|\bz\b)", re.IGNORECASE
)
_OFFSET_PATTERN = re.compile(
    r"(?:(?:\b(?:utc|gmt)\s*)|(?<=\s)|(?<=:\d\d))([+-]\d{1,2}(?::?\d{2})?)\b", re.IGNORECASE
)
_LOCAL_TZ_PATTERN = re.compile(
    r"\b(est|edt|cst|cdt|mst|mdt|pst|pdt|cet|cest|gmt|bst|jst|kst|ist|aest|sast|[A-Za-z_]+/[A-Za-z_]+)\b",
    re.IGNORECASE,
)
_NON_DATE_PATTERN = re.compile(
    r"^(n/?a|na|tba|tbd|none|rolling|see\s+website|soon|to\s+be\s+announced|to\s+be\s+determined)$",
    re.IGNORECASE,
)
_TIME_PATTERN = re.compile(
    r"(?:(?<=[T\s])|^)(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?)\b", re.IGNORECASE
)
_MONTHS_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_DATE_RANGE_SPLIT = re.compile(r"\s*-\s*|\s+to\s+", re.IGNORECASE)

# Standard English date regex: "Aug 22, 2026", "22 Aug 2026", "August 22 2026", "2026-08-22"
_MONTH_NAME_REGEX = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_MDY_RE = re.compile(
    rf"\b({_MONTH_NAME_REGEX})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_DMY_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAME_REGEX}),?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_ISO_RE = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})(?=[T\s]|$)"
)
_SLASH_RE = re.compile(
    r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b"
)


def parse_raw_date_components(
    raw: str | None,
) -> tuple[
    int | None,             # year
    int | None,             # month
    int | None,             # day
    str | None,             # time_str
    DeadlinePrecision,      # precision
    TimezoneIndicator,      # timezone_indicator
    bool,                   # is_present
    bool,                   # is_ambiguous
]:
    """
    Extract date components, precision, and timezone indicator from a raw string.

    CRITICAL: Does NOT convert to UTC or synthesize an artificial timestamp.
    """
    if not raw or not raw.strip():
        return None, None, None, None, DeadlinePrecision.UNKNOWN, TimezoneIndicator.UNSPECIFIED, False, False

    clean_raw = raw.strip()

    # Check for non-date strings (TBA, TBD, N/A, etc.)
    if _NON_DATE_PATTERN.match(clean_raw):
        return None, None, None, None, DeadlinePrecision.UNKNOWN, TimezoneIndicator.UNSPECIFIED, False, False

    # Extract explicit timezone indicator
    tz_ind = TimezoneIndicator.UNSPECIFIED
    if _AOE_PATTERN.search(clean_raw):
        tz_ind = TimezoneIndicator.EXPLICIT_AOE
    elif _UTC_PATTERN.search(clean_raw):
        tz_ind = TimezoneIndicator.EXPLICIT_UTC
    elif _OFFSET_PATTERN.search(clean_raw):
        tz_ind = TimezoneIndicator.EXPLICIT_OFFSET
    elif _LOCAL_TZ_PATTERN.search(clean_raw):
        tz_ind = TimezoneIndicator.LOCAL_NAMED

    # Extract time component if present
    time_match = _TIME_PATTERN.search(clean_raw)
    time_str = time_match.group(1).strip() if time_match else None
    precision = DeadlinePrecision.EXACT_TIME if time_str else DeadlinePrecision.DATE_ONLY

    year: int | None = None
    month: int | None = None
    day: int | None = None
    is_ambiguous = False

    # 1. Try ISO: YYYY-MM-DD
    iso_match = _ISO_RE.search(clean_raw)
    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        day = int(iso_match.group(3))
        return year, month, day, time_str, precision, tz_ind, True, False

    # 2. Try Month Day, Year: e.g. "Aug 22, 2026"
    mdy_match = _MDY_RE.search(clean_raw)
    if mdy_match:
        m_name = mdy_match.group(1).lower()
        month = _MONTHS_MAP.get(m_name)
        day = int(mdy_match.group(2))
        year = int(mdy_match.group(3))
        return year, month, day, time_str, precision, tz_ind, True, False

    # 3. Try Day Month Year: e.g. "22 Aug 2026"
    dmy_match = _DMY_RE.search(clean_raw)
    if dmy_match:
        day = int(dmy_match.group(1))
        m_name = dmy_match.group(2).lower()
        month = _MONTHS_MAP.get(m_name)
        year = int(dmy_match.group(3))
        return year, month, day, time_str, precision, tz_ind, True, False

    # 4. Try Slash format: e.g. "04/05/2026" (inherently ambiguous if both <= 12)
    slash_match = _SLASH_RE.search(clean_raw)
    if slash_match:
        p1 = int(slash_match.group(1))
        p2 = int(slash_match.group(2))
        raw_yr = slash_match.group(3)
        year = int(raw_yr) if len(raw_yr) == 4 else (2000 + int(raw_yr) if int(raw_yr) < 70 else 1900 + int(raw_yr))
        if p1 > 12 and p2 <= 12:
            # Clearly Day/Month/Year
            day, month = p1, p2
        elif p2 > 12 and p1 <= 12:
            # Clearly Month/Day/Year
            month, day = p1, p2
        else:
            # Ambiguous! Assume Month/Day but mark ambiguous
            month, day = p1, p2
            is_ambiguous = True
        return year, month, day, time_str, precision, tz_ind, True, is_ambiguous

    # 5. Fallback: Month and Year only (e.g. "August 2026")
    m_only = re.search(rf"\b({_MONTH_NAME_REGEX})\s+(\d{{4}})\b", clean_raw, re.IGNORECASE)
    if m_only:
        m_name = m_only.group(1).lower()
        month = _MONTHS_MAP.get(m_name)
        year = int(m_only.group(2))
        return year, month, None, time_str, DeadlinePrecision.YEAR_MONTH, tz_ind, True, False

    return None, None, None, time_str, DeadlinePrecision.UNKNOWN, tz_ind, True, True


class DeadlineEvidenceExtractor:
    """
    Extracts deadline evidence from heterogeneous academic opportunity representations.
    """

    @classmethod
    def extract_milestone_from_string(
        cls,
        raw: str | None,
        deadline_type: DeadlineType = DeadlineType.SUBMISSION,
        source: str = "unknown",
        provenance: DeadlineProvenance = DeadlineProvenance.UNKNOWN,
    ) -> DeadlineEvidence:
        """
        Extract a single deadline evidence item from a string.
        """
        yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(raw)
        return DeadlineEvidence(
            deadline_type=deadline_type,
            raw_value=raw,
            raw_text=f"{deadline_type.value}: {raw}" if raw else "",
            source=source,
            source_field="",
            extraction_method=ExtractionMethod.DIRECT_FIELD,
            confidence=1.0 if is_pres else 0.0,
            provenance=provenance,
            is_present=is_pres,
            precision=prec,
            timezone_indicator=tz_ind,
            parsed_year=yr,
            parsed_month=mo,
            parsed_day=dy,
            parsed_time_str=tm,
            is_ambiguous=is_ambig,
        )

    @classmethod
    def extract_from_raw_opportunity(
        cls,
        raw_opp: Any,
    ) -> DeadlineEvidenceCollection:
        """
        Extract deadline evidence from a scraped RawOpportunity record.
        """
        collection = DeadlineEvidenceCollection()
        source_name = getattr(raw_opp, "source_name", "wikicfp")
        source_url = getattr(raw_opp, "source_url", None)

        # 1. Primary submission deadline string
        raw_sub = getattr(raw_opp, "raw_submission_deadline", None)
        if raw_sub is not None:
            yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(raw_sub)
            ev = DeadlineEvidence(
                deadline_type=DeadlineType.SUBMISSION,
                raw_value=raw_sub,
                raw_text=f"Submission Deadline: {raw_sub}",
                source=source_name,
                source_url=source_url,
                source_field="raw_submission_deadline",
                extraction_method=ExtractionMethod.DIRECT_FIELD,
                confidence=1.0 if is_pres else 0.5,
                provenance=DeadlineProvenance.WIKICFP_LIST_PAGE,
                is_present=is_pres,
                precision=prec,
                timezone_indicator=tz_ind,
                parsed_year=yr,
                parsed_month=mo,
                parsed_day=dy,
                parsed_time_str=tm,
                is_ambiguous=is_ambig,
            )
            collection.add(ev)

        # 2. Event dates (e.g. "Oct 24, 2026 - Oct 25, 2026")
        raw_event = getattr(raw_opp, "raw_event_dates", None)
        if raw_event is not None:
            cls._extract_event_dates_range(
                collection,
                raw_event,
                source=source_name,
                source_url=source_url,
                provenance=DeadlineProvenance.WIKICFP_LIST_PAGE,
            )

        return collection

    @classmethod
    def extract_from_opportunity_model(
        cls,
        opp: Any,
    ) -> DeadlineEvidenceCollection:
        """
        Extract deadline evidence from an existing SQLAlchemy OpportunityModel or dict.
        """
        collection = DeadlineEvidenceCollection(
            opportunity_id=str(getattr(opp, "id", None) or (opp.get("id") if isinstance(opp, dict) else None))
        )

        def _get(attr: str) -> Any:
            return opp.get(attr) if isinstance(opp, dict) else getattr(opp, attr, None)

        def _parse_field_date(val: Any) -> tuple[str, int | None, int | None, int | None, str | None, DeadlinePrecision, TimezoneIndicator]:
            if isinstance(val, (datetime, date)):
                raw_v = val.isoformat()
                tm = val.strftime("%H:%M:%S") if isinstance(val, datetime) else None
                prec = DeadlinePrecision.EXACT_TIME if isinstance(val, datetime) else DeadlinePrecision.DATE_ONLY
                tz_i = TimezoneIndicator.EXPLICIT_UTC if isinstance(val, datetime) and val.tzinfo else TimezoneIndicator.UNSPECIFIED
                return raw_v, val.year, val.month, val.day, tm, prec, tz_i
            raw_v = str(val)
            yr, mo, dy, tm, prec, tz_i, _, _ = parse_raw_date_components(raw_v)
            return raw_v, yr, mo, dy, tm, prec, tz_i

        # 1. Submission Deadline
        sub = _get("submission_deadline")
        if sub is not None:
            raw_val, yr, mo, dy, tm, prec, tz_ind = _parse_field_date(sub)
            ev = DeadlineEvidence(
                deadline_type=DeadlineType.SUBMISSION,
                raw_value=raw_val,
                raw_text=f"submission_deadline: {raw_val}",
                source="database",
                source_field="submission_deadline",
                extraction_method=ExtractionMethod.DIRECT_FIELD,
                confidence=1.0,
                provenance=DeadlineProvenance.DATABASE_RECORD,
                is_present=True,
                precision=prec,
                timezone_indicator=tz_ind,
                parsed_year=yr,
                parsed_month=mo,
                parsed_day=dy,
                parsed_time_str=tm,
            )
            collection.add(ev)

        # 2. Notification Date
        notif = _get("notification_date")
        if notif is not None:
            raw_val, yr, mo, dy, tm, prec, tz_ind = _parse_field_date(notif)
            ev = DeadlineEvidence(
                deadline_type=DeadlineType.NOTIFICATION,
                raw_value=raw_val,
                raw_text=f"notification_date: {raw_val}",
                source="database",
                source_field="notification_date",
                extraction_method=ExtractionMethod.DIRECT_FIELD,
                confidence=1.0,
                provenance=DeadlineProvenance.DATABASE_RECORD,
                is_present=True,
                precision=prec,
                timezone_indicator=tz_ind,
                parsed_year=yr,
                parsed_month=mo,
                parsed_day=dy,
                parsed_time_str=tm,
            )
            collection.add(ev)

        # 3. Camera-Ready Deadline
        cam = _get("camera_ready_deadline")
        if cam is not None:
            raw_val, yr, mo, dy, tm, prec, tz_ind = _parse_field_date(cam)
            ev = DeadlineEvidence(
                deadline_type=DeadlineType.CAMERA_READY,
                raw_value=raw_val,
                raw_text=f"camera_ready_deadline: {raw_val}",
                source="database",
                source_field="camera_ready_deadline",
                extraction_method=ExtractionMethod.DIRECT_FIELD,
                confidence=1.0,
                provenance=DeadlineProvenance.DATABASE_RECORD,
                is_present=True,
                precision=prec,
                timezone_indicator=tz_ind,
                parsed_year=yr,
                parsed_month=mo,
                parsed_day=dy,
                parsed_time_str=tm,
            )
            collection.add(ev)

        # 4. Event Start Date
        ev_start = _get("event_start_date")
        if ev_start is not None:
            raw_val, yr, mo, dy, tm, prec, tz_ind = _parse_field_date(ev_start)
            collection.add(
                DeadlineEvidence(
                    deadline_type=DeadlineType.EVENT_START,
                    raw_value=raw_val,
                    raw_text=f"event_start_date: {raw_val}",
                    source="database",
                    source_field="event_start_date",
                    extraction_method=ExtractionMethod.DIRECT_FIELD,
                    confidence=1.0,
                    provenance=DeadlineProvenance.DATABASE_RECORD,
                    is_present=True,
                    precision=prec,
                    timezone_indicator=tz_ind,
                    parsed_year=yr,
                    parsed_month=mo,
                    parsed_day=dy,
                    parsed_time_str=tm,
                )
            )

        # 5. Event End Date
        ev_end = _get("event_end_date")
        if ev_end is not None:
            raw_val, yr, mo, dy, tm, prec, tz_ind = _parse_field_date(ev_end)
            collection.add(
                DeadlineEvidence(
                    deadline_type=DeadlineType.EVENT_END,
                    raw_value=raw_val,
                    raw_text=f"event_end_date: {raw_val}",
                    source="database",
                    source_field="event_end_date",
                    extraction_method=ExtractionMethod.DIRECT_FIELD,
                    confidence=1.0,
                    provenance=DeadlineProvenance.DATABASE_RECORD,
                    is_present=True,
                    precision=prec,
                    timezone_indicator=tz_ind,
                    parsed_year=yr,
                    parsed_month=mo,
                    parsed_day=dy,
                    parsed_time_str=tm,
                )
            )

        return collection

    @classmethod
    def extract_from_milestone_dict(
        cls,
        milestones: dict[str, str],
        source: str = "wikicfp",
        source_url: str | None = None,
        provenance: DeadlineProvenance = DeadlineProvenance.WIKICFP_DETAIL_PAGE,
    ) -> DeadlineEvidenceCollection:
        """
        Extract deadline evidence from a dictionary of milestone labels and raw date strings.
        Commonly produced by WikiCFP detail-page parsers.
        """
        collection = DeadlineEvidenceCollection()

        for label, raw_val in milestones.items():
            norm_label = label.lower().strip().rstrip(":")
            m_type = cls._classify_milestone_label(norm_label)

            if m_type == DeadlineType.UNKNOWN and "when" in norm_label:
                cls._extract_event_dates_range(
                    collection, raw_val, source=source, source_url=source_url, provenance=provenance
                )
                continue

            yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(raw_val)

            ev = DeadlineEvidence(
                deadline_type=m_type,
                raw_value=raw_val,
                raw_text=f"{label}: {raw_val}",
                source=source,
                source_url=source_url,
                source_field=label,
                extraction_method=ExtractionMethod.TABLE_ROW,
                confidence=0.95 if is_pres else 0.5,
                provenance=provenance,
                is_present=is_pres,
                precision=prec,
                timezone_indicator=tz_ind,
                parsed_year=yr,
                parsed_month=mo,
                parsed_day=dy,
                parsed_time_str=tm,
                is_ambiguous=is_ambig,
            )
            collection.add(ev)

        return collection

    @classmethod
    def extract_from_text(
        cls,
        text: str,
        source: str = "free_text",
        source_url: str | None = None,
    ) -> DeadlineEvidenceCollection:
        """
        Extract deadline evidence from unstructured CFP or announcement text using regex.
        """
        collection = DeadlineEvidenceCollection()
        if not text:
            return collection

        patterns: list[tuple[re.Pattern, DeadlineType, str]] = [
            (
                re.compile(
                    r"(?:abstract(?:\s+registration)?(?:\s+submission)?)\s*(?:deadline|due|date)?\s*[:\-]\s*([A-Za-z0-9, /:-]+(?:\s*(?:aoe|utc|gmt)[^\n\r,.]*)?)",
                    re.IGNORECASE,
                ),
                DeadlineType.ABSTRACT,
                "abstract_deadline_text",
            ),
            (
                re.compile(
                    r"(?<!abstract\s)(?:paper|manuscript|submission|full\s+paper)\s*(?:deadline|due|date)?\s*[:\-]\s*([A-Za-z0-9, /:-]+(?:\s*(?:aoe|utc|gmt)[^\n\r,.]*)?)",
                    re.IGNORECASE,
                ),
                DeadlineType.SUBMISSION,
                "submission_deadline_text",
            ),
            (
                re.compile(
                    r"(?:notification|acceptance\s+notification|decision)\s*(?:due|date|deadline)?\s*[:\-]\s*([A-Za-z0-9, /:-]+)",
                    re.IGNORECASE,
                ),
                DeadlineType.NOTIFICATION,
                "notification_date_text",
            ),
            (
                re.compile(
                    r"(?:camera[- ]ready|final\s+version|final\s+manuscript)\s*(?:due|deadline|date)?\s*[:\-]\s*([A-Za-z0-9, /:-]+)",
                    re.IGNORECASE,
                ),
                DeadlineType.CAMERA_READY,
                "camera_ready_deadline_text",
            ),
            (
                re.compile(
                    r"(?:author\s+registration|registration(?:\s+deadline)?|early\s+bird(?:\s+registration)?)\s*[:\-]\s*([A-Za-z0-9, /:-]+)",
                    re.IGNORECASE,
                ),
                DeadlineType.REGISTRATION,
                "registration_deadline_text",
            ),
        ]

        for pattern, m_type, field_label in patterns:
            for match in pattern.finditer(text):
                raw_match = match.group(1).strip().rstrip(".,;")
                yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(raw_match)
                # Only keep if parseable or affirmatively indicated
                if is_pres and (yr is not None or dy is not None):
                    ev = DeadlineEvidence(
                        deadline_type=m_type,
                        raw_value=raw_match,
                        raw_text=match.group(0).strip(),
                        source=source,
                        source_url=source_url,
                        source_field=field_label,
                        extraction_method=ExtractionMethod.REGEX_PATTERN,
                        confidence=0.85,
                        provenance=DeadlineProvenance.FREE_TEXT,
                        is_present=True,
                        precision=prec,
                        timezone_indicator=tz_ind,
                        parsed_year=yr,
                        parsed_month=mo,
                        parsed_day=dy,
                        parsed_time_str=tm,
                        is_ambiguous=is_ambig,
                    )
                    collection.add(ev)

        return collection

    # ── Private helper methods ─────────────────────────────────────────────────

    @classmethod
    def _classify_milestone_label(cls, label: str) -> DeadlineType:
        """Categorize a normalized milestone label into a standard DeadlineType."""
        if any(w in label for w in ["abstract", "abstract registration", "abstract submission"]):
            return DeadlineType.ABSTRACT
        if any(w in label for w in ["submission", "paper deadline", "paper due", "full paper", "manuscript"]):
            return DeadlineType.SUBMISSION
        if any(w in label for w in ["notification", "acceptance", "decision"]):
            return DeadlineType.NOTIFICATION
        if any(w in label for w in ["final version", "camera ready", "camera-ready", "final manuscript"]):
            return DeadlineType.CAMERA_READY
        if any(w in label for w in ["registration", "early bird"]):
            return DeadlineType.REGISTRATION
        if any(w in label for w in ["event start", "conference start"]):
            return DeadlineType.EVENT_START
        if any(w in label for w in ["event end", "conference end"]):
            return DeadlineType.EVENT_END
        return DeadlineType.UNKNOWN

    @classmethod
    def _extract_event_dates_range(
        cls,
        collection: DeadlineEvidenceCollection,
        raw_range: str,
        source: str,
        source_url: str | None,
        provenance: DeadlineProvenance,
    ) -> None:
        """Extract EVENT_START and EVENT_END from a date range string."""
        parts = _DATE_RANGE_SPLIT.split(raw_range.strip())
        start_raw = parts[0].strip() if parts else None
        end_raw = parts[1].strip() if len(parts) > 1 else start_raw

        if start_raw:
            yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(start_raw)
            collection.add(
                DeadlineEvidence(
                    deadline_type=DeadlineType.EVENT_START,
                    raw_value=start_raw,
                    raw_text=f"Event Start: {start_raw}",
                    source=source,
                    source_url=source_url,
                    source_field="event_start",
                    extraction_method=ExtractionMethod.TABLE_ROW,
                    confidence=0.95 if is_pres else 0.5,
                    provenance=provenance,
                    is_present=is_pres,
                    precision=prec,
                    timezone_indicator=tz_ind,
                    parsed_year=yr,
                    parsed_month=mo,
                    parsed_day=dy,
                    parsed_time_str=tm,
                    is_ambiguous=is_ambig,
                )
            )

        if end_raw:
            yr, mo, dy, tm, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(end_raw)
            collection.add(
                DeadlineEvidence(
                    deadline_type=DeadlineType.EVENT_END,
                    raw_value=end_raw,
                    raw_text=f"Event End: {end_raw}",
                    source=source,
                    source_url=source_url,
                    source_field="event_end",
                    extraction_method=ExtractionMethod.TABLE_ROW,
                    confidence=0.95 if is_pres else 0.5,
                    provenance=provenance,
                    is_present=is_pres,
                    precision=prec,
                    timezone_indicator=tz_ind,
                    parsed_year=yr,
                    parsed_month=mo,
                    parsed_day=dy,
                    parsed_time_str=tm,
                    is_ambiguous=is_ambig,
                )
            )
