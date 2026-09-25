"""
Phase 5.11 — Research Posting Application Service.

An application is jointly owned: the applicant owns the submission and may withdraw it, while
the posting's author owns the review decision. This service is where that split is enforced.

Guarantees:
  - Role-partitioned transitions. Each lifecycle move belongs to exactly one side, so an
    applicant cannot mark themselves shortlisted and an author cannot accept an offer on the
    applicant's behalf.
  - Eligibility at submission time. Applications are accepted only for an OPEN structured
    opening that handles applications on-platform and whose deadline has not passed.
  - One application per researcher per posting, with re-application after withdrawal reusing
    the same record so the author sees one continuous history per person.
  - Append-only status history readable by both sides, so a recorded decision cannot be
    silently revised.
  - Author privacy: `reviewer_note` is never returned to the applicant.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from typing import Literal
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
)
from app.models.research_posting import PostingStatus, PostingType, ResearchPostingModel
from app.models.research_posting_application import (
    ApplicationStatus,
    ResearchPostingApplicationModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.schemas.research_posting_application import (
    ApplicantSummarySchema,
    ApplicationCreate,
    ApplicationListResponse,
    ApplicationRead,
    ApplicationStatusEventSchema,
    ApplicationSummaryResponse,
)

logger = logging.getLogger(__name__)

ActorRole = Literal["APPLICANT", "AUTHOR"]

# Transitions the applicant may perform.
APPLICANT_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.SUBMITTED: frozenset({ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.UNDER_REVIEW: frozenset({ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.SHORTLISTED: frozenset({ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.OFFERED: frozenset(
        {ApplicationStatus.ACCEPTED, ApplicationStatus.DECLINED, ApplicationStatus.WITHDRAWN}
    ),
}

# Transitions the posting's author may perform.
AUTHOR_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.SUBMITTED: frozenset(
        {ApplicationStatus.UNDER_REVIEW, ApplicationStatus.SHORTLISTED, ApplicationStatus.REJECTED}
    ),
    ApplicationStatus.UNDER_REVIEW: frozenset(
        {ApplicationStatus.SHORTLISTED, ApplicationStatus.OFFERED, ApplicationStatus.REJECTED}
    ),
    ApplicationStatus.SHORTLISTED: frozenset(
        {ApplicationStatus.OFFERED, ApplicationStatus.REJECTED}
    ),
    # An offer already extended may be withdrawn by rejecting it, which is recorded in history.
    ApplicationStatus.OFFERED: frozenset({ApplicationStatus.REJECTED}),
}

# States in which the process has ended.
TERMINAL_STATUSES = frozenset(
    {
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.DECLINED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    }
)

# Still in play, for the "active" count researchers actually care about.
INACTIVE_STATUSES = frozenset(
    {ApplicationStatus.WITHDRAWN, ApplicationStatus.REJECTED, ApplicationStatus.DECLINED}
)


class ApplicationNotFoundError(Exception):
    pass


class ApplicationPermissionError(Exception):
    pass


class ApplicationNotAcceptedError(Exception):
    """The posting is not accepting applications through the platform."""


class DuplicateApplicationError(Exception):
    pass


class InvalidApplicationTransitionError(Exception):
    pass


class ResearchPostingApplicationService:
    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    # ── Eligibility ──────────────────────────────────────────────────────────

    @staticmethod
    def assert_posting_accepts_applications(
        posting: ResearchPostingModel,
        reference_time: datetime | None = None,
    ) -> None:
        """
        Checks that a posting can receive an application right now.

        Each condition is reported distinctly, because "closed" and "handled off-platform" call
        for different actions from the applicant.
        """
        now = reference_time or datetime.now(timezone.utc)

        if posting.status != PostingStatus.OPEN.value:
            raise ApplicationNotAcceptedError(
                "This posting is not open, so it cannot receive applications."
            )
        if PostingType(posting.posting_type) not in PostingType.structured_openings():
            raise ApplicationNotAcceptedError(
                "This posting is a supervisor-led opportunity rather than a funded opening. "
                "Contact the author directly using the details on the posting."
            )
        if not posting.accepts_applications:
            raise ApplicationNotAcceptedError(
                "The author handles applications for this opening off-platform. Use the contact "
                "details or external link on the posting."
            )
        deadline = posting.application_deadline
        if deadline is not None:
            aware = deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=timezone.utc)
            if aware <= now:
                raise ApplicationNotAcceptedError("The application deadline for this opening has passed.")

    # ── Submission ───────────────────────────────────────────────────────────

    @classmethod
    def submit_application(
        cls,
        db: Session,
        posting_id: uuid.UUID,
        applicant_profile: ResearchProfileModel,
        applicant_user: UserModel,
        payload: ApplicationCreate,
        reference_time: datetime | None = None,
    ) -> ResearchPostingApplicationModel:
        now = reference_time or datetime.now(timezone.utc)

        posting = db.get(ResearchPostingModel, posting_id)
        if posting is None:
            raise ApplicationNotFoundError(f"Research posting '{posting_id}' not found.")

        # An author applying to their own opening is a mistake worth catching explicitly.
        if posting.author_user_id == applicant_user.id:
            raise ApplicationPermissionError("You cannot apply to a posting you authored.")

        cls.assert_posting_accepts_applications(posting, reference_time=now)

        existing = db.execute(
            select(ResearchPostingApplicationModel).where(
                ResearchPostingApplicationModel.posting_id == posting_id,
                ResearchPostingApplicationModel.applicant_profile_id == applicant_profile.id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.status != ApplicationStatus.WITHDRAWN.value:
                raise DuplicateApplicationError(
                    "You have already applied to this opening. Withdraw your existing "
                    "application before applying again."
                )
            # Re-applying after withdrawal reuses the record so the author sees one continuous
            # history for this person rather than two competing submissions.
            application = existing
            previous = ApplicationStatus(existing.status)
            application.status = ApplicationStatus.SUBMITTED.value
            application.cover_note = payload.cover_note
            application.contact_email = payload.contact_email
            application.portfolio_url = payload.portfolio_url
            application.decision_reason = None
            application.withdrawn_at = None
            application.decided_at = None
            application.submitted_at = now
            cls._append_history(application, previous, ApplicationStatus.SUBMITTED, "APPLICANT", None, now)
        else:
            application = ResearchPostingApplicationModel(
                id=uuid.uuid4(),
                posting_id=posting_id,
                applicant_profile_id=applicant_profile.id,
                applicant_user_id=applicant_user.id,
                status=ApplicationStatus.SUBMITTED.value,
                cover_note=payload.cover_note,
                contact_email=payload.contact_email,
                portfolio_url=payload.portfolio_url,
                status_history=[],
                submitted_at=now,
            )
            db.add(application)
            cls._append_history(application, None, ApplicationStatus.SUBMITTED, "APPLICANT", None, now)
            posting.application_count = (posting.application_count or 0) + 1

        db.flush()
        cls._notify(
            db,
            recipient_user_id=posting.author_user_id,
            notification_type=NotificationType.SYSTEM,
            title="New application received",
            body=(
                f"A researcher applied to your posting “{posting.title}”. "
                "Review it from your postings dashboard."
            ),
            source_id=posting.id,
            metadata={"posting_id": str(posting.id), "application_id": str(application.id)},
            reference_time=now,
        )
        db.commit()
        db.refresh(application)
        logger.info(
            "Posting application submitted",
            extra={"application_id": str(application.id), "posting_id": str(posting_id)},
        )
        return application

    # ── Decisions ────────────────────────────────────────────────────────────

    @classmethod
    def get_application(
        cls,
        db: Session,
        application_id: uuid.UUID,
        user: UserModel,
    ) -> tuple[ResearchPostingApplicationModel, ActorRole]:
        """
        Loads an application and the requesting researcher's role in it.

        Anyone who is neither the applicant nor the posting's author is told the application
        does not exist, rather than that they may not see it.
        """
        application = db.execute(
            select(ResearchPostingApplicationModel)
            .options(
                joinedload(ResearchPostingApplicationModel.posting),
                joinedload(ResearchPostingApplicationModel.applicant_profile).joinedload(
                    ResearchProfileModel.user
                ),
            )
            .where(ResearchPostingApplicationModel.id == application_id)
        ).unique().scalar_one_or_none()
        if application is None:
            raise ApplicationNotFoundError(f"Application '{application_id}' not found.")

        if application.applicant_user_id == user.id:
            return application, "APPLICANT"
        if application.posting.author_user_id == user.id or user.role == "ADMIN":
            return application, "AUTHOR"
        raise ApplicationNotFoundError(f"Application '{application_id}' not found.")

    @staticmethod
    def allowed_transitions_for(
        status: ApplicationStatus | str,
        actor_role: ActorRole,
    ) -> list[ApplicationStatus]:
        current = ApplicationStatus(status) if not isinstance(status, ApplicationStatus) else status
        table = APPLICANT_TRANSITIONS if actor_role == "APPLICANT" else AUTHOR_TRANSITIONS
        return sorted(table.get(current, frozenset()), key=lambda s: s.value)

    @classmethod
    def transition_application(
        cls,
        db: Session,
        application_id: uuid.UUID,
        user: UserModel,
        target_status: ApplicationStatus,
        *,
        decision_reason: str | None = None,
        reviewer_note: str | None = None,
        reference_time: datetime | None = None,
    ) -> ResearchPostingApplicationModel:
        now = reference_time or datetime.now(timezone.utc)
        application, actor_role = cls.get_application(db, application_id, user)
        current = ApplicationStatus(application.status)

        if current in TERMINAL_STATUSES:
            raise InvalidApplicationTransitionError(
                f"This application is already {current.value} and can no longer change."
            )

        allowed = cls.allowed_transitions_for(current, actor_role)
        if target_status not in allowed:
            other_side = "the posting's author" if actor_role == "APPLICANT" else "the applicant"
            allowed_text = ", ".join(s.value for s in allowed) or "none"
            raise InvalidApplicationTransitionError(
                f"As {actor_role.lower()} you cannot move an application from {current.value} to "
                f"{target_status.value}; that decision belongs to {other_side}. "
                f"Available to you: {allowed_text}."
            )

        application.status = target_status.value
        if decision_reason is not None:
            application.decision_reason = decision_reason
        # A private note is the author's alone; an applicant supplying one is ignored rather
        # than silently written into the record the author relies on.
        if reviewer_note is not None and actor_role == "AUTHOR":
            application.reviewer_note = reviewer_note

        if actor_role == "AUTHOR":
            application.decided_at = now
        if target_status == ApplicationStatus.WITHDRAWN:
            application.withdrawn_at = now

        cls._append_history(application, current, target_status, actor_role, decision_reason, now)
        db.flush()

        # Notify the other side. Each side only learns what concerns them.
        if actor_role == "AUTHOR":
            cls._notify(
                db,
                recipient_user_id=application.applicant_user_id,
                notification_type=NotificationType.SYSTEM,
                title=f"Application {target_status.value.replace('_', ' ').lower()}",
                body=(
                    f"Your application to “{application.posting.title}” is now "
                    f"{target_status.value.replace('_', ' ').lower()}."
                    + (f" {decision_reason}" if decision_reason else "")
                ),
                source_id=application.posting_id,
                metadata={
                    "posting_id": str(application.posting_id),
                    "application_id": str(application.id),
                    "status": target_status.value,
                },
                reference_time=now,
            )
        else:
            cls._notify(
                db,
                recipient_user_id=application.posting.author_user_id,
                notification_type=NotificationType.SYSTEM,
                title=f"Applicant {target_status.value.lower()} an application",
                body=(
                    f"An applicant to “{application.posting.title}” is now "
                    f"{target_status.value.replace('_', ' ').lower()}."
                ),
                source_id=application.posting_id,
                metadata={
                    "posting_id": str(application.posting_id),
                    "application_id": str(application.id),
                    "status": target_status.value,
                },
                reference_time=now,
            )

        db.commit()
        db.refresh(application)
        logger.info(
            "Posting application transitioned",
            extra={
                "application_id": str(application.id),
                "from_status": current.value,
                "to_status": target_status.value,
                "actor_role": actor_role,
            },
        )
        return application

    # ── Listings ─────────────────────────────────────────────────────────────

    @classmethod
    def list_applications_for_posting(
        cls,
        db: Session,
        posting_id: uuid.UUID,
        user: UserModel,
        *,
        status: ApplicationStatus | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> ApplicationListResponse:
        """Lists a posting's applications for its author. Applicants cannot enumerate rivals."""
        posting = db.get(ResearchPostingModel, posting_id)
        if posting is None:
            raise ApplicationNotFoundError(f"Research posting '{posting_id}' not found.")
        if posting.author_user_id != user.id and user.role != "ADMIN":
            raise ApplicationPermissionError(
                "Only the posting's author may review its applications."
            )

        safe_limit = max(1, min(limit, cls.MAX_LIMIT))
        safe_offset = max(0, offset)

        stmt = (
            select(ResearchPostingApplicationModel)
            .options(
                joinedload(ResearchPostingApplicationModel.posting),
                joinedload(ResearchPostingApplicationModel.applicant_profile).joinedload(
                    ResearchProfileModel.user
                ),
            )
            .where(ResearchPostingApplicationModel.posting_id == posting_id)
        )
        count_stmt = (
            select(func.count())
            .select_from(ResearchPostingApplicationModel)
            .where(ResearchPostingApplicationModel.posting_id == posting_id)
        )
        if status is not None:
            stmt = stmt.where(ResearchPostingApplicationModel.status == status.value)
            count_stmt = count_stmt.where(ResearchPostingApplicationModel.status == status.value)

        total = db.execute(count_stmt).scalar_one()
        rows = (
            db.execute(
                stmt.order_by(
                    ResearchPostingApplicationModel.submitted_at.desc(),
                    ResearchPostingApplicationModel.id.desc(),
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .unique()
            .scalars()
            .all()
        )

        return ApplicationListResponse(
            applications=[cls.build_application_read(r, user, "AUTHOR") for r in rows],
            total=total,
            limit=safe_limit,
            offset=safe_offset,
        )

    @classmethod
    def list_my_applications(
        cls,
        db: Session,
        applicant_profile_id: uuid.UUID,
        user: UserModel,
        *,
        status: ApplicationStatus | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> ApplicationListResponse:
        safe_limit = max(1, min(limit, cls.MAX_LIMIT))
        safe_offset = max(0, offset)

        stmt = (
            select(ResearchPostingApplicationModel)
            .options(
                joinedload(ResearchPostingApplicationModel.posting),
                joinedload(ResearchPostingApplicationModel.applicant_profile).joinedload(
                    ResearchProfileModel.user
                ),
            )
            .where(ResearchPostingApplicationModel.applicant_profile_id == applicant_profile_id)
        )
        count_stmt = (
            select(func.count())
            .select_from(ResearchPostingApplicationModel)
            .where(ResearchPostingApplicationModel.applicant_profile_id == applicant_profile_id)
        )
        if status is not None:
            stmt = stmt.where(ResearchPostingApplicationModel.status == status.value)
            count_stmt = count_stmt.where(ResearchPostingApplicationModel.status == status.value)

        total = db.execute(count_stmt).scalar_one()
        rows = (
            db.execute(
                stmt.order_by(
                    ResearchPostingApplicationModel.submitted_at.desc(),
                    ResearchPostingApplicationModel.id.desc(),
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            .unique()
            .scalars()
            .all()
        )

        return ApplicationListResponse(
            applications=[cls.build_application_read(r, user, "APPLICANT") for r in rows],
            total=total,
            limit=safe_limit,
            offset=safe_offset,
        )

    @classmethod
    def summarize_my_applications(
        cls,
        db: Session,
        applicant_profile_id: uuid.UUID,
    ) -> ApplicationSummaryResponse:
        rows = db.execute(
            select(ResearchPostingApplicationModel.status, func.count())
            .where(ResearchPostingApplicationModel.applicant_profile_id == applicant_profile_id)
            .group_by(ResearchPostingApplicationModel.status)
        ).all()
        by_status = {row[0]: row[1] for row in rows}
        active = sum(
            count
            for status, count in by_status.items()
            if ApplicationStatus(status) not in INACTIVE_STATUSES
        )
        return ApplicationSummaryResponse(
            total=sum(by_status.values()),
            by_status=by_status,
            active=active,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _append_history(
        application: ResearchPostingApplicationModel,
        from_status: ApplicationStatus | None,
        to_status: ApplicationStatus,
        actor_role: ActorRole,
        reason: str | None,
        at: datetime,
    ) -> None:
        """
        Appends one entry to the status history.

        Reassigned rather than mutated in place so SQLAlchemy reliably detects the change to the
        JSON column; an in-place append can be missed and silently lose the audit entry.
        """
        entry = {
            "from_status": from_status.value if from_status is not None else None,
            "to_status": to_status.value,
            "actor_role": actor_role,
            "reason": reason,
            "at": at.isoformat(),
        }
        application.status_history = list(application.status_history or []) + [entry]

    @staticmethod
    def _notify(
        db: Session,
        *,
        recipient_user_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        body: str,
        source_id: uuid.UUID,
        metadata: dict[str, str],
        reference_time: datetime,
    ) -> NotificationModel | None:
        """
        Delivers an in-app notification, honouring the recipient's preferences.

        Mirrors the Phase 4.6 collaboration notifier, including a deterministic deduplication
        key so a retried request cannot produce two identical alerts.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.user_id == recipient_user_id)
        ).scalar_one_or_none()
        if profile is None:
            return None

        pref = db.execute(
            select(NotificationPreferenceModel).where(
                NotificationPreferenceModel.profile_id == profile.id
            )
        ).scalar_one_or_none()
        if pref is not None and not pref.in_app_enabled:
            return None

        raw_key = (
            f"posting-application:{notification_type.value}:{source_id}:{profile.id}:"
            f"{metadata.get('application_id', '')}:{metadata.get('status', 'NEW')}:"
            f"{reference_time.strftime('%Y%m%d%H%M')}"
        )
        dedup_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        existing = db.execute(
            select(NotificationModel).where(NotificationModel.deduplication_key == dedup_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        notification = NotificationModel(
            profile_id=profile.id,
            notification_type=notification_type.value,
            title=title,
            body=body,
            source_type="RESEARCH_POSTING",
            source_id=source_id,
            scheduled_for=reference_time,
            delivered_at=reference_time,
            delivery_status=DeliveryStatus.DELIVERED.value,
            delivery_channel=DeliveryChannel.IN_APP.value,
            deduplication_key=dedup_key,
            metadata_json=dict(metadata),
        )
        db.add(notification)
        db.flush()
        return notification

    @classmethod
    def build_application_read(
        cls,
        application: ResearchPostingApplicationModel,
        user: UserModel,
        actor_role: ActorRole,
    ) -> ApplicationRead:
        profile = application.applicant_profile
        applicant = ApplicantSummarySchema(
            profile_id=application.applicant_profile_id,
            full_name=getattr(getattr(profile, "user", None), "full_name", None),
            institution=getattr(profile, "institution", None),
            department=getattr(profile, "department", None),
            academic_status=getattr(profile, "academic_status", None),
        )

        history = [
            ApplicationStatusEventSchema(
                from_status=entry.get("from_status"),
                to_status=entry.get("to_status", ""),
                actor_role=entry.get("actor_role", "UNKNOWN"),
                reason=entry.get("reason"),
                at=entry.get("at"),
            )
            for entry in (application.status_history or [])
        ]

        return ApplicationRead(
            id=application.id,
            posting_id=application.posting_id,
            posting_title=getattr(application.posting, "title", None),
            applicant=applicant,
            status=ApplicationStatus(application.status),
            cover_note=application.cover_note,
            contact_email=application.contact_email,
            portfolio_url=application.portfolio_url,
            decision_reason=application.decision_reason,
            # The author's private note is withheld from the applicant.
            reviewer_note=application.reviewer_note if actor_role == "AUTHOR" else None,
            status_history=history,
            submitted_at=application.submitted_at,
            decided_at=application.decided_at,
            withdrawn_at=application.withdrawn_at,
            created_at=application.created_at,
            updated_at=application.updated_at,
            allowed_transitions=cls.allowed_transitions_for(application.status, actor_role),
            is_applicant=actor_role == "APPLICANT",
            is_posting_author=actor_role == "AUTHOR",
        )
