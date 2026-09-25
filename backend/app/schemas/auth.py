"""Phase 6 — Authentication, identity, and platform administration schemas."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import BCRYPT_MAX_PASSWORD_BYTES

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


class PlatformRole(str, Enum):
    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    ADMIN = "ADMIN"


class SelfServiceRole(str, Enum):
    """Roles a person may claim at registration. ADMIN is only granted by an administrator."""

    STUDENT = "STUDENT"
    FACULTY = "FACULTY"


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL_PATTERN.match(email):
        raise ValueError("Invalid email address.")
    return email


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    full_name: str = Field(min_length=1, max_length=255)
    role: SelfServiceRole = SelfServiceRole.STUDENT
    institution_name: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("Full name must not be blank.")
        return name

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes.")
        if v.strip() != v or not v.strip():
            raise ValueError("Password must not start or end with whitespace.")
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class AuthenticatedUser(BaseModel):
    """The caller's own account, as returned by /auth/me and on login."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: PlatformRole
    is_active: bool
    is_verified: bool
    profile_id: uuid.UUID | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthenticatedUser


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: PlatformRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRead]
    total: int


class AdminUserUpdate(BaseModel):
    """Administrative account changes. Omitted fields are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    role: PlatformRole | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
