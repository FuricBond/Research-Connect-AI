"""
Phase 5.12 — Peer & Co-Author Matching configuration.

Every weight and threshold the peer matcher uses lives here, so the scoring law is auditable in
one place rather than scattered through the engine. The weights are normalized and asserted to
sum to 1.0 at import, which is the same discipline the Phase 5.3 scoring config applies.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PeerMatchingConfig:
    """
    Deterministic peer-matching weights and thresholds.

    The two topical signals deliberately pull in opposite directions. Shared expertise predicts
    that two researchers can understand each other; complementary expertise predicts that the
    collaboration produces something neither could alone. A matcher using only the first returns
    the researcher's own reflection, and one using only the second returns strangers, so both are
    scored and both are reported separately in the explanation.
    """

    algorithm_version: str = "5.12.1"

    # ── Signal weights (must sum to 1.0) ──────────────────────────────────────
    shared_expertise_weight: float = 0.34
    complementary_expertise_weight: float = 0.26
    taxonomy_proximity_weight: float = 0.18
    methodology_overlap_weight: float = 0.12
    collaboration_readiness_weight: float = 0.10

    # ── Expertise strength tiers ──────────────────────────────────────────────
    # Classifications that count as genuine expertise rather than a passing interest.
    expertise_classifications: tuple[str, ...] = (
        "PRIMARY_EXPERTISE",
        "SECONDARY_EXPERTISE",
    )
    emerging_classifications: tuple[str, ...] = ("EMERGING_INTEREST",)

    # A topic is only treated as a shared strength when both researchers clear this strength.
    min_shared_topic_strength: float = 0.25
    # Below this, an interest is too weak to imply a complementary capability either.
    min_complementary_topic_strength: float = 0.35

    # ── Evidence sufficiency ──────────────────────────────────────────────────
    # Fewer topics than this on either side and the match is reported as insufficient evidence
    # rather than given a confident score from one accidental overlap.
    min_topics_for_match: int = 2
    min_shared_topics_for_high_confidence: int = 3

    # ── Diversity ─────────────────────────────────────────────────────────────
    # Cross-institution collaboration is the point of a discovery tool: a researcher already
    # knows their own department. This is a mild preference, not a filter.
    cross_institution_bonus: float = 0.06
    same_institution_penalty: float = 0.04

    # ── Collaboration readiness, by declared status ───────────────────────────
    readiness_scores: dict[str, float] = field(
        default_factory=lambda: {
            "SEEKING_COLLABORATORS": 1.00,
            "OPEN_TO_ENQUIRIES": 0.75,
            "SELECTIVELY_AVAILABLE": 0.40,
            "NOT_AVAILABLE": 0.00,
        }
    )

    # ── Result presentation ───────────────────────────────────────────────────
    # Below this a pairing is not worth showing; a long tail of near-zero matches makes the
    # useful ones harder to find.
    min_match_score: float = 0.12
    default_limit: int = 20
    max_limit: int = 50
    max_explanation_reasons: int = 6

    # Match tier boundaries, used for the label shown to researchers.
    strong_match_threshold: float = 0.60
    moderate_match_threshold: float = 0.35

    def __post_init__(self) -> None:
        total = (
            self.shared_expertise_weight
            + self.complementary_expertise_weight
            + self.taxonomy_proximity_weight
            + self.methodology_overlap_weight
            + self.collaboration_readiness_weight
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"Peer matching signal weights must sum to 1.0, got {total:.6f}."
            )


DEFAULT_PEER_MATCHING_CONFIG = PeerMatchingConfig()
