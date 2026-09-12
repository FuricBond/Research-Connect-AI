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


class ResearcherRecommendationSnapshotModel(Base, TimestampMixin):
    """
    Canonical persistent snapshot of recommendations presented to a researcher (Phase 3.7).

    Preserves the exact ranking output, score breakdown, and candidate ordering
    at recommendation time for auditability, immutability, and offline evaluation.

    Strict Architectural Boundaries:
      - Point-in-time immutable record: never changes when researcher profile or preferences mutate.
      - Stores deterministic ranking_version (e.g. 'phase3.7-v1', 'phase3.5-personalized', 'phase2-baseline').
      - Idempotent: request_hash and session_id prevent duplicate snapshot creation during rapid polling.
      - Evaluation is strictly read-only and never modifies recommendation scores.
    """

    __tablename__ = "researcher_recommendation_snapshots"
    __table_args__ = (
        Index("idx_rec_snapshots_researcher_id", "researcher_id"),
        Index("idx_rec_snapshots_created_at", "created_at"),
        Index("idx_rec_snapshots_version", "ranking_version"),
        Index("idx_rec_snapshots_request_hash", "request_hash"),
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

    # Deterministic ranking pipeline version identifier
    ranking_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="phase3.7-v1",
        comment="Deterministic ranking algorithm version (e.g. phase3.7-v1, phase3.5-personalized, phase2-baseline)",
    )

    # Total candidate pool evaluated before slicing/pagination
    candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total candidate opportunities evaluated during recommendation generation",
    )

    # Count of recommendations returned to the researcher
    returned_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of recommendations returned in this snapshot",
    )

    # Request context at recommendation time (limit, offset, filters, ablation flag)
    request_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Serialized query parameters and filter options at recommendation time",
    )

    # Deterministic hash of request inputs to prevent duplicate snapshot creation during rapid polling
    request_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Deterministic SHA-256 hash of query parameters for idempotency / polling deduplication",
    )

    # Optional client-supplied or generated recommendation session tracking token
    session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Optional client recommendation session identifier",
    )

    # Relationships
    researcher_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="recommendation_snapshots",
    )
    items: Mapped[list["ResearcherRecommendationItemModel"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="ResearcherRecommendationItemModel.rank",
    )


class ResearcherRecommendationItemModel(Base, TimestampMixin):
    """
    Individual opportunity item within a recommendation snapshot (Phase 3.7).

    Stores point-in-time scores and ranking positions for offline IR evaluation
    (Precision@K, Recall@K, HitRate@K, NDCG@K, Save Rate, Engagement Rate, Dismissal Rate).
    """

    __tablename__ = "researcher_recommendation_items"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "opportunity_id",
            name="uq_snapshot_opportunity",
        ),
        UniqueConstraint(
            "snapshot_id",
            "rank",
            name="uq_snapshot_rank",
        ),
        Index("idx_rec_items_snapshot_id", "snapshot_id"),
        Index("idx_rec_items_opportunity_id", "opportunity_id"),
        Index("idx_rec_items_snapshot_rank", "snapshot_id", "rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Parent snapshot
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("researcher_recommendation_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated ResearcherRecommendationSnapshotModel ID",
    )

    # Recommended opportunity
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated OpportunityModel ID",
    )

    # 1-indexed rank position at recommendation time
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1-indexed rank position in the presented recommendation list",
    )

    # Authoritative Phase 2 base relevance score (HybridRanker composite)
    base_relevance_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Phase 2 base relevance score in [0.0, 1.0]",
    )

    # Phase 3.5 Personalization score
    personalization_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Phase 3.5 raw personalization match score in [0.0, 1.0]",
    )

    # Phase 3.6 Behavioral adjustment contribution
    behavioral_adjustment: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Phase 3.6 learned behavioral contribution to adjustment",
    )

    # Composite final recommendation score
    final_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Composite final recommendation score in [0.0, 1.0]",
    )

    # Phase 2.6 Risk intelligence snapshot
    risk_level: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Phase 2.6 risk classification (LOW_RISK, MODERATE_RISK, HIGH_RISK)",
    )

    # Phase 2.7 Deadline intelligence snapshot
    deadline_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Phase 2.7 deadline lifecycle status (UPCOMING, DUE_TODAY, EXPIRED, MISSING)",
    )

    # Relationships
    snapshot: Mapped["ResearcherRecommendationSnapshotModel"] = relationship(
        back_populates="items",
    )
    opportunity: Mapped["OpportunityModel"] = relationship()
