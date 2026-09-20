"""
Deterministic Personalization Scorer for Phase 5.3 — Personalization-Aware Opportunity Scoring & Explainability.

Consumes Phase 5.2 explicit preference interpretation signals and produces
bounded, explainable personalization scores with structured dimension breakdowns.

Guarantees:
  - 100% deterministic (identical inputs produce identical outputs)
  - Zero LLM calls
  - Zero network calls
  - Zero database queries during scoring
  - Zero mutations to Phase 4 recommendation ranking scores or formulas
  - Preserves 3-state semantics: Preferred != Neutral != Excluded
  - Missing data is safe: INSUFFICIENT_EVIDENCE contributes 0.0 (never negative)
  - All scores and dimension contributions are strictly bounded
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Sequence
import uuid

from app.models.opportunity import OpportunityModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.personalization.interpreter import PreferenceInterpreter
from app.personalization.models import (
    PersonalizationAssessment,
    PersonalizationContribution,
    PersonalizationDimensionScore,
    PersonalizationExplanation,
    PersonalizationScore,
    PersonalizationScoreBreakdown,
    PreferenceDimension,
    PreferenceMatchSignal,
    PreferenceMatchType,
    PreferencePersonalizationAssessment,
    SignalPolarity,
)
from app.personalization.adaptive_config import (
    DEFAULT_ADAPTIVE_CONFIG,
    AdaptiveSignalConfig,
)
from app.personalization.adaptive_engine import AdaptiveSignalEngine
from app.personalization.adaptive_models import (
    AdaptivePersonalizationContribution,
    AdaptivePreferenceSignal,
)
from app.personalization.scoring_config import (
    DEFAULT_SCORING_CONFIG,
    PersonalizationScoringConfig,
)
from app.schemas.personalization_calibration import PersonalizationCalibrationSchema
from app.schemas.researcher_preference import (
    ResearcherPreferenceItemSchema,
    StructuredPreferencesResponseSchema,
)

logger = logging.getLogger(__name__)


class PersonalizationScorer:
    """
    Deterministic scoring and explainability engine for researcher personalization.
    """

    @classmethod
    def score_opportunity(
        cls,
        profile_id: uuid.UUID,
        preferences: Sequence[ResearcherPreferenceItemSchema | ResearcherPreferenceModel] | StructuredPreferencesResponseSchema,
        opportunity: OpportunityModel,
        config: PersonalizationScoringConfig = DEFAULT_SCORING_CONFIG,
        preference_assessment: PreferencePersonalizationAssessment | None = None,
        adaptive_signals: Sequence[AdaptivePreferenceSignal] | None = None,
        adaptive_config: AdaptiveSignalConfig = DEFAULT_ADAPTIVE_CONFIG,
        calibrations: Sequence[PersonalizationCalibrationSchema] | None = None,
    ) -> PersonalizationAssessment:
        """
        Evaluate and score a single opportunity against researcher explicit preferences,
        bounded Phase 5.5 adaptive preference signals, and Phase 5.6 calibration modifiers.

        Parameters
        ----------
        profile_id : uuid.UUID
            Canonical ResearchProfileModel ID.
        preferences : Sequence of preferences or StructuredPreferencesResponseSchema
            Active preferences of the researcher.
        opportunity : OpportunityModel
            Opportunity to evaluate.
        config : PersonalizationScoringConfig
            Scoring weights and multipliers configuration.
        preference_assessment : PreferencePersonalizationAssessment, optional
            Pre-computed Phase 5.2 assessment (to avoid recomputation if already available).
        adaptive_signals : Sequence of AdaptivePreferenceSignal, optional
            Aggregated adaptive preference signals for the researcher.
        adaptive_config : AdaptiveSignalConfig, optional
            Adaptive signal scoring configuration.
        calibrations : Sequence of PersonalizationCalibrationSchema, optional
            Materialized personalization calibrations for the researcher.

        Returns
        -------
        PersonalizationAssessment
            Complete score, breakdown, explanations, adaptive contributions, calibration score, and underlying signals.
        """
        # 1. Obtain Phase 5.2 preference match assessment
        if preference_assessment is None:
            preference_assessment = PreferenceInterpreter.evaluate_opportunity(
                profile_id=profile_id,
                preferences=preferences,
                opportunity=opportunity,
            )

        # 2. Build dimension-level contributions and scores
        breakdown = cls._build_score_breakdown(
            assessment=preference_assessment,
            config=config,
        )

        # 3. Calculate bounded, normalized, and absolute scores
        score = cls._calculate_personalization_score(
            breakdown=breakdown,
            assessment=preference_assessment,
            config=config,
        )

        # 4. Phase 5.5 & 5.6 — Evaluate additive adaptive contribution and calibration modifier
        adaptive_score = 0.0
        calibration_score = 0.0
        adaptive_contributions: list[AdaptivePersonalizationContribution] = []

        if adaptive_signals:
            raw_adaptive_score, adaptive_contributions = AdaptiveSignalEngine.evaluate_opportunity_adaptive_contribution(
                signals=adaptive_signals,
                opportunity=opportunity,
                config=adaptive_config,
            )

            # Apply Phase 5.6 calibration modifiers if available
            if calibrations and adaptive_contributions:
                calib_map: dict[tuple[str, str], float] = {
                    (c.dimension, c.signal_value): c.net_calibration_modifier
                    for c in calibrations
                }
                total_calib = 0.0
                for contrib in adaptive_contributions:
                    dim_str = contrib.dimension.value if hasattr(contrib.dimension, "value") else str(contrib.dimension)
                    c_mod = calib_map.get((dim_str, contrib.signal_value), 0.0)
                    contrib.calibration_modifier = round(c_mod, 4)
                    contrib.bounded_contribution = round(contrib.bounded_contribution + c_mod, 4)
                    total_calib += c_mod

                calibration_score = round(total_calib, 4)
                raw_adaptive_score = raw_adaptive_score + calibration_score

            # Invariant 13 & 1: Explicit preferences remain authoritative.
            # If explicit exclusion is present, adaptive signals CANNOT revive the score from 0.0.
            if (
                preference_assessment.overall_match_state == PreferenceMatchType.EXCLUDED_MATCH
                or preference_assessment.excluded_matches_count > 0
                or score.match_state == PreferenceMatchType.EXCLUDED_MATCH
            ):
                adaptive_score = 0.0
            else:
                # Clamp within adaptive config bounds [-max_adaptive_contribution, +max_adaptive_contribution]
                clamped_adaptive = max(
                    -adaptive_config.max_adaptive_contribution,
                    min(adaptive_config.max_adaptive_contribution, raw_adaptive_score),
                )
                # If explicit PREFERRED matches exist, opposing negative adaptive signals cannot drop the score below 0.50
                if preference_assessment.positive_matches_count > 0 and clamped_adaptive < 0.0:
                    if score.bounded_score >= 0.50:
                        bounded_adaptive = max(clamped_adaptive, 0.50 - score.bounded_score)
                    else:
                        bounded_adaptive = clamped_adaptive
                else:
                    bounded_adaptive = clamped_adaptive
                adaptive_score = round(bounded_adaptive, 4)

        final_personalization_score = round(
            max(0.0, min(1.0, score.bounded_score + adaptive_score)),
            4,
        )
        if (
            preference_assessment.overall_match_state == PreferenceMatchType.EXCLUDED_MATCH
            or preference_assessment.excluded_matches_count > 0
            or score.match_state == PreferenceMatchType.EXCLUDED_MATCH
        ):
            final_personalization_score = 0.0

        # 5. Generate structured deterministic explanations
        explanation = cls._generate_explanation(
            score=score,
            breakdown=breakdown,
            assessment=preference_assessment,
        )

        return PersonalizationAssessment(
            profile_id=profile_id,
            opportunity_id=opportunity.id,
            personalization_score=final_personalization_score,
            score=score,
            breakdown=breakdown,
            explanation=explanation,
            preference_assessment=preference_assessment,
            adaptive_score=adaptive_score,
            adaptive_contributions=adaptive_contributions,
            calibration_score=calibration_score,
            evaluated_at=datetime.now(timezone.utc),
        )

    @classmethod
    def score_opportunities_batch(
        cls,
        profile_id: uuid.UUID,
        preferences: Sequence[ResearcherPreferenceItemSchema | ResearcherPreferenceModel] | StructuredPreferencesResponseSchema,
        opportunities: Sequence[OpportunityModel],
        config: PersonalizationScoringConfig = DEFAULT_SCORING_CONFIG,
        adaptive_signals: Sequence[AdaptivePreferenceSignal] | None = None,
        adaptive_config: AdaptiveSignalConfig = DEFAULT_ADAPTIVE_CONFIG,
        calibrations: Sequence[PersonalizationCalibrationSchema] | None = None,
    ) -> dict[uuid.UUID, PersonalizationAssessment]:
        """
        Score a batch of opportunities in memory against researcher preferences, adaptive signals,
        and calibration modifiers with zero N+1 queries.
        """
        # 1. Batch evaluate Phase 5.2 preference interpretations
        batch_assessments = PreferenceInterpreter.evaluate_opportunities_batch(
            profile_id=profile_id,
            preferences=preferences,
            opportunities=opportunities,
        )

        # 2. Compute personalization assessments for each opportunity
        results: dict[uuid.UUID, PersonalizationAssessment] = {}
        for opp in opportunities:
            assessment = batch_assessments.get(opp.id)
            if assessment is not None:
                results[opp.id] = cls.score_opportunity(
                    profile_id=profile_id,
                    preferences=preferences,
                    opportunity=opp,
                    config=config,
                    preference_assessment=assessment,
                    adaptive_signals=adaptive_signals,
                    adaptive_config=adaptive_config,
                    calibrations=calibrations,
                )

        return results


    # -------------------------------------------------------------------------
    # Internal Calculation & Breakdown Helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _build_score_breakdown(
        cls,
        assessment: PreferencePersonalizationAssessment,
        config: PersonalizationScoringConfig,
    ) -> PersonalizationScoreBreakdown:
        """
        Produce structured contributions and per-dimension scores across all 9 dimensions.
        """
        dimension_scores: dict[PreferenceDimension, PersonalizationDimensionScore] = {}
        positive_contributions: list[PersonalizationContribution] = []
        negative_contributions: list[PersonalizationContribution] = []
        neutral_contributions: list[PersonalizationContribution] = []
        unresolved_contributions: list[PersonalizationContribution] = []

        # Map signals by dimension
        signals_by_dim: dict[PreferenceDimension, list[PreferenceMatchSignal]] = {}
        for sig in assessment.dimension_signals:
            signals_by_dim.setdefault(sig.dimension, []).append(sig)

        active_dims_count = 0
        total_pos_weight = 0.0
        total_neg_weight = 0.0

        for dim in PreferenceDimension:
            weight = config.get_dimension_weight(dim)
            signals = signals_by_dim.get(dim, [])

            if signals:
                active_dims_count += 1
                # Use primary signal for this dimension
                # If multiple signals exist (e.g. conflict), pick the most salient or combine
                primary_sig = cls._select_primary_signal(signals)
                match_type = primary_sig.match_type
                polarity = primary_sig.polarity
                confidence = primary_sig.confidence
                mult = config.get_match_multiplier(match_type)
                raw_contrib = round(weight * mult * confidence, 6)

                contrib = PersonalizationContribution(
                    dimension=dim,
                    match_type=match_type,
                    polarity=polarity,
                    weight=weight,
                    raw_contribution=raw_contrib,
                    normalized_contribution=raw_contrib,  # will be updated during score normalization
                    preference_value=primary_sig.preference_value,
                    opportunity_value=primary_sig.opportunity_value,
                    evidence=primary_sig.evidence,
                    explanation=primary_sig.explanation,
                )

                if match_type in (PreferenceMatchType.PREFERRED_MATCH, PreferenceMatchType.PARTIAL_MATCH) and raw_contrib > 0:
                    positive_contributions.append(contrib)
                    total_pos_weight += raw_contrib
                    dim_score_val = min(1.0, max(0.0, mult * confidence))
                elif match_type == PreferenceMatchType.EXCLUDED_MATCH or raw_contrib < 0:
                    negative_contributions.append(contrib)
                    total_neg_weight += abs(raw_contrib)
                    dim_score_val = 0.0
                elif match_type == PreferenceMatchType.CONFLICT:
                    unresolved_contributions.append(contrib)
                    dim_score_val = 0.5 * confidence
                elif match_type == PreferenceMatchType.INSUFFICIENT_EVIDENCE:
                    unresolved_contributions.append(contrib)
                    dim_score_val = 0.0
                else:
                    neutral_contributions.append(contrib)
                    dim_score_val = 0.0

                dimension_scores[dim] = PersonalizationDimensionScore(
                    dimension=dim,
                    score=round(dim_score_val, 4),
                    weight=weight,
                    weighted_score=round(weight * dim_score_val, 6),
                    status=match_type,
                    explanation=primary_sig.explanation,
                )
            else:
                # Dimension had no explicit preference evaluated or was marked insufficient/neutral
                is_insufficient = dim in assessment.insufficient_evidence_dimensions
                status = PreferenceMatchType.INSUFFICIENT_EVIDENCE if is_insufficient else PreferenceMatchType.NEUTRAL
                polarity = SignalPolarity.NEUTRAL

                contrib = PersonalizationContribution(
                    dimension=dim,
                    match_type=status,
                    polarity=polarity,
                    weight=weight,
                    raw_contribution=0.0,
                    normalized_contribution=0.0,
                    preference_value="None",
                    opportunity_value=None,
                    evidence="No explicit preference declared or opportunity evidence unavailable.",
                    explanation=(
                        f"Evidence for {dim.value.replace('_', ' ').lower()} was unavailable in this opportunity."
                        if is_insufficient
                        else f"No explicit preference declared for {dim.value.replace('_', ' ').lower()}."
                    ),
                )

                if is_insufficient:
                    unresolved_contributions.append(contrib)
                else:
                    neutral_contributions.append(contrib)

                dimension_scores[dim] = PersonalizationDimensionScore(
                    dimension=dim,
                    score=0.0,
                    weight=weight,
                    weighted_score=0.0,
                    status=status,
                    explanation=contrib.explanation,
                )

        return PersonalizationScoreBreakdown(
            dimension_scores=dimension_scores,
            positive_contributions=positive_contributions,
            negative_contributions=negative_contributions,
            neutral_contributions=neutral_contributions,
            unresolved_contributions=unresolved_contributions,
            total_positive_weight=round(total_pos_weight, 6),
            total_negative_weight=round(total_neg_weight, 6),
            active_dimensions_count=active_dims_count,
        )

    @classmethod
    def _select_primary_signal(cls, signals: list[PreferenceMatchSignal]) -> PreferenceMatchSignal:
        """Select the most representative signal when a dimension contains multiple signals."""
        if len(signals) == 1:
            return signals[0]
        # Priority order: CONFLICT > EXCLUDED_MATCH > PREFERRED_MATCH > PARTIAL_MATCH > INSUFFICIENT_EVIDENCE > NEUTRAL
        order = {
            PreferenceMatchType.CONFLICT: 0,
            PreferenceMatchType.EXCLUDED_MATCH: 1,
            PreferenceMatchType.PREFERRED_MATCH: 2,
            PreferenceMatchType.PARTIAL_MATCH: 3,
            PreferenceMatchType.INSUFFICIENT_EVIDENCE: 4,
            PreferenceMatchType.NEUTRAL: 5,
        }
        return min(signals, key=lambda s: order.get(s.match_type, 99))

    @classmethod
    def _calculate_personalization_score(
        cls,
        breakdown: PersonalizationScoreBreakdown,
        assessment: PreferencePersonalizationAssessment,
        config: PersonalizationScoringConfig,
    ) -> PersonalizationScore:
        """
        Calculate bounded, normalized, and absolute personalization scores.
        """
        pos = breakdown.total_positive_weight
        neg = breakdown.total_negative_weight
        raw_net = pos - neg

        # Active weights sum
        active_weights = sum(
            c.weight for c in breakdown.positive_contributions + breakdown.negative_contributions + breakdown.unresolved_contributions
            if c.match_type not in (PreferenceMatchType.NEUTRAL, PreferenceMatchType.INSUFFICIENT_EVIDENCE)
        )

        # Cold start (no preferences active) -> strictly neutral 0.0
        if breakdown.active_dimensions_count == 0 or active_weights == 0:
            return PersonalizationScore(
                bounded_score=0.0,
                normalized_score=0.0,
                absolute_score=0.0,
                raw_score=0.0,
                positive_contribution=0.0,
                negative_penalty=0.0,
                confidence=0.0,
                match_state=PreferenceMatchType.NEUTRAL,
            )

        # Normalized score: relative to active configured preferences
        # Range: [0.0, 1.0]
        normalized = max(0.0, min(1.0, (pos - neg) / active_weights))

        # Absolute score: relative to all 9 dimensions (sum of weights = 1.0)
        absolute = max(0.0, min(1.0, raw_net))

        # Bounded score is the authoritative score in [0.0, 1.0]
        bounded = round(normalized, 4)

        # Update normalized contribution in breakdown
        if active_weights > 0:
            for c in breakdown.positive_contributions:
                c.normalized_contribution = round(c.raw_contribution / active_weights, 4)
            for c in breakdown.negative_contributions:
                c.normalized_contribution = round(c.raw_contribution / active_weights, 4)

        return PersonalizationScore(
            bounded_score=bounded,
            normalized_score=round(normalized, 4),
            absolute_score=round(absolute, 4),
            raw_score=round(raw_net, 4),
            positive_contribution=round(pos, 4),
            negative_penalty=round(neg, 4),
            confidence=round(assessment.evidence_coverage, 4),
            match_state=assessment.overall_match_state,
        )

    @classmethod
    def _generate_explanation(
        cls,
        score: PersonalizationScore,
        breakdown: PersonalizationScoreBreakdown,
        assessment: PreferencePersonalizationAssessment,
    ) -> PersonalizationExplanation:
        """
        Generate structured deterministic natural-language explanations without LLMs.
        """
        positive_reasons = [c.explanation for c in breakdown.positive_contributions]
        negative_reasons = [c.explanation for c in breakdown.negative_contributions]
        unresolved_reasons = [
            c.explanation for c in breakdown.unresolved_contributions
            if c.match_type == PreferenceMatchType.CONFLICT
        ]
        insufficient_reasons = [
            c.explanation for c in breakdown.unresolved_contributions
            if c.match_type == PreferenceMatchType.INSUFFICIENT_EVIDENCE
        ]
        neutral_reasons = [c.explanation for c in breakdown.neutral_contributions]

        # Executive summary
        if score.match_state == PreferenceMatchType.NEUTRAL and score.bounded_score == 0.0:
            summary = "Personalization score: 0.00 (Neutral: no explicit preferences configured or applicable)."
        elif score.match_state == PreferenceMatchType.EXCLUDED_MATCH:
            summary = f"Personalization score: {score.bounded_score:.2f} (Excluded: opportunity matches explicit exclusion criteria)."
        elif score.match_state == PreferenceMatchType.CONFLICT:
            summary = f"Personalization score: {score.bounded_score:.2f} (Preference conflict: opportunity matches both preferred and excluded criteria)."
        elif score.match_state == PreferenceMatchType.PREFERRED_MATCH:
            summary = f"Personalization score: {score.bounded_score:.2f} (Preferred: matches explicit preferences across {len(positive_reasons)} dimension(s))."
        elif score.match_state == PreferenceMatchType.INSUFFICIENT_EVIDENCE:
            summary = f"Personalization score: {score.bounded_score:.2f} (Insufficient evidence: opportunity metadata was unavailable for evaluation)."
        else:
            summary = f"Personalization score: {score.bounded_score:.2f}."

        return PersonalizationExplanation(
            summary=summary,
            positive_reasons=positive_reasons,
            negative_reasons=negative_reasons,
            unresolved_reasons=unresolved_reasons,
            insufficient_evidence_reasons=insufficient_reasons,
            neutral_reasons=neutral_reasons,
        )
