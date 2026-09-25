"""
Phase 5.12 — Peer & Co-Author Discovery: researcher-controlled discoverability.

Peer discovery differs from every other matching surface in the platform: the thing being
matched is a person, not a venue. Showing one researcher to another exposes their affiliation,
expertise and availability, so discoverability is opt-in and its settings row is the record of
that consent. A researcher with no settings row is not discoverable, because absence of a
decision is not consent.

This mirrors the Phase 5.9 stance on personalization controls: the researcher holds the switch,
the platform records what they chose, and nothing derived can override it.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.research_profile import ResearchProfileModel


class CollaborationStatus(str, Enum):
    """
    How open a researcher currently is to being approached.

    Distinct from `is_discoverable`: a researcher may want to remain findable while signalling
    that they cannot take on anything new, which is more useful to a peer than disappearing.
    """

    SEEKING_COLLABORATORS = "SEEKING_COLLABORATORS"
    OPEN_TO_ENQUIRIES = "OPEN_TO_ENQUIRIES"
    SELECTIVELY_AVAILABLE = "SELECTIVELY_AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class CollaborationInterest(str, Enum):
    """The kinds of collaboration a researcher will consider."""

    CO_AUTHORSHIP = "CO_AUTHORSHIP"
    JOINT_GRANT = "JOINT_GRANT"
    DATA_SHARING = "DATA_SHARING"
    METHOD_EXCHANGE = "METHOD_EXCHANGE"
    STUDENT_CO_SUPERVISION = "STUDENT_CO_SUPERVISION"
    PEER_REVIEW_EXCHANGE = "PEER_REVIEW_EXCHANGE"
    MENTORSHIP = "MENTORSHIP"


class ResearcherDiscoverySettingsModel(Base, TimestampMixin):
    """A researcher's peer-discovery consent and collaboration preferences (Phase 5.12)."""

    __tablename__ = "researcher_discovery_settings"
    __table_args__ = (
        CheckConstraint(
            "collaboration_status IN ('SEEKING_COLLABORATORS', 'OPEN_TO_ENQUIRIES', "
            "'SELECTIVELY_AVAILABLE', 'NOT_AVAILABLE')",
            name="chk_discovery_settings_collaboration_status",
        ),
        Index("idx_discovery_settings_profile", "profile_id", unique=True),
        # Peer searches filter on discoverability first, so it leads the composite index.
        Index("idx_discovery_settings_discoverable", "is_discoverable", "collaboration_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    is_discoverable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment=(
            "Master consent switch. False, and absence of a row entirely, both mean the "
            "researcher is excluded from every peer discovery result."
        ),
    )

    collaboration_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=CollaborationStatus.OPEN_TO_ENQUIRIES.value,
        server_default=CollaborationStatus.OPEN_TO_ENQUIRIES.value,
    )

    collaboration_interests: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="Kinds of collaboration the researcher will consider",
    )

    # What a peer may see. Each field is a separate decision because researchers differ in what
    # they consider sensitive: an email address is not the same disclosure as an institution.
    show_institution: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    show_contact_email: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Off by default; an email address is the most consequential disclosure here",
    )

    collaboration_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Short statement shown to peers, e.g. what the researcher is looking for",
    )

    consent_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When discoverability was last changed, recorded as the consent timestamp",
    )

    researcher_profile: Mapped["ResearchProfileModel"] = relationship(
        back_populates="discovery_settings",
    )
