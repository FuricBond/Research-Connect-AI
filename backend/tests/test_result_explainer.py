"""
Unit and Integration tests for ResultExplainer and Explainability Layer in app.explainability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid
import pytest

from app.explainability.result_explainer import (
    ExplainedResult,
    ProvenanceEvidence,
    ResultExplainer,
    ResultExplanation,
    SignalContribution,
    TopicEvidence,
    result_explainer,
)
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import ResearchWorkModel
from app.ranking.hybrid_ranker import (
    RankedCandidate,
    RankerWeights,
    RankingMode,
    hybrid_ranker,
)
from app.repositories.lexical_repository import LexicalSearchResult
from app.repositories.vector_repository import VectorSearchResult
from app.services.hybrid_search_service import HybridSearchResult
from app.services.research_opportunity_matching_service import ResearchOpportunityMatch
from app.services.similar_research_service import SimilarResearchResult


# ── A. UNIT TESTS: BASIC EXPLANATIONS & STRENGTHS ────────────────────────────


class TestBasicExplanations:
    """Tests for basic signal explanation, reason generation, and thresholds."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer(
            high_threshold=0.75,
            positive_threshold=0.50,
            weak_threshold=0.25,
            max_reasons=5,
        )

    def test_high_semantic_similarity_produces_strong_reason(self, explainer):
        cand = RankedCandidate(
            entity_id=uuid.uuid4(),
            entity_type="research_work",
            rank=1,
            final_score=0.90,
            semantic_score=0.92,
            lexical_score=0.40,
            topic_score=0.30,
            type_score=0.0,
            freshness_score=0.0,
            urgency_score=0.0,
            retrieval_sources=["semantic"],
        )

        explanation = explainer.explain(cand, mode=RankingMode.GENERAL)

        assert "semantic_similarity" in explanation.primary_factors
        assert any("semantic similarity" in s.lower() for s in explanation.strengths)
        assert explanation.signal_contributions["semantic_similarity"].qualitative_assessment == "Very Strong"
        assert explanation.signal_contributions["semantic_similarity"].is_primary_driver is True

    def test_strong_topic_similarity_with_shared_topics(self, explainer):
        t1 = uuid.uuid4()
        t2 = uuid.uuid4()
        cand = RankedCandidate(
            entity_id=uuid.uuid4(),
            entity_type="research_work",
            rank=1,
            final_score=0.85,
            semantic_score=0.70,
            lexical_score=0.50,
            topic_score=0.88,
            type_score=0.0,
            freshness_score=0.0,
            urgency_score=0.0,
            shared_topic_ids=[t1, t2],
            shared_topic_names=["Computer Vision", "Deep Learning"],
            retrieval_sources=["semantic"],
        )

        explanation = explainer.explain(cand, mode=RankingMode.GENERAL)

        assert any("computer vision" in s.lower() for s in explanation.strengths)
        assert explanation.topic_evidence.topic_similarity == 0.88
        assert "Computer Vision" in explanation.topic_evidence.description

    def test_strong_lexical_similarity_reason(self, explainer):
        cand = RankedCandidate(
            entity_id=uuid.uuid4(),
            entity_type="research_work",
            rank=1,
            final_score=0.80,
            semantic_score=0.60,
            lexical_score=0.85,
            topic_score=0.40,
            type_score=0.0,
            freshness_score=0.0,
            urgency_score=0.0,
            retrieval_sources=["lexical"],
        )

        explanation = explainer.explain(cand, mode=RankingMode.GENERAL)

        assert any("keyword" in s.lower() or "lexical" in s.lower() for s in explanation.strengths)
        assert explanation.signal_contributions["lexical_relevance"].qualitative_assessment == "Very Strong"


# ── B. UNIT TESTS: LIMITATIONS & WEAK SIGNALS ─────────────────────────────────


class TestWeakSignalsAndLimitations:
    """Tests for negative signals, limiting factors, and missing metadata differentiation."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer()

    def test_weak_semantic_similarity_produces_limitation(self, explainer):
        cand = RankedCandidate(
            entity_id=uuid.uuid4(),
            entity_type="research_work",
            rank=1,
            final_score=0.45,
            semantic_score=0.15,  # weak (< 0.25)
            lexical_score=0.80,
            topic_score=0.80,
            type_score=0.0,
            freshness_score=0.0,
            urgency_score=0.0,
            retrieval_sources=["lexical"],
        )

        explanation = explainer.explain(cand, mode=RankingMode.GENERAL)

        assert any("low semantic similarity" in lim.lower() for lim in explanation.limitations)
        assert explanation.signal_contributions["semantic_similarity"].qualitative_assessment == "Minimal"

    def test_old_publication_produces_freshness_limitation_when_year_known(self, explainer):
        work_model = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Early Neural Networks",
            publication_year=2000,
        )
        cand = RankedCandidate(
            entity_id=work_model.id,
            entity_type="research_work",
            rank=1,
            final_score=0.65,
            semantic_score=0.85,
            lexical_score=0.60,
            topic_score=0.70,
            type_score=0.0,
            freshness_score=0.03,  # old publication (< 0.25)
            urgency_score=0.0,
            retrieval_sources=["semantic"],
            candidate=work_model,
        )

        explanation = explainer.explain(cand, mode=RankingMode.RESEARCH_SIMILARITY)

        assert any("older publication" in lim.lower() for lim in explanation.limitations)
        assert explanation.signal_contributions["publication_freshness"].is_available is True

    def test_missing_year_does_not_claim_old_publication(self, explainer):
        # Candidate with NO attached work and NO freshness signal
        cand = RankedCandidate(
            entity_id=uuid.uuid4(),
            entity_type="research_work",
            rank=1,
            final_score=0.75,
            semantic_score=0.85,
            lexical_score=0.60,
            topic_score=0.70,
            type_score=0.0,
            freshness_score=0.0,
            urgency_score=0.0,
            retrieval_sources=["semantic"],
            candidate=None,
        )

        explanation = explainer.explain(cand, mode=RankingMode.RESEARCH_SIMILARITY)

        # Must NOT claim older publication if date was unavailable
        assert not any("older publication" in lim.lower() for lim in explanation.limitations)
        assert explanation.signal_contributions["publication_freshness"].is_available is False

    def test_no_false_urgency_claim_when_deadline_is_expired_or_absent(self, explainer):
        opp_model = OpportunityModel(
            id=uuid.uuid4(),
            title="Past Workshop 2020",
            submission_deadline=datetime(2020, 1, 1, tzinfo=timezone.utc),  # expired
        )
        cand = RankedCandidate(
            entity_id=opp_model.id,
            entity_type="opportunity",
            rank=1,
            final_score=0.70,
            semantic_score=0.80,
            lexical_score=0.50,
            topic_score=0.70,
            type_score=1.0,
            freshness_score=0.0,
            urgency_score=0.0,  # 0.0 because expired
            retrieval_sources=["semantic"],
            candidate=opp_model,
        )

        explanation = explainer.explain(
            cand,
            mode=RankingMode.RESEARCH_OPPORTUNITY,
            reference_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )

        # Must not claim deadline is approaching
        assert not any("approaching" in s.lower() or "immediate term" in s.lower() for s in explanation.strengths)
        assert explanation.signal_contributions["deadline_urgency"].score == 0.0


# ── C. UNIT TESTS: OPPORTUNITY & SIMILAR RESEARCH INTEGRATION ────────────────


class TestOpportunityAndSimilarResearchExplainability:
    """Tests for explaining ResearchOpportunityMatch and SimilarResearchResult domain objects."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer()

    def test_research_opportunity_match_full_explanation(self, explainer):
        opp_id = uuid.uuid4()
        ref_time = datetime(2026, 9, 1, tzinfo=timezone.utc)
        opp_model = OpportunityModel(
            id=opp_id,
            title="ACM Conference on Information Systems",
            opportunity_type="CONFERENCE",
            submission_deadline=datetime(2026, 9, 10, tzinfo=timezone.utc),  # 9 days remaining -> high urgency
        )

        match = ResearchOpportunityMatch(
            research_work_id=uuid.uuid4(),
            opportunity_id=opp_id,
            match_score=0.82,
            semantic_similarity=0.88,
            lexical_similarity=0.70,
            topic_similarity=0.80,
            type_compatibility=1.00,
            rank=1,
            shared_topic_ids=[uuid.uuid4()],
            shared_topic_names=["Information Systems"],
            retrieval_sources=["semantic", "lexical"],
            opportunity=opp_model,
        )

        explanation = explainer.explain(
            match,
            mode=RankingMode.RESEARCH_OPPORTUNITY,
            reference_time=ref_time,
        )

        assert "academic opportunity" in explanation.summary.lower()
        assert any("type is highly compatible" in s.lower() for s in explanation.strengths)
        assert any("deadline" in s.lower() for s in explanation.strengths)
        assert any("independently surfaced by both" in s.lower() for s in explanation.strengths)
        assert explanation.provenance_evidence.retrieval_sources == ["lexical", "semantic"]
        assert explanation.signal_contributions["type_compatibility"].score == 1.00

    def test_similar_research_result_explanation(self, explainer):
        work_id = uuid.uuid4()
        work_model = ResearchWorkModel(
            id=work_id,
            title="Attention Is All You Need",
            publication_year=2025,  # recent
        )

        sim_res = SimilarResearchResult(
            source_work_id=uuid.uuid4(),
            candidate_work_id=work_id,
            combined_similarity=0.88,
            semantic_similarity=0.92,
            lexical_similarity=0.65,
            topic_similarity=0.85,
            rank=1,
            shared_topic_ids=[uuid.uuid4()],
            shared_topic_names=["Natural Language Processing"],
            retrieval_sources=["semantic"],
            candidate_work=work_model,
        )

        explanation = explainer.explain(
            sim_res,
            mode=RankingMode.RESEARCH_SIMILARITY,
            reference_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        assert "similar research work" in explanation.summary.lower()
        assert any("recent publication" in s.lower() for s in explanation.strengths)
        assert "Natural Language Processing" in explanation.topic_evidence.description
        assert explanation.signal_contributions["semantic_similarity"].is_primary_driver is True


# ── D. UNIT TESTS: SCORE CONTRIBUTION & WEIGHT ALIGNMENT ─────────────────────


class TestScoreContributionAlignment:
    """Tests for exact mathematical contribution calculation matching Phase 2.4E weights."""

    def test_contribution_formula_and_values(self):
        explainer = ResultExplainer()
        custom_weights = RankerWeights(
            semantic_weight=0.50,
            lexical_weight=0.20,
            topic_weight=0.20,
            freshness_weight=0.10,
        )

        cand = {
            "entity_id": uuid.uuid4(),
            "entity_type": "research_work",
            "semantic_similarity": 0.80,
            "lexical_similarity": 0.60,
            "topic_similarity": 0.90,
            "freshness": 0.70,
            "retrieval_sources": ["semantic"],
        }

        explanation = explainer.explain(cand, weights=custom_weights)

        # Contributions:
        # sem: 0.80 * 0.50 = 0.40
        # lex: 0.60 * 0.20 = 0.12
        # top: 0.90 * 0.20 = 0.18
        # fresh: 0.70 * 0.10 = 0.07
        sc = explanation.signal_contributions
        assert math.isclose(sc["semantic_similarity"].contribution, 0.40, abs_tol=1e-5)
        assert math.isclose(sc["lexical_relevance"].contribution, 0.12, abs_tol=1e-5)
        assert math.isclose(sc["topic_compatibility"].contribution, 0.18, abs_tol=1e-5)
        assert math.isclose(sc["publication_freshness"].contribution, 0.07, abs_tol=1e-5)

        # Primary factor must be semantic similarity (0.40 contribution)
        assert explanation.primary_factors[0] == "semantic_similarity"
        assert explanation.primary_factors[1] == "topic_compatibility"


# ── E. UNIT TESTS: DETERMINISM & BATCH EXPLANATION ────────────────────────────


class TestDeterminismAndBatching:
    """Tests ensuring strictly reproducible explanations and batch operations."""

    def test_deterministic_output_across_repeated_calls(self):
        explainer = ResultExplainer()
        cand = RankedCandidate(
            entity_id=uuid.uuid4(),
            entity_type="research_work",
            rank=1,
            final_score=0.85,
            semantic_score=0.80,
            lexical_score=0.70,
            topic_score=0.75,
            type_score=0.0,
            freshness_score=0.50,
            urgency_score=0.0,
            retrieval_sources=["semantic", "lexical"],
            shared_topic_names=["AI", "Robotics"],
        )

        expl1 = explainer.explain(cand, mode=RankingMode.RESEARCH_SIMILARITY)
        expl2 = explainer.explain(cand, mode=RankingMode.RESEARCH_SIMILARITY)

        assert expl1.summary == expl2.summary
        assert expl1.strengths == expl2.strengths
        assert expl1.limitations == expl2.limitations
        assert expl1.primary_factors == expl2.primary_factors
        assert expl1.topic_evidence == expl2.topic_evidence
        assert expl1.provenance_evidence == expl2.provenance_evidence

    def test_explain_batch_returns_explained_results(self):
        explainer = ResultExplainer()
        cand1 = {"entity_id": uuid.uuid4(), "semantic_similarity": 0.9}
        cand2 = {"entity_id": uuid.uuid4(), "semantic_similarity": 0.4}

        batch_results = explainer.explain_batch([cand1, cand2], mode=RankingMode.GENERAL)

        assert len(batch_results) == 2
        for item in batch_results:
            assert isinstance(item, ExplainedResult)
            assert isinstance(item.explanation, ResultExplanation)

    def test_singleton_instance_available(self):
        assert isinstance(result_explainer, ResultExplainer)


def make_ranked_candidate(
    entity_id: uuid.UUID | None = None,
    entity_type: str = "research_work",
    rank: int = 1,
    final_score: float = 0.80,
    semantic_score: float = 0.80,
    lexical_score: float = 0.50,
    topic_score: float = 0.50,
    type_score: float = 0.0,
    freshness_score: float = 0.0,
    urgency_score: float = 0.0,
    quality_score: float = 0.0,
    citation_score: float = 0.0,
    author_prominence_score: float = 0.0,
    author_position_score: float = 0.50,
    institution_score: float = 0.0,
    venue_score: float = 0.0,
    open_access_score: float = 0.35,
    retrieval_sources: list[str] | None = None,
    diversity_adjustment: float = 0.0,
    redundancy_score: float = 0.0,
    novelty_score: float = 0.0,
    reranker_adjustment: float = 0.0,
    candidate: Any = None,
    **kwargs: Any,
) -> RankedCandidate:
    return RankedCandidate(
        entity_id=entity_id or uuid.uuid4(),
        entity_type=entity_type,
        rank=rank,
        final_score=final_score,
        semantic_score=semantic_score,
        lexical_score=lexical_score,
        topic_score=topic_score,
        type_score=type_score,
        freshness_score=freshness_score,
        urgency_score=urgency_score,
        quality_score=quality_score,
        citation_score=citation_score,
        author_prominence_score=author_prominence_score,
        author_position_score=author_position_score,
        institution_score=institution_score,
        venue_score=venue_score,
        open_access_score=open_access_score,
        retrieval_sources=retrieval_sources or ["semantic"],
        diversity_adjustment=diversity_adjustment,
        redundancy_score=redundancy_score,
        novelty_score=novelty_score,
        reranker_adjustment=reranker_adjustment,
        candidate=candidate,
        **kwargs,
    )


# ── F. UNIT TESTS: PHASE 2.5F SCORE ATTRIBUTION & DECOMPOSITION ─────────────


class TestPhase25FExactAttributionAndDecomposition:
    """Rigorous mathematical tests for Phase 2.5F exact score attribution."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer()

    def test_mathematical_score_reconciliation_invariant(self, explainer):
        raw_cand = {
            "entity_id": uuid.uuid4(),
            "semantic_similarity": 0.90,
            "lexical_similarity": 0.60,
            "topic_similarity": 0.80,
            "type_compatibility": 0.50,
            "freshness": 0.70,
            "citation_impact": 0.85,
            "author_prominence": 0.75,
            "author_position": 0.90,
            "institution_prestige": 0.65,
            "venue_prestige": 0.80,
            "open_access_tier": 0.70,
            "retrieval_sources": ["semantic", "lexical"],
        }

        for mode in [RankingMode.GENERAL, RankingMode.RESEARCH_SIMILARITY, RankingMode.RESEARCH_OPPORTUNITY]:
            ranked_list = hybrid_ranker.rank([raw_cand], mode=mode)
            cand = ranked_list[0]
            expl = explainer.explain(cand, mode=mode)
            sb = expl.score_breakdown
            assert sb is not None
            assert sb.is_reconciled is True
            assert sb.reconciliation_gap <= 1e-5

            # Sum of all signal contributions == base_score
            total_contributions = sum(sc.contribution for sc in expl.signal_contributions.values())
            assert math.isclose(total_contributions, expl.base_score, abs_tol=1e-5)
            assert math.isclose(total_contributions, sb.base_score, abs_tol=1e-5)

            # Subtotals sum == base_score
            subtotals_sum = sb.relevance_subtotal + sb.contextual_subtotal + sb.academic_subtotal
            assert math.isclose(subtotals_sum, sb.base_score, abs_tol=1e-5)

            # Base score + adjustments == final_score
            reconstructed_final = sb.base_score + sb.reranker_adjustment + sb.diversity_adjustment
            assert math.isclose(reconstructed_final, sb.final_score, abs_tol=1e-5)


class TestPhase25FAcademicQualityEvidenceTruthfulness:
    """Adversarial and boundary tests ensuring academic claims map strictly to truth."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer()

    def test_zero_citations_never_claims_high_impact(self, explainer):
        work = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Brand New Paper",
            cited_by_count=0,
        )
        cand = make_ranked_candidate(
            entity_id=work.id,
            rank=1,
            final_score=0.75,
            semantic_score=0.95,
            citation_score=0.0,
            candidate=work,
        )

        expl = explainer.explain(cand, mode=RankingMode.GENERAL)
        assert not any("citation" in s.lower() or "cited" in s.lower() for s in expl.strengths)
        assert "citation_impact" not in expl.primary_factors
        if expl.academic_evidence:
            assert expl.academic_evidence.citation_count == 0

    def test_missing_venue_produces_no_false_venue_claims(self, explainer):
        work = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Unpublished Manuscript",
            primary_source_id=None,
        )
        cand = make_ranked_candidate(
            entity_id=work.id,
            rank=1,
            final_score=0.60,
            semantic_score=0.70,
            venue_score=0.0,
            candidate=work,
        )

        expl = explainer.explain(cand, mode=RankingMode.GENERAL)
        assert not any("prestigious venue" in s.lower() or "top-tier venue" in s.lower() for s in expl.strengths)
        assert "venue_prestige" not in expl.primary_factors

    def test_high_academic_impact_with_real_metadata(self, explainer):
        academic_weights = RankerWeights(
            semantic_weight=0.70,
            lexical_weight=0.10,
            topic_weight=0.05,
            citation_weight=0.05,
            venue_weight=0.05,
            open_access_weight=0.05,
        )
        cand = make_ranked_candidate(
            rank=1,
            final_score=0.92,
            semantic_score=0.85,
            citation_score=0.95,
            author_prominence_score=0.90,
            venue_score=0.92,
            open_access_score=0.85,
        )

        expl = explainer.explain(cand, weights=academic_weights)
        assert any("scholarly impact" in s.lower() or "citation" in s.lower() for s in expl.strengths)
        assert any("venue" in s.lower() for s in expl.strengths)


class TestPhase25FZeroWeightAndModeAwareness:
    """Tests ensuring zero-weight signals are suppressed and active mode weights govern attribution."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer()

    def test_zero_weight_signal_suppression(self, explainer):
        # In research similarity, urgency_weight is 0.0
        cand = make_ranked_candidate(
            rank=1,
            final_score=0.80,
            semantic_score=0.90,
            urgency_score=1.00,  # Max urgency value, but weight is 0.0!
        )

        expl = explainer.explain(cand, mode=RankingMode.RESEARCH_SIMILARITY)
        urg_contrib = expl.signal_contributions["deadline_urgency"]
        assert urg_contrib.weight == 0.0
        assert urg_contrib.contribution == 0.0
        assert urg_contrib.is_active is False
        assert urg_contrib.is_primary_driver is False
        assert "deadline_urgency" not in expl.primary_factors
        assert not any("deadline" in s.lower() or "urgency" in s.lower() for s in expl.strengths)

    def test_mode_specific_weight_attribution(self, explainer):
        cand = make_ranked_candidate(
            rank=1,
            final_score=0.85,
            semantic_score=0.90,
            type_score=1.00,
        )

        expl_gen = explainer.explain(cand, mode=RankingMode.GENERAL)
        expl_opp = explainer.explain(cand, mode=RankingMode.RESEARCH_OPPORTUNITY)

        w_gen = expl_gen.signal_contributions["type_compatibility"].weight
        w_opp = expl_opp.signal_contributions["type_compatibility"].weight
        assert w_opp > w_gen


class TestPhase25FCrossEncoderAndDiversityReconciliation:
    """Tests for neural cross-encoder and diversity adjustment honesty and attribution."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer()

    def test_diversity_penalty_attribution(self, explainer):
        cand = make_ranked_candidate(
            rank=3,
            final_score=0.72,
            semantic_score=0.85,
            diversity_adjustment=-0.045,
            redundancy_score=0.80,
            novelty_score=0.10,
        )

        expl = explainer.explain(cand, mode=RankingMode.GENERAL)
        assert expl.diversity_explanation is not None
        assert expl.diversity_explanation.enabled is True
        assert expl.diversity_explanation.adjustment == -0.045
        assert expl.diversity_explanation.redundancy_score == 0.80
        assert any("redundancy penalty" in lim.lower() for lim in expl.limitations)
        assert expl.score_breakdown.diversity_adjustment == -0.045

    def test_diversity_novelty_boost_attribution(self, explainer):
        cand = make_ranked_candidate(
            rank=2,
            final_score=0.82,
            semantic_score=0.80,
            diversity_adjustment=0.020,
            redundancy_score=0.05,
            novelty_score=0.85,
        )

        expl = explainer.explain(cand, mode=RankingMode.GENERAL)
        assert expl.diversity_explanation is not None
        assert expl.diversity_explanation.adjustment == 0.020
        assert expl.diversity_explanation.novelty_score == 0.85
        assert any("novelty boost" in s.lower() for s in expl.strengths)

    def test_cross_encoder_fallback_honesty(self, explainer):
        cand = make_ranked_candidate(
            rank=1,
            final_score=0.80,
            semantic_score=0.80,
            reranker_adjustment=0.0,
        )

        expl = explainer.explain(cand, mode=RankingMode.GENERAL)
        assert expl.score_breakdown.reranker_adjustment == 0.0


class TestPhase25FComparativeExplanations:
    """Tests for pairwise comparative ranking attribution."""

    @pytest.fixture
    def explainer(self) -> ResultExplainer:
        return ResultExplainer()

    def test_comparative_attribution_identifies_winner_and_dominant_dimension(self, explainer):
        id_a = uuid.uuid4()
        id_b = uuid.uuid4()

        cand_a = make_ranked_candidate(
            entity_id=id_a,
            rank=1,
            final_score=0.88,
            semantic_score=0.95,
            citation_score=0.50,
        )
        cand_b = make_ranked_candidate(
            entity_id=id_b,
            rank=2,
            final_score=0.74,
            semantic_score=0.60,
            citation_score=0.55,
        )

        comp = explainer.compare(cand_a, cand_b, mode=RankingMode.GENERAL)
        assert comp.winner_id == id_a
        assert comp.loser_id == id_b
        assert comp.score_difference > 0
        assert comp.relevance_difference > 0
        assert any("semantic" in f.lower() or "relevance" in f.lower() for f in comp.dominant_factors)
        assert "outranked" in comp.summary.lower()


