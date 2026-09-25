"""Phase 5.12 — Peer & co-author discovery schemas."""
from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.researcher_discovery import CollaborationInterest, CollaborationStatus
from app.personalization.peer_matching_engine import PeerMatchTier, PeerSignalType


class DiscoverySettingsSchema(BaseModel):
    """A researcher's own discoverability settings."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    is_discoverable: bool = False
    collaboration_status: CollaborationStatus = CollaborationStatus.OPEN_TO_ENQUIRIES
    collaboration_interests: list[CollaborationInterest] = Field(default_factory=list)
    show_institution: bool = True
    show_contact_email: bool = False
    collaboration_note: str | None = None
    consent_updated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DiscoverySettingsUpdate(BaseModel):
    """Partial update of discoverability settings. Omitted fields are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    is_discoverable: bool | None = None
    collaboration_status: CollaborationStatus | None = None
    collaboration_interests: list[CollaborationInterest] | None = None
    show_institution: bool | None = None
    show_contact_email: bool | None = None
    collaboration_note: str | None = Field(default=None, max_length=1000)

    @field_validator("collaboration_note")
    @classmethod
    def strip_note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("collaboration_interests")
    @classmethod
    def deduplicate_interests(
        cls, v: list[CollaborationInterest] | None
    ) -> list[CollaborationInterest] | None:
        if v is None:
            return None
        return list(dict.fromkeys(v))


class PeerMatchSignalSchema(BaseModel):
    """One scored contribution to a peer match, with the evidence behind it."""

    signal_type: PeerSignalType
    raw_score: float
    weight: float
    weighted_contribution: float
    evidence: list[str] = Field(default_factory=list)
    explanation: str


class PeerProfileSchema(BaseModel):
    """
    A suggested peer, filtered by their own disclosure settings.

    Institution and contact email appear only when that researcher chose to show them, so this
    schema is the boundary where consent is applied.
    """

    profile_id: uuid.UUID
    full_name: str | None = None
    institution: str | None = None
    department: str | None = None
    academic_status: str | None = None
    contact_email: str | None = None
    collaboration_status: CollaborationStatus
    collaboration_interests: list[CollaborationInterest] = Field(default_factory=list)
    collaboration_note: str | None = None


class PeerMatchSchema(BaseModel):
    """A ranked peer suggestion with its full explanation."""

    peer: PeerProfileSchema
    match_score: float = Field(ge=0.0, le=1.0)
    tier: PeerMatchTier
    confidence: float = Field(ge=0.0, le=1.0)
    shared_topics: list[str] = Field(default_factory=list)
    complementary_topics: list[str] = Field(default_factory=list)
    signals: list[PeerMatchSignalSchema] = Field(default_factory=list)
    explanation_reasons: list[str] = Field(default_factory=list)


class PeerMatchResponse(BaseModel):
    """The result of a peer search, including why it may be empty."""

    researcher_id: uuid.UUID
    matches: list[PeerMatchSchema] = Field(default_factory=list)
    total_candidates_evaluated: int = 0
    returned_count: int = 0
    algorithm_version: str
    is_discoverable: bool = Field(
        description="Whether the requesting researcher is themselves discoverable by peers",
    )
    data_sufficiency: str = Field(
        description=(
            "SUFFICIENT when the requester has enough recorded topics to match on, "
            "INSUFFICIENT_PROFILE when they do not, NO_CANDIDATES when nobody is discoverable"
        ),
    )
    guidance: str | None = Field(
        default=None,
        description="Actionable explanation when no matches could be produced",
    )
