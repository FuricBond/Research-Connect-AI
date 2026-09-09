from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_knowledge import ResearcherModel
    from app.models.research_profile import ResearchProfileModel
    from app.models.topic import TopicModel


class ResearcherInterestModel(Base, TimestampMixin):
    """
    Structured representation of researcher academic interest and expertise (Phase 3.2).
    
    Inferred deterministically from:
      - Canonical authored works (ResearchWorkAuthorModel -> ResearchWorkModel)
      - Canonical research topics and concept associations (ResearchWorkTopicModel -> TopicModel)
      - Publication recency, frequency, and citation metrics
      - Declared profile keywords (ResearchProfileModel.keywords)
    
    Strict Boundary:
      This is a descriptive intelligence layer representing what a researcher works on and
      has expertise in. It does NOT represent user preferences or recommendation scores.
    """

    __tablename__ = "researcher_interests"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "topic_name", name="uq_researcher_interests_profile_topic_name"
        ),
        Index("idx_researcher_interests_profile_id", "profile_id"),
        Index("idx_researcher_interests_researcher_id", "canonical_researcher_id"),
        Index("idx_researcher_interests_topic_id", "topic_id"),
        Index("idx_researcher_interests_topic_name", "topic_name"),
        Index("idx_researcher_interests_classification", "classification"),
        Index("idx_researcher_interests_strength", "strength"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to user platform profile (optional if analyzing canonical scholar directly)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Associated platform ResearchProfileModel ID if registered",
    )

    # Link to canonical OpenAlex/Crossref scholar entity
    canonical_researcher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("researchers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated canonical ResearcherModel ID from academic knowledge graph",
    )

    # Topic identity: canonical taxonomy reference + normalized string representations
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Canonical TopicModel ID if matched to taxonomy",
    )
    topic_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Normalized topic / concept display name",
    )
    topic_slug: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Normalized topic slug",
    )
    topic_category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Higher-level discipline or category if available",
    )

    # Deterministic scoring metrics: strictly in [0.0, 1.0]
    strength: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Composite topic strength score in [0.0, 1.0]",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Evidence certainty / confidence score in [0.0, 1.0]",
    )
    evidence_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Number of distinct supporting works or declared items",
    )
    recency_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Publication recency signal score in [0.15, 1.0]",
    )

    # Deterministic classification
    classification: Mapped[str] = mapped_column(
        String(50),
        default="WEAK_INTEREST",
        nullable=False,
        comment="PRIMARY_EXPERTISE, SECONDARY_EXPERTISE, EMERGING_INTEREST, WEAK_INTEREST, INSUFFICIENT_EVIDENCE",
    )
    is_primary_expertise: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if classified as primary expertise",
    )

    # Temporal observation bounds
    first_observed_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Earliest publication year supporting this topic",
    )
    last_observed_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Most recent publication year supporting this topic",
    )

    # Source & Provenance
    source: Mapped[str] = mapped_column(
        String(100),
        default="SCHOLARLY_WORKS",
        nullable=False,
        comment="Evidence origin: SCHOLARLY_WORKS, PROFILE_DECLARED, HYBRID",
    )
    provenance: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured evidence reasons, citation count, authorship breakdown",
    )
    supporting_work_ids: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of UUID strings for supporting research works",
    )

    # Relationships
    profile: Mapped[Optional["ResearchProfileModel"]] = relationship(
        foreign_keys=[profile_id],
    )
    canonical_researcher: Mapped[Optional["ResearcherModel"]] = relationship(
        foreign_keys=[canonical_researcher_id],
    )
    topic: Mapped[Optional["TopicModel"]] = relationship(
        foreign_keys=[topic_id],
    )
