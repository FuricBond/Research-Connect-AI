"""
Internal data models for the scraping pipeline.

RawOpportunity  — data as extracted directly from the source HTML, with
                  minimal transformation (only whitespace stripping).
NormalizedOpportunity — validated, type-coerced, URL-canonicalized record
                        ready for duplicate detection and database insertion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class RawOpportunity:
    """
    Data extracted directly from a single source entry.

    All string fields are left as-is from the HTML (after basic whitespace
    stripping).  All fields are optional except `title` and `source_name`.
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
    and persistence service.  It maps 1:1 to OpportunityModel columns.
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

    # Status (always ACTIVE for freshly scraped records)
    status: str = "ACTIVE"

    # Optional enrichment fields
    organizer: str | None = None
    publisher: str | None = None
    summary: str | None = None
    description: str | None = None

    # Risk / quality (not populated by scraper — Phase 2)
    is_predatory_flag: bool = False

    # Validation metadata (not stored in DB — used for pipeline logging)
    validation_errors: list[str] = field(default_factory=list)
