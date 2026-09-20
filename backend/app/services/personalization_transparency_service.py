from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.adaptive_signal import AdaptivePreferenceSignalModel
from app.models.opportunity import OpportunityModel
from app.models.personalization_calibration import PersonalizationCalibrationModel
from app.models.personalization_governance import (
    GovernanceGateState,
    PersonalizationDriftEvaluationModel,
)
from app.models.personalization_quality import (
    PersonalizationContextualAdaptationModel,
)
from app.models.personalization_transparency import (
    PersonalizationControlEventModel,
    PersonalizationControlEventType,
    PersonalizationImpact,
    ResearcherPersonalizationSettingsModel,
)
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.researcher_preference import ResearcherPreferenceModel
from app.personalization.governance_config import DEFAULT_GOVERNANCE_CONFIG
from app.personalization.transparency_config import (
    DEFAULT_TRANSPARENCY_CONFIG,
    PersonalizationTransparencyConfig,
)
from app.personalization.transparency_engine import PersonalizationTransparencyEngine
from app.schemas.adaptive_signal import AdaptivePreferenceSignal
from app.schemas.personalization_calibration import PersonalizationCalibrationSchema
from app.schemas.personalization_quality import (
    ContextualFallbackLevel,
    PersonalizationContextualAdaptationSchema,
    QualityEvaluationState,
)
from app.schemas.personalization_transparency import (
    PersonalizationControlEventSchema,
    PersonalizationControlHistoryResponse,
    PersonalizationResetResponse,
    RecommendationPersonalizationExplanationResponse,
    ResearcherPersonalizationSettingsSchema,
    ResearcherPersonalizationSettingsUpdate,
)
from app.schemas.researcher_preference import ResearcherPreferenceItemSchema

logger = logging.getLogger(__name__)


class PersonalizationTransparencyService:
    """
    Production-grade service managing researcher personalization controls, settings,
    reset operations, and deterministic recommendation explanations (Phase 5.9).

    Strict Architectural Boundaries:
      - Zero ML / Zero LLMs: 100% deterministic, rule-based logic.
      - Safe Reset: Invalidation of derived state by state version increment without
        deleting user accounts, profiles, explicit preferences, or audit records.
      - Zero N+1: Batch eagerly loads data in bounded queries.
    """

    @classmethod
    def get_or_create_settings(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> ResearcherPersonalizationSettingsModel:
        """
        Retrieves or bootstraps default personalization settings for a researcher.
        """
        settings = (
            db.execute(
                select(ResearcherPersonalizationSettingsModel).where(
                    ResearcherPersonalizationSettingsModel.profile_id == profile_id
                )
            )
            .scalar_one_or_none()
        )

        if not settings:
            settings = ResearcherPersonalizationSettingsModel(
                profile_id=profile_id,
                personalization_enabled=True,
                adaptive_signals_enabled=True,
                feedback_learning_enabled=True,
                personalization_state_version=1,
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)

        return settings

    @classmethod
    def update_settings(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        payload: ResearcherPersonalizationSettingsUpdate,
        trigger_reason: str = "User updated personalization settings",
    ) -> ResearcherPersonalizationSettingsModel:
        """
        Updates researcher personalization settings and records an append-only audit event.
        """
        settings = cls.get_or_create_settings(db, profile_id)

        prev_state = {
            "personalization_enabled": settings.personalization_enabled,
            "adaptive_signals_enabled": settings.adaptive_signals_enabled,
            "feedback_learning_enabled": settings.feedback_learning_enabled,
            "personalization_state_version": settings.personalization_state_version,
        }

        # Determine primary event type
        event_type = PersonalizationControlEventType.PERSONALIZATION_ENABLED
        if payload.personalization_enabled is not None and payload.personalization_enabled != settings.personalization_enabled:
            settings.personalization_enabled = payload.personalization_enabled
            event_type = (
                PersonalizationControlEventType.PERSONALIZATION_ENABLED
                if payload.personalization_enabled
                else PersonalizationControlEventType.PERSONALIZATION_DISABLED
            )

        if payload.adaptive_signals_enabled is not None and payload.adaptive_signals_enabled != settings.adaptive_signals_enabled:
            settings.adaptive_signals_enabled = payload.adaptive_signals_enabled
            if payload.personalization_enabled is None:
                event_type = (
                    PersonalizationControlEventType.ADAPTIVE_SIGNALS_ENABLED
                    if payload.adaptive_signals_enabled
                    else PersonalizationControlEventType.ADAPTIVE_SIGNALS_DISABLED
                )

        if payload.feedback_learning_enabled is not None and payload.feedback_learning_enabled != settings.feedback_learning_enabled:
            settings.feedback_learning_enabled = payload.feedback_learning_enabled
            if payload.personalization_enabled is None and payload.adaptive_signals_enabled is None:
                event_type = (
                    PersonalizationControlEventType.FEEDBACK_LEARNING_ENABLED
                    if payload.feedback_learning_enabled
                    else PersonalizationControlEventType.FEEDBACK_LEARNING_DISABLED
                )

        new_state = {
            "personalization_enabled": settings.personalization_enabled,
            "adaptive_signals_enabled": settings.adaptive_signals_enabled,
            "feedback_learning_enabled": settings.feedback_learning_enabled,
            "personalization_state_version": settings.personalization_state_version,
        }

        # Record audit event
        audit_event = PersonalizationControlEventModel(
            profile_id=profile_id,
            event_type=event_type.value,
            previous_state=prev_state,
            new_state=new_state,
            trigger_reason=trigger_reason,
            algorithm_version=DEFAULT_TRANSPARENCY_CONFIG.algorithm_version,
        )
        db.add(audit_event)

        db.commit()
        db.refresh(settings)
        return settings

    @classmethod
    def reset_personalization(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        reason: str = "User requested personalization reset",
    ) -> PersonalizationResetResponse:
        """
        Safely and idempotently resets derived personalization state while strictly preserving:
          - researcher account
          - researcher profile
          - explicit preferences (Phase 5.1)
          - recommendation history (Phase 3.7)
          - mandatory audit trail
        """
        settings = cls.get_or_create_settings(db, profile_id)

        prev_state = {
            "personalization_enabled": settings.personalization_enabled,
            "adaptive_signals_enabled": settings.adaptive_signals_enabled,
            "feedback_learning_enabled": settings.feedback_learning_enabled,
            "personalization_state_version": settings.personalization_state_version,
        }

        # 1. Increment personalization state version
        settings.personalization_state_version += 1
        new_version = settings.personalization_state_version

        # 2. Count and neutralize derived adaptive signals (Phase 5.5)
        adaptive_count = db.scalar(
            select(func.count(AdaptivePreferenceSignalModel.id)).where(
                AdaptivePreferenceSignalModel.profile_id == profile_id
            )
        ) or 0

        db.execute(
            delete(AdaptivePreferenceSignalModel).where(
                AdaptivePreferenceSignalModel.profile_id == profile_id
            )
        )

        # 3. Count and neutralize calibrations (Phase 5.6)
        calib_count = db.scalar(
            select(func.count(PersonalizationCalibrationModel.id)).where(
                PersonalizationCalibrationModel.profile_id == profile_id
            )
        ) or 0

        db.execute(
            delete(PersonalizationCalibrationModel).where(
                PersonalizationCalibrationModel.profile_id == profile_id
            )
        )

        # 4. Count and neutralize contextual adaptations (Phase 5.7)
        ctx_count = db.scalar(
            select(func.count(PersonalizationContextualAdaptationModel.id)).where(
                PersonalizationContextualAdaptationModel.profile_id == profile_id
            )
        ) or 0

        db.execute(
            delete(PersonalizationContextualAdaptationModel).where(
                PersonalizationContextualAdaptationModel.profile_id == profile_id
            )
        )

        new_state = {
            "personalization_enabled": settings.personalization_enabled,
            "adaptive_signals_enabled": settings.adaptive_signals_enabled,
            "feedback_learning_enabled": settings.feedback_learning_enabled,
            "personalization_state_version": new_version,
        }

        # 5. Record audit event
        audit_event = PersonalizationControlEventModel(
            profile_id=profile_id,
            event_type=PersonalizationControlEventType.PERSONALIZATION_RESET.value,
            previous_state=prev_state,
            new_state=new_state,
            trigger_reason=reason,
            algorithm_version=DEFAULT_TRANSPARENCY_CONFIG.algorithm_version,
        )
        db.add(audit_event)

        db.commit()

        return PersonalizationResetResponse(
            status="SUCCESS",
            personalization_state_version=new_version,
            adaptive_signals_reset=adaptive_count,
            calibration_states_reset=calib_count,
            contextual_modifiers_reset=ctx_count,
            explicit_preferences_changed=0,
            researcher_profile_changed=0,
            message=(
                f"Personalization state successfully reset to version {new_version}. "
                f"Neutralized {adaptive_count} adaptive signals, {calib_count} calibrations, "
                f"and {ctx_count} contextual adaptations. Explicit preferences and profile were preserved."
            ),
            timestamp=datetime.now(timezone.utc),
        )

    @classmethod
    def get_control_history(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> PersonalizationControlHistoryResponse:
        """
        Retrieves paginated control audit events for a researcher.
        """
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)

        total = db.scalar(
            select(func.count(PersonalizationControlEventModel.id)).where(
                PersonalizationControlEventModel.profile_id == profile_id
            )
        ) or 0

        events = (
            db.execute(
                select(PersonalizationControlEventModel)
                .where(PersonalizationControlEventModel.profile_id == profile_id)
                .order_by(PersonalizationControlEventModel.created_at.desc())
                .offset(safe_offset)
                .limit(safe_limit)
            )
            .scalars()
            .all()
        )

        return PersonalizationControlHistoryResponse(
            profile_id=profile_id,
            events=[
                PersonalizationControlEventSchema(
                    id=e.id,
                    profile_id=e.profile_id,
                    event_type=PersonalizationControlEventType(e.event_type),
                    previous_state=e.previous_state,
                    new_state=e.new_state,
                    trigger_reason=e.trigger_reason,
                    algorithm_version=e.algorithm_version,
                    created_at=e.created_at,
                )
                for e in events
            ],
            total=total,
            limit=safe_limit,
            offset=safe_offset,
        )

    @classmethod
    def explain_recommendation_personalization(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        config: PersonalizationTransparencyConfig = DEFAULT_TRANSPARENCY_CONFIG,
    ) -> RecommendationPersonalizationExplanationResponse | None:
        """
        Generates a transparent, deterministic explanation for why a recommendation was personalized.
        Accepts either a ResearcherRecommendationItemModel ID or an OpportunityModel ID.
        """
        # 1. Resolve recommendation item or opportunity
        rec_item = (
            db.execute(
                select(ResearcherRecommendationItemModel)
                .join(
                    ResearcherRecommendationSnapshotModel,
                    ResearcherRecommendationItemModel.snapshot_id == ResearcherRecommendationSnapshotModel.id,
                )
                .options(
                    selectinload(ResearcherRecommendationItemModel.opportunity),
                    selectinload(ResearcherRecommendationItemModel.snapshot),
                )
                .where(
                    ResearcherRecommendationSnapshotModel.researcher_id == profile_id,
                    (
                        (ResearcherRecommendationItemModel.id == recommendation_id)
                        | (ResearcherRecommendationItemModel.opportunity_id == recommendation_id)
                    ),
                )
                .order_by(ResearcherRecommendationItemModel.created_at.desc())
            )
            .scalars()
            .first()
        )

        opportunity: OpportunityModel | None = None
        base_relevance = 0.50
        pers_score = 0.50
        final_score = 0.50

        if rec_item:
            opportunity = rec_item.opportunity
            base_relevance = rec_item.base_relevance_score
            pers_score = rec_item.personalization_score
            final_score = rec_item.final_score
        else:
            # Check if recommendation_id is directly an opportunity ID
            opportunity = db.get(OpportunityModel, recommendation_id)
            if not opportunity:
                return None

        # 2. Eagerly load settings and governance
        settings = cls.get_or_create_settings(db, profile_id)

        # Governance state
        latest_gov = (
            db.execute(
                select(PersonalizationDriftEvaluationModel)
                .where(PersonalizationDriftEvaluationModel.profile_id == profile_id)
                .order_by(PersonalizationDriftEvaluationModel.evaluation_timestamp.desc())
            )
            .scalars()
            .first()
        )
        gov_state = latest_gov.governance_state if latest_gov else GovernanceGateState.ALLOW.value
        gov_mult = 1.0
        if gov_state == GovernanceGateState.ALLOW_BOUNDED.value:
            gov_mult = 0.5
        elif gov_state in (GovernanceGateState.HOLD.value, GovernanceGateState.REDUCE.value):
            gov_mult = 0.25
        elif gov_state == GovernanceGateState.SUSPEND.value:
            gov_mult = 0.0

        # 3. Load explicit preferences
        explicit_prefs = (
            db.execute(
                select(ResearcherPreferenceModel).where(
                    ResearcherPreferenceModel.profile_id == profile_id
                )
            )
            .scalars()
            .all()
        )

        # 4. Load active adaptive signals, calibrations, contextual adaptations
        adaptive_signals_models = (
            db.execute(
                select(AdaptivePreferenceSignalModel).where(
                    AdaptivePreferenceSignalModel.profile_id == profile_id
                )
            )
            .scalars()
            .all()
        )

        calibs_models = (
            db.execute(
                select(PersonalizationCalibrationModel).where(
                    PersonalizationCalibrationModel.profile_id == profile_id
                )
            )
            .scalars()
            .all()
        )

        ctx_models = (
            db.execute(
                select(PersonalizationContextualAdaptationModel).where(
                    PersonalizationContextualAdaptationModel.profile_id == profile_id
                )
            )
            .scalars()
            .all()
        )

        # 5. Evaluate on-the-fly via PersonalizationScorer to get exact match details if needed
        from app.personalization.scorer import PersonalizationScorer

        pref_items = [ResearcherPreferenceItemSchema.model_validate(p) for p in explicit_prefs]
        adaptive_schemas = [AdaptivePreferenceSignal.model_validate(s) for s in adaptive_signals_models]
        calib_schemas = [PersonalizationCalibrationSchema.model_validate(c) for c in calibs_models]
        ctx_schemas = [
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
                fallback_level=ContextualFallbackLevel(r.fallback_level) if hasattr(ContextualFallbackLevel, r.fallback_level or r.fallback_level) in [e.value for e in ContextualFallbackLevel] else ContextualFallbackLevel.RESEARCHER_EXACT_CONTEXT,
                contextual_modifier=r.contextual_modifier,
                hysteresis_state="STABLE",
                evaluation_state=QualityEvaluationState(r.adaptation_state) if r.adaptation_state in [e.value for e in QualityEvaluationState] else QualityEvaluationState.INSUFFICIENT_DATA,
                deterministic_explanation=r.deterministic_explanation,
                algorithm_version=r.algorithm_version,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in ctx_models
        ]

        assessment = PersonalizationScorer.score_opportunity(
            profile_id=profile_id,
            preferences=pref_items,
            opportunity=opportunity,
            adaptive_signals=adaptive_schemas if settings.adaptive_signals_enabled else None,
            calibrations=calib_schemas if settings.adaptive_signals_enabled else None,
            contextual_adaptations=ctx_schemas if settings.adaptive_signals_enabled else None,
            governance_state=gov_state,
        )

        if not rec_item:
            base_relevance = 0.50
            pers_score = assessment.personalization_score
            final_score = round(max(0.0, min(1.0, 0.85 * base_relevance + 0.15 * pers_score)), 4)

        # Extract explicit match factors
        explicit_matches = []
        for c in assessment.breakdown.positive_contributions:
            explicit_matches.append({
                "category": c.dimension.value if hasattr(c.dimension, "value") else str(c.dimension),
                "value": c.preference_value,
                "preference_type": "PREFERRED",
                "match_type": c.match_type.value if hasattr(c.match_type, "value") else str(c.match_type),
            })
        for c in assessment.breakdown.negative_contributions:
            explicit_matches.append({
                "category": c.dimension.value if hasattr(c.dimension, "value") else str(c.dimension),
                "value": c.preference_value,
                "preference_type": "EXCLUDED",
                "match_type": c.match_type.value if hasattr(c.match_type, "value") else str(c.match_type),
            })

        # Extract adaptive factors
        adaptive_factors = []
        for c in assessment.adaptive_contributions:
            adaptive_factors.append({
                "dimension": c.dimension.value if hasattr(c.dimension, "value") else str(c.dimension),
                "signal_value": c.signal_value,
                "contribution": c.bounded_contribution,
            })

        # Extract calibration factors
        calibration_factors = []
        for c in calibs_models:
            calibration_factors.append({
                "dimension": c.dimension,
                "signal_value": c.signal_value,
                "modifier": c.net_calibration_modifier,
            })

        # Extract contextual factors
        contextual_factors = []
        for x in ctx_models:
            contextual_factors.append({
                "context_dimension": x.context_type,
                "context_value": x.context_value,
                "modifier": x.contextual_modifier,
            })

        # Build factors and explanations via PersonalizationTransparencyEngine
        (
            impact,
            expl_factors,
            adapt_factors,
            cal_factors,
            ctx_factors,
            gov_notes,
            summary_list,
            explanation_text,
        ) = PersonalizationTransparencyEngine.build_factors_and_explanation(
            opportunity_title=opportunity.title,
            base_relevance_score=base_relevance,
            personalization_score=pers_score,
            final_score=final_score,
            personalization_enabled=settings.personalization_enabled,
            adaptive_signals_enabled=settings.adaptive_signals_enabled,
            governance_state=gov_state,
            governance_multiplier=gov_mult,
            explicit_matches=explicit_matches,
            adaptive_signals=adaptive_factors,
            calibrations=calibration_factors,
            contextual_adaptations=contextual_factors,
            config=config,
        )

        return RecommendationPersonalizationExplanationResponse(
            recommendation_id=recommendation_id,
            opportunity_id=opportunity.id,
            opportunity_title=opportunity.title,
            personalization_impact=impact,
            base_relevance_score=base_relevance,
            personalization_score=pers_score,
            final_score=final_score,
            explicit_preference_factors=expl_factors,
            adaptive_signal_factors=adapt_factors,
            calibration_factors=cal_factors,
            contextual_factors=ctx_factors,
            governance_state=gov_state,
            governance_multiplier=gov_mult,
            governance_notes=gov_notes,
            deterministic_explanation=explanation_text,
            contributing_factors_summary=summary_list,
            algorithm_version=config.algorithm_version,
            evaluated_at=datetime.now(timezone.utc),
            personalization_state_version=settings.personalization_state_version,
        )
