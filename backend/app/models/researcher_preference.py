from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_profile import ResearchProfileModel
    from app.models.topic import TopicModel


class ResearcherPreferenceModel(Base, TimestampMixin):
    """
    Canonical representation of a researcher's personal preferences (Phase 3.3).

    Answers:
      "What kinds of research opportunities, research topics, venues, formats,
       locations, deadlines, and other attributes does this researcher prefer?"

    Strict Boundaries:
      - This model does NOT represent opportunity recommendations or candidate rankings.
      - Expertise != Preference: Academic publications/interests (Phase 3.2) are evidence,
        not explicit preferences.
      - Behavioral inference (INFERRED) is strictly derived from verified platform activity
        (SavedOpportunityModel) and never fabricated.
    """

    __tablename__ = "researcher_preferences"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "category",
            "preference_value",
            name="uq_researcher_preferences_profile_cat_val",
        ),
        Index("idx_researcher_preferences_profile_id", "profile_id"),
        Index("idx_researcher_preferences_category", "category"),
        Index("idx_researcher_preferences_source", "source"),
        Index("idx_researcher_preferences_active", "is_active"),
        Index("idx_researcher_preferences_type", "preference_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to platform research profile
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated ResearchProfileModel ID",
    )

    # Preference taxonomy category: OPPORTUNITY_TYPE, DELIVERY_MODE, TOPIC, LOCATION, DEADLINE_WINDOW, OPEN_ACCESS, VENUE
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Taxonomy category of the preference",
    )

    # Explicit 3-state orientation: PREFERRED, EXCLUDED (unspecified = absence of row)
    preference_type: Mapped[str] = mapped_column(
        String(50),
        default="PREFERRED",
        server_default="PREFERRED",
        nullable=False,
        index=True,
        comment="Preference type: PREFERRED or EXCLUDED (Phase 5.1)",
    )

    # Specific attribute key (e.g. 'opportunity_type', 'delivery_mode', 'topic', 'location', 'min_days_before_deadline')
    preference_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Attribute key within category",
    )

    # Canonical normalized preference value (e.g. 'CONFERENCE', 'ONLINE', 'machine-learning', 'Europe', '14')
    preference_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Normalized canonical value",
    )

    # Human-readable display label
    display_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-friendly display name",
    )

    # Optional foreign key to canonical entity (e.g. TopicModel)
    canonical_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Canonical TopicModel ID if matched to taxonomy",
    )

    # Bounded metric signals strictly in [0.0, 1.0]
    strength: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
        comment="Preference strength in [0.0, 1.0]",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.95,
        nullable=False,
        comment="Preference confidence / certainty in [0.0, 1.0]",
    )

    # Provenance and source: EXPLICIT, INFERRED, DERIVED_FROM_EXPERTISE
    source: Mapped[str] = mapped_column(
        String(50),
        default="EXPLICIT",
        nullable=False,
        index=True,
        comment="Evidence origin: EXPLICIT, INFERRED, DERIVED_FROM_EXPERTISE",
    )

    # Active status toggle
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Whether the preference is currently active",
    )

    # Recency score strictly in [0.0, 1.0]
    recency_score: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
        comment="Recency signal in [0.0, 1.0]",
    )

    # Structured explainability reasons, observation metrics, source trace
    provenance: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured evidence trace and explanation notes",
    )

    # Temporal bounds
    last_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of latest supporting action or declaration",
    )

    # Relationships
    profile: Mapped[Optional["ResearchProfileModel"]] = relationship(
        foreign_keys=[profile_id],
    )
    canonical_topic: Mapped[Optional["TopicModel"]] = relationship(
        foreign_keys=[canonical_id],
    )
