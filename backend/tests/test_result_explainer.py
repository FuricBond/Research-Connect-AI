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
