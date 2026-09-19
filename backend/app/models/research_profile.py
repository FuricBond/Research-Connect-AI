from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_knowledge import InstitutionModel, ResearcherModel
    from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
    from app.models.recommendation_history import ResearcherRecommendationSnapshotModel
    from app.models.researcher_interaction import ResearcherInteractionModel
    from app.models.user import UserModel


class AcademicStatus(str, Enum):
    """Normalized academic career stage / status."""

    UNDERGRADUATE = "UNDERGRADUATE"
    POSTGRADUATE = "POSTGRADUATE"
    PHD = "PHD"
    POSTDOC = "POSTDOC"
    FACULTY = "FACULTY"
    RESEARCHER = "RESEARCHER"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ResearchProfileModel(Base, TimestampMixin):
    """
    Canonical researcher profile associated 1:1 with a User.
    Bridges the platform identity to canonical academic knowledge entities (Institution, Researcher).
    """

    __tablename__ = "research_profiles"
    __table_args__ = (
        Index("idx_research_profiles_orcid", "orcid"),
        Index("idx_research_profiles_openalex_id", "openalex_id"),
        Index("idx_research_profiles_canonical_researcher", "canonical_researcher_id"),
        Index("idx_research_profiles_institution_id", "institution_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Institution affiliation: canonical link + fallback text
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("institutions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    institution: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Fallback or raw institution name string",
    )
    department: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Academic career status
    academic_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default="UNKNOWN",
        server_default="UNKNOWN",
    )
    academic_level: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Legacy / detailed academic level label",
    )

    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Canonical researcher knowledge link (OpenAlex / Crossref author record)
    canonical_researcher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("researchers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Normalized external identifiers
    orcid: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Normalized ORCID identifier, e.g. '0000-0003-1613-5981'",
    )
    openalex_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Compact OpenAlex author ID, e.g. 'A5048491430'",
    )
    external_identifiers: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Dictionary of additional external identifiers (Google Scholar, Scopus, etc.)",
    )

    # Keywords & Interests
    keywords: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )
    target_opportunity_types: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )

    # Relationships
    user: Mapped["UserModel"] = relationship(
        back_populates="research_profile",
    )
    institution_rel: Mapped[Optional["InstitutionModel"]] = relationship(
        foreign_keys=[institution_id],
    )
    canonical_researcher: Mapped[Optional["ResearcherModel"]] = relationship(
        foreign_keys=[canonical_researcher_id],
    )
    recommendation_feedback: Mapped[list["ResearcherRecommendationFeedbackModel"]] = relationship(
        back_populates="researcher_profile",
        cascade="all, delete-orphan",
    )
    recommendation_snapshots: Mapped[list["ResearcherRecommendationSnapshotModel"]] = relationship(
        back_populates="researcher_profile",
        cascade="all, delete-orphan",
    )
    interactions: Mapped[list["ResearcherInteractionModel"]] = relationship(
        back_populates="researcher_profile",
        cascade="all, delete-orphan",
    )

