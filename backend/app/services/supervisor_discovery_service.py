"""
Phase 5.13 — Supervisor Discovery Service.

Finds faculty members whose research fits a student's interests, and hands the comparison to the
pure `SupervisorMatchingEngine`.

Consent and disclosure are exactly those of Phase 5.12 peer discovery, because the person being
suggested is the same:

  - A faculty member appears only if they set `is_discoverable` (on the Find Peers page) and are
    not NOT_AVAILABLE. No settings row means no consent, so they are absent, not defaulted in.
  - Institution and contact email are disclosed per their own field-level choices, through the
    peer service's serializer, so those choices are enforced in one place.

Reading never writes. No settings row, interest or intelligence record is created on a GET, which
is why `get_researcher_intelligence` (it recomputes and stores) is never called for candidates.

Zero N+1: candidates, interests, publications, publication topics, postings, the taxonomy and the
student's topic preferences each load in one bounded query, however many candidates there are.
"""
from __future__ import annotations

from collections import namedtuple
from dataclasses import replace
from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from app.models.research_knowledge import (
    ResearchWorkAuthorModel,
    ResearchWorkModel,
    ResearchWorkTopicModel,
)
from app.models.research_posting import PostingStatus, PostingType, ResearchPostingModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_discovery import (
    CollaborationStatus,
    ResearcherDiscoverySettingsModel,
)
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.personalization.peer_matching_engine import (
    PeerMatchAssessment,
    PeerMatchTier,
    TopicProfile,
)
from app.personalization.supervisor_matching_config import (
    DEFAULT_SUPERVISOR_MATCHING_CONFIG,
    SupervisorMatchingConfig,
)
from app.personalization.supervisor_matching_engine import (
    FacultyPaper,
    OpenPosting,
    SupervisionAvailability,
    SupervisorCandidate,
    SupervisorMatchAssessment,
    SupervisorMatchingEngine,
)
from app.schemas.researcher_discovery import PeerProfileSchema
from app.schemas.supervisor_discovery import (
    MatchingPaperSchema,
    OpenPostingRefSchema,
    SupervisorMatchResponse,
    SupervisorMatchSchema,
    SupervisorMatchSignalSchema,
)
from app.services.peer_discovery_service import PeerDiscoveryService
import os
import sys

# Ensure repository root is on sys.path for ml package imports
_root_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)

try:
    from ml.embeddings.service import get_embedding_service
except ImportError:
    get_embedding_service = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# `PeerDiscoveryService._load_topic_ancestors` reads only `.topic_slug` from each row, so topic
# slugs that come from publications and preferences are passed to it in this shape.
_SlugRef = namedtuple("_SlugRef", "topic_slug")


class SupervisorDiscoveryService:
    # Bounded so one student's search cannot pull the whole directory into memory.
    MAX_CANDIDATE_POOL = 500

    @classmethod
    def find_supervisors(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        *,
        limit: int | None = None,
        exclude_same_institution: bool = False,
        open_postings_only: bool = False,
        embedding_service: Any = None,
        config: SupervisorMatchingConfig | None = None,
        reference_time: datetime | None = None,
    ) -> SupervisorMatchResponse:
        """
        Finds and ranks discoverable faculty members for a student.

        Returns an explanatory empty result rather than a bare empty list: "no faculty member has
        opted in" and "your profile has too few topics" are different problems with different
        remedies, and a student seeing no matches deserves to know which one applies.
        """
        config = config or DEFAULT_SUPERVISOR_MATCHING_CONFIG
        peer_config = config.peer_config
        now = reference_time or datetime.now(timezone.utc)

        student_profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if student_profile is None:
            raise ValueError(f"Researcher profile '{profile_id}' not found.")

        # Candidate set, in one query: discoverable, active FACULTY accounts other than the
        # student. NOT_AVAILABLE faculty are excluded exactly as they are from peer results.
        candidate_rows = db.execute(
            select(ResearchProfileModel, ResearcherDiscoverySettingsModel)
            .join(
                ResearcherDiscoverySettingsModel,
                ResearcherDiscoverySettingsModel.profile_id == ResearchProfileModel.id,
            )
            .join(ResearchProfileModel.user)
            .options(contains_eager(ResearchProfileModel.user))
            .where(
                ResearcherDiscoverySettingsModel.is_discoverable.is_(True),
                ResearcherDiscoverySettingsModel.collaboration_status
                != CollaborationStatus.NOT_AVAILABLE.value,
                UserModel.role == "FACULTY",
                UserModel.is_active.is_(True),
                ResearchProfileModel.id != profile_id,
            )
            .order_by(ResearchProfileModel.id)
            .limit(cls.MAX_CANDIDATE_POOL)
        ).all()
        profiles_by_id = {profile.id: profile for profile, _ in candidate_rows}
        settings_by_profile = {profile.id: settings for profile, settings in candidate_rows}
        candidate_ids = list(profiles_by_id)

        interest_rows = PeerDiscoveryService._load_interests(db, [profile_id, *candidate_ids])
        student_interests = interest_rows.get(profile_id, [])
        preferred, preferred_labels, excluded = cls._load_topic_preferences(db, profile_id)

        # Topic count does not depend on the taxonomy, so sufficiency is decided before the
        # heavier loads; the profile is rebuilt with ancestors once they are known.
        student_topic_profile = cls._build_student_profile(
            student_profile, student_interests, preferred, {}, config
        )
        if len(student_topic_profile.all_topics) < config.min_topics_for_match:
            return cls._empty_response(
                profile_id,
                config,
                data_sufficiency="INSUFFICIENT_PROFILE",
                guidance=(
                    "Supervisor matching compares your research interests with faculty research, "
                    f"and your profile has fewer than {config.min_topics_for_match} topics. Add "
                    "keywords to your profile, choose preferred topics in your preferences, or "
                    "link your publications so your interests can be compared."
                ),
            )

        if not candidate_ids:
            return cls._empty_response(
                profile_id,
                config,
                data_sufficiency="NO_CANDIDATES",
                guidance=(
                    "No faculty members are currently discoverable. Supervisor discovery uses the "
                    "same opt-in as Find Peers, so faculty appear here once they choose to be "
                    "found there."
                ),
            )

        # Publications for the student and every candidate with a canonical author record.
        researcher_ids = {
            p.canonical_researcher_id
            for p in [student_profile, *profiles_by_id.values()]
            if p.canonical_researcher_id is not None
        }
        works_by_researcher, topics_by_work = cls._load_works(db, researcher_ids, config)
        postings_by_author = cls._load_open_postings(db, candidate_ids, config)

        extra_slugs = {slug for slugs in topics_by_work.values() for slug in slugs} | set(preferred)
        ancestor_sources: dict[Any, list[Any]] = dict(interest_rows)
        ancestor_sources["extra"] = [_SlugRef(slug) for slug in sorted(extra_slugs)]
        ancestors = PeerDiscoveryService._load_topic_ancestors(db, ancestor_sources)

        student_topic_profile = cls._build_student_profile(
            student_profile, student_interests, preferred, ancestors, config
        )
        own_works = works_by_researcher.get(student_profile.canonical_researcher_id, [])
        student_vector = cls._student_vector(
            [work["embedding"] for work in own_works],
            cls._interest_text(student_profile, student_interests, preferred_labels),
            embedding_service,
        )

        recent_cutoff = now.year - config.recent_years + 1
        source_institution = (student_profile.institution or "").strip().lower()
        candidates: list[SupervisorCandidate] = []
        for candidate_id in candidate_ids:
            profile = profiles_by_id[candidate_id]
            if exclude_same_institution and source_institution:
                if (profile.institution or "").strip().lower() == source_institution:
                    continue
            postings = postings_by_author.get(candidate_id, ())
            if open_postings_only and not postings:
                continue
            works = works_by_researcher.get(profile.canonical_researcher_id, [])
            settings = settings_by_profile[candidate_id]
            candidates.append(
                SupervisorCandidate(
                    faculty=cls._build_faculty_profile(
                        profile,
                        interest_rows.get(candidate_id, []),
                        works,
                        topics_by_work,
                        ancestors,
                        config,
                    ),
                    faculty_vector=cls._mean_vector([work["embedding"] for work in works]),
                    recent_papers=tuple(
                        FacultyPaper(
                            work_id=work["id"],
                            title=work["title"],
                            publication_year=work["publication_year"],
                            embedding=work["embedding"],
                            topics=frozenset(topics_by_work.get(work["id"], ())),
                            doi=work["doi"],
                            landing_page_url=work["landing_page_url"],
                        )
                        for work in works
                        if work["publication_year"] is not None
                        and work["publication_year"] >= recent_cutoff
                    ),
                    availability=SupervisionAvailability(
                        collaboration_status=settings.collaboration_status,
                        collaboration_interests=tuple(settings.collaboration_interests or ()),
                        open_postings=postings,
                    ),
                )
            )

        assessments = SupervisorMatchingEngine.rank_candidates(
            student_topic_profile,
            candidates,
            student_vector=student_vector,
            excluded_topics=excluded,
            config=config,
            limit=limit,
        )
        matches = [
            cls._build_match_schema(
                assessment,
                profiles_by_id[assessment.faculty_profile_id],
                settings_by_profile[assessment.faculty_profile_id],
                config,
            )
            for assessment in assessments
        ]

        guidance: str | None = None
        if not matches:
            if open_postings_only and not candidates:
                guidance = (
                    "No discoverable faculty member has an open thesis topic, project or research "
                    "assistantship right now. Clear the open postings filter to see every "
                    "discoverable supervisor."
                )
            else:
                guidance = (
                    "No faculty member passed the minimum match threshold. Adding keywords or "
                    "preferred topics to your profile widens the comparison."
                )

        return SupervisorMatchResponse(
            researcher_id=profile_id,
            matches=matches,
            total_candidates_evaluated=len(candidates),
            returned_count=len(matches),
            algorithm_version=config.algorithm_version,
            semantic_available=student_vector is not None,
            data_sufficiency="SUFFICIENT",
            guidance=guidance,
        )

    # ── Loading helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load_topic_preferences(
        db: Session,
        profile_id: uuid.UUID,
    ) -> tuple[dict[str, float], list[str], frozenset[str]]:
        """The student's active TOPIC preferences: PREFERRED slugs with strength, their labels,
        and EXCLUDED slugs, in one query."""
        rows = db.execute(
            select(
                ResearcherPreferenceModel.preference_type,
                ResearcherPreferenceModel.preference_value,
                ResearcherPreferenceModel.display_label,
                ResearcherPreferenceModel.strength,
            )
            .where(
                ResearcherPreferenceModel.profile_id == profile_id,
                ResearcherPreferenceModel.category == "TOPIC",
                ResearcherPreferenceModel.is_active.is_(True),
            )
            .order_by(ResearcherPreferenceModel.preference_value)
        ).all()
        preferred: dict[str, float] = {}
        labels: list[str] = []
        excluded: set[str] = set()
        for preference_type, value, label, strength in rows:
            slug = (value or "").strip().lower().replace(" ", "-")
            if not slug:
                continue
            if preference_type == "EXCLUDED":
                excluded.add(slug)
            elif preference_type == "PREFERRED":
                preferred[slug] = max(preferred.get(slug, 0.0), float(strength or 0.0))
                if label:
                    labels.append(label)
        return preferred, labels, frozenset(excluded)

    @staticmethod
    def _load_works(
        db: Session,
        researcher_ids: set[uuid.UUID],
        config: SupervisorMatchingConfig,
    ) -> tuple[dict[uuid.UUID, list[dict[str, Any]]], dict[uuid.UUID, set[str]]]:
        """
        Each author's most recent works, capped per author in SQL, and those works' topic slugs.

        Two queries for every author together. The cap is a window function rather than a
        per-author query, so a prolific author costs no more round trips than anyone else.
        """
        if not researcher_ids:
            return {}, {}
        ranked = (
            select(
                ResearchWorkAuthorModel.researcher_id.label("researcher_id"),
                ResearchWorkAuthorModel.work_id.label("work_id"),
                func.row_number()
                .over(
                    partition_by=ResearchWorkAuthorModel.researcher_id,
                    order_by=(
                        ResearchWorkModel.publication_year.desc().nulls_last(),
                        ResearchWorkModel.id,
                    ),
                )
                .label("position"),
            )
            .join(ResearchWorkModel, ResearchWorkModel.id == ResearchWorkAuthorModel.work_id)
            .where(ResearchWorkAuthorModel.researcher_id.in_(sorted(researcher_ids)))
            .subquery()
        )
        rows = db.execute(
            select(
                ranked.c.researcher_id,
                ResearchWorkModel.id,
                ResearchWorkModel.title,
                ResearchWorkModel.publication_year,
                ResearchWorkModel.doi,
                ResearchWorkModel.landing_page_url,
                ResearchWorkModel.embedding,
            )
            .select_from(ranked)
            .join(ResearchWorkModel, ResearchWorkModel.id == ranked.c.work_id)
            .where(ranked.c.position <= config.max_works_per_faculty)
            .order_by(ranked.c.researcher_id, ranked.c.position)
        ).all()

        works_by_researcher: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for researcher_id, work_id, title, year, doi, landing_page_url, embedding in rows:
            works_by_researcher.setdefault(researcher_id, []).append(
                {
                    "id": work_id,
                    "title": title,
                    "publication_year": year,
                    "doi": doi,
                    "landing_page_url": landing_page_url,
                    "embedding": embedding,
                }
            )
        if not works_by_researcher:
            return {}, {}

        topic_rows = db.execute(
            select(ResearchWorkTopicModel.work_id, TopicModel.slug)
            .join(TopicModel, TopicModel.id == ResearchWorkTopicModel.topic_id)
            .join(ranked, ranked.c.work_id == ResearchWorkTopicModel.work_id)
            .where(ranked.c.position <= config.max_works_per_faculty)
            .distinct()
        ).all()
        topics_by_work: dict[uuid.UUID, set[str]] = {}
        for work_id, slug in topic_rows:
            if slug:
                topics_by_work.setdefault(work_id, set()).add(slug)
        return works_by_researcher, topics_by_work

    @staticmethod
    def _load_open_postings(
        db: Session,
        candidate_ids: Sequence[uuid.UUID],
        config: SupervisorMatchingConfig,
    ) -> dict[uuid.UUID, tuple[OpenPosting, ...]]:
        """OPEN thesis topics, projects and assistantships, grouped by author, in one query."""
        rows = db.execute(
            select(
                ResearchPostingModel.author_profile_id,
                ResearchPostingModel.id,
                ResearchPostingModel.title,
                ResearchPostingModel.posting_type,
                ResearchPostingModel.application_deadline,
            )
            .where(
                ResearchPostingModel.author_profile_id.in_(list(candidate_ids)),
                ResearchPostingModel.status == PostingStatus.OPEN.value,
                ResearchPostingModel.posting_type.in_(config.supervision_posting_types),
            )
            .order_by(ResearchPostingModel.author_profile_id, ResearchPostingModel.id)
        ).all()
        grouped: dict[uuid.UUID, list[OpenPosting]] = {}
        for author_id, posting_id, title, posting_type, deadline in rows:
            grouped.setdefault(author_id, []).append(
                OpenPosting(
                    posting_id=posting_id,
                    title=title,
                    posting_type=posting_type,
                    application_deadline=deadline,
                )
            )
        return {author_id: tuple(postings) for author_id, postings in grouped.items()}

    # ── Profile building ─────────────────────────────────────────────────────

    @staticmethod
    def _build_student_profile(
        profile: ResearchProfileModel,
        interests: Sequence[ResearcherInterestModel],
        preferred: dict[str, float],
        ancestors: dict[str, frozenset[str]],
        config: SupervisorMatchingConfig,
    ) -> TopicProfile:
        """
        The peer topic profile, with the student's PREFERRED topics folded in as emerging
        interests. A student often has no publications yet, so the topics they chose are the
        clearest statement of what they want to work on.
        """
        peer_config = config.peer_config
        base = PeerDiscoveryService._build_topic_profile(profile, interests, ancestors, peer_config)
        emerging = dict(base.emerging)
        topic_ancestors = dict(base.ancestors)
        for slug, strength in preferred.items():
            if slug in base.expertise:
                continue
            # Never below the shared-topic floor: an explicit choice counts as a real interest.
            value = max(peer_config.min_shared_topic_strength, min(1.0, max(0.0, strength)))
            emerging[slug] = max(emerging.get(slug, 0.0), value)
            topic_ancestors.setdefault(slug, ancestors.get(slug, frozenset()))
        return replace(base, emerging=emerging, ancestors=topic_ancestors)

    @staticmethod
    def _build_faculty_profile(
        profile: ResearchProfileModel,
        interests: Sequence[ResearcherInterestModel],
        works: Sequence[dict[str, Any]],
        topics_by_work: dict[uuid.UUID, set[str]],
        ancestors: dict[str, frozenset[str]],
        config: SupervisorMatchingConfig,
    ) -> TopicProfile:
        """
        The peer topic profile. A faculty member with no interest rows (their intelligence has
        not been computed, and computing it here would write on a read) takes expertise from
        their works' topics instead: each topic's strength is how often it appears relative to
        their most frequent topic.
        """
        base = PeerDiscoveryService._build_topic_profile(
            profile, interests, ancestors, config.peer_config
        )
        if interests:
            return base
        counts: dict[str, int] = {}
        for work in works:
            for slug in topics_by_work.get(work["id"], ()):
                counts[slug] = counts.get(slug, 0) + 1
        if not counts:
            return base
        top = max(counts.values())
        expertise = {slug: round(count / top, 6) for slug, count in sorted(counts.items())}
        topic_ancestors = dict(base.ancestors)
        for slug in expertise:
            topic_ancestors[slug] = ancestors.get(slug, frozenset())
        return replace(base, expertise=expertise, ancestors=topic_ancestors)

    # ── Embeddings ───────────────────────────────────────────────────────────

    @staticmethod
    def _mean_vector(embeddings: Sequence[Any]) -> np.ndarray | None:
        """Mean of the stored embeddings; the engine re-normalises it before any cosine."""
        arrays = [
            np.asarray(embedding, dtype=np.float64).ravel()
            for embedding in embeddings
            if embedding is not None
        ]
        arrays = [array for array in arrays if array.size]
        if not arrays:
            return None
        shape = arrays[0].shape
        return np.mean(np.vstack([array for array in arrays if array.shape == shape]), axis=0)

    @staticmethod
    def _interest_text(
        profile: ResearchProfileModel,
        interests: Sequence[ResearcherInterestModel],
        preferred_labels: Sequence[str],
    ) -> str:
        """Sorted keywords, topic names and preferred-topic labels: the same text every time."""
        keywords = sorted({kw.strip().lower() for kw in profile.keywords or [] if kw and kw.strip()})
        topic_names = sorted(
            {(row.topic_name or "").strip() for row in interests if (row.topic_name or "").strip()}
        )
        labels = sorted({label.strip() for label in preferred_labels if label and label.strip()})
        return ". ".join(", ".join(group) for group in (keywords, topic_names, labels) if group)

    @classmethod
    def _student_vector(
        cls,
        own_embeddings: Sequence[Any],
        interest_text: str,
        embedding_service: Any,
    ) -> Any:
        """
        The mean of the student's own embedded works, otherwise their interest text encoded by
        the injected or process-wide embedding service. None when neither is possible, in which
        case every match is scored on topics and says so.
        """
        mean = cls._mean_vector(own_embeddings)
        if mean is not None:
            return mean
        if not interest_text:
            return None
        service = embedding_service
        if service is None and get_embedding_service is not None:
            service = get_embedding_service()
        if service is None:
            return None
        try:
            return service.encode_one(interest_text)
        except Exception as exc:  # the model may be missing or fail to load
            logger.warning(
                "Supervisor matching could not embed a student's interests (%s); "
                "scoring on research topics only",
                type(exc).__name__,
            )
            return None

    # ── Serialization ────────────────────────────────────────────────────────

    @staticmethod
    def _empty_response(
        profile_id: uuid.UUID,
        config: SupervisorMatchingConfig,
        *,
        data_sufficiency: str,
        guidance: str,
    ) -> SupervisorMatchResponse:
        return SupervisorMatchResponse(
            researcher_id=profile_id,
            matches=[],
            total_candidates_evaluated=0,
            returned_count=0,
            algorithm_version=config.algorithm_version,
            semantic_available=False,
            data_sufficiency=data_sufficiency,
            guidance=guidance,
        )

    @staticmethod
    def _disclosed_profile(
        profile: ResearchProfileModel,
        settings: ResearcherDiscoverySettingsModel,
        config: SupervisorMatchingConfig,
    ) -> PeerProfileSchema:
        """
        The faculty member's profile exactly as peer discovery would show it.

        Built through the peer service's serializer, the single place disclosure choices are
        enforced, so supervisor results cannot show a field that peer results would hide. Only
        its `peer` part is used; the neutral assessment carries no score.
        """
        neutral = PeerMatchAssessment(
            source_profile_id=profile.id,
            candidate_profile_id=profile.id,
            match_score=0.0,
            tier=PeerMatchTier.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            signals=(),
            shared_topics=(),
            complementary_topics=(),
            explanation_reasons=(),
            algorithm_version=config.algorithm_version,
        )
        return PeerDiscoveryService._build_match_schema(neutral, profile, settings).peer

    @classmethod
    def _build_match_schema(
        cls,
        assessment: SupervisorMatchAssessment,
        profile: ResearchProfileModel,
        settings: ResearcherDiscoverySettingsModel,
        config: SupervisorMatchingConfig,
    ) -> SupervisorMatchSchema:
        return SupervisorMatchSchema(
            supervisor=cls._disclosed_profile(profile, settings, config),
            match_score=assessment.match_score,
            tier=assessment.tier,
            confidence=assessment.confidence,
            shared_topics=list(assessment.shared_topics),
            matching_papers=[
                MatchingPaperSchema(
                    work_id=paper.work_id,
                    title=paper.title,
                    publication_year=paper.publication_year,
                    similarity=paper.similarity,
                    shared_topics=list(paper.shared_topics),
                    doi=paper.doi,
                    landing_page_url=paper.landing_page_url,
                )
                for paper in assessment.matching_papers
            ],
            open_postings=[
                OpenPostingRefSchema(
                    posting_id=posting.posting_id,
                    title=posting.title,
                    posting_type=PostingType(posting.posting_type),
                    application_deadline=posting.application_deadline,
                )
                for posting in assessment.open_postings
            ],
            signals=[
                SupervisorMatchSignalSchema(
                    signal_type=signal.signal_type,
                    raw_score=signal.raw_score,
                    weight=signal.weight,
                    weighted_contribution=signal.weighted_contribution,
                    evidence=[e for e in signal.evidence if e],
                    explanation=signal.explanation,
                )
                for signal in assessment.signals
            ],
            explanation_reasons=list(assessment.explanation_reasons),
        )
