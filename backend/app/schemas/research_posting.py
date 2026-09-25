"""Phase 5.10 — Faculty research posting schemas."""
from __future__ import annotations

from datetime import date, datetime, timezone
import re
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.research_posting import PostingStatus, PostingType, PostingWorkMode
from app.schemas.research_posting_application import OpeningTermsSchema, OpeningTermsUpdate

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_SKILLS = 25
MAX_TOPICS = 20


def _strip_optional_text(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


def _normalize_country_code(value: str | None) -> str | None:
    if value is None:
        return None
    code = value.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code.")
    return code


def _normalize_contact_email(value: str | None) -> str | None:
    if value is None:
        return None
    email = value.strip().lower()
    if not email:
        return None
    if not _EMAIL_PATTERN.match(email):
        raise ValueError("contact_email must be a valid email address.")
    return email


def _clean_skills(values: Any) -> list[str]:
    """Trims, de-duplicates case-insensitively, and preserves the author's ordering."""
    if not values:
        return []
    if not isinstance(values, (list, tuple)):
        raise ValueError("required_skills must be a list of strings.")
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        skill = str(raw).strip()
        if not skill:
            continue
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(skill)
    if len(cleaned) > MAX_SKILLS:
        raise ValueError(f"At most {MAX_SKILLS} required skills may be listed.")
    return cleaned


class ResearchPostingAuthorSchema(BaseModel):
    """The public identity of a posting's author."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    full_name: str | None = None
    institution: str | None = None
    department: str | None = None
    academic_status: str | None = None


class PostingTopicSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: uuid.UUID
    name: str | None = None
    slug: str | None = None
    is_primary: bool = False
    confidence_score: float = 1.0


class ResearchPostingBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=5, max_length=300)
    posting_type: PostingType
    summary: str | None = Field(default=None, max_length=500)
    description: str = Field(min_length=20)
    required_skills: list[str] = Field(default_factory=list)
    preferred_qualifications: str | None = None
    institution: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    work_mode: PostingWorkMode = PostingWorkMode.ONSITE
    positions_available: int = Field(default=1, ge=1, le=100)
    application_deadline: datetime | None = None
    expected_start_date: date | None = None
    expected_end_date: date | None = None
    contact_email: str | None = Field(default=None, max_length=255)
    external_url: str | None = None

    @field_validator("title", "summary", "preferred_qualifications", "description")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return _strip_optional_text(v)

    @field_validator("required_skills", mode="before")
    @classmethod
    def clean_skills(cls, v: Any) -> list[str]:
        return _clean_skills(v)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str | None) -> str | None:
        return _normalize_country_code(v)

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return _normalize_contact_email(v)

    @model_validator(mode="after")
    def validate_date_ordering(self) -> "ResearchPostingBase":
        if (
            self.expected_start_date is not None
            and self.expected_end_date is not None
            and self.expected_end_date < self.expected_start_date
        ):
            raise ValueError("expected_end_date must not precede expected_start_date.")
        return self


class ResearchPostingCreate(ResearchPostingBase):
    """
    Payload to author a posting.

    A posting is always created as a DRAFT; publishing is an explicit, separately authorized
    lifecycle transition rather than a field the client can set on creation.
    """

    topic_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_TOPICS)
    opening_terms: OpeningTermsUpdate | None = Field(
        default=None,
        description=(
            "Phase 5.11 appointment terms. Meaningful for internships, assistantships and "
            "post-docs; ignored for supervisor-led categories."
        ),
    )

    @field_validator("application_deadline")
    @classmethod
    def deadline_in_future(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        deadline = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if deadline <= datetime.now(timezone.utc):
            raise ValueError("application_deadline must be in the future.")
        return deadline


class ResearchPostingUpdate(BaseModel):
    """Partial update. Status is changed only through the transition endpoint."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=5, max_length=300)
    posting_type: PostingType | None = None
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, min_length=20)
    required_skills: list[str] | None = None
    preferred_qualifications: str | None = None
    institution: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    work_mode: PostingWorkMode | None = None
    positions_available: int | None = Field(default=None, ge=1, le=100)
    application_deadline: datetime | None = None
    expected_start_date: date | None = None
    expected_end_date: date | None = None
    contact_email: str | None = Field(default=None, max_length=255)
    external_url: str | None = None
    topic_ids: list[uuid.UUID] | None = Field(default=None, max_length=MAX_TOPICS)
    opening_terms: OpeningTermsUpdate | None = None

    @field_validator("title", "summary", "preferred_qualifications", "description")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return _strip_optional_text(v)

    @field_validator("required_skills", mode="before")
    @classmethod
    def clean_skills(cls, v: Any) -> list[str] | None:
        return None if v is None else _clean_skills(v)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str | None) -> str | None:
        return _normalize_country_code(v)

    @field_validator("contact_email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return _normalize_contact_email(v)

    @model_validator(mode="after")
    def validate_date_ordering(self) -> "ResearchPostingUpdate":
        if (
            self.expected_start_date is not None
            and self.expected_end_date is not None
            and self.expected_end_date < self.expected_start_date
        ):
            raise ValueError("expected_end_date must not precede expected_start_date.")
        return self


class PostingStatusTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: PostingStatus
    note: str | None = Field(default=None, max_length=1000)


class ResearchPostingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author: ResearchPostingAuthorSchema
    title: str
    posting_type: PostingType
    status: PostingStatus
    summary: str | None = None
    description: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_qualifications: str | None = None
    institution: str | None = None
    department: str | None = None
    location: str | None = None
    country: str | None = None
    work_mode: PostingWorkMode
    positions_available: int
    application_deadline: datetime | None = None
    expected_start_date: date | None = None
    expected_end_date: date | None = None
    contact_email: str | None = None
    external_url: str | None = None
    topics: list[PostingTopicSchema] = Field(default_factory=list)
    opening_terms: OpeningTermsSchema
    application_count: int = 0
    published_at: datetime | None = None
    closed_at: datetime | None = None
    archived_at: datetime | None = None
    status_note: str | None = None
    created_at: datetime
    updated_at: datetime

    # Derived, computed server-side so every client agrees on them.
    is_accepting_applications: bool = Field(
        default=False,
        description="True when the posting is OPEN and its application deadline has not passed",
    )
    days_until_deadline: int | None = Field(
        default=None,
        description="Whole days remaining until the application deadline; negative if passed",
    )
    allowed_transitions: list[PostingStatus] = Field(
        default_factory=list,
        description="Lifecycle states this posting may move to next",
    )
    is_owner: bool = Field(
        default=False,
        description="True when the requesting researcher authored this posting",
    )
    viewer_application_id: uuid.UUID | None = Field(
        default=None,
        description="The requesting researcher's own application to this posting, if any",
    )
    viewer_application_status: str | None = Field(
        default=None,
        description="Status of the requesting researcher's own application, if any",
    )


class ResearchPostingListResponse(BaseModel):
    postings: list[ResearchPostingRead]
    total: int
    limit: int
    offset: int


class PostingSummaryResponse(BaseModel):
    """Counts for an author's own postings, grouped by lifecycle state and type."""

    author_profile_id: uuid.UUID
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    total_applications: int = 0
    open_accepting_applications: int = 0
