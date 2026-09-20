"""
Personalization Governance, Drift Detection & Adaptation Safety Service (Phase 5.8).

Handles database persistence, eager bulk loading with zero N+1 queries,
deterministic recomputation, and multi-tenant isolation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.personalization_governance import (
    AdaptationState,
    DriftType,
    EvidenceStrength,
    GovernanceEventType,
    GovernanceGateState,
    PersonalizationDriftEvaluationModel,
    PersonalizationGovernanceEventModel,
    PersonalizationHealthState,
    PreferenceAlignmentState,
    SignalFreshnessState,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import ResearcherInteractionModel
from app.personalization.governance_config import (
    DEFAULT_GOVERNANCE_CONFIG,
    PersonalizationGovernanceConfig,
)
from app.personalization.governance_engine import PersonalizationGovernanceEngine
from app.schemas.personalization_governance import (
    PersonalizationDriftEvaluationSchema,
    PersonalizationDriftResponse,
    PersonalizationGovernanceEventSchema,
    PersonalizationGovernanceHistoryResponse,
    PersonalizationHealthResponse,
    SignalDriftItem,
)
from app.schemas.personalization_quality import (
    PersonalizationContextualAdaptationSchema,
    PersonalizationQualityEvaluationSchema,
)
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService
from app.services.personalization_calibration_service import PersonalizationCalibrationService
from app.services.personalization_quality_service import PersonalizationQualityService
from app.services.researcher_preference_service import ResearcherPreferenceService

logger = logging.getLogger(__name__)


class PersonalizationGovernanceService:
    """
    Database and service layer for personalization governance and drift detection.
    """

    @classmethod
    def get_latest_drift_evaluation(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> PersonalizationDriftEvaluationModel | None:
        """Fetch the most recent drift evaluation for a researcher."""
        try:
            stmt = (
                select(PersonalizationDriftEvaluationModel)
                .where(PersonalizationDriftEvaluationModel.profile_id == profile_id)
                .order_by(desc(PersonalizationDriftEvaluationModel.updated_at))
                .limit(1)
            )
            return db.execute(stmt).scalar_one_or_none()
        except Exception as e:
            logger.warning("Could not query personalization_drift_evaluations: %s", e)
            return None

    @classmethod
    def get_active_governance_state(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> GovernanceGateState:
        """Fast lookup of the active governance decision state for a researcher."""
        eval_model = cls.get_latest_drift_evaluation(db, profile_id)
        if not eval_model:
            return GovernanceGateState.ALLOW
        try:
            return GovernanceGateState(eval_model.governance_state)
        except (ValueError, KeyError):
            return GovernanceGateState.ALLOW

    @classmethod
    def get_governance_events(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PersonalizationGovernanceEventModel], int]:
        """Fetch paginated audit log of governance events."""
        try:
            count_stmt = (
                select(func.count(PersonalizationGovernanceEventModel.id))
                .where(PersonalizationGovernanceEventModel.profile_id == profile_id)
            )
            total_count = db.execute(count_stmt).scalar() or 0

            stmt = (
                select(PersonalizationGovernanceEventModel)
                .where(PersonalizationGovernanceEventModel.profile_id == profile_id)
                .order_by(desc(PersonalizationGovernanceEventModel.created_at))
                .limit(limit)
                .offset(offset)
            )
            events = list(db.execute(stmt).scalars().all())
            return events, total_count
        except Exception as e:
            logger.warning("Could not query personalization_governance_events: %s", e)
            return [], 0

    def __init__(self, db: Session, config: PersonalizationGovernanceConfig = DEFAULT_GOVERNANCE_CONFIG):
        self.db = db
        self.config = config

    def evaluate_researcher_governance(
        self,
        profile_id: uuid.UUID,
        reference_time: datetime | None = None,
        force_recompute: bool = False,
    ) -> tuple[PersonalizationDriftEvaluationSchema, list[PersonalizationGovernanceEventSchema]]:
        return self.recompute_governance(
            db=self.db,
            profile_id=profile_id,
            reference_time=reference_time,
            config=self.config,
        )

    @classmethod
    def recompute_governance(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        reference_time: datetime | None = None,
        historical_window_days: float | None = None,
        recent_window_days: float | None = None,
        config: PersonalizationGovernanceConfig = DEFAULT_GOVERNANCE_CONFIG,
    ) -> tuple[PersonalizationDriftEvaluationSchema, list[PersonalizationGovernanceEventSchema]]:
        """
        Idempotently recomputes personalization health, signal drift, and governance state
        from recommendation, interaction, and preference history deterministically with zero N+1 queries.
        """
        now = reference_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if historical_window_days or recent_window_days:
            config = PersonalizationGovernanceConfig(
                algorithm_version=config.algorithm_version,
                default_historical_window_days=historical_window_days or config.default_historical_window_days,
                default_recent_window_days=recent_window_days or config.default_recent_window_days,
                min_recent_window_days=config.min_recent_window_days,
                max_recent_window_days=config.max_recent_window_days,
                max_historical_window_days=config.max_historical_window_days,
                stale_evidence_days=config.stale_evidence_days,
                min_interactions_for_evaluation=config.min_interactions_for_evaluation,
                min_recent_interactions_for_drift=config.min_recent_interactions_for_drift,
                medium_evidence_interactions=config.medium_evidence_interactions,
                high_evidence_interactions=config.high_evidence_interactions,
                drift_difference_threshold=config.drift_difference_threshold,
                reversing_drift_threshold=config.reversing_drift_threshold,
                stable_difference_threshold=config.stable_difference_threshold,
                allow_multiplier=config.allow_multiplier,
                allow_bounded_multiplier=config.allow_bounded_multiplier,
                hold_multiplier=config.hold_multiplier,
                reduce_multiplier=config.reduce_multiplier,
                suspend_multiplier=config.suspend_multiplier,
                hysteresis_min_evidence=config.hysteresis_min_evidence,
                recovery_evidence_threshold=config.recovery_evidence_threshold,
                recovery_stability_ratio=config.recovery_stability_ratio,
                max_contextual_modifier=config.max_contextual_modifier,
                min_contextual_modifier=config.min_contextual_modifier,
                max_calibration_modifier=config.max_calibration_modifier,
                min_calibration_modifier=config.min_calibration_modifier,
                max_total_adaptive_contribution=config.max_total_adaptive_contribution,
                min_total_adaptive_contribution=config.min_total_adaptive_contribution,
            )

        # 1. Eager bulk loading (zero N+1 queries)
        # Fetch profile
        profile = db.get(ResearchProfileModel, profile_id)
        if not profile:
            raise ValueError(f"Researcher profile with ID '{profile_id}' not found.")

        # Explicit preferences
        structured_prefs = ResearcherPreferenceService.get_structured_preferences(db, profile_id)

        # Raw interactions (with joined opportunity)
        int_stmt = (
            select(ResearcherInteractionModel)
            .where(ResearcherInteractionModel.profile_id == profile_id)
            .options(joinedload(ResearcherInteractionModel.opportunity))
            .order_by(ResearcherInteractionModel.created_at)
        )
        interactions = list(db.execute(int_stmt).scalars().all())

        # Adaptive signals
        adaptive_signals = AdaptivePreferenceSignalService.get_adaptive_signals(db, profile_id)

        # Calibrations
        calibrations = PersonalizationCalibrationService.get_calibrations(db, profile_id)

        # Quality evaluation
        quality_schema = PersonalizationQualityService.get_latest_quality_evaluation(db, profile_id)

        # Contextual adaptations
        contextual_adaptations = PersonalizationQualityService.get_contextual_adaptations(db, profile_id)

        # Previous governance state for hysteresis
        prev_eval = cls.get_latest_drift_evaluation(db, profile_id)
        prev_state = None
        if prev_eval:
            try:
                prev_state = GovernanceGateState(prev_eval.governance_state)
            except (ValueError, KeyError):
                prev_state = None

        # 2. Run Pure Governance Engine
        eval_schema, events = PersonalizationGovernanceEngine.evaluate_governance(
            profile_id=profile_id,
            explicit_preferences=structured_prefs.raw_preferences if structured_prefs else [],
            interactions=interactions,
            adaptive_signals=adaptive_signals,
            calibrations=calibrations,
            quality_evaluation=quality_schema,
            contextual_adaptations=contextual_adaptations,
            previous_governance_state=prev_state,
            reference_time=now,
            config=config,
        )

        # 3. Dialect-neutral Upsert of PersonalizationDriftEvaluationModel
        existing_stmt = select(PersonalizationDriftEvaluationModel).where(
            PersonalizationDriftEvaluationModel.profile_id == profile_id,
            PersonalizationDriftEvaluationModel.algorithm_version == config.algorithm_version,
        )
        existing_model = db.execute(existing_stmt).scalar_one_or_none()

        drift_details_json = [item.model_dump(mode="json") for item in eval_schema.drift_details]

        if existing_model:
            eval_schema = eval_schema.model_copy(
                update={"id": existing_model.id, "created_at": existing_model.created_at}
            )
            existing_model.evaluation_timestamp = eval_schema.evaluation_timestamp
            existing_model.historical_window_days = eval_schema.historical_window_days
            existing_model.recent_window_days = eval_schema.recent_window_days
            existing_model.overall_health_state = eval_schema.overall_health_state.value
            existing_model.governance_state = eval_schema.governance_state.value
            existing_model.adaptation_state = eval_schema.adaptation_state.value
            existing_model.signal_freshness = eval_schema.signal_freshness.value
            existing_model.evidence_sufficiency = eval_schema.evidence_sufficiency.value
            existing_model.quality_stability = eval_schema.quality_stability
            existing_model.context_stability = eval_schema.context_stability
            existing_model.preference_alignment = eval_schema.preference_alignment.value
            existing_model.recommendation_diversity = eval_schema.recommendation_diversity
            existing_model.drifting_signals_count = eval_schema.drifting_signals_count
            existing_model.stale_signals_count = eval_schema.stale_signals_count
            existing_model.active_signals_count = eval_schema.active_signals_count
            existing_model.drift_details = drift_details_json
            existing_model.health_summary = eval_schema.health_summary
            existing_model.governance_explanation = eval_schema.governance_explanation
            existing_model.updated_at = now
        else:
            new_model = PersonalizationDriftEvaluationModel(
                id=eval_schema.id,
                profile_id=profile_id,
                evaluation_timestamp=eval_schema.evaluation_timestamp,
                historical_window_days=eval_schema.historical_window_days,
                recent_window_days=eval_schema.recent_window_days,
                overall_health_state=eval_schema.overall_health_state.value,
                governance_state=eval_schema.governance_state.value,
                adaptation_state=eval_schema.adaptation_state.value,
                signal_freshness=eval_schema.signal_freshness.value,
                evidence_sufficiency=eval_schema.evidence_sufficiency.value,
                quality_stability=eval_schema.quality_stability,
                context_stability=eval_schema.context_stability,
                preference_alignment=eval_schema.preference_alignment.value,
                recommendation_diversity=eval_schema.recommendation_diversity,
                drifting_signals_count=eval_schema.drifting_signals_count,
                stale_signals_count=eval_schema.stale_signals_count,
                active_signals_count=eval_schema.active_signals_count,
                drift_details=drift_details_json,
                health_summary=eval_schema.health_summary,
                governance_explanation=eval_schema.governance_explanation,
                algorithm_version=eval_schema.algorithm_version,
                created_at=now,
                updated_at=now,
            )
            db.add(new_model)

        # 4. Record Governance Events (Append-only)
        for ev in events:
            event_model = PersonalizationGovernanceEventModel(
                id=ev.id,
                profile_id=profile_id,
                event_type=ev.event_type.value,
                previous_state=ev.previous_state,
                new_state=ev.new_state,
                reason=ev.reason,
                affected_dimension=ev.affected_dimension,
                affected_signal_value=ev.affected_signal_value,
                evidence_count=ev.evidence_count,
                reference_time=ev.reference_time,
                algorithm_version=ev.algorithm_version,
                created_at=ev.created_at,
            )
            db.add(event_model)

        db.flush()
        return eval_schema, events

    @classmethod
    def get_health_response(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> PersonalizationHealthResponse:
        """Prepares structured API response for researcher personalization health."""
        eval_model = cls.get_latest_drift_evaluation(db, profile_id)
        if not eval_model:
            # Recompute on demand
            eval_schema, _ = cls.recompute_governance(db, profile_id)
            db.commit()
            return PersonalizationHealthResponse(
                profile_id=profile_id,
                evaluation=eval_schema,
                overall_health_state=eval_schema.overall_health_state,
                governance_state=eval_schema.governance_state,
                adaptation_state=eval_schema.adaptation_state,
                drifting_signals_count=eval_schema.drifting_signals_count,
                stale_signals_count=eval_schema.stale_signals_count,
                health_summary=eval_schema.health_summary,
                governance_explanation=eval_schema.governance_explanation,
            )

        eval_schema = cls._to_evaluation_schema(eval_model)
        return PersonalizationHealthResponse(
            profile_id=profile_id,
            evaluation=eval_schema,
            overall_health_state=eval_schema.overall_health_state,
            governance_state=eval_schema.governance_state,
            adaptation_state=eval_schema.adaptation_state,
            drifting_signals_count=eval_schema.drifting_signals_count,
            stale_signals_count=eval_schema.stale_signals_count,
            health_summary=eval_schema.health_summary,
            governance_explanation=eval_schema.governance_explanation,
        )

    @classmethod
    def get_drift_response(
        cls,
        db: Session,
        profile_id: uuid.UUID,
    ) -> PersonalizationDriftResponse:
        """Prepares structured API response containing granular signal-level drift classifications."""
        eval_model = cls.get_latest_drift_evaluation(db, profile_id)
        if not eval_model:
            eval_schema, _ = cls.recompute_governance(db, profile_id)
            db.commit()
            drift_items = eval_schema.drift_details
        else:
            drift_items = [
                SignalDriftItem.model_validate(item)
                for item in (eval_model.drift_details or [])
            ]

        drifting = [d for d in drift_items if d.drift_type in (DriftType.EMERGING, DriftType.PERSISTENT, DriftType.REVERSING)]
        stale = [d for d in drift_items if d.is_stale]
        stable = [d for d in drift_items if d.drift_type == DriftType.STABLE]

        return PersonalizationDriftResponse(
            profile_id=profile_id,
            drifting_signals=drifting,
            stale_signals=stale,
            stable_signals=stable,
            total_signals=len(drift_items),
        )

    @classmethod
    def get_governance_events_response(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> PersonalizationGovernanceHistoryResponse:
        """Prepares structured API response for paginated governance audit events."""
        event_models, total_count = cls.get_governance_events(db, profile_id, limit, offset)
        items = [
            PersonalizationGovernanceEventSchema(
                id=ev.id,
                profile_id=ev.profile_id,
                event_type=GovernanceEventType(ev.event_type),
                previous_state=ev.previous_state,
                new_state=ev.new_state,
                reason=ev.reason,
                affected_dimension=ev.affected_dimension,
                affected_signal_value=ev.affected_signal_value,
                evidence_count=ev.evidence_count,
                reference_time=ev.reference_time,
                algorithm_version=ev.algorithm_version,
                created_at=ev.created_at,
            )
            for ev in event_models
        ]
        return PersonalizationGovernanceHistoryResponse(
            profile_id=profile_id,
            items=items,
            total_count=total_count,
        )

    @classmethod
    def _to_evaluation_schema(
        cls,
        model: PersonalizationDriftEvaluationModel,
    ) -> PersonalizationDriftEvaluationSchema:
        """Converts database model to domain schema."""
        drift_items = [
            SignalDriftItem.model_validate(item)
            for item in (model.drift_details or [])
        ]
        return PersonalizationDriftEvaluationSchema(
            id=model.id,
            profile_id=model.profile_id,
            evaluation_timestamp=model.evaluation_timestamp,
            historical_window_days=model.historical_window_days,
            recent_window_days=model.recent_window_days,
            overall_health_state=PersonalizationHealthState(model.overall_health_state),
            governance_state=GovernanceGateState(model.governance_state),
            adaptation_state=AdaptationState(model.adaptation_state),
            signal_freshness=SignalFreshnessState(model.signal_freshness),
            evidence_sufficiency=EvidenceStrength(model.evidence_sufficiency),
            quality_stability=model.quality_stability,
            context_stability=model.context_stability,
            preference_alignment=PreferenceAlignmentState(model.preference_alignment),
            recommendation_diversity=model.recommendation_diversity,
            drifting_signals_count=model.drifting_signals_count,
            stale_signals_count=model.stale_signals_count,
            active_signals_count=model.active_signals_count,
            drift_details=drift_items,
            health_summary=model.health_summary,
            governance_explanation=model.governance_explanation,
            algorithm_version=model.algorithm_version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
