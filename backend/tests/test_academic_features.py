"""
Unit and Property-style Tests for Phase 2.5B Academic Feature Extraction & Normalization.
"""
from __future__ import annotations

import math
import uuid
from typing import Any
import pytest

from app.models.research_knowledge import (
    InstitutionModel,
    ResearcherModel,
    ResearchSourceModel,
    ResearchWorkAuthorModel,
    ResearchWorkInstitutionModel,
    ResearchWorkModel,
)
from app.ranking.features import (
    AcademicFeatureExtractor,
    AcademicFeatures,
    academic_feature_extractor,
    calculate_author_position_score,
    calculate_author_prominence,
    calculate_citation_impact,
    calculate_institution_prestige,
    calculate_open_access_tier,
    calculate_venue_prestige,
)


class TestCitationImpact:
    """Test suite for work-level citation impact logarithmic normalization."""

    def test_zero_and_baseline_citations(self):
        assert calculate_citation_impact(0) == 0.0
        assert calculate_citation_impact(0.0) == 0.0

    def test_positive_monotonicity(self):
        cits = [1, 10, 50, 100, 500, 1000, 5000, 10000, 50000]
        scores = [calculate_citation_impact(c) for c in cits]

        # Assert strictly non-decreasing
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1]
            assert 0.0 <= scores[i] <= 1.0

        # Known analytical points for max_citations = 10000
        # log10(1 + 10000) = log10(10001) ~ 4.000043
        assert pytest.approx(scores[-2], abs=1e-4) == 1.0  # at 10000
        assert scores[-1] == 1.0  # saturated beyond 10000

    def test_missing_and_invalid_inputs(self):
        assert calculate_citation_impact(None) == 0.0
        assert calculate_citation_impact(-10) == 0.0
        assert calculate_citation_impact(float("nan")) == 0.0
        assert calculate_citation_impact(float("inf")) == 0.0
        assert calculate_citation_impact("not-a-number") == 0.0
        assert calculate_citation_impact(True) == 0.0

    def test_invalid_max_citations_raises(self):
        with pytest.raises(ValueError):
            calculate_citation_impact(10, max_citations=0.0)
        with pytest.raises(ValueError):
            calculate_citation_impact(10, max_citations=-100.0)


class TestAuthorProminence:
    """Test suite for author prominence feature extraction."""

    def test_empty_or_none_authors(self):
        assert calculate_author_prominence(None) == 0.0
        assert calculate_author_prominence([]) == 0.0

    def test_single_author_citation_scaling(self):
        r1 = ResearcherModel(id=uuid.uuid4(), display_name="Alice", cited_by_count=1000)
        score = calculate_author_prominence([r1])
        assert 0.0 < score < 1.0

        # Monotonicity test
        r2 = ResearcherModel(id=uuid.uuid4(), display_name="Bob", cited_by_count=10000)
        score2 = calculate_author_prominence([r2])
        assert score < score2 <= 1.0

    def test_multi_author_max_aggregation(self):
        r_junior = ResearcherModel(id=uuid.uuid4(), display_name="Junior", cited_by_count=50)
        r_senior = ResearcherModel(id=uuid.uuid4(), display_name="Senior PI", cited_by_count=25000)
        r_mid = ResearcherModel(id=uuid.uuid4(), display_name="Postdoc", cited_by_count=1200)

        single_senior_score = calculate_author_prominence([r_senior])
        multi_author_score = calculate_author_prominence([r_junior, r_senior, r_mid])

        # Multi-author score equals the senior PI max score without consortium inflation
        assert multi_author_score == single_senior_score

    def test_junction_models_and_dict_fixtures(self):
        r = ResearcherModel(id=uuid.uuid4(), display_name="Carol", cited_by_count=5000)
        link = ResearchWorkAuthorModel(
            work_id=uuid.uuid4(),
            researcher_id=r.id,
            author_position="first",
            is_corresponding=True,
        )
        link.researcher = r

        score = calculate_author_prominence([link])
        assert 0.0 < score < 1.0

        dict_author = {"researcher": {"cited_by_count": 5000}}
        dict_score = calculate_author_prominence([dict_author])
        assert dict_score == score


class TestAuthorPosition:
    """Test suite for author position and contribution leadership scoring."""

    def test_explicit_positions(self):
        assert calculate_author_position_score("corresponding") == 1.00
        assert calculate_author_position_score("first") == 0.90
        assert calculate_author_position_score("last") == 0.80
        assert calculate_author_position_score("senior") == 0.80
        assert calculate_author_position_score("middle") == 0.50
        assert calculate_author_position_score("unknown") == 0.50
        assert calculate_author_position_score(None) == 0.50
        assert calculate_author_position_score("") == 0.50

    def test_corresponding_flag_override(self):
        assert calculate_author_position_score("middle", is_corresponding=True) == 1.00
        assert calculate_author_position_score(None, is_corresponding=True) == 1.00

    def test_multi_author_list_resolution(self):
        authors = [
            {"author_position": "middle", "is_corresponding": False},
            {"author_position": "first", "is_corresponding": False},
            {"author_position": "last", "is_corresponding": False},
        ]
        assert calculate_author_position_score(authors=authors) == 0.90

        authors_with_corr = [
            {"author_position": "middle", "is_corresponding": False},
            {"author_position": "last", "is_corresponding": True},
        ]
        assert calculate_author_position_score(authors=authors_with_corr) == 1.00


class TestInstitutionPrestige:
    """Test suite for institution prestige normalization."""

    def test_empty_or_none_institutions(self):
        assert calculate_institution_prestige(None) == 0.0
        assert calculate_institution_prestige([]) == 0.0

    def test_single_institution(self):
        inst = InstitutionModel(id=uuid.uuid4(), display_name="MIT", cited_by_count=200000)
        score = calculate_institution_prestige([inst])
        assert 0.0 < score <= 1.0

    def test_multi_institution_max_aggregation(self):
        inst1 = InstitutionModel(id=uuid.uuid4(), display_name="Small College", cited_by_count=5000)
        inst2 = InstitutionModel(id=uuid.uuid4(), display_name="Top University", cited_by_count=400000)

        score_max = calculate_institution_prestige([inst2])
        score_combined = calculate_institution_prestige([inst1, inst2])
        assert score_combined == score_max

    def test_junction_and_dict_compatibility(self):
        inst = InstitutionModel(id=uuid.uuid4(), display_name="Oxford", cited_by_count=300000)
        link = ResearchWorkInstitutionModel(work_id=uuid.uuid4(), institution_id=inst.id)
        link.institution = inst

        score = calculate_institution_prestige([link])
        assert 0.0 < score <= 1.0

        dict_inst = {"institution": {"cited_by_count": 300000}}
        assert calculate_institution_prestige([dict_inst]) == score


class TestVenuePrestige:
    """Test suite for publication venue and journal prestige scoring."""

    def test_empty_venue(self):
        assert calculate_venue_prestige(None) == 0.0

    def test_citation_based_prestige(self):
        venue_mod = ResearchSourceModel(
            id=uuid.uuid4(),
            display_name="Journal of ML Research",
            cited_by_count=50000,
            is_in_doaj=False,
        )
        score = calculate_venue_prestige(venue_mod)
        assert 0.0 < score < 1.0

    def test_doaj_bonus(self):
        venue_doaj = ResearchSourceModel(
            id=uuid.uuid4(),
            display_name="Open Journal",
            cited_by_count=5000,
            is_in_doaj=True,
        )
        venue_nondoaj = ResearchSourceModel(
            id=uuid.uuid4(),
            display_name="Closed Journal",
            cited_by_count=5000,
            is_in_doaj=False,
        )

        score_doaj = calculate_venue_prestige(venue_doaj)
        score_nondoaj = calculate_venue_prestige(venue_nondoaj)
        assert pytest.approx(score_doaj - score_nondoaj, abs=1e-4) == 0.10

    def test_venue_direct_overrides(self):
        score = calculate_venue_prestige(cited_by_count=100000, is_in_doaj=True)
        assert score == 1.00


class TestOpenAccessTier:
    """Test suite for open access tier normalization."""

    def test_canonical_status_mappings(self):
        assert calculate_open_access_tier("gold") == 1.00
        assert calculate_open_access_tier("diamond") == 1.00
        assert calculate_open_access_tier("hybrid") == 0.85
        assert calculate_open_access_tier("green") == 0.70
        assert calculate_open_access_tier("bronze") == 0.55
        assert calculate_open_access_tier("closed") == 0.20

    def test_missing_status_with_is_oa_flag(self):
        assert calculate_open_access_tier(None, is_oa=True) == 0.70
        assert calculate_open_access_tier(None, is_oa=False) == 0.20
        assert calculate_open_access_tier(None, is_oa=None) == 0.35
        assert calculate_open_access_tier("unknown", is_oa=True) == 0.70


class TestAcademicFeaturesAndExtractor:
    """Test suite for AcademicFeatures container and AcademicFeatureExtractor."""

    def test_academic_features_validation_and_bounds(self):
        features = AcademicFeatures(
            citation_impact=0.75,
            author_prominence=0.80,
            author_position=0.90,
            institution_prestige=0.60,
            venue_prestige=0.70,
            open_access_tier=1.00,
        )
        assert features.to_vector() == [0.75, 0.80, 0.90, 0.60, 0.70, 1.00]
        d = features.to_dict()
        assert d["citation_impact"] == 0.75
        assert d["open_access_tier"] == 1.00

    def test_invalid_features_raise_error(self):
        with pytest.raises(ValueError):
            AcademicFeatures(citation_impact=1.5)  # > 1.0
        with pytest.raises(ValueError):
            AcademicFeatures(citation_impact=-0.1)  # < 0.0
        with pytest.raises(ValueError):
            AcademicFeatures(author_prominence=float("nan"))
        with pytest.raises(ValueError):
            AcademicFeatures(author_prominence=float("inf"))

    def test_extractor_from_full_orm_mock(self):
        work_id = uuid.uuid4()
        inst = InstitutionModel(id=uuid.uuid4(), display_name="Stanford", cited_by_count=350000)
        researcher = ResearcherModel(id=uuid.uuid4(), display_name="John Doe", cited_by_count=20000)
        source = ResearchSourceModel(id=uuid.uuid4(), display_name="Nature", cited_by_count=90000, is_in_doaj=False)

        author_link = ResearchWorkAuthorModel(work_id=work_id, researcher_id=researcher.id, author_position="first", is_corresponding=True)
        author_link.researcher = researcher

        inst_link = ResearchWorkInstitutionModel(work_id=work_id, institution_id=inst.id)
        inst_link.institution = inst

        work = ResearchWorkModel(
            id=work_id,
            title="Transformer Advances in Genomics",
            cited_by_count=4500,
            is_oa=True,
            oa_status="gold",
        )
        work.author_links = [author_link]
        work.institution_links = [inst_link]
        work.primary_source = source

        extractor = AcademicFeatureExtractor()
        feats = extractor.extract_from_work(work)

        assert 0.0 < feats.citation_impact <= 1.0
        assert 0.0 < feats.author_prominence <= 1.0
        assert feats.author_position == 1.00  # is_corresponding
        assert 0.0 < feats.institution_prestige <= 1.0
        assert 0.0 < feats.venue_prestige <= 1.0
        assert feats.open_access_tier == 1.00  # gold

    def test_extractor_determinism_across_multiple_runs(self):
        work = {
            "id": str(uuid.uuid4()),
            "title": "Deterministic Evaluation Sample",
            "cited_by_count": 1200,
            "is_oa": True,
            "oa_status": "hybrid",
            "authors": [
                {"cited_by_count": 8000, "author_position": "first", "is_corresponding": False},
                {"cited_by_count": 30000, "author_position": "last", "is_corresponding": True},
            ],
            "institutions": [{"cited_by_count": 150000}],
            "primary_source": {"cited_by_count": 60000, "is_in_doaj": True},
        }

        extractor = AcademicFeatureExtractor()
        v1 = extractor.extract_from_work(work).to_vector()

        for _ in range(50):
            v2 = extractor.extract_from_work(work).to_vector()
            assert v1 == v2

    def test_batch_extraction_matches_single_extraction(self):
        works = [
            {"cited_by_count": 100, "is_oa": True, "oa_status": "gold"},
            {"cited_by_count": 5000, "is_oa": False, "oa_status": "closed"},
            {"cited_by_count": 0, "is_oa": None, "oa_status": None},
        ]
        extractor = AcademicFeatureExtractor()
        batch_results = extractor.extract_batch(works)
        single_results = [extractor.extract_from_work(w) for w in works]

        assert len(batch_results) == 3
        for b, s in zip(batch_results, single_results):
            assert b.to_vector() == s.to_vector()

    def test_property_monotonicity_and_bounds(self):
        """Assert all extracted feature vectors strictly reside in [0.0, 1.0] across edge-case combinations."""
        extractor = AcademicFeatureExtractor()

        for cits in [-100, 0, 1, 10, 100, 1000, 10000, 100000]:
            for oa in ["gold", "hybrid", "green", "bronze", "closed", "unknown", None]:
                for is_oa in [True, False, None]:
                    work = {
                        "cited_by_count": cits,
                        "oa_status": oa,
                        "is_oa": is_oa,
                        "authors": [{"cited_by_count": cits}],
                        "institutions": [{"cited_by_count": cits}],
                        "primary_source": {"cited_by_count": cits, "is_in_doaj": bool(is_oa)},
                    }
                    feats = extractor.extract_from_work(work)
                    vec = feats.to_vector()
                    assert len(vec) == 6
                    for v in vec:
                        assert isinstance(v, float)
                        assert not math.isnan(v)
                        assert not math.isinf(v)
                        assert 0.0 <= v <= 1.0

    def test_feature_extraction_performance_budget(self):
        """Measure extraction latency over 1,000 iterations and assert execution is within < 0.3 ms budget."""
        import time

        work = {
            "title": "Benchmarking High-Performance Feature Extraction",
            "cited_by_count": 1250,
            "is_oa": True,
            "oa_status": "gold",
            "authors": [
                {"cited_by_count": 5000, "author_position": "first", "is_corresponding": False},
                {"cited_by_count": 22000, "author_position": "last", "is_corresponding": True},
            ],
            "institutions": [{"cited_by_count": 180000}],
            "primary_source": {"cited_by_count": 45000, "is_in_doaj": True},
        }

        extractor = AcademicFeatureExtractor()
        latencies_ms: list[float] = []

        for _ in range(1000):
            t0 = time.perf_counter()
            _ = extractor.extract_from_work(work)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        latencies_ms.sort()
        n = len(latencies_ms)
        p50 = latencies_ms[int(0.50 * n)]
        p95 = latencies_ms[int(0.95 * n)]
        p99 = latencies_ms[int(0.99 * n)]

        # Feature extraction should easily take < 0.05 ms per candidate
        assert p50 < 0.05, f"P50 {p50:.4f} ms exceeded threshold"
        assert p95 < 0.10, f"P95 {p95:.4f} ms exceeded threshold"
        assert p99 < 0.30, f"P99 {p99:.4f} ms exceeded target 0.3 ms budget"
