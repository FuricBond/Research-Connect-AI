from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.opportunity import OpportunityModel
    from app.models.research_profile import ResearchProfileModel


class InteractionType(str, Enum):
    """
    Supported researcher-opportunity interaction types (Phase 5.4).
    
    Explicit feedback signals:
      - INTERESTED: Strong positive signal. Explicit researcher endorsement.
      - NOT_INTERESTED: Strong negative signal. Explicit researcher rejection.
      - DISMISSED: Negative signal. Skipped / hidden from feed.
      - HIDDEN: Negative signal. Explicitly hidden from consideration.
      - SAVED: Positive action signal. Opportunity bookmarked to workspace.
      - APPLIED: Strong positive action signal. Manuscript or proposal submitted.
      - SHARED: Positive action signal. Opportunity shared with collaborator.

    Passive observation signals:
      - VIEWED: Neutral observation. Opportunity card / preview rendered.
      - OPENED: Neutral observation. Opportunity detail view expanded.
    """

    # Explicit feedback signals
    INTERESTED = "INTERESTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    DISMISSED = "DISMISSED"
    HIDDEN = "HIDDEN"

    # Action signals
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    SHARED = "SHARED"

    # Passive observations (MUST NOT be treated as preference or affinity)
    VIEWED = "VIEWED"
    OPENED = "OPENED"


# Explicit signals set for deterministic classification
EXPLICIT_FEEDBACK_TYPES: frozenset[InteractionType] = frozenset(
    {
        InteractionType.INTERESTED,
        InteractionType.NOT_INTERESTED,
        InteractionType.DISMISSED,
        InteractionType.HIDDEN,
        InteractionType.SAVED,
        InteractionType.APPLIED,
        InteractionType.SHARED,
    }
)

PASSIVE_OBSERVATION_TYPES: frozenset[InteractionType] = frozenset(
    {
        InteractionType.VIEWED,
        InteractionType.OPENED,
    }
)

POSITIVE_EXPLICIT_TYPES: frozenset[InteractionType] = frozenset(
    {
        InteractionType.INTERESTED,
        InteractionType.SAVED,
        InteractionType.APPLIED,
        InteractionType.SHARED,
    }
)

NEGATIVE_EXPLICIT_TYPES: frozenset[InteractionType] = frozenset(
    {
        InteractionType.NOT_INTERESTED,
        InteractionType.DISMISSED,
        InteractionType.HIDDEN,
    }
)


class ResearcherInteractionModel(Base):
    """
    Persistent append-only event representation of a researcher's interaction with an opportunity (Phase 5.4).

    Answers:
      "When and how did this researcher interact with this specific opportunity,
       and was the signal explicit feedback or a passive observation?"

    Strict Architectural Boundaries:
      - Append-only event semantics: historical records are never mutated when preferences change.
      - Explicit vs Passive: VIEWED and OPENED are passive observations and MUST NOT be interpreted
        as preference or affinity.
      - Preference Inviolability: Interactions NEVER mutate or overwrite Phase 5.1 explicit preferences.
      - Zero ML / Zero LLM: No collaborative filtering, embeddings, or opaque behavioral inference.
      - Privacy First: No raw page DOM, PII, credentials, or unrelated browsing history stored.
    """

    __tablename__ = "researcher_interactions"
    __table_args__ = (
        CheckConstraint(
            "interaction_type IN ('VIEWED', 'OPENED', 'SAVED', 'DISMISSED', 'HIDDEN', "
            "'INTERESTED', 'NOT_INTERESTED', 'APPLIED', 'SHARED')",
            name="chk_researcher_interaction_type",
        ),
        Index("idx_researcher_interactions_profile_created", "profile_id", "created_at"),
        Index(
            "idx_researcher_interactions_profile_opp_type",
            "profile_id",
            "opportunity_id",
            "interaction_type",
        ),
        Index("idx_researcher_interactions_opp_type", "opportunity_id", "interaction_type"),
        Index("idx_researcher_interactions_client_event", "profile_id", "client_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Link to canonical research profile
    profile_id: Mapped[uuid.UUID] = mapped_column(
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

    # Interaction type
    interaction_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Interaction type (VIEWED, OPENED, SAVED, DISMISSED, HIDDEN, INTERESTED, NOT_INTERESTED, APPLIED, SHARED)",
    )

    # Whether this interaction is an intentional explicit feedback signal (vs passive observation)
    is_explicit_feedback: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if interaction is an explicit signal, False for passive observation",
    )

    # Channel or context where interaction occurred
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="RECOMMENDATION",
        comment="Context source (RECOMMENDATION, DISCOVERY, SEARCH, DIRECT, WORKSPACE)",
    )

    # Optional client-supplied event ID for idempotency deduplication
    client_event_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Client-supplied idempotency key / event identifier",
    )

    # Sanitized contextual metadata snapshot (e.g. rank position, session id; NO PII/credentials)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Sanitized contextual metadata snapshot (rank position, session ID; no PII/credentials)",
    )

    # Creation timestamp (server time in UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="Timestamp when interaction was recorded in UTC",
    )

    # Relationships
    researcher_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="interactions",
    )
    opportunity: Mapped["OpportunityModel"] = relationship()
