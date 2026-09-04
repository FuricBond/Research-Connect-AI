"""
Deterministic Explainability Layer for Phase 2.5F.

Takes candidate objects produced by upstream retrieval, matching, or recommendation ranking
(e.g., RankedCandidate, SimilarResearchResult, ResearchOpportunityMatch, HybridSearchResult)
and generates:
  1. Exact mathematical score attributions reconciling:
     sum(weighted_contributions) == base_score
     final_score == base_score + reranker_adjustment + diversity_adjustment
  2. Structured academic quality evidence (citations, author prominence, position, institution, venue DOAJ, OA).
  3. Neural cross-encoder reranker attribution and diversity/novelty mechanics attribution.
  4. Deterministic, truthful human-readable summaries, strengths, and limitations with zero-weight suppression.
  5. Comparative ranking diagnostics ("Why was Candidate A ranked above Candidate B?").

Zero external dependencies, zero LLM reliance, strictly deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import math
from typing import Any, Sequence
import uuid

from app.core.config import settings
from app.ranking.features import AcademicFeatures
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankerWeights,
    RankingMode,
    hybrid_ranker,
)
from app.ranking.signals import RankingSignals, validate_signal


# ── Structured Evidence Models ────────────────────────────────────────────────


@dataclass(frozen=True)
class SignalContribution:
    """
    Structured explanation for an individual ranking signal.

    Attributes
    ----------
    signal_name:
        Canonical identifier of the signal (e.g., 'semantic_similarity').
    score:
        Normalized signal value in range [0.0, 1.0].
    weight:
        Active weight applied to this signal in the active ranking mode in [0.0, 1.0].
    contribution:
        Weighted score contribution (score * weight) in [0.0, 1.0].
    qualitative_assessment:
        Descriptive assessment ('Very Strong', 'Moderate', 'Low', 'Minimal', 'Not Available').
    is_available:
        Whether the candidate actually provided data for this signal.
    is_primary_driver:
        Whether this signal is among the dominant positive contributors to the rank.
    raw_value:
        Optional unnormalized or source metric (e.g., raw citation count, publication year, etc.).
    is_active:
        Whether the signal has non-zero weight in the active ranking mode.
    """

    signal_name: str
    score: float
    weight: float
    contribution: float
    qualitative_assessment: str
    is_available: bool = True
    is_primary_driver: bool = False
    raw_value: Any | None = None
    is_active: bool = True


@dataclass(frozen=True)
class TopicEvidence:
    """
    Structured evidence of shared academic topics and taxonomy overlap.
    """

    shared_topic_ids: list[uuid.UUID] = field(default_factory=list)
    shared_topic_names: list[str] = field(default_factory=list)
    topic_similarity: float = 0.0
    description: str = ""


@dataclass(frozen=True)
class ProvenanceEvidence:
    """
    Structured evidence of discovery provenance across retrieval channels.
    """

    retrieval_sources: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class AcademicQualityEvidence:
    """
    Structured bibliographic and academic quality evidence for Phase 2.5D signals.
    """

    citation_count: int | None = None
    citation_impact_score: float = 0.0
    author_prominence_score: float = 0.0
    lead_author_citations: int | None = None
    author_position: str | None = None
    author_position_score: float = 0.50
    institution_names: list[str] = field(default_factory=list)
    institution_prestige_score: float = 0.0
    canonical_venue_name: str | None = None
    venue_prestige_score: float = 0.0
    is_in_doaj: bool = False
    oa_status: str | None = None
    open_access_tier_score: float = 0.35
    description: str = ""


@dataclass(frozen=True)
class ScoreBreakdown:
    """
    Detailed mathematical breakdown of candidate ranking score components.
    """

    base_score: float = 0.0
    relevance_subtotal: float = 0.0
    contextual_subtotal: float = 0.0
    academic_subtotal: float = 0.0
    reranker_adjustment: float = 0.0
    diversity_adjustment: float = 0.0
    final_score: float = 0.0
    reconciliation_gap: float = 0.0
    is_reconciled: bool = True


@dataclass(frozen=True)
class RerankerExplanation:
    """
    Structured attribution for cross-encoder neural reranking adjustments.
    """

    enabled: bool = False
    applied: bool = False
    weight: float = 0.0
    pre_rerank_score: float | None = None
    post_rerank_score: float | None = None
    adjustment: float = 0.0
    raw_score: float | None = None
    fallback: bool = False
    description: str = ""


@dataclass(frozen=True)
class DiversityExplanation:
    """
    Structured attribution for Phase 2.5E diversity and novelty reranking.
    """

    enabled: bool = False
    applied: bool = False
    adjustment: float = 0.0
    redundancy_score: float | None = None
    novelty_score: float | None = None
    redundancy_reasons: list[str] = field(default_factory=list)
    novelty_reasons: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class ComparativeExplanation:
    """
    Deterministic comparison between two ranked candidates explaining why A outranked B.
    """

    winner_id: uuid.UUID
    loser_id: uuid.UUID
    score_difference: float = 0.0
    relevance_difference: float = 0.0
    academic_difference: float = 0.0
    contextual_difference: float = 0.0
    reranker_difference: float = 0.0
    diversity_difference: float = 0.0
    dominant_factors: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class ResultExplanation:
    """
    Complete explanation container for a ranked candidate result.

    Attributes
    ----------
    summary:
        Concise 1-2 sentence overview of why the result was selected and ranked.
    strengths:
        Ordered list of key positive factors supporting the match.
    limitations:
        Ordered list of limiting factors or low-signal characteristics.
    signal_contributions:
        Dictionary mapping canonical signal names to structured SignalContribution objects.
    topic_evidence:
        Structured topic overlap and taxonomy information.
    provenance_evidence:
        Structured discovery channel provenance.
    primary_factors:
        Ordered list of the strongest ranking factors.
    final_score:
        Composite ranking score of the candidate in [0.0, 1.0].
    rank:
        1-based rank position of the candidate in results.
    base_score:
        Pre-adjustment composite score from weighted signals in [0.0, 1.0].
    score_breakdown:
        Detailed mathematical breakdown of subtotals and score reconciliation.
    academic_evidence:
        Structured bibliographic and venue quality evidence.
    reranker_explanation:
        Attribution for neural cross-encoder reranker adjustments.
    diversity_explanation:
        Attribution for Phase 2.5E diversity and novelty reranker mechanics.
    """

    summary: str
    strengths: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    signal_contributions: dict[str, SignalContribution] = field(default_factory=dict)
    topic_evidence: TopicEvidence = field(default_factory=TopicEvidence)
    provenance_evidence: ProvenanceEvidence = field(default_factory=ProvenanceEvidence)
    primary_factors: list[str] = field(default_factory=list)
    final_score: float = 0.0
    rank: int = 0
    base_score: float = 0.0
    score_breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    academic_evidence: AcademicQualityEvidence = field(
        default_factory=AcademicQualityEvidence
    )
    reranker_explanation: RerankerExplanation = field(
        default_factory=RerankerExplanation
    )
    diversity_explanation: DiversityExplanation = field(
        default_factory=DiversityExplanation
    )


@dataclass(frozen=True)
class ExplainedResult:
    """
    Envelope pairing a candidate result with its detailed explanation.
    """

    result: Any
    explanation: ResultExplanation


# ── Result Explainer Engine ───────────────────────────────────────────────────


class ResultExplainer:
    """
    Deterministic Explainability Engine for Search, Similar Research, and Opportunity Matching.

    Produces clear human-readable rationales and machine-readable feature attributions
    derived strictly from normalized ranking signals and configured weights.
    """

    def __init__(
        self,
        high_threshold: float | None = None,
        positive_threshold: float | None = None,
        weak_threshold: float | None = None,
        max_reasons: int | None = None,
        ranker: HybridRanker | None = None,
    ) -> None:
        self.high_threshold = (
            high_threshold
            if high_threshold is not None
            else getattr(settings, "explainability_high_threshold", 0.75)
        )
        self.positive_threshold = (
            positive_threshold
            if positive_threshold is not None
            else getattr(settings, "explainability_positive_threshold", 0.50)
        )
        self.weak_threshold = (
            weak_threshold
            if weak_threshold is not None
            else getattr(settings, "explainability_weak_threshold", 0.25)
        )
        self.max_reasons = (
            max_reasons
            if max_reasons is not None
            else getattr(settings, "explainability_max_reasons", 8)
        )
        self.ranker = ranker or hybrid_ranker

    def _get_qualitative_label(self, score: float, is_available: bool) -> str:
        """Map numerical score to a qualitative verbal tier."""
        if not is_available:
            return "Not Available"
        if score >= self.high_threshold:
            return "Very Strong"
        if score >= self.positive_threshold:
            return "Moderate"
        if score >= self.weak_threshold:
            return "Low"
        return "Minimal"

    def _build_provenance_evidence(self, sources: list[str]) -> ProvenanceEvidence:
        """Generate structured and human-readable provenance evidence."""
        norm_sources = sorted(list(set(sources)))
        has_semantic = "semantic" in norm_sources or "vector" in norm_sources
        has_lexical = "lexical" in norm_sources
        has_topic = "topic" in norm_sources

        if has_semantic and has_lexical:
            desc = "Independently surfaced by both semantic vector search and full-text keyword matching."
        elif has_semantic:
            desc = "Surfaced via semantic vector search."
        elif has_lexical:
            desc = "Surfaced via full-text keyword matching."
        elif has_topic:
            desc = "Surfaced via canonical academic topic associations."
        elif norm_sources:
            desc = f"Surfaced via {', '.join(norm_sources)} retrieval."
        else:
            desc = "Surfaced via candidate retrieval."

        return ProvenanceEvidence(
            retrieval_sources=norm_sources,
            description=desc,
        )

    def _build_topic_evidence(
        self,
        shared_ids: list[uuid.UUID],
        shared_names: list[str],
        topic_score: float,
        is_available: bool,
    ) -> TopicEvidence:
        """Generate structured topic evidence and narrative description."""
        if not is_available:
            return TopicEvidence(
                shared_topic_ids=[],
                shared_topic_names=[],
                topic_similarity=0.0,
                description="Topic information was unavailable for this candidate.",
            )

        if shared_names:
            topic_str = ", ".join(shared_names[:4])
            if len(shared_names) > 4:
                topic_str += f" (and {len(shared_names) - 4} others)"

            if topic_score >= self.high_threshold:
                desc = f"Strong topical alignment across shared topics: {topic_str}."
            elif topic_score >= self.positive_threshold:
                desc = f"Moderate topical overlap in shared fields: {topic_str}."
            else:
                desc = f"Shares topics: {topic_str}."
        elif topic_score > 0.0:
            desc = "Related through shared academic taxonomy DAG hierarchy."
        else:
            desc = "No direct canonical topic overlap identified."

        return TopicEvidence(
            shared_topic_ids=shared_ids,
            shared_topic_names=shared_names,
            topic_similarity=topic_score,
            description=desc,
        )

    def _build_academic_evidence(
        self,
        signals: RankingSignals,
        attached_entity: Any,
        candidate: Any,
    ) -> AcademicQualityEvidence:
        """Extract verified underlying bibliographic metadata without fabrication."""
        cit_count: int | None = None
        oa_stat: str | None = None
        venue_nm: str | None = None
        in_doaj: bool = False
        top_aut_cits: int | None = None
        aut_pos_str: str | None = None
        inst_nms: list[str] = []

        target = attached_entity if attached_entity is not None else candidate

        if isinstance(target, dict):
            cit_count = target.get("cited_by_count")
            oa_stat = target.get("oa_status")
            v = target.get("primary_source", target.get("venue"))
            if isinstance(v, dict):
                venue_nm = v.get("name", v.get("title"))
                in_doaj = bool(v.get("is_in_doaj", False))
            elif isinstance(v, str):
                venue_nm = v

            insts = target.get("institution_links", target.get("institutions", []))
            if isinstance(insts, list):
                for it in insts:
                    if isinstance(it, dict) and "name" in it:
                        inst_nms.append(str(it["name"]))
                    elif isinstance(it, str):
                        inst_nms.append(it)
        elif target is not None:
            cit_count = getattr(target, "cited_by_count", None)
            oa_stat = getattr(target, "oa_status", None)
            ps = getattr(target, "primary_source", None)
            if ps is not None:
                venue_nm = getattr(ps, "name", None)
                in_doaj = bool(getattr(ps, "is_in_doaj", False))
            elif hasattr(target, "venue") and getattr(target, "venue"):
                v_attr = getattr(target, "venue")
                if isinstance(v_attr, str):
                    venue_nm = v_attr
                elif hasattr(v_attr, "name"):
                    venue_nm = getattr(v_attr, "name")

            al = getattr(target, "author_links", None)
            if al:
                for item in al:
                    res = getattr(item, "researcher", None)
                    if res and hasattr(res, "cited_by_count") and getattr(res, "cited_by_count") is not None:
                        c = int(getattr(res, "cited_by_count"))
                        if top_aut_cits is None or c > top_aut_cits:
                            top_aut_cits = c
                    pos = getattr(item, "author_position", None)
                    if pos and aut_pos_str is None:
                        aut_pos_str = str(pos)

            il = getattr(target, "institution_links", None)
            if il:
                for item in il:
                    inst = getattr(item, "institution", None)
                    if inst and hasattr(inst, "name") and getattr(inst, "name"):
                        inst_nms.append(str(getattr(inst, "name")))

        # Fallback to direct candidate attributes if target was an envelope
        if cit_count is None and hasattr(candidate, "cited_by_count"):
            cit_count = getattr(candidate, "cited_by_count")
        if oa_stat is None and hasattr(candidate, "oa_status"):
            oa_stat = getattr(candidate, "oa_status")

        desc_clauses: list[str] = []
        if cit_count is not None and cit_count > 0:
            desc_clauses.append(f"{cit_count:,} citations")
        elif signals.citation_impact >= self.high_threshold:
            desc_clauses.append("high citation impact")

        if venue_nm:
            doaj_note = " (DOAJ Open Access)" if in_doaj else ""
            desc_clauses.append(f"published in '{venue_nm}'{doaj_note}")

        if oa_stat:
            desc_clauses.append(f"{oa_stat.title()} Open Access")

        if inst_nms:
            clean_insts = sorted(list(set(inst_nms)))[:2]
            desc_clauses.append(f"affiliated with {', '.join(clean_insts)}")

        description = (
            "; ".join(desc_clauses).capitalize() + "."
            if desc_clauses
            else "Baseline academic quality profile."
        )

        return AcademicQualityEvidence(
            citation_count=cit_count,
            citation_impact_score=signals.citation_impact,
            author_prominence_score=signals.author_prominence,
            lead_author_citations=top_aut_cits,
            author_position=aut_pos_str,
            author_position_score=signals.author_position,
            institution_names=sorted(list(set(inst_nms)))[:3],
            institution_prestige_score=signals.institution_prestige,
            canonical_venue_name=venue_nm,
            venue_prestige_score=signals.venue_prestige,
            is_in_doaj=in_doaj,
            oa_status=oa_stat,
            open_access_tier_score=signals.open_access_tier,
            description=description,
        )

    def explain(
        self,
        candidate: Any,
        *,
        mode: RankingMode | str = RankingMode.GENERAL,
        weights: RankerWeights | None = None,
        reference_time: datetime | None = None,
    ) -> ResultExplanation:
        """
        Generate a comprehensive, deterministic ResultExplanation for a candidate.

        Parameters
        ----------
        candidate:
            Candidate instance (RankedCandidate, SimilarResearchResult, ResearchOpportunityMatch, etc.).
        mode:
            Ranking mode context ('research_similarity', 'research_opportunity', or 'general').
        weights:
            Optional custom weights. If omitted, uses configured defaults for mode.
        reference_time:
            Optional anchor datetime for urgency calculation.

        Returns
        -------
        ResultExplanation
            Complete explanation model with exact subtotals, academic quality evidence,
            cross-encoder and diversity attributions, and truthful summaries.
        """
        # 1. Resolve Active Weights for Mode
        active_weights = self.ranker.resolve_weights(mode, weights)
        active_weights.validate()

        # 2. Extract Signals & Metadata
        precomputed_af: AcademicFeatures | None = getattr(
            candidate, "academic_features", None
        )

        (
            entity_id,
            entity_type,
            signals,
            shared_ids,
            shared_names,
            attached_entity,
        ) = self.ranker.extract_signals(
            candidate=candidate,
            mode=str(mode),
            reference_time=reference_time,
            precomputed_academic_features=precomputed_af,
        )

        rank_pos = getattr(candidate, "rank", 0)
        reported_final_score = getattr(
            candidate,
            "final_score",
            getattr(
                candidate,
                "combined_similarity",
                getattr(
                    candidate,
                    "match_score",
                    getattr(candidate, "hybrid_score", 0.0),
                ),
            ),
        )

        # 3. Detect Availability of Optional Metadata
        has_embedding = (
            signals.semantic_similarity > 0.0
            or "semantic" in signals.retrieval_sources
            or "vector" in signals.retrieval_sources
        )
        has_lexical = (
            signals.lexical_similarity > 0.0
            or "lexical" in signals.retrieval_sources
        )
        has_topics = bool(shared_ids or shared_names or signals.topic_similarity > 0.0)

        has_freshness = False
        if attached_entity is not None and (
            hasattr(attached_entity, "publication_year")
            or hasattr(attached_entity, "publication_date")
        ):
            has_freshness = (
                getattr(attached_entity, "publication_year", None) is not None
                or getattr(attached_entity, "publication_date", None) is not None
            )
        elif hasattr(candidate, "freshness") and getattr(candidate, "freshness") is not None and getattr(candidate, "freshness") > 0.0:
            has_freshness = True
        elif hasattr(candidate, "freshness_score") and getattr(candidate, "freshness_score") is not None and getattr(candidate, "freshness_score") > 0.0:
            has_freshness = True

        has_urgency = False
        if attached_entity is not None and hasattr(attached_entity, "submission_deadline"):
            has_urgency = getattr(attached_entity, "submission_deadline", None) is not None
        elif hasattr(candidate, "urgency") and getattr(candidate, "urgency") is not None and getattr(candidate, "urgency") > 0.0:
            has_urgency = True
        elif hasattr(candidate, "urgency_score") and getattr(candidate, "urgency_score") is not None and getattr(candidate, "urgency_score") > 0.0:
            has_urgency = True

        has_type = (
            signals.type_compatibility > 0.0
            or (attached_entity is not None and hasattr(attached_entity, "opportunity_type"))
            or hasattr(candidate, "type_compatibility")
            or hasattr(candidate, "type_score")
        )

        has_quality = (
            signals.opportunity_quality > 0.0
            or (attached_entity is not None and hasattr(attached_entity, "indexing"))
            or hasattr(candidate, "quality_score")
            or hasattr(candidate, "opportunity_quality")
            or entity_type == "opportunity"
        )

        # 4. Extract Raw Values for Attribution Transparency
        raw_cits = getattr(attached_entity, "cited_by_count", getattr(candidate, "cited_by_count", None))
        if isinstance(attached_entity, dict) and raw_cits is None:
            raw_cits = attached_entity.get("cited_by_count")

        raw_year = getattr(attached_entity, "publication_year", None)
        if isinstance(attached_entity, dict) and raw_year is None:
            raw_year = attached_entity.get("publication_year")

        raw_deadline = getattr(attached_entity, "submission_deadline", None)
        if isinstance(attached_entity, dict) and raw_deadline is None:
            raw_deadline = attached_entity.get("submission_deadline")

        # 5. Build Structured Signal Contributions with Exact Math
        signal_defs = [
            # Relevance Signals
            (
                "semantic_similarity",
                signals.semantic_similarity,
                active_weights.semantic_weight,
                has_embedding,
                signals.semantic_similarity,
            ),
            (
                "lexical_relevance",
                signals.lexical_similarity,
                active_weights.lexical_weight,
                has_lexical,
                getattr(candidate, "lexical_score", signals.lexical_similarity),
            ),
            (
                "topic_compatibility",
                signals.topic_similarity,
                active_weights.topic_weight,
                has_topics,
                len(shared_names) if shared_names else signals.topic_similarity,
            ),
            # Contextual Signals
            (
                "type_compatibility",
                signals.type_compatibility,
                active_weights.type_weight,
                has_type,
                getattr(attached_entity, "opportunity_type", None),
            ),
            (
                "opportunity_quality",
                signals.opportunity_quality,
                active_weights.quality_weight,
                has_quality,
                getattr(attached_entity, "indexing", None),
            ),
            (
                "publication_freshness",
                signals.freshness,
                active_weights.freshness_weight,
                has_freshness,
                raw_year,
            ),
            (
                "deadline_urgency",
                signals.urgency,
                active_weights.urgency_weight,
                has_urgency,
                str(raw_deadline) if raw_deadline else None,
            ),
            # Academic Quality Signals
            (
                "citation_impact",
                signals.citation_impact,
                active_weights.citation_weight,
                (raw_cits is not None and raw_cits > 0) or signals.citation_impact > 0.0,
                raw_cits,
            ),
            (
                "author_prominence",
                signals.author_prominence,
                active_weights.author_prominence_weight,
                signals.author_prominence > 0.0,
                None,
            ),
            (
                "author_position",
                signals.author_position,
                active_weights.author_position_weight,
                signals.author_position > 0.50,
                None,
            ),
            (
                "institution_prestige",
                signals.institution_prestige,
                active_weights.institution_weight,
                signals.institution_prestige > 0.0,
                None,
            ),
            (
                "venue_prestige",
                signals.venue_prestige,
                active_weights.venue_weight,
                signals.venue_prestige > 0.0,
                getattr(getattr(attached_entity, "primary_source", None), "name", None),
            ),
            (
                "open_access_tier",
                signals.open_access_tier,
                active_weights.open_access_weight,
                signals.open_access_tier > 0.35,
                getattr(attached_entity, "oa_status", None),
            ),
        ]

        contributions: dict[str, SignalContribution] = {}
        active_candidates_for_driver: list[tuple[str, float, float]] = []

        for name, score, weight, is_avail, raw_val in signal_defs:
            is_active = weight > 0.0
            if is_active or is_avail:
                contrib_val = round(score * weight, 6)
                if is_active and is_avail and score >= self.positive_threshold and contrib_val > 0.0:
                    active_candidates_for_driver.append((name, contrib_val, score))

                qual_label = self._get_qualitative_label(score, is_avail)
                contributions[name] = SignalContribution(
                    signal_name=name,
                    score=score,
                    weight=weight,
                    contribution=contrib_val,
                    qualitative_assessment=qual_label,
                    is_available=is_avail,
                    is_primary_driver=False,
                    raw_value=raw_val,
                    is_active=is_active,
                )

        # Mark primary drivers (top active contributors by contribution magnitude)
        # Strict zero-weight suppression: only signals with weight > 0 and contribution > 0 can drive ranking
        active_candidates_for_driver.sort(key=lambda x: (-x[1], -x[2]))
        primary_factor_names = [item[0] for item in active_candidates_for_driver[:2]]

        for p_name in primary_factor_names:
            if p_name in contributions:
                old_sc = contributions[p_name]
                contributions[p_name] = SignalContribution(
                    signal_name=old_sc.signal_name,
                    score=old_sc.score,
                    weight=old_sc.weight,
                    contribution=old_sc.contribution,
                    qualitative_assessment=old_sc.qualitative_assessment,
                    is_available=old_sc.is_available,
                    is_primary_driver=True,
                    raw_value=old_sc.raw_value,
                    is_active=old_sc.is_active,
                )

        # 6. Calculate Subtotals and Exact Score Reconciliation
        rel_subtotal = round(
            active_weights.semantic_weight * signals.semantic_similarity
            + active_weights.lexical_weight * signals.lexical_similarity
            + active_weights.topic_weight * signals.topic_similarity,
            6,
        )
        ctx_subtotal = round(
            active_weights.type_weight * signals.type_compatibility
            + active_weights.freshness_weight * signals.freshness
            + active_weights.urgency_weight * signals.urgency
            + active_weights.quality_weight * signals.opportunity_quality,
            6,
        )
        acad_subtotal = round(
            active_weights.citation_weight * signals.citation_impact
            + active_weights.author_prominence_weight * signals.author_prominence
            + active_weights.author_position_weight * signals.author_position
            + active_weights.institution_weight * signals.institution_prestige
            + active_weights.venue_weight * signals.venue_prestige
            + active_weights.open_access_weight * signals.open_access_tier,
            6,
        )
        calculated_base_score = round(rel_subtotal + ctx_subtotal + acad_subtotal, 6)

        # Extract post-ranking adjustments (Cross-Encoder & Diversity)
        reranker_adj: float | None = getattr(candidate, "reranker_adjustment", None)
        raw_reranker: float | None = getattr(candidate, "raw_reranker_score", None)
        if reranker_adj is None and isinstance(candidate, dict):
            reranker_adj = candidate.get("reranker_adjustment")
            raw_reranker = candidate.get("raw_reranker_score")

        diversity_adj: float | None = getattr(candidate, "diversity_adjustment", None)
        nov_score: float | None = getattr(candidate, "novelty_score", None)
        red_score: float | None = getattr(candidate, "redundancy_score", None)
        red_reasons = list(getattr(candidate, "redundancy_reasons", []))
        nov_reasons = list(getattr(candidate, "novelty_reasons", []))
        if diversity_adj is None and isinstance(candidate, dict):
            diversity_adj = candidate.get("diversity_adjustment")
            nov_score = candidate.get("novelty_score")
            red_score = candidate.get("redundancy_score")
            red_reasons = list(candidate.get("redundancy_reasons", []))
            nov_reasons = list(candidate.get("novelty_reasons", []))

        final_score_val = round(float(reported_final_score), 6)

        # Total expected final score reconciliation:
        # final_score ≈ base_score + reranker_adjustment + diversity_adjustment
        effective_reranker_adj = float(reranker_adj) if reranker_adj is not None else 0.0
        effective_diversity_adj = float(diversity_adj) if diversity_adj is not None else 0.0
        expected_final = round(
            calculated_base_score + effective_reranker_adj + effective_diversity_adj, 6
        )
        reconciliation_gap = round(abs(final_score_val - expected_final), 6)
        is_reconciled = reconciliation_gap <= 1e-4

        score_breakdown = ScoreBreakdown(
            base_score=calculated_base_score,
            relevance_subtotal=rel_subtotal,
            contextual_subtotal=ctx_subtotal,
            academic_subtotal=acad_subtotal,
            reranker_adjustment=effective_reranker_adj,
            diversity_adjustment=effective_diversity_adj,
            final_score=final_score_val,
            reconciliation_gap=reconciliation_gap,
            is_reconciled=is_reconciled,
        )

        # 7. Extract Academic Quality Evidence Container
        academic_evidence = self._build_academic_evidence(
            signals, attached_entity, candidate
        )

        # 8. Extract Cross-Encoder Reranker Attribution Container
        reranker_applied = reranker_adj is not None and abs(reranker_adj) > 1e-6
        reranker_enabled = getattr(settings, "reranker_enabled", False) or reranker_applied
        reranker_desc = ""
        if reranker_applied:
            if reranker_adj > 0:
                reranker_desc = f"Semantic cross-encoder reranking boosted score by +{reranker_adj:.4f}."
            else:
                reranker_desc = f"Semantic cross-encoder reranking adjusted score by {reranker_adj:.4f}."
        elif reranker_enabled and reranker_adj == 0.0:
            reranker_desc = "Cross-encoder reranking produced neutral adjustment (0.0000)."
        else:
            reranker_desc = "Baseline ranking retained; cross-encoder neural reranking was not active."

        reranker_explanation = RerankerExplanation(
            enabled=reranker_enabled,
            applied=reranker_applied,
            weight=getattr(settings, "reranker_weight", 0.10) if reranker_enabled else 0.0,
            pre_rerank_score=calculated_base_score if reranker_applied else None,
            post_rerank_score=round(calculated_base_score + effective_reranker_adj, 6) if reranker_applied else None,
            adjustment=effective_reranker_adj,
            raw_score=raw_reranker,
            fallback=False,
            description=reranker_desc,
        )

        # 9. Extract Diversity & Novelty Attribution Container
        diversity_applied = diversity_adj is not None and abs(diversity_adj) > 1e-6
        diversity_desc = ""
        if diversity_applied:
            diversity_desc = (
                f"List-aware diversity reranking applied adjustment of {diversity_adj:+.4f} "
                f"to reduce redundancy with previously selected papers."
            )
        elif nov_score is not None:
            diversity_desc = "List-aware diversity evaluated; candidate provides distinct novelty without penalty."
        else:
            diversity_desc = "Diversity reranking was not active for this candidate."

        diversity_explanation = DiversityExplanation(
            enabled=diversity_adj is not None or nov_score is not None,
            applied=diversity_applied,
            adjustment=effective_diversity_adj,
            redundancy_score=red_score,
            novelty_score=nov_score,
            redundancy_reasons=red_reasons,
            novelty_reasons=nov_reasons,
            description=diversity_desc,
        )

        # 10. Extract Strengths (Positive Human-Readable Factors)
        # Prioritized: Relevance -> Academic Quality -> Cross-Encoder -> Diversity/Novelty -> Contextual
        strengths: list[str] = []

        # (a) Relevance Strengths (only if active in mode)
        if has_embedding and active_weights.semantic_weight > 0.0:
            if signals.semantic_similarity >= self.high_threshold:
                strengths.append(
                    "Strong semantic similarity reflecting deep conceptual and contextual alignment."
                )
            elif signals.semantic_similarity >= self.positive_threshold:
                strengths.append(
                    "Moderate semantic similarity to the source research concepts."
                )

        if has_topics and active_weights.topic_weight > 0.0:
            if signals.topic_similarity >= self.high_threshold:
                if shared_names:
                    topic_str = ", ".join(shared_names[:3])
                    strengths.append(
                        f"Direct alignment on core academic topics: {topic_str}."
                    )
                else:
                    strengths.append("High topic alignment across domain taxonomy.")
            elif signals.topic_similarity >= self.positive_threshold:
                if shared_names:
                    strengths.append(
                        f"Moderate topical overlap in {', '.join(shared_names[:2])}."
                    )
                else:
                    strengths.append("Moderate topical overlap in shared research areas.")
            elif signals.topic_similarity > 0.0:
                strengths.append(
                    "Related through hierarchical academic taxonomy DAG proximity."
                )

        if has_lexical and active_weights.lexical_weight > 0.0:
            if signals.lexical_similarity >= self.high_threshold:
                strengths.append(
                    "Substantial keyword and terminology overlap in title and textual metadata."
                )
            elif signals.lexical_similarity >= self.positive_threshold:
                strengths.append("Notable keyword overlap with key terminology.")

        # (b) Academic Quality Strengths (strictly gated by active weight & truthfulness)
        if active_weights.citation_weight > 0.0 and signals.citation_impact >= self.high_threshold:
            if raw_cits and raw_cits > 0:
                strengths.append(
                    f"High scholarly impact supported by significant academic citation volume ({raw_cits:,} citations)."
                )
            else:
                strengths.append(
                    "High scholarly impact supported by significant academic citation volume."
                )

        if active_weights.venue_weight > 0.0 and signals.venue_prestige >= self.high_threshold:
            if academic_evidence.canonical_venue_name:
                strengths.append(
                    f"Published in a prestigious academic venue ({academic_evidence.canonical_venue_name})."
                )
            else:
                strengths.append(
                    "Published in a prestigious, highly-cited academic venue or verified DOAJ journal."
                )

        if active_weights.open_access_weight > 0.0 and signals.open_access_tier >= 0.85:
            strengths.append("Freely accessible under an open-access publishing model.")

        if (
            active_weights.author_prominence_weight > 0.0
            and signals.author_prominence >= self.high_threshold
        ):
            strengths.append(
                "Authored by prominent researchers with distinguished academic citation records."
            )

        # (c) Cross-Encoder Reranker Strength
        if reranker_adj is not None and reranker_adj >= 0.02:
            strengths.append(
                "Semantic cross-encoder reranking boosted ranking based on full contextual relevance."
            )

        # (d) Diversity & Novelty Strengths
        if nov_reasons:
            for nr in nov_reasons[:2]:
                strengths.append(nr)
        elif nov_score is not None and nov_score >= 0.70 and diversity_adj is not None and diversity_adj >= -0.01:
            if diversity_adj > 0.005:
                strengths.append(
                    f"Novelty boost applied ({diversity_adj:+.4f}): introduces distinct research direction with low redundancy against selected papers."
                )
            else:
                strengths.append(
                    "Introduces distinct research direction with low redundancy against selected papers."
                )

        # (e) Contextual Secondary Strengths (Type, Quality, Freshness, Urgency)
        if has_type and active_weights.type_weight > 0.0:
            if signals.type_compatibility >= 0.85:
                strengths.append(
                    "Publication type is highly compatible with this opportunity category."
                )
            elif signals.type_compatibility >= 0.65:
                strengths.append(
                    "Publication type is moderately compatible with this opportunity category."
                )

        # Opportunity Quality strength
        is_pred: bool | None = None
        risk_sc: float | None = None
        indexing_list: list[str] | None = None

        if attached_entity is not None:
            if isinstance(attached_entity, dict):
                is_pred = attached_entity.get("is_predatory_flag", attached_entity.get("is_predatory"))
                risk_sc = attached_entity.get("risk_score")
                indexing_list = attached_entity.get("indexing")
            else:
                is_pred = getattr(attached_entity, "is_predatory_flag", getattr(attached_entity, "is_predatory", None))
                risk_sc = getattr(attached_entity, "risk_score", None)
                indexing_list = getattr(attached_entity, "indexing", None)

        if is_pred is None and candidate is not None:
            if isinstance(candidate, dict):
                is_pred = candidate.get("is_predatory_flag", candidate.get("is_predatory"))
                if risk_sc is None:
                    risk_sc = candidate.get("risk_score")
                if indexing_list is None:
                    indexing_list = candidate.get("indexing")
            else:
                is_pred = getattr(candidate, "is_predatory_flag", getattr(candidate, "is_predatory", None))
                if risk_sc is None:
                    risk_sc = getattr(candidate, "risk_score", None)
                if indexing_list is None:
                    indexing_list = getattr(candidate, "indexing", None)

        if has_quality and active_weights.quality_weight > 0.0:
            if signals.opportunity_quality >= self.high_threshold:
                if indexing_list and any(
                    isinstance(x, str) and x.upper() in {"SCOPUS", "SCI", "SCIE", "WEB OF SCIENCE", "WOS", "IEEE", "ACM", "PUBMED"}
                    for x in indexing_list
                ):
                    top_indexers = [
                        x for x in indexing_list
                        if isinstance(x, str) and x.upper() in {"SCOPUS", "SCI", "SCIE", "WEB OF SCIENCE", "WOS", "IEEE", "ACM", "PUBMED"}
                    ]
                    strengths.append(
                        f"High venue quality indexed in recognized academic databases ({', '.join(top_indexers[:2])})."
                    )
                else:
                    strengths.append("High venue quality and verified status reliability.")
            elif signals.opportunity_quality >= self.positive_threshold:
                strengths.append("Verified venue status with standard academic indexing.")

        if has_freshness and active_weights.freshness_weight > 0.0:
            if signals.freshness >= self.high_threshold:
                strengths.append("Recent publication reflecting contemporary research.")
            elif signals.freshness >= self.positive_threshold:
                strengths.append("Moderately recent publication.")

        if has_urgency and active_weights.urgency_weight > 0.0:
            if signals.urgency >= self.high_threshold:
                strengths.append("Upcoming submission deadline due in the immediate term.")
            elif signals.urgency >= self.positive_threshold:
                strengths.append("Active upcoming submission deadline within the active window.")

        prov_evidence = self._build_provenance_evidence(signals.retrieval_sources)
        if len(prov_evidence.retrieval_sources) >= 2:
            strengths.append(prov_evidence.description)

        # 11. Extract Limitations (Weaknesses / Limiting Factors)
        limitations: list[str] = []

        # Predatory risk penalty warning
        if is_pred is True or (risk_sc is not None and float(risk_sc) >= 0.70):
            limitations.append(
                "Flagged for potential predatory publication risk; ranking significantly penalized."
            )
        elif has_quality and active_weights.quality_weight > 0.0 and signals.opportunity_quality < self.weak_threshold:
            limitations.append("Lower verified venue quality or incomplete indexing status.")

        # Diversity penalty limitation
        if diversity_adj is not None and diversity_adj <= -0.01:
            if red_reasons:
                limitations.append(
                    f"Redundancy penalty applied ({diversity_adj:+.4f}): {', '.join(red_reasons[:2])}."
                )
            else:
                limitations.append(
                    f"Redundancy penalty applied ({diversity_adj:+.4f}) to avoid semantic or topical redundancy with selected research."
                )

        # Weak active signals (only evaluated if signal has non-zero weight)
        if (
            has_embedding
            and active_weights.semantic_weight > 0.0
            and signals.semantic_similarity < self.weak_threshold
        ):
            limitations.append("Low semantic similarity to the source research concepts.")

        if (
            has_topics
            and active_weights.topic_weight > 0.0
            and signals.topic_similarity < self.weak_threshold
        ):
            limitations.append("Minimal canonical topic overlap.")
        elif not has_topics and active_weights.topic_weight > 0.0:
            limitations.append("No canonical topic associations were identified.")

        if (
            has_lexical
            and active_weights.lexical_weight > 0.0
            and signals.lexical_similarity < self.weak_threshold
        ):
            limitations.append("Limited lexical keyword overlap.")

        if (
            has_type
            and active_weights.type_weight > 0.0
            and signals.type_compatibility < 0.50
        ):
            limitations.append("Lower conventional compatibility for this publication type.")

        if (
            has_freshness
            and active_weights.freshness_weight > 0.0
            and signals.freshness < self.weak_threshold
        ):
            limitations.append("Older publication with lower recency weight.")

        # 12. Synthesize Deterministic Summary
        str_mode = mode.value if isinstance(mode, RankingMode) else str(mode).lower()

        if str_mode == RankingMode.RESEARCH_OPPORTUNITY.value or entity_type == "opportunity":
            entity_label = "academic opportunity"
        else:
            entity_label = "similar research work"

        if primary_factor_names:
            clean_drivers = [
                name.replace("_", " ").title() for name in primary_factor_names
            ]
            drivers_str = " and ".join(clean_drivers)
            summary = (
                f"Ranked as a relevant {entity_label} driven primarily by {drivers_str.lower()}."
            )
        elif strengths:
            summary = f"Ranked as a relevant {entity_label} with positive matching signals."
        else:
            summary = f"Ranked as a potential {entity_label} based on baseline matching criteria."

        # If significant adjustments took place, append brief note
        if diversity_adj is not None and diversity_adj <= -0.02:
            summary += " Score includes an adjustment for research diversity."
        elif reranker_adj is not None and abs(reranker_adj) >= 0.02:
            summary += " Score includes neural cross-encoder reranking adjustment."

        truncated_strengths = strengths[: self.max_reasons]
        truncated_limitations = limitations[: self.max_reasons]

        topic_evidence = self._build_topic_evidence(
            shared_ids, shared_names, signals.topic_similarity, has_topics
        )

        return ResultExplanation(
            summary=summary,
            strengths=truncated_strengths,
            limitations=truncated_limitations,
            signal_contributions=contributions,
            topic_evidence=topic_evidence,
            provenance_evidence=prov_evidence,
            primary_factors=primary_factor_names,
            final_score=final_score_val,
            rank=int(rank_pos),
            base_score=calculated_base_score,
            score_breakdown=score_breakdown,
            academic_evidence=academic_evidence,
            reranker_explanation=reranker_explanation,
            diversity_explanation=diversity_explanation,
        )

    def explain_batch(
        self,
        candidates: Sequence[Any],
        *,
        mode: RankingMode | str = RankingMode.GENERAL,
        weights: RankerWeights | None = None,
        reference_time: datetime | None = None,
    ) -> list[ExplainedResult]:
        """
        Generate explanations for a batch of ranked candidates.

        Returns
        -------
        list[ExplainedResult]
            List of ExplainedResult envelopes preserving the candidate and its explanation.
        """
        results: list[ExplainedResult] = []
        for cand in candidates:
            expl = self.explain(
                candidate=cand,
                mode=mode,
                weights=weights,
                reference_time=reference_time,
            )
            results.append(ExplainedResult(result=cand, explanation=expl))
        return results

    def compare(
        self,
        candidate_a: Any,
        candidate_b: Any,
        *,
        mode: RankingMode | str = RankingMode.GENERAL,
        weights: RankerWeights | None = None,
        reference_time: datetime | None = None,
    ) -> ComparativeExplanation:
        """
        Generate a deterministic comparative ranking explanation between two candidates.

        Explains why candidate A was ranked higher (or lower) than candidate B
        based on exact score differences across relevance, academic quality, contextual,
        and post-ranking adjustments.
        """
        expl_a = self.explain(
            candidate_a, mode=mode, weights=weights, reference_time=reference_time
        )
        expl_b = self.explain(
            candidate_b, mode=mode, weights=weights, reference_time=reference_time
        )

        id_a = getattr(candidate_a, "entity_id", getattr(candidate_a, "id", None))
        if id_a is None and isinstance(candidate_a, dict):
            id_a = candidate_a.get("entity_id", candidate_a.get("id"))
        id_b = getattr(candidate_b, "entity_id", getattr(candidate_b, "id", None))
        if id_b is None and isinstance(candidate_b, dict):
            id_b = candidate_b.get("entity_id", candidate_b.get("id"))

        uuid_a = uuid.UUID(str(id_a)) if id_a else uuid.uuid4()
        uuid_b = uuid.UUID(str(id_b)) if id_b else uuid.uuid4()

        # Determine winner based on final_score (or base_score if equal)
        if expl_a.final_score >= expl_b.final_score:
            winner_id, loser_id = uuid_a, uuid_b
            winner_expl, loser_expl = expl_a, expl_b
        else:
            winner_id, loser_id = uuid_b, uuid_a
            winner_expl, loser_expl = expl_b, expl_a

        score_diff = round(abs(expl_a.final_score - expl_b.final_score), 6)
        rel_diff = round(
            winner_expl.score_breakdown.relevance_subtotal
            - loser_expl.score_breakdown.relevance_subtotal,
            6,
        )
        acad_diff = round(
            winner_expl.score_breakdown.academic_subtotal
            - loser_expl.score_breakdown.academic_subtotal,
            6,
        )
        ctx_diff = round(
            winner_expl.score_breakdown.contextual_subtotal
            - loser_expl.score_breakdown.contextual_subtotal,
            6,
        )
        rerank_diff = round(
            winner_expl.score_breakdown.reranker_adjustment
            - loser_expl.score_breakdown.reranker_adjustment,
            6,
        )
        div_diff = round(
            winner_expl.score_breakdown.diversity_adjustment
            - loser_expl.score_breakdown.diversity_adjustment,
            6,
        )

        # Extract dominant positive drivers of the advantage
        signal_diffs: list[tuple[str, float]] = []
        all_signals = set(winner_expl.signal_contributions.keys()) | set(
            loser_expl.signal_contributions.keys()
        )
        for sig_name in all_signals:
            ca = winner_expl.signal_contributions.get(sig_name)
            cb = loser_expl.signal_contributions.get(sig_name)
            contrib_a = ca.contribution if ca else 0.0
            contrib_b = cb.contribution if cb else 0.0
            diff = round(contrib_a - contrib_b, 6)
            if diff > 1e-4:
                clean_name = sig_name.replace("_", " ").title()
                signal_diffs.append((clean_name, diff))

        signal_diffs.sort(key=lambda x: -x[1])
        dominant_factors = [f"{name} (+{diff:.4f})" for name, diff in signal_diffs[:3]]
        if div_diff > 1e-4:
            dominant_factors.append(f"Lower Diversity Penalty (+{div_diff:.4f})")
        if rerank_diff > 1e-4:
            dominant_factors.append(f"Neural Reranking Boost (+{rerank_diff:.4f})")

        if dominant_factors:
            summary = (
                f"Candidate {winner_id} outranked {loser_id} by {score_diff:.4f} score difference, "
                f"driven primarily by {', '.join(dominant_factors[:2])}."
            )
        else:
            summary = (
                f"Candidate {winner_id} outranked {loser_id} by {score_diff:.4f} composite score difference."
            )

        return ComparativeExplanation(
            winner_id=winner_id,
            loser_id=loser_id,
            score_difference=score_diff,
            relevance_difference=rel_diff,
            academic_difference=acad_diff,
            contextual_difference=ctx_diff,
            reranker_difference=rerank_diff,
            diversity_difference=div_diff,
            dominant_factors=dominant_factors,
            summary=summary,
        )


# Module-level default singleton instance
result_explainer = ResultExplainer()
