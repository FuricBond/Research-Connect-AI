"""
Phase 5.12 — Peer & Co-Author Matching Engine.

A pure, deterministic engine: given two researchers' topic profiles it produces a bounded score
and a structured explanation, with no database access, no network, no randomness and no model
inference. Identical inputs always yield an identical result, which is what lets a researcher be
told precisely why someone was suggested.

The scoring law balances two opposing signals:

  Shared expertise         predicts that two researchers can understand each other.
  Complementary expertise  predicts that the collaboration yields something neither could alone.

Optimizing only the first returns the researcher's own reflection; only the second returns
strangers with nothing in common. Both are computed, both are bounded, and both are reported
separately so the researcher can judge the suggestion rather than trust a single number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence
import uuid

from app.personalization.peer_matching_config import (
    DEFAULT_PEER_MATCHING_CONFIG,
    PeerMatchingConfig,
)


class PeerMatchTier(str, Enum):
    """Coarse label for a match score, so the UI need not invent its own thresholds."""

    STRONG = "STRONG"
    MODERATE = "MODERATE"
    EXPLORATORY = "EXPLORATORY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PeerSignalType(str, Enum):
    SHARED_EXPERTISE = "SHARED_EXPERTISE"
    COMPLEMENTARY_EXPERTISE = "COMPLEMENTARY_EXPERTISE"
    TAXONOMY_PROXIMITY = "TAXONOMY_PROXIMITY"
    METHODOLOGY_OVERLAP = "METHODOLOGY_OVERLAP"
    COLLABORATION_READINESS = "COLLABORATION_READINESS"
    INSTITUTION_DIVERSITY = "INSTITUTION_DIVERSITY"


@dataclass(frozen=True)
class TopicProfile:
    """
    One researcher's topical footprint, normalized away from the ORM.

    Keeping the engine free of model objects is what makes it testable without a database and
    reusable for candidates that came from anywhere.
    """

    profile_id: uuid.UUID
    # topic slug -> strength in [0, 1]
    expertise: dict[str, float] = field(default_factory=dict)
    emerging: dict[str, float] = field(default_factory=dict)
    # topic slug -> its taxonomy ancestor slugs, for hierarchical proximity
    ancestors: dict[str, frozenset[str]] = field(default_factory=dict)
    keywords: frozenset[str] = frozenset()
    institution: str | None = None
    academic_status: str | None = None

    @property
    def all_topics(self) -> dict[str, float]:
        """Expertise and emerging interests together, expertise winning on conflict."""
        combined = dict(self.emerging)
        combined.update(self.expertise)
        return combined


@dataclass(frozen=True)
class PeerMatchSignal:
    """One scored contribution, with the evidence that produced it."""

    signal_type: PeerSignalType
    raw_score: float
    weight: float
    weighted_contribution: float
    evidence: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class PeerMatchAssessment:
    """The complete, explainable outcome of comparing two researchers."""

    source_profile_id: uuid.UUID
    candidate_profile_id: uuid.UUID
    match_score: float
    tier: PeerMatchTier
    confidence: float
    signals: tuple[PeerMatchSignal, ...]
    shared_topics: tuple[str, ...]
    complementary_topics: tuple[str, ...]
    explanation_reasons: tuple[str, ...]
    algorithm_version: str


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class PeerMatchingEngine:
    """Deterministic peer and co-author matcher."""

    @classmethod
    def score_pair(
        cls,
        source: TopicProfile,
        candidate: TopicProfile,
        *,
        candidate_readiness: str | None = None,
        config: PeerMatchingConfig = DEFAULT_PEER_MATCHING_CONFIG,
    ) -> PeerMatchAssessment:
        """
        Scores one candidate against one source researcher.

        Returns an INSUFFICIENT_EVIDENCE assessment with a zero score when either side has too
        few topics to compare, rather than inventing confidence from a single chance overlap.
        """
        source_topics = source.all_topics
        candidate_topics = candidate.all_topics

        if (
            len(source_topics) < config.min_topics_for_match
            or len(candidate_topics) < config.min_topics_for_match
        ):
            return PeerMatchAssessment(
                source_profile_id=source.profile_id,
                candidate_profile_id=candidate.profile_id,
                match_score=0.0,
                tier=PeerMatchTier.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                signals=(),
                shared_topics=(),
                complementary_topics=(),
                explanation_reasons=(
                    "Not enough recorded research topics on one or both profiles to compare "
                    "expertise meaningfully.",
                ),
                algorithm_version=config.algorithm_version,
            )

        signals: list[PeerMatchSignal] = []

        shared_score, shared_topics = cls._score_shared_expertise(source, candidate, config)
        signals.append(
            PeerMatchSignal(
                signal_type=PeerSignalType.SHARED_EXPERTISE,
                raw_score=shared_score,
                weight=config.shared_expertise_weight,
                weighted_contribution=round(shared_score * config.shared_expertise_weight, 6),
                evidence=shared_topics,
                explanation=(
                    f"You both work on {cls._join(shared_topics)}."
                    if shared_topics
                    else "No research topics are held as a strength by both of you."
                ),
            )
        )

        comp_score, comp_topics = cls._score_complementary_expertise(source, candidate, config)
        signals.append(
            PeerMatchSignal(
                signal_type=PeerSignalType.COMPLEMENTARY_EXPERTISE,
                raw_score=comp_score,
                weight=config.complementary_expertise_weight,
                weighted_contribution=round(
                    comp_score * config.complementary_expertise_weight, 6
                ),
                evidence=comp_topics,
                explanation=(
                    f"They bring expertise you have not recorded: {cls._join(comp_topics)}."
                    if comp_topics
                    else "They do not add expertise beyond what you already have."
                ),
            )
        )

        taxonomy_score, taxonomy_evidence = cls._score_taxonomy_proximity(source, candidate, config)
        signals.append(
            PeerMatchSignal(
                signal_type=PeerSignalType.TAXONOMY_PROXIMITY,
                raw_score=taxonomy_score,
                weight=config.taxonomy_proximity_weight,
                weighted_contribution=round(taxonomy_score * config.taxonomy_proximity_weight, 6),
                evidence=taxonomy_evidence,
                explanation=(
                    f"Your fields sit close together in the research taxonomy "
                    f"({cls._join(taxonomy_evidence)})."
                    if taxonomy_evidence
                    else "Your fields are not closely related in the research taxonomy."
                ),
            )
        )

        method_score, method_evidence = cls._score_methodology_overlap(source, candidate)
        signals.append(
            PeerMatchSignal(
                signal_type=PeerSignalType.METHODOLOGY_OVERLAP,
                raw_score=method_score,
                weight=config.methodology_overlap_weight,
                weighted_contribution=round(method_score * config.methodology_overlap_weight, 6),
                evidence=method_evidence,
                explanation=(
                    f"You describe your work with overlapping terms: {cls._join(method_evidence)}."
                    if method_evidence
                    else "Your stated keywords do not overlap."
                ),
            )
        )

        readiness_score = config.readiness_scores.get(candidate_readiness or "", 0.0)
        signals.append(
            PeerMatchSignal(
                signal_type=PeerSignalType.COLLABORATION_READINESS,
                raw_score=readiness_score,
                weight=config.collaboration_readiness_weight,
                weighted_contribution=round(
                    readiness_score * config.collaboration_readiness_weight, 6
                ),
                evidence=(candidate_readiness,) if candidate_readiness else (),
                explanation=cls._readiness_explanation(candidate_readiness),
            )
        )

        base_score = sum(signal.weighted_contribution for signal in signals)

        # Institution diversity is a mild adjustment, not a weighted signal: a researcher already
        # knows their own department, so a cross-institution peer is usually the more useful
        # suggestion, but never at the cost of overriding topical fit.
        diversity_adjustment = 0.0
        diversity_note: str | None = None
        if source.institution and candidate.institution:
            if source.institution.strip().lower() == candidate.institution.strip().lower():
                diversity_adjustment = -config.same_institution_penalty
                diversity_note = "You are at the same institution, which you can already reach directly."
            else:
                diversity_adjustment = config.cross_institution_bonus
                diversity_note = f"They are at a different institution ({candidate.institution})."

        if diversity_note is not None:
            signals.append(
                PeerMatchSignal(
                    signal_type=PeerSignalType.INSTITUTION_DIVERSITY,
                    raw_score=1.0 if diversity_adjustment > 0 else 0.0,
                    weight=abs(diversity_adjustment),
                    weighted_contribution=round(diversity_adjustment, 6),
                    evidence=(candidate.institution,) if candidate.institution else (),
                    explanation=diversity_note,
                )
            )

        match_score = round(_clamp(base_score + diversity_adjustment), 6)
        confidence = cls._compute_confidence(source, candidate, shared_topics, comp_topics, config)
        tier = cls._classify_tier(match_score, config)

        return PeerMatchAssessment(
            source_profile_id=source.profile_id,
            candidate_profile_id=candidate.profile_id,
            match_score=match_score,
            tier=tier,
            confidence=confidence,
            signals=tuple(signals),
            shared_topics=shared_topics,
            complementary_topics=comp_topics,
            explanation_reasons=cls._build_reasons(signals, config),
            algorithm_version=config.algorithm_version,
        )

    @classmethod
    def rank_candidates(
        cls,
        source: TopicProfile,
        candidates: Sequence[tuple[TopicProfile, str | None]],
        *,
        config: PeerMatchingConfig = DEFAULT_PEER_MATCHING_CONFIG,
        limit: int | None = None,
    ) -> list[PeerMatchAssessment]:
        """
        Scores and orders candidates.

        Self-matches are dropped, results below `min_match_score` are omitted, and ties break on
        confidence then profile id so the ordering is stable across identical runs.
        """
        assessments = [
            cls.score_pair(source, candidate, candidate_readiness=readiness, config=config)
            for candidate, readiness in candidates
            if candidate.profile_id != source.profile_id
        ]
        eligible = [
            assessment
            for assessment in assessments
            if assessment.match_score >= config.min_match_score
            and assessment.tier != PeerMatchTier.INSUFFICIENT_EVIDENCE
        ]
        eligible.sort(
            key=lambda a: (-a.match_score, -a.confidence, str(a.candidate_profile_id))
        )
        effective_limit = limit if limit is not None else config.default_limit
        return eligible[: max(0, min(effective_limit, config.max_limit))]

    # ── Individual signals ───────────────────────────────────────────────────

    @classmethod
    def _score_shared_expertise(
        cls,
        source: TopicProfile,
        candidate: TopicProfile,
        config: PeerMatchingConfig,
    ) -> tuple[float, tuple[str, ...]]:
        """
        Overlap where both researchers hold real strength.

        Normalized by the smaller footprint, so a specialist matching a generalist is not
        penalized for the generalist's breadth.
        """
        shared: list[tuple[str, float]] = []
        for topic, source_strength in source.all_topics.items():
            candidate_strength = candidate.all_topics.get(topic)
            if candidate_strength is None:
                continue
            if (
                source_strength < config.min_shared_topic_strength
                or candidate_strength < config.min_shared_topic_strength
            ):
                continue
            shared.append((topic, min(source_strength, candidate_strength)))

        if not shared:
            return 0.0, ()

        shared.sort(key=lambda item: (-item[1], item[0]))
        strength_sum = sum(strength for _, strength in shared)
        denominator = max(1, min(len(source.all_topics), len(candidate.all_topics)))
        return round(_clamp(strength_sum / denominator), 6), tuple(topic for topic, _ in shared)

    @classmethod
    def _score_complementary_expertise(
        cls,
        source: TopicProfile,
        candidate: TopicProfile,
        config: PeerMatchingConfig,
    ) -> tuple[float, tuple[str, ...]]:
        """
        Strengths the candidate has that the source does not.

        Only counts topics the candidate holds at real strength: a topic they barely touch is not
        a capability the source gains by collaborating.
        """
        complementary = [
            (topic, strength)
            for topic, strength in candidate.expertise.items()
            if topic not in source.all_topics and strength >= config.min_complementary_topic_strength
        ]
        if not complementary:
            return 0.0, ()

        complementary.sort(key=lambda item: (-item[1], item[0]))
        # Normalized against the candidate's own expertise breadth, so the signal expresses "how
        # much of what they know is new to you" rather than rewarding sheer topic count.
        denominator = max(1, len(candidate.expertise))
        strength_sum = sum(strength for _, strength in complementary)
        return round(_clamp(strength_sum / denominator), 6), tuple(
            topic for topic, _ in complementary
        )

    @classmethod
    def _score_taxonomy_proximity(
        cls,
        source: TopicProfile,
        candidate: TopicProfile,
        config: PeerMatchingConfig,
    ) -> tuple[float, tuple[str, ...]]:
        """
        Hierarchical closeness for topics that are not identical.

        Two researchers working on sibling topics under one parent are related even with no exact
        overlap, which is precisely the adjacency a co-author search should surface.
        """
        source_unshared = set(source.all_topics) - set(candidate.all_topics)
        candidate_unshared = set(candidate.all_topics) - set(source.all_topics)
        if not source_unshared or not candidate_unshared:
            return 0.0, ()

        common_ancestors: set[str] = set()
        related_pairs = 0
        for source_topic in sorted(source_unshared):
            source_ancestors = source.ancestors.get(source_topic, frozenset())
            if not source_ancestors:
                continue
            for candidate_topic in sorted(candidate_unshared):
                candidate_ancestors = candidate.ancestors.get(candidate_topic, frozenset())
                if not candidate_ancestors:
                    continue
                overlap = source_ancestors & candidate_ancestors
                if overlap:
                    related_pairs += 1
                    common_ancestors |= overlap

        if related_pairs == 0:
            return 0.0, ()

        # Saturating transform: the first few adjacencies are informative, the twentieth is not.
        score = related_pairs / (related_pairs + 3.0)
        return round(_clamp(score), 6), tuple(sorted(common_ancestors))

    @classmethod
    def _score_methodology_overlap(
        cls,
        source: TopicProfile,
        candidate: TopicProfile,
    ) -> tuple[float, tuple[str, ...]]:
        """
        Jaccard overlap of self-declared keywords, a proxy for shared methods and vocabulary.

        Distinct from topic overlap because keywords are what researchers choose to say about
        themselves, and two people can share a topic while working on it entirely differently.
        """
        if not source.keywords or not candidate.keywords:
            return 0.0, ()
        shared = source.keywords & candidate.keywords
        if not shared:
            return 0.0, ()
        union = source.keywords | candidate.keywords
        return round(_clamp(len(shared) / len(union)), 6), tuple(sorted(shared))

    # ── Confidence, tiering and explanation ──────────────────────────────────

    @classmethod
    def _compute_confidence(
        cls,
        source: TopicProfile,
        candidate: TopicProfile,
        shared_topics: tuple[str, ...],
        complementary_topics: tuple[str, ...],
        config: PeerMatchingConfig,
    ) -> float:
        """
        How much evidence the score rests on, kept separate from the score itself.

        A thin-profile match can still score highly by coincidence; reporting confidence lets a
        researcher discount that without the engine silently suppressing the suggestion.
        """
        evidence_volume = min(len(source.all_topics), len(candidate.all_topics))
        volume_factor = _clamp(evidence_volume / 8.0)
        overlap_factor = _clamp(len(shared_topics) / max(1, config.min_shared_topics_for_high_confidence))
        breadth_factor = _clamp((len(shared_topics) + len(complementary_topics)) / 6.0)
        return round(_clamp(0.45 * volume_factor + 0.35 * overlap_factor + 0.20 * breadth_factor), 6)

    @staticmethod
    def _classify_tier(score: float, config: PeerMatchingConfig) -> PeerMatchTier:
        if score >= config.strong_match_threshold:
            return PeerMatchTier.STRONG
        if score >= config.moderate_match_threshold:
            return PeerMatchTier.MODERATE
        return PeerMatchTier.EXPLORATORY

    @staticmethod
    def _readiness_explanation(status: str | None) -> str:
        return {
            "SEEKING_COLLABORATORS": "They are actively seeking collaborators.",
            "OPEN_TO_ENQUIRIES": "They are open to enquiries.",
            "SELECTIVELY_AVAILABLE": "They are selectively available.",
            "NOT_AVAILABLE": "They are not currently available for new collaborations.",
        }.get(status or "", "They have not stated their availability.")

    @classmethod
    def _build_reasons(
        cls,
        signals: Sequence[PeerMatchSignal],
        config: PeerMatchingConfig,
    ) -> tuple[str, ...]:
        """
        Orders explanations by how much each signal actually moved the score.

        A researcher reading this should see the reason that mattered most first, not a fixed
        template order that buries it.
        """
        contributing = [
            signal
            for signal in signals
            if abs(signal.weighted_contribution) > 1e-9 and signal.evidence
        ]
        contributing.sort(key=lambda s: -abs(s.weighted_contribution))
        reasons = [signal.explanation for signal in contributing]
        if not reasons:
            reasons = ["No individual signal contributed meaningfully to this suggestion."]
        return tuple(reasons[: config.max_explanation_reasons])

    @staticmethod
    def _join(items: Sequence[str], limit: int = 3) -> str:
        """Renders a topic list for prose, naming a few and counting the rest."""
        readable = [item.replace("-", " ") for item in items[:limit]]
        remainder = len(items) - len(readable)
        joined = ", ".join(readable)
        if remainder > 0:
            joined += f" and {remainder} more"
        return joined
