"""
Phase 5.13 — Supervisor Matching Engine.

A pure, deterministic engine: given a student's topic profile and one faculty member's topics,
recent papers and availability, it produces a bounded score and a structured explanation. It
does no database access, no network and no model inference: any embedding is computed by the
caller and passed in, so identical inputs always yield an identical result.

The scoring law has five weighted signals and one penalty:

  Topic fit                 research topics both hold at real strength
  Semantic fit              closeness in meaning of the student's and the faculty member's
                            mean embeddings
  Recent paper evidence     how closely the faculty member's recent papers match the student
  Taxonomy proximity        related, not identical, topics
  Supervision availability  an open thesis topic, project or assistantship, else stated readiness
  Excluded-topic penalty    faculty topics the student explicitly excluded

Topic fit and taxonomy proximity reuse the Phase 5.12 peer scorers, so a topic counts as shared,
and two fields as related, by exactly the same rule on both surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Sequence
import uuid

import numpy as np

from app.personalization.peer_matching_engine import (
    PeerMatchingEngine,
    PeerMatchTier,
    TopicProfile,
)
from app.personalization.supervisor_matching_config import (
    DEFAULT_SUPERVISOR_MATCHING_CONFIG,
    SupervisorMatchingConfig,
)


class SupervisorSignalType(str, Enum):
    TOPIC_FIT = "TOPIC_FIT"
    SEMANTIC_FIT = "SEMANTIC_FIT"
    RECENT_PAPER_EVIDENCE = "RECENT_PAPER_EVIDENCE"
    TAXONOMY_PROXIMITY = "TAXONOMY_PROXIMITY"
    SUPERVISION_AVAILABILITY = "SUPERVISION_AVAILABILITY"
    EXCLUDED_TOPIC_PENALTY = "EXCLUDED_TOPIC_PENALTY"


@dataclass(frozen=True)
class FacultyPaper:
    """One of a faculty member's recent papers, normalized away from the ORM."""

    work_id: uuid.UUID
    title: str
    publication_year: int | None = None
    # The stored embedding (a list or a numpy array), or None when the work has none yet.
    embedding: Any = field(default=None, compare=False)
    topics: frozenset[str] = frozenset()
    doi: str | None = None
    landing_page_url: str | None = None


@dataclass(frozen=True)
class OpenPosting:
    """An OPEN research posting authored by the faculty member."""

    posting_id: uuid.UUID
    title: str
    posting_type: str
    application_deadline: datetime | None = None


@dataclass(frozen=True)
class SupervisionAvailability:
    """What the faculty member has said about taking on students."""

    collaboration_status: str | None = None
    collaboration_interests: tuple[str, ...] = ()
    open_postings: tuple[OpenPosting, ...] = ()


@dataclass(frozen=True)
class SupervisorCandidate:
    """Everything the engine needs about one faculty member."""

    faculty: TopicProfile
    # Mean embedding of their publications, or None when none is embedded.
    faculty_vector: Any = field(default=None, compare=False)
    recent_papers: tuple[FacultyPaper, ...] = ()
    availability: SupervisionAvailability = field(default_factory=SupervisionAvailability)


@dataclass(frozen=True)
class MatchingPaper:
    """A recent paper offered as evidence of fit, with how closely it matched."""

    work_id: uuid.UUID
    title: str
    publication_year: int | None
    similarity: float
    shared_topics: tuple[str, ...]
    doi: str | None = None
    landing_page_url: str | None = None


@dataclass(frozen=True)
class SupervisorMatchSignal:
    """One scored contribution, with the evidence that produced it."""

    signal_type: SupervisorSignalType
    raw_score: float
    weight: float
    weighted_contribution: float
    evidence: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class SupervisorMatchAssessment:
    """The complete, explainable outcome of comparing a student with one faculty member."""

    student_profile_id: uuid.UUID
    faculty_profile_id: uuid.UUID
    match_score: float
    tier: PeerMatchTier
    confidence: float
    signals: tuple[SupervisorMatchSignal, ...]
    shared_topics: tuple[str, ...]
    matching_papers: tuple[MatchingPaper, ...]
    open_postings: tuple[OpenPosting, ...]
    explanation_reasons: tuple[str, ...]
    algorithm_version: str


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _unit_vector(vector: Any) -> np.ndarray | None:
    """
    The vector scaled to unit length, or None when it is missing, empty, zero or not finite.

    A mean of unit embeddings is shorter than unit length, so every vector is re-normalised here
    before a dot product is read as a cosine. Arrays are tested with `is None`, never for truth.
    """
    if vector is None:
        return None
    array = np.asarray(vector, dtype=np.float64).ravel()
    if array.size == 0 or not np.all(np.isfinite(array)):
        return None
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        return None
    return array / norm


def _cosine(a: np.ndarray | None, b: np.ndarray | None) -> float | None:
    """Cosine of two unit vectors clamped to [0, 1], or None when they cannot be compared."""
    if a is None or b is None or a.shape != b.shape:
        return None
    return round(_clamp(float(np.dot(a, b))), 6)


class SupervisorMatchingEngine:
    """Deterministic supervisor matcher for students."""

    @classmethod
    def score_pair(
        cls,
        student: TopicProfile,
        faculty: TopicProfile,
        *,
        student_vector: Any = None,
        faculty_vector: Any = None,
        recent_papers: Sequence[FacultyPaper] = (),
        availability: SupervisionAvailability | None = None,
        excluded_topics: frozenset[str] | set[str] = frozenset(),
        config: SupervisorMatchingConfig = DEFAULT_SUPERVISOR_MATCHING_CONFIG,
    ) -> SupervisorMatchAssessment:
        """
        Scores one faculty member for one student.

        Returns an INSUFFICIENT_EVIDENCE assessment with a zero score when the student has too
        few topics, or the faculty member has too few topics and no embedding to compare by
        meaning instead, rather than inventing confidence from one chance overlap.
        """
        if availability is None:
            availability = SupervisionAvailability()
        student_unit = _unit_vector(student_vector)
        faculty_unit = _unit_vector(faculty_vector)
        semantic = _cosine(student_unit, faculty_unit)

        if len(student.all_topics) < config.min_topics_for_match or (
            len(faculty.all_topics) < config.min_topics_for_match and semantic is None
        ):
            return SupervisorMatchAssessment(
                student_profile_id=student.profile_id,
                faculty_profile_id=faculty.profile_id,
                match_score=0.0,
                tier=PeerMatchTier.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                signals=(),
                shared_topics=(),
                matching_papers=(),
                open_postings=(),
                explanation_reasons=(
                    "Not enough recorded research topics on one or both profiles to compare "
                    "research fit meaningfully.",
                ),
                algorithm_version=config.algorithm_version,
            )

        signals: list[SupervisorMatchSignal] = []
        peer_config = config.peer_config

        # The peer matcher's private topic scorers are called deliberately rather than copied:
        # a topic counts as shared, and two fields as related, by the same rule on both surfaces.
        topic_score, shared_topics = PeerMatchingEngine._score_shared_expertise(
            student, faculty, peer_config
        )
        signals.append(
            cls._signal(
                SupervisorSignalType.TOPIC_FIT,
                topic_score,
                config.topic_fit_weight,
                shared_topics,
                (
                    f"You share research topics: {PeerMatchingEngine._join(shared_topics)}."
                    if shared_topics
                    else "None of their research topics matches yours closely enough to count "
                    "as shared."
                ),
            )
        )

        if semantic is None:
            signals.append(
                cls._signal(
                    SupervisorSignalType.SEMANTIC_FIT,
                    0.0,
                    config.semantic_fit_weight,
                    (),
                    cls._semantic_unavailable_reason(student_unit, faculty_unit),
                )
            )
        else:
            signals.append(
                cls._signal(
                    SupervisorSignalType.SEMANTIC_FIT,
                    semantic,
                    config.semantic_fit_weight,
                    (f"similarity {semantic:.2f}",),
                    (
                        f"Your interests and their publications are close in meaning "
                        f"(similarity {semantic:.2f})."
                        if semantic >= config.min_paper_similarity
                        else f"Your interests and their publications are only loosely related "
                        f"in meaning (similarity {semantic:.2f})."
                    ),
                )
            )

        paper_score, matching_papers, by_meaning = cls._score_recent_papers(
            student, student_unit, recent_papers, config
        )
        signals.append(
            cls._signal(
                SupervisorSignalType.RECENT_PAPER_EVIDENCE,
                paper_score,
                config.recent_paper_evidence_weight,
                tuple(paper.title for paper in matching_papers),
                cls._paper_explanation(matching_papers, by_meaning, bool(recent_papers), config),
            )
        )

        taxonomy_score, taxonomy_evidence = PeerMatchingEngine._score_taxonomy_proximity(
            student, faculty, peer_config
        )
        signals.append(
            cls._signal(
                SupervisorSignalType.TAXONOMY_PROXIMITY,
                taxonomy_score,
                config.taxonomy_proximity_weight,
                taxonomy_evidence,
                (
                    f"Their fields sit close to yours in the research taxonomy "
                    f"({PeerMatchingEngine._join(taxonomy_evidence)})."
                    if taxonomy_evidence
                    else "Their fields are not closely related to yours in the research taxonomy."
                ),
            )
        )

        open_postings = cls._supervision_postings(availability, config)
        availability_score, availability_evidence, availability_explanation = (
            cls._score_availability(availability, open_postings, config)
        )
        signals.append(
            cls._signal(
                SupervisorSignalType.SUPERVISION_AVAILABILITY,
                availability_score,
                config.supervision_availability_weight,
                availability_evidence,
                availability_explanation,
            )
        )

        base_score = sum(signal.weighted_contribution for signal in signals)

        # A topic the student excluded counts against a faculty member who works on it, once per
        # topic, without removing them: the rest of their research may still fit.
        excluded_hits = tuple(sorted(set(faculty.all_topics) & set(excluded_topics)))
        penalty = round(config.excluded_topic_penalty * len(excluded_hits), 6)
        if excluded_hits:
            signals.append(
                SupervisorMatchSignal(
                    signal_type=SupervisorSignalType.EXCLUDED_TOPIC_PENALTY,
                    raw_score=float(len(excluded_hits)),
                    weight=config.excluded_topic_penalty,
                    weighted_contribution=-penalty,
                    evidence=excluded_hits,
                    explanation=(
                        f"They also work on {PeerMatchingEngine._join(excluded_hits)}, "
                        "which you excluded."
                    ),
                )
            )

        match_score = round(_clamp(base_score - penalty), 6)
        confidence = cls._compute_confidence(
            student, faculty, shared_topics, semantic, matching_papers, config
        )

        return SupervisorMatchAssessment(
            student_profile_id=student.profile_id,
            faculty_profile_id=faculty.profile_id,
            match_score=match_score,
            tier=cls._classify_tier(match_score, config),
            confidence=confidence,
            signals=tuple(signals),
            shared_topics=shared_topics,
            matching_papers=matching_papers,
            open_postings=open_postings[: config.max_open_postings],
            explanation_reasons=cls._build_reasons(signals, semantic is not None, config),
            algorithm_version=config.algorithm_version,
        )

    @classmethod
    def rank_candidates(
        cls,
        student: TopicProfile,
        candidates: Sequence[SupervisorCandidate],
        *,
        student_vector: Any = None,
        excluded_topics: frozenset[str] | set[str] = frozenset(),
        config: SupervisorMatchingConfig = DEFAULT_SUPERVISOR_MATCHING_CONFIG,
        limit: int | None = None,
    ) -> list[SupervisorMatchAssessment]:
        """
        Scores and orders faculty candidates.

        Self-matches are dropped, results below `min_match_score` are omitted, and ties break on
        confidence then profile id so the ordering is stable across identical runs.
        """
        assessments = [
            cls.score_pair(
                student,
                candidate.faculty,
                student_vector=student_vector,
                faculty_vector=candidate.faculty_vector,
                recent_papers=candidate.recent_papers,
                availability=candidate.availability,
                excluded_topics=excluded_topics,
                config=config,
            )
            for candidate in candidates
            if candidate.faculty.profile_id != student.profile_id
        ]
        eligible = [
            assessment
            for assessment in assessments
            if assessment.match_score >= config.min_match_score
            and assessment.tier != PeerMatchTier.INSUFFICIENT_EVIDENCE
        ]
        eligible.sort(
            key=lambda a: (-a.match_score, -a.confidence, str(a.faculty_profile_id))
        )
        effective_limit = limit if limit is not None else config.default_limit
        return eligible[: max(0, min(effective_limit, config.max_limit))]

    # ── Individual signals ───────────────────────────────────────────────────

    @staticmethod
    def _signal(
        signal_type: SupervisorSignalType,
        raw_score: float,
        weight: float,
        evidence: tuple[str, ...],
        explanation: str,
    ) -> SupervisorMatchSignal:
        return SupervisorMatchSignal(
            signal_type=signal_type,
            raw_score=raw_score,
            weight=weight,
            weighted_contribution=round(raw_score * weight, 6),
            evidence=evidence,
            explanation=explanation,
        )

    @classmethod
    def _score_recent_papers(
        cls,
        student: TopicProfile,
        student_unit: np.ndarray | None,
        papers: Sequence[FacultyPaper],
        config: SupervisorMatchingConfig,
    ) -> tuple[float, tuple[MatchingPaper, ...], bool]:
        """
        Mean similarity of the closest recent papers, and those papers.

        Similarity is the cosine to the student's embedding when the student and at least one
        paper have one; otherwise it falls back to the share of a paper's topics the student
        holds. Papers below `min_paper_similarity` are not evidence. Returns whether similarity
        was measured by meaning, so the explanation can say which.
        """
        student_topics = set(student.all_topics)
        units = [(paper, _unit_vector(paper.embedding)) for paper in papers]
        by_meaning = student_unit is not None and any(unit is not None for _, unit in units)

        scored: list[MatchingPaper] = []
        for paper, unit in units:
            if by_meaning:
                similarity = _cosine(student_unit, unit)
                if similarity is None:
                    continue
            else:
                if not paper.topics:
                    continue
                similarity = round(len(paper.topics & student_topics) / len(paper.topics), 6)
            if similarity < config.min_paper_similarity:
                continue
            scored.append(
                MatchingPaper(
                    work_id=paper.work_id,
                    title=paper.title,
                    publication_year=paper.publication_year,
                    similarity=similarity,
                    shared_topics=tuple(sorted(paper.topics & student_topics)),
                    doi=paper.doi,
                    landing_page_url=paper.landing_page_url,
                )
            )

        scored.sort(key=lambda p: (-p.similarity, -(p.publication_year or 0), str(p.work_id)))
        top = tuple(scored[: config.max_matching_papers])
        if not top:
            return 0.0, (), by_meaning
        return round(_clamp(sum(p.similarity for p in top) / len(top)), 6), top, by_meaning

    @staticmethod
    def _supervision_postings(
        availability: SupervisionAvailability,
        config: SupervisorMatchingConfig,
    ) -> tuple[OpenPosting, ...]:
        """Open postings of a supervision type, soonest deadline first, open-ended last."""
        postings = [
            posting
            for posting in availability.open_postings
            if posting.posting_type in config.supervision_posting_types
        ]
        postings.sort(
            key=lambda p: (
                p.application_deadline is None,
                p.application_deadline or datetime.min,
                p.title,
                str(p.posting_id),
            )
        )
        return tuple(postings)

    @staticmethod
    def _score_availability(
        availability: SupervisionAvailability,
        open_postings: tuple[OpenPosting, ...],
        config: SupervisorMatchingConfig,
    ) -> tuple[float, tuple[str, ...], str]:
        """
        An open thesis topic, project or assistantship is a concrete offer and scores 1.0.
        Otherwise the faculty member's stated readiness counts, raised when they list student
        co-supervision or mentorship among the collaboration they will consider.
        """
        if open_postings:
            count = len(open_postings)
            titles = tuple(posting.title for posting in open_postings)
            named = "; ".join(titles[:2])
            more = f" and {count - 2} more" if count > 2 else ""
            noun = "posting" if count == 1 else "postings"
            return 1.0, titles, f"They have {count} open {noun} for students: {named}{more}."

        status = availability.collaboration_status
        score = config.peer_config.readiness_scores.get(status or "", 0.0)
        evidence: list[str] = [status] if status else []
        # The peer readiness wording is reused so availability reads the same on both surfaces.
        explanation = PeerMatchingEngine._readiness_explanation(status)
        supervising = sorted(
            set(availability.collaboration_interests) & set(config.supervision_interests)
        )
        if supervising:
            score += config.supervision_interest_bonus
            evidence.extend(supervising)
            readable = " and ".join(interest.replace("_", " ").lower() for interest in supervising)
            explanation += f" They are open to {readable}."
        return round(_clamp(score), 6), tuple(evidence), explanation

    # ── Confidence, tiering and explanation ──────────────────────────────────

    @staticmethod
    def _compute_confidence(
        student: TopicProfile,
        faculty: TopicProfile,
        shared_topics: tuple[str, ...],
        semantic: float | None,
        matching_papers: tuple[MatchingPaper, ...],
        config: SupervisorMatchingConfig,
    ) -> float:
        """
        How much evidence the score rests on, kept separate from the score itself: topic volume,
        topic overlap, whether meaning could be compared, and how many papers back the match.
        """
        volume_factor = _clamp(min(len(student.all_topics), len(faculty.all_topics)) / 8.0)
        overlap_factor = _clamp(
            len(shared_topics) / max(1, config.peer_config.min_shared_topics_for_high_confidence)
        )
        semantic_factor = 1.0 if semantic is not None else 0.0
        paper_factor = _clamp(len(matching_papers) / max(1, config.max_matching_papers))
        return round(
            _clamp(
                0.30 * volume_factor
                + 0.30 * overlap_factor
                + 0.20 * semantic_factor
                + 0.20 * paper_factor
            ),
            6,
        )

    @staticmethod
    def _classify_tier(score: float, config: SupervisorMatchingConfig) -> PeerMatchTier:
        if score >= config.strong_match_threshold:
            return PeerMatchTier.STRONG
        if score >= config.moderate_match_threshold:
            return PeerMatchTier.MODERATE
        return PeerMatchTier.EXPLORATORY

    @staticmethod
    def _semantic_unavailable_reason(
        student_unit: np.ndarray | None,
        faculty_unit: np.ndarray | None,
    ) -> str:
        if student_unit is None and faculty_unit is None:
            cause = "Neither your interests nor their publications have an embedding"
        elif student_unit is None:
            cause = "Your interests could not be embedded"
        elif faculty_unit is None:
            cause = "None of their publications has an embedding yet"
        else:
            cause = "Your embedding and theirs come from different models"
        return f"{cause}, so this match is scored on research topics only."

    @staticmethod
    def _paper_explanation(
        matching_papers: tuple[MatchingPaper, ...],
        by_meaning: bool,
        has_recent_papers: bool,
        config: SupervisorMatchingConfig,
    ) -> str:
        if matching_papers:
            count = len(matching_papers)
            closest = matching_papers[0]
            year = f" ({closest.publication_year})" if closest.publication_year else ""
            how = "are close in meaning to your interests" if by_meaning else "share your topics"
            noun = "paper" if count == 1 else "papers"
            return (
                f"{count} of their recent {noun} {how}; the closest is "
                f'"{closest.title}"{year}.'
            )
        if not has_recent_papers:
            return f"They have no papers from the last {config.recent_years} years on record."
        return "None of their recent papers is close enough to your interests to count."

    @classmethod
    def _build_reasons(
        cls,
        signals: Sequence[SupervisorMatchSignal],
        semantic_available: bool,
        config: SupervisorMatchingConfig,
    ) -> tuple[str, ...]:
        """
        Orders explanations by how much each signal moved the score, largest first. When meaning
        could not be compared, that is always stated last, so a topic-only match says so.
        """
        contributing = [
            signal
            for signal in signals
            if abs(signal.weighted_contribution) > 1e-9 and signal.evidence
        ]
        contributing.sort(key=lambda s: -abs(s.weighted_contribution))
        reasons = [signal.explanation for signal in contributing]
        limit = config.max_explanation_reasons
        if not semantic_available:
            note = next(
                s.explanation for s in signals if s.signal_type == SupervisorSignalType.SEMANTIC_FIT
            )
            reasons = reasons[: limit - 1] + [note]
        if not reasons:
            reasons = ["No individual signal contributed meaningfully to this suggestion."]
        return tuple(reasons[:limit])
