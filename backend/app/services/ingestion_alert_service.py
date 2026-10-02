"""
Research refresh (step 4/6) — an in-app alert when the refresh keeps failing.

After ``threshold`` research refresh runs in a row have failed (every pass of each run
FAILED), every active administrator gets one SYSTEM notification. It is keyed on the run
that completed the streak, so calling again for the same run never repeats it.

The body names how many runs failed and the last error category only: never a URL, a
request, an API key or exception text.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationModel,
    NotificationType,
)
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.services.ingestion_run_service import error_category, newest_run_tags, run_status, runs_for_tag

logger = logging.getLogger(__name__)

ALERT_TITLE = "Research refresh failing"
# How far back a failure streak is counted for the message.
_STREAK_LOOKBACK = 50


def _failed(rows) -> bool:
    """A run failed when every pass failed; a run that was asked to stop did not."""
    if run_status(rows) != "FAILED":
        return False
    return any(error_category(row.error_message) != "stop requested" for row in rows)


def _last_error_type(rows) -> str:
    newest = sorted(rows, key=lambda row: row.started_at, reverse=True)
    for row in newest:
        category = error_category(row.error_message)
        if category is not None:
            return category
    return "error"


def _profile_for(db: Session, user: UserModel) -> ResearchProfileModel:
    """The admin's research profile, created minimal when missing (as notifications do)."""
    profile = db.execute(
        select(ResearchProfileModel).where(ResearchProfileModel.user_id == user.id)
    ).scalars().first()
    if profile is None:
        profile = ResearchProfileModel(user_id=user.id, academic_status="RESEARCHER")
        db.add(profile)
        db.flush()
    return profile


def notify_admins_after_repeated_failures(
    db: Session,
    *,
    run_tag: str,
    threshold: int = 2,
    now: datetime | None = None,
) -> int:
    """
    Notify every active admin once ``run_tag`` completes a streak of ``threshold`` failed
    research refresh runs. Returns how many notifications were created: 0 when the streak
    is not there, ``run_tag`` is not the newest run, or the alert was already sent.
    """
    now = now or datetime.now(timezone.utc)
    tags = newest_run_tags(db, max(threshold, _STREAK_LOOKBACK))
    if len(tags) < threshold or tags[0] != run_tag:
        return 0

    streak = 0
    newest_rows = None
    for tag in tags:
        rows = runs_for_tag(db, tag)
        if not _failed(rows):
            break
        newest_rows = newest_rows if newest_rows is not None else rows
        streak += 1
    if streak < threshold:
        return 0

    error_type = _last_error_type(newest_rows)
    body = (
        f"The last {streak} research refresh runs failed. Last error: {error_type}. "
        "Newly published research is not being added until a run succeeds."
    )

    admins = db.execute(
        select(UserModel).where(UserModel.role == "ADMIN", UserModel.is_active.is_(True))
    ).scalars().all()
    created = 0
    for admin in admins:
        profile = _profile_for(db, admin)
        key = hashlib.sha256(f"ingestion-alert:{run_tag}:{profile.id}".encode("utf-8")).hexdigest()
        exists = db.execute(
            select(NotificationModel.id).where(NotificationModel.deduplication_key == key)
        ).first()
        if exists is not None:
            continue
        db.add(
            NotificationModel(
                profile_id=profile.id,
                notification_type=NotificationType.SYSTEM.value,
                title=ALERT_TITLE,
                body=body,
                source_type="SYSTEM",
                source_id=None,
                scheduled_for=now,
                delivered_at=now,
                delivery_status=DeliveryStatus.DELIVERED.value,
                delivery_channel=DeliveryChannel.IN_APP.value,
                deduplication_key=key,
                metadata_json={"run_tag": run_tag, "failed_runs": streak, "error_type": error_type},
            )
        )
        created += 1
    db.commit()
    if created:
        logger.warning(
            "Research refresh failed %d run(s) in a row; alerted %d administrator(s)", streak, created
        )
    return created
