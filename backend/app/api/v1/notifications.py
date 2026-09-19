from __future__ import annotations

from datetime import datetime
import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.schemas.notification import (
    NotificationListResponse,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    NotificationUnreadCountResponse,
    ReminderRuleCreate,
    ReminderRuleListResponse,
    ReminderRuleRead,
    ReminderRuleUpdate,
    ReminderRunSummaryResponse,
)
from app.services.notification_service import NotificationService
from app.services.reminder_scheduler_service import ReminderSchedulerService
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def resolve_current_user(
    db: Session,
    x_user_id: uuid.UUID | None,
) -> UserModel:
    """
    Resolves the authenticated user from the X-User-ID header or falls back to
    the primary active user in developer mode.
    """
    if x_user_id is not None:
        user = db.get(UserModel, x_user_id)
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{x_user_id}' not found.",
        )

    fallback_user = db.execute(
        select(UserModel).order_by(UserModel.created_at.asc())
    ).scalars().first()
    if fallback_user is not None:
        return fallback_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: Please provide an 'X-User-ID' header.",
    )


def resolve_profile_for_user(
    db: Session,
    user: UserModel,
) -> ResearchProfileModel:
    """Resolves or establishes a researcher profile for the user."""
    stmt = select(ResearchProfileModel).where(ResearchProfileModel.user_id == user.id)
    profile = db.execute(stmt).scalars().first()
    if profile:
        return profile

    # Auto-bootstrap minimal profile
    profile = ResearchProfileModel(
        user_id=user.id,
        academic_status="RESEARCHER",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


# ----------------------------------------------------------------------------
# Notifications Endpoints
# ----------------------------------------------------------------------------

@router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List notifications for current user",
)
def list_notifications(
    unread_only: bool = Query(default=False, description="Filter only unread notifications"),
    notification_type: str | None = Query(default=None, description="Filter by notification type"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    items, total, unread = NotificationService.list_notifications(
        db=db,
        profile_id=profile.id,
        unread_only=unread_only,
        notification_type=notification_type,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        notifications=[NotificationRead.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
    )


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unread notifications count",
)
def get_unread_count(
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationUnreadCountResponse:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    count = NotificationService.get_unread_count(db, profile.id)
    return NotificationUnreadCountResponse(
        profile_id=profile.id,
        unread_count=count,
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    status_code=status.HTTP_200_OK,
    summary="Mark single notification as read",
)
def mark_notification_read(
    notification_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationRead:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    try:
        notif = NotificationService.mark_as_read(db, profile.id, notification_id)
        return NotificationRead.model_validate(notif)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Notification belongs to another researcher.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.post(
    "/read-all",
    response_model=dict[str, int],
    status_code=status.HTTP_200_OK,
    summary="Mark all notifications as read",
)
def mark_all_notifications_read(
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    count = NotificationService.mark_all_as_read(db, profile.id)
    return {"marked_read_count": count}


# ----------------------------------------------------------------------------
# Notification Preferences Endpoints
# ----------------------------------------------------------------------------

@router.get(
    "/preferences",
    response_model=NotificationPreferenceRead,
    status_code=status.HTTP_200_OK,
    summary="Get notification preferences",
)
def get_preferences(
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationPreferenceRead:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    prefs = NotificationService.get_or_create_preferences(db, profile.id)
    return NotificationPreferenceRead.model_validate(prefs)


@router.patch(
    "/preferences",
    response_model=NotificationPreferenceRead,
    status_code=status.HTTP_200_OK,
    summary="Update notification preferences",
)
def update_preferences(
    payload: NotificationPreferenceUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> NotificationPreferenceRead:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    prefs = NotificationService.update_preferences(db, profile.id, payload)
    return NotificationPreferenceRead.model_validate(prefs)


# ----------------------------------------------------------------------------
# Reminder Rules Endpoints
# ----------------------------------------------------------------------------

@router.get(
    "/rules",
    response_model=ReminderRuleListResponse,
    status_code=status.HTTP_200_OK,
    summary="List reminder rules",
)
def list_rules(
    is_active: bool | None = Query(default=None),
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ReminderRuleListResponse:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    rules = NotificationService.list_reminder_rules(db, profile.id, is_active=is_active)
    if not rules:
        rules = NotificationService.bootstrap_default_reminder_rules(db, profile.id)

    return ReminderRuleListResponse(
        rules=[ReminderRuleRead.model_validate(r) for r in rules],
        total=len(rules),
    )


@router.post(
    "/rules",
    response_model=ReminderRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create reminder rule",
)
def create_rule(
    payload: ReminderRuleCreate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ReminderRuleRead:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    rule = NotificationService.create_reminder_rule(db, profile.id, payload)
    return ReminderRuleRead.model_validate(rule)


@router.patch(
    "/rules/{rule_id}",
    response_model=ReminderRuleRead,
    status_code=status.HTTP_200_OK,
    summary="Update reminder rule",
)
def update_rule(
    rule_id: uuid.UUID,
    payload: ReminderRuleUpdate,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> ReminderRuleRead:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    try:
        rule = NotificationService.update_reminder_rule(db, profile.id, rule_id, payload)
        return ReminderRuleRead.model_validate(rule)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Reminder rule belongs to another researcher.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete reminder rule",
)
def delete_rule(
    rule_id: uuid.UUID,
    x_user_id: Annotated[uuid.UUID | None, Header(alias="X-User-ID")] = None,
    db: Session = Depends(get_db),
) -> Response:
    user = resolve_current_user(db, x_user_id)
    profile = resolve_profile_for_user(db, user)

    try:
        NotificationService.delete_reminder_rule(db, profile.id, rule_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Reminder rule belongs to another researcher.",
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )


# ----------------------------------------------------------------------------
# Scheduler Trigger Endpoint
# ----------------------------------------------------------------------------

@router.post(
    "/trigger-reminders",
    response_model=ReminderRunSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute scheduled reminder pass",
    description="Admin / worker trigger to discover and dispatch all due deadline reminders.",
)
def trigger_reminders(
    db: Session = Depends(get_db),
) -> ReminderRunSummaryResponse:
    summary = ReminderSchedulerService.run_scheduled_reminders(db)
    return ReminderRunSummaryResponse(
        discovered_reminders=summary.discovered_reminders,
        created_notifications=summary.created_notifications,
        delivered_notifications=summary.delivered_notifications,
        skipped_duplicates=summary.skipped_duplicates,
        cancelled_obsolete=summary.cancelled_obsolete,
        errors=summary.errors,
        executed_at=summary.executed_at,
    )
