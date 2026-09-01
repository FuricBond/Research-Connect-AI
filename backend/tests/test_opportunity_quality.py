"""
Unit tests for Phase 2.4J — Ranking Hardening & Opportunity Quality Signals.

Covers:
  1. Indexing Tier Evaluation (Tier 1, Tier 2, Tier 3, Unrecognized, Empty/Missing neutrality)
  2. Predatory Risk Penalty Multiplier (Flagged, risk_score gradients, Clean, Missing neutrality)
  3. Status Reliability Scoring (VERIFIED, ACTIVE, UNVERIFIED, ARCHIVED, CANCELLED)
  4. Composite calculate_opportunity_quality integration and boundary conditions
  5. RankerWeights quality_weight validation and normalization
  6. HybridRanker multi-signal candidate ranking with quality signals
  7. Relevance dominance over quality (Quality never overrules high topical/semantic relevance)
  8. Predatory venue downranking
  9. ResultExplainer quality attributions, indexing strengths, and predatory risk warnings
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

import pytest

from app.explainability.result_explainer import ResultExplainer
from app.ranking.hybrid_ranker import HybridRanker, RankedCandidate, RankerWeights, RankingMode
from app.ranking.signals import (
    DEFAULT_NEUTRAL_INDEXING_SCORE,
    INDEXING_TIER_SCORES,
    RankingSignals,
    calculate_indexing_quality,
    calculate_opportunity_quality,
    calculate_predatory_penalty,
    calculate_status_reliability,
)
from app.services.research_opportunity_matching_service import ResearchOpportunityMatch


class TestIndexingTierScoring:
    """Test deterministic academic indexing quality evaluation."""

    def test_tier_1_indexing_gives_perfect_score(self) -> None:
        for idx in ["Scopus", "SCOPUS", "SCI", "SCIE", "Web of Science", "WOS", "IEEE", "IEEE Xplore", "ACM", "PubMed", "Medline"]:
            score = calculate_indexing_quality([idx])
            assert score == 1.00, f"Expected 1.00 for {idx}, got {score}"

    def test_tier_2_indexing_gives_recognized_score(self) -> None:
        for idx in ["DBLP", "EI Compendex", "DOAJ", "Springer", "Elsevier", "Inspec", "ERIC"]:
            score = calculate_indexing_quality([idx])
            assert score == 0.75, f"Expected 0.75 for {idx}, got {score}"

    def test_tier_3_indexing_gives_standard_score(self) -> None:
        for idx in ["Google Scholar", "Crossref", "Semantic Scholar", "WikiCFP"]:
            score = calculate_indexing_quality([idx])
            assert score == 0.50, f"Expected 0.50 for {idx}, got {score}"

    def test_unrecognized_indexing_gives_lower_score(self) -> None:
        score = calculate_indexing_quality(["Some Completely Unknown Directory"])
        assert score == 0.40

    def test_multi_indexer_takes_highest_tier(self) -> None:
        score = calculate_indexing_quality(["Google Scholar", "Scopus", "Unknown Index"])
        assert score == 1.00

    def test_case_insensitivity_and_whitespace(self) -> None:
        score = calculate_indexing_quality(["   scopus   ", "  ieee xplore  "])
        assert score == 1.00

    def test_missing_and_empty_indexing_policy_is_neutral(self) -> None:
        """Missing or empty indexing must return neutral score (0.50) without penalizing scraped items."""
        assert calculate_indexing_quality(None) == DEFAULT_NEUTRAL_INDEXING_SCORE
        assert calculate_indexing_quality([]) == DEFAULT_NEUTRAL_INDEXING_SCORE
        assert calculate_indexing_quality(["", "   "]) == DEFAULT_NEUTRAL_INDEXING_SCORE
        assert calculate_indexing_quality("invalid_type") == DEFAULT_NEUTRAL_INDEXING_SCORE  # type: ignore[arg-type]


class TestPredatoryPenalty:
    """Test multiplicative predatory risk penalty calculations."""

    def test_flagged_predatory_applies_maximum_penalty(self) -> None:
        penalty = calculate_predatory_penalty(is_predatory_flag=True)
        assert penalty == 0.20

    def test_custom_penalty_factor(self) -> None:
        penalty = calculate_predatory_penalty(is_predatory_flag=True, penalty_factor=0.10)
        assert penalty == 0.10

    def test_high_risk_score_applies_penalty(self) -> None:
        penalty = calculate_predatory_penalty(is_predatory_flag=False, risk_score=0.85)
        assert penalty == 0.20

    def test_moderate_risk_score_graduated_penalty(self) -> None:
        penalty = calculate_predatory_penalty(is_predatory_flag=False, risk_score=0.40)
        assert penalty == 0.80  # 1.0 - (0.40 * 0.50)

    def test_clean_venue_zero_penalty(self) -> None:
        penalty = calculate_predatory_penalty(is_predatory_flag=False, risk_score=0.0)
        assert penalty == 1.00

    def test_missing_metadata_neutral_no_penalty(self) -> None:
        """Missing predatory flags must NOT trigger a false positive penalty."""
        assert calculate_predatory_penalty(is_predatory_flag=None, risk_score=None) == 1.00


class TestStatusReliability:
    """Test opportunity lifecycle status reliability scoring."""

    def test_verified_and_active_status(self) -> None:
        assert calculate_status_reliability("VERIFIED") == 1.00
        assert calculate_status_reliability("ACTIVE") == 1.00
        assert calculate_status_reliability(" active ") == 1.00

    def test_unverified_status(self) -> None:
        assert calculate_status_reliability("UNVERIFIED") == 0.70

    def test_archived_and_cancelled_status(self) -> None:
        assert calculate_status_reliability("ARCHIVED") == 0.30
        assert calculate_status_reliability("CANCELLED") == 0.00

    def test_missing_status_neutral(self) -> None:
        assert calculate_status_reliability(None) == 0.70
        assert calculate_status_reliability("") == 0.70


class TestCalculateOpportunityQuality:
    """Test composite opportunity quality calculation."""

    def test_premium_verified_venue_score(self) -> None:
        score = calculate_opportunity_quality(
            indexing=["Scopus", "IEEE"],
            status="VERIFIED",
            is_predatory_flag=False,
        )
        assert score == 1.00

    def test_predatory_venue_severely_penalized(self) -> None:
        # Even with Scopus indexing claimed, predatory flag reduces score by factor of 0.20
        score = calculate_opportunity_quality(
            indexing=["Scopus"],
            status="ACTIVE",
            is_predatory_flag=True,
            risk_score=0.90,
        )
        assert score == 0.20

    def test_missing_metadata_receives_neutral_score(self) -> None:
        score = calculate_opportunity_quality(
            indexing=None,
            status=None,
            is_predatory_flag=None,
            risk_score=None,
        )
        assert 0.50 <= score <= 0.65

    def test_extract_from_dict_and_object(self) -> None:
        opp_dict = {
            "indexing": ["ACM"],
            "status": "VERIFIED",
            "is_predatory_flag": False,
        }
        score = calculate_opportunity_quality(opp_dict)
        assert score == 1.00

    def test_score_bounded_in_0_to_1(self) -> None:
        for p in [True, False, None]:
            for r in [0.0, 0.5, 1.0, None]:
                for idx in [["Scopus"], ["Unknown"], [], None]:
                    s = calculate_opportunity_quality(
                        indexing=idx,
                        is_predatory_flag=p,
                        risk_score=r,
                        status="ACTIVE",
                    )
                    assert 0.0 <= s <= 1.0


class TestHybridRankerQualityIntegration:
    """Test RankerWeights and HybridRanker quality scoring."""

    def test_ranker_weights_validation_and_normalization(self) -> None:
        w = RankerWeights(
            semantic_weight=0.40,
            lexical_weight=0.15,
            topic_weight=0.20,
            type_weight=0.10,
            urgency_weight=0.05,
            quality_weight=0.10,
        )
        w.validate()
        norm_w = w.normalized()
        total = (
            norm_w.semantic_weight
            + norm_w.lexical_weight
            + norm_w.topic_weight
            + norm_w.type_weight
            + norm_w.urgency_weight
            + norm_w.quality_weight
        )
        assert math.isclose(total, 1.0, rel_tol=1e-4)

    def test_ranker_weights_rejects_negative_or_nan(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            RankerWeights(quality_weight=-0.5).validate()
        with pytest.raises(ValueError, match="cannot be NaN"):
            RankerWeights(quality_weight=float("nan")).validate()

    def test_opportunity_mode_defaults_include_quality(self) -> None:
        ranker = HybridRanker()
        weights = ranker.resolve_weights(RankingMode.RESEARCH_OPPORTUNITY)
        assert weights.quality_weight == 0.10
        assert weights.semantic_weight == 0.40
        assert weights.urgency_weight == 0.05

    def test_general_mode_preserves_zero_quality_weight(self) -> None:
        ranker = HybridRanker()
        weights = ranker.resolve_weights(RankingMode.GENERAL)
        assert weights.quality_weight == 0.0

    def test_quality_indexing_prioritization(self) -> None:
        """Equal relevance candidates are prioritized by indexing quality."""
        ranker = HybridRanker()
        c_scopus = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.85,
            "lexical_similarity": 0.50,
            "topic_similarity": 0.80,
            "type_compatibility": 0.80,
            "indexing": ["Scopus", "IEEE"],
            "status": "VERIFIED",
            "is_predatory_flag": False,
        }
        c_unindexed = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.85,
            "lexical_similarity": 0.50,
            "topic_similarity": 0.80,
            "type_compatibility": 0.80,
            "indexing": [],
            "status": "UNVERIFIED",
            "is_predatory_flag": False,
        }

        results = ranker.rank(
            [c_unindexed, c_scopus],
            mode=RankingMode.RESEARCH_OPPORTUNITY,
        )
        assert results[0].entity_id == c_scopus["id"]
        assert results[0].quality_score > results[1].quality_score

    def test_predatory_downranking(self) -> None:
        """A predatory candidate is severely downranked."""
        ranker = HybridRanker()
        c_clean = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.75,
            "lexical_similarity": 0.40,
            "topic_similarity": 0.70,
            "type_compatibility": 0.80,
            "indexing": ["ACM"],
            "status": "VERIFIED",
            "is_predatory_flag": False,
        }
        c_predatory = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.82,  # slightly higher semantic
            "lexical_similarity": 0.45,
            "topic_similarity": 0.75,
            "type_compatibility": 0.80,
            "indexing": ["Google Scholar"],
            "status": "ACTIVE",
            "is_predatory_flag": True,
            "risk_score": 0.95,
        }

        results = ranker.rank(
            [c_predatory, c_clean],
            mode=RankingMode.RESEARCH_OPPORTUNITY,
        )
        assert results[0].entity_id == c_clean["id"]
        assert results[1].entity_id == c_predatory["id"]

    def test_relevance_dominance_over_quality(self) -> None:
        """Quality does NOT allow an irrelevant venue to outrank a highly relevant one."""
        ranker = HybridRanker()
        c_relevant = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.92,
            "lexical_similarity": 0.85,
            "topic_similarity": 0.90,
            "type_compatibility": 0.90,
            "indexing": ["Google Scholar"],
            "status": "ACTIVE",
            "is_predatory_flag": False,
        }
        c_irrelevant_scopus = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.10,
            "lexical_similarity": 0.00,
            "topic_similarity": 0.05,
            "type_compatibility": 0.50,
            "indexing": ["Scopus", "SCI"],
            "status": "VERIFIED",
            "is_predatory_flag": False,
        }

        results = ranker.rank(
            [c_irrelevant_scopus, c_relevant],
            mode=RankingMode.RESEARCH_OPPORTUNITY,
        )
        assert results[0].entity_id == c_relevant["id"]
        assert results[0].final_score > 0.75
        assert results[1].final_score < 0.35


class TestExplainabilityQualityIntegration:
    """Test ResultExplainer quality signal attributions and warnings."""

    def test_explainer_includes_opportunity_quality_signal(self) -> None:
        explainer = ResultExplainer()
        cand = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.88,
            "lexical_similarity": 0.60,
            "topic_similarity": 0.80,
            "type_compatibility": 0.90,
            "indexing": ["Scopus", "IEEE"],
            "status": "VERIFIED",
            "is_predatory_flag": False,
        }

        explanation = explainer.explain(cand, mode=RankingMode.RESEARCH_OPPORTUNITY)
        assert "opportunity_quality" in explanation.signal_contributions
        sc = explanation.signal_contributions["opportunity_quality"]
        assert sc.score == 1.00
        assert sc.weight == 0.10
        assert sc.qualitative_assessment == "Very Strong"
        assert any("Scopus" in s or "IEEE" in s or "quality" in s.lower() for s in explanation.strengths)

    def test_explainer_warns_on_predatory_risk(self) -> None:
        explainer = ResultExplainer()
        cand = {
            "id": uuid.uuid4(),
            "entity_type": "opportunity",
            "semantic_similarity": 0.80,
            "lexical_similarity": 0.50,
            "topic_similarity": 0.70,
            "type_compatibility": 0.80,
            "indexing": [],
            "status": "ACTIVE",
            "is_predatory_flag": True,
            "risk_score": 0.90,
        }

        explanation = explainer.explain(cand, mode=RankingMode.RESEARCH_OPPORTUNITY)
        assert any("predatory" in limit.lower() for limit in explanation.limitations)
