"""
Deterministic Adaptive Signal Engine for Phase 5.5 — Adaptive Preference Signal Aggregation & Personalization Bridge.

Guarantees:
  - 100% deterministic: pure functions, identical inputs + reference time produce identical outputs.
  - Zero LLM calls.
  - Zero network calls.
  - Bounded outputs: signal strength in [-1.0, 1.0], confidence in [0.0, 1.0].
  - Additive contribution strictly clamped to [-MAX_ADAPTIVE_CONTRIBUTION, +MAX_ADAPTIVE_CONTRIBUTION].
  - Sparse evidence protection: single events strictly yield INSUFFICIENT_EVIDENCE.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence
import uuid

from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptiveSignalDimension,
)
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.researcher_interaction import (
    NEGATIVE_EXPLICIT_TYPES,
    POSITIVE_EXPLICIT_TYPES,
    InteractionType,
    ResearcherInteractionModel,
)
from app.personalization.adaptive_config import (
    DEFAULT_ADAPTIVE_CONFIG,
    AdaptiveSignalConfig,
)
from app.personalization.adaptive_models import (
    AdaptivePersonalizationContribution,
    AdaptivePreferenceSignal,
)


class AdaptiveSignalEngine:
    """
    Stateless calculation engine for aggregating researcher interactions into adaptive preference signals.
    """

    @classmethod
    def aggregate_interactions(
        cls,
        profile_id: uuid.UUID,
        interactions: Sequence[ResearcherInteractionModel],
        opportunities: Mapping[uuid.UUID, OpportunityModel] | None = None,
        reference_time: datetime | None = None,
        config: AdaptiveSignalConfig = DEFAULT_ADAPTIVE_CONFIG,
    ) -> list[AdaptivePreferenceSignal]:
        """
        Aggregate a researcher's historical interactions into structured adaptive signals across all dimensions.
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # Accumulator: (dimension, signal_value) -> metrics dict
        accum: dict[tuple[AdaptiveSignalDimension, str], dict[str, Any]] = {}

        for interaction in interactions:
            opp = None
            if opportunities is not None:
                opp = opportunities.get(interaction.opportunity_id)
            if opp is None and hasattr(interaction, "opportunity") and interaction.opportunity is not None:
                opp = interaction.opportunity
            if not opp:
                continue


            event_time = interaction.created_at
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            age_seconds = max(0.0, (ref_time - event_time).total_seconds())
            age_days = age_seconds / 86400.0

            # Discard events older than the maximum horizon
            if age_days > config.max_horizon_days:
                continue

            decay = config.calculate_decay(age_days)
            base_weight = config.get_interaction_weight(interaction.interaction_type)
            effective_weight = base_weight * decay

            # Determine whether positive or negative
            is_positive = base_weight > 0
            is_negative = base_weight < 0

            # Extract opportunity attributes for all dimensions
            extracted_attributes = cls._extract_opportunity_attributes(opp)

            for dim, val in extracted_attributes:
                key = (dim, val)
                if key not in accum:
                    accum[key] = {
                        "pos_count": 0,
                        "neg_count": 0,
                        "pos_weight": 0.0,
                        "neg_weight": 0.0,
                        "latest_timestamp": event_time,
                    }

                entry = accum[key]
                if is_positive:
                    entry["pos_count"] += 1
                    entry["pos_weight"] += effective_weight
                elif is_negative:
                    entry["neg_count"] += 1
                    entry["neg_weight"] += abs(effective_weight)

                if event_time > entry["latest_timestamp"]:
                    entry["latest_timestamp"] = event_time

        # Convert accumulated stats into AdaptivePreferenceSignal domain models
        signals: list[AdaptivePreferenceSignal] = []
        now_utc = datetime.now(timezone.utc)

        for (dim, val), data in sorted(accum.items(), key=lambda x: (x[0][0].value, x[0][1])):
            pos_c = data["pos_count"]
            neg_c = data["neg_count"]
            tot_c = pos_c + neg_c

            pos_w = data["pos_weight"]
            neg_w = data["neg_weight"]

            # Net signal strength in [-1.0, 1.0] with Laplace smoothing
            strength = (pos_w - neg_w) / (pos_w + neg_w + config.strength_smoothing_epsilon)
            strength = round(max(-1.0, min(1.0, strength)), 4)

            # Volume scale factor: 1.0 - exp(-N / kappa)
            vol_scale = 1.0 - math.exp(-tot_c / config.volume_scale_kappa)

            # Consistency factor: 1.0 - min(W_pos, W_neg) / (max(W_pos, W_neg) + eps)
            max_w = max(pos_w, neg_w)
            min_w = min(pos_w, neg_w)
            consistency = 1.0 - (min_w / (max_w + config.consistency_epsilon))
            consistency = max(0.0, min(1.0, consistency))

            confidence = round(max(0.0, min(1.0, vol_scale * consistency)), 4)

            # Classify evidence state
            if tot_c < config.insufficient_min_count or confidence < config.insufficient_min_confidence:
                state = AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE
            elif tot_c >= config.strong_min_count and confidence >= config.strong_min_confidence:
                state = AdaptiveEvidenceState.STRONG
            elif tot_c >= config.established_min_count and confidence >= config.established_min_confidence:
                state = AdaptiveEvidenceState.ESTABLISHED
            else:
                state = AdaptiveEvidenceState.EMERGING

            explanation = cls._generate_explanation(
                dimension=dim,
                signal_value=val,
                state=state,
                pos_count=pos_c,
                neg_count=neg_c,
                strength=strength,
                confidence=confidence,
            )

            # Deterministic signal UUID based on profile, dimension, and value
            signal_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{profile_id}:{dim.value}:{val}")

            signals.append(
                AdaptivePreferenceSignal(
                    id=signal_id,
                    profile_id=profile_id,
                    dimension=dim,
                    signal_value=val,
                    positive_evidence_count=pos_c,
                    negative_evidence_count=neg_c,
                    total_evidence_count=tot_c,
                    decay_adjusted_positive_weight=round(pos_w, 4),
                    decay_adjusted_negative_weight=round(neg_w, 4),
                    weighted_signal_strength=strength,
                    confidence=confidence,
                    evidence_state=state,
                    evidence_window_days=config.max_horizon_days,
                    latest_evidence_timestamp=data["latest_timestamp"],
                    algorithm_version=config.algorithm_version,
                    deterministic_explanation=explanation,
                    created_at=now_utc,
                    updated_at=now_utc,
                )
            )

        return signals

    @classmethod
    def evaluate_opportunity_adaptive_contribution(
        cls,
        signals: Sequence[AdaptivePreferenceSignal],
        opportunity: OpportunityModel,
        config: AdaptiveSignalConfig = DEFAULT_ADAPTIVE_CONFIG,
    ) -> tuple[float, list[AdaptivePersonalizationContribution]]:
        """
        Evaluate the additive adaptive personalization contribution for an opportunity.

        Returns
        -------
        tuple[float, list[AdaptivePersonalizationContribution]]
            Bounded additive contribution in [-max_adaptive_contribution, +max_adaptive_contribution]
            and list of dimension contributions.
        """
        if not signals:
            return 0.0, []

        # Index active signals by (dimension, signal_value)
        # Only consider EMERGING, ESTABLISHED, STRONG signals (INSUFFICIENT_EVIDENCE contributes 0.0)
        signal_map: dict[tuple[AdaptiveSignalDimension, str], AdaptivePreferenceSignal] = {
            (s.dimension, s.signal_value): s
            for s in signals
            if s.evidence_state != AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE
        }

        if not signal_map:
            return 0.0, []

        attributes = cls._extract_opportunity_attributes(opportunity)
        contributions: list[AdaptivePersonalizationContribution] = []
        raw_total = 0.0

        for dim, val in attributes:
            sig = signal_map.get((dim, val))
            if not sig:
                continue

            dim_weight = config.dimension_weights.get(dim, 0.10)

            # Emerging signals receive 50% dampening; Established/Strong receive full
            state_multiplier = 0.50 if sig.evidence_state == AdaptiveEvidenceState.EMERGING else 1.0

            raw_contrib = sig.weighted_signal_strength * sig.confidence * dim_weight * state_multiplier
            raw_contrib = round(raw_contrib, 6)
            raw_total += raw_contrib

            contributions.append(
                AdaptivePersonalizationContribution(
                    dimension=dim,
                    signal_value=val,
                    signal_strength=sig.weighted_signal_strength,
                    confidence=sig.confidence,
                    evidence_state=sig.evidence_state,
                    weight=dim_weight,
                    raw_contribution=raw_contrib,
                    bounded_contribution=round(
                        max(-config.max_adaptive_contribution, min(config.max_adaptive_contribution, raw_contrib)),
                        4,
                    ),
                    explanation=sig.deterministic_explanation,
                )
            )

        # Clamped overall adaptive contribution
        bounded_total = max(
            -config.max_adaptive_contribution,
            min(config.max_adaptive_contribution, raw_total),
        )
        return round(bounded_total, 4), contributions

    @classmethod
    def _extract_opportunity_attributes(cls, opp: OpportunityModel) -> list[tuple[AdaptiveSignalDimension, str]]:
        """Extract canonical attributes from OpportunityModel across all supported dimensions."""
        attrs: list[tuple[AdaptiveSignalDimension, str]] = []

        # 1. OPPORTUNITY_TYPE
        if opp.opportunity_type:
            attrs.append((AdaptiveSignalDimension.OPPORTUNITY_TYPE, opp.opportunity_type.strip()))

        # 2. DELIVERY_MODE
        if opp.delivery_mode:
            attrs.append((AdaptiveSignalDimension.DELIVERY_MODE, opp.delivery_mode.strip()))

        # 3. LOCATION
        if opp.location:
            attrs.append((AdaptiveSignalDimension.LOCATION, opp.location.strip()))

        # 4. PUBLISHER / ORGANIZER
        if opp.publisher:
            attrs.append((AdaptiveSignalDimension.PUBLISHER, opp.publisher.strip()))
        elif opp.organizer:
            attrs.append((AdaptiveSignalDimension.PUBLISHER, opp.organizer.strip()))

        # 5. RESEARCH_TOPIC (from topic associations)
        if hasattr(opp, "topic_associations") and opp.topic_associations:
            for ta in opp.topic_associations:
                if hasattr(ta, "topic") and ta.topic and hasattr(ta.topic, "name") and ta.topic.name:
                    attrs.append((AdaptiveSignalDimension.RESEARCH_TOPIC, ta.topic.name.strip()))
                elif hasattr(ta, "topic_id") and ta.topic_id:
                    attrs.append((AdaptiveSignalDimension.RESEARCH_TOPIC, str(ta.topic_id)))

        return attrs

    @classmethod
    def _generate_explanation(
        cls,
        dimension: AdaptiveSignalDimension,
        signal_value: str,
        state: AdaptiveEvidenceState,
        pos_count: int,
        neg_count: int,
        strength: float,
        confidence: float,
    ) -> str:
        """Generate human-readable deterministic explanation for an adaptive signal."""
        dim_name = dimension.value.replace("_", " ").lower()

        if state == AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE:
            return (
                f"Insufficient interaction evidence to establish an adaptive preference for "
                f"{dim_name} '{signal_value}' ({pos_count + neg_count} interaction(s))."
            )

        state_desc = state.value.lower()

        # Conflicting signal check
        if pos_count > 0 and neg_count > 0 and abs(strength) < 0.20:
            return (
                f"Interaction history contains mixed positive ({pos_count}) and negative ({neg_count}) "
                f"feedback for {dim_name} '{signal_value}'; no strong adaptive preference established."
            )

        if strength >= 0:
            return (
                f"Adaptive signal: {state_desc} positive affinity for {dim_name} '{signal_value}'. "
                f"Based on {pos_count} positive interaction(s) vs {neg_count} negative interaction(s) "
                f"(net strength: {strength:+.2f}, confidence: {confidence:.0%})."
            )
        else:
            return (
                f"Adaptive signal: {state_desc} negative aversion for {dim_name} '{signal_value}'. "
                f"Based on {neg_count} negative interaction(s) vs {pos_count} positive interaction(s) "
                f"(net strength: {strength:+.2f}, confidence: {confidence:.0%})."
            )
