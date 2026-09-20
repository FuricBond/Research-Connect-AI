"""
Personalization Quality Service for Phase 5.7 — Personalization Evaluation, Contextual Adaptation & Recommendation Quality Loop.

Guarantees:
  - Zero N+1 queries: eager/batch loading across recommendation items, interactions, opportunities, and calibrations.
  - Multi-tenant isolation: all operations strictly scoped by profile_id.
  - Dialect-neutral persistence: update-or-insert pattern compatible with SQLite and PostgreSQL.
  - Clean error recovery: handles unmigrated environments gracefully.
  - Subordinate bounded adaptation: contextual modifiers clamped strictly to [-0.03, +0.03].
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Sequence
import uuid

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from app.models.adaptive_signal import AdaptivePreferenceSignalModel
from app.models.opportunity import OpportunityModel
from app.models.personalization_calibration import (
    PersonalizationCalibrationModel,
    RecommendationFeedbackAttributionModel,
)
from app.models.personalization_quality import (
    ContextualFallbackLevel,
    PersonalizationContextualAdaptationModel,
    PersonalizationQualityEvaluationModel,
    QualityEvaluationState,
)
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import ResearcherInteractionModel
from app.personalization.quality_config import (
    DEFAULT_QUALITY_CONFIG,
    PersonalizationQualityConfig,
)
from app.personalization.quality_engine import PersonalizationQualityEngine
from app.schemas.personalization_quality import (
    ContextualAdaptationsResponse,
    ContextualSummaryItem,
    PersonalizationContextualAdaptationSchema,
    PersonalizationQualityEvaluationSchema,
    PersonalizationQualityResponse,
    SignalQualityResponse,
    SignalQualitySummaryItem,
)
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService
from app.services.personalization_calibration_service import PersonalizationCalibrationService

logger = logging.getLogger(__name__)


class PersonalizationQualityService:
    """Service managing personalization quality evaluation and contextual adaptation."""

    @classmethod
    def _to_evaluation_schema(
        cls,
        record: PersonalizationQualityEvaluationModel | PersonalizationQualityEvaluationSchema,
    ) -> PersonalizationQualityEvaluationSchema:
        """Converts database model to domain schema (or returns schema if already converted)."""
        if isinstance(record, PersonalizationQualityEvaluationSchema):
            return record
        return PersonalizationQualityEvaluationSchema(
            id=record.id,
            profile_id=record.profile_id,
            evaluation_period_days=record.evaluation_window_days,
            recommendations_evaluated_count=record.total_recommendations_evaluated,
            attributed_interactions_count=record.total_attributed_interactions,
            positive_outcomes_count=record.positive_outcome_count,
            negative_outcomes_count=record.negative_outcome_count,
            neutral_outcomes_count=record.neutral_outcome_count,
            observed_engagement_rate=record.engagement_rate or 0.0,
            observed_positive_rate=record.positive_feedback_rate or 0.0,
            observed_negative_rate=record.negative_feedback_rate or 0.0,
            baseline_engagement_rate=0.20,
            baseline_positive_rate=0.15,
            observed_personalization_lift=record.observed_personalization_lift or 0.0,
            confidence=record.confidence,
            evaluation_state=QualityEvaluationState(record.evaluation_state),
            diversity_score=record.recommendation_diversity_score or 0.0,
            novelty_rate=record.novelty_rate or 0.0,
            contextual_breakdown=record.quality_metrics_breakdown or {},
            deterministic_explanation=record.deterministic_explanation,
            algorithm_version=record.algorithm_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @classmethod
    def get_latest_quality_evaluation(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> PersonalizationQualityEvaluationSchema | None:
        """
        Query the latest materialized personalization quality evaluation for a researcher.
        """
        try:
            stmt = (
                select(PersonalizationQualityEvaluationModel)
                .where(PersonalizationQualityEvaluationModel.profile_id == profile_id)
                .order_by(PersonalizationQualityEvaluationModel.created_at.desc())
                .limit(1)
            )
            record = db.execute(stmt).scalars().first()
            if record:
                return cls._to_evaluation_schema(record)
            return None
        except OperationalError as exc:
            logger.warning(f"Could not query personalization_quality_evaluations: {exc}")
            return None

    @classmethod
    def get_contextual_adaptations(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        context_dimension: str | None = None,
    ) -> list[PersonalizationContextualAdaptationSchema]:
        """
        Query materialized contextual adaptations for a researcher.
        """
        try:
            stmt = select(PersonalizationContextualAdaptationModel).where(
                PersonalizationContextualAdaptationModel.profile_id == profile_id
            )
            if context_dimension:
                stmt = stmt.where(PersonalizationContextualAdaptationModel.context_type == context_dimension)

            stmt = stmt.order_by(
                PersonalizationContextualAdaptationModel.signal_dimension.asc(),
                PersonalizationContextualAdaptationModel.signal_value.asc(),
                PersonalizationContextualAdaptationModel.context_type.asc(),
                PersonalizationContextualAdaptationModel.context_value.asc(),
            )
            records = db.execute(stmt).scalars().all()
            return [
                PersonalizationContextualAdaptationSchema(
                    id=r.id,
                    profile_id=r.profile_id,
                    dimension=r.signal_dimension,
                    signal_value=r.signal_value,
                    context_dimension=r.context_type,
                    context_value=r.context_value,
                    sample_size=r.recommendations_count,
                    positive_count=r.positive_outcome_count,
                    negative_count=r.negative_outcome_count,
                    observed_lift=r.contextual_lift or 0.0,
                    confidence=r.confidence,
                    fallback_level=ContextualFallbackLevel(r.fallback_level),
                    contextual_modifier=r.contextual_modifier,
                    hysteresis_state="STABLE",
                    evaluation_state=QualityEvaluationState(r.adaptation_state),
                    deterministic_explanation=r.deterministic_explanation,
                    algorithm_version=r.algorithm_version,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in records
            ]
        except OperationalError as exc:
            logger.warning(f"Could not query personalization_contextual_adaptations: {exc}")
            return []

    @classmethod
    def recompute_personalization_quality(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        reference_time: datetime | None = None,
        evaluation_period_days: float = 30.0,
        config: PersonalizationQualityConfig = DEFAULT_QUALITY_CONFIG,
    ) -> tuple[
        PersonalizationQualityEvaluationSchema,
        list[PersonalizationContextualAdaptationSchema],
        list[ContextualSummaryItem],
        list[SignalQualitySummaryItem],
    ]:
        """
        Recompute personalization quality evaluation and contextual adaptations for a researcher.
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # 1. Fetch recommendation items for this researcher
        rec_items = db.execute(
            select(ResearcherRecommendationItemModel)
            .join(ResearcherRecommendationSnapshotModel)
            .where(ResearcherRecommendationSnapshotModel.researcher_id == profile_id)
            .order_by(ResearcherRecommendationItemModel.created_at.asc())
        ).scalars().all()

        # 2. Fetch interactions for this researcher
        interactions = db.execute(
            select(ResearcherInteractionModel)
            .where(ResearcherInteractionModel.profile_id == profile_id)
            .order_by(ResearcherInteractionModel.created_at.asc())
        ).scalars().all()

        # 3. Fetch attributions for this researcher (Phase 5.6)
        attributions = db.execute(
            select(RecommendationFeedbackAttributionModel)
            .where(RecommendationFeedbackAttributionModel.profile_id == profile_id)
        ).scalars().all()

        # 4. Fetch active adaptive signals (Phase 5.5)
        signals = AdaptivePreferenceSignalService.get_adaptive_signals(db, profile_id)

        # 5. Fetch calibrations (Phase 5.6)
        calibrations = PersonalizationCalibrationService.get_calibrations(db, profile_id)

        # 6. Fetch researcher profile (for academic status)
        researcher_profile = db.execute(
            select(ResearchProfileModel).where(ResearchProfileModel.id == profile_id)
        ).scalars().first()

        # 7. Gather all needed opportunity models in one query (zero N+1)
        needed_opp_ids = {r.opportunity_id for r in rec_items} | {i.opportunity_id for i in interactions}
        opportunities_map: dict[uuid.UUID, OpportunityModel] = {}
        if needed_opp_ids:
            opps = db.execute(
                select(OpportunityModel)
                .options(selectinload(OpportunityModel.topic_associations))
                .where(OpportunityModel.id.in_(needed_opp_ids))
            ).scalars().all()
            opportunities_map = {o.id: o for o in opps}

        # 8. Run calculation engine
        evaluation, adaptations, summaries, signal_qualities = PersonalizationQualityEngine.evaluate_personalization_quality(
            profile_id=profile_id,
            recommendation_items=rec_items,
            interactions=interactions,
            attributions=attributions,
            opportunities=opportunities_map,
            signals=signals,
            calibrations=calibrations,
            researcher_profile=researcher_profile,
            reference_time=ref_time,
            evaluation_period_days=evaluation_period_days,
            config=config,
        )

        # 9. Persist to database (dialect-neutral update-or-insert)
        try:
            # 9a. Persist evaluation
            existing_eval = db.execute(
                select(PersonalizationQualityEvaluationModel)
                .where(PersonalizationQualityEvaluationModel.profile_id == profile_id)
                .order_by(PersonalizationQualityEvaluationModel.created_at.desc())
                .limit(1)
            ).scalars().first()

            eval_state_val = (
                evaluation.evaluation_state.value
                if hasattr(evaluation.evaluation_state, "value")
                else str(evaluation.evaluation_state)
            )

            if existing_eval:
                existing_eval.evaluation_window_days = evaluation.evaluation_period_days
                existing_eval.evaluation_timestamp = ref_time
                existing_eval.total_recommendations_evaluated = evaluation.recommendations_evaluated_count
                existing_eval.total_attributed_interactions = evaluation.attributed_interactions_count
                existing_eval.positive_outcome_count = evaluation.positive_outcomes_count
                existing_eval.negative_outcome_count = evaluation.negative_outcomes_count
                existing_eval.neutral_outcome_count = evaluation.neutral_outcomes_count
                existing_eval.engagement_rate = evaluation.observed_engagement_rate
                existing_eval.positive_feedback_rate = evaluation.observed_positive_rate
                existing_eval.negative_feedback_rate = evaluation.observed_negative_rate
                existing_eval.observed_personalization_lift = evaluation.observed_personalization_lift
                existing_eval.confidence = evaluation.confidence
                existing_eval.evaluation_state = eval_state_val
                existing_eval.recommendation_diversity_score = evaluation.diversity_score
                existing_eval.novelty_rate = evaluation.novelty_rate
                existing_eval.quality_metrics_breakdown = evaluation.contextual_breakdown
                existing_eval.deterministic_explanation = evaluation.deterministic_explanation
                existing_eval.algorithm_version = evaluation.algorithm_version
                existing_eval.updated_at = ref_time
            else:
                new_eval = PersonalizationQualityEvaluationModel(
                    id=evaluation.id,
                    profile_id=profile_id,
                    evaluation_window_days=evaluation.evaluation_period_days,
                    evaluation_timestamp=ref_time,
                    total_recommendations_evaluated=evaluation.recommendations_evaluated_count,
                    total_attributed_interactions=evaluation.attributed_interactions_count,
                    positive_outcome_count=evaluation.positive_outcomes_count,
                    negative_outcome_count=evaluation.negative_outcomes_count,
                    neutral_outcome_count=evaluation.neutral_outcomes_count,
                    engagement_rate=evaluation.observed_engagement_rate,
                    positive_feedback_rate=evaluation.observed_positive_rate,
                    negative_feedback_rate=evaluation.observed_negative_rate,
                    observed_personalization_lift=evaluation.observed_personalization_lift,
                    confidence=evaluation.confidence,
                    evaluation_state=eval_state_val,
                    recommendation_diversity_score=evaluation.diversity_score,
                    novelty_rate=evaluation.novelty_rate,
                    quality_metrics_breakdown=evaluation.contextual_breakdown,
                    deterministic_explanation=evaluation.deterministic_explanation,
                    algorithm_version=evaluation.algorithm_version,
                    created_at=ref_time,
                    updated_at=ref_time,
                )
                db.add(new_eval)

            # 9b. Persist contextual adaptations
            existing_adaptations = db.execute(
                select(PersonalizationContextualAdaptationModel).where(
                    PersonalizationContextualAdaptationModel.profile_id == profile_id
                )
            ).scalars().all()
            existing_adapt_by_key = {
                (a.signal_dimension, a.signal_value, a.context_type, a.context_value): a
                for a in existing_adaptations
            }
            new_adapt_keys = set()

            for adapt in adaptations:
                key = (adapt.dimension, adapt.signal_value, adapt.context_dimension, adapt.context_value)
                new_adapt_keys.add(key)
                state_val = (
                    adapt.evaluation_state.value
                    if hasattr(adapt.evaluation_state, "value")
                    else str(adapt.evaluation_state)
                )
                fallback_val = (
                    adapt.fallback_level.value
                    if hasattr(adapt.fallback_level, "value")
                    else str(adapt.fallback_level)
                )

                if key in existing_adapt_by_key:
                    m = existing_adapt_by_key[key]
                    m.recommendations_count = adapt.sample_size
                    m.positive_outcome_count = adapt.positive_count
                    m.negative_outcome_count = adapt.negative_count
                    m.contextual_lift = adapt.observed_lift
                    m.confidence = adapt.confidence
                    m.fallback_level = fallback_val
                    m.contextual_modifier = adapt.contextual_modifier
                    m.adaptation_state = state_val
                    m.deterministic_explanation = adapt.deterministic_explanation
                    m.algorithm_version = adapt.algorithm_version
                    m.updated_at = ref_time
                else:
                    new_m = PersonalizationContextualAdaptationModel(
                        id=adapt.id,
                        profile_id=profile_id,
                        signal_dimension=adapt.dimension,
                        signal_value=adapt.signal_value,
                        context_type=adapt.context_dimension,
                        context_value=adapt.context_value,
                        recommendations_count=adapt.sample_size,
                        positive_outcome_count=adapt.positive_count,
                        negative_outcome_count=adapt.negative_count,
                        contextual_lift=adapt.observed_lift,
                        confidence=adapt.confidence,
                        fallback_level=fallback_val,
                        contextual_modifier=adapt.contextual_modifier,
                        adaptation_state=state_val,
                        deterministic_explanation=adapt.deterministic_explanation,
                        algorithm_version=adapt.algorithm_version,
                        created_at=ref_time,
                        updated_at=ref_time,
                    )
                    db.add(new_m)

            # Remove stale adaptations
            for key, old_m in existing_adapt_by_key.items():
                if key not in new_adapt_keys:
                    db.delete(old_m)

            db.flush()
        except OperationalError as exc:
            logger.warning(f"Could not persist personalization quality evaluation: {exc}")

        return evaluation, adaptations, summaries, signal_qualities

    @classmethod
    def get_quality_response(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> PersonalizationQualityResponse:
        """
        Get aggregated quality response for a researcher, computing if not yet present.
        """
        evaluation = cls.get_latest_quality_evaluation(db, profile_id)
        if not evaluation:
            evaluation, _, summaries, _ = cls.recompute_personalization_quality(db, profile_id)
            context_summaries = summaries
        else:
            raw_contexts = evaluation.contextual_breakdown.get("contexts", [])
            context_summaries = [ContextualSummaryItem.model_validate(c) for c in raw_contexts]

        return PersonalizationQualityResponse(
            profile_id=profile_id,
            evaluation=evaluation,
            context_summaries=context_summaries,
            deterministic_explanation=evaluation.deterministic_explanation,
        )

    @classmethod
    def get_contextual_adaptations_response(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        context_dimension: str | None = None,
    ) -> ContextualAdaptationsResponse:
        """
        Get contextual adaptations response for a researcher.
        """
        adaptations = cls.get_contextual_adaptations(db, profile_id, context_dimension=context_dimension)
        return ContextualAdaptationsResponse(
            profile_id=profile_id,
            items=adaptations,
            total_count=len(adaptations),
        )

    @classmethod
    def get_signal_quality_response(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> SignalQualityResponse:
        """
        Get signal-level quality response for a researcher.
        """
        _, _, _, signal_qualities = cls.recompute_personalization_quality(db, profile_id)
        return SignalQualityResponse(
            profile_id=profile_id,
            items=signal_qualities,
            total_count=len(signal_qualities),
        )
