"""
Phase 5.12 — Peer & Co-Author Discovery Service.

Loads researcher topic profiles, applies the consent rules, and hands the comparison to the pure
`PeerMatchingEngine`.

Consent is the defining constraint of this surface, because the thing being matched is a person:

  - A researcher appears in results only if they set `is_discoverable`. No settings row means no
    consent, so they are absent, not defaulted in.
  - A researcher who has not opted in may still search. Discoverability governs being *found*,
    and forcing someone to publish themselves before they can look would be coercive.
  - Institution and contact email are disclosed per that researcher's own field-level choices.

Zero N+1: candidate profiles, their interests and their settings load in three bounded queries
regardless of how many candidates there are.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.researcher_discovery import (
    CollaborationInterest,
    CollaborationStatus,
    ResearcherDiscoverySettingsModel,
)
from app.models.researcher_interest import ResearcherInterestModel
from app.models.research_profile import ResearchProfileModel
from app.models.topic import TopicModel
from app.personalization.peer_matching_config import (
    DEFAULT_PEER_MATCHING_CONFIG,
    PeerMatchingConfig,
)
from app.personalization.peer_matching_engine import (
    PeerMatchAssessment,
    PeerMatchingEngine,
    TopicProfile,
)
from app.schemas.researcher_discovery import (
    DiscoverySettingsSchema,
    DiscoverySettingsUpdate,
    PeerMatchResponse,
    PeerMatchSchema,
    PeerMatchSignalSchema,
    PeerProfileSchema,
)

logger = logging.getLogger(__name__)


class PeerDiscoveryService:
    # Bounded so one researcher's search cannot pull the whole directory into memory.
    MAX_CANDIDATE_POOL = 500

    # ── Settings ─────────────────────────────────────────────────────────────

    @classmethod
    def load_settings(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> ResearcherDiscoverySettingsModel | None:
        """Read-only lookup. None means the researcher has never made a choice."""
        return db.execute(
            select(ResearcherDiscoverySettingsModel).where(
                ResearcherDiscoverySettingsModel.profile_id == profile_id
            )
        ).scalar_one_or_none()

    @classmethod
    def get_settings(cls, db: Session, profile_id: uuid.UUID) -> DiscoverySettingsSchema:
        """
        Returns the researcher's settings, or the not-discoverable defaults if they have none.

        Deliberately does not create a row: reading one's own settings is not consent, and a
        GET that writes would make the consent timestamp meaningless.
        """
        settings = cls.load_settings(db, profile_id)
        if settings is None:
            return DiscoverySettingsSchema(
                profile_id=profile_id,
                is_discoverable=False,
                collaboration_status=CollaborationStatus.OPEN_TO_ENQUIRIES,
                collaboration_interests=[],
            )
        return cls._build_settings_schema(settings)

    @classmethod
    def update_settings(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        payload: DiscoverySettingsUpdate,
        reference_time: datetime | None = None,
    ) -> DiscoverySettingsSchema:
        """
        Applies a settings change, creating the row on first use.

        `consent_updated_at` is stamped only when discoverability itself changes, so it records
        when the researcher agreed to be found rather than when they last edited a note.
        """
        now = reference_time or datetime.now(timezone.utc)
        settings = cls.load_settings(db, profile_id)
        if settings is None:
            settings = ResearcherDiscoverySettingsModel(
                id=uuid.uuid4(),
                profile_id=profile_id,
                is_discoverable=False,
                collaboration_status=CollaborationStatus.OPEN_TO_ENQUIRIES.value,
                collaboration_interests=[],
            )
            db.add(settings)
            db.flush()

        data = payload.model_dump(exclude_unset=True)
        if "is_discoverable" in data and data["is_discoverable"] != settings.is_discoverable:
            settings.consent_updated_at = now

        for field, value in data.items():
            if field == "collaboration_status" and value is not None:
                settings.collaboration_status = (
                    value.value if hasattr(value, "value") else str(value)
                )
            elif field == "collaboration_interests" and value is not None:
                settings.collaboration_interests = [
                    item.value if hasattr(item, "value") else str(item) for item in value
                ]
            else:
                setattr(settings, field, value)

        db.commit()
        db.refresh(settings)
        logger.info(
            "Peer discovery settings updated",
            extra={
                "profile_id": str(profile_id),
                "is_discoverable": settings.is_discoverable,
                "collaboration_status": settings.collaboration_status,
            },
        )
        return cls._build_settings_schema(settings)

    # ── Peer matching ────────────────────────────────────────────────────────

    @classmethod
    def find_peers(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        *,
        limit: int | None = None,
        collaboration_interest: CollaborationInterest | None = None,
        exclude_same_institution: bool = False,
        config: PeerMatchingConfig = DEFAULT_PEER_MATCHING_CONFIG,
    ) -> PeerMatchResponse:
        """
        Finds and ranks discoverable peers for a researcher.

        Returns an explanatory empty result rather than a bare empty list: "nobody has opted in"
        and "your profile has too few topics" are different problems with different remedies, and
        a researcher seeing no matches deserves to know which one applies.
        """
        source_profile = db.execute(
            select(ResearchProfileModel)
            .options(joinedload(ResearchProfileModel.user))
            .where(ResearchProfileModel.id == profile_id)
        ).unique().scalar_one_or_none()
        if source_profile is None:
            raise ValueError(f"Researcher profile '{profile_id}' not found.")

        own_settings = cls.load_settings(db, profile_id)
        is_discoverable = bool(own_settings and own_settings.is_discoverable)

        # Candidate set: discoverable researchers other than the requester. NOT_AVAILABLE peers
        # are excluded because scoring them would be wasted work, since readiness is 0.0 and the
        # result would fall below the minimum score anyway.
        candidate_settings_rows = (
            db.execute(
                select(ResearcherDiscoverySettingsModel)
                .where(
                    ResearcherDiscoverySettingsModel.is_discoverable.is_(True),
                    ResearcherDiscoverySettingsModel.profile_id != profile_id,
                    ResearcherDiscoverySettingsModel.collaboration_status
                    != CollaborationStatus.NOT_AVAILABLE.value,
                )
                .limit(cls.MAX_CANDIDATE_POOL)
            )
            .scalars()
            .all()
        )

        if collaboration_interest is not None:
            wanted = collaboration_interest.value
            candidate_settings_rows = [
                row
                for row in candidate_settings_rows
                if wanted in (row.collaboration_interests or [])
            ]

        candidate_ids = [row.profile_id for row in candidate_settings_rows]
        settings_by_profile = {row.profile_id: row for row in candidate_settings_rows}

        # Two bounded queries cover every candidate's profile and topical footprint.
        profiles_by_id: dict[uuid.UUID, ResearchProfileModel] = {}
        if candidate_ids:
            profiles_by_id = {
                p.id: p
                for p in db.execute(
                    select(ResearchProfileModel)
                    .options(joinedload(ResearchProfileModel.user))
                    .where(ResearchProfileModel.id.in_(candidate_ids))
                )
                .unique()
                .scalars()
                .all()
            }

        interest_rows = cls._load_interests(db, [profile_id, *candidate_ids])
        ancestors = cls._load_topic_ancestors(db, interest_rows)

        source_topic_profile = cls._build_topic_profile(
            source_profile, interest_rows.get(profile_id, []), ancestors, config
        )

        if len(source_topic_profile.all_topics) < config.min_topics_for_match:
            return PeerMatchResponse(
                researcher_id=profile_id,
                matches=[],
                total_candidates_evaluated=0,
                returned_count=0,
                algorithm_version=config.algorithm_version,
                is_discoverable=is_discoverable,
                data_sufficiency="INSUFFICIENT_PROFILE",
                guidance=(
                    "Peer matching compares recorded research topics, and your profile has fewer "
                    f"than {config.min_topics_for_match}. Add keywords to your profile or link "
                    "your publications so your expertise can be compared."
                ),
            )

        if not candidate_ids:
            return PeerMatchResponse(
                researcher_id=profile_id,
                matches=[],
                total_candidates_evaluated=0,
                returned_count=0,
                algorithm_version=config.algorithm_version,
                is_discoverable=is_discoverable,
                data_sufficiency="NO_CANDIDATES",
                guidance=(
                    "No other researchers are currently discoverable. Peer discovery is opt-in, "
                    "so results appear as colleagues choose to be found."
                ),
            )

        candidates: list[tuple[TopicProfile, str | None]] = []
        source_institution = (source_profile.institution or "").strip().lower()
        for candidate_id in candidate_ids:
            candidate_profile = profiles_by_id.get(candidate_id)
            if candidate_profile is None:
                continue
            if exclude_same_institution and source_institution:
                if (candidate_profile.institution or "").strip().lower() == source_institution:
                    continue
            candidates.append(
                (
                    cls._build_topic_profile(
                        candidate_profile, interest_rows.get(candidate_id, []), ancestors, config
                    ),
                    settings_by_profile[candidate_id].collaboration_status,
                )
            )

        assessments = PeerMatchingEngine.rank_candidates(
            source_topic_profile, candidates, config=config, limit=limit
        )

        matches = [
            cls._build_match_schema(
                assessment,
                profiles_by_id[assessment.candidate_profile_id],
                settings_by_profile[assessment.candidate_profile_id],
            )
            for assessment in assessments
            if assessment.candidate_profile_id in profiles_by_id
        ]

        return PeerMatchResponse(
            researcher_id=profile_id,
            matches=matches,
            total_candidates_evaluated=len(candidates),
            returned_count=len(matches),
            algorithm_version=config.algorithm_version,
            is_discoverable=is_discoverable,
            data_sufficiency="SUFFICIENT",
            guidance=(
                None
                if matches
                else (
                    "No peers passed the minimum match threshold. Recording more research topics, "
                    "or broadening your collaboration interests, widens the comparison."
                )
            ),
        )

    # ── Loading helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load_interests(
        db: Session,
        profile_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, list[ResearcherInterestModel]]:
        """Loads every relevant researcher's interests in a single query."""
        if not profile_ids:
            return {}
        rows = (
            db.execute(
                select(ResearcherInterestModel).where(
                    ResearcherInterestModel.profile_id.in_(list(profile_ids))
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[uuid.UUID, list[ResearcherInterestModel]] = {}
        for row in rows:
            if row.profile_id is None:
                continue
            grouped.setdefault(row.profile_id, []).append(row)
        return grouped

    @staticmethod
    def _load_topic_ancestors(
        db: Session,
        interest_rows: dict[uuid.UUID, list[ResearcherInterestModel]],
    ) -> dict[str, frozenset[str]]:
        """
        Builds slug -> ancestor slugs for every topic in play, in one query.

        Walks the stored parent chain rather than importing the taxonomy service, so peer matching
        stays a database-only concern and cannot drift from the topics actually recorded.
        """
        slugs = {
            row.topic_slug
            for rows in interest_rows.values()
            for row in rows
            if row.topic_slug
        }
        if not slugs:
            return {}

        all_topics = (
            db.execute(select(TopicModel.id, TopicModel.slug, TopicModel.parent_id)).all()
        )
        by_id = {row[0]: (row[1], row[2]) for row in all_topics}
        slug_to_id = {row[1]: row[0] for row in all_topics}

        ancestors: dict[str, frozenset[str]] = {}
        for slug in slugs:
            topic_id = slug_to_id.get(slug)
            chain: list[str] = []
            seen: set[uuid.UUID] = set()
            while topic_id is not None and topic_id in by_id and topic_id not in seen:
                seen.add(topic_id)
                _, parent_id = by_id[topic_id]
                if parent_id is None or parent_id not in by_id:
                    break
                parent_slug = by_id[parent_id][0]
                if parent_slug:
                    chain.append(parent_slug)
                topic_id = parent_id
            ancestors[slug] = frozenset(chain)
        return ancestors

    @staticmethod
    def _build_topic_profile(
        profile: ResearchProfileModel,
        interests: Sequence[ResearcherInterestModel],
        ancestors: dict[str, frozenset[str]],
        config: PeerMatchingConfig,
    ) -> TopicProfile:
        """
        Converts ORM rows into the engine's plain input.

        Profile keywords are folded in as emerging interests so a researcher who has declared
        their focus but not yet linked publications is still matchable.
        """
        expertise: dict[str, float] = {}
        emerging: dict[str, float] = {}
        relevant_ancestors: dict[str, frozenset[str]] = {}

        for interest in interests:
            slug = interest.topic_slug or (interest.topic_name or "").strip().lower().replace(" ", "-")
            if not slug:
                continue
            strength = float(interest.strength or 0.0)
            classification = interest.classification or ""
            if classification in config.expertise_classifications:
                expertise[slug] = max(expertise.get(slug, 0.0), strength)
            elif classification in config.emerging_classifications:
                emerging[slug] = max(emerging.get(slug, 0.0), strength)
            relevant_ancestors[slug] = ancestors.get(slug, frozenset())

        keywords = {
            kw.strip().lower()
            for kw in (profile.keywords or [])
            if kw and kw.strip()
        }
        # A declared keyword is weaker evidence than an inferred expertise topic, so it enters as
        # an emerging interest and never displaces a real expertise score.
        for keyword in keywords:
            slug = keyword.replace(" ", "-")
            if slug not in expertise:
                emerging.setdefault(slug, config.min_shared_topic_strength)
                relevant_ancestors.setdefault(slug, ancestors.get(slug, frozenset()))

        return TopicProfile(
            profile_id=profile.id,
            expertise=expertise,
            emerging=emerging,
            ancestors=relevant_ancestors,
            keywords=frozenset(keywords),
            institution=profile.institution,
            academic_status=profile.academic_status,
        )

    # ── Serialization ────────────────────────────────────────────────────────

    @staticmethod
    def _build_settings_schema(
        settings: ResearcherDiscoverySettingsModel,
    ) -> DiscoverySettingsSchema:
        interests: list[CollaborationInterest] = []
        for raw in settings.collaboration_interests or []:
            try:
                interests.append(CollaborationInterest(raw))
            except ValueError:
                # A value retired from the enum should not break a researcher's settings page.
                logger.debug("Ignoring unknown collaboration interest %r", raw)
        return DiscoverySettingsSchema(
            profile_id=settings.profile_id,
            is_discoverable=settings.is_discoverable,
            collaboration_status=CollaborationStatus(settings.collaboration_status),
            collaboration_interests=interests,
            show_institution=settings.show_institution,
            show_contact_email=settings.show_contact_email,
            collaboration_note=settings.collaboration_note,
            consent_updated_at=settings.consent_updated_at,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )

    @classmethod
    def _build_match_schema(
        cls,
        assessment: PeerMatchAssessment,
        profile: ResearchProfileModel,
        settings: ResearcherDiscoverySettingsModel,
    ) -> PeerMatchSchema:
        """
        Serializes a match, applying the peer's own field-level disclosure choices.

        This is the single place those choices are enforced, so a field cannot leak by being
        added to a response model elsewhere.
        """
        interests: list[CollaborationInterest] = []
        for raw in settings.collaboration_interests or []:
            try:
                interests.append(CollaborationInterest(raw))
            except ValueError:
                continue

        peer = PeerProfileSchema(
            profile_id=profile.id,
            full_name=getattr(getattr(profile, "user", None), "full_name", None),
            institution=profile.institution if settings.show_institution else None,
            department=profile.department if settings.show_institution else None,
            academic_status=profile.academic_status,
            contact_email=(
                getattr(getattr(profile, "user", None), "email", None)
                if settings.show_contact_email
                else None
            ),
            collaboration_status=CollaborationStatus(settings.collaboration_status),
            collaboration_interests=interests,
            collaboration_note=settings.collaboration_note,
        )

        return PeerMatchSchema(
            peer=peer,
            match_score=assessment.match_score,
            tier=assessment.tier,
            confidence=assessment.confidence,
            shared_topics=list(assessment.shared_topics),
            complementary_topics=list(assessment.complementary_topics),
            signals=[
                PeerMatchSignalSchema(
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
