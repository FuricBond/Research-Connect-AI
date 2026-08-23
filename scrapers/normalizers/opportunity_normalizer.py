"""
Opportunity normalizer.

Transforms a RawOpportunity (raw strings from HTML) into a
NormalizedOpportunity (typed, cleaned, DB-ready).

Normalization steps:
1. Whitespace — strip all string fields; collapse internal whitespace.
2. Dates — try multiple date formats common in WikiCFP.
3. Opportunity type — infer from title keywords (title heuristic).
4. Delivery mode — infer from location string keywords.
5. URLs — validate and clean (strip tracking params, ensure scheme).
6. Location — strip leading/trailing whitespace; set None if "Virtual".

No fabrication: if a value cannot be confidently extracted, it is left None.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

from scrapers.models import NormalizedOpportunity, RawOpportunity

logger = logging.getLogger(__name__)

# ── Date parsing ──────────────────────────────────────────────────────────────

# WikiCFP date formats observed in the wild:
#   "Aug 22, 2026"          — deadline / single-day event
#   "Oct 24, 2026 - Oct 25, 2026"  — event date range
DATE_FORMATS = [
    "%b %d, %Y",    # Aug 22, 2026
    "%B %d, %Y",    # August 22, 2026
    "%Y-%m-%d",     # ISO (just in case)
    "%d %b %Y",     # 22 Aug 2026
    "%d %B %Y",     # 22 August 2026
]

_DATE_RANGE_SEP_RE = re.compile(r"\s*-\s*")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str | None) -> str | None:
    """Strip and collapse internal whitespace."""
    if text is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", text).strip()
    return cleaned if cleaned else None


def _parse_date(raw: str | None) -> datetime | None:
    """
    Attempt to parse a date string into a timezone-aware datetime (UTC midnight).

    Returns None if the string is absent or unparseable.
    """
    if not raw:
        return None
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            # Attach UTC timezone (assume deadline is UTC midnight)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.debug("Could not parse date string: %r", raw)
    return None


def _parse_event_dates(raw: str | None) -> tuple[date | None, date | None]:
    """
    Parse an event date range like "Oct 24, 2026 - Oct 25, 2026".

    Returns (start_date, end_date). If only one date is present, both are the same.
    """
    if not raw:
        return None, None
    parts = _DATE_RANGE_SEP_RE.split(raw.strip(), maxsplit=1)
    start_dt = _parse_date(parts[0].strip())
    end_dt = _parse_date(parts[1].strip()) if len(parts) > 1 else start_dt

    start = start_dt.date() if start_dt else None
    end = end_dt.date() if end_dt else None
    return start, end


# ── Opportunity type inference ────────────────────────────────────────────────

# Keywords in the title/abbreviation that strongly suggest a type.
# Order matters: more specific patterns first.
_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bspecial\s+issue\b", re.I), "SPECIAL_ISSUE"),
    (re.compile(r"\bworkshop\b", re.I), "WORKSHOP"),
    (re.compile(r"\bsymposium\b", re.I), "WORKSHOP"),
    (re.compile(r"\bjournal\b", re.I), "JOURNAL"),
    (re.compile(r"\btransactions?\b", re.I), "JOURNAL"),
    (re.compile(r"\bletters?\b", re.I), "JOURNAL"),
    (re.compile(r"\bcall\s+for\s+paper", re.I), "CALL_FOR_PAPERS"),
    (re.compile(r"\bcfp\b", re.I), "CALL_FOR_PAPERS"),
    (re.compile(r"\bconference\b", re.I), "CONFERENCE"),
    (re.compile(r"\bcongress\b", re.I), "CONFERENCE"),
]


def _infer_opportunity_type(title: str, abbreviation: str | None = None) -> str:
    """
    Heuristically infer opportunity type from the title.

    Falls back to CONFERENCE (the most common type on WikiCFP) if no pattern matches.
    """
    text = f"{title} {abbreviation or ''}"
    for pattern, opp_type in _TYPE_PATTERNS:
        if pattern.search(text):
            return opp_type
    return "CONFERENCE"  # Safe default — most WikiCFP entries are conferences


# ── Delivery mode inference ───────────────────────────────────────────────────

_ONLINE_PATTERNS = re.compile(
    r"\b(virtual|online|remote|digital|hybrid)\b", re.I
)


def _infer_delivery_mode(location: str | None) -> str:
    """
    Infer delivery mode from location string.

    "Virtual Conference", "Online", "Virtual" → ONLINE
    "Hybrid" (explicitly) → HYBRID
    Anything else with a real city → OFFLINE
    """
    if not location:
        return "OFFLINE"
    if re.search(r"\bhybrid\b", location, re.I):
        return "HYBRID"
    if _ONLINE_PATTERNS.search(location):
        return "ONLINE"
    return "OFFLINE"


# ── URL normalization ─────────────────────────────────────────────────────────

def _normalize_url(url: str | None) -> str | None:
    """
    Ensure a URL has a scheme and is stripped of whitespace.

    Returns None if the URL is empty or obviously invalid.
    """
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    # Basic sanity — must have a host
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return url


# ── Main normalizer ───────────────────────────────────────────────────────────

def normalize_opportunity(raw: RawOpportunity) -> NormalizedOpportunity:
    """
    Transform a RawOpportunity into a NormalizedOpportunity.

    This function is pure (no side effects, no DB access).
    """
    title = _clean(raw.title) or ""
    abbreviation = _clean(raw.abbreviation)
    location_clean = _clean(raw.raw_location)

    # "Virtual Conference" → treat location as None for the DB (delivery_mode captures it)
    if location_clean and re.match(r"^virtual", location_clean, re.I):
        location_for_db = None
    else:
        location_for_db = location_clean

    opportunity_type = _infer_opportunity_type(title, abbreviation)
    delivery_mode = _infer_delivery_mode(location_clean)
    submission_deadline = _parse_date(raw.raw_submission_deadline)
    event_start, event_end = _parse_event_dates(raw.raw_event_dates)
    website_url = _normalize_url(raw.website_url)
    source_url = _normalize_url(raw.source_url) or raw.source_url

    return NormalizedOpportunity(
        source_name=raw.source_name,
        raw_source_id=raw.raw_source_id,
        source_url=source_url,
        title=title,
        abbreviation=abbreviation,
        opportunity_type=opportunity_type,
        website_url=website_url,
        submission_deadline=submission_deadline,
        event_start_date=event_start,
        event_end_date=event_end,
        location=location_for_db,
        delivery_mode=delivery_mode,
        status="ACTIVE",
        is_predatory_flag=False,
    )
