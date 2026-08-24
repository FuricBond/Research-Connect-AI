"""
Freshness tracking and staleness assessment for scraped opportunities.

Answers:
- When was this opportunity first discovered? (`created_at`)
- When was it last seen during a crawl? (`last_seen_at`)
- When was it last verified? (`last_verified_at`)
- Is the data stale? (`is_opportunity_stale`)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_STALE_DAYS = 30


def is_opportunity_stale(
    last_seen_at: datetime | None,
    stale_threshold_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
) -> bool:
    """
    Check if an opportunity is considered stale based on how long ago it was last seen.

    Args:
        last_seen_at: Timestamp when the opportunity was last detected in a scrape feed.
        stale_threshold_days: Max days before data is considered stale (default: 30).
        now: Optional reference UTC datetime.

    Returns:
        bool: True if last_seen_at is None or older than threshold.
    """
    if last_seen_at is None:
        return True

    ref_time = now or datetime.now(tz=timezone.utc)
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)

    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)

    cutoff = ref_time - timedelta(days=stale_threshold_days)
    return last_seen_at < cutoff


def get_freshness_summary(
    opportunity: Any,
    stale_threshold_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
) -> dict:
    """
    Extract a structured freshness summary for an opportunity record.
    """
    ref_time = now or datetime.now(tz=timezone.utc)

    if isinstance(opportunity, dict):
        created_at = opportunity.get("created_at")
        last_seen_at = opportunity.get("last_seen_at")
        last_verified_at = opportunity.get("last_verified_at")
    else:
        created_at = getattr(opportunity, "created_at", None)
        last_seen_at = getattr(opportunity, "last_seen_at", None)
        last_verified_at = getattr(opportunity, "last_verified_at", None)

    return {
        "first_discovered_at": created_at,
        "last_seen_at": last_seen_at,
        "last_verified_at": last_verified_at,
        "is_stale": is_opportunity_stale(last_seen_at, stale_threshold_days, ref_time),
    }
