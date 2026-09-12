"""
Phase 3.6 — Feedback Learning & Aggregation Engine.

Pure, deterministic behavioral learning algorithms:
  - Temporal exponential decay with 30-day half-life
  - Diminishing returns saturation for repeated actions
  - Multi-dimensional behavioral confidence calculation
  - Metadata-grounded attribute learning (topics, types, modes, locations, venues)
  - Explicit preference protection & dominance floor
  - Negative signal opportunity suppression set

Strict Architectural Boundaries:
  - 100% Deterministic: Zero random numbers, zero ML/black-box models.
  - Explainable: All weights, decay factors, and confidence values are inspectable.
  - Inviolable Explicit Preferences: Explicit declarations are NEVER overwritten or flipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Sequence
import uuid

from app.ranking.feedback_config import (
    CONFIDENCE_VOLUME_SCALE_N,
    DIMINISHING_RETURNS_GAMMA,
    EXPLICIT_PREFERENCE_DOMINANCE_FLOOR,
    FEEDBACK_EVENT_WEIGHTS,
    FEEDBACK_HALF_LIFE_DAYS,
    MAX_BEHAVIORAL_DAMPENING_OF_EXPLICIT,
    MAX_FEEDBACK_HORIZON_DAYS,
    MAX_NEGATIVE_BEHAVIORAL_ADJUSTMENT,
    MAX_OPPORTUNITY_CUMULATIVE_NEGATIVE_WEIGHT,
    MAX_OPPORTUNITY_CUMULATIVE_POSITIVE_WEIGHT,
    MAX_POSITIVE_BEHAVIORAL_ADJUSTMENT,
    MIN_BEHAVIORAL_CONFIDENCE_THRESHOLD,
    NEGATIVE_FEEDBACK_TYPES,
    POSITIVE_FEEDBACK_TYPES,
    SUPPRESSION_TTL_DAYS,
    TEMPORAL_DECAY_LAMBDA,
)
from app.schemas.researcher_feedback import BehavioralSignalSchema


# ── Mathematical Primitives ───────────────────────────────────────────────────


def calculate_temporal_decay(
    event_time: datetime,
    reference_time: datetime,
    half_life_days: float = FEEDBACK_HALF_LIFE_DAYS,
) -> float:
    """
    Calculate deterministic exponential decay for a historical feedback event.

    Formula:
      decay(t) = exp(-lambda * delta_t_days)
      where lambda = ln(2) / half_life_days

    Guarantees:
      - Returns 1.0 for contemporaneous events (delta_t <= 0).
      - Returns 0.50 at delta_t = half_life_days (30 days).
      - Returns 0.25 at delta_t = 2 * half_life_days (60 days).
      - Returns 0.0 for events beyond MAX_FEEDBACK_HORIZON_DAYS.
    """
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    delta_seconds = (reference_time - event_time).total_seconds()
    if delta_seconds <= 0.0:
        return 1.0

    delta_days = delta_seconds / 86400.0
    if delta_days > MAX_FEEDBACK_HORIZON_DAYS:
        return 0.0

    decay_lambda = math.log(2.0) / max(0.1, half_life_days)
    decay_factor = math.exp(-decay_lambda * delta_days)
    return max(0.0, min(1.0, round(decay_factor, 6)))


def calculate_diminishing_returns(
    base_weight: float,
    repetition_index: int,
    gamma: float = DIMINISHING_RETURNS_GAMMA,
) -> float:
    """
    Apply diminishing returns saturation to repeated feedback on the same entity or attribute.

    Formula:
      effective_weight(k) = base_weight / (1.0 + gamma * (k - 1))
      where k is the 1-indexed interaction count.

    Guarantees:
      - k = 1: effective_weight = base_weight (100%)
      - k = 2: effective_weight = base_weight / 1.5 (~66.7%)
      - k = 3: effective_weight = base_weight / 2.0 (50.0%)
      - k = 5: effective_weight = base_weight / 3.0 (~33.3%)
      - Sign is strictly preserved.
    """
    if repetition_index <= 1:
        return base_weight

    scale = 1.0 + gamma * (repetition_index - 1)
    return round(base_weight / scale, 6)


def calculate_behavioral_confidence(
    sample_size: int,
    signed_weight_sum: float,
    absolute_weight_sum: float,
    avg_recency: float,
    scale_n: float = CONFIDENCE_VOLUME_SCALE_N,
) -> float:
    """
    Calculate bounded confidence [0.0, 1.0] for a learned behavioral signal.

    Formula:
      confidence = volume_factor * consistency_factor * recency_factor
      where:
        volume_factor = 1.0 - exp(-sample_size / scale_n)
        consistency_factor = |signed_weight_sum| / absolute_weight_sum
        recency_factor = avg_recency in [0.0, 1.0]

    Guarantees:
      - sample_size = 0: confidence = 0.0
      - Single click (N=1, low weight, no consistency history): confidence < 0.25
      - Conflicting behavior (e.g. 2 saves, 2 dismisses): consistency_factor -> 0.0, confidence -> 0.0
      - High volume, unanimous, recent feedback: confidence -> ~0.95+
      - Strictly bounded in [0.0, 1.0].
    """
    if sample_size <= 0 or absolute_weight_sum <= 1e-6:
        return 0.0

    volume_factor = 1.0 - math.exp(-float(sample_size) / max(0.1, scale_n))
    consistency_factor = abs(signed_weight_sum) / max(1e-6, absolute_weight_sum)
    recency_factor = max(0.0, min(1.0, avg_recency))

    raw_conf = volume_factor * consistency_factor * recency_factor
    return max(0.0, min(1.0, round(raw_conf, 4)))


# ── Behavioral Profile Container ──────────────────────────────────────────────


@dataclass
class BehavioralProfile:
    """
    Aggregated behavioral profile synthesized from researcher feedback history.
    """

    researcher_id: uuid.UUID
    signals: list[BehavioralSignalSchema] = field(default_factory=list)
    suppressed_opportunity_ids: set[uuid.UUID] = field(default_factory=set)
    total_feedback_events: int = 0
    feedback_type_counts: dict[str, int] = field(default_factory=dict)
    top_positive_topics: list[str] = field(default_factory=list)
    top_negative_topics: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    is_cold_start: bool = True


# ── Behavioral Learning Engine ────────────────────────────────────────────────


class FeedbackEngine:
    """
    Deterministic Behavioral Aggregation & Learning Engine.
    """

    @classmethod
    def aggregate_feedback(
        cls,
        researcher_id: uuid.UUID,
        feedback_events: Sequence[Any],
        reference_time: datetime | None = None,
        explicit_preferences: Sequence[Any] | None = None,
    ) -> BehavioralProfile:
        """
        Synthesize raw feedback history into a structured behavioral profile.

        Parameters
        ----------
        researcher_id : uuid.UUID
            Canonical researcher profile ID.
        feedback_events : Sequence[Any]
            List of ResearcherRecommendationFeedbackModel records, eager-loaded with opportunities.
        reference_time : datetime | None
            Evaluation timestamp for decay calculations (defaults to current UTC).
        explicit_preferences : Sequence[Any] | None
            Active explicit preferences from Phase 3.3 for conflict resolution.

        Returns
        -------
        BehavioralProfile
            Deterministic behavioral signals, suppression set, and confidence metrics.
        """
        if reference_time is None:
            ref_time = datetime.now(timezone.utc)
        elif reference_time.tzinfo is None:
            ref_time = reference_time.replace(timezone.utc)
        else:
            ref_time = reference_time.astimezone(timezone.utc)

        if not feedback_events:
            return BehavioralProfile(
                researcher_id=researcher_id,
                is_cold_start=True,
            )

        # ── 1. Sort Events Chronologically ────────────────────────────────────
        # Consistent chronological order ensures deterministic diminishing returns
        sorted_events = sorted(
            feedback_events,
            key=lambda e: (
                e.created_at.replace(tzinfo=timezone.utc)
                if e.created_at and e.created_at.tzinfo is None
                else (e.created_at or ref_time),
                str(e.id),
            ),
        )

        counts_by_type: dict[str, int] = {}
        for e in sorted_events:
            f_type = getattr(e, "feedback_type", "").upper()
            counts_by_type[f_type] = counts_by_type.get(f_type, 0) + 1

        # ── 2. Opportunity-Level Suppression & De-duplication ───────────────────
        # An opportunity is suppressed if its latest negative feedback falls within SUPPRESSION_TTL_DAYS
        # and has not been superseded by a more recent positive feedback (e.g. SAVE/APPLY).
        opp_latest_event: dict[uuid.UUID, tuple[str, datetime]] = {}
        opp_event_counts: dict[tuple[uuid.UUID, str], int] = {}

        for e in sorted_events:
            opp_id = getattr(e, "opportunity_id", None)
            if not opp_id:
                continue

            f_type = getattr(e, "feedback_type", "").upper()
            e_time = e.created_at
            if e_time.tzinfo is None:
                e_time = e_time.replace(tzinfo=timezone.utc)

            key = (opp_id, f_type)
            opp_event_counts[key] = opp_event_counts.get(key, 0) + 1

            if opp_id not in opp_latest_event or e_time > opp_latest_event[opp_id][1]:
                opp_latest_event[opp_id] = (f_type, e_time)

        suppressed_ids: set[uuid.UUID] = set()
        for opp_id, (latest_type, latest_time) in opp_latest_event.items():
            if latest_type in NEGATIVE_FEEDBACK_TYPES:
                age_days = (ref_time - latest_time).total_seconds() / 86400.0
                if age_days <= SUPPRESSION_TTL_DAYS:
                    suppressed_ids.add(opp_id)

        # ── 3. Attribute-Level Feedback Tallying ───────────────────────────────
        # Map: (category, preference_key, canonical_value, display_label) -> list of decayed diminishing weights
        attribute_weights: dict[tuple[str, str, str, str], list[float]] = {}
        attribute_recencies: dict[tuple[str, str, str, str], list[float]] = {}
        attribute_latest_time: dict[tuple[str, str, str, str], datetime] = {}
        attribute_repetition_counts: dict[tuple[str, str, str, str], int] = {}

        for e in sorted_events:
            opp = getattr(e, "opportunity", None)
            if not opp:
                continue

            f_type = getattr(e, "feedback_type", "").upper()
            base_weight = FEEDBACK_EVENT_WEIGHTS.get(f_type, 0.0)
            if abs(base_weight) < 1e-6:
                continue

            e_time = e.created_at
            if e_time.tzinfo is None:
                e_time = e_time.replace(tzinfo=timezone.utc)

            decay = calculate_temporal_decay(e_time, ref_time)
            if decay <= 0.0:
                continue

            # Extract verified opportunity attributes (topics, type, mode, location, organizer)
            extracted_attributes: list[tuple[str, str, str, str]] = []

            # 1. Topics (from topic associations or joined topics)
            topics = []
            if hasattr(opp, "topic_associations") and opp.topic_associations:
                for ta in opp.topic_associations:
                    if hasattr(ta, "topic") and ta.topic and ta.topic.name:
                        topics.append((ta.topic.name, ta.topic.slug or ta.topic.name))
            elif hasattr(opp, "topics") and opp.topics:
                for t in opp.topics:
                    t_str = str(t).strip()
                    if t_str:
                        topics.append((t_str, t_str.lower().replace(" ", "-")))

            for t_name, t_slug in topics:
                extracted_attributes.append(
                    ("TOPIC", "topic", t_slug.lower(), t_name.strip().title())
                )

            # 2. Opportunity Type
            opp_type = (getattr(opp, "opportunity_type", None) or "").strip().upper()
            if opp_type:
                extracted_attributes.append(
                    ("OPPORTUNITY_TYPE", "opportunity_type", opp_type, opp_type.replace("_", " ").title())
                )

            # 3. Delivery Mode
            delivery_mode = (getattr(opp, "delivery_mode", None) or "").strip().upper()
            if delivery_mode:
                extracted_attributes.append(
                    ("DELIVERY_MODE", "delivery_mode", delivery_mode, delivery_mode.replace("_", " ").title())
                )

            # 4. Location
            location = (getattr(opp, "location", None) or "").strip()
            if len(location) >= 3:
                extracted_attributes.append(
                    ("LOCATION", "location", location.lower(), location.title())
                )

            # 5. Venue / Organizer
            organizer = (getattr(opp, "organizer", None) or getattr(opp, "publisher", None) or "").strip()
            if len(organizer) >= 3:
                extracted_attributes.append(
                    ("VENUE", "organizer", organizer.lower(), organizer.title())
                )

            # Accumulate decayed weights with diminishing returns
            for attr_key in extracted_attributes:
                rep = attribute_repetition_counts.get(attr_key, 0) + 1
                attribute_repetition_counts[attr_key] = rep

                effective_weight = calculate_diminishing_returns(base_weight, rep)
                decayed_weight = round(effective_weight * decay, 6)

                if attr_key not in attribute_weights:
                    attribute_weights[attr_key] = []
                    attribute_recencies[attr_key] = []
                    attribute_latest_time[attr_key] = e_time

                attribute_weights[attr_key].append(decayed_weight)
                attribute_recencies[attr_key].append(decay)
                if e_time > attribute_latest_time[attr_key]:
                    attribute_latest_time[attr_key] = e_time

        # ── 4. Map Explicit Preferences for Conflict Protection ───────────────
        # Map: (category, canonical_value) -> explicit preference object
        explicit_map: dict[tuple[str, str], Any] = {}
        if explicit_preferences:
            for p in explicit_preferences:
                if getattr(p, "is_active", True) and getattr(p, "source", "") == "EXPLICIT":
                    cat = (getattr(p, "category", "") or "").upper()
                    val = (getattr(p, "preference_value", "") or "").strip().lower()
                    explicit_map[(cat, val)] = p

        # ── 5. Synthesize Behavioral Signals ──────────────────────────────────
        behavioral_signals: list[BehavioralSignalSchema] = []
        positive_topic_scores: list[tuple[str, float]] = []
        negative_topic_scores: list[tuple[str, float]] = []

        for attr_key, weights in attribute_weights.items():
            cat, p_key, p_val, display_label = attr_key
            sample_size = len(weights)
            signed_sum = sum(weights)
            abs_sum = sum(abs(w) for w in weights)
            avg_recency = sum(attribute_recencies[attr_key]) / max(1, sample_size)

            confidence = calculate_behavioral_confidence(
                sample_size=sample_size,
                signed_weight_sum=signed_sum,
                absolute_weight_sum=abs_sum,
                avg_recency=avg_recency,
            )

            if confidence < MIN_BEHAVIORAL_CONFIDENCE_THRESHOLD:
                # Signal is too sparse, conflicting, or stale to be authoritative
                continue

            # Bounded normalized score in [-1.0, 1.0] using tanh saturation
            # signed_sum of 1.0 -> tanh(1.0) = 0.76; signed_sum of 2.0 -> tanh(2.0) = 0.96
            normalized_score = round(math.tanh(signed_sum), 4)

            # Conflict Handling with Explicit Preferences:
            # If explicit preference exists for this attribute, behavioral negative feedback
            # cannot flip or eradicate the explicit preference.
            explicit_key = (cat, p_val.lower())
            if explicit_key in explicit_map:
                if normalized_score < 0.0:
                    # Explicit preference protection: dampen behavioral negative impact
                    dampened_score = normalized_score * MAX_BEHAVIORAL_DAMPENING_OF_EXPLICIT
                    normalized_score = round(max(-EXPLICIT_PREFERENCE_DOMINANCE_FLOOR, dampened_score), 4)

            direction = "POSITIVE" if normalized_score >= 0.0 else "NEGATIVE"

            signal = BehavioralSignalSchema(
                category=cat,
                preference_key=p_key,
                preference_value=p_val,
                display_label=display_label,
                raw_score=round(signed_sum, 4),
                normalized_score=normalized_score,
                confidence=confidence,
                sample_size=sample_size,
                direction=direction,
                recency_score=round(avg_recency, 4),
                last_interacted_at=attribute_latest_time.get(attr_key),
            )
            behavioral_signals.append(signal)

            if cat == "TOPIC":
                if normalized_score > 0.0:
                    positive_topic_scores.append((display_label, normalized_score * confidence))
                elif normalized_score < 0.0:
                    negative_topic_scores.append((display_label, abs(normalized_score) * confidence))

        # Sort top positive and negative topics by effective weight
        positive_topic_scores.sort(key=lambda x: x[1], reverse=True)
        negative_topic_scores.sort(key=lambda x: x[1], reverse=True)

        top_pos = [t[0] for t in positive_topic_scores[:5]]
        top_neg = [t[0] for t in negative_topic_scores[:5]]

        # Overall behavioral confidence: average confidence of top signals
        overall_conf = (
            round(sum(s.confidence for s in behavioral_signals) / len(behavioral_signals), 4)
            if behavioral_signals
            else 0.0
        )

        return BehavioralProfile(
            researcher_id=researcher_id,
            signals=behavioral_signals,
            suppressed_opportunity_ids=suppressed_ids,
            total_feedback_events=len(sorted_events),
            feedback_type_counts=counts_by_type,
            top_positive_topics=top_pos,
            top_negative_topics=top_neg,
            overall_confidence=overall_conf,
            is_cold_start=len(behavioral_signals) == 0,
        )
