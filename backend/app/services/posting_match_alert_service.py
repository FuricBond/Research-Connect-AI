"""
Phase 5.15 — "Notify me when a new posting matches my interests".

When a research posting is first published, every student who opted in (and keeps in-app
notifications on) is scored against it, and those at or above their own threshold get one
in-app POSTING_MATCH notification.

  - One alert per student and posting, ever: the deduplication key carries no timestamp, so a
    reopened or re-published posting never alerts the same student twice.
  - Never the posting's author, and never anyone who has not opted in.
  - Signals for every candidate load in a fixed number of queries.
  - The notification names the posting and the fit only: no contact email or other personal data.
  - Flush only: the caller's transaction commits it together with the publish.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
)
from app.models.research_posting import ResearchPostingModel
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.services.posting_fit_service import PostingFitService

logger = logging.getLogger(__name__)

ALERT_TITLE = "New posting matches your interests"
SOURCE_TYPE = "RESEARCH_POSTING"


def dedup_key(posting_id, profile_id) -> str:
    return hashlib.sha256(f"posting-match:{posting_id}:{profile_id}".encode("utf-8")).hexdigest()


def notify_matching_students(db: Session, posting: ResearchPostingModel, now: datetime) -> int:
    """Creates the POSTING_MATCH alerts for a newly published posting; returns how many."""
    candidates = db.execute(
        select(ResearchProfileModel, NotificationPreferenceModel)
        .join(UserModel, UserModel.id == ResearchProfileModel.user_id)
        .join(
            NotificationPreferenceModel,
            NotificationPreferenceModel.profile_id == ResearchProfileModel.id,
        )
        .where(
            UserModel.role == "STUDENT",
            UserModel.is_active.is_(True),
            UserModel.id != posting.author_user_id,
            ResearchProfileModel.id != posting.author_profile_id,
            NotificationPreferenceModel.posting_match_alerts_enabled.is_(True),
            NotificationPreferenceModel.in_app_enabled.is_(True),
        )
        .order_by(ResearchProfileModel.id)
    ).all()
    if not candidates:
        return 0

    profiles = [profile for profile, _ in candidates]
    signals = PostingFitService.load_signals(db, profiles)
    keys = {profile.id: dedup_key(posting.id, profile.id) for profile in profiles}
    already_sent = set(
        db.execute(
            select(NotificationModel.deduplication_key).where(
                NotificationModel.deduplication_key.in_(list(keys.values()))
            )
        ).scalars()
    )

    created = 0
    for profile, preference in candidates:
        key = keys[profile.id]
        if key in already_sent:
            continue
        fit = PostingFitService.score(posting, signals.get(profile.id), now=now)
        if fit.score is None or fit.score < preference.posting_match_min_score:
            continue
        db.add(
            NotificationModel(
                profile_id=profile.id,
                notification_type=NotificationType.POSTING_MATCH.value,
                title=ALERT_TITLE,
                body=f"“{posting.title}” — {fit.score}% fit",
                source_type=SOURCE_TYPE,
                source_id=posting.id,
                scheduled_for=now,
                delivered_at=now,
                delivery_status=DeliveryStatus.DELIVERED.value,
                delivery_channel=DeliveryChannel.IN_APP.value,
                deduplication_key=key,
                metadata_json={
                    "posting_id": str(posting.id),
                    "fit_score": fit.score,
                    "band": fit.band,
                    "reasons": [reason.model_dump() for reason in fit.reasons[:3]],
                },
            )
        )
        created += 1

    if created:
        db.flush()
        logger.info(
            "Posting match alerts created",
            extra={"posting_id": str(posting.id), "alerts": created},
        )
    return created
