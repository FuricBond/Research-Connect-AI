"""
Internal data models for the scraping pipeline.

RawOpportunity  — data as extracted directly from the source HTML, with
                  minimal transformation (only whitespace stripping).
NormalizedOpportunity — validated, type-coerced, URL-canonicalized record
                        ready for duplicate detection and database insertion.
LifecycleAction — record-level action taken during ingestion.
DuplicateClassification — distinction between confirmed duplicate, potential duplicate, and unique.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class LifecycleAction(str, Enum):
    """Lifecycle change action for an opportunity record during ingestion."""
    NEW = "NEW"                          # Inserted for the first time
    UPDATED = "UPDATED"                  # Existing record modified with new/changed metadata
    UNCHANGED = "UNCHANGED"              # Existing record identical; last_seen_at refreshed
    DUPLICATE = "DUPLICATE"              # Exact duplicate detected (same source+id or URL)
    POTENTIAL_DUPLICATE = "POTENTIAL_DUPLICATE"  # Cross-source soft collision (title+deadline)
    INVALID = "INVALID"                  # Rejected by validator
    EXPIRED = "EXPIRED"                  # Past deadline / event end date


class DuplicateClassification(str, Enum):
    """Classification of duplicate detection check."""
    CONFIRMED_DUPLICATE = "CONFIRMED_DUPLICATE"  # Tier 1 or Tier 2 exact match
    POTENTIAL_DUPLICATE = "POTENTIAL_DUPLICATE"  # Tier 3 soft match (title + deadline)
    UNIQUE = "UNIQUE"                            # No collisions detected


@dataclass
class FieldChange:
    """Represents a detected modification to an opportunity field."""
    field_name: str
    old_value: Any
    new_value: Any


@dataclass
class ChangeDetectionResult:
    """Outcome of change detection comparison between DB model and incoming normalized data."""
    has_changed: bool
    changes: list[FieldChange] = field(default_factory=list)


@dataclass
class RawOpportunity:
    """
    Data extracted directly from a single source entry.

    All string fields are left as-is from the HTML (after basic whitespace
    stripping). All fields are optional except `title` and `source_name`.
    """

    # Provenance
    source_name: str                   # e.g. "WikiCFP"
    raw_source_id: str                 # source-internal identifier (e.g. "195331")
    source_url: str                    # URL of the *list/detail page* we scraped

    # Core
    title: str                         # Full name of the event/journal
    abbreviation: str | None = None    # Short acronym, e.g. "ICML 2026"
    website_url: str | None = None     # External event homepage

    # Dates (raw strings from source, e.g. "Aug 22, 2026")
    raw_submission_deadline: str | None = None
    raw_event_dates: str | None = None  # e.g. "Oct 24, 2026 - Oct 25, 2026"

    # Location
    raw_location: str | None = None    # e.g. "Vienna, Austria" / "Virtual Conference" / "N/A"

    # Type hint from source (may be absent — we infer from title/context)
    raw_opportunity_type: str | None = None


@dataclass
class NormalizedOpportunity:
    """
    Cleaned, validated, type-coerced opportunity record.

    This is the output of the normalizer and input to the duplicate detector
    and persistence service. It maps 1:1 to OpportunityModel columns.
    """

    # Provenance
    source_name: str
    raw_source_id: str
    source_url: str

    # Core
    title: str
    abbreviation: str | None
    opportunity_type: str             # One of CONFERENCE JOURNAL WORKSHOP CALL_FOR_PAPERS SPECIAL_ISSUE
    website_url: str | None

    # Normalized dates
    submission_deadline: datetime | None
    event_start_date: date | None
    event_end_date: date | None

    # Location + delivery
    location: str | None
    delivery_mode: str               # ONLINE | OFFLINE | HYBRID

    # Status (business lifecycle: ACTIVE, EXPIRED, ARCHIVED, DRAFT, UNVERIFIED)
    status: str = "ACTIVE"

    # Optional enrichment fields
    organizer: str | None = None
    publisher: str | None = None
    summary: str | None = None
    description: str | None = None
    indexing: list[str] | None = None
    apc_or_fee: dict | None = None

    # Freshness / timestamps
    last_seen_at: datetime | None = None
    last_verified_at: datetime | None = None

    # Risk / quality (not populated by scraper — Phase 2)
    is_predatory_flag: bool = False

    # Ingestion metadata (used for pipeline tracking)
    lifecycle_action: LifecycleAction | None = None
    validation_errors: list[str] = field(default_factory=list)
