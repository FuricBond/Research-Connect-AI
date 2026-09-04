"""
Deadline evidence domain models for ResearchConnect AI (Phase 2.7B).

This module defines typed representations for raw, structured, and provenance-tracked
deadline evidence extracted from research sources.

CRITICAL INVARIANTS:
1. Phase 2.7B extracts evidence; it does NOT determine the final normalized deadline instant.
2. Date-only evidence is preserved with Precision.DATE_ONLY and TimezoneIndicator.UNSPECIFIED.
   It must NEVER be converted to midnight UTC in this phase.
3. Explicit AoE is preserved as TimezoneIndicator.EXPLICIT_AOE without premature conversion.
4. Missing, ambiguous, or non-date strings (TBA, TBD, N/A) are preserved truthfully.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any


class DeadlineType(str, Enum):
    """Semantic milestone type in the academic publication lifecycle."""

    SUBMISSION = "SUBMISSION"                  # Main paper / manuscript submission cut-off
    ABSTRACT = "ABSTRACT"                      # Abstract registration deadline (pre-submission)
    NOTIFICATION = "NOTIFICATION"              # Author notification of acceptance / rejection
    CAMERA_READY = "CAMERA_READY"              # Final publication-ready manuscript cut-off
    REGISTRATION = "REGISTRATION"              # Author or early-bird conference registration
    EVENT_START = "EVENT_START"                # Event convening / start date
    EVENT_END = "EVENT_END"                    # Event conclusion / end date
    UNKNOWN = "UNKNOWN"                        # Unspecified or unclassified milestone


class DeadlinePrecision(str, Enum):
    """Granularity of the extracted deadline information."""

    DATE_ONLY = "DATE_ONLY"                    # e.g. "Aug 22, 2026" (calendar date without time)
    EXACT_TIME = "EXACT_TIME"                  # e.g. "Aug 22, 2026 23:59" (hour/minute specified)
    YEAR_MONTH = "YEAR_MONTH"                  # e.g. "August 2026" (month and year only)
    APPROXIMATE = "APPROXIMATE"                # e.g. "Late August 2026", "Mid-September"
    UNKNOWN = "UNKNOWN"                        # Could not determine precision


class TimezoneIndicator(str, Enum):
    """Timezone information explicitly provided or denoted by the source."""

    EXPLICIT_AOE = "EXPLICIT_AOE"              # Explicitly says "AoE", "Anywhere on Earth", "UTC-12"
    EXPLICIT_UTC = "EXPLICIT_UTC"              # Explicitly says "UTC", "GMT", "Z"
    EXPLICIT_OFFSET = "EXPLICIT_OFFSET"        # Explicitly specifies offset, e.g. "+05:30", "-04:00"
    LOCAL_NAMED = "LOCAL_NAMED"                # Mentions named timezone, e.g. "EST", "PST", "CET", "JST"
    UNSPECIFIED = "UNSPECIFIED"                # No timezone information supplied by source


class DeadlineProvenance(str, Enum):
    """Provenance origin of the extracted deadline evidence."""

    WIKICFP_LIST_PAGE = "WIKICFP_LIST_PAGE"    # Scraped from WikiCFP list table (/cfp/call)
    WIKICFP_DETAIL_PAGE = "WIKICFP_DETAIL_PAGE"# Scraped from WikiCFP detail page (event.showcfp)
    OPENALEX = "OPENALEX"                      # Ingested via OpenAlex API
    CROSSREF = "CROSSREF"                      # Ingested via Crossref API
    DATABASE_RECORD = "DATABASE_RECORD"        # Read from existing OpportunityModel database columns
    FREE_TEXT = "FREE_TEXT"                    # Extracted from CFP description or unstructured text
    UNKNOWN = "UNKNOWN"                        # Unknown provenance


class ExtractionMethod(str, Enum):
    """Technique used to extract the deadline evidence."""

    DIRECT_FIELD = "DIRECT_FIELD"              # Read directly from structured model or payload field
    TABLE_ROW = "TABLE_ROW"                    # Extracted from labeled HTML table row
    KEY_VALUE_PAIR = "KEY_VALUE_PAIR"          # Extracted from labeled definition list or header/value
    REGEX_PATTERN = "REGEX_PATTERN"            # Extracted from unstructured text via regex pattern
    FALLBACK = "FALLBACK"                      # Fallback extraction


@dataclass(frozen=True)
class DeadlineEvidence:
    """
    Atomic unit of deadline evidence extracted from a source.

    Preserves what the source explicitly states without forcing premature normalization.
    """

    deadline_type: DeadlineType
    raw_value: str | None                      # The verbatim date/time string extracted
    raw_text: str | None = None                # Contextual snippet or table row text
    source: str = "unknown"                    # e.g. "wikicfp", "openalex", "database"
    source_url: str | None = None              # Provenance URL of page/record
    source_field: str = ""                     # Field label e.g. "submission_deadline", "Notification Due"
    extraction_method: ExtractionMethod = ExtractionMethod.DIRECT_FIELD
    confidence: float = 1.0                    # Extraction confidence in range [0.0, 1.0]
    provenance: DeadlineProvenance = DeadlineProvenance.UNKNOWN
    is_present: bool = True                    # False if source explicitly indicates N/A, TBA, TBD, or missing
    precision: DeadlinePrecision = DeadlinePrecision.DATE_ONLY
    timezone_indicator: TimezoneIndicator = TimezoneIndicator.UNSPECIFIED
    parsed_year: int | None = None             # Discerned calendar year (if clearly parseable)
    parsed_month: int | None = None            # Discerned calendar month 1-12 (if clearly parseable)
    parsed_day: int | None = None              # Discerned calendar day 1-31 (if clearly parseable)
    parsed_time_str: str | None = None         # Verbatim time string e.g. "23:59", "11:59 PM"
    is_ambiguous: bool = False                 # True if format is ambiguous (e.g. "04/05/2026")
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert evidence item to a serializable dictionary."""
        return {
            "deadline_type": self.deadline_type.value,
            "raw_value": self.raw_value,
            "raw_text": self.raw_text,
            "source": self.source,
            "source_url": self.source_url,
            "source_field": self.source_field,
            "extraction_method": self.extraction_method.value,
            "confidence": round(self.confidence, 4),
            "provenance": self.provenance.value,
            "is_present": self.is_present,
            "precision": self.precision.value,
            "timezone_indicator": self.timezone_indicator.value,
            "parsed_year": self.parsed_year,
            "parsed_month": self.parsed_month,
            "parsed_day": self.parsed_day,
            "parsed_time_str": self.parsed_time_str,
            "is_ambiguous": self.is_ambiguous,
            "metadata": self.metadata,
        }


@dataclass
class DeadlineEvidenceCollection:
    """
    Container of all deadline evidence items associated with an opportunity or venue.
    """

    opportunity_id: str | None = None
    items: list[DeadlineEvidence] = field(default_factory=list)

    def add(self, evidence: DeadlineEvidence) -> None:
        """Add a deadline evidence item to the collection."""
        self.items.append(evidence)

    def get_by_type(self, deadline_type: DeadlineType) -> list[DeadlineEvidence]:
        """Return all evidence items for a given milestone type."""
        return [item for item in self.items if item.deadline_type == deadline_type]

    def get_primary_submission_deadline(self) -> DeadlineEvidence | None:
        """
        Return the primary SUBMISSION deadline evidence, prioritizing detail pages
        over list pages.
        """
        submissions = self.get_by_type(DeadlineType.SUBMISSION)
        if not submissions:
            return None
        # Sort by confidence descending, detail page over list page
        def _sort_key(ev: DeadlineEvidence) -> tuple[float, int]:
            prov_weight = 2 if ev.provenance == DeadlineProvenance.WIKICFP_DETAIL_PAGE else 1
            return (ev.confidence, prov_weight)

        return max(submissions, key=_sort_key)

    def has_type(self, deadline_type: DeadlineType) -> bool:
        """Return True if evidence for the milestone type is present."""
        return any(item.deadline_type == deadline_type and item.is_present for item in self.items)

    def get_present_deadlines(self) -> list[DeadlineEvidence]:
        """Return all evidence items that are affirmatively present (non-empty/non-TBA)."""
        return [item for item in self.items if item.is_present]

    def to_dict(self) -> list[dict[str, Any]]:
        """Return serialized list of all evidence items."""
        return [item.to_dict() for item in self.items]


# ── Phase 2.7C Normalization Models ───────────────────────────────────────────


class NormalizationStatus(str, Enum):
    """Status of the date/timezone normalization process."""

    NORMALIZED = "NORMALIZED"                  # Successfully resolved to a deterministic UTC instant
    DATE_ONLY = "DATE_ONLY"                    # Calendar date preserved; no exact instant without policy
    EXPLICIT_TIMEZONE = "EXPLICIT_TIMEZONE"    # Explicit timezone/AoE/offset present in source and normalized
    INFERRED_TIMEZONE = "INFERRED_TIMEZONE"    # Timezone inferred from academic convention or venue location
    AMBIGUOUS = "AMBIGUOUS"                    # Ambiguous date representation (e.g. 04/05/2026); cannot resolve
    INVALID = "INVALID"                        # Malformed date components or unsupported timezone
    MISSING = "MISSING"                        # No deadline provided (e.g. None, TBA, TBD, N/A, Rolling)


class TimezoneSource(str, Enum):
    """Provenance origin of the timezone information."""

    EXPLICIT = "EXPLICIT"                      # Explicitly stated in source text/field
    INFERRED = "INFERRED"                      # Inferred from academic convention (e.g. default AoE policy)
    UNKNOWN = "UNKNOWN"                        # Completely unknown/unspecified


class DefaultTimezonePolicy(str, Enum):
    """Configurable policy for handling unspecified timezones on academic milestones."""

    INFERRED_AOE = "INFERRED_AOE"              # Default academic conference submission convention (23:59:59 AoE)
    UTC = "UTC"                                # Assume UTC
    STRICT_UNKNOWN = "STRICT_UNKNOWN"          # Do not synthesize UTC instant; preserve DATE_ONLY with None instant


@dataclass(frozen=True)
class NormalizedDeadline:
    """
    Standardized, deterministic temporal representation of an academic deadline.

    Transforms raw DeadlineEvidence into a concrete local date/time and UTC instant
    while retaining complete provenance and confidence metrics.
    """

    deadline_type: DeadlineType
    local_date: date | None = None
    local_time: time | None = None
    timezone_name: str | None = None
    timezone_offset: str | None = None
    normalized_utc: datetime | None = None
    precision: DeadlinePrecision = DeadlinePrecision.DATE_ONLY
    timezone_source: TimezoneSource = TimezoneSource.UNKNOWN
    normalization_confidence: float = 1.0
    normalization_status: NormalizationStatus = NormalizationStatus.NORMALIZED
    source_evidence: DeadlineEvidence | None = None
    is_end_of_day_inferred: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, reference_time: datetime | None = None) -> bool:
        """
        Evaluate whether this deadline has passed relative to reference_time.
        """
        ref = reference_time or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)

        if self.normalized_utc is not None:
            return self.normalized_utc < ref

        if self.local_date is not None:
            return self.local_date < ref.date()

        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert normalized deadline to serializable dictionary."""
        return {
            "deadline_type": self.deadline_type.value,
            "local_date": self.local_date.isoformat() if self.local_date else None,
            "local_time": self.local_time.isoformat() if self.local_time else None,
            "timezone_name": self.timezone_name,
            "timezone_offset": self.timezone_offset,
            "normalized_utc": self.normalized_utc.isoformat() if self.normalized_utc else None,
            "precision": self.precision.value,
            "timezone_source": self.timezone_source.value,
            "normalization_confidence": round(self.normalization_confidence, 4),
            "normalization_status": self.normalization_status.value,
            "is_end_of_day_inferred": self.is_end_of_day_inferred,
            "source_evidence": self.source_evidence.to_dict() if self.source_evidence else None,
            "metadata": self.metadata,
        }


@dataclass
class NormalizedDeadlineCollection:
    """
    Container of all normalized deadline milestones for an opportunity.
    """

    opportunity_id: str | None = None
    items: list[NormalizedDeadline] = field(default_factory=list)

    def add(self, item: NormalizedDeadline) -> None:
        """Add a normalized deadline to the collection."""
        self.items.append(item)

    def get_by_type(self, deadline_type: DeadlineType) -> list[NormalizedDeadline]:
        """Return all milestones matching the given type."""
        return [item for item in self.items if item.deadline_type == deadline_type]

    def get_primary_submission(self) -> NormalizedDeadline | None:
        """
        Return the primary SUBMISSION deadline, prioritizing highest confidence.
        """
        submissions = self.get_by_type(DeadlineType.SUBMISSION)
        if not submissions:
            return None
        # Prefer higher normalization confidence
        return max(submissions, key=lambda d: d.normalization_confidence)

    def to_dict(self) -> list[dict[str, Any]]:
        """Return serialized list of all normalized deadlines."""
        return [item.to_dict() for item in self.items]

