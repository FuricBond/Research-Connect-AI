"""
Opportunity validator.

Validates a NormalizedOpportunity before it reaches the database.
Invalid records are REJECTED — they are logged but not inserted.

Validation rules:
1. title — required, must be non-empty string
2. source_name — required, must be non-empty string
3. raw_source_id — required, must be non-empty string
4. opportunity_type — must be in the allowed set
5. delivery_mode — must be in the allowed set
6. website_url — if present, must be a valid HTTP/HTTPS URL
7. submission_deadline — if present, must be between 2000 and now+5 years
8. event dates — if present, start must not be after end
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from scrapers.models import NormalizedOpportunity

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_OPPORTUNITY_TYPES = {
    "CONFERENCE",
    "JOURNAL",
    "WORKSHOP",
    "CALL_FOR_PAPERS",
    "SPECIAL_ISSUE",
}

ALLOWED_DELIVERY_MODES = {"ONLINE", "OFFLINE", "HYBRID"}

_DATE_MIN = datetime(2000, 1, 1, tzinfo=timezone.utc)
_DATE_MAX_OFFSET = timedelta(days=365 * 6)  # 6 years in the future


def _is_valid_url(url: str) -> bool:
    """Return True if the URL has a valid HTTP/HTTPS scheme and a hostname."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:  # noqa: BLE001
        return False


def validate_opportunity(
    opp: NormalizedOpportunity,
) -> tuple[bool, list[str]]:
    """
    Validate a NormalizedOpportunity.

    Returns:
        (is_valid, errors) — True + empty list if valid;
        False + list of human-readable error messages if invalid.
    """
    errors: list[str] = []
    now = datetime.now(tz=timezone.utc)
    date_max = now + _DATE_MAX_OFFSET

    # 1. Required: title
    if not opp.title or not opp.title.strip():
        errors.append("title is required and must not be empty")

    # 2. Required: source_name
    if not opp.source_name or not opp.source_name.strip():
        errors.append("source_name is required and must not be empty")

    # 3. Required: raw_source_id
    if not opp.raw_source_id or not opp.raw_source_id.strip():
        errors.append("raw_source_id is required and must not be empty")

    # 4. opportunity_type
    if opp.opportunity_type not in ALLOWED_OPPORTUNITY_TYPES:
        errors.append(
            f"opportunity_type {opp.opportunity_type!r} is not in "
            f"{sorted(ALLOWED_OPPORTUNITY_TYPES)}"
        )

    # 5. delivery_mode
    if opp.delivery_mode not in ALLOWED_DELIVERY_MODES:
        errors.append(
            f"delivery_mode {opp.delivery_mode!r} is not in "
            f"{sorted(ALLOWED_DELIVERY_MODES)}"
        )

    # 6. website_url — optional but must be valid if present
    if opp.website_url is not None:
        if not _is_valid_url(opp.website_url):
            errors.append(f"website_url {opp.website_url!r} is not a valid HTTP/HTTPS URL")

    # 7. submission_deadline — optional but must be within sane range
    if opp.submission_deadline is not None:
        if opp.submission_deadline < _DATE_MIN:
            errors.append(
                f"submission_deadline {opp.submission_deadline.date()} is before 2000-01-01"
            )
        if opp.submission_deadline > date_max:
            errors.append(
                f"submission_deadline {opp.submission_deadline.date()} is more than 6 years in the future"
            )

    # 8. Event dates — start must not be after end
    if opp.event_start_date and opp.event_end_date:
        if opp.event_start_date > opp.event_end_date:
            errors.append(
                f"event_start_date {opp.event_start_date} is after event_end_date {opp.event_end_date}"
            )

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(
            "Validation failed for %r (id=%r): %s",
            opp.title,
            opp.raw_source_id,
            "; ".join(errors),
        )

    return is_valid, errors
