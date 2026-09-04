"""
Deadline normalization engine for ResearchConnect AI (Phase 2.7C).

Transforms raw DeadlineEvidence into safe, deterministic, normalized temporal representations.

CRITICAL INVARIANTS:
1. Phase 2.7C normalizes deadline evidence into safe temporal representations.
   It does NOT calculate urgency tiers or change recommendation ranking.
2. Date-only deadlines are NOT coerced to 00:00:00 UTC.
   Academic submission deadlines without specified timezone apply the academic
   Anywhere on Earth (AoE) convention (23:59:59 AoE = 11:59:59 UTC next day),
   preserving local calendar date and explicitly flagging timezone_source as INFERRED.
3. Explicit AoE (UTC-12) converts correctly:
   2026-08-22 23:59:59 AoE -> 2026-08-23 11:59:59 UTC.
4. Ambiguous date formats (e.g. 04/05/2026) are flagged as AMBIGUOUS without guessing.
5. Missing values (None, TBA, TBD, N/A, Rolling) are flagged as MISSING without fabrication.
6. Unknown/invalid timezones are flagged as INVALID without silent fallback to UTC.
7. Normalization is strictly deterministic (no datetime.now() inside normalization, no network, no DB).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import logging
import re
from typing import Any
import zoneinfo

from app.ranking.deadline.extractors import (
    DeadlineEvidenceExtractor,
    parse_raw_date_components,
)
from app.ranking.deadline.models import (
    DeadlineEvidence,
    DeadlineEvidenceCollection,
    DeadlinePrecision,
    DeadlineProvenance,
    DeadlineType,
    DefaultTimezonePolicy,
    ExtractionMethod,
    NormalizationStatus,
    NormalizedDeadline,
    NormalizedDeadlineCollection,
    TimezoneIndicator,
    TimezoneSource,
)

logger = logging.getLogger(__name__)

# ── Timezone mappings and constants ───────────────────────────────────────────

AOE_OFFSET = timedelta(hours=-12)
AOE_TIMEZONE = timezone(AOE_OFFSET, name="AoE")

_NAMED_TIMEZONE_OFFSETS: dict[str, timedelta] = {
    # Standard academic and global abbreviations
    "aoe": AOE_OFFSET,
    "utc": timedelta(hours=0),
    "gmt": timedelta(hours=0),
    "z": timedelta(hours=0),
    "est": timedelta(hours=-5),
    "edt": timedelta(hours=-4),
    "cst": timedelta(hours=-6),
    "cdt": timedelta(hours=-5),
    "mst": timedelta(hours=-7),
    "mdt": timedelta(hours=-6),
    "pst": timedelta(hours=-8),
    "pdt": timedelta(hours=-7),
    "cet": timedelta(hours=1),
    "cest": timedelta(hours=2),
    "bst": timedelta(hours=1),
    "jst": timedelta(hours=9),
    "kst": timedelta(hours=9),
    "ist": timedelta(hours=5, minutes=30),
    "aest": timedelta(hours=10),
    "aedt": timedelta(hours=11),
    "sast": timedelta(hours=2),
}

_NUMERIC_OFFSET_RE = re.compile(
    r"^(?:utc|gmt)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE
)

_TIME_PARSE_RE = re.compile(
    r"^(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*([ap]\.?m\.?))?$", re.IGNORECASE
)


def parse_numeric_offset(raw_offset: str | None) -> tuple[timedelta | None, str | None]:
    """
    Parse a numeric timezone offset string (e.g. "+05:30", "-04:00", "+02", "-0800").

    Returns (timedelta, formatted_str) e.g. (timedelta(hours=5, minutes=30), "+05:30").
    """
    if not raw_offset or not raw_offset.strip():
        return None, None

    clean = raw_offset.strip()
    match = _NUMERIC_OFFSET_RE.match(clean)
    if not match:
        return None, None

    sign_str, hours_str, mins_str = match.groups()
    hours = int(hours_str)
    mins = int(mins_str) if mins_str else 0

    if hours > 14 or mins >= 60:
        return None, None

    total_seconds = (hours * 3600 + mins * 60) * (-1 if sign_str == "-" else 1)
    td = timedelta(seconds=total_seconds)
    formatted = f"{sign_str}{hours:02d}:{mins:02d}"
    return td, formatted


def resolve_timezone(
    tz_indicator: TimezoneIndicator,
    raw_snippet: str | None,
    local_date: date | None = None,
    local_time: time | None = None,
) -> tuple[timezone | zoneinfo.ZoneInfo | None, str | None, str | None, bool]:
    """
    Resolve timezone object, canonical name, offset string, and whether it's valid.

    Returns (tz_obj, tz_name, offset_str, is_valid).
    """
    if tz_indicator == TimezoneIndicator.EXPLICIT_AOE:
        return AOE_TIMEZONE, "AoE", "-12:00", True

    if tz_indicator == TimezoneIndicator.EXPLICIT_UTC:
        return timezone.utc, "UTC", "+00:00", True

    if tz_indicator == TimezoneIndicator.UNSPECIFIED:
        return None, None, None, True

    if not raw_snippet:
        return None, None, None, True

    snippet = raw_snippet.strip().lower()

    # 1. Direct match for AoE tokens
    if snippet in {"aoe", "anywhere on earth", "utc-12", "utc - 12", "gmt-12"}:
        return AOE_TIMEZONE, "AoE", "-12:00", True

    # 2. Check standard numeric offsets (+05:30, -04:00, etc.)
    offset_match = re.search(
        r"(?:(?:\b(?:utc|gmt)\s*)|(?<=\s)|(?<=:\d\d))([+-]\d{1,2}(?::?\d{2})?)\b",
        raw_snippet,
        re.IGNORECASE,
    )
    if offset_match:
        td, formatted = parse_numeric_offset(offset_match.group(1))
        if td is not None:
            tz = timezone(td, name=formatted)
            return tz, formatted, formatted, True

    # 3. Check known abbreviation
    # Look for individual words matching known timezone codes
    words = re.findall(r"\b[a-zA-Z]{2,5}\b", raw_snippet)
    for word in words:
        w_lower = word.lower()
        if w_lower in _NAMED_TIMEZONE_OFFSETS:
            td = _NAMED_TIMEZONE_OFFSETS[w_lower]
            hours = int(td.total_seconds() // 3600)
            mins = int((abs(td.total_seconds()) % 3600) // 60)
            sign = "+" if hours >= 0 else "-"
            formatted = f"{sign}{abs(hours):02d}:{mins:02d}"
            code_upper = word.upper()
            return timezone(td, name=code_upper), code_upper, formatted, True

    # 4. Check IANA timezone name (e.g. America/New_York, Europe/London)
    iana_match = re.search(r"\b([A-Za-z_]+/[A-Za-z_]+)\b", raw_snippet)
    if iana_match:
        iana_name = iana_match.group(1)
        try:
            zi = zoneinfo.ZoneInfo(iana_name)
            # Calculate offset for specific date/time if provided
            ref_dt = datetime.combine(
                local_date or date(2026, 1, 1),
                local_time or time(12, 0, 0),
            )
            utcoffset = zi.utcoffset(ref_dt)
            if utcoffset is not None:
                h = int(utcoffset.total_seconds() // 3600)
                m = int((abs(utcoffset.total_seconds()) % 3600) // 60)
                sign = "+" if h >= 0 else "-"
                formatted = f"{sign}{abs(h):02d}:{m:02d}"
                return zi, iana_name, formatted, True
            return zi, iana_name, None, True
        except Exception:
            return None, iana_name, None, False

    # If the source indicated a local named timezone but it could not be resolved:
    if tz_indicator == TimezoneIndicator.LOCAL_NAMED:
        return None, raw_snippet.strip(), None, False

    return None, None, None, True


def parse_time_string(time_str: str | None) -> time | None:
    """
    Parse a raw time string into a Python time object.

    Handles:
    - "23:59" -> time(23, 59, 0)
    - "23:59:59" -> time(23, 59, 59)
    - "11:59 PM" -> time(23, 59, 0)
    - "11:59:59 PM" -> time(23, 59, 59)
    - "5:00 AM" -> time(5, 0, 0)
    """
    if not time_str or not time_str.strip():
        return None

    clean = time_str.strip()
    match = _TIME_PARSE_RE.match(clean)
    if not match:
        return None

    h_str, m_str, s_str, am_pm = match.groups()
    hour = int(h_str)
    minute = int(m_str)
    second = int(s_str) if s_str else 0

    if am_pm:
        am_pm_clean = am_pm.replace(".", "").lower()
        if am_pm_clean == "pm" and hour < 12:
            hour += 12
        elif am_pm_clean == "am" and hour == 12:
            hour = 0

    if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
        return time(hour, minute, second)

    return None


# ── Canonical Deadline Normalizer ─────────────────────────────────────────────


class DeadlineNormalizer:
    """
    Authoritative, deterministic date and timezone normalizer for ResearchConnect AI.

    Transforms raw DeadlineEvidence or strings into standardized NormalizedDeadline models.
    """

    @classmethod
    def normalize_evidence(
        cls,
        evidence: DeadlineEvidence,
        policy: DefaultTimezonePolicy = DefaultTimezonePolicy.INFERRED_AOE,
    ) -> NormalizedDeadline:
        """
        Normalize a single DeadlineEvidence instance into a NormalizedDeadline.

        Pure, deterministic, in-memory execution.
        """
        # 1. Missing / Non-present evidence
        if not evidence.is_present:
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=None,
                local_time=None,
                timezone_name=None,
                timezone_offset=None,
                normalized_utc=None,
                precision=DeadlinePrecision.UNKNOWN,
                timezone_source=TimezoneSource.UNKNOWN,
                normalization_confidence=0.0,
                normalization_status=NormalizationStatus.MISSING,
                source_evidence=evidence,
                is_end_of_day_inferred=False,
                metadata={"reason": "non_date_or_missing_in_source"},
            )

        # 2. Ambiguous date representation (e.g. 04/05/2026)
        if evidence.is_ambiguous:
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=None,
                local_time=None,
                timezone_name=None,
                timezone_offset=None,
                normalized_utc=None,
                precision=evidence.precision,
                timezone_source=TimezoneSource.UNKNOWN,
                normalization_confidence=0.0,
                normalization_status=NormalizationStatus.AMBIGUOUS,
                source_evidence=evidence,
                is_end_of_day_inferred=False,
                metadata={"reason": "ambiguous_date_format_unresolved"},
            )

        # 3. Validate calendar date components
        if (
            evidence.parsed_year is None
            or evidence.parsed_month is None
            or evidence.parsed_day is None
        ):
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=None,
                local_time=None,
                timezone_name=None,
                timezone_offset=None,
                normalized_utc=None,
                precision=evidence.precision,
                timezone_source=TimezoneSource.UNKNOWN,
                normalization_confidence=0.0,
                normalization_status=NormalizationStatus.INVALID,
                source_evidence=evidence,
                is_end_of_day_inferred=False,
                metadata={"reason": "incomplete_calendar_date_components"},
            )

        try:
            local_date = date(
                evidence.parsed_year,
                evidence.parsed_month,
                evidence.parsed_day,
            )
        except ValueError as err:
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=None,
                local_time=None,
                timezone_name=None,
                timezone_offset=None,
                normalized_utc=None,
                precision=evidence.precision,
                timezone_source=TimezoneSource.UNKNOWN,
                normalization_confidence=0.0,
                normalization_status=NormalizationStatus.INVALID,
                source_evidence=evidence,
                is_end_of_day_inferred=False,
                metadata={"error": str(err)},
            )

        # 4. Resolve local time (if present)
        parsed_time = parse_time_string(evidence.parsed_time_str)

        # 5. Resolve timezone
        tz_obj, tz_name, tz_offset, is_tz_valid = resolve_timezone(
            evidence.timezone_indicator,
            evidence.raw_value,
            local_date=local_date,
            local_time=parsed_time,
        )

        if not is_tz_valid:
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=local_date,
                local_time=parsed_time,
                timezone_name=tz_name,
                timezone_offset=None,
                normalized_utc=None,
                precision=evidence.precision,
                timezone_source=TimezoneSource.UNKNOWN,
                normalization_confidence=0.0,
                normalization_status=NormalizationStatus.INVALID,
                source_evidence=evidence,
                is_end_of_day_inferred=False,
                metadata={"reason": f"unrecognized_or_invalid_timezone: {tz_name}"},
            )

        # 6. Branch by Precision and Timezone Availability
        # Case A: Explicit Time AND Explicit Timezone
        if parsed_time is not None and tz_obj is not None:
            local_dt = datetime.combine(local_date, parsed_time, tzinfo=tz_obj)
            normalized_utc = local_dt.astimezone(timezone.utc)
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=local_date,
                local_time=parsed_time,
                timezone_name=tz_name,
                timezone_offset=tz_offset,
                normalized_utc=normalized_utc,
                precision=evidence.precision,
                timezone_source=TimezoneSource.EXPLICIT,
                normalization_confidence=1.0,
                normalization_status=NormalizationStatus.EXPLICIT_TIMEZONE,
                source_evidence=evidence,
                is_end_of_day_inferred=False,
                metadata={"conversion": "explicit_datetime_to_utc"},
            )

        # Case B: Explicit Time with Unspecified Timezone
        if parsed_time is not None and tz_obj is None:
            if policy == DefaultTimezonePolicy.INFERRED_AOE and evidence.deadline_type == DeadlineType.SUBMISSION:
                # Time given, but timezone absent in academic submission -> Infer AoE
                local_dt = datetime.combine(local_date, parsed_time, tzinfo=AOE_TIMEZONE)
                normalized_utc = local_dt.astimezone(timezone.utc)
                return NormalizedDeadline(
                    deadline_type=evidence.deadline_type,
                    local_date=local_date,
                    local_time=parsed_time,
                    timezone_name="AoE",
                    timezone_offset="-12:00",
                    normalized_utc=normalized_utc,
                    precision=evidence.precision,
                    timezone_source=TimezoneSource.INFERRED,
                    normalization_confidence=0.85,
                    normalization_status=NormalizationStatus.INFERRED_TIMEZONE,
                    source_evidence=evidence,
                    is_end_of_day_inferred=False,
                    metadata={"policy": "academic_submission_time_inferred_aoe"},
                )
            elif policy == DefaultTimezonePolicy.UTC:
                local_dt = datetime.combine(local_date, parsed_time, tzinfo=timezone.utc)
                return NormalizedDeadline(
                    deadline_type=evidence.deadline_type,
                    local_date=local_date,
                    local_time=parsed_time,
                    timezone_name="UTC",
                    timezone_offset="+00:00",
                    normalized_utc=local_dt,
                    precision=evidence.precision,
                    timezone_source=TimezoneSource.INFERRED,
                    normalization_confidence=0.70,
                    normalization_status=NormalizationStatus.INFERRED_TIMEZONE,
                    source_evidence=evidence,
                    is_end_of_day_inferred=False,
                    metadata={"policy": "fallback_utc_policy"},
                )
            else:
                return NormalizedDeadline(
                    deadline_type=evidence.deadline_type,
                    local_date=local_date,
                    local_time=parsed_time,
                    timezone_name=None,
                    timezone_offset=None,
                    normalized_utc=None,
                    precision=evidence.precision,
                    timezone_source=TimezoneSource.UNKNOWN,
                    normalization_confidence=0.60,
                    normalization_status=NormalizationStatus.NORMALIZED,
                    source_evidence=evidence,
                    is_end_of_day_inferred=False,
                    metadata={"policy": "strict_unknown_timezone"},
                )

        # Case C: Date-Only with Explicit Timezone (e.g. "Aug 22, 2026 AoE")
        if parsed_time is None and tz_obj is not None:
            # Explicit AoE or UTC date without time -> End of day (23:59:59) in that timezone
            end_of_day = time(23, 59, 59)
            local_dt = datetime.combine(local_date, end_of_day, tzinfo=tz_obj)
            normalized_utc = local_dt.astimezone(timezone.utc)
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=local_date,
                local_time=end_of_day,
                timezone_name=tz_name,
                timezone_offset=tz_offset,
                normalized_utc=normalized_utc,
                precision=DeadlinePrecision.DATE_ONLY,
                timezone_source=TimezoneSource.EXPLICIT,
                normalization_confidence=0.95,
                normalization_status=NormalizationStatus.EXPLICIT_TIMEZONE,
                source_evidence=evidence,
                is_end_of_day_inferred=True,
                metadata={"convention": "end_of_day_in_explicit_tz"},
            )

        # Case D: Date-Only with Unspecified Timezone (e.g. "Aug 22, 2026")
        # Academic submission convention:
        if (
            policy == DefaultTimezonePolicy.INFERRED_AOE
            and evidence.deadline_type == DeadlineType.SUBMISSION
        ):
            # Academic standard: Submissions accepted until end of calendar date Anywhere on Earth
            end_of_day_aoe = time(23, 59, 59)
            local_dt = datetime.combine(local_date, end_of_day_aoe, tzinfo=AOE_TIMEZONE)
            normalized_utc = local_dt.astimezone(timezone.utc)
            return NormalizedDeadline(
                deadline_type=evidence.deadline_type,
                local_date=local_date,
                local_time=end_of_day_aoe,
                timezone_name="AoE",
                timezone_offset="-12:00",
                normalized_utc=normalized_utc,
                precision=DeadlinePrecision.DATE_ONLY,
                timezone_source=TimezoneSource.INFERRED,
                normalization_confidence=0.85,
                normalization_status=NormalizationStatus.INFERRED_TIMEZONE,
                source_evidence=evidence,
                is_end_of_day_inferred=True,
                metadata={
                    "convention": "academic_submission_date_only_inferred_aoe",
                    "explanation": "23:59:59 AoE on calendar date equals 11:59:59 UTC on subsequent calendar day",
                },
            )

        # For non-submission milestones (e.g. EVENT_START, EVENT_END, NOTIFICATION) or STRICT_UNKNOWN:
        return NormalizedDeadline(
            deadline_type=evidence.deadline_type,
            local_date=local_date,
            local_time=None,
            timezone_name=None,
            timezone_offset=None,
            normalized_utc=None,
            precision=DeadlinePrecision.DATE_ONLY,
            timezone_source=TimezoneSource.UNKNOWN,
            normalization_confidence=0.90,
            normalization_status=NormalizationStatus.DATE_ONLY,
            source_evidence=evidence,
            is_end_of_day_inferred=False,
            metadata={"description": "calendar_date_without_synthesized_instant"},
        )

    @classmethod
    def normalize_collection(
        cls,
        collection: DeadlineEvidenceCollection,
        policy: DefaultTimezonePolicy = DefaultTimezonePolicy.INFERRED_AOE,
    ) -> NormalizedDeadlineCollection:
        """
        Normalize all deadline evidence items in a collection.
        """
        norm_collection = NormalizedDeadlineCollection(opportunity_id=collection.opportunity_id)
        for evidence in collection.items:
            norm_collection.add(cls.normalize_evidence(evidence, policy=policy))
        return norm_collection

    @classmethod
    def normalize_raw_string(
        cls,
        raw: str | None,
        deadline_type: DeadlineType = DeadlineType.SUBMISSION,
        source: str = "unknown",
        source_field: str = "",
        provenance: DeadlineProvenance = DeadlineProvenance.UNKNOWN,
        policy: DefaultTimezonePolicy = DefaultTimezonePolicy.INFERRED_AOE,
    ) -> NormalizedDeadline:
        """
        Extract and normalize a raw date/time string in one seamless call.

        Provides the single canonical normalization path for external ingestion components.
        """
        yr, mo, dy, tm_str, prec, tz_ind, is_pres, is_ambig = parse_raw_date_components(raw)

        evidence = DeadlineEvidence(
            deadline_type=deadline_type,
            raw_value=raw,
            raw_text=raw,
            source=source,
            source_field=source_field,
            extraction_method=ExtractionMethod.DIRECT_FIELD,
            confidence=1.0 if is_pres else 0.0,
            provenance=provenance,
            is_present=is_pres,
            precision=prec,
            timezone_indicator=tz_ind,
            parsed_year=yr,
            parsed_month=mo,
            parsed_day=dy,
            parsed_time_str=tm_str,
            is_ambiguous=is_ambig,
        )

        return cls.normalize_evidence(evidence, policy=policy)

    @classmethod
    def normalize_opportunity_model(
        cls,
        model: Any,
        policy: DefaultTimezonePolicy = DefaultTimezonePolicy.INFERRED_AOE,
    ) -> NormalizedDeadlineCollection:
        """
        Extract evidence from an existing OpportunityModel and normalize all milestones.
        """
        evidence_col = DeadlineEvidenceExtractor.extract_from_opportunity_model(model)
        return cls.normalize_collection(evidence_col, policy=policy)

    @classmethod
    def normalize_raw_opportunity(
        cls,
        raw_opp: Any,
        policy: DefaultTimezonePolicy = DefaultTimezonePolicy.INFERRED_AOE,
    ) -> NormalizedDeadlineCollection:
        """
        Extract evidence from a scraper RawOpportunity and normalize all milestones.
        """
        evidence_col = DeadlineEvidenceExtractor.extract_from_raw_opportunity(raw_opp)
        return cls.normalize_collection(evidence_col, policy=policy)
