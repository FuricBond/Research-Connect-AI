from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationDeliveryAttemptModel,
    NotificationModel,
    NotificationPreferenceModel,
    OffsetUnit,
    ReminderRuleModel,
)
from app.models.research_profile import ResearchProfileModel
from app.schemas.notification import (
    NotificationPreferenceUpdate,
    ReminderRuleCreate,
    ReminderRuleUpdate,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Core service managing researcher notification preferences, reminder rules,
    in-app notification delivery states, and delivery attempt audit logs.
    """

    # ------------------------------------------------------------------------
    # Notification Preferences
    # ------------------------------------------------------------------------

    @classmethod
    def get_or_create_preferences(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> NotificationPreferenceModel:
        """
        Retrieves the notification preferences for a researcher profile.
        Bootstraps default preferences (all enabled) if not yet established.
        """
        stmt = select(NotificationPreferenceModel).where(
            NotificationPreferenceModel.profile_id == profile_id
        )
        prefs = db.execute(stmt).scalars().first()
        if prefs:
            return prefs

        # Ensure profile exists
        profile = db.get(ResearchProfileModel, profile_id)
        if not profile:
            raise ValueError(f"Research profile with ID '{profile_id}' does not exist.")

        prefs = NotificationPreferenceModel(
            profile_id=profile_id,
            email_enabled=True,
            in_app_enabled=True,
            deadline_reminders_enabled=True,
            extension_notifications_enabled=True,
            conflict_notifications_enabled=True,
            calendar_event_reminders_enabled=True,
        )
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
        return prefs

    @classmethod
    def update_preferences(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        payload: NotificationPreferenceUpdate,
    ) -> NotificationPreferenceModel:
        """Updates notification preferences for a researcher."""
        prefs = cls.get_or_create_preferences(db, profile_id)

        update_data = payload.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            if hasattr(prefs, key) and val is not None:
                setattr(prefs, key, val)

        db.commit()
        db.refresh(prefs)
        return prefs

    # ------------------------------------------------------------------------
    # Reminder Rules Management
    # ------------------------------------------------------------------------

    @classmethod
    def list_reminder_rules(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        is_active: bool | None = None,
    ) -> list[ReminderRuleModel]:
        """Lists configured reminder rules for a researcher profile."""
        stmt = select(ReminderRuleModel).where(
            ReminderRuleModel.profile_id == profile_id
        )
        if is_active is not None:
            stmt = stmt.where(ReminderRuleModel.is_active == is_active)

        stmt = stmt.order_by(
            ReminderRuleModel.offset_unit.asc(),
            ReminderRuleModel.offset_amount.desc(),
        )
        return list(db.execute(stmt).scalars().all())

    @classmethod
    def bootstrap_default_reminder_rules(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> list[ReminderRuleModel]:
        """
        Bootstraps standard academic deadline reminder rules if none exist:
        - 14 days before (IN_APP)
        - 7 days before (IN_APP)
        - 3 days before (IN_APP)
        - 24 hours before (IN_APP)
        """
        existing = cls.list_reminder_rules(db, profile_id)
        if existing:
            return existing

        defaults = [
            ReminderRuleCreate(offset_amount=14, offset_unit=OffsetUnit.DAYS, delivery_channel=DeliveryChannel.IN_APP),
            ReminderRuleCreate(offset_amount=7, offset_unit=OffsetUnit.DAYS, delivery_channel=DeliveryChannel.IN_APP),
            ReminderRuleCreate(offset_amount=3, offset_unit=OffsetUnit.DAYS, delivery_channel=DeliveryChannel.IN_APP),
            ReminderRuleCreate(offset_amount=24, offset_unit=OffsetUnit.HOURS, delivery_channel=DeliveryChannel.IN_APP),
        ]

        rules = []
        for d in defaults:
            rule = ReminderRuleModel(
                profile_id=profile_id,
                event_type=d.event_type,
                offset_amount=d.offset_amount,
                offset_unit=d.offset_unit.value,
                delivery_channel=d.delivery_channel.value,
                is_active=True,
            )
            db.add(rule)
            rules.append(rule)

        db.commit()
        for r in rules:
            db.refresh(r)
        return rules

    @classmethod
    def create_reminder_rule(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        payload: ReminderRuleCreate,
    ) -> ReminderRuleModel:
        """Creates a new reminder rule for a researcher profile."""
        # Ensure profile exists
        profile = db.get(ResearchProfileModel, profile_id)
        if not profile:
            raise ValueError(f"Research profile with ID '{profile_id}' does not exist.")

        # Check for duplicate rule
        stmt = select(ReminderRuleModel).where(
            ReminderRuleModel.profile_id == profile_id,
            ReminderRuleModel.event_type == payload.event_type,
            ReminderRuleModel.offset_amount == payload.offset_amount,
            ReminderRuleModel.offset_unit == payload.offset_unit.value,
            ReminderRuleModel.delivery_channel == payload.delivery_channel.value,
        )
        existing = db.execute(stmt).scalars().first()
        if existing:
            if not existing.is_active and payload.is_active:
                existing.is_active = True
                db.commit()
                db.refresh(existing)
                return existing
            return existing

        rule = ReminderRuleModel(
            profile_id=profile_id,
            event_type=payload.event_type,
            offset_amount=payload.offset_amount,
            offset_unit=payload.offset_unit.value,
            delivery_channel=payload.delivery_channel.value,
            is_active=payload.is_active,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    @classmethod
    def get_reminder_rule(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        rule_id: uuid.UUID,
    ) -> ReminderRuleModel:
        """Retrieves a reminder rule, validating researcher ownership."""
        rule = db.get(ReminderRuleModel, rule_id)
        if not rule:
            raise ValueError(f"Reminder rule '{rule_id}' not found.")
        if rule.profile_id != profile_id:
            raise PermissionError("Access denied: reminder rule belongs to another researcher.")
        return rule

    @classmethod
    def update_reminder_rule(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        rule_id: uuid.UUID,
        payload: ReminderRuleUpdate,
    ) -> ReminderRuleModel:
        """Updates a reminder rule with ownership validation."""
        rule = cls.get_reminder_rule(db, profile_id, rule_id)

        update_data = payload.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            if val is not None:
                if key in ("offset_unit", "delivery_channel"):
                    setattr(rule, key, val.value if hasattr(val, "value") else str(val))
                else:
                    setattr(rule, key, val)

        db.commit()
        db.refresh(rule)
        return rule

    @classmethod
    def delete_reminder_rule(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        rule_id: uuid.UUID,
    ) -> None:
        """Deletes a reminder rule with ownership validation."""
        rule = cls.get_reminder_rule(db, profile_id, rule_id)
        db.delete(rule)
        db.commit()

    # ------------------------------------------------------------------------
    # Notifications Retrieval and Read State
    # ------------------------------------------------------------------------

    @classmethod
    def list_notifications(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        unread_only: bool = False,
        notification_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[NotificationModel], int, int]:
        """
        Lists notifications for a researcher profile.
        Returns (notifications, total_matching, unread_count).
        """
        base_stmt = select(NotificationModel).where(
            NotificationModel.profile_id == profile_id
        )

        # Unread total across all types
        unread_stmt = select(func.count(NotificationModel.id)).where(
            NotificationModel.profile_id == profile_id,
            NotificationModel.read_at.is_(None),
        )
        unread_count = db.execute(unread_stmt).scalar() or 0

        if unread_only:
            base_stmt = base_stmt.where(NotificationModel.read_at.is_(None))
        if notification_type:
            base_stmt = base_stmt.where(NotificationModel.notification_type == notification_type)

        # Count total matching current filter
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_matching = db.execute(count_stmt).scalar() or 0

        # Retrieve items
        query = (
            base_stmt.order_by(
                NotificationModel.created_at.desc(),
                NotificationModel.scheduled_for.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        notifications = list(db.execute(query).scalars().all())

        return notifications, total_matching, unread_count

    @classmethod
    def get_unread_count(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> int:
        """Returns total unread notifications count for a profile."""
        stmt = select(func.count(NotificationModel.id)).where(
            NotificationModel.profile_id == profile_id,
            NotificationModel.read_at.is_(None),
        )
        return db.execute(stmt).scalar() or 0

    @classmethod
    def mark_as_read(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> NotificationModel:
        """Marks a single notification as read, enforcing ownership."""
        notification = db.get(NotificationModel, notification_id)
        if not notification:
            raise ValueError(f"Notification '{notification_id}' not found.")
        if notification.profile_id != profile_id:
            raise PermissionError("Access denied: notification belongs to another researcher.")

        if notification.read_at is None:
            notification.read_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(notification)

        return notification

    @classmethod
    def mark_all_as_read(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> int:
        """Marks all unread notifications as read for a researcher profile."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(NotificationModel)
            .where(
                NotificationModel.profile_id == profile_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=now, updated_at=now)
        )
        result = db.execute(stmt)
        db.commit()
        return result.rowcount

    # ------------------------------------------------------------------------
    # Delivery Attempt Logging
    # ------------------------------------------------------------------------

    @classmethod
    def record_delivery_attempt(
        cls,
        db: Session,
        notification_id: uuid.UUID,
        channel: str,
        status: str,
        attempt_number: int = 1,
        provider_reference: str | None = None,
        error_message: str | None = None,
        auto_commit: bool = True,
    ) -> NotificationDeliveryAttemptModel:
        """Records an audit log entry for a delivery attempt."""
        status_val = status.value if hasattr(status, "value") else status
        channel_val = channel.value if hasattr(channel, "value") else channel

        attempt = NotificationDeliveryAttemptModel(
            id=uuid.uuid4(),
            notification_id=notification_id,
            channel=channel_val,
            status=status_val,
            attempt_number=attempt_number,
            provider_reference=provider_reference,
            error_message=error_message,
        )
        db.add(attempt)

        notif = db.get(NotificationModel, notification_id)
        if notif:
            notif_status = DeliveryStatus.DELIVERED.value if status_val in ("SUCCESS", DeliveryStatus.DELIVERED.value) else status_val
            if notif_status in [s.value for s in DeliveryStatus]:
                notif.delivery_status = notif_status
            if notif_status == DeliveryStatus.DELIVERED.value:
                notif.delivered_at = datetime.now(timezone.utc)

        if auto_commit:
            db.commit()
            db.refresh(attempt)
        return attempt
