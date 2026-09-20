"""
Deterministic Personalization Governance, Drift Detection & Adaptation Safety Engine (Phase 5.8).

Guarantees:
  - 100% deterministic: identical inputs + reference_time produce identical outputs.
  - Zero ML / Zero LLM / Zero vector DB / Zero network calls.
  - Read-only evaluation: raw interactions, explicit preferences, and ranking are never mutated.
  - Explicit preferences remain authoritative: behavioral drift NEVER overrides explicit PREFERRED or EXCLUDED.
  - Safe suspension: suspended personalization sets modifiers to neutral 0.0 (never negative).
  - Hysteresis protected: prevents rapid flapping between ALLOW and SUSPEND.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Sequence
import uuid

from app.models.personalization_governance import (
    AdaptationState,
    DriftType,
    EvidenceStrength,
    GovernanceEventType,
    GovernanceGateState,
    PersonalizationHealthState,
    PreferenceAlignmentState,
    SignalFreshnessState,
)
from app.models.personalization_quality import (
    ContextualFallbackLevel,
    QualityEvaluationState,
)
from app.models.researcher_interaction import (
    InteractionType,
    ResearcherInteractionModel,
)
from app.models.researcher_preference import (
    ResearcherPreferenceModel,
)
from app.personalization.adaptive_models import (
    AdaptivePreferenceSignal,
)
from app.personalization.governance_config import (
    DEFAULT_GOVERNANCE_CONFIG,
    PersonalizationGovernanceConfig,
)
from app.schemas.personalization_calibration import (
    PersonalizationCalibrationSchema,
)
from app.schemas.personalization_governance import (
    PersonalizationDriftEvaluationSchema,
    PersonalizationGovernanceEventSchema,
    SignalDriftItem,
)
from app.schemas.personalization_quality import (
    PersonalizationContextualAdaptationSchema,
    PersonalizationQualityEvaluationSchema,
)
from app.schemas.researcher_preference import (
    PreferenceType,
    ResearcherPreferenceItemSchema,
)


# Interaction weight mapping (consistent with Phase 5.6 / 5.5)
INTERACTION_WEIGHTS: dict[str, float] = {
    InteractionType.APPLIED.value: 1.0,
    InteractionType.INTERESTED.value: 0.8,
    InteractionType.SAVED.value: 0.6,
    InteractionType.SHARED.value: 0.3,
    InteractionType.OPENED.value: 0.1,
    InteractionType.VIEWED.value: 0.05,
    InteractionType.NOT_INTERESTED.value: -0.7,
    InteractionType.DISMISSED.value: -0.5,
    InteractionType.HIDDEN.value: -0.9,
}


class PersonalizationGovernanceEngine:
    """
    Deterministic governance, drift detection, and adaptation safety engine.
    Supports both class-method execution and configured instance usage.
    """

    def __init__(self, config: PersonalizationGovernanceConfig = DEFAULT_GOVERNANCE_CONFIG):
        self.config = config

    def partition_temporal_interactions(
        self,
        interactions: Sequence[ResearcherInteractionModel],
        reference_time: datetime | None = None,
    ) -> tuple[list[ResearcherInteractionModel], list[ResearcherInteractionModel]]:
        return self._partition_temporal_interactions_static(interactions, reference_time, self.config)

    @classmethod
    def _partition_temporal_interactions_static(
        cls,
        interactions: Sequence[ResearcherInteractionModel],
        reference_time: datetime | None = None,
        config: PersonalizationGovernanceConfig = DEFAULT_GOVERNANCE_CONFIG,
    ) -> tuple[list[ResearcherInteractionModel], list[ResearcherInteractionModel]]:
        now = reference_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        all_interactions = list(interactions or [])
        hist_start = now - timedelta(days=config.default_historical_window_days)
        recent_start = now - timedelta(days=config.default_recent_window_days)

        historical = [
            i for i in all_interactions
            if hist_start <= (i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)) < recent_start
        ]
        recent = [
            i for i in all_interactions
            if recent_start <= (i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)) <= now
        ]
        return historical, recent

    def evaluate_signal_drift(
        self,
        dimension: str,
        signal_value: str,
        current_strength: float = 0.0,
        historical_interactions: Sequence[Any] | None = None,
        recent_interactions: Sequence[Any] | None = None,
        last_evidence_time: datetime | None = None,
        reference_time: datetime | None = None,
    ) -> SignalDriftItem:
        return self._evaluate_signal_drift_static(
            dimension=dimension,
            signal_value=signal_value,
            current_strength=current_strength,
            historical_interactions=historical_interactions,
            recent_interactions=recent_interactions,
            last_evidence_time=last_evidence_time,
            reference_time=reference_time,
            config=self.config,
        )

    @classmethod
    def _evaluate_signal_drift_static(
        cls,
        dimension: str,
        signal_value: str,
        current_strength: float = 0.0,
        historical_interactions: Sequence[Any] | None = None,
        recent_interactions: Sequence[Any] | None = None,
        last_evidence_time: datetime | None = None,
        reference_time: datetime | None = None,
        config: PersonalizationGovernanceConfig = DEFAULT_GOVERNANCE_CONFIG,
    ) -> SignalDriftItem:
        now = reference_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        h_list = list(historical_interactions or [])
        r_list = list(recent_interactions or [])

        h_str, h_cnt = cls._extract_strength(h_list, default_strength=current_strength)
        r_str, r_cnt = cls._extract_strength(r_list, default_strength=current_strength)

        diff = round(r_str - h_str, 4)

        # Staleness check (Invariant 2: Stale evidence is not negative evidence)
        is_stale = False
        if last_evidence_time is not None:
            let = last_evidence_time if last_evidence_time.tzinfo else last_evidence_time.replace(tzinfo=timezone.utc)
            age_days = (now - let).total_seconds() / 86400.0
            if age_days > config.stale_evidence_days:
                is_stale = True

        # Evidence strength
        total_cnt = h_cnt + r_cnt
        if total_cnt < config.min_interactions_for_evaluation or r_cnt < config.min_recent_interactions_for_drift:
            ev_str = EvidenceStrength.INSUFFICIENT
        elif r_cnt < config.medium_evidence_interactions:
            ev_str = EvidenceStrength.LOW
        elif r_cnt < config.high_evidence_interactions:
            ev_str = EvidenceStrength.MEDIUM
        else:
            ev_str = EvidenceStrength.HIGH

        # Drift classification (Invariant 3 & 6: Missing evidence/noise cannot trigger drift)
        is_reversing = (
            current_strength != h_str
            and abs(current_strength - h_str) >= config.drift_difference_threshold
            and abs(r_str - h_str) < abs(current_strength - h_str)
            and abs(r_str - current_strength) >= config.reversing_drift_threshold
        )

        if ev_str == EvidenceStrength.INSUFFICIENT:
            d_type = DriftType.UNKNOWN
        elif is_reversing:
            d_type = DriftType.REVERSING
        elif abs(diff) < config.drift_difference_threshold:
            d_type = DriftType.STABLE
        else:
            if ev_str == EvidenceStrength.LOW:
                d_type = DriftType.EMERGING
            else:
                d_type = DriftType.PERSISTENT

        explanation = cls._generate_signal_drift_explanation(
            dimension=dimension,
            signal_value=signal_value,
            h_str=h_str,
            r_str=r_str,
            diff=diff,
            drift_type=d_type,
            evidence_strength=ev_str,
            is_stale=is_stale,
        )

        return SignalDriftItem(
            dimension=dimension,
            signal_value=signal_value,
            historical_strength=h_str,
            recent_strength=r_str,
            difference=diff,
            evidence_strength=ev_str,
            drift_type=d_type,
            is_stale=is_stale,
            last_evidence_timestamp=last_evidence_time,
            explanation=explanation,
        )

    @staticmethod
    def _parse_governance_state(
        state: GovernanceGateState | str | None,
    ) -> GovernanceGateState | None:
        """Safely coerces a gate state enum, string representation, or empty/None value to GovernanceGateState | None."""
        if isinstance(state, GovernanceGateState):
            return state
        if isinstance(state, str) and state.strip():
            try:
                return GovernanceGateState(state.strip())
            except ValueError:
                return None
        return None

    def evaluate_governance_gate(
        self,
        drifting_count: int,
        persistent_drift_count: int,
        stale_count: int,
        quality_stability: str,
        context_stability: str,
        evidence_sufficiency: EvidenceStrength,
        preference_alignment: PreferenceAlignmentState,
        current_gate_state: GovernanceGateState | str | None,
        recent_evidence_count: int = 10,
    ) -> tuple[GovernanceGateState, AdaptationState, str]:
        prev = self._parse_governance_state(current_gate_state)
        return self._determine_governance_state(
            overall_health=PersonalizationHealthState.HEALTHY,
            quality_stability=quality_stability,
            pref_alignment=preference_alignment,
            drifting_count=drifting_count,
            recent_count=recent_evidence_count,
            prev_state=prev,
            config=self.config,
            persistent_drift_count=persistent_drift_count,
        )

    @classmethod
    def evaluate_governance(
        cls,
        profile_id: uuid.UUID,
        explicit_preferences: Sequence[ResearcherPreferenceItemSchema | ResearcherPreferenceModel] | None = None,
        interactions: Sequence[ResearcherInteractionModel] | None = None,
        adaptive_signals: Sequence[AdaptivePreferenceSignal] | None = None,
        calibrations: Sequence[PersonalizationCalibrationSchema] | None = None,
        quality_evaluation: PersonalizationQualityEvaluationSchema | None = None,
        contextual_adaptations: Sequence[PersonalizationContextualAdaptationSchema] | None = None,
        previous_governance_state: GovernanceGateState | str | None = None,
        reference_time: datetime | None = None,
        config: PersonalizationGovernanceConfig = DEFAULT_GOVERNANCE_CONFIG,
    ) -> tuple[PersonalizationDriftEvaluationSchema, list[PersonalizationGovernanceEventSchema]]:
        """
        Execute deterministic drift detection, personalization health evaluation,
        and governance gate state assignment.
        """
        now = reference_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        all_interactions = list(interactions or [])
        explicit_prefs = list(explicit_preferences or [])
        prev_state = cls._parse_governance_state(previous_governance_state)

        # 1. Temporal Window Partitioning
        hist_start = now - timedelta(days=config.default_historical_window_days)
        recent_start = now - timedelta(days=config.default_recent_window_days)

        historical_interactions = [
            i for i in all_interactions
            if hist_start <= (i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)) < recent_start
        ]
        recent_interactions = [
            i for i in all_interactions
            if recent_start <= (i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)) <= now
        ]

        # 2. Extract Signal Universe
        # We monitor signals present in adaptive_signals, calibrations, or derived from interactions
        signal_keys: set[tuple[str, str]] = set()
        if adaptive_signals:
            for s in adaptive_signals:
                dim = s.dimension.value if hasattr(s.dimension, "value") else str(s.dimension)
                signal_keys.add((dim, s.signal_value))

        if calibrations:
            for c in calibrations:
                signal_keys.add((c.dimension, c.signal_value))

        # Also extract any signals present in explicit preferences
        for p in explicit_prefs:
            p_cat = p.category.value if hasattr(p.category, "value") else p.category
            p_val = getattr(p, "preference_value", None) or getattr(p, "preference_key", "")
            if p_val:
                signal_keys.add((p_cat, str(p_val)))

        # 3. Aggregate Behavioral Strengths per Window
        hist_strengths, hist_counts, _ = cls._aggregate_window_signals(historical_interactions)
        recent_strengths, recent_counts, last_seen_map = cls._aggregate_window_signals(recent_interactions)

        # Also check last seen across all interactions
        for i in all_interactions:
            dim_vals = cls._extract_interaction_dimensions(i)
            i_time = i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)
            for dim, val in dim_vals:
                signal_keys.add((dim, val))
                if (dim, val) not in last_seen_map or i_time > last_seen_map[(dim, val)]:
                    last_seen_map[(dim, val)] = i_time

        # 4. Evaluate Granular Signal Drift & Staleness
        drift_items: list[SignalDriftItem] = []
        drifting_count = 0
        stale_count = 0

        for dim, val in sorted(signal_keys):
            h_str = hist_strengths.get((dim, val), 0.0)
            r_str = recent_strengths.get((dim, val), 0.0)
            r_cnt = recent_counts.get((dim, val), 0)
            last_ts = last_seen_map.get((dim, val))

            diff = round(r_str - h_str, 4)

            # Staleness check (Invariant 2: Stale evidence is not negative evidence)
            is_stale = False
            if last_ts is not None:
                age_days = (now - last_ts).total_seconds() / 86400.0
                if age_days > config.stale_evidence_days:
                    is_stale = True
                    stale_count += 1
            elif (dim, val) in signal_keys and not all_interactions:
                is_stale = True
                stale_count += 1

            # Evidence strength
            if r_cnt < config.min_recent_interactions_for_drift:
                ev_str = EvidenceStrength.INSUFFICIENT
            elif r_cnt < config.medium_evidence_interactions:
                ev_str = EvidenceStrength.LOW
            elif r_cnt < config.high_evidence_interactions:
                ev_str = EvidenceStrength.MEDIUM
            else:
                ev_str = EvidenceStrength.HIGH

            # Drift classification (Invariant 3 & 6: Missing evidence/noise cannot trigger drift)
            if ev_str == EvidenceStrength.INSUFFICIENT:
                d_type = DriftType.UNKNOWN
            elif abs(diff) < config.drift_difference_threshold:
                d_type = DriftType.STABLE
            else:
                if ev_str == EvidenceStrength.LOW:
                    d_type = DriftType.EMERGING
                    drifting_count += 1
                else:
                    # Check if reversing: recent shift is moving back toward neutral/historical baseline
                    if (h_str > 0 and diff < 0 and r_str >= 0) or (h_str < 0 and diff > 0 and r_str <= 0):
                        d_type = DriftType.REVERSING
                    else:
                        d_type = DriftType.PERSISTENT
                    drifting_count += 1

            explanation = cls._generate_signal_drift_explanation(
                dimension=dim,
                signal_value=val,
                h_str=h_str,
                r_str=r_str,
                diff=diff,
                drift_type=d_type,
                evidence_strength=ev_str,
                is_stale=is_stale,
            )

            drift_items.append(
                SignalDriftItem(
                    dimension=dim,
                    signal_value=val,
                    historical_strength=h_str,
                    recent_strength=r_str,
                    difference=diff,
                    evidence_strength=ev_str,
                    drift_type=d_type,
                    is_stale=is_stale,
                    last_evidence_timestamp=last_ts,
                    explanation=explanation,
                )
            )

        # 5. Evaluate Preference vs Behavioral Alignment (Invariant 1, 21, 22)
        pref_alignment = cls._evaluate_preference_alignment(
            explicit_prefs=explicit_prefs,
            recent_strengths=recent_strengths,
            recent_counts=recent_counts,
        )

        # 6. Multi-Dimensional Personalization Health Evaluation
        freshness_state = cls._evaluate_signal_freshness(
            all_interactions=all_interactions,
            stale_count=stale_count,
            total_signals=len(signal_keys),
            now=now,
        )

        total_recent_cnt = len(recent_interactions)
        if total_recent_cnt < config.min_interactions_for_evaluation:
            evidence_sufficiency = EvidenceStrength.INSUFFICIENT
        elif total_recent_cnt < config.medium_evidence_interactions:
            evidence_sufficiency = EvidenceStrength.LOW
        elif total_recent_cnt < config.high_evidence_interactions:
            evidence_sufficiency = EvidenceStrength.MEDIUM
        else:
            evidence_sufficiency = EvidenceStrength.HIGH

        quality_stability = "INSUFFICIENT_DATA"
        if quality_evaluation:
            q_state = quality_evaluation.evaluation_state
            q_state_str = q_state.value if hasattr(q_state, "value") else str(q_state)
            if q_state_str in ("POSITIVE", "STABLE"):
                quality_stability = "STABLE"
            elif q_state_str in ("NEGATIVE", "MIXED"):
                quality_stability = "DEGRADED"
            else:
                quality_stability = "INSUFFICIENT_DATA"

        context_stability = "INSUFFICIENT_DATA"
        if contextual_adaptations:
            c_mods = [a.contextual_modifier for a in contextual_adaptations]
            if c_mods:
                pos_cnt = sum(1 for m in c_mods if m > 0.005)
                neg_cnt = sum(1 for m in c_mods if m < -0.005)
                if neg_cnt == 0:
                    context_stability = "STABLE"
                elif pos_cnt > 0 and neg_cnt > 0:
                    context_stability = "MIXED"
                else:
                    context_stability = "DEGRADED"

        diversity_stability = "INSUFFICIENT_DATA"
        if quality_evaluation:
            d_score = quality_evaluation.diversity_score
            if d_score >= 0.60:
                diversity_stability = "HIGH"
            elif d_score >= 0.30:
                diversity_stability = "ACCEPTABLE"
            else:
                diversity_stability = "LOW"

        # Overall Health State
        if len(all_interactions) < config.min_interactions_for_evaluation:
            overall_health = PersonalizationHealthState.INSUFFICIENT_DATA
        elif quality_stability == "DEGRADED" and pref_alignment == PreferenceAlignmentState.CONFLICTED:
            overall_health = PersonalizationHealthState.DEGRADED
        elif drifting_count > 0:
            overall_health = PersonalizationHealthState.DRIFTING
        elif freshness_state == SignalFreshnessState.HEALTHY and quality_stability != "DEGRADED":
            overall_health = PersonalizationHealthState.HEALTHY
        else:
            overall_health = PersonalizationHealthState.STABLE

        # 7. Governance Gate Determination with Hysteresis & Recovery (Invariants 4, 5, 8, 9, 10, 11, 12)
        persistent_drift_count = sum(1 for d in drift_items if d.drift_type == DriftType.PERSISTENT)
        gov_state, adapt_state, gov_reason = cls._determine_governance_state(
            overall_health=overall_health,
            quality_stability=quality_stability,
            pref_alignment=pref_alignment,
            drifting_count=drifting_count,
            recent_count=total_recent_cnt,
            prev_state=prev_state,
            config=config,
            persistent_drift_count=persistent_drift_count,
        )

        health_summary = cls._generate_health_summary(
            overall_health=overall_health,
            freshness_state=freshness_state,
            evidence_sufficiency=evidence_sufficiency,
            quality_stability=quality_stability,
            drifting_count=drifting_count,
            stale_count=stale_count,
        )

        eval_schema = PersonalizationDriftEvaluationSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            evaluation_timestamp=now,
            historical_window_days=config.default_historical_window_days,
            recent_window_days=config.default_recent_window_days,
            overall_health_state=overall_health,
            governance_state=gov_state,
            adaptation_state=adapt_state,
            signal_freshness=freshness_state,
            evidence_sufficiency=evidence_sufficiency,
            quality_stability=quality_stability,
            context_stability=context_stability,
            preference_alignment=pref_alignment,
            recommendation_diversity=diversity_stability,
            drifting_signals_count=drifting_count,
            stale_signals_count=stale_count,
            active_signals_count=len(drift_items),
            drift_details=drift_items,
            health_summary=health_summary,
            governance_explanation=gov_reason,
            algorithm_version=config.algorithm_version,
            created_at=now,
            updated_at=now,
        )

        # 8. Check for Governance State Transition Audit Event (Invariant 7, 18, 39)
        events: list[PersonalizationGovernanceEventSchema] = []
        if prev_state != gov_state:
            event_type = GovernanceEventType.GATE_TRANSITION
            if gov_state == GovernanceGateState.SUSPEND:
                event_type = GovernanceEventType.ADAPTATION_SUSPENSION
            elif prev_state == GovernanceGateState.SUSPEND and gov_state in (
                GovernanceGateState.ALLOW,
                GovernanceGateState.ALLOW_BOUNDED,
            ):
                event_type = GovernanceEventType.ADAPTATION_RECOVERY

            events.append(
                PersonalizationGovernanceEventSchema(
                    id=uuid.uuid4(),
                    profile_id=profile_id,
                    event_type=event_type,
                    previous_state=prev_state.value if prev_state else None,
                    new_state=gov_state.value,
                    reason=gov_reason,
                    affected_dimension=None,
                    affected_signal_value=None,
                    evidence_count=total_recent_cnt,
                    reference_time=now,
                    algorithm_version=config.algorithm_version,
                    created_at=now,
                )
            )

        return eval_schema, events

    @classmethod
    def _aggregate_window_signals(
        cls,
        interactions: list[ResearcherInteractionModel],
    ) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], int], dict[tuple[str, str], datetime]]:
        """
        Computes normalized behavioral strength [-1.0, 1.0], interaction count,
        and last seen timestamp for each signal dimension and value.
        """
        signal_weights: dict[tuple[str, str], list[float]] = {}
        last_seen: dict[tuple[str, str], datetime] = {}

        for i in interactions:
            dim_vals = cls._extract_interaction_dimensions(i)
            i_type = i.interaction_type.value if hasattr(i.interaction_type, "value") else i.interaction_type
            w = INTERACTION_WEIGHTS.get(i_type, 0.0)
            i_time = i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)

            for dim, val in dim_vals:
                key = (dim, val)
                if key not in signal_weights:
                    signal_weights[key] = []
                signal_weights[key].append(w)
                if key not in last_seen or i_time > last_seen[key]:
                    last_seen[key] = i_time

        strengths: dict[tuple[str, str], float] = {}
        counts: dict[tuple[str, str], int] = {}

        for key, weights in signal_weights.items():
            counts[key] = len(weights)
            # Bounded normalized average weight
            avg_w = sum(weights) / len(weights)
            strengths[key] = round(max(-1.0, min(1.0, avg_w)), 4)

        return strengths, counts, last_seen

    @classmethod
    def _extract_strength(cls, interactions: Sequence[Any], default_strength: float = 0.0) -> tuple[float, int]:
        """Extracts normalized behavioral strength [-1.0, 1.0] and count from a list of interactions or dicts."""
        if not interactions:
            return default_strength, 0
        weights: list[float] = []
        for item in interactions:
            if isinstance(item, dict):
                w = item.get("weight", 1.0)
                if item.get("is_positive") is False:
                    w = -abs(w)
                elif item.get("is_positive") is True:
                    w = abs(w)
                weights.append(float(w))
            elif hasattr(item, "interaction_type"):
                i_type = item.interaction_type.value if hasattr(item.interaction_type, "value") else str(item.interaction_type)
                weights.append(INTERACTION_WEIGHTS.get(i_type, 0.0))
            elif isinstance(item, (int, float)):
                weights.append(float(item))
        if not weights:
            return default_strength, 0
        avg_w = sum(weights) / len(weights)
        return round(max(-1.0, min(1.0, avg_w)), 4), len(weights)

    @classmethod
    def _extract_interaction_dimensions(
        cls,
        interaction: ResearcherInteractionModel,
    ) -> list[tuple[str, str]]:
        """Extracts dimension-value pairs associated with an interaction."""
        results: list[tuple[str, str]] = []
        opp = getattr(interaction, "opportunity", None)

        if opp:
            if getattr(opp, "opportunity_type", None):
                results.append(("OPPORTUNITY_TYPE", str(opp.opportunity_type)))
            if getattr(opp, "delivery_mode", None):
                results.append(("DELIVERY_MODE", str(opp.delivery_mode)))

        # Also inspect interaction metadata if present
        meta = getattr(interaction, "interaction_metadata", None)
        if isinstance(meta, dict):
            for k, v in meta.items():
                if k in ("dimension", "signal_dimension") and "signal_value" in meta:
                    results.append((str(v), str(meta["signal_value"])))

        return results

    @classmethod
    def _evaluate_preference_alignment(
        cls,
        explicit_prefs: list[ResearcherPreferenceItemSchema | ResearcherPreferenceModel],
        recent_strengths: dict[tuple[str, str], float],
        recent_counts: dict[tuple[str, str], int],
    ) -> PreferenceAlignmentState:
        """
        Determines alignment between explicit researcher preferences and recent behavior.
        Invariant 1: Explicit preferences are authoritative and never overridden.
        """
        has_conflict = False
        has_divergence = False
        has_alignment = False

        for p in explicit_prefs:
            cat = p.category.value if hasattr(p.category, "value") else p.category
            val = getattr(p, "preference_value", None) or getattr(p, "preference_key", "")
            p_type = p.preference_type.value if hasattr(p.preference_type, "value") else p.preference_type
            key = (cat, str(val))

            r_str = recent_strengths.get(key)
            r_cnt = recent_counts.get(key, 0)

            if r_str is not None and r_cnt >= 2:
                if p_type == PreferenceType.PREFERRED.value:
                    if r_str < -0.30:
                        has_divergence = True
                    elif r_str > 0.20:
                        has_alignment = True
                elif p_type == PreferenceType.EXCLUDED.value:
                    if r_str > 0.30:
                        has_conflict = True

        if has_conflict:
            return PreferenceAlignmentState.CONFLICTED
        if has_divergence:
            return PreferenceAlignmentState.DIVERGING
        if has_alignment:
            return PreferenceAlignmentState.ALIGNED
        return PreferenceAlignmentState.NEUTRAL

    @classmethod
    def _evaluate_signal_freshness(
        cls,
        all_interactions: list[ResearcherInteractionModel],
        stale_count: int,
        total_signals: int,
        now: datetime,
    ) -> SignalFreshnessState:
        """Evaluates overall freshness of behavioral interaction evidence."""
        if not all_interactions:
            return SignalFreshnessState.INSUFFICIENT_DATA

        latest_time = max(
            i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)
            for i in all_interactions
        )
        age_days = (now - latest_time).total_seconds() / 86400.0

        if age_days <= 14.0:
            return SignalFreshnessState.HEALTHY
        if age_days <= 60.0:
            return SignalFreshnessState.STABLE
        return SignalFreshnessState.STALE

    @classmethod
    def _determine_governance_state(
        cls,
        overall_health: PersonalizationHealthState,
        quality_stability: str,
        pref_alignment: PreferenceAlignmentState,
        drifting_count: int,
        recent_count: int,
        prev_state: GovernanceGateState | None,
        config: PersonalizationGovernanceConfig,
        persistent_drift_count: int = 0,
    ) -> tuple[GovernanceGateState, AdaptationState, str]:
        """
        Determines governance decision gate with hysteresis and recovery rules.
        """
        # Invariant 4: One interaction cannot trigger suspension
        # Invariant 8 & 11: Recovery requires sufficient stable evidence
        if prev_state == GovernanceGateState.SUSPEND:
            if (
                recent_count >= config.recovery_evidence_threshold
                and quality_stability != "DEGRADED"
                and pref_alignment not in (
                    PreferenceAlignmentState.CONFLICTED,
                    PreferenceAlignmentState.DIVERGENT,
                    PreferenceAlignmentState.DIVERGING,
                )
            ):
                return (
                    GovernanceGateState.ALLOW_BOUNDED,
                    AdaptationState.BOUNDED,
                    "Personalization recovery: new behavioral evidence has stabilized sufficiently (N >= 5). "
                    "Personalization is recovered into conservative bounded adaptation.",
                )
            else:
                return (
                    GovernanceGateState.SUSPEND,
                    AdaptationState.SUSPENDED,
                    "Personalization remains suspended. Recovery requires additional stable interaction evidence "
                    f"(observed {recent_count}/{config.recovery_evidence_threshold} required).",
                )

        # Standard state transitions
        if recent_count < config.min_interactions_for_evaluation:
            return (
                GovernanceGateState.HOLD,
                AdaptationState.BOUNDED,
                "Insufficient recent behavioral evidence (N < 3). "
                "Personalization adaptation is held at current baseline without modification.",
            )

        if quality_stability == "DEGRADED" and (
            pref_alignment in (
                PreferenceAlignmentState.CONFLICTED,
                PreferenceAlignmentState.DIVERGENT,
                PreferenceAlignmentState.DIVERGING,
            )
            or persistent_drift_count >= 2
        ):
            # Severe degradation and conflict -> Suspend
            return (
                GovernanceGateState.SUSPEND,
                AdaptationState.SUSPENDED,
                "Personalization adaptation is suspended due to severe recommendation quality "
                "degradation and conflicting preference evidence.",
            )

        if quality_stability == "DEGRADED":
            return (
                GovernanceGateState.REDUCE,
                AdaptationState.DAMPENED,
                "Recommendation quality metrics indicate negative feedback tendencies. "
                "Personalization adaptation modifiers are reduced to preserve core relevance.",
            )

        if persistent_drift_count > 0:
            return (
                GovernanceGateState.HOLD,
                AdaptationState.CONSERVATIVE,
                f"Detected {persistent_drift_count} behavioral signal(s) with persistent drift. "
                "Personalization adaptation is held in conservative mode pending stabilization.",
            )

        if drifting_count > 0:
            return (
                GovernanceGateState.ALLOW_BOUNDED,
                AdaptationState.BOUNDED,
                f"Detected {drifting_count} behavioral signals with emerging or persistent drift. "
                "Adaptation is permitted under conservative bounded limits (50% multiplier).",
            )

        return (
            GovernanceGateState.ALLOW,
            AdaptationState.ACTIVE,
            "Personalization signals are stable and aligned with explicit preferences. "
            "Full bounded adaptation is active.",
        )

    @classmethod
    def _generate_signal_drift_explanation(
        cls,
        dimension: str,
        signal_value: str,
        h_str: float,
        r_str: float,
        diff: float,
        drift_type: DriftType,
        evidence_strength: EvidenceStrength,
        is_stale: bool,
    ) -> str:
        """Generates deterministic, non-speculative natural language explanation per signal."""
        dim_clean = dimension.replace("_", " ").title()
        if is_stale:
            return (
                f"{dim_clean} '{signal_value}' evidence is older than 180 days (stale). "
                f"Historical affinity ({h_str:+.2f}) is preserved without assuming adverse intent."
            )

        if drift_type == DriftType.UNKNOWN:
            return (
                f"{dim_clean} '{signal_value}' has insufficient recent evidence to assess drift."
            )

        if drift_type == DriftType.STABLE:
            return (
                f"{dim_clean} '{signal_value}' is stable across historical ({h_str:+.2f}) "
                f"and recent ({r_str:+.2f}) observation windows (diff: {diff:+.2f})."
            )

        if drift_type == DriftType.EMERGING:
            return (
                f"{dim_clean} '{signal_value}' exhibits an emerging behavioral shift "
                f"from {h_str:+.2f} to {r_str:+.2f} (diff: {diff:+.2f}, evidence: {evidence_strength.value})."
            )

        if drift_type == DriftType.PERSISTENT:
            return (
                f"{dim_clean} '{signal_value}' exhibits persistent behavioral drift "
                f"from {h_str:+.2f} to {r_str:+.2f} (diff: {diff:+.2f}, evidence: {evidence_strength.value})."
            )

        if drift_type == DriftType.REVERSING:
            return (
                f"{dim_clean} '{signal_value}' shows reversing drift back toward baseline "
                f"(historical: {h_str:+.2f}, recent: {r_str:+.2f}, diff: {diff:+.2f})."
            )

        return f"{dim_clean} '{signal_value}' evaluated with drift type {drift_type.value}."

    @classmethod
    def _generate_health_summary(
        cls,
        overall_health: PersonalizationHealthState,
        freshness_state: SignalFreshnessState,
        evidence_sufficiency: EvidenceStrength,
        quality_stability: str,
        drifting_count: int,
        stale_count: int,
    ) -> str:
        """Generates deterministic natural language summary of personalization health."""
        parts = [f"Personalization health is {overall_health.value}."]
        if freshness_state == SignalFreshnessState.STALE:
            parts.append(f"Behavioral evidence includes {stale_count} stale signal(s).")
        if drifting_count > 0:
            parts.append(f"Detected {drifting_count} drifting signal(s) undergoing conservative adaptation.")
        if quality_stability == "DEGRADED":
            parts.append("Recommendation quality metrics show elevated negative feedback.")
        elif quality_stability == "STABLE":
            parts.append("Recommendation quality and engagement remain stable.")
        return " ".join(parts)
