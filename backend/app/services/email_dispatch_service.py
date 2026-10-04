"""
Phase 5.16 — Email copies of in-app notifications.

Every notification is still created in-app exactly as before, by whichever feature raises it.
This pass, run by the email_dispatch scheduler job, decides once per in-app notification whether
it is also emailed, and records the outcome in notifications.email_status:

    SKIPPED  not an emailed type, already read in the app, email alerts off in the recipient's
             preferences, no active account or address, recipient not allowed by the
             provider, or older than EMAIL_WINDOW
    SENT     the mail server accepted it
    RETRY    the server was unreachable or refused for now; tried again on the next pass
    FAILED   refused for good, or MAX_EMAIL_ATTEMPTS used

Only the email columns change: the in-app delivery_status and delivered_at are never touched.
Each send is committed on its own, so a crash repeats at most the one email in flight. Every
send attempt is recorded in notification_delivery_attempts with channel EMAIL. When the server
is unreachable the pass stops, and the rest wait for the next pass. No address is logged.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import logging
import uuid

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    EmailStatus,
    NotificationDeliveryAttemptModel,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
)
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.services.reminder_scheduler_service import EmailProvider, get_email_provider

logger = logging.getLogger(__name__)

# Notifications worth an email. Frequent collaboration activity (invitation accepted, task
# completed, document updated, general activity) stays in-app only.
EMAILED_TYPES = frozenset(
    notification_type.value
    for notification_type in (
        NotificationType.DEADLINE_UPCOMING,
        NotificationType.DEADLINE_TODAY,
        NotificationType.DEADLINE_EXTENDED,
        NotificationType.DEADLINE_MOVED_EARLIER,
        NotificationType.DEADLINE_CONFLICT,
        NotificationType.CALENDAR_EVENT_UPCOMING,
        NotificationType.SUBMISSION_STATUS_CHANGE,
        NotificationType.SYSTEM,
        NotificationType.WORKSPACE_INVITATION,
        NotificationType.MEMBER_ROLE_CHANGED,
        NotificationType.MEMBER_REMOVED,
        NotificationType.TASK_ASSIGNED,
        NotificationType.POSTING_MATCH,
    )
)
# Older notifications are no longer news: they are skipped, never sent.
EMAIL_WINDOW = timedelta(hours=6)
BATCH_SIZE = 25
MAX_EMAIL_ATTEMPTS = 5
MAX_ERROR_LENGTH = 500


@dataclass
class EmailDispatchSummary:
    sent: int = 0
    skipped: int = 0
    retrying: int = 0
    failed: int = 0
    expired: int = 0
    # True when the pass stopped early because the mail server was unreachable.
    paused: bool = False


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


def link_path(notification: NotificationModel) -> str:
    """The page in the web app that the email links to."""
    if notification.source_type == "RESEARCH_POSTING" and notification.source_id:
        return f"/postings/{notification.source_id}"
    if notification.calendar_event_id:
        return "/calendar"
    if notification.opportunity_id or notification.source_type == "WORKSPACE":
        return "/workspace"
    return "/notifications"


def render_email(notification: NotificationModel, user: UserModel, app_url: str) -> RenderedEmail:
    """A plain-text and an HTML version; every stored value is escaped in the HTML."""
    base = app_url.rstrip("/")
    link = base + link_path(notification)
    settings_link = base + "/settings/notifications"
    name = (user.full_name or "").strip() or "there"
    subject = " ".join(notification.title.split())
    text = (
        f"Hi {name},\n\n"
        f"{notification.body}\n\n"
        f"Open in ResearchConnect: {link}\n\n"
        "--\n"
        "You get this email because email alerts are on.\n"
        f"Change that in your notification settings: {settings_link}\n"
    )
    escape = html.escape
    html_body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#1f2937">'
        f"<p>Hi {escape(name)},</p>"
        f"<p><strong>{escape(subject)}</strong></p>"
        f"<p>{escape(notification.body)}</p>"
        f'<p><a href="{escape(link)}">Open in ResearchConnect</a></p>'
        '<p style="color:#6b7280;font-size:12px">You get this email because email alerts are on. '
        f'<a href="{escape(settings_link)}">Change your notification settings</a>.</p>'
        "</div>"
    )
    return RenderedEmail(subject=subject, text=text, html=html_body)


class EmailDispatchService:
    """Sends the email copies of recent in-app notifications."""

    @classmethod
    def dispatch_pending(
        cls,
        db: Session,
        *,
        app_url: str,
        now: datetime | None = None,
        provider: EmailProvider | None = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> EmailDispatchSummary:
        now = now or datetime.now(timezone.utc)
        provider = provider or get_email_provider()
        summary = EmailDispatchSummary()
        cutoff = now - EMAIL_WINDOW

        waiting = and_(
            NotificationModel.delivery_channel == DeliveryChannel.IN_APP.value,
            NotificationModel.delivery_status == DeliveryStatus.DELIVERED.value,
            or_(
                NotificationModel.email_status.is_(None),
                NotificationModel.email_status == EmailStatus.RETRY.value,
            ),
        )

        # Too old to be worth an email: decided once, never sent.
        summary.expired = db.execute(
            update(NotificationModel)
            .where(waiting, NotificationModel.created_at < cutoff)
            .values(email_status=EmailStatus.SKIPPED.value)
            .execution_options(synchronize_session=False)
        ).rowcount
        db.commit()

        rows = db.execute(
            select(NotificationModel, UserModel, NotificationPreferenceModel)
            .outerjoin(ResearchProfileModel, ResearchProfileModel.id == NotificationModel.profile_id)
            .outerjoin(UserModel, UserModel.id == ResearchProfileModel.user_id)
            .outerjoin(
                NotificationPreferenceModel,
                NotificationPreferenceModel.profile_id == NotificationModel.profile_id,
            )
            .where(waiting, NotificationModel.created_at >= cutoff)
            .order_by(NotificationModel.created_at, NotificationModel.id)
            .limit(BATCH_SIZE)
        ).all()

        for notification, user, preferences in rows:
            if should_stop():
                break

            if not cls._should_email(notification, user, preferences, provider):
                notification.email_status = EmailStatus.SKIPPED.value
                summary.skipped += 1
                db.commit()
                continue

            email = render_email(notification, user, app_url)
            result = provider.send_email(
                to_email=user.email,
                subject=email.subject,
                body_text=email.text,
                body_html=email.html,
            )
            notification.email_attempts = (notification.email_attempts or 0) + 1
            if result.success:
                notification.email_status = EmailStatus.SENT.value
                notification.email_sent_at = now
                summary.sent += 1
            elif result.retryable and notification.email_attempts < MAX_EMAIL_ATTEMPTS:
                notification.email_status = EmailStatus.RETRY.value
                summary.retrying += 1
            else:
                notification.email_status = EmailStatus.FAILED.value
                summary.failed += 1

            db.add(
                NotificationDeliveryAttemptModel(
                    id=uuid.uuid4(),
                    notification_id=notification.id,
                    channel=DeliveryChannel.EMAIL.value,
                    status=DeliveryStatus.DELIVERED.value if result.success else DeliveryStatus.FAILED.value,
                    attempt_number=notification.email_attempts,
                    attempted_at=now,
                    provider_reference=result.provider_reference,
                    error_message=result.error_message[:MAX_ERROR_LENGTH] if result.error_message else None,
                )
            )
            db.commit()

            if not result.success and result.retryable:
                # The server is down or refusing for now: the rest wait for the next pass.
                summary.paused = True
                logger.warning(
                    "Email delivery paused until the next pass: %s",
                    result.error_message,
                    extra={"notification_id": str(notification.id)},
                )
                break

        if summary.sent or summary.failed or summary.retrying:
            logger.info(
                "Email dispatch: %d sent, %d retrying, %d failed, %d skipped, %d expired",
                summary.sent,
                summary.retrying,
                summary.failed,
                summary.skipped,
                summary.expired,
            )
        return summary

    @staticmethod
    def _should_email(
        notification: NotificationModel,
        user: UserModel | None,
        preferences: NotificationPreferenceModel | None,
        provider: EmailProvider,
    ) -> bool:
        return (
            notification.notification_type in EMAILED_TYPES
            and notification.read_at is None
            # No preference row means the documented defaults, email on.
            and (preferences is None or preferences.email_enabled)
            and user is not None
            and user.is_active
            and bool(user.email)
            and provider.accepts_recipient(user.email)
        )
