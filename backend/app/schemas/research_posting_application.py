"""Phase 5.11 — Research internship / RA opening and application schemas."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.research_posting_application import (
    ApplicationStatus,
    CommitmentType,
    CompensationType,
)

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

COMPENSATION_PERIODS = frozenset({"HOUR", "WEEK", "MONTH", "YEAR", "TOTAL"})


class OpeningTermsSchema(BaseModel):
    """
    The structured terms of a funded appointment (Phase 5.11).

    Separated from the posting's descriptive fields so a client can render "the offer" as a
    distinct block, and so `UNPAID` is always an explicit statement rather than a blank field
    the reader has to interpret.
    """

    model_config = ConfigDict(from_attributes=True)

    compensation_type: CompensationType = CompensationType.UNSPECIFIED
    compensation_amount: float | None = None
    compensation_currency: str | None = None
    compensation_period: str | None = None
    commitment_type: CommitmentType | None = None
    hours_per_week: int | None = None
    duration_months: int | None = None
    eligibility_requirements: str | None = None
    accepts_applications: bool = False
    is_structured_opening: bool = Field(
        default=False,
        description="True when the posting category is an internship, assistantship or post-doc",
    )


class OpeningTermsUpdate(BaseModel):
    """Opening terms supplied when authoring or editing a posting."""

    model_config = ConfigDict(extra="forbid")

    compensation_type: CompensationType | None = None
    compensation_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    compensation_currency: str | None = Field(default=None, min_length=3, max_length=3)
    compensation_period: str | None = None
    commitment_type: CommitmentType | None = None
    hours_per_week: int | None = Field(default=None, ge=1, le=80)
    duration_months: int | None = Field(default=None, ge=1, le=120)
    eligibility_requirements: str | None = None
    accepts_applications: bool | None = None

    @field_validator("compensation_currency")
    @classmethod
    def normalize_currency(cls, v: str | None) -> str | None:
        if v is None:
            return None
        code = v.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("compensation_currency must be a 3-letter ISO 4217 code.")
        return code

    @field_validator("compensation_period")
    @classmethod
    def normalize_period(cls, v: str | None) -> str | None:
        if v is None:
            return None
        period = v.strip().upper()
        if period not in COMPENSATION_PERIODS:
            raise ValueError(
                f"compensation_period must be one of: {', '.join(sorted(COMPENSATION_PERIODS))}."
            )
        return period


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cover_note: str | None = Field(default=None, max_length=5000)
    contact_email: str | None = Field(default=None, max_length=255)
    portfolio_url: str | None = Field(default=None, max_length=2000)

    @field_validator("cover_note", "portfolio_url")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        email = v.strip().lower()
        if not email:
            return None
        if not _EMAIL_PATTERN.match(email):
            raise ValueError("contact_email must be a valid email address.")
        return email


class ApplicationDecision(BaseModel):
    """A posting author's review decision, or an applicant's response to an offer."""

    model_config = ConfigDict(extra="forbid")

    target_status: ApplicationStatus
    decision_reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Shared with the applicant",
    )
    reviewer_note: str | None = Field(
        default=None,
        max_length=2000,
        description="Author's private note; never returned to the applicant",
    )


class ApplicantSummarySchema(BaseModel):
    """The applicant's identity, as shown to the posting's author."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    full_name: str | None = None
    institution: str | None = None
    department: str | None = None
    academic_status: str | None = None


class ApplicationStatusEventSchema(BaseModel):
    """One entry from the append-only status history."""

    from_status: str | None = None
    to_status: str
    actor_role: str
    reason: str | None = None
    at: datetime


class ApplicationRead(BaseModel):
    """
    An application.

    `reviewer_note` is populated only when the posting's author is reading; it is omitted for
    the applicant so a candid internal assessment cannot leak as feedback.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    posting_id: uuid.UUID
    posting_title: str | None = None
    applicant: ApplicantSummarySchema
    status: ApplicationStatus
    cover_note: str | None = None
    contact_email: str | None = None
    portfolio_url: str | None = None
    decision_reason: str | None = None
    reviewer_note: str | None = None
    status_history: list[ApplicationStatusEventSchema] = Field(default_factory=list)
    submitted_at: datetime
    decided_at: datetime | None = None
    withdrawn_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    allowed_transitions: list[ApplicationStatus] = Field(
        default_factory=list,
        description="Transitions available to the researcher making this request",
    )
    is_applicant: bool = False
    is_posting_author: bool = False


class ApplicationListResponse(BaseModel):
    applications: list[ApplicationRead]
    total: int
    limit: int
    offset: int


class ApplicationSummaryResponse(BaseModel):
    """Counts across an author's or applicant's applications, grouped by status."""

    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    active: int = Field(
        default=0,
        description="Applications still in play, i.e. not withdrawn, rejected or declined",
    )
