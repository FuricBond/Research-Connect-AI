from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.opportunity import OpportunityModel
    from app.models.research_profile import ResearchProfileModel


class ResearcherRecommendationFeedbackModel(Base, TimestampMixin):
    """
    Canonical persistent representation of researcher recommendation feedback (Phase 3.6).

    Captures explicit and implicit user interaction events with recommended
    opportunities, providing the source data for deterministic behavioral learning.

    Supported feedback types:
      - VIEW: Weak positive signal (+0.05). User inspected opportunity details.
      - SAVE: Strong positive signal (+0.25). User bookmarked opportunity.
      - INTERESTED: Strong positive signal (+0.30). Explicit thumbs up / endorsement.
      - APPLY: Strongest positive signal (+0.40). Manuscript submitted / application tracked.
      - DISMISS: Negative signal (-0.20). Card skipped / hidden.
      - NOT_INTERESTED: Strong negative signal (-0.30). Explicit thumbs down / rejected.

    Strict Architectural Boundaries:
      - Feedback events record behavior; they NEVER mutate or overwrite Phase 3.3 explicit preferences.
      - Feedback events NEVER bypass Phase 2.6 risk checks or Phase 2.7 deadline lifecycle.
      - Repeated feedback is subject to deterministic temporal decay and diminishing returns.
    """

    __tablename__ = "researcher_recommendation_feedback"
    __table_args__ = (
        UniqueConstraint(
            "researcher_id",
            "opportunity_id",
            "feedback_type",
            name="uq_researcher_feedback_type",
        ),
        Index("idx_researcher_feedback_researcher_id", "researcher_id"),
        Index("idx_researcher_feedback_opportunity_id", "opportunity_id"),
        Index("idx_researcher_feedback_type", "feedback_type"),
        Index("idx_researcher_feedback_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to canonical research profile
    researcher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated ResearchProfileModel ID",
    )

    # Link to opportunity
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated OpportunityModel ID",
    )

    # Feedback type: VIEW, SAVE, DISMISS, INTERESTED, NOT_INTERESTED, APPLY
    feedback_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Interaction event type (VIEW, SAVE, DISMISS, INTERESTED, NOT_INTERESTED, APPLY)",
    )

    # Source channel: RECOMMENDATION, DISCOVERY, DIRECT, SEARCH
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="RECOMMENDATION",
        comment="Originating channel (RECOMMENDATION, DISCOVERY, SEARCH, DIRECT)",
    )

    # User note or explanation
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional researcher feedback note or categorization tag",
    )

    # Recommendation provenance: rank position at interaction time
    rank_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Rank position where this candidate was presented when interacted with",
    )

    # Session identifier for attribution
    recommendation_session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Recommendation session tracking token",
    )

    # Contextual metadata snapshot at event time (e.g. matched topics, base score)
    metadata_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Snapshot of opportunity and ranking metadata at event creation",
    )

    # Relationships
    researcher_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="recommendation_feedback",
    )
    opportunity: Mapped["OpportunityModel"] = relationship()
