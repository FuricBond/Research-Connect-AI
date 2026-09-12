"""
Personalized Candidate Generation Service for Phase 3.4.

Orchestrates multi-source personalized candidate generation:
  1. Explicit preference candidates (Phase 3.3)
  2. Inferred preference candidates (Phase 3.3 with confidence >= 0.40)
  3. Scholarly expertise & interest candidates (Phase 3.2)
  4. Profile keyword & target type candidates (Phase 3.1)
  5. Cold-start & general high-quality discovery fallback (Phase 2.2 / Phase 2)

Architectural Invariants:
  - Phase 3.4 determines which opportunities enter the candidate pool.
  - Phase 3.4 stops at the candidate set and does NOT implement personalized ranking (reserved for Phase 3.5).
  - Phase 2 matching, ranking, trust/risk, and deadline intelligence remain authoritative.
  - Personalization never bypasses or lowers Phase 2.6 risk intelligence.
  - Expired opportunities are strictly ineligible per Phase 2.7 deadline intelligence.
  - Candidate deduplication merges provenance (sources, matched preferences, matched topics, reasons).
  - Bounded database queries: O(1) query count, zero N+1.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.topic import TopicModel
from app.ranking.deadline.intelligence import DeadlineIntelligence
from app.ranking.deadline.models import DeadlineTemporalStatus
from app.ranking.risk.models import RiskLevel
from app.ranking.risk.scoring import assess_opportunity_risk
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceCoverageSchema,
    CandidateSourceType,
    PersonalizedCandidateItemSchema,
    PersonalizedCandidateOpportunitySchema,
    PersonalizedCandidateSetResponse,
)

logger = logging.getLogger(__name__)


class PersonalizedCandidateGenerationService:
    """
    Deterministic candidate generation service orchestrating multi-source retrieval,
    source balancing quotas, eligibility filtering, and provenance tracking.
    """

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    # Minimum confidence threshold for inferred preferences to generate candidates
    INFERRED_CONFIDENCE_THRESHOLD = 0.40

    @classmethod
    def generate_personalized_candidates(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        *,
        limit: int = DEFAULT_LIMIT,
        include_inferred: bool = True,
        include_expertise: bool = True,
        include_fallback: bool = True,
        suppressed_opportunity_ids: set[uuid.UUID] | None = None,
        include_suppression: bool = True,
        reference_time: datetime | None = None,
    ) -> PersonalizedCandidateSetResponse:
        """
        Generate a deduplicated, eligibility-verified personalized candidate set
        with complete provenance for the specified researcher.

        Parameters
        ----------
        db : Session
            Active SQLAlchemy database session.
        profile_id : uuid.UUID
            Canonical ResearchProfileModel ID.
        limit : int
            Target candidate set size (default: 50, max: 200).
        include_inferred : bool
            Whether to include candidates from inferred preferences.
        include_expertise : bool
            Whether to include candidates from Phase 3.2 scholarly expertise.
        include_fallback : bool
            Whether to include cold-start/general fallback candidates to reach target limit.
        reference_time : datetime | None
            Reference evaluation timestamp (defaults to current UTC time).
        """
        # ── 1. Reference Timestamp Normalization ──────────────────────────────
        if reference_time is None:
            ref_time = datetime.now(timezone.utc)
        elif reference_time.tzinfo is None:
            ref_time = reference_time.replace(tzinfo=timezone.utc)
        else:
            ref_time = reference_time.astimezone(timezone.utc)

        safe_limit = max(1, min(limit, cls.MAX_LIMIT))

        # ── 2. Batch Load Profile and Personalization Context ─────────────────
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile '{profile_id}' not found.")

        # Batch load active preferences
        preferences = (
            db.execute(
                select(ResearcherPreferenceModel).where(
                    ResearcherPreferenceModel.profile_id == profile.id,
                    ResearcherPreferenceModel.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )

        explicit_prefs = [p for p in preferences if p.source == "EXPLICIT"]
        inferred_prefs = (
            [
                p
                for p in preferences
                if p.source == "INFERRED"
                and p.confidence >= cls.INFERRED_CONFIDENCE_THRESHOLD
            ]
            if include_inferred
            else []
        )

        # Batch load scholarly interests/expertise
        interests: list[ResearcherInterestModel] = []
        if include_expertise:
            interest_stmt = select(ResearcherInterestModel).where(
                ResearcherInterestModel.profile_id == profile.id
            )
            interests = list(db.execute(interest_stmt).scalars().all())

        expertise_items = [
            i
            for i in interests
            if i.classification
            in ("PRIMARY_EXPERTISE", "SECONDARY_EXPERTISE", "EMERGING_INTEREST")
        ]

        profile_keywords = [
            kw.strip() for kw in (profile.keywords or []) if kw and kw.strip()
        ]
        profile_target_types = [
            tt.strip().upper()
            for tt in (profile.target_opportunity_types or [])
            if tt and tt.strip()
        ]

        # Determine cold-start status
        is_cold_start = (
            len(explicit_prefs) == 0
            and len(inferred_prefs) == 0
            and len(expertise_items) == 0
            and len(profile_keywords) == 0
            and len(profile_target_types) == 0
        )

        # ── 3. Source Allocation Quotas (Source Balancing) ────────────────────
        explicit_quota = max(1, int(safe_limit * 0.40)) if explicit_prefs else 0
        inferred_quota = max(1, int(safe_limit * 0.15)) if inferred_prefs else 0
        expertise_quota = max(1, int(safe_limit * 0.35)) if expertise_items else 0
        profile_quota = (
            max(1, int(safe_limit * 0.15))
            if (profile_keywords or profile_target_types)
            else 0
        )

        # Resolve negative feedback suppression set (Phase 3.6)
        active_suppressed: set[uuid.UUID] = set()
        if suppressed_opportunity_ids is not None:
            active_suppressed = set(suppressed_opportunity_ids)
        elif include_suppression:
            try:
                from app.services.feedback_service import ResearcherFeedbackService
                active_suppressed = ResearcherFeedbackService.get_suppressed_opportunity_ids(
                    db=db, researcher_id=profile.id, reference_time=ref_time
                )
            except Exception as e:
                logger.warning("Could not resolve suppressed opportunities for profile %s: %s", profile.id, e)
                active_suppressed = set()

        # ── 4. Candidate Retrieval Pipeline ───────────────────────────────────
        # In-memory candidate registry: opportunity_id -> raw candidate dict
        raw_candidates: dict[uuid.UUID, dict[str, Any]] = {}
        source_instance_counts = {
            CandidateSourceType.EXPLICIT_PREFERENCE: 0,
            CandidateSourceType.INFERRED_PREFERENCE: 0,
            CandidateSourceType.RESEARCH_EXPERTISE: 0,
            CandidateSourceType.RESEARCH_INTEREST: 0,
            CandidateSourceType.PROFILE_KEYWORD: 0,
            CandidateSourceType.COLD_START_FALLBACK: 0,
        }

        # Collect researcher topic scope for relevance floor enforcement
        researcher_topics: set[str] = set()
        for p in explicit_prefs:
            if p.category == "TOPIC":
                researcher_topics.add(p.preference_value.lower())
        for p in inferred_prefs:
            if p.category == "TOPIC":
                researcher_topics.add(p.preference_value.lower())
        for exp in expertise_items:
            researcher_topics.add(exp.topic_name.lower())
            researcher_topics.add(exp.topic_slug.lower())
        for kw in profile_keywords:
            researcher_topics.add(kw.lower())

        def _record_candidate(
            opp: OpportunityModel,
            source: CandidateSourceType,
            matched_topics: list[str] | None = None,
            matched_prefs: list[str] | None = None,
            matched_exp: list[str] | None = None,
            reason: str = "",
            retrieval_channel: str = "metadata_query",
        ) -> None:
            if active_suppressed and opp.id in active_suppressed:
                # Omit dismissed/not_interested candidates from candidate pool
                return
            source_instance_counts[source] = source_instance_counts.get(source, 0) + 1
            opp_id = opp.id
            if opp_id not in raw_candidates:
                raw_candidates[opp_id] = {
                    "opportunity": opp,
                    "sources": {source},
                    "matched_topics": set(matched_topics or []),
                    "matched_preferences": set(matched_prefs or []),
                    "matched_expertise": set(matched_exp or []),
                    "reasons": [reason] if reason else [],
                    "retrieval_channels": {retrieval_channel},
                }
            else:
                entry = raw_candidates[opp_id]
                entry["sources"].add(source)
                if matched_topics:
                    entry["matched_topics"].update(matched_topics)
                if matched_prefs:
                    entry["matched_preferences"].update(matched_prefs)
                if matched_exp:
                    entry["matched_expertise"].update(matched_exp)
                if reason and reason not in entry["reasons"]:
                    entry["reasons"].append(reason)
                entry["retrieval_channels"].add(retrieval_channel)

        # Helper to query opportunities with eager topic loading
        def _fetch_active_opportunities(
            base_query,
            query_limit: int,
        ) -> list[OpportunityModel]:
            stmt = (
                base_query.where(
                    OpportunityModel.status.in_(["ACTIVE", "UNVERIFIED"])
                )
                .options(
                    selectinload(OpportunityModel.topic_associations).joinedload(
                        OpportunityTopicModel.topic
                    )
                )
                .limit(query_limit)
            )
            return list(db.execute(stmt).scalars().unique().all())

        # ── 4A. Explicit Preference Candidates ────────────────────────────────
        if explicit_prefs:
            # 1. Topic preferences
            explicit_topic_prefs = [
                p for p in explicit_prefs if p.category == "TOPIC"
            ]
            if explicit_topic_prefs:
                topic_queries = [p.preference_value.lower() for p in explicit_topic_prefs]
                canonical_ids = [
                    p.canonical_id for p in explicit_topic_prefs if p.canonical_id
                ]

                topic_stmt = (
                    select(OpportunityModel)
                    .join(OpportunityTopicModel)
                    .join(TopicModel)
                    .where(
                        or_(
                            TopicModel.id.in_(canonical_ids) if canonical_ids else False,
                            func.lower(TopicModel.name).in_(topic_queries),
                            func.lower(TopicModel.slug).in_(topic_queries),
                        )
                    )
                )
                topic_opps = _fetch_active_opportunities(topic_stmt, explicit_quota * 2)
                for opp in topic_opps:
                    matched_t = [
                        ta.topic.name
                        for ta in opp.topic_associations
                        if ta.topic
                        and (
                            ta.topic.name.lower() in topic_queries
                            or ta.topic.slug.lower() in topic_queries
                            or ta.topic.id in canonical_ids
                        )
                    ]
                    for t_name in matched_t:
                        _record_candidate(
                            opp=opp,
                            source=CandidateSourceType.EXPLICIT_PREFERENCE,
                            matched_topics=[t_name],
                            matched_prefs=[f"Topic: {t_name}"],
                            reason=f"Matches explicit topic preference '{t_name}'",
                            retrieval_channel="explicit_topic_association",
                        )

            # 2. Opportunity type & delivery mode preferences (with relevance floor)
            type_prefs = [
                p.preference_value.upper()
                for p in explicit_prefs
                if p.category == "OPPORTUNITY_TYPE"
            ]
            mode_prefs = [
                p.preference_value.upper()
                for p in explicit_prefs
                if p.category == "DELIVERY_MODE"
            ]
            loc_prefs = [
                p.preference_value.lower()
                for p in explicit_prefs
                if p.category == "LOCATION"
            ]

            if type_prefs or mode_prefs or loc_prefs:
                filter_conds = []
                if type_prefs:
                    filter_conds.append(OpportunityModel.opportunity_type.in_(type_prefs))
                if mode_prefs:
                    filter_conds.append(OpportunityModel.delivery_mode.in_(mode_prefs))
                if loc_prefs:
                    loc_match = or_(
                        *[
                            func.lower(OpportunityModel.location).like(f"%{lp}%")
                            for lp in loc_prefs
                        ]
                    )
                    filter_conds.append(loc_match)

                attr_stmt = select(OpportunityModel).where(or_(*filter_conds))
                attr_opps = _fetch_active_opportunities(attr_stmt, explicit_quota * 2)

                for opp in attr_opps:
                    opp_topics = [
                        ta.topic.name.lower()
                        for ta in opp.topic_associations
                        if ta.topic
                    ]
                    # RELEVANCE FLOOR CHECK:
                    # If researcher has topic scope, opportunity must match at least one topic
                    # or keyword to avoid generating unrelated opportunities.
                    if researcher_topics:
                        has_topic_match = any(t in researcher_topics for t in opp_topics)
                        title_match = any(
                            t in opp.title.lower() for t in researcher_topics
                        )
                        if not (has_topic_match or title_match):
                            continue  # Relevance floor failed: skip generic preference match

                    matched_p: list[str] = []
                    reasons: list[str] = []
                    if opp.opportunity_type in type_prefs:
                        matched_p.append(f"Type: {opp.opportunity_type}")
                        reasons.append(
                            f"Matches preferred opportunity type '{opp.opportunity_type}'"
                        )
                    if opp.delivery_mode in mode_prefs:
                        matched_p.append(f"Mode: {opp.delivery_mode}")
                        reasons.append(
                            f"Matches preferred delivery mode '{opp.delivery_mode}'"
                        )
                    if opp.location and any(lp in opp.location.lower() for lp in loc_prefs):
                        matched_p.append(f"Location: {opp.location}")
                        reasons.append(f"Matches preferred location '{opp.location}'")

                    if matched_p:
                        _record_candidate(
                            opp=opp,
                            source=CandidateSourceType.EXPLICIT_PREFERENCE,
                            matched_prefs=matched_p,
                            reason="; ".join(reasons),
                            retrieval_channel="explicit_attribute_filter",
                        )

        # ── 4B. Inferred Preference Candidates ────────────────────────────────
        if inferred_prefs and include_inferred:
            inferred_topic_prefs = [
                p for p in inferred_prefs if p.category == "TOPIC"
            ]
            if inferred_topic_prefs:
                inf_topics = [p.preference_value.lower() for p in inferred_topic_prefs]
                inf_canonical = [
                    p.canonical_id for p in inferred_topic_prefs if p.canonical_id
                ]

                inf_stmt = (
                    select(OpportunityModel)
                    .join(OpportunityTopicModel)
                    .join(TopicModel)
                    .where(
                        or_(
                            TopicModel.id.in_(inf_canonical) if inf_canonical else False,
                            func.lower(TopicModel.name).in_(inf_topics),
                            func.lower(TopicModel.slug).in_(inf_topics),
                        )
                    )
                )
                inf_opps = _fetch_active_opportunities(inf_stmt, inferred_quota * 2)
                for opp in inf_opps:
                    matched_inf = [
                        ta.topic.name
                        for ta in opp.topic_associations
                        if ta.topic
                        and (
                            ta.topic.name.lower() in inf_topics
                            or ta.topic.slug.lower() in inf_topics
                            or ta.topic.id in inf_canonical
                        )
                    ]
                    for t_name in matched_inf:
                        # Find corresponding confidence
                        conf_val = next(
                            (
                                p.confidence
                                for p in inferred_topic_prefs
                                if p.preference_value.lower() == t_name.lower()
                            ),
                            0.50,
                        )
                        _record_candidate(
                            opp=opp,
                            source=CandidateSourceType.INFERRED_PREFERENCE,
                            matched_topics=[t_name],
                            matched_prefs=[f"Inferred Topic: {t_name}"],
                            reason=f"Matches inferred topic interest '{t_name}' (confidence: {conf_val:.2f})",
                            retrieval_channel="inferred_topic_association",
                        )

        # ── 4C. Scholarly Expertise & Interest Candidates ─────────────────────
        if expertise_items and include_expertise:
            exp_names = [e.topic_name.lower() for e in expertise_items]
            exp_slugs = [e.topic_slug.lower() for e in expertise_items]
            exp_ids = [e.topic_id for e in expertise_items if e.topic_id]

            exp_stmt = (
                select(OpportunityModel)
                .join(OpportunityTopicModel)
                .join(TopicModel)
                .where(
                    or_(
                        TopicModel.id.in_(exp_ids) if exp_ids else False,
                        func.lower(TopicModel.name).in_(exp_names),
                        func.lower(TopicModel.slug).in_(exp_slugs),
                    )
                )
            )
            exp_opps = _fetch_active_opportunities(exp_stmt, expertise_quota * 2)
            for opp in exp_opps:
                matched_exp_items = [
                    e
                    for e in expertise_items
                    if any(
                        ta.topic
                        and (
                            ta.topic.name.lower() == e.topic_name.lower()
                            or ta.topic.slug.lower() == e.topic_slug.lower()
                            or (e.topic_id and ta.topic.id == e.topic_id)
                        )
                        for ta in opp.topic_associations
                    )
                ]
                for exp_item in matched_exp_items:
                    source_type = (
                        CandidateSourceType.RESEARCH_EXPERTISE
                        if exp_item.classification
                        in ("PRIMARY_EXPERTISE", "SECONDARY_EXPERTISE")
                        else CandidateSourceType.RESEARCH_INTEREST
                    )
                    _record_candidate(
                        opp=opp,
                        source=source_type,
                        matched_topics=[exp_item.topic_name],
                        matched_exp=[f"{exp_item.topic_name} ({exp_item.classification})"],
                        reason=f"Aligns with scholarly expertise in '{exp_item.topic_name}' ({exp_item.classification})",
                        retrieval_channel="expertise_topic_association",
                    )

        # ── 4D. Profile Keyword & Target Type Candidates ──────────────────────
        if (profile_keywords or profile_target_types) and profile_quota > 0:
            kw_filters = []
            for kw in profile_keywords:
                term = f"%{kw.lower()}%"
                kw_filters.append(func.lower(OpportunityModel.title).like(term))
                kw_filters.append(func.lower(OpportunityModel.summary).like(term))

            if profile_target_types:
                kw_filters.append(
                    OpportunityModel.opportunity_type.in_(profile_target_types)
                )

            if kw_filters:
                prof_stmt = select(OpportunityModel).where(or_(*kw_filters))
                prof_opps = _fetch_active_opportunities(prof_stmt, profile_quota * 2)
                for opp in prof_opps:
                    matched_kws = [
                        kw
                        for kw in profile_keywords
                        if kw.lower() in opp.title.lower()
                        or (opp.summary and kw.lower() in opp.summary.lower())
                    ]
                    matched_tt = (
                        [opp.opportunity_type]
                        if opp.opportunity_type in profile_target_types
                        else []
                    )
                    if matched_kws or matched_tt:
                        reason_parts = []
                        if matched_kws:
                            reason_parts.append(
                                f"Matches profile keyword(s): {', '.join(matched_kws)}"
                            )
                        if matched_tt:
                            reason_parts.append(
                                f"Matches profile target type '{opp.opportunity_type}'"
                            )
                        _record_candidate(
                            opp=opp,
                            source=CandidateSourceType.PROFILE_KEYWORD,
                            matched_topics=matched_kws,
                            matched_prefs=[f"Target Type: {t}" for t in matched_tt],
                            reason="; ".join(reason_parts),
                            retrieval_channel="profile_keyword_match",
                        )

        # ── 4E. Cold-Start & General Fallback Candidates ──────────────────────
        # Trigger fallback if total candidates < safe_limit and include_fallback is True
        current_candidate_count = len(raw_candidates)
        if include_fallback and current_candidate_count < safe_limit:
            needed = safe_limit - current_candidate_count
            existing_ids = list(raw_candidates.keys())

            fallback_stmt = select(OpportunityModel).where(
                OpportunityModel.status.in_(["ACTIVE", "UNVERIFIED"]),
            )
            if existing_ids:
                fallback_stmt = fallback_stmt.where(
                    OpportunityModel.id.not_in(existing_ids)
                )
            # Prioritize upcoming deadlines
            fallback_stmt = fallback_stmt.order_by(
                OpportunityModel.submission_deadline.asc().nulls_last(),
                OpportunityModel.title.asc(),
            )
            fallback_opps = _fetch_active_opportunities(fallback_stmt, needed * 2)

            for opp in fallback_opps:
                if len(raw_candidates) >= safe_limit * 2:
                    break
                _record_candidate(
                    opp=opp,
                    source=CandidateSourceType.COLD_START_FALLBACK,
                    reason="Surfaced via active discovery candidate pool (cold start / general fallback)",
                    retrieval_channel="general_active_discovery",
                )

        # ── 5. Eligibility, Risk & Deadline Verification ──────────────────────
        verified_candidates: list[PersonalizedCandidateItemSchema] = []

        for opp_id, entry in raw_candidates.items():
            opp: OpportunityModel = entry["opportunity"]

            # Eligibility Check 1: Status must be active/unverified
            if opp.status not in ("ACTIVE", "UNVERIFIED"):
                continue

            # Eligibility Check 2: Phase 2.7 Deadline Intelligence (exclude expired)
            deadline_assessment = DeadlineIntelligence.assess_opportunity_model(
                opp, reference_time=ref_time
            )
            primary_dl = deadline_assessment.primary_assessment

            # Exclude expired opportunities per Phase 2.7 deadline lifecycle
            if primary_dl is not None and primary_dl.status == DeadlineTemporalStatus.EXPIRED:
                continue

            # Safety Assessment: Phase 2.6 Trust & Risk Intelligence
            risk_assessment = assess_opportunity_risk(opp)

            effective_predatory = bool(opp.is_predatory_flag or risk_assessment.is_predatory_flag)
            effective_risk_score = (
                float(opp.risk_score)
                if (opp.risk_score is not None and float(opp.risk_score) > 0.0)
                else float(risk_assessment.risk_score)
            )
            if effective_predatory or effective_risk_score >= 0.70:
                effective_risk_level = RiskLevel.HIGH_RISK.value
            elif effective_risk_score >= 0.35:
                effective_risk_level = RiskLevel.MODERATE_RISK.value
            else:
                effective_risk_level = risk_assessment.risk_level.value

            effective_reasons = list(risk_assessment.risk_reasons)
            if opp.risk_reasons:
                for r in opp.risk_reasons:
                    if r not in effective_reasons:
                        effective_reasons.append(r)
            if effective_predatory and not any("predatory" in r.lower() for r in effective_reasons):
                effective_reasons.append("Flagged as suspected predatory opportunity.")

            # Build canonical opportunity schema
            topic_names = [
                ta.topic.name for ta in opp.topic_associations if ta.topic
            ]

            opp_schema = PersonalizedCandidateOpportunitySchema(
                id=opp.id,
                title=opp.title,
                opportunity_type=opp.opportunity_type,
                delivery_mode=opp.delivery_mode,
                location=opp.location,
                organizer=opp.organizer,
                submission_deadline=opp.submission_deadline,
                website_url=opp.website_url,
                topics=topic_names,
                status=opp.status,
                # Phase 2.6 risk intelligence preserved
                is_predatory_flag=effective_predatory,
                risk_level=effective_risk_level,
                risk_score=effective_risk_score,
                risk_reasons=effective_reasons,
                # Phase 2.7 deadline intelligence preserved
                deadline_status=primary_dl.status.value if primary_dl is not None else None,
                days_remaining=primary_dl.days_remaining if primary_dl is not None else None,
                urgency_tier=primary_dl.urgency_tier.value if primary_dl is not None else None,
                deadline_explanation=primary_dl.explanation if primary_dl is not None else None,
            )


            # Build merged provenance schema
            provenance = CandidateProvenanceSchema(
                candidate_id=uuid.uuid4(),
                opportunity_id=opp.id,
                sources=sorted(list(entry["sources"]), key=lambda s: s.value),
                matched_topics=sorted(list(entry["matched_topics"])),
                matched_preferences=sorted(list(entry["matched_preferences"])),
                matched_expertise=sorted(list(entry["matched_expertise"])),
                reasons=entry["reasons"],
                retrieval_channels=sorted(list(entry["retrieval_channels"])),
            )

            verified_candidates.append(
                PersonalizedCandidateItemSchema(
                    candidate_id=provenance.candidate_id,
                    opportunity=opp_schema,
                    provenance=provenance,
                    eligibility_passed=True,
                    eligibility_reasons=[
                        f"Status '{opp.status}' valid",
                        f"Deadline temporal status: '{primary_dl.status.value if primary_dl is not None else 'UNKNOWN'}'",
                        f"Risk assessed: {risk_assessment.risk_level.value}",
                    ],
                )
            )

        # ── 6. Deterministic Exploratory Ordering ─────────────────────────────
        # Note: This is exploratory candidate presentation order, NOT recommendation ranking.
        # Phase 2 ranker is untouched. Phase 3.5 will introduce personalized ranking.
        def _sort_key(c: PersonalizedCandidateItemSchema) -> tuple[int, int, float, str, str]:
            # 1. More sources first (e.g. matched both preference and expertise)
            source_count_neg = -len(c.provenance.sources)
            # 2. Upcoming deadlines prioritized; null deadlines last
            has_deadline = 0 if c.opportunity.days_remaining is not None else 1
            days_rem = (
                c.opportunity.days_remaining
                if c.opportunity.days_remaining is not None
                else 999999.0
            )
            # 3. Deterministic alphabetical title
            title_clean = c.opportunity.title.lower()
            # 4. Canonical UUID tie-breaker
            opp_id_str = str(c.opportunity.id)
            return (source_count_neg, has_deadline, days_rem, title_clean, opp_id_str)

        verified_candidates.sort(key=_sort_key)

        # Slice to final requested limit
        final_candidates = verified_candidates[:safe_limit]

        # ── 7. Coverage Diagnostics ───────────────────────────────────────────
        total_unique = len(final_candidates)
        total_raw_instances = sum(
            len(c.provenance.sources) for c in final_candidates
        )
        dedup_ratio = (
            round(1.0 - (total_unique / max(1, total_raw_instances)), 4)
            if total_raw_instances > 0
            else 0.0
        )

        coverage = CandidateSourceCoverageSchema(
            explicit_preference_count=sum(
                1
                for c in final_candidates
                if CandidateSourceType.EXPLICIT_PREFERENCE in c.provenance.sources
            ),
            inferred_preference_count=sum(
                1
                for c in final_candidates
                if CandidateSourceType.INFERRED_PREFERENCE in c.provenance.sources
            ),
            expertise_count=sum(
                1
                for c in final_candidates
                if CandidateSourceType.RESEARCH_EXPERTISE in c.provenance.sources
                or CandidateSourceType.RESEARCH_INTEREST in c.provenance.sources
            ),
            profile_count=sum(
                1
                for c in final_candidates
                if CandidateSourceType.PROFILE_KEYWORD in c.provenance.sources
            ),
            fallback_count=sum(
                1
                for c in final_candidates
                if CandidateSourceType.COLD_START_FALLBACK in c.provenance.sources
            ),
            unique_candidate_count=total_unique,
            deduplication_ratio=dedup_ratio,
        )

        return PersonalizedCandidateSetResponse(
            researcher_id=profile.id,
            candidate_count=total_unique,
            is_cold_start=is_cold_start,
            coverage=coverage,
            candidates=final_candidates,
            metadata={
                "requested_limit": limit,
                "safe_limit": safe_limit,
                "include_inferred": include_inferred,
                "include_expertise": include_expertise,
                "include_fallback": include_fallback,
                "reference_time": ref_time.isoformat(),
                "phase_boundary": "Phase 3.4 Candidate Generation (Unranked Candidate Pool)",
            },
        )
