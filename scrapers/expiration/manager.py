"""
Opportunity expiration management.

Provides deterministic, timezone-aware expiration checks and state transitions
for academic opportunities whose submission deadlines or event dates have elapsed.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def is_opportunity_expired(
    opportunity: Any,
    now: datetime | None = None,
) -> bool:
    """
    Determine whether an opportunity has passed its submission deadline or event date.

    Args:
        opportunity: OpportunityModel or NormalizedOpportunity instance or dict.
        now: Optional reference UTC datetime (defaults to current UTC time).

    Returns:
        bool: True if the deadline or event date is in the past.
    """
    ref_time = now or datetime.now(tz=timezone.utc)
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)

    # Extract submission deadline
    if isinstance(opportunity, dict):
        deadline = opportunity.get("submission_deadline")
        event_end = opportunity.get("event_end_date")
        event_start = opportunity.get("event_start_date")
    else:
        deadline = getattr(opportunity, "submission_deadline", None)
        event_end = getattr(opportunity, "event_end_date", None)
        event_start = getattr(opportunity, "event_start_date", None)

    # Check if deadline is a NormalizedDeadline object
    if hasattr(deadline, "is_expired"):
        return deadline.is_expired(ref_time)

    # Primary check: submission deadline
    if deadline is not None:
        if isinstance(deadline, date) and not isinstance(deadline, datetime):
            return deadline < ref_time.date()
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        # Legacy date-only protection: If deadline was stored at exact UTC midnight
        # and current date is still on the deadline date, do not expire prematurely
        if (
            deadline.hour == 0
            and deadline.minute == 0
            and deadline.second == 0
            and deadline.date() == ref_time.date()
        ):
            return False

        return deadline < ref_time

    # Secondary check: event end or start date if no submission deadline
    event_date = event_end or event_start
    if event_date is not None:
        ref_date = ref_time.date() if isinstance(ref_time, datetime) else ref_time
        return event_date < ref_date

    return False


def apply_expiration_status(
    opportunity: Any,
    now: datetime | None = None,
) -> bool:
    """
    Check if an opportunity is expired and update its status attribute if necessary.

    Returns:
        bool: True if the status was changed to EXPIRED.
    """
    if is_opportunity_expired(opportunity, now):
        current_status = (
            opportunity.get("status")
            if isinstance(opportunity, dict)
            else getattr(opportunity, "status", None)
        )
        if current_status in {"ACTIVE", "UNVERIFIED"}:
            if isinstance(opportunity, dict):
                opportunity["status"] = "EXPIRED"
            else:
                setattr(opportunity, "status", "EXPIRED")
            return True
    return False


def expire_past_opportunities(
    session: Session,
    now: datetime | None = None,
) -> int:
    """
    Batch sweep over database opportunities to transition past active records to EXPIRED.

    Preserves historical records (does not delete).

    Returns:
        int: Number of records updated to EXPIRED.
    """
    from app.models.opportunity import OpportunityModel

    ref_time = now or datetime.now(tz=timezone.utc)
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)

    stmt = select(OpportunityModel).where(
        OpportunityModel.status.in_(["ACTIVE", "UNVERIFIED"]),
        or_(
            OpportunityModel.submission_deadline < ref_time,
            (OpportunityModel.submission_deadline.is_(None) & (OpportunityModel.event_end_date < ref_time.date())),
        ),
    )

    expired_records = session.execute(stmt).scalars().all()
    count = 0
    for record in expired_records:
        record.status = "EXPIRED"
        record.updated_at = ref_time
        count += 1

    if count > 0:
        session.flush()
        logger.info("Marked %d past opportunities as EXPIRED (as of %s)", count, ref_time.isoformat())

    return count
