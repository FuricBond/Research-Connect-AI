"""
PreferenceInterpreter for Phase 5.2 — Explicit Preference Interpretation & Personalization Signal Foundation.

Evaluates research opportunities against explicit researcher preferences deterministically,
producing structured, explainable personalization signals and comprehensive assessments.

Guarantees:
  - 100% deterministic (no random seeds, no time drift, no floating-point ambiguity)
  - Zero LLM calls
  - Zero network calls
  - Zero database writes
  - Zero N+1 queries (batch evaluation in memory)
  - Preserves 3-state semantics: PREFERRED != NEUTRAL != EXCLUDED
  - Missing opportunity data -> INSUFFICIENT_EVIDENCE (never assumed negative or excluded)
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any, Sequence
import uuid

from app.models.opportunity import OpportunityModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.personalization.models import (
    PreferenceDimension,
    PreferenceMatchSignal,
    PreferenceMatchType,
    PreferencePersonalizationAssessment,
    SignalPolarity,
)
from app.schemas.researcher_preference import (
    PreferenceCategory,
    ResearcherPreferenceItemSchema,
    StructuredPreferencesResponseSchema,
)
from app.services.researcher_preference_service import (
    CANONICAL_OPPORTUNITY_TYPES,
    ResearcherPreferenceService,
)

logger = logging.getLogger(__name__)

# Common country name to ISO 2-letter code mapping for geographic matching
COUNTRY_NAME_TO_CODE: dict[str, str] = {
    "UNITED STATES": "US",
    "USA": "US",
    "UNITED STATES OF AMERICA": "US",
    "GERMANY": "DE",
    "DEUTSCHLAND": "DE",
    "UNITED KINGDOM": "GB",
    "UK": "GB",
    "GREAT BRITAIN": "GB",
    "ENGLAND": "GB",
    "FRANCE": "FR",
    "CANADA": "CA",
    "AUSTRALIA": "AU",
    "JAPAN": "JP",
    "CHINA": "CN",
    "INDIA": "IN",
    "ITALY": "IT",
    "SPAIN": "ES",
    "NETHERLANDS": "NL",
    "SWITZERLAND": "CH",
    "SWEDEN": "SE",
    "SINGAPORE": "SG",
    "BRAZIL": "BR",
    "SOUTH KOREA": "KR",
    "KOREA": "KR",
}


class PreferenceInterpreter:
    """
    Authoritative evaluation engine for converting explicit researcher preferences
    into explainable personalization signals.
    """

    @classmethod
    def evaluate_opportunity(
        cls,
        profile_id: uuid.UUID,
        preferences: Sequence[ResearcherPreferenceItemSchema | ResearcherPreferenceModel] | StructuredPreferencesResponseSchema,
        opportunity: OpportunityModel,
    ) -> PreferencePersonalizationAssessment:
        """
        Evaluate a single opportunity against a researcher's explicit preferences.

        Parameters
        ----------
        profile_id : uuid.UUID
            Canonical ResearchProfileModel ID.
        preferences : Sequence of preferences or StructuredPreferencesResponseSchema
            Active explicit preferences of the researcher.
        opportunity : OpportunityModel
            Opportunity to evaluate (with topic_associations preloaded where possible).

        Returns
        -------
        PreferencePersonalizationAssessment
            Complete, deterministic assessment with per-dimension signals.
        """
        # 1. Normalize preferences into categorized buckets
        structured_prefs = cls._normalize_to_structured(preferences, profile_id)

        signals: list[PreferenceMatchSignal] = []
        insufficient_dims: list[PreferenceDimension] = []
        neutral_dims: list[PreferenceDimension] = []

        # 2. Evaluate each supported dimension deterministically
        # A. OPPORTUNITY TYPE
        type_signals, type_insufficient = cls._evaluate_opportunity_type(
            profile_id, opportunity, structured_prefs
        )
        signals.extend(type_signals)
        if type_insufficient:
            insufficient_dims.append(PreferenceDimension.OPPORTUNITY_TYPE)

        # B. KEYWORDS
        kw_signals, kw_insufficient = cls._evaluate_keywords(
            profile_id, opportunity, structured_prefs
        )
        signals.extend(kw_signals)
        if kw_insufficient:
            insufficient_dims.append(PreferenceDimension.KEYWORD)

        # C. RESEARCH DOMAINS & TOPICS
        domain_signals, domain_insufficient = cls._evaluate_domains_and_topics(
            profile_id, opportunity, structured_prefs
        )
        signals.extend(domain_signals)
        if domain_insufficient:
            insufficient_dims.append(PreferenceDimension.RESEARCH_DOMAIN)

        # D. GEOGRAPHY (COUNTRY & REGION)
        geo_signals, geo_insufficient = cls._evaluate_geography(
            profile_id, opportunity, structured_prefs
        )
        signals.extend(geo_signals)
        if geo_insufficient:
            insufficient_dims.append(PreferenceDimension.COUNTRY)

        # E. INSTITUTION
        inst_signals, inst_insufficient = cls._evaluate_institution(
            profile_id, opportunity, structured_prefs
        )
        signals.extend(inst_signals)
        if inst_insufficient:
            insufficient_dims.append(PreferenceDimension.INSTITUTION)

        # F. FUNDING
        funding_signals, funding_insufficient = cls._evaluate_funding(
            profile_id, opportunity, structured_prefs
        )
        signals.extend(funding_signals)
        if funding_insufficient:
            insufficient_dims.append(PreferenceDimension.FUNDING)

        # G. ACADEMIC LEVEL & CAREER STAGE
        academic_signals, academic_insufficient = cls._evaluate_academic_and_career(
            profile_id, opportunity, structured_prefs
        )
        signals.extend(academic_signals)
        if academic_insufficient:
            insufficient_dims.append(PreferenceDimension.ACADEMIC_LEVEL)

        # 3. Categorize signals by match type & polarity
        positive_matches = [s for s in signals if s.match_type == PreferenceMatchType.PREFERRED_MATCH]
        excluded_matches = [s for s in signals if s.match_type == PreferenceMatchType.EXCLUDED_MATCH]
        conflicts = [s for s in signals if s.match_type == PreferenceMatchType.CONFLICT]
        neutral_signals = [s for s in signals if s.match_type == PreferenceMatchType.NEUTRAL]

        # Record neutral dimensions
        evaluated_dims = {s.dimension for s in signals}
        all_dims = set(PreferenceDimension)
        for dim in all_dims:
            if dim not in evaluated_dims and dim not in insufficient_dims:
                neutral_dims.append(dim)
        for s in neutral_signals:
            if s.dimension not in neutral_dims:
                neutral_dims.append(s.dimension)

        # 4. Synthesize Overall Match State
        overall_state = cls._synthesize_overall_state(
            positive_matches=positive_matches,
            excluded_matches=excluded_matches,
            conflicts=conflicts,
            insufficient_dims=insufficient_dims,
            total_preferences_configured=cls._count_total_preferences(structured_prefs),
        )

        # 5. Calculate Evidence Coverage
        total_eval_dims = len(evaluated_dims) + len(insufficient_dims)
        evidence_coverage = 1.0
        if total_eval_dims > 0:
            evidence_coverage = round(
                (total_eval_dims - len(insufficient_dims)) / total_eval_dims, 2
            )

        # 6. Generate Deterministic Explanation
        explanation = cls._generate_deterministic_explanation(
            overall_state=overall_state,
            positive_matches=positive_matches,
            excluded_matches=excluded_matches,
            conflicts=conflicts,
            insufficient_dims=insufficient_dims,
        )

        return PreferencePersonalizationAssessment(
            profile_id=profile_id,
            opportunity_id=opportunity.id,
            overall_match_state=overall_state,
            positive_matches_count=len(positive_matches),
            excluded_matches_count=len(excluded_matches),
            conflict_count=len(conflicts),
            neutral_dimensions_count=len(neutral_dims),
            insufficient_evidence_count=len(insufficient_dims),
            total_evaluated_preferences=len(signals),
            evidence_coverage=evidence_coverage,
            deterministic_explanation=explanation,
            dimension_signals=signals,
            positive_matches=positive_matches,
            excluded_matches=excluded_matches,
            conflicts=conflicts,
            insufficient_evidence_dimensions=insufficient_dims,
            neutral_dimensions=neutral_dims,
            computed_at=datetime.now(timezone.utc),
        )

    @classmethod
    def evaluate_opportunities_batch(
        cls,
        profile_id: uuid.UUID,
        preferences: Sequence[ResearcherPreferenceItemSchema | ResearcherPreferenceModel] | StructuredPreferencesResponseSchema,
        opportunities: Sequence[OpportunityModel],
    ) -> dict[uuid.UUID, PreferencePersonalizationAssessment]:
        """
        Evaluate a batch of opportunities in memory against researcher preferences with zero N+1 queries.
        """
        # Normalize preferences once for all opportunities
        structured_prefs = cls._normalize_to_structured(preferences, profile_id)
        results: dict[uuid.UUID, PreferencePersonalizationAssessment] = {}

        for opp in opportunities:
            results[opp.id] = cls.evaluate_opportunity(
                profile_id=profile_id,
                preferences=structured_prefs,
                opportunity=opp,
            )

        return results

    # -------------------------------------------------------------------------
    # Dimension Evaluators
    # -------------------------------------------------------------------------

    @classmethod
    def _evaluate_opportunity_type(
        cls,
        profile_id: uuid.UUID,
        opportunity: OpportunityModel,
        prefs: StructuredPreferencesResponseSchema,
    ) -> tuple[list[PreferenceMatchSignal], bool]:
        signals: list[PreferenceMatchSignal] = []

        preferred_types = set(prefs.opportunities.preferred_types)
        excluded_types = set(prefs.opportunities.excluded_types)

        if not preferred_types and not excluded_types:
            return signals, False

        opp_type_raw = opportunity.opportunity_type
        if not opp_type_raw:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.OPPORTUNITY_TYPE,
                    preference_value=", ".join(preferred_types | excluded_types),
                    preference_type="PREFERRED" if preferred_types else "EXCLUDED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.INSUFFICIENT_EVIDENCE,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity has no opportunity_type specified.",
                    explanation="Opportunity type could not be evaluated because it is not specified.",
                    confidence=0.0,
                )
            )
            return signals, True

        # Normalize opportunity type
        norm_opp_type = opp_type_raw.upper().replace("-", "_")
        if norm_opp_type in CANONICAL_OPPORTUNITY_TYPES:
            norm_opp_type = CANONICAL_OPPORTUNITY_TYPES[norm_opp_type][0]

        is_preferred = norm_opp_type in preferred_types
        is_excluded = norm_opp_type in excluded_types

        if is_preferred and is_excluded:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.OPPORTUNITY_TYPE,
                    preference_value=norm_opp_type,
                    preference_type="CONFLICT",
                    opportunity_value=norm_opp_type,
                    match_type=PreferenceMatchType.CONFLICT,
                    polarity=SignalPolarity.UNRESOLVED,
                    evidence=f"Opportunity type '{norm_opp_type}' is configured as both preferred and excluded.",
                    explanation=f"Preference conflict: opportunity type '{norm_opp_type}' is both preferred and excluded.",
                    confidence=1.0,
                )
            )
        elif is_excluded:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.OPPORTUNITY_TYPE,
                    preference_value=norm_opp_type,
                    preference_type="EXCLUDED",
                    opportunity_value=norm_opp_type,
                    match_type=PreferenceMatchType.EXCLUDED_MATCH,
                    polarity=SignalPolarity.NEGATIVE,
                    evidence=f"Opportunity type '{norm_opp_type}' matches explicit exclusion.",
                    explanation=f"Matches your excluded opportunity type: {norm_opp_type}.",
                    confidence=1.0,
                )
            )
        elif is_preferred:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.OPPORTUNITY_TYPE,
                    preference_value=norm_opp_type,
                    preference_type="PREFERRED",
                    opportunity_value=norm_opp_type,
                    match_type=PreferenceMatchType.PREFERRED_MATCH,
                    polarity=SignalPolarity.POSITIVE,
                    evidence=f"Opportunity type '{norm_opp_type}' matches preferred type.",
                    explanation=f"Matches your preferred opportunity type: {norm_opp_type}.",
                    confidence=1.0,
                )
            )
        else:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.OPPORTUNITY_TYPE,
                    preference_value=", ".join(preferred_types),
                    preference_type="PREFERRED",
                    opportunity_value=norm_opp_type,
                    match_type=PreferenceMatchType.NEUTRAL,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence=f"Opportunity type '{norm_opp_type}' is neither preferred nor excluded.",
                    explanation=f"Opportunity type '{norm_opp_type}' is neutral relative to your preferences.",
                    confidence=1.0,
                )
            )

        return signals, False

    @classmethod
    def _evaluate_keywords(
        cls,
        profile_id: uuid.UUID,
        opportunity: OpportunityModel,
        prefs: StructuredPreferencesResponseSchema,
    ) -> tuple[list[PreferenceMatchSignal], bool]:
        signals: list[PreferenceMatchSignal] = []

        preferred_kws = [kw.lower().strip() for kw in prefs.interests.keywords if kw.strip()]
        excluded_kws = [kw.lower().strip() for kw in prefs.exclusions.excluded_topics if kw.strip()]

        if not preferred_kws and not excluded_kws:
            return signals, False

        # Extract textual corpus from opportunity
        opp_tokens = set()
        opp_phrases = []

        if opportunity.title:
            clean_title = opportunity.title.lower()
            opp_phrases.append(clean_title)
            opp_tokens.update(re.findall(r"\b\w+\b", clean_title))

        if opportunity.summary:
            clean_sum = opportunity.summary.lower()
            opp_phrases.append(clean_sum)
            opp_tokens.update(re.findall(r"\b\w+\b", clean_sum))

        # Extract topics attached to opportunity
        if hasattr(opportunity, "topic_associations") and opportunity.topic_associations:
            for ta in opportunity.topic_associations:
                if ta.topic:
                    t_name = ta.topic.name.lower()
                    opp_phrases.append(t_name)
                    opp_tokens.update(re.findall(r"\b\w+\b", t_name))
                    if ta.topic.slug:
                        opp_phrases.append(ta.topic.slug.lower().replace("-", " "))

        if not opp_phrases:
            # Opportunity has no textual content or topics
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.KEYWORD,
                    preference_value=", ".join(set(preferred_kws) | set(excluded_kws)),
                    preference_type="PREFERRED" if preferred_kws else "EXCLUDED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.INSUFFICIENT_EVIDENCE,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity has no title, summary, or topics for keyword matching.",
                    explanation="Keywords could not be evaluated because opportunity content is unavailable.",
                    confidence=0.0,
                )
            )
            return signals, True

        # Helper to check if a keyword matches opportunity text
        def matches_keyword(kw: str) -> bool:
            if " " in kw:
                return any(kw in p for p in opp_phrases)
            return kw in opp_tokens or any(kw in p for p in opp_phrases)

        # Check preferred keywords
        matched_preferred = [kw for kw in preferred_kws if matches_keyword(kw)]
        # Check excluded keywords
        matched_excluded = [kw for kw in excluded_kws if matches_keyword(kw)]

        # Determine conflict vs preferred vs excluded
        if matched_preferred and matched_excluded:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.KEYWORD,
                    preference_value=f"Preferred: {', '.join(matched_preferred)} | Excluded: {', '.join(matched_excluded)}",
                    preference_type="CONFLICT",
                    opportunity_value=", ".join(matched_preferred + matched_excluded),
                    match_type=PreferenceMatchType.CONFLICT,
                    polarity=SignalPolarity.UNRESOLVED,
                    evidence=f"Opportunity matches preferred keyword(s) {matched_preferred} but also excluded keyword(s) {matched_excluded}.",
                    explanation=f"Preference conflict: matches preferred keyword(s) '{', '.join(matched_preferred)}' but conflicts with excluded keyword(s) '{', '.join(matched_excluded)}'.",
                    confidence=1.0,
                )
            )
        elif matched_excluded:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.KEYWORD,
                    preference_value=", ".join(matched_excluded),
                    preference_type="EXCLUDED",
                    opportunity_value=", ".join(matched_excluded),
                    match_type=PreferenceMatchType.EXCLUDED_MATCH,
                    polarity=SignalPolarity.NEGATIVE,
                    evidence=f"Opportunity contains excluded keyword(s): {', '.join(matched_excluded)}.",
                    explanation=f"Matches your excluded keyword(s): {', '.join(matched_excluded)}.",
                    confidence=1.0,
                )
            )
        elif matched_preferred:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.KEYWORD,
                    preference_value=", ".join(matched_preferred),
                    preference_type="PREFERRED",
                    opportunity_value=", ".join(matched_preferred),
                    match_type=PreferenceMatchType.PREFERRED_MATCH,
                    polarity=SignalPolarity.POSITIVE,
                    evidence=f"Opportunity matches preferred keyword(s): {', '.join(matched_preferred)}.",
                    explanation=f"Matches your preferred keyword(s): {', '.join(matched_preferred)}.",
                    confidence=1.0,
                )
            )
        else:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.KEYWORD,
                    preference_value=", ".join(preferred_kws),
                    preference_type="PREFERRED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.NEUTRAL,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="No preferred or excluded keywords were found in opportunity content.",
                    explanation="No explicit keyword matches found.",
                    confidence=1.0,
                )
            )

        return signals, False

    @classmethod
    def _evaluate_domains_and_topics(
        cls,
        profile_id: uuid.UUID,
        opportunity: OpportunityModel,
        prefs: StructuredPreferencesResponseSchema,
    ) -> tuple[list[PreferenceMatchSignal], bool]:
        signals: list[PreferenceMatchSignal] = []

        preferred_domains = [d.lower().strip() for d in prefs.interests.research_domains if d.strip()]
        preferred_topics = [t.lower().strip() for t in prefs.interests.topics if t.strip()]
        excluded_topics = [t.lower().strip() for t in prefs.exclusions.excluded_topics if t.strip()]

        if not preferred_domains and not preferred_topics and not excluded_topics:
            return signals, False

        # Gather opportunity topics
        opp_topics: list[str] = []
        if hasattr(opportunity, "topic_associations") and opportunity.topic_associations:
            for ta in opportunity.topic_associations:
                if ta.topic and ta.topic.name:
                    opp_topics.append(ta.topic.name.lower().strip())
                    if ta.topic.slug:
                        opp_topics.append(ta.topic.slug.lower().replace("-", " "))

        if not opp_topics:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.RESEARCH_DOMAIN,
                    preference_value=", ".join(preferred_domains + preferred_topics + excluded_topics),
                    preference_type="PREFERRED" if (preferred_domains or preferred_topics) else "EXCLUDED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.INSUFFICIENT_EVIDENCE,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity has no linked canonical topics or domains.",
                    explanation="Research domain could not be evaluated because opportunity has no topics attached.",
                    confidence=0.0,
                )
            )
            return signals, True

        matched_pref_domains = [
            d for d in preferred_domains if any(d in ot or ot in d for ot in opp_topics)
        ]
        matched_pref_topics = [
            t for t in preferred_topics if any(t == ot or t in ot for ot in opp_topics)
        ]
        matched_excl_topics = [
            t for t in excluded_topics if any(t == ot or t in ot for ot in opp_topics)
        ]

        all_positive = matched_pref_domains + matched_pref_topics

        if all_positive and matched_excl_topics:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.RESEARCH_DOMAIN,
                    preference_value=f"Preferred: {', '.join(all_positive)} | Excluded: {', '.join(matched_excl_topics)}",
                    preference_type="CONFLICT",
                    opportunity_value=", ".join(opp_topics),
                    match_type=PreferenceMatchType.CONFLICT,
                    polarity=SignalPolarity.UNRESOLVED,
                    evidence=f"Opportunity topics match preferred {all_positive} but also excluded {matched_excl_topics}.",
                    explanation=f"Preference conflict: matches preferred topic(s) '{', '.join(all_positive)}' but conflicts with excluded '{', '.join(matched_excl_topics)}'.",
                    confidence=1.0,
                )
            )
        elif matched_excl_topics:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.RESEARCH_DOMAIN,
                    preference_value=", ".join(matched_excl_topics),
                    preference_type="EXCLUDED",
                    opportunity_value=", ".join(matched_excl_topics),
                    match_type=PreferenceMatchType.EXCLUDED_MATCH,
                    polarity=SignalPolarity.NEGATIVE,
                    evidence=f"Opportunity topic(s) match excluded topic: {', '.join(matched_excl_topics)}.",
                    explanation=f"Matches your excluded topic: {', '.join(matched_excl_topics)}.",
                    confidence=1.0,
                )
            )
        elif all_positive:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.RESEARCH_DOMAIN,
                    preference_value=", ".join(all_positive),
                    preference_type="PREFERRED",
                    opportunity_value=", ".join(all_positive),
                    match_type=PreferenceMatchType.PREFERRED_MATCH,
                    polarity=SignalPolarity.POSITIVE,
                    evidence=f"Opportunity topic(s) match preferred: {', '.join(all_positive)}.",
                    explanation=f"Matches your preferred research domain/topic: {', '.join(all_positive)}.",
                    confidence=1.0,
                )
            )
        else:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.RESEARCH_DOMAIN,
                    preference_value=", ".join(preferred_domains + preferred_topics),
                    preference_type="PREFERRED",
                    opportunity_value=", ".join(opp_topics),
                    match_type=PreferenceMatchType.NEUTRAL,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity topics do not match explicit preferred or excluded domains.",
                    explanation="No explicit research domain match found.",
                    confidence=1.0,
                )
            )

        return signals, False

    @classmethod
    def _evaluate_geography(
        cls,
        profile_id: uuid.UUID,
        opportunity: OpportunityModel,
        prefs: StructuredPreferencesResponseSchema,
    ) -> tuple[list[PreferenceMatchSignal], bool]:
        signals: list[PreferenceMatchSignal] = []

        preferred_countries = [c.upper().strip() for c in prefs.geography.preferred_countries if c.strip()]
        excluded_countries = [c.upper().strip() for c in prefs.geography.excluded_countries if c.strip()]
        preferred_regions = [r.upper().strip() for r in prefs.geography.preferred_regions if r.strip()]
        excluded_regions = [r.upper().strip() for r in prefs.geography.excluded_regions if r.strip()]

        if not preferred_countries and not excluded_countries and not preferred_regions and not excluded_regions:
            return signals, False

        loc_str = opportunity.location
        if not loc_str or not loc_str.strip():
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.COUNTRY,
                    preference_value=", ".join(set(preferred_countries) | set(excluded_countries)),
                    preference_type="PREFERRED" if preferred_countries else "EXCLUDED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.INSUFFICIENT_EVIDENCE,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity has no location metadata specified.",
                    explanation="Geographic preference could not be evaluated because location information is unavailable.",
                    confidence=0.0,
                )
            )
            return signals, True

        loc_upper = loc_str.upper()

        # Helper to check if country matches location
        def location_contains_country(c_code_or_name: str) -> bool:
            # Check direct string match
            if c_code_or_name in loc_upper:
                return True
            # Check ISO code mapped from name
            mapped = COUNTRY_NAME_TO_CODE.get(c_code_or_name)
            if mapped and (mapped in loc_upper or f", {mapped}" in loc_upper or f" {mapped}" in loc_upper):
                return True
            # Check names mapped to ISO code
            for name, code in COUNTRY_NAME_TO_CODE.items():
                if code == c_code_or_name and name in loc_upper:
                    return True
            return False

        matched_pref_c = [c for c in preferred_countries if location_contains_country(c)]
        matched_excl_c = [c for c in excluded_countries if location_contains_country(c)]
        matched_pref_r = [r for r in preferred_regions if r in loc_upper]
        matched_excl_r = [r for r in excluded_regions if r in loc_upper]

        has_positive = bool(matched_pref_c or matched_pref_r)
        has_negative = bool(matched_excl_c or matched_excl_r)

        if has_positive and has_negative:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.COUNTRY,
                    preference_value=f"Preferred: {', '.join(matched_pref_c + matched_pref_r)} | Excluded: {', '.join(matched_excl_c + matched_excl_r)}",
                    preference_type="CONFLICT",
                    opportunity_value=loc_str,
                    match_type=PreferenceMatchType.CONFLICT,
                    polarity=SignalPolarity.UNRESOLVED,
                    evidence=f"Location '{loc_str}' matches preferred geography but also excluded geography.",
                    explanation=f"Preference conflict: location matches preferred geography '{', '.join(matched_pref_c + matched_pref_r)}' but conflicts with excluded '{', '.join(matched_excl_c + matched_excl_r)}'.",
                    confidence=1.0,
                )
            )
        elif has_negative:
            neg_items = matched_excl_c + matched_excl_r
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.COUNTRY,
                    preference_value=", ".join(neg_items),
                    preference_type="EXCLUDED",
                    opportunity_value=loc_str,
                    match_type=PreferenceMatchType.EXCLUDED_MATCH,
                    polarity=SignalPolarity.NEGATIVE,
                    evidence=f"Location '{loc_str}' matches excluded geography: {', '.join(neg_items)}.",
                    explanation=f"Matches your excluded country/region: {', '.join(neg_items)}.",
                    confidence=1.0,
                )
            )
        elif has_positive:
            pos_items = matched_pref_c + matched_pref_r
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.COUNTRY,
                    preference_value=", ".join(pos_items),
                    preference_type="PREFERRED",
                    opportunity_value=loc_str,
                    match_type=PreferenceMatchType.PREFERRED_MATCH,
                    polarity=SignalPolarity.POSITIVE,
                    evidence=f"Location '{loc_str}' matches preferred geography: {', '.join(pos_items)}.",
                    explanation=f"Matches your preferred country/region: {', '.join(pos_items)}.",
                    confidence=1.0,
                )
            )
        else:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.COUNTRY,
                    preference_value=", ".join(preferred_countries + preferred_regions),
                    preference_type="PREFERRED",
                    opportunity_value=loc_str,
                    match_type=PreferenceMatchType.NEUTRAL,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence=f"Location '{loc_str}' does not match explicit preferred or excluded locations.",
                    explanation=f"Location '{loc_str}' is neutral relative to your geographic preferences.",
                    confidence=1.0,
                )
            )

        return signals, False

    @classmethod
    def _evaluate_institution(
        cls,
        profile_id: uuid.UUID,
        opportunity: OpportunityModel,
        prefs: StructuredPreferencesResponseSchema,
    ) -> tuple[list[PreferenceMatchSignal], bool]:
        signals: list[PreferenceMatchSignal] = []

        preferred_insts = [i.strip() for i in prefs.geography.preferred_institutions if i.strip()]
        excluded_insts = [i.strip() for i in prefs.geography.excluded_institutions if i.strip()]

        if not preferred_insts and not excluded_insts:
            return signals, False

        # Check opportunity publisher / organizer
        opp_inst = opportunity.organizer or opportunity.publisher
        if not opp_inst or not opp_inst.strip():
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.INSTITUTION,
                    preference_value=", ".join(set(preferred_insts) | set(excluded_insts)),
                    preference_type="PREFERRED" if preferred_insts else "EXCLUDED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.INSUFFICIENT_EVIDENCE,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity has no institution, organizer, or publisher specified.",
                    explanation="Institution preference could not be evaluated because institution information is unavailable.",
                    confidence=0.0,
                )
            )
            return signals, True

        opp_inst_lower = opp_inst.lower()

        matched_pref = [i for i in preferred_insts if i.lower() in opp_inst_lower]
        matched_excl = [i for i in excluded_insts if i.lower() in opp_inst_lower]

        if matched_pref and matched_excl:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.INSTITUTION,
                    preference_value=f"Preferred: {', '.join(matched_pref)} | Excluded: {', '.join(matched_excl)}",
                    preference_type="CONFLICT",
                    opportunity_value=opp_inst,
                    match_type=PreferenceMatchType.CONFLICT,
                    polarity=SignalPolarity.UNRESOLVED,
                    evidence=f"Organizer/publisher '{opp_inst}' matches preferred institution but also excluded institution.",
                    explanation=f"Preference conflict: matches preferred institution '{', '.join(matched_pref)}' but conflicts with excluded '{', '.join(matched_excl)}'.",
                    confidence=0.8,
                    metadata_payload={"match_level": "FALLBACK_STRING"},
                )
            )
        elif matched_excl:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.INSTITUTION,
                    preference_value=", ".join(matched_excl),
                    preference_type="EXCLUDED",
                    opportunity_value=opp_inst,
                    match_type=PreferenceMatchType.EXCLUDED_MATCH,
                    polarity=SignalPolarity.NEGATIVE,
                    evidence=f"Organizer/publisher '{opp_inst}' matches excluded institution: {', '.join(matched_excl)} (fallback string match).",
                    explanation=f"Matches your excluded institution: {', '.join(matched_excl)}.",
                    confidence=0.8,
                    metadata_payload={"match_level": "FALLBACK_STRING"},
                )
            )
        elif matched_pref:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.INSTITUTION,
                    preference_value=", ".join(matched_pref),
                    preference_type="PREFERRED",
                    opportunity_value=opp_inst,
                    match_type=PreferenceMatchType.PREFERRED_MATCH,
                    polarity=SignalPolarity.POSITIVE,
                    evidence=f"Organizer/publisher '{opp_inst}' matches preferred institution: {', '.join(matched_pref)} (fallback string match).",
                    explanation=f"Matches your preferred institution: {', '.join(matched_pref)}.",
                    confidence=0.8,
                    metadata_payload={"match_level": "FALLBACK_STRING"},
                )
            )
        else:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.INSTITUTION,
                    preference_value=", ".join(preferred_insts),
                    preference_type="PREFERRED",
                    opportunity_value=opp_inst,
                    match_type=PreferenceMatchType.NEUTRAL,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence=f"Organizer/publisher '{opp_inst}' does not match explicit institution preferences.",
                    explanation="No explicit institution match found.",
                    confidence=1.0,
                )
            )

        return signals, False

    @classmethod
    def _evaluate_funding(
        cls,
        profile_id: uuid.UUID,
        opportunity: OpportunityModel,
        prefs: StructuredPreferencesResponseSchema,
    ) -> tuple[list[PreferenceMatchSignal], bool]:
        signals: list[PreferenceMatchSignal] = []

        funding_required = prefs.funding.funding_required
        min_amount = prefs.funding.min_funding_amount
        max_amount = prefs.funding.max_funding_amount

        if funding_required is None and min_amount is None and max_amount is None:
            return signals, False

        fee_or_funding = opportunity.apc_or_fee
        if fee_or_funding is None:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.FUNDING,
                    preference_value="Funding configured",
                    preference_type="PREFERRED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.INSUFFICIENT_EVIDENCE,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity has no apc_or_fee or funding metadata specified.",
                    explanation="Funding preference could not be evaluated because funding information is unavailable.",
                    confidence=0.0,
                )
            )
            return signals, True

        # Check funding fields
        has_funding = fee_or_funding.get("has_funding", False)
        funding_amt = fee_or_funding.get("funding_amount") or fee_or_funding.get("amount")

        if funding_required:
            if not has_funding and not funding_amt:
                signals.append(
                    PreferenceMatchSignal(
                        profile_id=profile_id,
                        opportunity_id=opportunity.id,
                        dimension=PreferenceDimension.FUNDING,
                        preference_value="Funding Required",
                        preference_type="PREFERRED",
                        opportunity_value="Unfunded / Fee only",
                        match_type=PreferenceMatchType.PARTIAL_MATCH,
                        polarity=SignalPolarity.NEGATIVE,
                        evidence="Opportunity does not provide funding as required by preference.",
                        explanation="Opportunity does not meet your explicit requirement for funding.",
                        confidence=1.0,
                    )
                )
                return signals, False

            # Opportunity provides funding
            if min_amount is not None and funding_amt is not None:
                try:
                    amt = float(funding_amt)
                    if amt >= min_amount:
                        signals.append(
                            PreferenceMatchSignal(
                                profile_id=profile_id,
                                opportunity_id=opportunity.id,
                                dimension=PreferenceDimension.FUNDING,
                                preference_value=f"Min Funding: {min_amount}",
                                preference_type="PREFERRED",
                                opportunity_value=f"{amt}",
                                match_type=PreferenceMatchType.PREFERRED_MATCH,
                                polarity=SignalPolarity.POSITIVE,
                                evidence=f"Funding amount {amt} meets or exceeds preferred minimum {min_amount}.",
                                explanation=f"Funding satisfies your minimum threshold of {min_amount}.",
                                confidence=1.0,
                            )
                        )
                    else:
                        signals.append(
                            PreferenceMatchSignal(
                                profile_id=profile_id,
                                opportunity_id=opportunity.id,
                                dimension=PreferenceDimension.FUNDING,
                                preference_value=f"Min Funding: {min_amount}",
                                preference_type="PREFERRED",
                                opportunity_value=f"{amt}",
                                match_type=PreferenceMatchType.PARTIAL_MATCH,
                                polarity=SignalPolarity.NEGATIVE,
                                evidence=f"Funding amount {amt} is below preferred minimum {min_amount}.",
                                explanation=f"Funding amount of {amt} is below your preferred minimum of {min_amount}.",
                                confidence=1.0,
                            )
                        )
                except (ValueError, TypeError):
                    signals.append(
                        PreferenceMatchSignal(
                            profile_id=profile_id,
                            opportunity_id=opportunity.id,
                            dimension=PreferenceDimension.FUNDING,
                            preference_value="Funding Required",
                            preference_type="PREFERRED",
                            opportunity_value="Funded",
                            match_type=PreferenceMatchType.PREFERRED_MATCH,
                            polarity=SignalPolarity.POSITIVE,
                            evidence="Opportunity provides funding as required by preference.",
                            explanation="Opportunity is funded as preferred.",
                            confidence=0.8,
                        )
                    )
            else:
                signals.append(
                    PreferenceMatchSignal(
                        profile_id=profile_id,
                        opportunity_id=opportunity.id,
                        dimension=PreferenceDimension.FUNDING,
                        preference_value="Funding Required",
                        preference_type="PREFERRED",
                        opportunity_value="Funded",
                        match_type=PreferenceMatchType.PREFERRED_MATCH,
                        polarity=SignalPolarity.POSITIVE,
                        evidence="Opportunity provides funding as required by preference.",
                        explanation="Opportunity is funded as preferred.",
                        confidence=1.0,
                    )
                )

        return signals, False

    @classmethod
    def _evaluate_academic_and_career(
        cls,
        profile_id: uuid.UUID,
        opportunity: OpportunityModel,
        prefs: StructuredPreferencesResponseSchema,
    ) -> tuple[list[PreferenceMatchSignal], bool]:
        signals: list[PreferenceMatchSignal] = []

        academic_level = prefs.academic.academic_level
        career_stage = prefs.academic.career_stage

        if not academic_level and not career_stage:
            return signals, False

        # In OpportunityModel, academic eligibility is not stored as a top-level column,
        # but may reside in apc_or_fee or other structured metadata if ingested.
        metadata = opportunity.apc_or_fee or {}
        eligibility = metadata.get("eligibility") or metadata.get("target_academic_level")

        if not eligibility:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.ACADEMIC_LEVEL,
                    preference_value=f"{academic_level or ''} {career_stage or ''}".strip(),
                    preference_type="PREFERRED",
                    opportunity_value=None,
                    match_type=PreferenceMatchType.INSUFFICIENT_EVIDENCE,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence="Opportunity has no structured eligibility requirements specified.",
                    explanation="Academic eligibility could not be evaluated because structured eligibility information is unavailable.",
                    confidence=0.0,
                )
            )
            return signals, True

        elig_str = str(eligibility).upper()
        matched = False
        if academic_level and academic_level.upper() in elig_str:
            matched = True
        if career_stage and career_stage.upper() in elig_str:
            matched = True

        if matched:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.ACADEMIC_LEVEL,
                    preference_value=f"{academic_level or ''} {career_stage or ''}".strip(),
                    preference_type="PREFERRED",
                    opportunity_value=elig_str,
                    match_type=PreferenceMatchType.PREFERRED_MATCH,
                    polarity=SignalPolarity.POSITIVE,
                    evidence=f"Opportunity eligibility '{elig_str}' matches academic level/career stage.",
                    explanation=f"Matches your academic level/career stage: {academic_level or career_stage}.",
                    confidence=1.0,
                )
            )
        else:
            signals.append(
                PreferenceMatchSignal(
                    profile_id=profile_id,
                    opportunity_id=opportunity.id,
                    dimension=PreferenceDimension.ACADEMIC_LEVEL,
                    preference_value=f"{academic_level or ''} {career_stage or ''}".strip(),
                    preference_type="PREFERRED",
                    opportunity_value=elig_str,
                    match_type=PreferenceMatchType.NEUTRAL,
                    polarity=SignalPolarity.NEUTRAL,
                    evidence=f"Opportunity eligibility '{elig_str}' is neutral relative to preference.",
                    explanation="No explicit academic eligibility conflict or match.",
                    confidence=1.0,
                )
            )

        return signals, False

    # -------------------------------------------------------------------------
    # Overall State & Explanation Synthesis
    # -------------------------------------------------------------------------

    @classmethod
    def _synthesize_overall_state(
        cls,
        positive_matches: list[PreferenceMatchSignal],
        excluded_matches: list[PreferenceMatchSignal],
        conflicts: list[PreferenceMatchSignal],
        insufficient_dims: list[PreferenceDimension],
        total_preferences_configured: int,
    ) -> PreferenceMatchType:
        """
        Synthesize aggregate match state following deterministic hierarchy:
          1. CONFLICT if any conflict exists or if positive matches intersect with excluded matches.
          2. EXCLUDED_MATCH if any explicit exclusion matches without positive matches.
          3. PREFERRED_MATCH if positive matches exist and zero exclusions.
          4. INSUFFICIENT_EVIDENCE if preferences were configured but all lacked opportunity data.
          5. NEUTRAL if no preferences configured or opportunity was neutral across all dimensions.
        """
        if total_preferences_configured == 0:
            return PreferenceMatchType.NEUTRAL

        if conflicts:
            return PreferenceMatchType.CONFLICT

        if positive_matches and excluded_matches:
            return PreferenceMatchType.CONFLICT

        if excluded_matches:
            return PreferenceMatchType.EXCLUDED_MATCH

        if positive_matches:
            return PreferenceMatchType.PREFERRED_MATCH

        # If we had preferences configured, but all evaluated dimensions had insufficient evidence
        if insufficient_dims and not positive_matches and not excluded_matches:
            return PreferenceMatchType.INSUFFICIENT_EVIDENCE

        return PreferenceMatchType.NEUTRAL

    @classmethod
    def _generate_deterministic_explanation(
        cls,
        overall_state: PreferenceMatchType,
        positive_matches: list[PreferenceMatchSignal],
        excluded_matches: list[PreferenceMatchSignal],
        conflicts: list[PreferenceMatchSignal],
        insufficient_dims: list[PreferenceDimension],
    ) -> str:
        """
        Produce a clear, deterministic explanation based strictly on observed signals.
        """
        if overall_state == PreferenceMatchType.CONFLICT:
            conflict_details = [c.explanation for c in conflicts]
            if not conflict_details:
                conflict_details = [
                    f"Matches preferred {s.dimension.value.lower()}: '{s.preference_value}' but conflicts with excluded {e.dimension.value.lower()}: '{e.preference_value}'"
                    for s in positive_matches
                    for e in excluded_matches
                ]
            return f"Preference conflict detected: {'; '.join(conflict_details[:2])}."

        if overall_state == PreferenceMatchType.EXCLUDED_MATCH:
            reasons = [s.explanation for s in excluded_matches]
            return f"Excluded by your preferences: {'; '.join(reasons)}."

        if overall_state == PreferenceMatchType.PREFERRED_MATCH:
            reasons = [s.explanation for s in positive_matches]
            return f"Matches your explicit preferences: {'; '.join(reasons)}."

        if overall_state == PreferenceMatchType.INSUFFICIENT_EVIDENCE:
            missing = [d.value.replace("_", " ").lower() for d in insufficient_dims]
            return f"Preferences could not be evaluated due to missing opportunity data ({', '.join(missing)})."

        return "This opportunity is neutral relative to your configured preferences."

    # -------------------------------------------------------------------------
    # Helper Utilities
    # -------------------------------------------------------------------------

    @classmethod
    def _normalize_to_structured(
        cls,
        preferences: Sequence[ResearcherPreferenceItemSchema | ResearcherPreferenceModel] | StructuredPreferencesResponseSchema,
        profile_id: uuid.UUID,
    ) -> StructuredPreferencesResponseSchema:
        if isinstance(preferences, StructuredPreferencesResponseSchema):
            return preferences

        # Convert Sequence[Preference] to StructuredPreferencesResponseSchema
        return ResearcherPreferenceService.build_structured_from_items(
            profile_id=profile_id,
            user_id=profile_id,
            items=preferences,
        )

    @classmethod
    def _count_total_preferences(cls, prefs: StructuredPreferencesResponseSchema) -> int:
        count = 0
        count += len(prefs.interests.research_domains)
        count += len(prefs.interests.topics)
        count += len(prefs.interests.keywords)
        count += len(prefs.opportunities.preferred_types)
        count += len(prefs.opportunities.excluded_types)
        count += len(prefs.opportunities.delivery_modes)
        count += len(prefs.geography.preferred_countries)
        count += len(prefs.geography.excluded_countries)
        count += len(prefs.geography.preferred_regions)
        count += len(prefs.geography.excluded_regions)
        count += len(prefs.geography.preferred_institutions)
        count += len(prefs.geography.excluded_institutions)
        if prefs.funding.funding_required is not None or prefs.funding.min_funding_amount is not None:
            count += 1
        if prefs.academic.academic_level or prefs.academic.career_stage:
            count += 1
        return count
