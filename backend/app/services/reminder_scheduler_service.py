from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Any, ClassVar, overload
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models.calendar import CalendarEventType, ResearchCalendarEventModel, ResearchCalendarModel
from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationDeliveryAttemptModel,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
    OffsetUnit,
    ReminderRuleModel,
)
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.user import UserModel
from app.ranking.deadline.extractors import DeadlineEvidenceExtractor
from app.ranking.deadline.models import (
    ConflictState,
    DeadlinePrecision,
    DeadlineType,
    NormalizationStatus,
    RevisionClassification,
)
from app.ranking.deadline.resolvers import DeadlineConflictResolver
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Provider Abstractions & Delivery Results
# ----------------------------------------------------------------------------

@dataclass
class DeliveryResult:
    success: bool
    provider_reference: str | None = None
    error_message: str | None = None


class EmailProvider(ABC):
    """Abstract injectable interface for dispatching email notifications."""

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> DeliveryResult:
        """Send an email to a recipient."""
        pass


class MockEmailProvider(EmailProvider):
    """In-memory safe email provider for development, testing, and CI."""

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> DeliveryResult:
        if not to_email or "@" not in to_email:
            return DeliveryResult(
                success=False,
                error_message=f"Invalid email address: '{to_email}'",
            )

        ref_id = f"mock-msg-{uuid.uuid4().hex[:12]}"
        self.sent_emails.append({
            "to": to_email,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "reference": ref_id,
            "sent_at": datetime.now(timezone.utc),
        })
        logger.info("[MockEmailProvider] Sent email to %s: %s (ref: %s)", to_email, subject, ref_id)
        return DeliveryResult(success=True, provider_reference=ref_id)

    def clear(self) -> None:
        self.sent_emails.clear()


# Default singleton instance
_DEFAULT_EMAIL_PROVIDER: EmailProvider = MockEmailProvider()


def get_email_provider() -> EmailProvider:
    return _DEFAULT_EMAIL_PROVIDER


def set_email_provider(provider: EmailProvider) -> None:
    global _DEFAULT_EMAIL_PROVIDER
    _DEFAULT_EMAIL_PROVIDER = provider


class NotificationChannel(ABC):
    """Abstract delivery channel dispatcher."""

    @abstractmethod
    def dispatch(
        self,
        db: Session,
        notification: NotificationModel,
        user: UserModel,
        auto_commit: bool = True,
    ) -> DeliveryResult:
        pass


class InAppNotificationChannel(NotificationChannel):
    """
    In-app notification channel: marks notification delivered immediately in DB
    with zero external network calls.
    """

    def dispatch(
        self,
        db: Session,
        notification: NotificationModel,
        user: UserModel,
        auto_commit: bool = True,
    ) -> DeliveryResult:
        now = datetime.now(timezone.utc)
        notification.delivery_status = DeliveryStatus.DELIVERED.value
        notification.delivered_at = now
        notification.updated_at = now

        NotificationService.record_delivery_attempt(
            db=db,
            notification_id=notification.id,
            channel=DeliveryChannel.IN_APP.value,
            status=DeliveryStatus.DELIVERED.value,
            attempt_number=1,
            provider_reference=f"in-app-{notification.id}",
            auto_commit=auto_commit,
        )
        return DeliveryResult(success=True, provider_reference=f"in-app-{notification.id}")


class EmailNotificationChannel(NotificationChannel):
    """
    Email notification channel: formats email and dispatches via configured EmailProvider.
    """

    def dispatch(
        self,
        db: Session,
        notification: NotificationModel,
        user: UserModel,
        auto_commit: bool = True,
    ) -> DeliveryResult:
        provider = get_email_provider()
        to_email = user.email

        if not to_email:
            err = "User has no registered email address."
            notification.delivery_status = DeliveryStatus.FAILED.value
            notification.updated_at = datetime.now(timezone.utc)
            NotificationService.record_delivery_attempt(
                db=db,
                notification_id=notification.id,
                channel=DeliveryChannel.EMAIL.value,
                status="FAILED",
                attempt_number=1,
                error_message=err,
                auto_commit=auto_commit,
            )
            return DeliveryResult(success=False, error_message=err)

        subject = f"[ResearchConnect Alert] {notification.title}"
        body = (
            f"Hello {user.full_name or 'Researcher'},\n\n"
            f"{notification.body}\n\n"
            f"Notification Type: {notification.notification_type}\n"
            f"Scheduled For: {notification.scheduled_for.isoformat()}\n\n"
            f"View details on ResearchConnect AI: /notifications\n"
        )

        result = provider.send_email(to_email=to_email, subject=subject, body_text=body)
        now = datetime.now(timezone.utc)

        if result.success:
            notification.delivery_status = DeliveryStatus.DELIVERED.value
            notification.delivered_at = now
            notification.updated_at = now
            NotificationService.record_delivery_attempt(
                db=db,
                notification_id=notification.id,
                channel=DeliveryChannel.EMAIL.value,
                status=DeliveryStatus.DELIVERED.value,
                attempt_number=1,
                provider_reference=result.provider_reference,
                auto_commit=auto_commit,
            )
        else:
            notification.delivery_status = DeliveryStatus.FAILED.value
            notification.updated_at = now
            NotificationService.record_delivery_attempt(
                db=db,
                notification_id=notification.id,
                channel=DeliveryChannel.EMAIL.value,
                status="FAILED",
                attempt_number=1,
                error_message=result.error_message,
                auto_commit=auto_commit,
            )

        return result


class PushNotificationChannel(NotificationChannel):
    """Push notification channel with mock provider support."""

    def dispatch(
        self,
        db: Session,
        notification: NotificationModel,
        user: UserModel,
        auto_commit: bool = True,
    ) -> DeliveryResult:
        now = datetime.now(timezone.utc)
        notification.delivery_status = DeliveryStatus.DELIVERED.value
        notification.delivered_at = now
        notification.updated_at = now

        ref = f"push-mock-{notification.id}"
        NotificationService.record_delivery_attempt(
            db=db,
            notification_id=notification.id,
            channel=DeliveryChannel.PUSH.value,
            status=DeliveryStatus.DELIVERED.value,
            attempt_number=1,
            provider_reference=ref,
            auto_commit=auto_commit,
        )
        return DeliveryResult(success=True, provider_reference=ref)


# Channel registry
_CHANNELS: dict[str, NotificationChannel] = {
    DeliveryChannel.IN_APP.value: InAppNotificationChannel(),
    DeliveryChannel.EMAIL.value: EmailNotificationChannel(),
    DeliveryChannel.PUSH.value: PushNotificationChannel(),
}


# ----------------------------------------------------------------------------
# Milestone Mapping & Deduplication Key Computation
# ----------------------------------------------------------------------------

DEADLINE_TO_CALENDAR_TYPE: dict[DeadlineType, CalendarEventType] = {
    DeadlineType.SUBMISSION: CalendarEventType.OPPORTUNITY_SUBMISSION,
    DeadlineType.ABSTRACT: CalendarEventType.ABSTRACT_DEADLINE,
    DeadlineType.NOTIFICATION: CalendarEventType.NOTIFICATION,
    DeadlineType.CAMERA_READY: CalendarEventType.CAMERA_READY,
    DeadlineType.REGISTRATION: CalendarEventType.REGISTRATION,
    DeadlineType.EVENT_START: CalendarEventType.EVENT_START,
    DeadlineType.EVENT_END: CalendarEventType.EVENT_END,
}


@overload
def _as_utc(dt: None) -> None: ...


@overload
def _as_utc(dt: datetime) -> datetime: ...


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_deduplication_key(
    profile_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID | str,
    deadline_type: str | None,
    rule_id: uuid.UUID | str | None,
    delivery_channel: str,
    target_instant: datetime | str | None,
    notification_type: str,
) -> str:
    """
    Computes a deterministic hash key preventing duplicate notifications.
    Identical inputs always yield the exact same deduplication key.
    """
    if isinstance(target_instant, datetime):
        utc_dt = _as_utc(target_instant)
        instant_str = utc_dt.strftime("%Y%m%dT%H%M%SZ") if utc_dt is not None else "NONE"
    else:
        instant_str = target_instant if target_instant else "NONE"

    raw = (
        f"{profile_id}:{source_type}:{source_id}:{deadline_type or 'NONE'}:"
        f"{rule_id or 'DEFAULT'}:{delivery_channel}:{instant_str}:{notification_type}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------
# Reminder Scheduler Engine
# ----------------------------------------------------------------------------

@dataclass
class ReminderRunSummary:
    discovered_reminders: int = 0
    created_notifications: int = 0
    delivered_notifications: int = 0
    skipped_duplicates: int = 0
    cancelled_obsolete: int = 0
    errors: list[str] = field(default_factory=list)
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ReminderSchedulerService:
    """
    Core engine managing scheduled reminder evaluation, deadline revision tracking,
    idempotent notification creation, and multi-channel delivery dispatching.
    """

    @classmethod
    def calculate_scheduled_time(
        cls,
        target_utc: datetime,
        offset_amount: int,
        offset_unit: str,
    ) -> datetime:
        """
        Calculates reminder scheduled time based on offset amount and unit.
        """
        if offset_unit == OffsetUnit.DAYS.value:
            return target_utc - timedelta(days=offset_amount)
        elif offset_unit == OffsetUnit.HOURS.value:
            return target_utc - timedelta(hours=offset_amount)
        elif offset_unit == OffsetUnit.MINUTES.value:
            return target_utc - timedelta(minutes=offset_amount)
        return target_utc - timedelta(days=offset_amount)

    @classmethod
    def run_scheduled_reminders(
        cls,
        db: Session,
        now: datetime | None = None,
    ) -> ReminderRunSummary:
        """
        Executes a deterministic scheduled reminder pass.

        Workflow:
        1. Queries all active research profiles.
        2. Retrieves user notification preferences and reminder rules.
        3. Inspects tracked opportunities (Workspace) and calendar events.
        4. Evaluates canonical Phase 2.7 deadline representations without mutating evidence.
        5. Computes reminder due times and detects deadline revisions/extensions.
        6. Idempotently creates notifications and dispatches to enabled delivery channels.
        7. Records full delivery attempt history.
        """
        eval_time = _as_utc(now) or datetime.now(timezone.utc)
        summary = ReminderRunSummary(executed_at=eval_time)
        opp_canonical_cache: dict[uuid.UUID, Any] = {}

        # 1. Fetch all profiles with associated user and preferences
        profiles_stmt = (
            select(ResearchProfileModel)
            .options(
                joinedload(ResearchProfileModel.user),
            )
        )
        profiles = list(db.execute(profiles_stmt).scalars().all())
        if not profiles:
            return summary

        profile_ids = [p.id for p in profiles]
        user_ids = [p.user_id for p in profiles if p.user_id]

        def _chunked(items: list, size: int = 400):
            for i in range(0, len(items), size):
                yield items[i : i + size]

        # 2. Bulk load preferences
        prefs_map = {}
        for chunk in _chunked(profile_ids):
            prefs_stmt = select(NotificationPreferenceModel).where(
                NotificationPreferenceModel.profile_id.in_(chunk)
            )
            for pref in db.execute(prefs_stmt).scalars().all():
                prefs_map[pref.profile_id] = pref

        # 3. Bulk load active reminder rules
        rules_map: dict[uuid.UUID, list[ReminderRuleModel]] = defaultdict(list)
        for chunk in _chunked(profile_ids):
            rules_stmt = select(ReminderRuleModel).where(
                ReminderRuleModel.profile_id.in_(chunk),
                ReminderRuleModel.is_active.is_(True),
            )
            for r in db.execute(rules_stmt).scalars().all():
                rules_map[r.profile_id].append(r)

        # 4. Bulk load saved opportunities
        saved_opps_map: dict[uuid.UUID, list[SavedOpportunityModel]] = defaultdict(list)
        for chunk in _chunked(user_ids):
            saved_opps_stmt = (
                select(SavedOpportunityModel)
                .options(joinedload(SavedOpportunityModel.opportunity))
                .where(
                    SavedOpportunityModel.user_id.in_(chunk),
                    SavedOpportunityModel.status != "ARCHIVED",
                )
            )
            for s_opp in db.execute(saved_opps_stmt).scalars().all():
                saved_opps_map[s_opp.user_id].append(s_opp)

        # 5. Bulk load existing notifications for deduplication
        existing_notifs_map = {}
        for chunk in _chunked(profile_ids):
            existing_notifs_stmt = select(NotificationModel).where(
                NotificationModel.profile_id.in_(chunk)
            )
            for n in db.execute(existing_notifs_stmt).scalars().all():
                existing_notifs_map[n.deduplication_key] = n

        for profile in profiles:
            try:
                cls._process_profile_reminders(
                    db=db,
                    profile=profile,
                    eval_time=eval_time,
                    summary=summary,
                    opp_canonical_cache=opp_canonical_cache,
                    prefs_map=prefs_map,
                    rules_map=rules_map,
                    saved_opps_map=saved_opps_map,
                    existing_notifs_map=existing_notifs_map,
                )
            except Exception as err:
                logger.exception("Error processing reminders for profile %s: %s", profile.id, err)
                summary.errors.append(f"Profile {profile.id}: {str(err)}")

        db.commit()
        return summary

    @classmethod
    def _process_profile_reminders(
        cls,
        db: Session,
        profile: ResearchProfileModel,
        eval_time: datetime,
        summary: ReminderRunSummary,
        opp_canonical_cache: dict[uuid.UUID, Any] | None = None,
        prefs_map: dict[uuid.UUID, NotificationPreferenceModel] | None = None,
        rules_map: dict[uuid.UUID, list[ReminderRuleModel]] | None = None,
        saved_opps_map: dict[uuid.UUID, list[SavedOpportunityModel]] | None = None,
        existing_notifs_map: dict[str, NotificationModel] | None = None,
    ) -> None:
        user = profile.user
        if not user:
            return

        if opp_canonical_cache is None:
            opp_canonical_cache = {}

        prefs = prefs_map.get(profile.id) if prefs_map is not None else None
        if not prefs:
            prefs = NotificationPreferenceModel(
                profile_id=profile.id,
                email_enabled=True,
                in_app_enabled=True,
                deadline_reminders_enabled=True,
                extension_notifications_enabled=True,
                conflict_notifications_enabled=True,
                calendar_event_reminders_enabled=True,
            )
            db.add(prefs)
            if prefs_map is not None:
                prefs_map[profile.id] = prefs

        rules = rules_map.get(profile.id) if rules_map is not None else None
        if not rules:
            rules = NotificationService.list_reminder_rules(db, profile.id, is_active=True)
            if not rules:
                rules = NotificationService.bootstrap_default_reminder_rules(db, profile.id)
            if rules_map is not None:
                rules_map[profile.id] = rules

        # --------------------------------------------------------------------
        # A. Process Opportunities from Workspace & Saved Opportunities
        # --------------------------------------------------------------------
        if saved_opps_map is not None:
            saved_opps = saved_opps_map.get(user.id, [])
        else:
            saved_opps_stmt = (
                select(SavedOpportunityModel)
                .options(joinedload(SavedOpportunityModel.opportunity))
                .where(
                    SavedOpportunityModel.user_id == user.id,
                    SavedOpportunityModel.status != "ARCHIVED",
                )
            )
            saved_opps = list(db.execute(saved_opps_stmt).scalars().all())

        for s_opp in saved_opps:
            opp = s_opp.opportunity
            if not opp:
                continue

            cls._process_opportunity_milestones(
                db=db,
                profile=profile,
                user=user,
                opp=opp,
                prefs=prefs,
                rules=rules,
                eval_time=eval_time,
                summary=summary,
                opp_canonical_cache=opp_canonical_cache,
                existing_notifs_map=existing_notifs_map,
            )

        # --------------------------------------------------------------------
        # B. Process User-Created Calendar Planning Events
        # --------------------------------------------------------------------
        if prefs.calendar_event_reminders_enabled and prefs.in_app_enabled:
            cls._process_calendar_planning_events(
                db=db,
                profile=profile,
                user=user,
                prefs=prefs,
                rules=rules,
                eval_time=eval_time,
                summary=summary,
                existing_notifs_map=existing_notifs_map,
            )

    @classmethod
    def _process_opportunity_milestones(
        cls,
        db: Session,
        profile: ResearchProfileModel,
        user: UserModel,
        opp: OpportunityModel,
        prefs: NotificationPreferenceModel,
        rules: list[ReminderRuleModel],
        eval_time: datetime,
        summary: ReminderRunSummary,
        opp_canonical_cache: dict[uuid.UUID, Any] | None = None,
        existing_notifs_map: dict[str, NotificationModel] | None = None,
    ) -> None:
        # Resolve canonical view from Phase 2.7 authoritative resolver (cached per opportunity)
        if opp_canonical_cache is not None and opp.id in opp_canonical_cache:
            canonical_opp = opp_canonical_cache[opp.id]
        else:
            evidence_collection = DeadlineEvidenceExtractor.extract_from_opportunity_model(opp)
            canonical_opp = DeadlineConflictResolver.resolve_opportunity(
                evidence_collection,
                opportunity_id=str(opp.id),
            )
            if opp_canonical_cache is not None:
                opp_canonical_cache[opp.id] = canonical_opp

        for m_type, v in canonical_opp.milestone_views.items():
            summary.discovered_reminders += 1

            # Check for equal-authority conflict (Invariant 9 & 15)
            if v.conflict_state == ConflictState.SOURCE_CONFLICT:
                if prefs.conflict_notifications_enabled:
                    cls._handle_conflict_notification(
                        db=db,
                        profile=profile,
                        user=user,
                        opp=opp,
                        m_type=m_type,
                        prefs=prefs,
                        eval_time=eval_time,
                        summary=summary,
                        existing_notifs_map=existing_notifs_map,
                    )
                continue

            canonical_dl = v.canonical_deadline
            if not canonical_dl:
                continue

            # Invariant 1 & 2: Missing, ambiguous, or invalid deadline does not schedule reminder
            if canonical_dl.normalization_status in (
                NormalizationStatus.MISSING,
                NormalizationStatus.AMBIGUOUS,
                NormalizationStatus.INVALID,
            ):
                continue

            # Target UTC instant
            target_utc = _as_utc(canonical_dl.normalized_utc)
            if not target_utc:
                continue

            # Check for revisions (Phase 2.7E extensions or moves)
            if v.latest_revision:
                cls._handle_revision_notifications(
                    db=db,
                    profile=profile,
                    user=user,
                    opp=opp,
                    m_type=m_type,
                    v=v,
                    target_utc=target_utc,
                    prefs=prefs,
                    eval_time=eval_time,
                    summary=summary,
                    existing_notifs_map=existing_notifs_map,
                )

            # Invariant 18: If deadline reminders are disabled in preferences, skip
            if not prefs.deadline_reminders_enabled:
                continue

            # Evaluate reminder rules against this milestone
            m_type_val = m_type.value if hasattr(m_type, "value") else str(m_type)
            clean_m_name = m_type_val.replace("_", " ").title()

            # Precompute matching event types (milestone type and corresponding calendar event type)
            cal_event = DEADLINE_TO_CALENDAR_TYPE.get(m_type)
            cal_event_val = cal_event.value if hasattr(cal_event, "value") else (str(cal_event) if cal_event else None)
            matching_event_types = {m_type_val}
            if cal_event_val:
                matching_event_types.add(cal_event_val)

            for rule in rules:
                if not rule.is_active:
                    continue

                # Milestone filtering: rule applies if rule.event_type matches or is None
                if rule.event_type and rule.event_type not in matching_event_types:
                    continue

                channel = rule.delivery_channel
                # Channel enablement check
                if channel == DeliveryChannel.EMAIL.value and not prefs.email_enabled:
                    continue
                if channel == DeliveryChannel.IN_APP.value and not prefs.in_app_enabled:
                    continue

                scheduled_time = cls.calculate_scheduled_time(
                    target_utc=target_utc,
                    offset_amount=rule.offset_amount,
                    offset_unit=rule.offset_unit,
                )

                # A reminder is due if scheduled_time <= eval_time < target_utc
                # or if target is today (within lookback window)
                if scheduled_time <= eval_time < target_utc:
                    notif_type = (
                        NotificationType.DEADLINE_TODAY.value
                        if target_utc.date() == eval_time.date()
                        else NotificationType.DEADLINE_UPCOMING.value
                    )

                    time_str = f"{rule.offset_amount} {rule.offset_unit.lower()}"
                    tz_display = canonical_dl.timezone_name or canonical_dl.timezone_offset or "UTC"
                    venue_str = getattr(opp, "location", None) or getattr(opp, "publisher", None) or "Venue TBA"

                    title = f"Upcoming {clean_m_name}: {opp.title}"
                    body = (
                        f"The canonical {clean_m_name} for '{opp.title}' ({venue_str}) "
                        f"is scheduled for {target_utc.strftime('%Y-%m-%d %H:%M %Z')} ({tz_display}). "
                        f"This is your {time_str} reminder."
                    )

                    dedup_key = compute_deduplication_key(
                        profile_id=profile.id,
                        source_type="OPPORTUNITY",
                        source_id=opp.id,
                        deadline_type=m_type.value,
                        rule_id=rule.id,
                        delivery_channel=channel,
                        target_instant=target_utc,
                        notification_type=notif_type,
                    )

                    cls._create_and_dispatch_notification(
                        db=db,
                        profile=profile,
                        user=user,
                        notification_type=notif_type,
                        title=title,
                        body=body,
                        source_type="OPPORTUNITY",
                        source_id=opp.id,
                        opportunity_id=opp.id,
                        calendar_event_id=None,
                        submission_id=None,
                        deadline_type=m_type.value,
                        scheduled_for=scheduled_time,
                        delivery_channel=channel,
                        deduplication_key=dedup_key,
                        metadata_json={
                            "opportunity_id": str(opp.id),
                            "opportunity_title": opp.title,
                            "milestone_type": m_type.value,
                            "canonical_deadline": target_utc.isoformat(),
                            "original_timezone": tz_display,
                            "rule_offset": f"{rule.offset_amount} {rule.offset_unit}",
                        },
                        summary=summary,
                        existing_notifs_map=existing_notifs_map,
                    )

    @classmethod
    def _handle_conflict_notification(
        cls,
        db: Session,
        profile: ResearchProfileModel,
        user: UserModel,
        opp: OpportunityModel,
        m_type: DeadlineType,
        prefs: NotificationPreferenceModel,
        eval_time: datetime,
        summary: ReminderRunSummary,
        existing_notifs_map: dict[str, NotificationModel] | None = None,
    ) -> None:
        """Surfaces unresolved equal-authority deadline conflict without fabricating a winner."""
        clean_m_name = m_type.value.replace("_", " ").title()
        title = f"Deadline Conflict: {opp.title} ({clean_m_name})"
        body = (
            f"An unresolved deadline conflict was detected for '{opp.title}'. "
            f"Multiple authoritative sources report differing dates for the {clean_m_name} milestone. "
            f"The milestone remains pending verified canonical evidence."
        )

        dedup_key = compute_deduplication_key(
            profile_id=profile.id,
            source_type="OPPORTUNITY",
            source_id=opp.id,
            deadline_type=m_type.value,
            rule_id="CONFLICT_ALERT",
            delivery_channel=DeliveryChannel.IN_APP.value,
            target_instant="CONFLICT",
            notification_type=NotificationType.DEADLINE_CONFLICT.value,
        )

        cls._create_and_dispatch_notification(
            db=db,
            profile=profile,
            user=user,
            notification_type=NotificationType.DEADLINE_CONFLICT.value,
            title=title,
            body=body,
            source_type="OPPORTUNITY",
            source_id=opp.id,
            opportunity_id=opp.id,
            calendar_event_id=None,
            submission_id=None,
            deadline_type=m_type.value,
            scheduled_for=eval_time,
            delivery_channel=DeliveryChannel.IN_APP.value,
            deduplication_key=dedup_key,
            metadata_json={
                "opportunity_id": str(opp.id),
                "opportunity_title": opp.title,
                "milestone_type": m_type.value,
                "conflict_state": ConflictState.SOURCE_CONFLICT.value,
            },
            summary=summary,
            existing_notifs_map=existing_notifs_map,
        )

    @classmethod
    def _handle_revision_notifications(
        cls,
        db: Session,
        profile: ResearchProfileModel,
        user: UserModel,
        opp: OpportunityModel,
        m_type: DeadlineType,
        v: Any,
        target_utc: datetime,
        prefs: NotificationPreferenceModel,
        eval_time: datetime,
        summary: ReminderRunSummary,
        existing_notifs_map: dict[str, NotificationModel] | None = None,
    ) -> None:
        """Handles deadline extensions and earlier shifts according to Phase 2.7E revision intelligence."""
        rev = v.latest_revision
        clean_m_name = m_type.value.replace("_", " ").title()
        rev_val = rev.classification.value if hasattr(rev.classification, "value") else str(rev.classification)

        if rev_val == RevisionClassification.EXTENDED.value and prefs.extension_notifications_enabled:
            title = f"Deadline Extended: {opp.title} ({clean_m_name})"
            body = (
                f"The {clean_m_name} deadline for '{opp.title}' has been extended to "
                f"{target_utc.strftime('%Y-%m-%d %H:%M %Z')}. {rev.explanation or ''}"
            )
            dedup_key = compute_deduplication_key(
                profile_id=profile.id,
                source_type="OPPORTUNITY",
                source_id=opp.id,
                deadline_type=m_type.value,
                rule_id=f"REVISION_EXTENDED_{m_type.value}",
                delivery_channel=DeliveryChannel.IN_APP.value,
                target_instant=target_utc,
                notification_type=NotificationType.DEADLINE_EXTENDED.value,
            )

            cls._create_and_dispatch_notification(
                db=db,
                profile=profile,
                user=user,
                notification_type=NotificationType.DEADLINE_EXTENDED.value,
                title=title,
                body=body,
                source_type="OPPORTUNITY",
                source_id=opp.id,
                opportunity_id=opp.id,
                calendar_event_id=None,
                submission_id=None,
                deadline_type=m_type.value,
                scheduled_for=eval_time,
                delivery_channel=DeliveryChannel.IN_APP.value,
                deduplication_key=dedup_key,
                metadata_json={
                    "opportunity_id": str(opp.id),
                    "opportunity_title": opp.title,
                    "milestone_type": m_type.value,
                    "revision_type": "EXTENDED",
                    "new_deadline": target_utc.isoformat(),
                    "reason": rev.explanation,
                },
                summary=summary,
                existing_notifs_map=existing_notifs_map,
            )

        elif rev_val == RevisionClassification.MOVED_EARLIER.value and prefs.deadline_reminders_enabled:
            title = f"Deadline Moved Earlier: {opp.title} ({clean_m_name})"
            body = (
                f"Notice: The {clean_m_name} deadline for '{opp.title}' was moved earlier to "
                f"{target_utc.strftime('%Y-%m-%d %H:%M %Z')}. Please review your submission schedule."
            )
            dedup_key = compute_deduplication_key(
                profile_id=profile.id,
                source_type="OPPORTUNITY",
                source_id=opp.id,
                deadline_type=m_type.value,
                rule_id=f"REVISION_MOVED_{m_type.value}",
                delivery_channel=DeliveryChannel.IN_APP.value,
                target_instant=target_utc,
                notification_type=NotificationType.DEADLINE_MOVED_EARLIER.value,
            )

            cls._create_and_dispatch_notification(
                db=db,
                profile=profile,
                user=user,
                notification_type=NotificationType.DEADLINE_MOVED_EARLIER.value,
                title=title,
                body=body,
                source_type="OPPORTUNITY",
                source_id=opp.id,
                opportunity_id=opp.id,
                calendar_event_id=None,
                submission_id=None,
                deadline_type=m_type.value,
                scheduled_for=eval_time,
                delivery_channel=DeliveryChannel.IN_APP.value,
                deduplication_key=dedup_key,
                metadata_json={
                    "opportunity_id": str(opp.id),
                    "opportunity_title": opp.title,
                    "milestone_type": m_type.value,
                    "revision_type": "MOVED_EARLIER",
                    "new_deadline": target_utc.isoformat(),
                    "reason": rev.explanation,
                },
                summary=summary,
                existing_notifs_map=existing_notifs_map,
            )

    @classmethod
    def _process_calendar_planning_events(
        cls,
        db: Session,
        profile: ResearchProfileModel,
        user: UserModel,
        prefs: NotificationPreferenceModel,
        rules: list[ReminderRuleModel],
        eval_time: datetime,
        summary: ReminderRunSummary,
        existing_notifs_map: dict[str, NotificationModel] | None = None,
    ) -> None:
        """Evaluates reminders for researcher-created calendar planning events."""
        events_stmt = (
            select(ResearchCalendarEventModel)
            .join(ResearchCalendarModel, ResearchCalendarEventModel.calendar_id == ResearchCalendarModel.id)
            .where(
                ResearchCalendarModel.user_id == user.id,
                ResearchCalendarEventModel.is_canonical_projection.is_(False),
                ResearchCalendarEventModel.start_datetime.is_not(None),
            )
        )
        user_events = list(db.execute(events_stmt).scalars().all())

        for ev in user_events:
            target_utc = _as_utc(ev.start_datetime)
            if not target_utc or eval_time >= target_utc:
                continue

            # Standard 24h advance reminder for planning milestones
            scheduled_time = target_utc - timedelta(hours=24)
            if scheduled_time <= eval_time < target_utc:
                title = f"Milestone Reminder: {ev.title}"
                body = (
                    f"Your research planning milestone '{ev.title}' is scheduled for "
                    f"{target_utc.strftime('%Y-%m-%d %H:%M %Z')}."
                )
                dedup_key = compute_deduplication_key(
                    profile_id=profile.id,
                    source_type="CALENDAR_EVENT",
                    source_id=ev.id,
                    deadline_type=ev.event_type,
                    rule_id="PLANNING_24H",
                    delivery_channel=DeliveryChannel.IN_APP.value,
                    target_instant=target_utc,
                    notification_type=NotificationType.CALENDAR_EVENT_UPCOMING.value,
                )

                cls._create_and_dispatch_notification(
                    db=db,
                    profile=profile,
                    user=user,
                    notification_type=NotificationType.CALENDAR_EVENT_UPCOMING.value,
                    title=title,
                    body=body,
                    source_type="CALENDAR_EVENT",
                    source_id=ev.id,
                    opportunity_id=None,
                    calendar_event_id=ev.id,
                    submission_id=ev.submission_id,
                    deadline_type=ev.event_type,
                    scheduled_for=scheduled_time,
                    delivery_channel=DeliveryChannel.IN_APP.value,
                    deduplication_key=dedup_key,
                    metadata_json={
                        "calendar_event_id": str(ev.id),
                        "calendar_event_title": ev.title,
                        "event_type": ev.event_type,
                    },
                    summary=summary,
                    existing_notifs_map=existing_notifs_map,
                )

    @classmethod
    def _create_and_dispatch_notification(
        cls,
        db: Session,
        profile: ResearchProfileModel,
        user: UserModel,
        notification_type: str,
        title: str,
        body: str,
        source_type: str,
        source_id: uuid.UUID | None,
        opportunity_id: uuid.UUID | None,
        calendar_event_id: uuid.UUID | None,
        submission_id: uuid.UUID | None,
        deadline_type: str | None,
        scheduled_for: datetime,
        delivery_channel: str,
        deduplication_key: str,
        metadata_json: dict[str, Any],
        summary: ReminderRunSummary,
        existing_notifs_map: dict[str, NotificationModel] | None = None,
    ) -> NotificationModel | None:
        """
        Idempotently creates a notification and dispatches to the requested delivery channel.
        If a notification with deduplication_key already exists, skips gracefully.
        """
        # Invariant 15 & 32: Check for existing notification with identical deduplication_key
        if existing_notifs_map is not None:
            existing = existing_notifs_map.get(deduplication_key)
        else:
            stmt = select(NotificationModel).where(
                NotificationModel.deduplication_key == deduplication_key
            )
            existing = db.execute(stmt).scalars().first()

        if existing:
            summary.skipped_duplicates += 1
            # If already delivered or skipped, return existing
            if existing.delivery_status == DeliveryStatus.DELIVERED.value:
                return existing
            # If failed or pending, attempt delivery retry
            channel_handler = _CHANNELS.get(delivery_channel)
            if channel_handler:
                result = channel_handler.dispatch(db=db, notification=existing, user=user, auto_commit=False)
                if result.success:
                    summary.delivered_notifications += 1
            return existing

        # Create new notification
        notif_id = uuid.uuid4()
        notif = NotificationModel(
            id=notif_id,
            profile_id=profile.id,
            notification_type=notification_type,
            title=title,
            body=body,
            source_type=source_type,
            source_id=source_id,
            opportunity_id=opportunity_id,
            calendar_event_id=calendar_event_id,
            submission_id=submission_id,
            deadline_type=deadline_type,
            scheduled_for=scheduled_for,
            delivery_status=DeliveryStatus.PENDING.value,
            delivery_channel=delivery_channel,
            deduplication_key=deduplication_key,
            metadata_json=metadata_json,
        )
        db.add(notif)
        if existing_notifs_map is not None:
            existing_notifs_map[deduplication_key] = notif
        summary.created_notifications += 1

        # Dispatch via channel
        channel_handler = _CHANNELS.get(delivery_channel)
        if channel_handler:
            result = channel_handler.dispatch(db=db, notification=notif, user=user, auto_commit=False)
            if result.success:
                summary.delivered_notifications += 1

        return notif
