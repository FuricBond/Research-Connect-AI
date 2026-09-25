"""
Phase 6 — Account registration, credential verification, and administration.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import burn_password_check, hash_password, verify_password
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.user import UserModel
from app.schemas.auth import (
    AdminUserListResponse,
    AdminUserRead,
    AdminUserUpdate,
    AuthenticatedUser,
    PlatformRole,
    RegisterRequest,
    SelfServiceRole,
)
from app.schemas.researcher import ResearcherProfileCreate
from app.services.researcher_profile_service import ResearcherProfileService

logger = logging.getLogger(__name__)


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class LastAdministratorError(Exception):
    pass


class AuthService:

    @classmethod
    def find_user_by_email(cls, db: Session, email: str) -> UserModel | None:
        return db.execute(
            select(UserModel).where(func.lower(UserModel.email) == email.strip().lower())
        ).scalars().first()

    @classmethod
    def register(cls, db: Session, payload: RegisterRequest) -> UserModel:
        """
        Creates an account and its researcher profile in one transaction. The chosen
        role is self-declared; `is_verified` stays false until an administrator confirms it.
        """
        if cls.find_user_by_email(db, payload.email) is not None:
            raise EmailAlreadyRegisteredError("An account with this email already exists.")

        user = UserModel(
            id=uuid.uuid4(),
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role=payload.role.value,
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        db.flush()

        profile_payload = ResearcherProfileCreate(
            full_name=payload.full_name,
            email=payload.email,
            institution_name=payload.institution_name,
            department=payload.department,
            academic_status=(
                AcademicStatus.FACULTY if payload.role == SelfServiceRole.FACULTY else AcademicStatus.UNKNOWN
            ),
        )
        try:
            ResearcherProfileService.create_profile(db, profile_payload, user_id=user.id)
        except Exception:
            db.rollback()
            raise
        db.refresh(user)
        logger.info("Registered account", extra={"registered_user_id": str(user.id), "role": user.role})
        return user

    @classmethod
    def authenticate(cls, db: Session, email: str, password: str) -> UserModel:
        user = cls.find_user_by_email(db, email)
        if user is None:
            burn_password_check(password)
            raise InvalidCredentialsError("Incorrect email or password.")
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Incorrect email or password.")
        if not user.is_active:
            raise InvalidCredentialsError("Account is deactivated.")
        return user

    @classmethod
    def build_authenticated_user(cls, db: Session, user: UserModel) -> AuthenticatedUser:
        profile_id = db.execute(
            select(ResearchProfileModel.id).where(ResearchProfileModel.user_id == user.id)
        ).scalar_one_or_none()
        return AuthenticatedUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=PlatformRole(user.role),
            is_active=user.is_active,
            is_verified=user.is_verified,
            profile_id=profile_id,
            created_at=user.created_at,
        )

    # ── Administration ──────────────────────────────────────────────────────

    @classmethod
    def list_users(
        cls,
        db: Session,
        role: PlatformRole | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminUserListResponse:
        stmt = select(UserModel)
        if role is not None:
            stmt = stmt.where(UserModel.role == role.value)
        if search:
            pattern = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                func.lower(UserModel.email).like(pattern) | func.lower(UserModel.full_name).like(pattern)
            )
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        users = db.execute(
            stmt.order_by(UserModel.created_at.asc(), UserModel.id.asc()).limit(limit).offset(offset)
        ).scalars().all()
        return AdminUserListResponse(
            users=[AdminUserRead.model_validate(u) for u in users],
            total=total,
        )

    @classmethod
    def update_user(
        cls,
        db: Session,
        acting_admin: UserModel,
        user_id: uuid.UUID,
        payload: AdminUserUpdate,
    ) -> UserModel:
        user = db.get(UserModel, user_id)
        if user is None:
            raise LookupError(f"User '{user_id}' not found.")

        demotes_admin = (
            user.role == PlatformRole.ADMIN.value
            and (
                (payload.role is not None and payload.role != PlatformRole.ADMIN)
                or payload.is_active is False
            )
        )
        if demotes_admin:
            active_admins = db.execute(
                select(func.count()).select_from(UserModel).where(
                    UserModel.role == PlatformRole.ADMIN.value,
                    UserModel.is_active.is_(True),
                )
            ).scalar_one()
            if active_admins <= 1:
                raise LastAdministratorError("Cannot demote or deactivate the last active administrator.")

        if payload.role is not None:
            user.role = payload.role.value
        if payload.is_active is not None:
            user.is_active = payload.is_active
        if payload.is_verified is not None:
            user.is_verified = payload.is_verified
        db.commit()
        db.refresh(user)
        logger.info(
            "Administrator updated account",
            extra={
                "admin_user_id": str(acting_admin.id),
                "target_user_id": str(user.id),
                "changes": payload.model_dump(exclude_none=True, mode="json"),
            },
        )
        return user
