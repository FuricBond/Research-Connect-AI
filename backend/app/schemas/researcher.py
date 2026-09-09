from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.research_profile import AcademicStatus


# ── External Identifiers Validation & Schemas ─────────────────────────────────

ORCID_REGEX = re.compile(r"^(\d{4}-\d{4}-\d{4}-[\dX]{4})$")
OPENALEX_ID_REGEX = re.compile(r"^[A-Za-z]?\d+$")


def normalize_orcid(v: str | None) -> str | None:
    """Normalize and validate an ORCID identifier (stripping URL prefixes)."""
    if not v:
        return None
    cleaned = v.strip()
    # Strip protocol and domain if supplied as URL
    for prefix in ("https://orcid.org/", "http://orcid.org/", "orcid.org/"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    # Uppercase terminal 'x'
    if cleaned.endswith("x"):
        cleaned = cleaned[:-1] + "X"
    if not ORCID_REGEX.match(cleaned):
        raise ValueError(
            f"Invalid ORCID identifier format: '{v}'. Expected 16-character format '0000-0002-1825-0097' or valid ORCID URL."
        )
    return cleaned


def normalize_openalex_id(v: str | None) -> str | None:
    """Normalize and validate an OpenAlex Author/Researcher ID."""
    if not v:
        return None
    cleaned = v.strip()
    for prefix in ("https://openalex.org/", "http://openalex.org/", "openalex.org/"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    # Ensure compact format e.g. A5048491430
    if not cleaned.upper().startswith("A") and cleaned.isdigit():
        cleaned = f"A{cleaned}"
    cleaned = cleaned.upper()
    if not OPENALEX_ID_REGEX.match(cleaned):
        raise ValueError(
            f"Invalid OpenAlex author ID: '{v}'. Expected format 'A5048491430' or URL."
        )
    return cleaned


class ExternalIdentifiersSchema(BaseModel):
    """Normalized container for external scholarly identity systems."""
    model_config = ConfigDict(from_attributes=True)

    orcid: str | None = None
    openalex_id: str | None = None
    google_scholar_id: str | None = None
    scopus_id: str | None = None
    semantic_scholar_id: str | None = None

    @field_validator("orcid", mode="before")
    @classmethod
    def validate_orcid_field(cls, v: Any) -> str | None:
        if v is None:
            return None
        return normalize_orcid(str(v))

    @field_validator("openalex_id", mode="before")
    @classmethod
    def validate_openalex_field(cls, v: Any) -> str | None:
        if v is None:
            return None
        return normalize_openalex_id(str(v))


# ── Institution & Publication Summary Schemas ─────────────────────────────────


class InstitutionSummarySchema(BaseModel):
    """Canonical institution summary representation."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    ror: str | None = None
    country_code: str | None = None
    institution_type: str | None = None
    homepage_url: str | None = None


class ResearcherWorkSummarySchema(BaseModel):
    """Summary of scholarly publication authored by the researcher."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    doi: str | None = None
    publication_year: int | None = None
    work_type: str | None = None
    author_position: str | None = None
    is_corresponding: bool = False
    cited_by_count: int = 0


# ── Profile Completeness Schema ───────────────────────────────────────────────


class CompletenessLevel(str, Enum):
    INCOMPLETE = "INCOMPLETE"
    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    COMPLETE = "COMPLETE"


class ProfileCompletenessSchema(BaseModel):
    """
    Deterministic profile completeness audit.
    Metadata only — not used for recommendation scoring.
    """
    model_config = ConfigDict(from_attributes=True)

    score: float = Field(ge=0.0, le=1.0, description="Completeness ratio between 0.0 and 1.0")
    percentage: int = Field(ge=0, le=100, description="Completeness percentage 0 to 100")
    level: CompletenessLevel = CompletenessLevel.INCOMPLETE
    is_complete: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    field_breakdown: dict[str, bool] = Field(default_factory=dict)


# ── Researcher Profile CRUD Schemas ───────────────────────────────────────────


class ResearcherProfileCreate(BaseModel):
    """Payload to create or register a canonical researcher profile."""
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=255, description="Researcher full display name")
    email: str = Field(min_length=3, max_length=255, description="Contact/account email address")
    institution_name: str | None = Field(default=None, max_length=255)
    institution_id: uuid.UUID | None = None
    department: str | None = Field(default=None, max_length=255)
    academic_status: AcademicStatus = AcademicStatus.UNKNOWN
    academic_level: str | None = Field(default=None, max_length=100)
    bio: str | None = None
    orcid: str | None = None
    openalex_id: str | None = None
    external_identifiers: dict[str, Any] = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    target_opportunity_types: list[str] = Field(default_factory=list)

    @field_validator("orcid", mode="before")
    @classmethod
    def clean_orcid(cls, v: Any) -> str | None:
        return normalize_orcid(v) if v else None

    @field_validator("openalex_id", mode="before")
    @classmethod
    def clean_openalex_id(cls, v: Any) -> str | None:
        return normalize_openalex_id(v) if v else None


class ResearcherProfileUpdate(BaseModel):
    """Payload to partially update a researcher profile."""
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    institution_name: str | None = Field(default=None, max_length=255)
    institution_id: uuid.UUID | None = None
    department: str | None = Field(default=None, max_length=255)
    academic_status: AcademicStatus | None = None
    academic_level: str | None = Field(default=None, max_length=100)
    bio: str | None = None
    orcid: str | None = None
    openalex_id: str | None = None
    external_identifiers: dict[str, Any] | None = None
    keywords: list[str] | None = None
    target_opportunity_types: list[str] | None = None

    @field_validator("orcid", mode="before")
    @classmethod
    def clean_orcid(cls, v: Any) -> str | None:
        return normalize_orcid(v) if v else None

    @field_validator("openalex_id", mode="before")
    @classmethod
    def clean_openalex_id(cls, v: Any) -> str | None:
        return normalize_openalex_id(v) if v else None


class ResearcherProfileRead(BaseModel):
    """Authoritative API response schema for a canonical researcher profile."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str | None = None
    academic_status: AcademicStatus
    academic_level: str | None = None
    department: str | None = None
    bio: str | None = None
    institution_id: uuid.UUID | None = None
    institution_name: str | None = None
    institution: InstitutionSummarySchema | None = None
    canonical_researcher_id: uuid.UUID | None = None
    orcid: str | None = None
    openalex_id: str | None = None
    external_identifiers: dict[str, Any] = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    target_opportunity_types: list[str] = Field(default_factory=list)
    completeness: ProfileCompletenessSchema
    works_count: int = 0
    created_at: datetime
    updated_at: datetime
