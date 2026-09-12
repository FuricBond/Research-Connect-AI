"""
Service layer for Phase 3.8 — Personalization Explainability + Researcher UI.

Strict Architectural Boundaries:
  - Read-only explanation generation.
  - Strictly grounded in database records: interests, preferences, feedback, and snapshots.
  - Zero N+1 query patterns: aggregates signals using batched queries.
  - Historical immutability: explains historical snapshots using frozen snapshot items.
"""
from __future__ import annotations

from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.opportunity import OpportunityModel
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.ranking.personalization_ranker import (
    ResearcherPersonalizationContext,
    personalization_ranker,
)
from app.ranking.recommendation_explainer import recommendation_explainer
from app.schemas.recommendation_explanation import (
    LearnedSignalItemSchema,
    PersonalizationSummaryResponse,
    RecommendationExplanationSchema,
)
from app.services.feedback_service import ResearcherFeedbackService
from app.services.personalization_ranking_service import PersonalizationRankingService


class PersonalizationExplanationService:
    """
    Orchestrates personalization summary aggregation and individual recommendation explanations.
    """

    @classmethod
    def get_personalization_summary(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> PersonalizationSummaryResponse:
        """
        Aggregate researcher personalization KPIs, active signals, and learned preferences.
        """
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile '{profile_id}' not found.")

        # ── 1. Active Research Interests & Expertise ──────────────────────────
        interests = (
            db.execute(
                select(ResearcherInterestModel).where(
                    ResearcherInterestModel.profile_id == profile_id,
                )
            )
            .scalars()
            .all()
        )
        active_interests_count = len(interests)
        strong_expertise_count = sum(
            1
            for i in interests
            if getattr(i, "is_primary_expertise", False)
            or "PRIMARY" in str(getattr(i, "classification", "")).upper()
            or "SECONDARY" in str(getattr(i, "classification", "")).upper()
            or str(getattr(i, "expertise_level", "")).upper() in ("PRIMARY", "SECONDARY")
            or float(getattr(i, "strength", 0.0)) >= 0.75
        )

        # ── 2. Explicit Preferences ───────────────────────────────────────────
        preferences = (
            db.execute(
                select(ResearcherPreferenceModel).where(
                    ResearcherPreferenceModel.profile_id == profile_id,
                    ResearcherPreferenceModel.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        explicit_preferences_count = len(preferences)

        # ── 3. Learned Behavioral Signals via Phase 3.6 ───────────────────────
        behavioral_profile = ResearcherFeedbackService.get_behavioral_profile(
            db, profile_id
        )
        behavioral_signals_count = len(behavioral_profile.signals)
        conf_score = float(getattr(behavioral_profile, "overall_confidence", 0.0) or 0.0)

        # ── 4. Total Feedback Interactions Count ──────────────────────────────
        total_feedback_count = (
            db.execute(
                select(func.count(ResearcherRecommendationFeedbackModel.id)).where(
                    ResearcherRecommendationFeedbackModel.researcher_id == profile_id
                )
            ).scalar_one()
            or 0
        )
        has_feedback = total_feedback_count > 0

        # ── 5. Cold Start & Overall Personalization Confidence ─────────────────
        is_cold_start = bool(
            active_interests_count == 0
            and explicit_preferences_count == 0
            and not has_feedback
        )

        if is_cold_start:
            confidence_label = "Cold Start"
            normalized_conf = 0.0
        elif conf_score >= 0.65:
            confidence_label = "High"
            normalized_conf = round(conf_score, 2)
        elif conf_score >= 0.30 or (explicit_preferences_count >= 2 and active_interests_count >= 2):
            confidence_label = "Moderate"
            normalized_conf = max(0.40, round(conf_score, 2))
        else:
            confidence_label = "Low"
            normalized_conf = max(0.20, round(conf_score, 2))

        # ── 6. Format Learned Categorical Signals ─────────────────────────────
        learned_topics: list[LearnedSignalItemSchema] = []
        learned_opp_types: list[LearnedSignalItemSchema] = []
        learned_delivery_modes: list[LearnedSignalItemSchema] = []
        top_positive_signals: list[str] = []
        top_negative_signals: list[str] = []

        # Add explicit preference drivers first
        for p in preferences:
            cat_name = getattr(p, "category", "")
            val_name = getattr(p, "preference_value", "")
            top_positive_signals.append(f"Explicit: {cat_name} -> {val_name}")

        for sig in behavioral_profile.signals:
            cat = getattr(sig, "category", "")
            val = getattr(sig, "preference_value", "")
            direction = getattr(sig, "direction", "POSITIVE")
            norm_score = float(getattr(sig, "normalized_score", 0.0))
            conf = float(getattr(sig, "confidence", 0.0))
            count = int(getattr(sig, "supporting_event_count", 0))

            if direction == "NEGATIVE":
                strength = "Negative"
                top_negative_signals.append(f"Learned Demotion: {cat} -> {val}")
            elif norm_score >= 0.60:
                strength = "Strong"
                top_positive_signals.append(f"Learned Preference: {cat} -> {val} (Strong)")
            elif norm_score >= 0.30:
                strength = "Moderate"
                top_positive_signals.append(f"Learned Preference: {cat} -> {val} (Moderate)")
            else:
                strength = "Weak"

            item = LearnedSignalItemSchema(
                dimension=cat,
                value=val,
                strength=strength,
                confidence=round(conf, 2),
                direction=direction,
                sample_count=count,
            )

            if cat == "TOPIC":
                learned_topics.append(item)
            elif cat == "OPPORTUNITY_TYPE":
                learned_opp_types.append(item)
            elif cat == "DELIVERY_MODE":
                learned_delivery_modes.append(item)

        return PersonalizationSummaryResponse(
            researcher_id=profile_id,
            active_interests_count=active_interests_count,
            strong_expertise_count=strong_expertise_count,
            explicit_preferences_count=explicit_preferences_count,
            behavioral_signals_count=behavioral_signals_count,
            personalization_confidence=confidence_label,
            confidence_score=normalized_conf,
            is_cold_start=is_cold_start,
            has_feedback=has_feedback,
            total_feedback_count=total_feedback_count,
            learned_topics=learned_topics[:8],
            learned_opportunity_types=learned_opp_types[:5],
            learned_delivery_modes=learned_delivery_modes[:3],
            top_positive_signals=top_positive_signals[:8],
            top_negative_signals=top_negative_signals[:5],
        )

    @classmethod
    def explain_opportunity_for_researcher(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        opportunity_id: uuid.UUID,
    ) -> RecommendationExplanationSchema:
        """
        Produce a real-time explanation for a specific opportunity recommendation.
        """
        # Load recommendations batch that includes the target opportunity
        ranking_response = PersonalizationRankingService.get_personalized_recommendations(
            db=db,
            profile_id=profile_id,
            limit=50,
            persist_snapshot=False,
        )

        for rec in ranking_response.recommendations:
            if rec.opportunity_id == opportunity_id:
                if rec.explanation:
                    return rec.explanation

        # Fallback: if not in top 50, fetch opportunity directly and generate explanation
        opp = db.execute(
            select(OpportunityModel).where(OpportunityModel.id == opportunity_id)
        ).scalar_one_or_none()
        if not opp:
            raise ValueError(f"Opportunity '{opportunity_id}' not found.")

        # Build context for target researcher
        profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalar_one_or_none()
        if not profile:
            raise ValueError(f"Researcher profile '{profile_id}' not found.")

        interests = (
            db.execute(
                select(ResearcherInterestModel).where(
                    ResearcherInterestModel.profile_id == profile_id,
                )
            )
            .scalars()
            .all()
        )
        preferences = (
            db.execute(
                select(ResearcherPreferenceModel).where(
                    ResearcherPreferenceModel.profile_id == profile_id,
                    ResearcherPreferenceModel.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        behavioral_profile = ResearcherFeedbackService.get_behavioral_profile(
            db, profile_id
        )

        context = ResearcherPersonalizationContext(
            profile_id=profile_id,
            explicit_preferences=tuple(preferences),
            expertise_items=tuple(interests),
            profile_keywords=tuple(profile.keywords or []),
            behavioral_signals=tuple(behavioral_profile.signals),
            suppressed_opportunity_ids=frozenset(behavioral_profile.suppressed_opportunity_ids),
            is_cold_start=bool(len(interests) == 0 and len(preferences) == 0),
        )

        from app.schemas.personalized_candidate import PersonalizedCandidateOpportunitySchema

        cand_opp = PersonalizedCandidateOpportunitySchema.model_validate(opp)

        # Score candidate using personalization ranker
        raw_p, breakdown, matched_sigs = personalization_ranker.evaluate_personalization_signals(
            opp=cand_opp,
            provenance=None,
            context=context,
        )

        from types import SimpleNamespace
        dummy_cand = SimpleNamespace(
            opportunity_id=opp.id,
            rank=1,
            base_relevance_score=0.50,
            personalization_score=raw_p,
            personalization_adjustment=min(0.15, raw_p * 0.15),
            final_score=min(1.0, 0.50 + min(0.15, raw_p * 0.15)),
            score_breakdown=breakdown,
            matched_signals=matched_sigs,
            opportunity=cand_opp,
        )

        return recommendation_explainer.explain_ranked_candidate(
            candidate=dummy_cand,
            context=context,
            ranking_version="phase3.8-v1",
        )

    @classmethod
    def explain_historical_recommendation(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        opportunity_id: uuid.UUID,
    ) -> RecommendationExplanationSchema:
        """
        Produce a frozen historical explanation for a snapshot recommendation item.

        Strict Architectural Boundary:
          - Uses frozen point-in-time data from ResearcherRecommendationItemModel.
          - Never re-runs active ranking or queries current profile preferences.
        """
        snapshot = db.execute(
            select(ResearcherRecommendationSnapshotModel).where(
                ResearcherRecommendationSnapshotModel.id == snapshot_id,
                ResearcherRecommendationSnapshotModel.researcher_id == profile_id,
            )
        ).scalar_one_or_none()
        if not snapshot:
            raise ValueError(f"Recommendation snapshot '{snapshot_id}' not found for researcher '{profile_id}'.")

        item = db.execute(
            select(ResearcherRecommendationItemModel)
            .options(joinedload(ResearcherRecommendationItemModel.opportunity))
            .where(
                ResearcherRecommendationItemModel.snapshot_id == snapshot_id,
                ResearcherRecommendationItemModel.opportunity_id == opportunity_id,
            )
        ).scalar_one_or_none()
        if not item:
            raise ValueError(
                f"Opportunity '{opportunity_id}' not found in recommendation snapshot '{snapshot_id}'."
            )

        opp_title = item.opportunity.title if item.opportunity else None
        opp_type = item.opportunity.opportunity_type if item.opportunity else None

        return recommendation_explainer.explain_historical_item(
            item=item,
            snapshot=snapshot,
            opportunity_title=opp_title,
            opportunity_type=opp_type,
        )
