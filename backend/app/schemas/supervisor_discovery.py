"""Phase 5.13 — Supervisor discovery schemas."""
from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import BaseModel, Field

from app.models.research_posting import PostingType
from app.personalization.peer_matching_engine import PeerMatchTier
from app.personalization.supervisor_matching_engine import SupervisorSignalType
from app.schemas.researcher_discovery import PeerProfileSchema


class MatchingPaperSchema(BaseModel):
    """A faculty member's recent paper offered as evidence of research fit."""

    work_id: uuid.UUID
    title: str
    publication_year: int | None = None
    similarity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Cosine similarity to the student's embedding, or the share of the paper's topics "
            "the student holds when no embedding could be compared"
        ),
    )
    shared_topics: list[str] = Field(default_factory=list)
    doi: str | None = None
    landing_page_url: str | None = None


class OpenPostingRefSchema(BaseModel):
    """An OPEN posting by the faculty member that a student could apply to or ask about."""

    posting_id: uuid.UUID
    title: str
    posting_type: PostingType
    application_deadline: datetime | None = None


class SupervisorMatchSignalSchema(BaseModel):
    """One scored contribution to a supervisor match, with the evidence behind it."""

    signal_type: SupervisorSignalType
    raw_score: float
    weight: float
    weighted_contribution: float
    evidence: list[str] = Field(default_factory=list)
    explanation: str


class SupervisorMatchSchema(BaseModel):
    """
    A ranked supervisor suggestion with its full explanation.

    `supervisor` is the peer discovery profile, filtered by the faculty member's own disclosure
    settings exactly as it is for peers.
    """

    supervisor: PeerProfileSchema
    match_score: float = Field(ge=0.0, le=1.0)
    tier: PeerMatchTier
    confidence: float = Field(ge=0.0, le=1.0)
    shared_topics: list[str] = Field(default_factory=list)
    matching_papers: list[MatchingPaperSchema] = Field(default_factory=list)
    open_postings: list[OpenPostingRefSchema] = Field(default_factory=list)
    signals: list[SupervisorMatchSignalSchema] = Field(default_factory=list)
    explanation_reasons: list[str] = Field(default_factory=list)


class SupervisorMatchResponse(BaseModel):
    """The result of a supervisor search, including why it may be empty."""

    researcher_id: uuid.UUID
    matches: list[SupervisorMatchSchema] = Field(default_factory=list)
    total_candidates_evaluated: int = 0
    returned_count: int = 0
    algorithm_version: str
    semantic_available: bool = Field(
        description=(
            "Whether the student's interests could be embedded. When false, matches are scored "
            "on research topics only"
        ),
    )
    data_sufficiency: str = Field(
        description=(
            "SUFFICIENT when the student has enough recorded topics to match on, "
            "INSUFFICIENT_PROFILE when they do not, NO_CANDIDATES when no faculty member is "
            "discoverable"
        ),
    )
    guidance: str | None = Field(
        default=None,
        description="Actionable explanation when no matches could be produced",
    )
