"""
Personalization Calibration Service for Phase 5.6 — Adaptive Personalization Calibration & Recommendation Feedback Loop.

Guarantees:
  - Zero N+1 queries: eager/batch loading across recommendation items, interactions, and opportunities.
  - Multi-tenant isolation: all operations strictly scoped by profile_id.
  - Idempotent recomputation: upsert via unique constraint (profile_id, dimension, signal_value).
  - Clean error recovery: handles unmigrated environments gracefully.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from app.models.adaptive_signal import AdaptivePreferenceSignalModel
from app.models.opportunity import OpportunityModel
from app.models.personalization_calibration import (
    CalibrationState,
    PersonalizationCalibrationModel,
    RecommendationFeedbackAttributionModel,
)
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.researcher_interaction import ResearcherInteractionModel
from app.personalization.adaptive_models import AdaptivePreferenceSignal
from app.personalization.calibration_config import (
    DEFAULT_CALIBRATION_CONFIG,
    PersonalizationCalibrationConfig,
)
from app.personalization.calibration_engine import PersonalizationCalibrationEngine
from app.schemas.personalization_calibration import (
    PersonalizationCalibrationDetailResponse,
    PersonalizationCalibrationResponse,
    PersonalizationCalibrationSchema,
    RecommendationFeedbackAttributionSchema,
)
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService

logger = logging.getLogger(__name__)


class PersonalizationCalibrationService:
    """Service managing persistent recommendation feedback attribution and personalization calibration."""

    @classmethod
    def get_calibrations(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        dimension: str | None = None,
        state: CalibrationState | None = None,
    ) -> list[PersonalizationCalibrationSchema]:
        """
        Query materialized personalization calibrations for a researcher.
        """
        try:
            stmt = select(PersonalizationCalibrationModel).where(
                PersonalizationCalibrationModel.profile_id == profile_id
            )
            if dimension is not None:
                dim_str = dimension.value if hasattr(dimension, "value") else dimension
                stmt = stmt.where(PersonalizationCalibrationModel.dimension == dim_str)
            if state is not None:
                state_str = state.value if hasattr(state, "value") else str(state)
                stmt = stmt.where(PersonalizationCalibrationModel.calibration_state == state_str)

            stmt = stmt.order_by(
                PersonalizationCalibrationModel.dimension.asc(),
                PersonalizationCalibrationModel.signal_value.asc(),
            )
            records = db.execute(stmt).scalars().all()
            return [PersonalizationCalibrationSchema.model_validate(r) for r in records]
        except OperationalError as exc:
            logger.warning(f"Could not query personalization_calibrations table: {exc}")
            return []

    @classmethod
    def get_calibration_by_signal_id(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        signal_id: uuid.UUID,
    ) -> PersonalizationCalibrationDetailResponse | None:
        """
        Retrieve a single calibration with linked granular attribution events.
        """
        try:
            calib = db.execute(
                select(PersonalizationCalibrationModel).where(
                    PersonalizationCalibrationModel.profile_id == profile_id,
                    PersonalizationCalibrationModel.signal_id == signal_id,
                )
            ).scalar_one_or_none()

            if not calib:
                # Also check by calibration model ID directly
                calib = db.execute(
                    select(PersonalizationCalibrationModel).where(
                        PersonalizationCalibrationModel.profile_id == profile_id,
                        PersonalizationCalibrationModel.id == signal_id,
                    )
                ).scalar_one_or_none()

            if not calib:
                return None

            # Fetch recent attributions for this signal
            attrs = db.execute(
                select(RecommendationFeedbackAttributionModel)
                .where(
                    RecommendationFeedbackAttributionModel.profile_id == profile_id,
                    RecommendationFeedbackAttributionModel.dimension == calib.dimension,
                    RecommendationFeedbackAttributionModel.signal_value == calib.signal_value,
                )
                .order_by(RecommendationFeedbackAttributionModel.interaction_timestamp.desc())
                .limit(50)
            ).scalars().all()

            calib_schema = PersonalizationCalibrationSchema.model_validate(calib)
            attr_schemas = [
                RecommendationFeedbackAttributionSchema.model_validate(a) for a in attrs
            ]

            return PersonalizationCalibrationDetailResponse(
                calibration=calib_schema,
                attributions=attr_schemas,
                total_attributions=len(attr_schemas),
            )
        except OperationalError as exc:
            logger.warning(f"Error querying calibration detail: {exc}")
            return None

    @classmethod
    def recompute_calibrations(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        reference_time: datetime | None = None,
        config: PersonalizationCalibrationConfig = DEFAULT_CALIBRATION_CONFIG,
    ) -> list[PersonalizationCalibrationSchema]:
        """
        Recompute all personalization calibration records and attribution events for a researcher.
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # 1. Fetch all recommendation items for this researcher
        rec_items = db.execute(
            select(ResearcherRecommendationItemModel)
            .join(ResearcherRecommendationSnapshotModel)
            .where(ResearcherRecommendationSnapshotModel.researcher_id == profile_id)
            .order_by(ResearcherRecommendationItemModel.created_at.asc())
        ).scalars().all()

        # 2. Fetch all interaction events for this researcher
        interactions = db.execute(
            select(ResearcherInteractionModel)
            .where(ResearcherInteractionModel.profile_id == profile_id)
            .order_by(ResearcherInteractionModel.created_at.asc())
        ).scalars().all()

        # 3. Fetch active adaptive signals for this researcher
        signals = AdaptivePreferenceSignalService.get_adaptive_signals(db, profile_id)

        # 4. Gather all distinct opportunity IDs needed (zero N+1)
        needed_opp_ids = {r.opportunity_id for r in rec_items} | {i.opportunity_id for i in interactions}
        opportunities_map: dict[uuid.UUID, OpportunityModel] = {}
        if needed_opp_ids:
            opps = db.execute(
                select(OpportunityModel)
                .options(selectinload(OpportunityModel.topic_associations))
                .where(OpportunityModel.id.in_(needed_opp_ids))
            ).scalars().all()
            opportunities_map = {o.id: o for o in opps}

        # 5. Compute attributions
        attributions = PersonalizationCalibrationEngine.attribute_interactions_to_recommendations(
            profile_id=profile_id,
            recommendation_items=rec_items,
            interactions=interactions,
            opportunities=opportunities_map,
            signals=signals,
            reference_time=ref_time,
            config=config,
        )

        # 6. Compute calibrations
        calibrations = PersonalizationCalibrationEngine.calculate_signal_calibrations(
            profile_id=profile_id,
            attributions=attributions,
            signals=signals,
            reference_time=ref_time,
            config=config,
        )

        # 7. Persist to database
        try:
            existing_calibs = db.execute(
                select(PersonalizationCalibrationModel).where(
                    PersonalizationCalibrationModel.profile_id == profile_id
                )
            ).scalars().all()
            existing_by_key = {(c.dimension, c.signal_value): c for c in existing_calibs}
            new_keys = set()

            for calib in calibrations:
                key = (calib.dimension, calib.signal_value)
                new_keys.add(key)
                state_val = calib.calibration_state.value if hasattr(calib.calibration_state, "value") else str(calib.calibration_state)

                if key in existing_by_key:
                    model = existing_by_key[key]
                    model.signal_id = calib.signal_id
                    model.recommendations_influenced_count = calib.recommendations_influenced_count
                    model.positive_outcome_count = calib.positive_outcome_count
                    model.negative_outcome_count = calib.negative_outcome_count
                    model.neutral_outcome_count = calib.neutral_outcome_count
                    model.accumulated_positive_weight = calib.accumulated_positive_weight
                    model.accumulated_negative_weight = calib.accumulated_negative_weight
                    model.net_calibration_modifier = calib.net_calibration_modifier
                    model.calibration_confidence = calib.calibration_confidence
                    model.calibration_state = state_val
                    model.algorithm_version = calib.algorithm_version
                    model.deterministic_explanation = calib.deterministic_explanation
                    model.latest_feedback_timestamp = calib.latest_feedback_timestamp
                    model.updated_at = calib.updated_at
                else:
                    new_model = PersonalizationCalibrationModel(
                        id=calib.id,
                        profile_id=calib.profile_id,
                        signal_id=calib.signal_id,
                        dimension=calib.dimension,
                        signal_value=calib.signal_value,
                        recommendations_influenced_count=calib.recommendations_influenced_count,
                        positive_outcome_count=calib.positive_outcome_count,
                        negative_outcome_count=calib.negative_outcome_count,
                        neutral_outcome_count=calib.neutral_outcome_count,
                        accumulated_positive_weight=calib.accumulated_positive_weight,
                        accumulated_negative_weight=calib.accumulated_negative_weight,
                        net_calibration_modifier=calib.net_calibration_modifier,
                        calibration_confidence=calib.calibration_confidence,
                        calibration_state=state_val,
                        algorithm_version=calib.algorithm_version,
                        deterministic_explanation=calib.deterministic_explanation,
                        latest_feedback_timestamp=calib.latest_feedback_timestamp,
                        created_at=calib.created_at,
                        updated_at=calib.updated_at,
                    )
                    db.add(new_model)

            # Remove stale calibrations
            for key, old_model in existing_by_key.items():
                if key not in new_keys:
                    db.delete(old_model)

            # Delete old attributions for idempotency and insert fresh
            db.query(RecommendationFeedbackAttributionModel).filter(
                RecommendationFeedbackAttributionModel.profile_id == profile_id
            ).delete(synchronize_session=False)

            for attr in attributions:
                attr_model = RecommendationFeedbackAttributionModel(
                    id=attr.id,
                    profile_id=attr.profile_id,
                    opportunity_id=attr.opportunity_id,
                    interaction_id=attr.interaction_id,
                    dimension=attr.dimension,
                    signal_value=attr.signal_value,
                    personalization_contribution=attr.personalization_contribution,
                    interaction_type=attr.interaction_type,
                    outcome_type=attr.outcome_type.value if hasattr(attr.outcome_type, "value") else str(attr.outcome_type),
                    attribution_confidence=attr.attribution_confidence.value if hasattr(attr.attribution_confidence, "value") else str(attr.attribution_confidence),
                    attribution_weight=attr.attribution_weight,
                    decay_adjusted_weight=attr.decay_adjusted_weight,
                    recommendation_timestamp=attr.recommendation_timestamp,
                    interaction_timestamp=attr.interaction_timestamp,
                    algorithm_version=attr.algorithm_version,
                    created_at=attr.created_at,
                )
                db.add(attr_model)

            db.flush()
        except OperationalError as exc:
            logger.warning(f"Could not persist calibrations or attributions: {exc}")

        return calibrations

    @classmethod
    def get_calibration_response(
        cls,
        db: Session,
        profile_id: uuid.UUID,
        dimension: str | None = None,
        state: CalibrationState | None = None,
    ) -> PersonalizationCalibrationResponse:
        """
        Get aggregated response with summary statistics for a researcher.
        """
        calibrations = cls.get_calibrations(db, profile_id, dimension=dimension, state=state)

        state_counts: dict[str, int] = {}
        total_conf = 0.0
        calibrated_count = 0

        for c in calibrations:
            state_val = c.calibration_state.value if hasattr(c.calibration_state, "value") else str(c.calibration_state)
            state_counts[state_val] = state_counts.get(state_val, 0) + 1
            total_conf += c.calibration_confidence
            if c.net_calibration_modifier != 0.0:
                calibrated_count += 1

        avg_conf = round(total_conf / len(calibrations), 4) if calibrations else 0.0

        return PersonalizationCalibrationResponse(
            profile_id=profile_id,
            items=calibrations,
            total_count=len(calibrations),
            state_counts=state_counts,
            average_confidence=avg_conf,
            calibrated_signals_count=calibrated_count,
        )
