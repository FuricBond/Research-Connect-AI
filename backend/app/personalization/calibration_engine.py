"""
Deterministic Personalization Calibration Engine for Phase 5.6.

Guarantees:
  - 100% deterministic: pure functions, identical inputs + reference time produce identical outputs.
  - Zero LLM calls.
  - Zero network calls.
  - Bounded outputs: calibration modifier strictly clamped to [-0.05, +0.05].
  - Anti-feedback-loop protection: capped outcomes per opportunity per signal.
  - Sparse evidence protection: N < 3 strictly yields INSUFFICIENT_DATA with 0.0 modifier.
  - Conflicting feedback preserves both positive and negative evidence and dampens modifier.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence
import uuid

from app.models.adaptive_signal import AdaptivePreferenceSignalModel
from app.models.opportunity import OpportunityModel
from app.models.personalization_calibration import (
    AttributionConfidence,
    CalibrationState,
    FeedbackOutcomeType,
)
from app.models.recommendation_history import ResearcherRecommendationItemModel
from app.models.researcher_interaction import ResearcherInteractionModel
from app.personalization.adaptive_engine import AdaptiveSignalEngine
from app.personalization.adaptive_models import AdaptivePreferenceSignal
from app.personalization.calibration_config import (
    DEFAULT_CALIBRATION_CONFIG,
    PersonalizationCalibrationConfig,
)
from app.schemas.personalization_calibration import (
    PersonalizationCalibrationSchema,
    RecommendationFeedbackAttributionSchema,
)


class PersonalizationCalibrationEngine:
    """
    Stateless calculation engine for attributing researcher feedback to recommendations
    and computing bounded personalization calibration modifiers.
    """

    @classmethod
    def attribute_interactions_to_recommendations(
        cls,
        profile_id: uuid.UUID,
        recommendation_items: Sequence[ResearcherRecommendationItemModel],
        interactions: Sequence[ResearcherInteractionModel],
        opportunities: Mapping[uuid.UUID, OpportunityModel],
        signals: Sequence[AdaptivePreferenceSignal | AdaptivePreferenceSignalModel],
        reference_time: datetime | None = None,
        config: PersonalizationCalibrationConfig = DEFAULT_CALIBRATION_CONFIG,
    ) -> list[RecommendationFeedbackAttributionSchema]:
        """
        Attribute subsequent researcher interactions to prior recommendation exposures.

        Enforces:
          - Temporal attribution window (default 14 days).
          - Non-retroactive causality: interaction must occur after recommendation.
          - Multi-signal attribution across opportunity attributes matching active signals.
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # Index active signals by (dimension_str, signal_value)
        signal_map: dict[tuple[str, str], float] = {}
        for s in signals:
            dim_str = s.dimension.value if hasattr(s.dimension, "value") else str(s.dimension)
            val_str = s.signal_value
            # Store signal strength or default weight
            signal_map[(dim_str, val_str)] = float(getattr(s, "weighted_signal_strength", 0.0))

        # Index recommendation items by opportunity_id, sorted by created_at ascending
        rec_by_opp: dict[uuid.UUID, list[ResearcherRecommendationItemModel]] = {}
        for item in recommendation_items:
            rec_by_opp.setdefault(item.opportunity_id, []).append(item)

        attributions: list[RecommendationFeedbackAttributionSchema] = []

        for interaction in interactions:
            opp = opportunities.get(interaction.opportunity_id)
            if not opp:
                continue

            rec_candidates = rec_by_opp.get(interaction.opportunity_id, [])
            if not rec_candidates:
                continue

            inter_time = interaction.created_at
            if inter_time.tzinfo is None:
                inter_time = inter_time.replace(tzinfo=timezone.utc)

            # Find the most recent recommendation exposure that occurred BEFORE this interaction
            eligible_recs = [
                r for r in rec_candidates
                if (r.created_at.replace(tzinfo=timezone.utc) if r.created_at.tzinfo is None else r.created_at) <= inter_time
            ]
            if not eligible_recs:
                continue

            # Pick the latest recommendation exposure prior to interaction
            latest_rec = max(
                eligible_recs,
                key=lambda r: (r.created_at.replace(tzinfo=timezone.utc) if r.created_at.tzinfo is None else r.created_at),
            )
            rec_time = latest_rec.created_at
            if rec_time.tzinfo is None:
                rec_time = rec_time.replace(tzinfo=timezone.utc)

            # Check direct session/snapshot link
            is_direct = False
            if interaction.metadata_payload:
                meta_snap_id = interaction.metadata_payload.get("snapshot_id")
                if meta_snap_id and str(latest_rec.snapshot_id) == str(meta_snap_id):
                    is_direct = True

            conf_tier, conf_mult = config.get_attribution_confidence(
                recommendation_time=rec_time.timestamp(),
                interaction_time=inter_time.timestamp(),
                is_direct_session_link=is_direct,
            )

            # If unattributed (e.g. outside 14-day attribution window), skip
            if conf_tier == AttributionConfidence.UNATTRIBUTED or conf_mult <= 0.0:
                continue

            outcome_type = config.outcome_classification.get(
                interaction.interaction_type,
                FeedbackOutcomeType.NEUTRAL,
            )
            base_weight = config.interaction_weights.get(interaction.interaction_type, 0.0)

            age_days = max(0.0, (ref_time - inter_time).total_seconds() / 86400.0)
            decay = config.calculate_decay(age_days)

            decay_adjusted_weight = round(base_weight * conf_mult * decay, 6)

            # Extract opportunity attributes for active signals
            attributes = AdaptiveSignalEngine._extract_opportunity_attributes(opp)

            for dim, val in attributes:
                dim_str = dim.value if hasattr(dim, "value") else str(dim)
                key = (dim_str, val)
                if key in signal_map:
                    contrib = round(signal_map[key], 4)
                    attr_id = uuid.uuid5(
                        uuid.NAMESPACE_DNS,
                        f"{profile_id}:{interaction.id}:{dim_str}:{val}",
                    )
                    attributions.append(
                        RecommendationFeedbackAttributionSchema(
                            id=attr_id,
                            profile_id=profile_id,
                            opportunity_id=opp.id,
                            interaction_id=interaction.id,
                            dimension=dim_str,
                            signal_value=val,
                            personalization_contribution=contrib,
                            interaction_type=interaction.interaction_type,
                            outcome_type=outcome_type,
                            attribution_confidence=conf_tier,
                            attribution_weight=conf_mult,
                            decay_adjusted_weight=decay_adjusted_weight,
                            recommendation_timestamp=rec_time,
                            interaction_timestamp=inter_time,
                            algorithm_version=config.algorithm_version,
                            created_at=ref_time,
                        )
                    )

        return attributions

    @classmethod
    def calculate_signal_calibrations(
        cls,
        profile_id: uuid.UUID,
        attributions: Sequence[RecommendationFeedbackAttributionSchema],
        signals: Sequence[AdaptivePreferenceSignal | AdaptivePreferenceSignalModel],
        all_recommendations_count_by_signal: Mapping[tuple[str, str], int] | None = None,
        reference_time: datetime | None = None,
        config: PersonalizationCalibrationConfig = DEFAULT_CALIBRATION_CONFIG,
    ) -> list[PersonalizationCalibrationSchema]:
        """
        Aggregate attributions per personalization signal, applying anti-feedback-loop safeguards,
        calculating confidence, evidence state, and bounded calibration modifier [-0.05, +0.05].
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # 1. Anti-Feedback-Loop Safeguard: Cap outcomes per opportunity per signal
        # Map: (dimension, signal_value, opportunity_id) -> list of attributions
        opp_signal_attrs: dict[tuple[str, str, uuid.UUID], list[RecommendationFeedbackAttributionSchema]] = {}
        for attr in attributions:
            key = (attr.dimension, attr.signal_value, attr.opportunity_id)
            opp_signal_attrs.setdefault(key, []).append(attr)

        filtered_attributions: list[RecommendationFeedbackAttributionSchema] = []
        for key, attrs in opp_signal_attrs.items():
            # Pick highest absolute weight outcome to avoid repeated view/open spamming
            best_attr = max(attrs, key=lambda a: abs(a.decay_adjusted_weight))
            filtered_attributions.append(best_attr)

        # 2. Group by (dimension, signal_value)
        signal_data: dict[tuple[str, str], dict[str, Any]] = {}
        for s in signals:
            dim_str = s.dimension.value if hasattr(s.dimension, "value") else str(s.dimension)
            val_str = s.signal_value
            signal_id = getattr(s, "id", None)
            signal_data[(dim_str, val_str)] = {
                "signal_id": signal_id,
                "pos_count": 0,
                "neg_count": 0,
                "neutral_count": 0,
                "pos_weight": 0.0,
                "neg_weight": 0.0,
                "latest_feedback_time": None,
                "distinct_opportunities": set(),
            }

        for attr in filtered_attributions:
            key = (attr.dimension, attr.signal_value)
            if key not in signal_data:
                signal_data[key] = {
                    "signal_id": None,
                    "pos_count": 0,
                    "neg_count": 0,
                    "neutral_count": 0,
                    "pos_weight": 0.0,
                    "neg_weight": 0.0,
                    "latest_feedback_time": None,
                    "distinct_opportunities": set(),
                }

            entry = signal_data[key]
            entry["distinct_opportunities"].add(attr.opportunity_id)

            if attr.decay_adjusted_weight > 0:
                entry["pos_count"] += 1
                entry["pos_weight"] += attr.decay_adjusted_weight
            elif attr.decay_adjusted_weight < 0:
                entry["neg_count"] += 1
                entry["neg_weight"] += abs(attr.decay_adjusted_weight)
            else:
                entry["neutral_count"] += 1

            if entry["latest_feedback_time"] is None or attr.interaction_timestamp > entry["latest_feedback_time"]:
                entry["latest_feedback_time"] = attr.interaction_timestamp

        calibrations: list[PersonalizationCalibrationSchema] = []

        for (dim, val), data in sorted(signal_data.items(), key=lambda x: (x[0][0], x[0][1])):
            pos_c = data["pos_count"]
            neg_c = data["neg_count"]
            neu_c = data["neutral_count"]
            tot_c = pos_c + neg_c

            pos_w = data["pos_weight"]
            neg_w = data["neg_weight"]

            # Number of recommendations influenced
            recs_influenced = len(data["distinct_opportunities"])
            if all_recommendations_count_by_signal and (dim, val) in all_recommendations_count_by_signal:
                recs_influenced = max(recs_influenced, all_recommendations_count_by_signal[(dim, val)])

            # Evaluate agreement / conflict
            max_w = max(pos_w, neg_w)
            min_w = min(pos_w, neg_w)
            conflict_ratio = min_w / (max_w + config.consistency_epsilon)
            is_conflicted = (min_w > 0.5) and (conflict_ratio >= config.conflict_ratio_threshold)

            # Volume scale factor: 1.0 - exp(-N / kappa)
            vol_scale = 1.0 - math.exp(-tot_c / config.volume_scale_kappa)
            consistency = max(0.0, min(1.0, 1.0 - conflict_ratio))
            confidence = round(max(0.0, min(1.0, vol_scale * consistency)), 4)

            # Classify calibration state
            if tot_c < config.insufficient_min_count:
                state = CalibrationState.INSUFFICIENT_DATA
                state_multiplier = 0.0
            elif is_conflicted:
                state = CalibrationState.CONFLICTED
                state_multiplier = 0.25
            elif confidence < config.insufficient_min_confidence:
                state = CalibrationState.INSUFFICIENT_DATA
                state_multiplier = 0.0
            elif tot_c >= config.stable_min_count and confidence >= config.stable_min_confidence:
                state = CalibrationState.STABLE
                state_multiplier = 1.0
            elif tot_c >= config.calibrating_min_count:
                state = CalibrationState.CALIBRATING
                state_multiplier = 0.80
            else:
                state = CalibrationState.EARLY_SIGNAL
                state_multiplier = 0.50

            # Calculate net modifier
            if state == CalibrationState.INSUFFICIENT_DATA or tot_c == 0:
                modifier = 0.0
            else:
                raw_ratio = (pos_w - neg_w) / (pos_w + neg_w + config.consistency_epsilon)
                # Bounded by max modifier and scaled by confidence and state multiplier
                if raw_ratio > 0:
                    modifier = raw_ratio * config.max_positive_modifier * confidence * state_multiplier
                else:
                    modifier = raw_ratio * abs(config.max_negative_modifier) * confidence * state_multiplier

                modifier = max(config.max_negative_modifier, min(config.max_positive_modifier, modifier))
                modifier = round(modifier, 4)

            explanation = cls._generate_explanation(
                dimension=dim,
                signal_value=val,
                state=state,
                pos_count=pos_c,
                neg_count=neg_c,
                recs_influenced=recs_influenced,
                modifier=modifier,
                confidence=confidence,
            )

            calib_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{profile_id}:{dim}:{val}:calib")

            calibrations.append(
                PersonalizationCalibrationSchema(
                    id=calib_id,
                    profile_id=profile_id,
                    signal_id=data["signal_id"],
                    dimension=dim,
                    signal_value=val,
                    recommendations_influenced_count=recs_influenced,
                    positive_outcome_count=pos_c,
                    negative_outcome_count=neg_c,
                    neutral_outcome_count=neu_c,
                    accumulated_positive_weight=round(pos_w, 4),
                    accumulated_negative_weight=round(neg_w, 4),
                    net_calibration_modifier=modifier,
                    calibration_confidence=confidence,
                    calibration_state=state,
                    algorithm_version=config.algorithm_version,
                    deterministic_explanation=explanation,
                    latest_feedback_timestamp=data["latest_feedback_time"],
                    created_at=ref_time,
                    updated_at=ref_time,
                )
            )

        return calibrations

    @classmethod
    def _generate_explanation(
        cls,
        dimension: str,
        signal_value: str,
        state: CalibrationState,
        pos_count: int,
        neg_count: int,
        recs_influenced: int,
        modifier: float,
        confidence: float,
    ) -> str:
        """Generate deterministic natural language description of calibration status."""
        dim_label = dimension.replace("_", " ").lower()

        if state == CalibrationState.INSUFFICIENT_DATA:
            return (
                f"Insufficient interaction evidence to calibrate {dim_label} '{signal_value}'. "
                f"Observed {pos_count} positive and {neg_count} negative interactions (minimum {3} required)."
            )

        if state == CalibrationState.CONFLICTED:
            return (
                f"Feedback for {dim_label} '{signal_value}' is mixed ({pos_count} positive vs {neg_count} negative "
                f"across {recs_influenced} recommendations). Calibration modifier is dampened to {modifier:+.3f}."
            )

        if modifier > 0:
            return (
                f"Adaptive personalization for {dim_label} '{signal_value}' was reinforced ({modifier:+.3f}) by "
                f"{pos_count} positive interactions across {recs_influenced} attributed recommendations (confidence: {int(confidence * 100)}%)."
            )
        elif modifier < 0:
            return (
                f"Adaptive personalization for {dim_label} '{signal_value}' was reduced ({modifier:+.3f}) due to "
                f"{neg_count} negative interactions across {recs_influenced} attributed recommendations (confidence: {int(confidence * 100)}%)."
            )
        else:
            return (
                f"Personalization calibration for {dim_label} '{signal_value}' is in {state.value} state with "
                f"balanced evidence. Net modifier is 0.000."
            )
