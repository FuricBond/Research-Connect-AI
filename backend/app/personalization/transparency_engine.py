from __future__ import annotations

from typing import Any, Sequence

from app.models.personalization_governance import GovernanceGateState
from app.models.personalization_transparency import PersonalizationImpact
from app.personalization.transparency_config import (
    DEFAULT_TRANSPARENCY_CONFIG,
    PersonalizationTransparencyConfig,
)


class PersonalizationTransparencyEngine:
    """
    Deterministic engine for generating researcher-facing personalization explanations,
    impact classifications, and factor attributions (Phase 5.9).

    Strict Architectural Boundaries:
      - Zero ML / Zero LLMs: 100% deterministic, rule-based logic.
      - Explanation Safety: Never claims 'you will like this' or 'we know your interests'.
      - Precedence Hierarchy:
          explicit preference > adaptive signal > calibration > contextual quality > governance state.
      - Core Relevance Dominance: Clearly distinguishes core relevance (>= 85%) from personalization (<= 15%).
    """

    @classmethod
    def determine_personalization_impact(
        cls,
        personalization_enabled: bool,
        is_excluded: bool,
        governance_state: GovernanceGateState | str | None,
        base_relevance_score: float,
        personalization_score: float,
        final_score: float,
        config: PersonalizationTransparencyConfig = DEFAULT_TRANSPARENCY_CONFIG,
    ) -> PersonalizationImpact:
        """
        Classifies the net personalization impact into a bounded deterministic category.
        """
        if is_excluded:
            return PersonalizationImpact.PERSONALIZATION_SUPPRESSED

        gov_str = (
            governance_state.value
            if hasattr(governance_state, "value")
            else str(governance_state or "")
        ).upper()

        if gov_str == "SUSPEND":
            return PersonalizationImpact.PERSONALIZATION_SUPPRESSED

        if not personalization_enabled:
            return PersonalizationImpact.NO_PERSONALIZATION

        net_delta = round(abs(final_score - base_relevance_score), 4)

        if net_delta < config.impact_low_threshold:
            return PersonalizationImpact.NO_PERSONALIZATION
        elif net_delta < config.impact_moderate_threshold:
            return PersonalizationImpact.LOW_PERSONALIZATION
        elif net_delta < config.impact_strong_threshold:
            return PersonalizationImpact.MODERATE_PERSONALIZATION
        else:
            return PersonalizationImpact.STRONG_PERSONALIZATION

    @classmethod
    def build_factors_and_explanation(
        cls,
        opportunity_title: str,
        base_relevance_score: float,
        personalization_score: float,
        final_score: float,
        personalization_enabled: bool,
        adaptive_signals_enabled: bool,
        governance_state: GovernanceGateState | str | None,
        governance_multiplier: float,
        explicit_matches: Sequence[dict[str, Any]] | None = None,
        adaptive_signals: Sequence[dict[str, Any]] | None = None,
        calibrations: Sequence[dict[str, Any]] | None = None,
        contextual_adaptations: Sequence[dict[str, Any]] | None = None,
        config: PersonalizationTransparencyConfig = DEFAULT_TRANSPARENCY_CONFIG,
    ) -> tuple[
        PersonalizationImpact,
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        str | None,
        list[str],
        str,
    ]:
        """
        Builds all factor breakdowns and deterministic natural language explanation.

        Returns
        -------
        tuple:
          (impact, explicit_factors, adaptive_factors, calib_factors, ctx_factors, gov_notes, summary_list, explanation_text)
        """
        is_excluded = any(
            m.get("preference_type") == "EXCLUDED"
            or m.get("match_type") == "EXCLUDED_MATCH"
            for m in (explicit_matches or [])
        )

        impact = cls.determine_personalization_impact(
            personalization_enabled=personalization_enabled,
            is_excluded=is_excluded,
            governance_state=governance_state,
            base_relevance_score=base_relevance_score,
            personalization_score=personalization_score,
            final_score=final_score,
            config=config,
        )

        gov_str = (
            governance_state.value
            if hasattr(governance_state, "value")
            else str(governance_state or "ALLOW")
        ).upper()

        # 1. Explicit Preference Factors
        explicit_factors: list[dict[str, Any]] = []
        for m in (explicit_matches or []):
            cat = m.get("category", "General")
            val = m.get("value", "")
            p_type = m.get("preference_type", "PREFERRED")
            explicit_factors.append({
                "category": cat,
                "value": val,
                "preference_type": p_type,
                "summary": f"Matches your explicit {p_type.lower()} preference for {cat.lower()}: {val}",
            })

        # 2. Adaptive Signal Factors
        adaptive_factors: list[dict[str, Any]] = []
        if adaptive_signals_enabled and personalization_enabled and gov_str != "SUSPEND":
            for s in (adaptive_signals or []):
                dim = s.get("dimension", "")
                val = s.get("signal_value", "")
                score_mod = s.get("contribution", 0.0)
                adaptive_factors.append({
                    "dimension": dim,
                    "signal_value": val,
                    "contribution": score_mod,
                    "summary": f"Recent positive engagement with {dim.lower()} '{val}'",
                })

        # 3. Calibration Factors
        calibration_factors: list[dict[str, Any]] = []
        if adaptive_signals_enabled and personalization_enabled and gov_str != "SUSPEND":
            for c in (calibrations or []):
                dim = c.get("dimension", "")
                val = c.get("signal_value", "")
                mod = c.get("modifier", 0.0)
                if abs(mod) > 0.0001:
                    action = "strengthened" if mod > 0 else "moderated"
                    calibration_factors.append({
                        "dimension": dim,
                        "signal_value": val,
                        "modifier": mod,
                        "summary": f"Personalization {action} based on feedback history for {dim.lower()} '{val}'",
                    })

        # 4. Contextual Factors
        contextual_factors: list[dict[str, Any]] = []
        if adaptive_signals_enabled and personalization_enabled and gov_str != "SUSPEND":
            for ctx in (contextual_adaptations or []):
                ctx_dim = ctx.get("context_dimension", "")
                ctx_val = ctx.get("context_value", "")
                mod = ctx.get("modifier", 0.0)
                if abs(mod) > 0.0001:
                    contextual_factors.append({
                        "context_dimension": ctx_dim,
                        "context_value": ctx_val,
                        "modifier": mod,
                        "summary": f"Contextual adaptation for {ctx_dim.lower()} '{ctx_val}'",
                    })

        # 5. Governance Notes
        gov_notes = None
        if gov_str == "SUSPEND":
            gov_notes = "Personalization is temporarily suspended due to signal instability or explicit exclusion. Recommendations rely strictly on core relevance."
        elif gov_str == "ALLOW_BOUNDED":
            gov_notes = "Personalization is operating in a bounded safety tier (50% damping) while recent behavioral signals stabilize."
        elif gov_str == "HOLD":
            gov_notes = "Adaptive updates are temporarily held (25% damping) pending signal convergence."
        elif gov_str == "REDUCE":
            gov_notes = "Adaptive influence is progressively reduced (10% damping) to maintain recommendation quality."

        # 6. Summary Checklist (Precedence ordered)
        summary_list: list[str] = []

        if not personalization_enabled:
            summary_list.append("○ Personalization is disabled by your controls; showing general relevance.")
        elif is_excluded:
            summary_list.append("✕ Excluded by your explicit preferences.")
        else:
            if explicit_factors:
                summary_list.append("✓ Matches your explicit research preferences")
            if adaptive_factors:
                summary_list.append("✓ Similar opportunities received positive interactions")
            if calibration_factors:
                summary_list.append("✓ Calibrated against your historical interaction outcomes")
            if contextual_factors:
                summary_list.append("✓ Adapted for the opportunity's specific deadline and type context")

            if gov_str == "SUSPEND":
                summary_list.append("○ Personalization suspended to preserve recommendation safety")
            elif gov_str in ("ALLOW_BOUNDED", "HOLD", "REDUCE"):
                summary_list.append(f"○ Personalization bounded ({gov_str}) to ensure safety")
            elif not summary_list:
                summary_list.append("✓ Recommended primarily based on core topic and domain relevance")

        # 7. Narrative Explanation
        relevance_pct = round(base_relevance_score * 100)
        pers_pct = round(personalization_score * 100)

        if not personalization_enabled:
            explanation_text = (
                f"'{opportunity_title}' was retrieved based on core academic relevance ({relevance_pct}%). "
                "Personalization is currently turned off in your researcher controls, so no behavioral "
                "or adaptive adjustments were applied."
            )
        elif is_excluded:
            explanation_text = (
                f"'{opportunity_title}' matches one of your explicit exclusion preferences. "
                "In accordance with platform safety rules, excluded opportunities are suppressed from active recommendations."
            )
        elif gov_str == "SUSPEND":
            explanation_text = (
                f"'{opportunity_title}' was retrieved with a core relevance score of {relevance_pct}%. "
                "Personalization adjustments are currently suspended by the governance safety gate to ensure "
                "recommendation reliability."
            )
        else:
            reasons = []
            if explicit_factors:
                reasons.append("aligns with your explicit research preferences")
            if adaptive_factors:
                reasons.append("matches patterns from your recent positive interactions")
            if not reasons:
                reasons.append("has high overall academic relevance to your profile")

            reason_str = " and ".join(reasons)
            explanation_text = (
                f"This opportunity has a core relevance score of {relevance_pct}% and a personalization score of {pers_pct}%. "
                f"It was recommended because it {reason_str}. "
            )
            if gov_notes:
                explanation_text += gov_notes

        return (
            impact,
            explicit_factors,
            adaptive_factors,
            calibration_factors,
            contextual_factors,
            gov_notes,
            summary_list,
            explanation_text,
        )
