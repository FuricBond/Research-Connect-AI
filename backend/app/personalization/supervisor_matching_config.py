"""
Phase 5.13 — Supervisor Matching configuration.

Every weight and threshold the supervisor matcher uses lives here, so the scoring law is
auditable in one place. The weights are asserted to sum to 1.0 at construction, the same
discipline the Phase 5.12 peer matching config applies.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.personalization.peer_matching_config import (
    DEFAULT_PEER_MATCHING_CONFIG,
    PeerMatchingConfig,
)


@dataclass(frozen=True)
class SupervisorMatchingConfig:
    """
    Deterministic supervisor-matching weights and thresholds.

    A student looking for a supervisor needs research fit first: shared topics and close meaning
    between what the student wants to work on and what the faculty member publishes. Recent
    papers show that fit is current rather than historical, and availability says whether the
    faculty member is actually taking students. Each is scored and reported separately so the
    student can judge a suggestion rather than trust a single number.
    """

    algorithm_version: str = "5.13.1"

    # ── Signal weights (must sum to 1.0) ──────────────────────────────────────
    topic_fit_weight: float = 0.35
    semantic_fit_weight: float = 0.25
    recent_paper_evidence_weight: float = 0.15
    taxonomy_proximity_weight: float = 0.15
    supervision_availability_weight: float = 0.10

    # ── Penalties ─────────────────────────────────────────────────────────────
    # Subtracted once per faculty topic the student explicitly excluded (TOPIC preference).
    excluded_topic_penalty: float = 0.05

    # ── Evidence sufficiency ──────────────────────────────────────────────────
    # Fewer topics than this and a pairing is reported as insufficient evidence, unless both
    # sides have an embedding to compare by meaning instead.
    min_topics_for_match: int = 2

    # ── Recent paper evidence ─────────────────────────────────────────────────
    # A paper counts as recent when published in the current calendar year or the five before.
    recent_years: int = 6
    # Works loaded per faculty member, most recent first; bounds memory for prolific authors.
    max_works_per_faculty: int = 50
    max_matching_papers: int = 3
    # A paper below this similarity is not evidence of fit.
    min_paper_similarity: float = 0.35

    # ── Supervision availability ──────────────────────────────────────────────
    # An OPEN posting of one of these types is a concrete offer to supervise a student.
    supervision_posting_types: tuple[str, ...] = (
        "THESIS_TOPIC",
        "PROJECT",
        "RESEARCH_ASSISTANTSHIP",
    )
    # Collaboration interests that signal willingness to supervise or mentor.
    supervision_interests: tuple[str, ...] = ("STUDENT_CO_SUPERVISION", "MENTORSHIP")
    supervision_interest_bonus: float = 0.2
    max_open_postings: int = 5

    # Shared-topic strength floor and readiness-by-status scores come from the peer matcher,
    # whose topic scorers this matcher reuses.
    peer_config: PeerMatchingConfig = field(
        default_factory=lambda: DEFAULT_PEER_MATCHING_CONFIG
    )

    # ── Result presentation ───────────────────────────────────────────────────
    min_match_score: float = 0.12
    default_limit: int = 20
    max_limit: int = 50
    max_explanation_reasons: int = 6

    # Match tier boundaries, used for the label shown to students.
    strong_match_threshold: float = 0.60
    moderate_match_threshold: float = 0.35

    def __post_init__(self) -> None:
        total = (
            self.topic_fit_weight
            + self.semantic_fit_weight
            + self.recent_paper_evidence_weight
            + self.taxonomy_proximity_weight
            + self.supervision_availability_weight
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"Supervisor matching signal weights must sum to 1.0, got {total:.6f}."
            )


DEFAULT_SUPERVISOR_MATCHING_CONFIG = SupervisorMatchingConfig()
