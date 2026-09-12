"""
Phase 3.5 — Personalization Ranking Layer Engine.

Implements a deterministic, bounded personalization layer over Phase 2 recommendation ranking.
Preserves Phase 2 base relevance dominance, Phase 2.6 trust/risk gates, and Phase 2.7 deadline lifecycle.

Mathematical Guarantees:
  - Personalization adjustment is strictly bounded: MAX_PERSONALIZATION_CONTRIBUTION <= 0.15.
  - Relevance dominance: Base score gaps > 0.15 can NEVER be inverted by personalization.
  - Relevance damping: Weak candidates (base < 0.50) have their personalization contribution damped
    proportionately, preventing manufacture of relevance for irrelevant opportunities.
  - Safety dominance: High-risk and predatory opportunities receive zero personalization boost
    and retain full Phase 2.6 risk penalties and classifications.
  - Deadline dominance: Expired opportunities remain excluded; upcoming deadlines prioritized.
  - Multi-key deterministic tie-breaking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Sequence 
import uuid

from app.ranking.feedback_config import (
    MAX_NEGATIVE_BEHAVIORAL_ADJUSTMENT,
    MAX_POSITIVE_BEHAVIORAL_ADJUSTMENT,
)
from app.ranking.signals import validate_signal
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceType,
    PersonalizedCandidateItemSchema,
    PersonalizedCandidateOpportunitySchema,
)
from app.schemas.personalized_ranking import (
    MatchedPersonalizationSignalsSchema,
    PersonalizationScoreBreakdownSchema,
    PersonalizedRankedCandidateSchema,
)

logger = logging.getLogger(__name__)


# ── Constants & Configuration ─────────────────────────────────────────────────

# Conservative maximum personalization contribution (strictly capped at 15%)
MAX_PERSONALIZATION_CONTRIBUTION = 0.15

# Personalization Signal Hierarchy Weights (Sum = 1.00)
# Explicit preference > Verified inferred preference > Research expertise > Profile signal > Provenance
EXPLICIT_PREFERENCE_WEIGHT = 0.40
INFERRED_PREFERENCE_WEIGHT = 0.15
EXPERTISE_MATCH_WEIGHT = 0.25
PROFILE_MATCH_WEIGHT = 0.10
PROVENANCE_WEIGHT = 0.10

# Expertise Classification Multipliers
EXPERTISE_MULTIPLIERS: dict[str, float] = {
    "PRIMARY_EXPERTISE": 1.00,
    "SECONDARY_EXPERTISE": 0.75,
    "EMERGING_INTEREST": 0.50,
    "PAST_EXPERTISE": 0.30,
}

# Relevance floor for damping (candidates below 0.50 base relevance are damped)
RELEVANCE_DAMPING_THRESHOLD = 0.50
MIN_RELEVANCE_DAMPING = 0.10


# ── Researcher Personalization Context Container ──────────────────────────────


@dataclass(frozen=True)
class ResearcherPersonalizationContext:
    """
    Immutable context container aggregating researcher signals from Phases 3.1–3.3.
    """

    profile_id: uuid.UUID
    # Active preferences
    explicit_preferences: tuple[Any, ...] = ()
    inferred_preferences: tuple[Any, ...] = ()
    # Scholarly expertise (ResearcherInterestModel items)
    expertise_items: tuple[Any, ...] = ()
    # Profile attributes
    profile_keywords: tuple[str, ...] = ()
    target_opportunity_types: tuple[str, ...] = ()
    institution: str | None = None
    academic_status: str | None = None
    # Phase 3.6 Behavioral feedback signals & negative suppression
    behavioral_signals: tuple[Any, ...] = ()
    suppressed_opportunity_ids: frozenset[uuid.UUID] = frozenset()
    # Cold start status
    is_cold_start: bool = False


# ── Internal Candidate Scoring Intermediate Container ─────────────────────────


@dataclass
class _ScoredPersonalizedCandidate:
    """Internal container for scoring and sorting before final schema generation."""

    opportunity_id: uuid.UUID
    base_rank: int
    base_relevance_score: float
    personalization_score: float
    personalization_adjustment: float
    final_score: float
    urgency_score: float
    breakdown: PersonalizationScoreBreakdownSchema
    matched_signals: MatchedPersonalizationSignalsSchema
    provenance: CandidateProvenanceSchema
    opportunity: PersonalizedCandidateOpportunitySchema
    candidate_item: Any | None = None


# ── Personalization Ranker Engine ─────────────────────────────────────────────


class PersonalizationRanker:
    """
    Deterministic Personalization Ranking Engine (Phase 3.5).

    Ranks candidate opportunities by combining Phase 2 base relevance scores
    with bounded, explainable personalization adjustments.
    """

    def __init__(
        self,
        max_contribution: float = MAX_PERSONALIZATION_CONTRIBUTION,
        explicit_weight: float = EXPLICIT_PREFERENCE_WEIGHT,
        inferred_weight: float = INFERRED_PREFERENCE_WEIGHT,
        expertise_weight: float = EXPERTISE_MATCH_WEIGHT,
        profile_weight: float = PROFILE_MATCH_WEIGHT,
        provenance_weight: float = PROVENANCE_WEIGHT,
    ) -> None:
        if max_contribution > 0.15:
            raise ValueError(
                f"max_contribution cannot exceed 0.15 per Phase 3.5 architecture, got {max_contribution}"
            )
        self.max_contribution = max_contribution
        self.explicit_weight = explicit_weight
        self.inferred_weight = inferred_weight
        self.expertise_weight = expertise_weight
        self.profile_weight = profile_weight
        self.provenance_weight = provenance_weight

    @staticmethod
    def calculate_relevance_damping(base_score: float) -> float:
        """
        Calculate continuous damping factor for low-relevance candidates.

        Guarantees that candidates with low base relevance cannot have relevance
        artificially manufactured via personalization.
        """
        if base_score >= RELEVANCE_DAMPING_THRESHOLD:
            return 1.0
        # Linear decay from 1.0 at threshold down to MIN_RELEVANCE_DAMPING at 0.0
        ratio = max(0.0, base_score) / RELEVANCE_DAMPING_THRESHOLD
        return round(
            MIN_RELEVANCE_DAMPING + (1.0 - MIN_RELEVANCE_DAMPING) * ratio, 6
        )

    def evaluate_personalization_signals(
        self,
        opp: PersonalizedCandidateOpportunitySchema,
        provenance: CandidateProvenanceSchema | None,
        context: ResearcherPersonalizationContext,
    ) -> tuple[
        float,
        PersonalizationScoreBreakdownSchema,
        MatchedPersonalizationSignalsSchema,
    ]:
        """
        Deterministically evaluate researcher personalization signals against candidate opportunity.

        Returns
        -------
        tuple:
          - raw_personalization_score: float in [0.0, 1.0]
          - breakdown: PersonalizationScoreBreakdownSchema
          - matched_signals: MatchedPersonalizationSignalsSchema
        """
        matched_prefs: list[str] = []
        matched_exp: list[str] = []
        matched_topics: set[str] = set()
        matched_types: set[str] = set()

        opp_topics_lower = {t.lower() for t in opp.topics}
        opp_type_upper = (opp.opportunity_type or "").upper()
        opp_mode_upper = (opp.delivery_mode or "").upper()
        opp_location_lower = (opp.location or "").lower()
        opp_title_lower = (opp.title or "").lower()

        # ── 1. Explicit Preference Matching (Weight: 0.40) ────────────────────
        explicit_score_sum = 0.0
        explicit_matches_count = 0

        for pref in context.explicit_preferences:
            p_cat = getattr(pref, "category", "")
            p_val = getattr(pref, "preference_value", "")
            p_strength = float(getattr(pref, "strength", 1.0) or 1.0)
            p_conf = float(getattr(pref, "confidence", 1.0) or 1.0)
            p_recency = float(getattr(pref, "recency_score", 1.0) or 1.0)
            p_weight = p_strength * p_conf * p_recency

            matched = False
            if p_cat == "OPPORTUNITY_TYPE" and p_val.upper() == opp_type_upper:
                matched = True
                matched_types.add(f"Type: {p_val}")
                matched_prefs.append(f"Explicit Type: {p_val}")
            elif p_cat == "DELIVERY_MODE" and p_val.upper() == opp_mode_upper:
                matched = True
                matched_types.add(f"Mode: {p_val}")
                matched_prefs.append(f"Explicit Mode: {p_val}")
            elif p_cat == "TOPIC":
                val_lower = p_val.lower()
                if val_lower in opp_topics_lower or val_lower in opp_title_lower:
                    matched = True
                    matched_topics.add(p_val)
                    matched_prefs.append(f"Explicit Topic: {p_val}")
            elif p_cat == "LOCATION" and p_val.lower() in opp_location_lower:
                matched = True
                matched_prefs.append(f"Explicit Location: {p_val}")
            elif p_cat == "VENUE" and opp.organizer and p_val.lower() in opp.organizer.lower():
                matched = True
                matched_prefs.append(f"Explicit Venue: {p_val}")

            if matched:
                explicit_score_sum += p_weight
                explicit_matches_count += 1

        explicit_score = (
            min(1.0, explicit_score_sum / max(1, explicit_matches_count))
            if explicit_matches_count > 0
            else 0.0
        )

        # ── 2. Inferred Preference Matching (Weight: 0.15) ────────────────────
        inferred_score_sum = 0.0
        inferred_matches_count = 0

        for pref in context.inferred_preferences:
            p_cat = getattr(pref, "category", "")
            p_val = getattr(pref, "preference_value", "")
            p_conf = float(getattr(pref, "confidence", 0.0) or 0.0)
            # Verified inferred preferences require confidence >= 0.40
            if p_conf < 0.40:
                continue
            p_strength = float(getattr(pref, "strength", 1.0) or 1.0)
            p_recency = float(getattr(pref, "recency_score", 1.0) or 1.0)
            p_weight = p_strength * p_conf * p_recency

            matched = False
            if p_cat == "OPPORTUNITY_TYPE" and p_val.upper() == opp_type_upper:
                matched = True
                matched_types.add(f"Type: {p_val}")
                matched_prefs.append(f"Inferred Type: {p_val}")
            elif p_cat == "DELIVERY_MODE" and p_val.upper() == opp_mode_upper:
                matched = True
                matched_types.add(f"Mode: {p_val}")
                matched_prefs.append(f"Inferred Mode: {p_val}")
            elif p_cat == "TOPIC":
                val_lower = p_val.lower()
                if val_lower in opp_topics_lower or val_lower in opp_title_lower:
                    matched = True
                    matched_topics.add(p_val)
                    matched_prefs.append(f"Inferred Topic: {p_val}")

            if matched:
                inferred_score_sum += p_weight
                inferred_matches_count += 1

        inferred_score = (
            min(1.0, inferred_score_sum / max(1, inferred_matches_count))
            if inferred_matches_count > 0
            else 0.0
        )

        # ── 3. Scholarly Expertise Matching (Weight: 0.25) ────────────────────
        expertise_score_sum = 0.0
        expertise_matches_count = 0

        for item in context.expertise_items:
            t_name = getattr(item, "topic_name", "")
            t_slug = getattr(item, "topic_slug", "")
            classification = getattr(item, "classification", "SECONDARY_EXPERTISE")
            mult = EXPERTISE_MULTIPLIERS.get(classification, 0.50)
            i_strength = float(getattr(item, "interest_strength", 1.0) or 1.0)
            i_conf = float(getattr(item, "confidence", 1.0) or 1.0)
            i_recency = float(getattr(item, "recency_score", 1.0) or 1.0)

            t_name_lower = t_name.lower()
            t_slug_lower = t_slug.lower()

            if (
                t_name_lower in opp_topics_lower
                or t_slug_lower in opp_topics_lower
                or t_name_lower in opp_title_lower
            ):
                expertise_score_sum += mult * i_strength * i_conf * i_recency
                expertise_matches_count += 1
                matched_topics.add(t_name)
                matched_exp.append(f"{t_name} ({classification})")

        expertise_score = (
            min(1.0, expertise_score_sum / max(1, expertise_matches_count))
            if expertise_matches_count > 0
            else 0.0
        )

        # ── 4. Profile Signal Matching (Weight: 0.10) ─────────────────────────
        profile_matches = 0
        total_profile_signals = len(context.profile_keywords) + (
            1 if context.target_opportunity_types else 0
        )

        for kw in context.profile_keywords:
            kw_lower = kw.lower()
            if kw_lower in opp_topics_lower or kw_lower in opp_title_lower:
                profile_matches += 1
                matched_topics.add(kw)

        if opp_type_upper in context.target_opportunity_types:
            profile_matches += 1
            matched_types.add(f"Target Type: {opp_type_upper}")

        profile_score = (
            min(1.0, profile_matches / max(1, total_profile_signals))
            if total_profile_signals > 0
            else 0.0
        )

        # ── 5. Candidate Provenance Confirmation (Weight: 0.10) ───────────────
        provenance_score = 0.0
        if provenance:
            # Candidates discovered through multiple verified channels earn confirmation boost
            valid_sources = [
                s
                for s in provenance.sources
                if s != CandidateSourceType.COLD_START_FALLBACK
            ]
            if len(valid_sources) > 1:
                provenance_score = min(
                    1.0,
                    (len(valid_sources) * 0.35)
                    + (len(provenance.retrieval_channels) * 0.15),
                )
            elif len(valid_sources) == 1:
                provenance_score = 0.20
            else:
                provenance_score = 0.0

            for t in provenance.matched_topics:
                matched_topics.add(t)
            for p in provenance.matched_preferences:
                if p not in matched_prefs:
                    matched_prefs.append(p)
            for e in provenance.matched_expertise:
                if e not in matched_exp:
                    matched_exp.append(e)


        # ── 6. Phase 3.6 Behavioral Feedback Signals ──────────────────────────
        opp_id = getattr(opp, "id", None)
        is_suppressed = bool(opp_id and opp_id in context.suppressed_opportunity_ids)

        behavioral_conf_sum = 0.0
        behavioral_matches_count = 0
        signed_behavioral_adjustment = 0.0

        for sig in context.behavioral_signals:
            s_cat = getattr(sig, "category", "")
            s_val = getattr(sig, "preference_value", "")
            s_conf = float(getattr(sig, "confidence", 0.0) or 0.0)
            s_norm = float(getattr(sig, "normalized_score", 0.0) or 0.0)

            matched = False
            if s_cat == "OPPORTUNITY_TYPE" and s_val.upper() == opp_type_upper:
                matched = True
                matched_prefs.append(f"Behavioral Type: {s_val} ({getattr(sig, 'direction', '')})")
            elif s_cat == "DELIVERY_MODE" and s_val.upper() == opp_mode_upper:
                matched = True
                matched_prefs.append(f"Behavioral Mode: {s_val} ({getattr(sig, 'direction', '')})")
            elif s_cat == "TOPIC":
                val_lower = s_val.lower()
                if val_lower in opp_topics_lower or val_lower in opp_title_lower:
                    matched = True
                    matched_topics.add(s_val)
                    matched_prefs.append(f"Behavioral Topic: {s_val} ({getattr(sig, 'direction', '')})")
            elif s_cat == "LOCATION" and s_val.lower() in opp_location_lower:
                matched = True
                matched_prefs.append(f"Behavioral Location: {s_val} ({getattr(sig, 'direction', '')})")
            elif s_cat == "VENUE" and opp.organizer and s_val.lower() in opp.organizer.lower():
                matched = True
                matched_prefs.append(f"Behavioral Venue: {s_val} ({getattr(sig, 'direction', '')})")

            if matched:
                behavioral_matches_count += 1
                behavioral_conf_sum += s_conf
                signed_behavioral_adjustment += s_norm * s_conf

        if is_suppressed:
            signed_behavioral_adjustment = -MAX_NEGATIVE_BEHAVIORAL_ADJUSTMENT
            avg_conf = 1.0
            behavioral_score = 0.0
            matched_prefs.append("Suppressed: Active negative feedback")
        elif behavioral_matches_count > 0:
            avg_conf = round(behavioral_conf_sum / behavioral_matches_count, 4)
            behavioral_score = max(0.0, min(1.0, (signed_behavioral_adjustment / behavioral_matches_count + 1.0) / 2.0))
            signed_behavioral_adjustment = max(
                -MAX_NEGATIVE_BEHAVIORAL_ADJUSTMENT,
                min(MAX_POSITIVE_BEHAVIORAL_ADJUSTMENT, signed_behavioral_adjustment / behavioral_matches_count * 0.10),
            )
        else:
            avg_conf = 0.0
            behavioral_score = 0.0
            signed_behavioral_adjustment = 0.0

        # ── Weighted Composite Personalization Score ──────────────────────────
        base_p_score = round(
            self.explicit_weight * explicit_score
            + self.inferred_weight * inferred_score
            + self.expertise_weight * expertise_score
            + self.profile_weight * profile_score
            + self.provenance_weight * provenance_score,
            6,
        )

        if is_suppressed:
            raw_personalization_score = 0.0
        else:
            raw_personalization_score = min(1.0, max(0.0, round(base_p_score + signed_behavioral_adjustment, 6)))

        breakdown = PersonalizationScoreBreakdownSchema(
            explicit_preference_score=round(explicit_score, 4),
            inferred_preference_score=round(inferred_score, 4),
            expertise_match_score=round(expertise_score, 4),
            profile_match_score=round(profile_score, 4),
            provenance_score=round(provenance_score, 4),
            behavioral_score=round(behavioral_score, 4),
            behavioral_confidence=round(avg_conf, 4),
            behavioral_adjustment=round(signed_behavioral_adjustment, 4),
            raw_personalization_score=raw_personalization_score,
            relevance_damping=1.0,  # attached during ranking with candidate base score
        )

        matched_signals = MatchedPersonalizationSignalsSchema(
            matched_preferences=sorted(list(set(matched_prefs))),
            matched_expertise=sorted(list(set(matched_exp))),
            matched_topics=sorted(list(matched_topics)),
            matched_types=sorted(list(matched_types)),
        )

        return raw_personalization_score, breakdown, matched_signals

    def rank(
        self,
        candidates: Sequence[PersonalizedCandidateItemSchema | Any],
        context: ResearcherPersonalizationContext,
        *,
        enable_personalization: bool = True,
        base_scores: dict[uuid.UUID, float] | None = None,
        limit: int | None = None,
        offset: int = 0,
        reference_time: datetime | None = None,
    ) -> list[PersonalizedRankedCandidateSchema]:
        """
        Rank candidates using Phase 2 base relevance and Phase 3.5 personalization adjustment.

        Parameters
        ----------
        candidates : Sequence[PersonalizedCandidateItemSchema | Any]
            Candidate opportunities (must include opportunity metadata and provenance).
        context : ResearcherPersonalizationContext
            Target researcher's personalization context.
        enable_personalization : bool
            If False, adjustment is 0.0 (pure Phase 2 baseline ranking R0).
        base_scores : dict[uuid.UUID, float] | None
            Optional pre-computed Phase 2 base relevance scores. If not provided,
            base score is extracted from candidate or calculated from Phase 2 signals.
        limit : int | None
            Maximum candidates to return.
        offset : int
            Pagination offset.
        reference_time : datetime | None
            Anchor timestamp for deadline urgency calculation.

        Returns
        -------
        list[PersonalizedRankedCandidateSchema]
            Deterministically sorted personalized recommendation results.
        """
        if not candidates:
            return []

        if reference_time is None:
            ref_time = datetime.now(timezone.utc)
        elif reference_time.tzinfo is None:
            ref_time = reference_time.replace(tzinfo=timezone.utc)
        else:
            ref_time = reference_time.astimezone(timezone.utc)

        # ── Phase 1: Determine Baseline Phase 2 Base Scores & Base Ranks (R0) ──
        scored_intermediates: list[_ScoredPersonalizedCandidate] = []

        for cand in candidates:
            # Extract opportunity and provenance
            if isinstance(cand, PersonalizedCandidateItemSchema):
                opp = cand.opportunity
                prov = cand.provenance
                cand_item = cand
            elif hasattr(cand, "opportunity") and hasattr(cand, "provenance"):
                opp = cand.opportunity
                prov = cand.provenance
                cand_item = cand
            else:
                # Direct opportunity or model container
                opp = getattr(cand, "opportunity", cand)
                prov = getattr(cand, "provenance", None)
                cand_item = cand

            opp_id = getattr(opp, "id", None) or getattr(cand, "opportunity_id", uuid.uuid4())

            # Eligibility Guard: Skip inactive/archived/expired opportunities
            status = getattr(opp, "status", "ACTIVE")
            if status not in ("ACTIVE", "UNVERIFIED"):
                continue

            deadline_status = getattr(opp, "deadline_status", None)
            if deadline_status == "EXPIRED":
                continue

            # Phase 2 Base Relevance Score Extraction
            base_score: float = 0.50
            if base_scores and opp_id in base_scores:
                base_score = validate_signal(base_scores[opp_id], "base_relevance_score")
            elif hasattr(cand, "base_relevance_score") and cand.base_relevance_score is not None:
                base_score = validate_signal(cand.base_relevance_score, "base_relevance_score")
            elif hasattr(cand, "final_score") and cand.final_score is not None:
                base_score = validate_signal(cand.final_score, "base_relevance_score")
            elif hasattr(cand, "match_score") and cand.match_score is not None:
                base_score = validate_signal(cand.match_score, "base_relevance_score")
            else:
                # Compute deterministic base relevance approximation from opportunity features
                # combining topic similarity, quality, and urgency
                topic_overlap = (
                    0.60
                    if any(
                        t.lower() in [k.lower() for k in context.profile_keywords]
                        for t in (getattr(opp, "topics", []) or [])
                    )
                    else 0.40
                )
                urgency = 0.50
                days_rem = getattr(opp, "days_remaining", None)
                if days_rem is not None and days_rem >= 0:
                    urgency = max(0.0, min(1.0, 1.0 - (days_rem / 90.0)))
                base_score = round(0.60 * topic_overlap + 0.40 * urgency, 6)

            # Extract or calculate urgency for tie-breaking
            days_rem = getattr(opp, "days_remaining", None)
            urgency_score = (
                max(0.0, min(1.0, 1.0 - (days_rem / 90.0)))
                if (days_rem is not None and days_rem >= 0)
                else 0.0
            )

            # Evaluate Personalization Signals
            raw_p_score, breakdown, matched_sigs = self.evaluate_personalization_signals(
                opp=opp,
                provenance=prov,
                context=context,
            )

            # Relevance Damping
            damping = self.calculate_relevance_damping(base_score)
            breakdown.relevance_damping = damping

            # Safety Gate: Phase 2.6 Trust & Risk Intelligence
            # High-risk / predatory opportunities CANNOT receive personalization boost
            is_predatory = getattr(opp, "is_predatory_flag", False)
            risk_level = getattr(opp, "risk_level", "LOW_RISK")
            risk_score = getattr(opp, "risk_score", 0.0) or 0.0
            is_high_risk = is_predatory or risk_level == "HIGH_RISK" or risk_score >= 0.70

            is_suppressed = bool(opp_id and opp_id in context.suppressed_opportunity_ids)

            if not enable_personalization or context.is_cold_start or is_high_risk or is_suppressed:
                p_adjustment = 0.0
            else:
                # Bounded adjustment: min(0.15, raw * 0.15 * damping)
                p_adjustment = round(
                    min(
                        self.max_contribution,
                        raw_p_score * self.max_contribution * damping,
                    ),
                    6,
                )

            # Final Score: min(1.0, base_score + p_adjustment)
            if is_suppressed:
                final_score = round(max(0.0, base_score - 0.50), 6)
            else:
                final_score = round(min(1.0, max(0.0, base_score + p_adjustment)), 6)

            scored_intermediates.append(
                _ScoredPersonalizedCandidate(
                    opportunity_id=opp_id,
                    base_rank=0,  # assigned after baseline sort
                    base_relevance_score=base_score,
                    personalization_score=raw_p_score,
                    personalization_adjustment=p_adjustment,
                    final_score=final_score,
                    urgency_score=urgency_score,
                    breakdown=breakdown,
                    matched_signals=matched_sigs,
                    provenance=prov or CandidateProvenanceSchema(
                        candidate_id=uuid.uuid4(),
                        opportunity_id=opp_id,
                        sources=[CandidateSourceType.COLD_START_FALLBACK],
                        matched_topics=[],
                        matched_preferences=[],
                        matched_expertise=[],
                        reasons=["Candidate evaluated via personalization ranker"],
                        retrieval_channels=["personalization_layer"],
                    ),
                    opportunity=opp,
                    candidate_item=cand_item,
                )
            )

        if not scored_intermediates:
            return []

        # ── Phase 2: Compute Authoritative Base Rank (R0) ─────────────────────
        # Sorted strictly by Phase 2 base relevance
        scored_intermediates.sort(
            key=lambda c: (
                -c.base_relevance_score,
                -c.urgency_score,
                str(c.opportunity_id),
            )
        )
        for idx, item in enumerate(scored_intermediates, start=1):
            item.base_rank = idx

        # ── Phase 3: Deterministic Personalized Ranking (R1) ──────────────────
        # Multi-Key Tie-Breaker:
        # 1. final_score DESC (relevance + bounded personalization)
        # 2. base_relevance_score DESC (relevance dominance in near-ties)
        # 3. personalization_score DESC (higher personalization preference)
        # 4. urgency_score DESC (Phase 2.7 upcoming deadline preference)
        # 5. opportunity_id ASC (deterministic lexicographical UUID)
        scored_intermediates.sort(
            key=lambda c: (
                -c.final_score,
                -c.base_relevance_score,
                -c.personalization_score,
                -c.urgency_score,
                str(c.opportunity_id),
            )
        )

        # Slice for pagination
        total_count = len(scored_intermediates)
        start_idx = min(offset, total_count)
        end_idx = min(start_idx + limit, total_count) if limit is not None else total_count
        sliced = scored_intermediates[start_idx:end_idx]

        final_ranked_results: list[PersonalizedRankedCandidateSchema] = []
        for rank_pos, item in enumerate(sliced, start=start_idx + 1):
            rank_delta = item.base_rank - rank_pos
            final_ranked_results.append(
                PersonalizedRankedCandidateSchema(
                    opportunity_id=item.opportunity_id,
                    rank=rank_pos,
                    base_rank=item.base_rank,
                    rank_delta=rank_delta,
                    final_score=item.final_score,
                    base_relevance_score=item.base_relevance_score,
                    personalization_score=item.personalization_score,
                    personalization_adjustment=item.personalization_adjustment,
                    score_breakdown=item.breakdown,
                    matched_signals=item.matched_signals,
                    provenance=item.provenance,
                    opportunity=item.opportunity,
                )
            )

        return final_ranked_results


# Canonical singleton instance
personalization_ranker = PersonalizationRanker()
