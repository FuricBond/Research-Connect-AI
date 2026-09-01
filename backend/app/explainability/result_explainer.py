"""
Explainable Results Layer for Phase 2.4F.

Takes candidate objects produced by upstream retrieval, matching, or hybrid ranking
(e.g., RankedCandidate, SimilarResearchResult, ResearchOpportunityMatch, HybridSearchResult)
and generates:
  1. Structured, machine-readable signal contributions and evidence.
  2. Deterministic, human-readable qualitative summaries, strengths, and limitations.

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
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankerWeights,
    RankingMode,
    hybrid_ranker,
)
from app.ranking.signals import validate_signal


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
        Active weight applied to this signal in the ranking model in [0.0, 1.0].
    contribution:
        Weighted score contribution (score * weight) in [0.0, 1.0].
    qualitative_assessment:
        Descriptive assessment ('Very Strong', 'Moderate', 'Weak', 'Not Available', etc.).
    is_available:
        Whether the candidate actually provided data for this signal.
    is_primary_driver:
        Whether this signal is among the dominant positive contributors to the final rank.
    """

    signal_name: str
    score: float
    weight: float
    contribution: float
    qualitative_assessment: str
    is_available: bool = True
    is_primary_driver: bool = False


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
class ResultExplanation:
    """
    Complete explanation for a ranked candidate result.

    Attributes
    ----------
    summary:
        Concise 1-2 sentence overview of why the result was selected and ranked.
    strengths:
        Ordered list of key positive factors supporting the match.
    limitations:
        Ordered list of limiting factors or low-signal characteristics.
    signal_contributions:
        Dictionary mapping signal names to structured SignalContribution objects.
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
            Complete explanation model with summary, strengths, limitations, and signal attributions.
        """
        # 1. Resolve Active Weights for Mode
        active_weights = self.ranker.resolve_weights(mode, weights)
        active_weights.validate()

        # 2. Extract Signals & Metadata
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
        )

        rank_pos = getattr(candidate, "rank", 0)
        final_score = getattr(
            candidate,
            "final_score",
            getattr(
                candidate,
                "combined_similarity",
                getattr(candidate, "match_score", getattr(candidate, "hybrid_score", 0.0)),
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

        # 4. Build Structured Signal Contributions
        contributions: dict[str, SignalContribution] = {}

        signal_defs = [
            (
                "semantic_similarity",
                signals.semantic_similarity,
                active_weights.semantic_weight,
                has_embedding,
            ),
            (
                "lexical_relevance",
                signals.lexical_similarity,
                active_weights.lexical_weight,
                has_lexical,
            ),
            (
                "topic_compatibility",
                signals.topic_similarity,
                active_weights.topic_weight,
                has_topics,
            ),
            (
                "type_compatibility",
                signals.type_compatibility,
                active_weights.type_weight,
                has_type,
            ),
            (
                "opportunity_quality",
                signals.opportunity_quality,
                active_weights.quality_weight,
                has_quality,
            ),
            (
                "publication_freshness",
                signals.freshness,
                active_weights.freshness_weight,
                has_freshness,
            ),
            (
                "deadline_urgency",
                signals.urgency,
                active_weights.urgency_weight,
                has_urgency,
            ),
        ]

        active_contributions: list[tuple[str, float, float]] = []

        for name, score, weight, is_avail in signal_defs:
            if weight > 0.0 or is_avail:
                contrib_val = round(score * weight, 6)
                if weight > 0.0 and is_avail and score >= self.positive_threshold:
                    active_contributions.append((name, contrib_val, score))

                qual_label = self._get_qualitative_label(score, is_avail)
                contributions[name] = SignalContribution(
                    signal_name=name,
                    score=score,
                    weight=weight,
                    contribution=contrib_val,
                    qualitative_assessment=qual_label,
                    is_available=is_avail,
                    is_primary_driver=False,
                )

        # Mark primary drivers (top active contributors by contribution value)
        active_contributions.sort(key=lambda x: (-x[1], -x[2]))
        primary_factor_names = [item[0] for item in active_contributions[:2]]

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
                )

        # 5. Extract Strengths (Positive Human-Readable Reasons)
        strengths: list[str] = []

        # Semantic strength
        if has_embedding and signals.semantic_similarity >= self.high_threshold:
            strengths.append(
                "Strong semantic similarity reflecting deep conceptual and contextual alignment."
            )
        elif has_embedding and signals.semantic_similarity >= self.positive_threshold:
            strengths.append(
                "Moderate semantic similarity to the source research concepts."
            )

        # Topic strength
        if has_topics and signals.topic_similarity >= self.high_threshold:
            if shared_names:
                topic_str = ", ".join(shared_names[:3])
                strengths.append(
                    f"Strong topical alignment in shared fields ({topic_str})."
                )
            else:
                strengths.append(
                    "Strong topical alignment across shared canonical research areas."
                )
        elif has_topics and signals.topic_similarity >= self.positive_threshold:
            if shared_names:
                strengths.append(
                    f"Moderate topical overlap in {', '.join(shared_names[:2])}."
                )
            else:
                strengths.append("Moderate topical overlap in shared research areas.")
        elif has_topics and signals.topic_similarity > 0.0:
            strengths.append("Related through hierarchical academic taxonomy DAG proximity.")

        # Lexical strength
        if has_lexical and signals.lexical_similarity >= self.high_threshold:
            strengths.append(
                "Substantial keyword and terminology overlap in title and textual metadata."
            )
        elif has_lexical and signals.lexical_similarity >= self.positive_threshold:
            strengths.append("Notable keyword overlap with key terminology.")

        # Type compatibility strength
        if has_type and signals.type_compatibility >= 0.85:
            strengths.append(
                "Publication type is highly compatible with this opportunity category."
            )
        elif has_type and signals.type_compatibility >= 0.65:
            strengths.append(
                "Publication type is moderately compatible with this opportunity category."
            )

        # Opportunity Quality metadata extraction
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

        # Opportunity Quality strength
        if has_quality and signals.opportunity_quality >= self.high_threshold:
            if indexing_list and any(isinstance(x, str) and x.upper() in {"SCOPUS", "SCI", "SCIE", "WEB OF SCIENCE", "WOS", "IEEE", "ACM", "PUBMED"} for x in indexing_list):
                top_indexers = [x for x in indexing_list if isinstance(x, str) and x.upper() in {"SCOPUS", "SCI", "SCIE", "WEB OF SCIENCE", "WOS", "IEEE", "ACM", "PUBMED"}]
                strengths.append(f"High venue quality indexed in recognized academic databases ({', '.join(top_indexers[:2])}).")
            else:
                strengths.append("High venue quality and verified status reliability.")
        elif has_quality and signals.opportunity_quality >= self.positive_threshold and active_weights.quality_weight > 0.0:
            strengths.append("Verified venue status with standard academic indexing.")

        # Freshness strength
        if has_freshness and signals.freshness >= self.high_threshold:
            strengths.append("Recent publication reflecting contemporary research.")
        elif has_freshness and signals.freshness >= self.positive_threshold:
            strengths.append("Moderately recent publication.")

        # Urgency strength
        if has_urgency and signals.urgency >= self.high_threshold:
            strengths.append("Upcoming submission deadline due in the immediate term.")
        elif has_urgency and signals.urgency >= self.positive_threshold:
            strengths.append("Active upcoming submission deadline within the active window.")

        # Provenance strength
        prov_evidence = self._build_provenance_evidence(signals.retrieval_sources)
        if len(prov_evidence.retrieval_sources) >= 2:
            strengths.append(prov_evidence.description)

        # 6. Extract Limitations (Weaknesses / Limiting Factors)
        limitations: list[str] = []

        # Predatory risk penalty limitation / warning
        if is_pred is True or (risk_sc is not None and float(risk_sc) >= 0.70):
            limitations.append("Flagged for potential predatory publication risk; ranking significantly penalized.")
        elif has_quality and active_weights.quality_weight > 0.0 and signals.opportunity_quality < self.weak_threshold:
            limitations.append("Lower verified venue quality or incomplete indexing status.")

        # Weak semantic similarity
        if (
            has_embedding
            and active_weights.semantic_weight > 0.0
            and signals.semantic_similarity < self.weak_threshold
        ):
            limitations.append("Low semantic similarity to the source research concepts.")

        # Weak topic similarity
        if (
            has_topics
            and active_weights.topic_weight > 0.0
            and signals.topic_similarity < self.weak_threshold
        ):
            limitations.append("Minimal canonical topic overlap.")
        elif not has_topics and active_weights.topic_weight > 0.0:
            limitations.append("No canonical topic associations were identified.")

        # Weak lexical relevance
        if (
            has_lexical
            and active_weights.lexical_weight > 0.0
            and signals.lexical_similarity < self.weak_threshold
        ):
            limitations.append("Limited lexical keyword overlap.")

        # Low type compatibility
        if (
            has_type
            and active_weights.type_weight > 0.0
            and signals.type_compatibility < 0.50
        ):
            limitations.append("Lower conventional compatibility for this publication type.")

        # Older publication
        if (
            has_freshness
            and active_weights.freshness_weight > 0.0
            and signals.freshness < self.weak_threshold
        ):
            limitations.append("Older publication with lower recency weight.")

        # 7. Synthesize Concise Summary
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

        # Cap reasons to max_reasons
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
            final_score=round(float(final_score), 6),
            rank=int(rank_pos),
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


# Module-level default singleton instance
result_explainer = ResultExplainer()
