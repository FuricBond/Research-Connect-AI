"""
Researcher Interest & Expertise Intelligence Service (Phase 3.2).

Transforms canonical researcher profiles and scholarly knowledge graph relations into a
structured, explainable representation of the researcher's interests and expertise.

Strict Phase Boundary:
  - Descriptive intelligence only.
  - NO personalized recommendations.
  - NO candidate generation.
  - NO personalized ranking.
  - NO preference learning (interest/expertise != user preference).
  - ZERO LLM dependency (deterministic math, rule-based provenance, in-memory scoring).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import math
import os
import sys
from typing import Any, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.research_knowledge import (
    ResearcherModel,
    ResearchWorkAuthorModel,
    ResearchWorkModel,
    ResearchWorkTopicModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.researcher_intelligence import (
    ExpertiseClassification,
    ResearcherIntelligenceResponse,
    ResearcherIntelligenceSummarySchema,
    ResearcherInterestItemSchema,
    SupportingWorkReferenceSchema,
)

# Import deterministic extraction and normalization from ml.topic_analysis
_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)

try:
    from ml.topic_analysis.extraction import KeywordExtractor
    from ml.topic_analysis.normalization import TopicNormalizer, normalize_topic_name
except ImportError:
    KeywordExtractor = None  # type: ignore[assignment,misc]
    TopicNormalizer = None  # type: ignore[assignment,misc]
    normalize_topic_name = lambda name: (name or "").strip().lower()  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Reference year for bounded recency computation
REFERENCE_YEAR: int = 2026


@dataclass
class TopicAccumulator:
    """Internal aggregator for topic evidence across a researcher's scholarly works."""

    topic_id: uuid.UUID | None
    topic_name: str
    topic_slug: str
    topic_category: str | None
    work_ids: set[uuid.UUID] = field(default_factory=set)
    supporting_works: list[SupportingWorkReferenceSchema] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    publication_years: list[int] = field(default_factory=list)
    lead_works_count: int = 0
    primary_works_count: int = 0
    total_citations: int = 0
    has_abstracts_count: int = 0
    has_dois_count: int = 0
    has_years_count: int = 0
    is_profile_keyword: bool = False
    sources: set[str] = field(default_factory=set)


class ResearcherIntelligenceService:
    """
    Canonical Service for Researcher Interest & Expertise Intelligence (Phase 3.2).
    """

    @classmethod
    def get_researcher_intelligence(
        cls,
        db: Session,
        identifier: uuid.UUID,
        refresh: bool = False,
    ) -> ResearcherIntelligenceResponse:
        """
        Compute or retrieve structured research intelligence for a researcher.
        Accepts profile ID, user ID, or canonical researcher ID.
        """
        # 1. Resolve profile and canonical researcher
        profile, canonical_researcher = cls._resolve_identities(db, identifier)
        if not profile and not canonical_researcher:
            raise ValueError(f"Researcher entity with ID '{identifier}' not found.")

        # 2. Check for persisted records if refresh is False and profile exists
        if not refresh and profile:
            persisted = cls._load_persisted_interests(db, profile.id)
            if persisted:
                return cls._build_response_from_persisted(
                    identifier=identifier,
                    profile=profile,
                    canonical_researcher=canonical_researcher,
                    persisted_records=persisted,
                )

        # 3. Compute deterministic intelligence in-memory
        intelligence = cls.compute_intelligence(
            db=db,
            profile=profile,
            canonical_researcher=canonical_researcher,
        )

        # 4. Persist materialized records if profile exists
        if profile:
            cls.persist_intelligence(db, profile.id, intelligence)

        return intelligence

    @classmethod
    def get_researcher_interests(
        cls,
        db: Session,
        identifier: uuid.UUID,
    ) -> list[ResearcherInterestItemSchema]:
        """Convenience method to retrieve structured research interests."""
        intelligence = cls.get_researcher_intelligence(db, identifier, refresh=False)
        return intelligence.interests

    @classmethod
    def get_researcher_expertise(
        cls,
        db: Session,
        identifier: uuid.UUID,
    ) -> list[ResearcherInterestItemSchema]:
        """Convenience method to retrieve structured researcher expertise."""
        intelligence = cls.get_researcher_intelligence(db, identifier, refresh=False)
        return intelligence.expertise

    @classmethod
    def _resolve_identities(
        cls,
        db: Session,
        identifier: uuid.UUID,
    ) -> tuple[ResearchProfileModel | None, ResearcherModel | None]:
        """
        Resolve ResearchProfileModel and ResearcherModel from an identifier.
        Attempts:
          1. Direct Profile ID match
          2. User ID match (linking to profile)
          3. Canonical Researcher ID match
        """
        # Try as profile ID
        stmt = (
            select(ResearchProfileModel)
            .options(
                joinedload(ResearchProfileModel.user),
                joinedload(ResearchProfileModel.canonical_researcher),
            )
            .where(ResearchProfileModel.id == identifier)
        )
        profile = db.execute(stmt).scalars().first()

        if profile:
            return profile, profile.canonical_researcher

        # Try as user ID
        stmt_user = (
            select(ResearchProfileModel)
            .options(
                joinedload(ResearchProfileModel.user),
                joinedload(ResearchProfileModel.canonical_researcher),
            )
            .where(ResearchProfileModel.user_id == identifier)
        )
        profile = db.execute(stmt_user).scalars().first()
        if profile:
            return profile, profile.canonical_researcher

        # Try as canonical researcher ID directly
        canonical = db.get(ResearcherModel, identifier)
        if canonical:
            # Check if linked to any profile
            stmt_link = (
                select(ResearchProfileModel)
                .options(joinedload(ResearchProfileModel.user))
                .where(ResearchProfileModel.canonical_researcher_id == canonical.id)
            )
            linked_profile = db.execute(stmt_link).scalars().first()
            return linked_profile, canonical

        return None, None

    @classmethod
    def compute_intelligence(
        cls,
        db: Session,
        profile: ResearchProfileModel | None,
        canonical_researcher: ResearcherModel | None,
    ) -> ResearcherIntelligenceResponse:
        """
        Execute deterministic topic aggregation and intelligence scoring.
        Zero N+1 queries: all works and topics are loaded in a single eager query.
        """
        researcher_id = (
            profile.id
            if profile
            else (canonical_researcher.id if canonical_researcher else uuid.uuid4())
        )
        display_name = ""
        if profile and profile.user and profile.user.full_name:
            display_name = profile.user.full_name
        elif canonical_researcher and canonical_researcher.display_name:
            display_name = canonical_researcher.display_name
        else:
            display_name = "Researcher"

        # 1. Fetch authored works with eager loaded topics (Zero N+1)
        authored_links: list[ResearchWorkAuthorModel] = []
        if canonical_researcher:
            stmt = (
                select(ResearchWorkAuthorModel)
                .join(
                    ResearchWorkModel,
                    ResearchWorkAuthorModel.work_id == ResearchWorkModel.id,
                )
                .options(
                    joinedload(ResearchWorkAuthorModel.work)
                    .joinedload(ResearchWorkModel.topic_associations)
                    .joinedload(ResearchWorkTopicModel.topic)
                )
                .where(
                    ResearchWorkAuthorModel.researcher_id == canonical_researcher.id
                )
                .order_by(ResearchWorkModel.publication_year.desc().nulls_last())
            )
            authored_links = db.execute(stmt).scalars().unique().all()

        total_works = len(authored_links)


        # 2. Extract and normalize profile keywords
        profile_keywords: list[str] = []
        if profile and profile.keywords:
            profile_keywords = [
                kw.strip() for kw in profile.keywords if kw and kw.strip()
            ]

        # 3. Aggregate evidence by normalized topic
        topic_map: dict[str, TopicAccumulator] = {}

        # Keyword extractor fallback for works without explicit DB topic associations
        extractor = KeywordExtractor() if KeywordExtractor else None

        for link in authored_links:
            work = link.work
            if not work:
                continue

            work_ref = SupportingWorkReferenceSchema(
                id=work.id,
                title=work.title,
                doi=work.doi,
                publication_year=work.publication_year,
                work_type=work.work_type,
                author_position=link.author_position,
                is_corresponding=link.is_corresponding,
                cited_by_count=work.cited_by_count,
            )

            is_lead = bool(
                (link.author_position and link.author_position.lower() in ("first", "1"))
                or link.is_corresponding
            )

            has_explicit_topics = False
            if work.topic_associations:
                for assoc in work.topic_associations:
                    topic = assoc.topic
                    if not topic:
                        continue
                    has_explicit_topics = True
                    norm_key = normalize_topic_name(topic.name)
                    if norm_key not in topic_map:
                        topic_map[norm_key] = TopicAccumulator(
                            topic_id=topic.id,
                            topic_name=topic.name,
                            topic_slug=topic.slug,
                            topic_category=None,
                        )
                    acc = topic_map[norm_key]
                    acc.work_ids.add(work.id)
                    acc.confidences.append(float(assoc.confidence_score))
                    acc.sources.add(assoc.source or "TopicModel")
                    if assoc.is_primary:
                        acc.primary_works_count += 1
                    if is_lead:
                        acc.lead_works_count += 1
                    acc.total_citations += work.cited_by_count
                    if work.abstract:
                        acc.has_abstracts_count += 1
                    if work.doi:
                        acc.has_dois_count += 1
                    if work.publication_year:
                        acc.has_years_count += 1
                        acc.publication_years.append(work.publication_year)
                    if work_ref not in acc.supporting_works:
                        acc.supporting_works.append(work_ref)

            # If no DB topic associations, fallback to metadata concepts or keyword extraction
            if not has_explicit_topics:
                extracted_terms: list[tuple[str, str, float]] = []

                # Check raw_metadata for concepts (OpenAlex format)
                if work.raw_metadata and isinstance(work.raw_metadata, dict):
                    raw_concepts = work.raw_metadata.get("concepts", [])
                    if isinstance(raw_concepts, list):
                        for c in raw_concepts:
                            if isinstance(c, dict) and "display_name" in c:
                                c_name = c["display_name"]
                                c_score = float(c.get("score", 0.70))
                                extracted_terms.append((c_name, c_name.lower().replace(" ", "-"), c_score))

                # Fallback to deterministic KeywordExtractor
                if not extracted_terms and extractor and work.title:
                    kw_list = extractor.extract_keywords(
                        title=work.title,
                        abstract=work.abstract,
                        top_k=5,
                    )
                    for kw in kw_list:
                        extracted_terms.append((kw.keyword.title(), kw.keyword.replace(" ", "-"), kw.weight))

                for term_name, term_slug, term_conf in extracted_terms:
                    norm_key = normalize_topic_name(term_name)
                    if not norm_key:
                        continue
                    if norm_key not in topic_map:
                        topic_map[norm_key] = TopicAccumulator(
                            topic_id=None,
                            topic_name=term_name,
                            topic_slug=term_slug,
                            topic_category=None,
                        )
                    acc = topic_map[norm_key]
                    acc.work_ids.add(work.id)
                    acc.confidences.append(min(1.0, term_conf))
                    acc.sources.add("EXTRACTED")
                    if is_lead:
                        acc.lead_works_count += 1
                    acc.total_citations += work.cited_by_count
                    if work.abstract:
                        acc.has_abstracts_count += 1
                    if work.doi:
                        acc.has_dois_count += 1
                    if work.publication_year:
                        acc.has_years_count += 1
                        acc.publication_years.append(work.publication_year)
                    if work_ref not in acc.supporting_works:
                        acc.supporting_works.append(work_ref)

        # 4. Integrate explicit profile keywords
        for kw in profile_keywords:
            norm_key = normalize_topic_name(kw)
            if not norm_key:
                continue
            if norm_key not in topic_map:
                topic_map[norm_key] = TopicAccumulator(
                    topic_id=None,
                    topic_name=kw.title(),
                    topic_slug=norm_key.replace(" ", "-"),
                    topic_category="DECLARED_PROFILE",
                )
            acc = topic_map[norm_key]
            acc.is_profile_keyword = True
            acc.sources.add("PROFILE_DECLARED")

        # 5. Compute scores, classifications, and provenance for each topic
        all_interests: list[ResearcherInterestItemSchema] = []

        for norm_key, acc in topic_map.items():
            work_count = len(acc.work_ids)
            has_works = work_count > 0

            # Recency Signal [0.15, 1.0]
            recency = cls._compute_recency(acc.publication_years)

            # Strength Score [0.0, 1.0]
            strength = cls._compute_strength(
                work_count=work_count,
                total_works=total_works,
                lead_works_count=acc.lead_works_count,
                primary_works_count=acc.primary_works_count,
                total_citations=acc.total_citations,
                is_profile_keyword=acc.is_profile_keyword,
                recency=recency,
            )

            # Confidence Score [0.0, 1.0]
            confidence = cls._compute_confidence(
                confidences=acc.confidences,
                work_count=work_count,
                has_abstracts_count=acc.has_abstracts_count,
                has_dois_count=acc.has_dois_count,
                has_years_count=acc.has_years_count,
                is_profile_keyword=acc.is_profile_keyword,
                source_count=len(acc.sources),
            )

            # First and last observed years
            first_year = min(acc.publication_years) if acc.publication_years else None
            last_year = max(acc.publication_years) if acc.publication_years else None
            span_years = (last_year - first_year) if (first_year and last_year) else 0

            # Expertise Classification
            classification, is_primary = cls._classify_topic(
                work_count=work_count,
                total_works=total_works,
                strength=strength,
                confidence=confidence,
                recency=recency,
                span_years=span_years,
                is_profile_keyword=acc.is_profile_keyword,
            )

            # Deterministic Provenance Reasons
            provenance = cls._generate_provenance(
                work_count=work_count,
                lead_works_count=acc.lead_works_count,
                primary_works_count=acc.primary_works_count,
                total_citations=acc.total_citations,
                span_years=span_years,
                first_year=first_year,
                last_year=last_year,
                recency=recency,
                is_profile_keyword=acc.is_profile_keyword,
                confidence=confidence,
            )

            # Sort supporting works by publication year desc, then citations desc
            sorted_works = sorted(
                acc.supporting_works,
                key=lambda w: (
                    w.publication_year or 0,
                    w.cited_by_count,
                ),
                reverse=True,
            )

            interest_item = ResearcherInterestItemSchema(
                topic_id=acc.topic_id,
                topic_name=acc.topic_name,
                topic_slug=acc.topic_slug,
                topic_category=acc.topic_category,
                strength=strength,
                confidence=confidence,
                evidence_count=max(1, work_count),
                recency_score=recency,
                classification=classification,
                is_primary_expertise=is_primary,
                first_observed_year=first_year,
                last_observed_year=last_year,
                source=(
                    "HYBRID"
                    if (acc.is_profile_keyword and has_works)
                    else ("PROFILE_DECLARED" if acc.is_profile_keyword else "SCHOLARLY_WORKS")
                ),
                provenance_reasons=provenance,
                supporting_works=sorted_works,
            )
            all_interests.append(interest_item)

        # 6. Deterministic tie-breaking sort:
        # strength DESC, confidence DESC, evidence_count DESC, topic_name ASC
        all_interests.sort(
            key=lambda item: (
                -item.strength,
                -item.confidence,
                -item.evidence_count,
                item.topic_name.lower(),
            )
        )

        # 7. Segment into expertise and emerging lists
        expertise_list = [
            i
            for i in all_interests
            if i.classification
            in (
                ExpertiseClassification.PRIMARY_EXPERTISE,
                ExpertiseClassification.SECONDARY_EXPERTISE,
            )
        ]
        emerging_list = [
            i
            for i in all_interests
            if i.classification == ExpertiseClassification.EMERGING_INTEREST
        ]

        # 8. Compute summary
        all_years = [
            yr
            for i in all_interests
            for yr in (i.first_observed_year, i.last_observed_year)
            if yr is not None
        ]
        active_span = (
            f"{min(all_years)}–{max(all_years)}"
            if all_years and min(all_years) != max(all_years)
            else (str(all_years[0]) if all_years else None)
        )

        summary = ResearcherIntelligenceSummarySchema(
            total_topics_analyzed=len(all_interests),
            primary_expertise_count=sum(
                1
                for i in all_interests
                if i.classification == ExpertiseClassification.PRIMARY_EXPERTISE
            ),
            secondary_expertise_count=sum(
                1
                for i in all_interests
                if i.classification == ExpertiseClassification.SECONDARY_EXPERTISE
            ),
            emerging_interest_count=len(emerging_list),
            total_works_analyzed=total_works,
            active_years_span=active_span,
            has_profile_keywords=bool(len(profile_keywords) > 0),
        )

        return ResearcherIntelligenceResponse(
            researcher_id=researcher_id,
            profile_id=profile.id if profile else None,
            canonical_researcher_id=(
                canonical_researcher.id if canonical_researcher else None
            ),
            display_name=display_name,
            interests=all_interests,
            expertise=expertise_list,
            emerging=emerging_list,
            summary=summary,
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _compute_recency(publication_years: list[int]) -> float:
        """
        Bounded recency signal in [0.15, 1.0].
        Preserves older expertise without zeroing it out.
        """
        if not publication_years:
            return 0.50

        max_year = max(publication_years)
        delta = max(0, REFERENCE_YEAR - max_year)

        if delta <= 1:
            score = 1.00
        elif delta <= 5:
            score = 1.00 - (0.10 * (delta - 1))
        else:
            # Half-life decay with floor at 0.15
            decayed = 0.60 * math.pow(0.92, delta - 5)
            score = max(0.15, decayed)

        return round(min(1.0, max(0.15, score)), 3)

    @staticmethod
    def _compute_strength(
        work_count: int,
        total_works: int,
        lead_works_count: int,
        primary_works_count: int,
        total_citations: int,
        is_profile_keyword: bool,
        recency: float,
    ) -> float:
        """
        Bounded topic strength score in [0.0, 1.0].
        Combines volume, coverage dominance, lead authorship, citations, profile signal, and recency.
        """
        if work_count == 0:
            # Profile declared interest without publications yet
            return 0.50 if is_profile_keyword else 0.0

        # 1. Volume & Depth (diminishing returns, saturated at 15 works)
        s_vol = min(1.0, math.log(1.0 + work_count) / math.log(1.0 + 15.0))

        # 2. Coverage proportion of corpus
        s_cov = work_count / max(1, total_works)

        # 3. Authority: lead authorship & primary topic
        lead_ratio = lead_works_count / work_count
        primary_ratio = primary_works_count / work_count
        s_lead = (0.5 * lead_ratio) + (0.5 * primary_ratio)

        # 4. Citations (diminishing returns, saturated at 100 citations)
        s_cit = min(1.0, math.log(1.0 + max(0, total_citations)) / math.log(1.0 + 100.0))
        s_auth = (0.6 * s_lead) + (0.4 * s_cit)

        # 5. Profile keyword declared bonus
        s_prof = 1.0 if is_profile_keyword else 0.0

        raw_strength = (
            (0.40 * s_vol)
            + (0.25 * s_cov)
            + (0.15 * s_auth)
            + (0.10 * recency)
            + (0.10 * s_prof)
        )
        return round(min(1.0, max(0.0, raw_strength)), 3)

    @staticmethod
    def _compute_confidence(
        confidences: list[float],
        work_count: int,
        has_abstracts_count: int,
        has_dois_count: int,
        has_years_count: int,
        is_profile_keyword: bool,
        source_count: int,
    ) -> float:
        """
        Bounded certainty / confidence score in [0.0, 1.0].
        Reflects extraction confidence, evidence quantity, metadata completeness, and diversity.
        """
        if work_count == 0:
            return 0.45 if is_profile_keyword else 0.10

        # Mean assignment confidence
        c_extract = (
            sum(confidences) / len(confidences) if confidences else 0.75
        )

        # Quantity factor (saturated at 5 works)
        c_qty = min(1.0, work_count / 5.0)

        # Metadata completeness
        meta_items = has_abstracts_count + has_dois_count + has_years_count
        c_meta = meta_items / (3.0 * work_count)

        # Multi-source bonus
        c_div = 0.15 if (is_profile_keyword and work_count > 0) or source_count > 1 else 0.0

        raw_conf = (
            (0.40 * c_extract)
            + (0.30 * c_qty)
            + (0.20 * c_meta)
            + (0.10 * min(1.0, c_div * 6.66))
        )
        return round(min(1.0, max(0.0, raw_conf)), 3)

    @staticmethod
    def _classify_topic(
        work_count: int,
        total_works: int,
        strength: float,
        confidence: float,
        recency: float,
        span_years: int,
        is_profile_keyword: bool,
    ) -> tuple[ExpertiseClassification, bool]:
        """
        Deterministic classification into expertise and interest tiers.
        """
        # Edge case: insufficient evidence
        if (confidence < 0.35 and not is_profile_keyword) or (strength < 0.20 and work_count == 0):
            return ExpertiseClassification.INSUFFICIENT_EVIDENCE, False

        coverage = work_count / max(1, total_works) if total_works > 0 else 0.0

        # Primary Expertise: sustained record, high strength and confidence
        if (
            work_count >= 3
            and strength >= 0.65
            and confidence >= 0.60
            and (span_years >= 2 or work_count >= 5 or coverage >= 0.35)
        ):
            return ExpertiseClassification.PRIMARY_EXPERTISE, True

        # Secondary Expertise: solid scholarly evidence
        if work_count >= 2 and strength >= 0.40 and confidence >= 0.45:
            return ExpertiseClassification.SECONDARY_EXPERTISE, False

        # Emerging Interest: recent activity (within 2-3 years) with active publication
        if recency >= 0.75 and work_count >= 1:
            return ExpertiseClassification.EMERGING_INTEREST, False

        # Weak Interest / Profile declaration
        if strength >= 0.20:
            return ExpertiseClassification.WEAK_INTEREST, False

        return ExpertiseClassification.INSUFFICIENT_EVIDENCE, False

    @staticmethod
    def _generate_provenance(
        work_count: int,
        lead_works_count: int,
        primary_works_count: int,
        total_citations: int,
        span_years: int,
        first_year: int | None,
        last_year: int | None,
        recency: float,
        is_profile_keyword: bool,
        confidence: float,
    ) -> list[str]:
        """Generate deterministic, human-readable explanatory reasons."""
        reasons: list[str] = []

        if work_count > 0:
            reasons.append(
                f"{work_count} authored publication{'s' if work_count > 1 else ''} in this domain"
            )
        if primary_works_count > 0:
            reasons.append(
                f"Primary topic in {primary_works_count} publication{'s' if primary_works_count > 1 else ''}"
            )
        if lead_works_count > 0:
            reasons.append(
                f"First or corresponding author on {lead_works_count} work{'s' if lead_works_count > 1 else ''}"
            )
        if total_citations > 0:
            reasons.append(
                f"{total_citations} scholarly citation{'s' if total_citations > 1 else ''} across supporting works"
            )
        if span_years >= 2 and first_year and last_year:
            reasons.append(
                f"Sustained scholarly activity over {span_years} years ({first_year}–{last_year})"
            )
        elif last_year and recency >= 0.75:
            reasons.append(f"Recent active publication ({last_year})")
        if is_profile_keyword:
            reasons.append("Explicitly declared in researcher profile keywords")
        if confidence >= 0.80:
            reasons.append("High taxonomy assignment confidence")

        if not reasons:
            reasons.append("Inferred from scholarly activity context")

        return reasons

    @classmethod
    def persist_intelligence(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        intelligence: ResearcherIntelligenceResponse,
    ) -> None:
        """
        Materialize computed intelligence into the researcher_interests table.
        Removes previous records for this profile and writes the fresh batch.
        """
        try:
            # Delete old records
            stmt_del = (
                select(ResearcherInterestModel)
                .where(ResearcherInterestModel.profile_id == profile_id)
            )
            old_records = db.execute(stmt_del).scalars().all()
            for r in old_records:
                db.delete(r)

            # Insert fresh records
            for item in intelligence.interests:
                record = ResearcherInterestModel(
                    id=uuid.uuid4(),
                    profile_id=profile_id,
                    canonical_researcher_id=intelligence.canonical_researcher_id,
                    topic_id=item.topic_id,
                    topic_name=item.topic_name,
                    topic_slug=item.topic_slug,
                    topic_category=item.topic_category,
                    strength=item.strength,
                    confidence=item.confidence,
                    evidence_count=item.evidence_count,
                    recency_score=item.recency_score,
                    classification=item.classification.value,
                    is_primary_expertise=item.is_primary_expertise,
                    first_observed_year=item.first_observed_year,
                    last_observed_year=item.last_observed_year,
                    source=item.source,
                    provenance={"reasons": item.provenance_reasons},
                    supporting_work_ids=[str(w.id) for w in item.supporting_works],
                )
                db.add(record)

            db.commit()
        except Exception as e:
            logger.warning(
                "Failed to persist researcher interests for profile %s: %s",
                profile_id,
                e,
            )
            db.rollback()

    @classmethod
    def _load_persisted_interests(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> list[ResearcherInterestModel]:
        """Load materialized interest records from the database."""
        stmt = (
            select(ResearcherInterestModel)
            .where(ResearcherInterestModel.profile_id == profile_id)
            .order_by(
                ResearcherInterestModel.strength.desc(),
                ResearcherInterestModel.confidence.desc(),
                ResearcherInterestModel.evidence_count.desc(),
                ResearcherInterestModel.topic_name.asc(),
            )
        )
        return list(db.execute(stmt).scalars().all())

    @classmethod
    def _build_response_from_persisted(
        cls,
        identifier: uuid.UUID,
        profile: ResearchProfileModel | None,
        canonical_researcher: ResearcherModel | None,
        persisted_records: list[ResearcherInterestModel],
    ) -> ResearcherIntelligenceResponse:
        """Construct response model from persisted database records."""
        display_name = ""
        if profile and profile.user and profile.user.full_name:
            display_name = profile.user.full_name
        elif canonical_researcher and canonical_researcher.display_name:
            display_name = canonical_researcher.display_name
        else:
            display_name = "Researcher"

        interests: list[ResearcherInterestItemSchema] = []
        for r in persisted_records:
            provenance_reasons = []
            if r.provenance and isinstance(r.provenance, dict):
                provenance_reasons = r.provenance.get("reasons", [])

            # Load supporting work summaries if IDs are present
            supporting_refs: list[SupportingWorkReferenceSchema] = []
            if r.supporting_work_ids and isinstance(r.supporting_work_ids, list):
                for wid_str in r.supporting_work_ids:
                    try:
                        wid = uuid.UUID(wid_str)
                        supporting_refs.append(
                            SupportingWorkReferenceSchema(
                                id=wid,
                                title="Referenced Research Work",
                                publication_year=r.last_observed_year,
                            )
                        )
                    except ValueError:
                        continue

            try:
                classification_enum = ExpertiseClassification(r.classification)
            except ValueError:
                classification_enum = ExpertiseClassification.WEAK_INTEREST

            interests.append(
                ResearcherInterestItemSchema(
                    topic_id=r.topic_id,
                    topic_name=r.topic_name,
                    topic_slug=r.topic_slug,
                    topic_category=r.topic_category,
                    strength=r.strength,
                    confidence=r.confidence,
                    evidence_count=r.evidence_count,
                    recency_score=r.recency_score,
                    classification=classification_enum,
                    is_primary_expertise=r.is_primary_expertise,
                    first_observed_year=r.first_observed_year,
                    last_observed_year=r.last_observed_year,
                    source=r.source,
                    provenance_reasons=provenance_reasons,
                    supporting_works=supporting_refs,
                )
            )

        expertise = [
            i
            for i in interests
            if i.classification
            in (
                ExpertiseClassification.PRIMARY_EXPERTISE,
                ExpertiseClassification.SECONDARY_EXPERTISE,
            )
        ]
        emerging = [
            i
            for i in interests
            if i.classification == ExpertiseClassification.EMERGING_INTEREST
        ]

        all_years = [
            yr
            for i in interests
            for yr in (i.first_observed_year, i.last_observed_year)
            if yr is not None
        ]
        active_span = (
            f"{min(all_years)}–{max(all_years)}"
            if all_years and min(all_years) != max(all_years)
            else (str(all_years[0]) if all_years else None)
        )

        summary = ResearcherIntelligenceSummarySchema(
            total_topics_analyzed=len(interests),
            primary_expertise_count=sum(
                1
                for i in interests
                if i.classification == ExpertiseClassification.PRIMARY_EXPERTISE
            ),
            secondary_expertise_count=sum(
                1
                for i in interests
                if i.classification == ExpertiseClassification.SECONDARY_EXPERTISE
            ),
            emerging_interest_count=len(emerging),
            total_works_analyzed=len(
                set(
                    wid
                    for r in persisted_records
                    if r.supporting_work_ids
                    for wid in r.supporting_work_ids
                )
            ),
            active_years_span=active_span,
            has_profile_keywords=bool(profile and profile.keywords),
        )

        return ResearcherIntelligenceResponse(
            researcher_id=identifier,
            profile_id=profile.id if profile else None,
            canonical_researcher_id=(
                canonical_researcher.id if canonical_researcher else None
            ),
            display_name=display_name,
            interests=interests,
            expertise=expertise,
            emerging=emerging,
            summary=summary,
            generated_at=datetime.now(timezone.utc),
        )
