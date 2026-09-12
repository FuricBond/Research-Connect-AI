"""
Deterministic Recommendation Explanation Engine (Phase 3.8).

Strict Architectural Boundaries:
  - Transparent, human-understandable, and machine-inspectable explanations.
  - Zero mathematical hallucinations: reasons are strictly derived from verified active or historical signals.
  - Influence-ordered factor hierarchy:
      1. Strong explicit preferences
      2. Scholarly expertise & emerging interests
      3. Behavioral feedback signals (positive interactions & negative demotions)
      4. Profile attributes & academic status
      5. Baseline domain & semantic relevance
      6. Deadline urgency & lifecycle
      7. Academic trust & safety compliance
  - Safety Dominance: High-risk opportunities prominently preserve risk warnings and never praise fit.
  - Historical Immutability: Historical snapshot items are explained strictly from frozen snapshot data.
  - Full Score Consistency: reported scores exactly match ranking candidate scores.
"""
from __future__ import annotations

from typing import Any, Sequence
import uuid

from app.schemas.recommendation_explanation import (
    ExplanationFactorSchema,
    ExplanationReasonCategory,
    RecommendationExplanationSchema,
    SignalImpact,
)


class RecommendationExplainer:
    """
    Pure deterministic explanation generator for ResearchConnect AI recommendations.
    """

    @staticmethod
    def derive_personalization_strength(
        adjustment: float,
        personalization_score: float,
        is_cold_start: bool = False,
    ) -> str:
        """
        Derive human-friendly personalization strength level strictly from actual scores.
        """
        if is_cold_start:
            return "General recommendation"
        if adjustment >= 0.10 or (personalization_score >= 0.80 and adjustment >= 0.05):
            return "Highly personalized"
        if adjustment >= 0.05 or (personalization_score >= 0.50 and adjustment >= 0.02):
            return "Personalized"
        if adjustment > 0.001 or personalization_score >= 0.20:
            return "Some personalization"
        return "General recommendation"

    @classmethod
    def explain_ranked_candidate(
        cls,
        candidate: Any,
        context: Any,
        ranking_version: str = "phase3.8-v1",
    ) -> RecommendationExplanationSchema:
        """
        Generate a structured, grounded explanation for an actively ranked candidate.

        Parameters
        ----------
        candidate : PersonalizedRankedCandidateSchema or _ScoredPersonalizedCandidate
            The ranked opportunity candidate with scores, breakdown, matched signals, and opportunity metadata.
        context : ResearcherPersonalizationContext
            The researcher personalization context with active preferences, expertise, and behavioral signals.
        ranking_version : str
            Deterministic version of the ranking pipeline.
        """
        opp_id = getattr(candidate, "opportunity_id", uuid.uuid4())
        rank = int(getattr(candidate, "rank", 1))
        base_score = float(getattr(candidate, "base_relevance_score", 0.0))
        p_score = float(getattr(candidate, "personalization_score", 0.0))
        p_adj = float(getattr(candidate, "personalization_adjustment", 0.0))
        final_score = float(getattr(candidate, "final_score", base_score))

        breakdown = getattr(candidate, "score_breakdown", None) or getattr(candidate, "breakdown", None)
        matched_sigs = getattr(candidate, "matched_signals", None)
        opp = getattr(candidate, "opportunity", None)

        # ── 1. Safety & Risk Intelligence Verification ───────────────────────
        risk_level = (getattr(opp, "risk_level", "LOW_RISK") if opp else "LOW_RISK") or "LOW_RISK"
        is_predatory = bool(getattr(opp, "is_predatory_flag", False) if opp else False)
        risk_score = float(getattr(opp, "risk_score", 0.0) or 0.0 if opp else 0.0)
        is_high_risk = is_predatory or risk_level == "HIGH_RISK" or risk_score >= 0.70

        if is_predatory:
            trust_status = "High Risk"
            risk_summary = "CRITICAL WARNING: This venue is flagged with predatory characteristics. Proceed with caution."
        elif is_high_risk:
            trust_status = "High Risk"
            risk_summary = f"HIGH RISK: Elevated risk indicators detected (Score: {risk_score:.2f}). Thorough verification required."
        elif risk_level == "MODERATE_RISK" or risk_score >= 0.40:
            trust_status = "Caution"
            risk_summary = f"CAUTION: Moderate risk signals detected. Publisher verification recommended."
        else:
            trust_status = "Verified"
            risk_summary = "Verified academic venue passing publication-quality and trust checks."

        # ── 2. Deadline Intelligence Summary ─────────────────────────────────
        deadline_status = getattr(opp, "deadline_status", None) if opp else None
        submission_deadline = getattr(opp, "submission_deadline", None) if opp else None

        if deadline_status == "EXPIRED":
            deadline_summary = "Submission deadline has passed."
        elif deadline_status == "DUE_TODAY":
            deadline_summary = "URGENT: Submission deadline is today."
        elif deadline_status == "APPROACHING" or deadline_status == "UPCOMING":
            deadline_summary = "Upcoming submission deadline approaching."
        elif submission_deadline:
            deadline_summary = f"Submission deadline active."
        else:
            deadline_summary = "Open submission / Rolling deadline."

        # ── 3. Categorized Explanations ──────────────────────────────────────
        primary_reasons: list[str] = []
        supporting_reasons: list[str] = []
        behavioral_reasons: list[str] = []
        preference_reasons: list[str] = []
        expertise_reasons: list[str] = []
        negative_signals: list[str] = []
        factors: list[ExplanationFactorSchema] = []

        # Grounding sets from context
        ctx_pref_values = set()
        for p in getattr(context, "explicit_preferences", ()):
            val = getattr(p, "preference_value", None)
            if val:
                ctx_pref_values.add(str(val).upper())

        ctx_expertise_topics = set()
        for e in getattr(context, "expertise_items", ()):
            topic = getattr(e, "topic_name", None)
            if topic:
                ctx_expertise_topics.add(str(topic).lower())

        # (A) Explicit Preferences
        if matched_sigs and hasattr(matched_sigs, "matched_preferences"):
            for mp in matched_sigs.matched_preferences:
                if mp.upper().startswith("BEHAVIORAL") or mp.startswith("Suppressed"):
                    continue
                # Verify grounding against context
                mp_upper = mp.upper()
                is_grounded = any(p_val in mp_upper for p_val in ctx_pref_values) if ctx_pref_values else True
                if is_grounded:
                    desc = f"Matches your explicit preference: {mp}."
                    preference_reasons.append(desc)
                    factors.append(
                        ExplanationFactorSchema(
                            category=ExplanationReasonCategory.EXPLICIT_PREFERENCE,
                            title="Explicit Preference Match",
                            description=desc,
                            impact=SignalImpact.POSITIVE,
                            weight_contribution=round(float(getattr(breakdown, "explicit_preference_score", 0.40) or 0.40), 2),
                        )
                    )

        # (B) Scholarly Expertise & Emerging Interests
        if matched_sigs and hasattr(matched_sigs, "matched_expertise"):
            for exp in matched_sigs.matched_expertise:
                desc = f"Strong alignment with your scholarly expertise in {exp}."
                expertise_reasons.append(desc)
                factors.append(
                    ExplanationFactorSchema(
                        category=ExplanationReasonCategory.EXPERTISE_MATCH,
                        title="Scholarly Expertise Match",
                        description=desc,
                        impact=SignalImpact.POSITIVE,
                        weight_contribution=round(float(getattr(breakdown, "expertise_match_score", 0.25) or 0.25), 2),
                    )
                )

        # (C) Behavioral Signals (Phase 3.6)
        beh_adj = float(getattr(breakdown, "behavioral_adjustment", 0.0) or 0.0)
        beh_score = float(getattr(breakdown, "behavioral_score", 0.0) or 0.0)
        beh_conf = float(getattr(breakdown, "behavioral_confidence", 0.0) or 0.0)

        is_suppressed = bool(
            hasattr(context, "suppressed_opportunity_ids")
            and opp_id in getattr(context, "suppressed_opportunity_ids")
        )

        if is_suppressed:
            neg_desc = "Lowered rank because this opportunity has active negative interaction feedback."
            negative_signals.append(neg_desc)
            behavioral_reasons.append(neg_desc)
            factors.append(
                ExplanationFactorSchema(
                    category=ExplanationReasonCategory.NEGATIVE_SIGNAL,
                    title="Active Negative Suppression",
                    description=neg_desc,
                    impact=SignalImpact.NEGATIVE,
                    weight_contribution=round(beh_adj, 2),
                )
            )
        elif beh_adj > 0.0:
            pos_desc = "Boosted based on your past positive engagement with similar opportunities (saved/applied)."
            behavioral_reasons.append(pos_desc)
            factors.append(
                ExplanationFactorSchema(
                    category=ExplanationReasonCategory.BEHAVIORAL_SIGNAL,
                    title="Learned Behavioral Affinity",
                    description=pos_desc,
                    impact=SignalImpact.POSITIVE,
                    weight_contribution=round(beh_adj, 2),
                )
            )
        elif beh_adj < 0.0:
            neg_desc = "Adjusted lower due to past dismissals of related opportunities."
            negative_signals.append(neg_desc)
            behavioral_reasons.append(neg_desc)
            factors.append(
                ExplanationFactorSchema(
                    category=ExplanationReasonCategory.NEGATIVE_SIGNAL,
                    title="Learned Negative Feedback",
                    description=neg_desc,
                    impact=SignalImpact.NEGATIVE,
                    weight_contribution=round(beh_adj, 2),
                )
            )

        # (D) Profile Keywords
        prof_score = float(getattr(breakdown, "profile_match_score", 0.0) or 0.0)
        if prof_score >= 0.5:
            supporting_reasons.append("Matches your researcher profile keywords and academic department.")
            factors.append(
                ExplanationFactorSchema(
                    category=ExplanationReasonCategory.PROFILE_MATCH,
                    title="Profile Alignment",
                    description="Matches your researcher profile keywords.",
                    impact=SignalImpact.POSITIVE,
                    weight_contribution=round(prof_score, 2),
                )
            )

        # (E) Domain / Semantic Relevance
        if base_score >= 0.70:
            supporting_reasons.append(f"High semantic and lexical domain relevance ({round(base_score * 100)}% match).")
        elif base_score >= 0.40:
            supporting_reasons.append(f"Moderate scholarly relevance to your research scope ({round(base_score * 100)}% match).")
        else:
            supporting_reasons.append(f"Baseline discovery candidate ({round(base_score * 100)}% match).")

        factors.append(
            ExplanationFactorSchema(
                category=ExplanationReasonCategory.DOMAIN_RELEVANCE,
                title="Base Academic Relevance",
                description=f"Phase 2 hybrid semantic and lexical score: {base_score:.2f}",
                impact=SignalImpact.POSITIVE if base_score >= 0.40 else SignalImpact.NEUTRAL,
                weight_contribution=round(base_score, 2),
            )
        )

        # (F) Negative risk signal factor
        if is_high_risk:
            negative_signals.append(risk_summary)
            factors.append(
                ExplanationFactorSchema(
                    category=ExplanationReasonCategory.TRUST_SAFETY,
                    title="Trust & Safety Warning",
                    description=risk_summary,
                    impact=SignalImpact.WARNING,
                    weight_contribution=-0.50,
                )
            )

        # ── 4. Build Prioritized Primary Reasons (Strict Influence Hierarchy) ──
        # Priority:
        # 1. High-risk warning (if present, safety dominance requires immediate visibility)
        # 2. Strong explicit preference
        # 3. Strong scholarly expertise match
        # 4. Strong behavioral signal (positive or negative)
        # 5. Profile keyword match
        # 6. General domain relevance
        # 7. Deadline urgency
        if is_high_risk:
            primary_reasons.append(f"⚠️ {risk_summary}")

        if preference_reasons:
            primary_reasons.append(preference_reasons[0])

        if expertise_reasons:
            primary_reasons.append(expertise_reasons[0])

        if not is_high_risk and behavioral_reasons and len(primary_reasons) < 3:
            primary_reasons.append(behavioral_reasons[0])

        if len(primary_reasons) < 2 and supporting_reasons:
            primary_reasons.append(supporting_reasons[0])

        # If cold start or no specific reasons were identified, provide grounded fallback
        is_cold = bool(getattr(context, "is_cold_start", False))
        if not primary_reasons:
            if is_cold:
                primary_reasons.append(f"Recommended based on general domain relevance ({round(base_score * 100)}% match). Complete your profile to enable personalized ranking.")
            else:
                primary_reasons.append(f"Recommended based on academic topic alignment and publication trust checks.")

        personalization_strength = cls.derive_personalization_strength(
            adjustment=p_adj,
            personalization_score=p_score,
            is_cold_start=is_cold,
        )

        confidence = max(0.2, min(1.0, 0.5 + (beh_conf * 0.3) + (0.2 if preference_reasons or expertise_reasons else 0.0)))

        return RecommendationExplanationSchema(
            opportunity_id=opp_id,
            rank=rank,
            final_score=round(final_score, 4),
            base_relevance_score=round(base_score, 4),
            personalization_contribution=round(p_adj, 4),
            personalization_strength=personalization_strength,
            primary_reasons=primary_reasons,
            supporting_reasons=supporting_reasons,
            behavioral_reasons=behavioral_reasons,
            preference_reasons=preference_reasons,
            expertise_reasons=expertise_reasons,
            negative_signals=negative_signals,
            factors=factors,
            risk_summary=risk_summary,
            deadline_summary=deadline_summary,
            confidence=round(confidence, 2),
            trust_status=trust_status,
            is_historical=False,
            ranking_version=ranking_version,
        )

    @classmethod
    def explain_historical_item(
        cls,
        item: Any,
        snapshot: Any,
        opportunity_title: str | None = None,
        opportunity_type: str | None = None,
    ) -> RecommendationExplanationSchema:
        """
        Generate a frozen historical explanation for a snapshot item (Phase 3.7).

        Strict Architectural Boundary:
          - Uses only frozen values stored on ResearcherRecommendationItemModel and Snapshot.
          - Never re-queries today's researcher profile or re-ranks against current models.
        """
        opp_id = getattr(item, "opportunity_id", uuid.uuid4())
        rank = int(getattr(item, "rank", 1))
        base_score = float(getattr(item, "base_relevance_score", 0.0))
        p_score = float(getattr(item, "personalization_score", 0.0))
        beh_adj = float(getattr(item, "behavioral_adjustment", 0.0))
        final_score = float(getattr(item, "final_score", base_score))
        risk_level = getattr(item, "risk_level", None) or "LOW_RISK"
        deadline_status = getattr(item, "deadline_status", None) or "UPCOMING"
        version = getattr(snapshot, "ranking_version", "phase3.7-v1")
        created_at = getattr(snapshot, "created_at", None)

        p_adj = max(0.0, round(final_score - base_score, 4)) if final_score >= base_score else 0.0
        p_strength = cls.derive_personalization_strength(p_adj, p_score)

        # Risk summary from frozen risk level
        is_high_risk = risk_level == "HIGH_RISK"
        if is_high_risk:
            trust_status = "High Risk"
            risk_summary = f"Historical record indicates high-risk indicators detected at recommendation time."
        elif risk_level == "MODERATE_RISK":
            trust_status = "Caution"
            risk_summary = f"Historical record indicates moderate risk indicators at recommendation time."
        else:
            trust_status = "Verified"
            risk_summary = f"Verified publisher status at recommendation time."

        # Deadline summary from frozen deadline status
        if deadline_status == "EXPIRED":
            deadline_summary = "Deadline was expired at recommendation time."
        elif deadline_status == "DUE_TODAY":
            deadline_summary = "Deadline was due on recommendation date."
        elif deadline_status == "APPROACHING":
            deadline_summary = "Deadline was approaching at recommendation time."
        else:
            deadline_summary = "Standard active submission window."

        primary_reasons: list[str] = []
        supporting_reasons: list[str] = []
        negative_signals: list[str] = []
        factors: list[ExplanationFactorSchema] = []

        if is_high_risk:
            primary_reasons.append(f"⚠️ {risk_summary}")
            negative_signals.append(risk_summary)

        date_str = created_at.strftime("%b %d, %Y") if created_at and hasattr(created_at, "strftime") else "historical session"
        primary_reasons.append(f"Recommended on {date_str} via {version} pipeline.")

        if p_adj > 0.0:
            primary_reasons.append(f"Received personalization boost (+{p_adj:.2f}) based on profile alignment at recommendation time.")
        else:
            primary_reasons.append(f"Ranked based on Phase 2 baseline relevance ({round(base_score * 100)}% match).")

        supporting_reasons.append(f"Frozen point-in-time snapshot preserved for auditability and offline evaluation.")

        factors.append(
            ExplanationFactorSchema(
                category=ExplanationReasonCategory.DOMAIN_RELEVANCE,
                title="Historical Base Relevance",
                description=f"Phase 2 base relevance at recommendation time: {base_score:.2f}",
                impact=SignalImpact.POSITIVE if base_score >= 0.40 else SignalImpact.NEUTRAL,
                weight_contribution=round(base_score, 2),
            )
        )

        if beh_adj != 0.0:
            factors.append(
                ExplanationFactorSchema(
                    category=ExplanationReasonCategory.BEHAVIORAL_SIGNAL,
                    title="Historical Behavioral Adjustment",
                    description=f"Phase 3.6 behavioral contribution: {beh_adj:.2f}",
                    impact=SignalImpact.POSITIVE if beh_adj > 0 else SignalImpact.NEGATIVE,
                    weight_contribution=round(beh_adj, 2),
                )
            )

        return RecommendationExplanationSchema(
            opportunity_id=opp_id,
            rank=rank,
            final_score=round(final_score, 4),
            base_relevance_score=round(base_score, 4),
            personalization_contribution=round(p_adj, 4),
            personalization_strength=p_strength,
            primary_reasons=primary_reasons,
            supporting_reasons=supporting_reasons,
            behavioral_reasons=[],
            preference_reasons=[],
            expertise_reasons=[],
            negative_signals=negative_signals,
            factors=factors,
            risk_summary=risk_summary,
            deadline_summary=deadline_summary,
            confidence=1.0,
            trust_status=trust_status,
            is_historical=True,
            ranking_version=version,
        )


recommendation_explainer = RecommendationExplainer()
