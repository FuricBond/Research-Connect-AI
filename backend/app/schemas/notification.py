from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationType,
    OffsetUnit,
)


# ----------------------------------------------------------------------------
# Notification Preferences Schemas
# ----------------------------------------------------------------------------

class NotificationPreferenceBase(BaseModel):
    email_enabled: bool = True
    in_app_enabled: bool = True
    deadline_reminders_enabled: bool = True
    extension_notifications_enabled: bool = True
    conflict_notifications_enabled: bool = True
    calendar_event_reminders_enabled: bool = True


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    in_app_enabled: bool | None = None
    deadline_reminders_enabled: bool | None = None
    extension_notifications_enabled: bool | None = None
    conflict_notifications_enabled: bool | None = None
    calendar_event_reminders_enabled: bool | None = None


class NotificationPreferenceRead(NotificationPreferenceBase):
    id: uuid.UUID
    profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------------
# Reminder Rule Schemas
# ----------------------------------------------------------------------------

class ReminderRuleCreate(BaseModel):
    event_type: str | None = Field(
        default=None,
        description="Target milestone type (e.g. OPPORTUNITY_SUBMISSION) or None for all milestones",
    )
    offset_amount: int = Field(
        gt=0,
        description="Duration offset amount (e.g. 14, 7, 3, 24)",
    )
    offset_unit: OffsetUnit = Field(
        default=OffsetUnit.DAYS,
        description="Unit of offset: DAYS, HOURS, MINUTES",
    )
    delivery_channel: DeliveryChannel = Field(
        default=DeliveryChannel.IN_APP,
        description="Delivery channel: IN_APP, EMAIL, PUSH",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this rule is active",
    )


class ReminderRuleUpdate(BaseModel):
    event_type: str | None = None
    offset_amount: int | None = Field(default=None, gt=0)
    offset_unit: OffsetUnit | None = None
    delivery_channel: DeliveryChannel | None = None
    is_active: bool | None = None


class ReminderRuleRead(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    event_type: str | None
    offset_amount: int
    offset_unit: str
    delivery_channel: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReminderRuleListResponse(BaseModel):
    rules: list[ReminderRuleRead]
    total: int


# ----------------------------------------------------------------------------
# Notification Schemas
# ----------------------------------------------------------------------------

class NotificationRead(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID
    notification_type: str
    title: str
    body: str
    source_type: str
    source_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    calendar_event_id: uuid.UUID | None
    submission_id: uuid.UUID | None
    deadline_type: str | None
    scheduled_for: datetime
    delivered_at: datetime | None
    read_at: datetime | None
    delivery_status: str
    delivery_channel: str
    deduplication_key: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    notifications: list[NotificationRead]
    total: int
    unread_count: int


class NotificationUnreadCountResponse(BaseModel):
    profile_id: uuid.UUID
    unread_count: int


# ----------------------------------------------------------------------------
# Scheduler Run Summary Schemas
# ----------------------------------------------------------------------------

class ReminderRunSummaryResponse(BaseModel):
    discovered_reminders: int
    created_notifications: int
    delivered_notifications: int
    skipped_duplicates: int
    cancelled_obsolete: int
    errors: list[str] = Field(default_factory=list)
    executed_at: datetime
