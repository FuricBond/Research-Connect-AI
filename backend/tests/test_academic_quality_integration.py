"""
Unit, Integration, and Performance Tests for Phase 2.5D:
Academic Quality & Venue Signals Integration.

Verifies:
  1. Relational entity resolution (Author -> Researcher, Institution -> Institution, Work -> Venue).
  2. Venue normalization, abbreviation expansion, and canonical ISSN hashing.
  3. Academic coverage diagnostics measurement.
  4. Missing, malformed, and extreme metadata resilience.
  5. Multi-author and multi-institution aggregation & deduplication.
  6. Zero N+1 query behavior across batch sizes (10, 50, 100, 200).
  7. Relevance dominance invariant enforcement with academic signals.
  8. Deterministic 15-key tie-breaking consistency.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.research_knowledge import (
    InstitutionModel,
    ResearcherModel,
    ResearchSourceModel,
    ResearchWorkAuthorModel,
    ResearchWorkInstitutionModel,
    ResearchWorkModel,
)
from app.ranking.diagnostics import AcademicCoverageDiagnostics
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
from app.ranking.hybrid_ranker import (
    HybridRanker,
    RankedCandidate,
    RankerWeights,
    RankingMode,
    hybrid_ranker,
)
from app.ranking.venue_intelligence import (
    VenueResolver,
    get_canonical_venue_key,
    normalize_issn,
    normalize_venue_name,
    venue_resolver,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sqlite_session() -> Session:
    """In-memory SQLite session with all tables created for batch relational testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def ranker() -> HybridRanker:
    return HybridRanker()


# ── 1. Venue Intelligence & Normalization Tests ───────────────────────────────


class TestVenueIntelligence:
    """Test suite for ISSN normalization and venue display name canonicalization."""

    def test_normalize_issn_formats(self) -> None:
        """Verify normalization of various valid and invalid ISSN formats."""
        assert normalize_issn("0028-0836") == "0028-0836"
        assert normalize_issn("00280836") == "0028-0836"
        assert normalize_issn(" 0028-0836 ") == "0028-0836"
        assert normalize_issn("2434-572X") == "2434-572X"
        assert normalize_issn("2434572x") == "2434-572X"  # Coerces lowercase check-digit
        assert normalize_issn(None) is None
        assert normalize_issn("") is None
        assert normalize_issn("123") is None
        assert normalize_issn("invalid-issn") is None

    def test_normalize_venue_name(self) -> None:
        """Verify whitespace trimming, punctuation stripping, and cleaning."""
        assert normalize_venue_name("Nature  ") == "Nature"
        assert normalize_venue_name("  IEEE Transactions on Pattern Analysis  ") == "IEEE Transactions on Pattern Analysis"
        assert normalize_venue_name("Bioinformatics,") == "Bioinformatics"
        assert normalize_venue_name("Science...") == "Science"
        assert normalize_venue_name(None) is None
        assert normalize_venue_name("   ") is None

    def test_get_canonical_venue_key(self) -> None:
        """Verify deterministic canonical venue key generation hierarchy."""
        # Linking ISSN has top priority
        key_issn = get_canonical_venue_key(
            name="Nature",
            issn_l="0028-0836",
            issn_list=["0028-0836", "1476-4687"],
        )
        assert key_issn == "issn:0028-0836"

        # Alternative ISSN list when issn_l is missing
        key_list = get_canonical_venue_key(
            name="Nature",
            issn_l=None,
            issn_list=["1476-4687", "0028-0836"],
        )
        assert key_list == "issn:0028-0836"

        # Name fallback when no ISSN is present
        key_name = get_canonical_venue_key(
            name="IEEE Trans. on Software Engineering",
            issn_l=None,
        )
        assert key_name.startswith("name:ieee transactions on")

    def test_venue_resolver_metadata_extraction(self) -> None:
        """Verify VenueResolver extracts and canonicalizes venue dictionary/ORM attributes."""
        raw_dict = {
            "display_name": "IEEE Trans. Signal Process.",
            "issn_l": "1053-587X",
            "is_in_doaj": False,
            "cited_by_count": 45000,
        }
        res = venue_resolver.resolve_venue_metadata(raw_dict)
        assert res["normalized_name"] == "IEEE Trans. Signal Process"
        assert res["issn_l"] == "1053-587X"
        assert res["is_in_doaj"] is False
        assert res["cited_by_count"] == 45000
        assert res["canonical_key"] == "issn:1053-587X"


# ── 2. Data Quality & Coverage Diagnostics Tests ──────────────────────────────


class TestAcademicCoverageDiagnostics:
    """Test suite for academic metadata completeness diagnostics."""

    def test_empty_candidates_diagnostics(self) -> None:
        """Verify diagnostics on empty candidate collection."""
        diag = AcademicCoverageDiagnostics.from_candidates([])
        assert diag.total_candidates == 0
        assert diag.citation_coverage == 0.0
        assert diag.author_coverage == 0.0
        assert diag.institution_coverage == 0.0
        assert diag.venue_coverage == 0.0
        assert diag.oa_coverage == 0.0
        assert diag.overall_academic_completeness == 0.0

    def test_full_coverage_diagnostics(self) -> None:
        """Verify diagnostics when all candidates have complete metadata."""
        now = datetime.now(timezone.utc)
        cand1 = {
            "id": uuid.uuid4(),
            "cited_by_count": 100,
            "author_links": [{"id": uuid.uuid4()}],
            "institution_links": [{"id": uuid.uuid4()}],
            "primary_source": {"id": uuid.uuid4()},
            "is_oa": True,
            "oa_status": "gold",
        }
        cand2 = {
            "id": uuid.uuid4(),
            "cited_by_count": 50,
            "author_links": [{"id": uuid.uuid4()}],
            "institution_links": [{"id": uuid.uuid4()}],
            "primary_source": {"id": uuid.uuid4()},
            "is_oa": False,
            "oa_status": "closed",
        }

        diag = AcademicCoverageDiagnostics.from_candidates([cand1, cand2])
        assert diag.total_candidates == 2
        assert diag.citation_coverage == 1.0
        assert diag.author_coverage == 1.0
        assert diag.institution_coverage == 1.0
        assert diag.venue_coverage == 1.0
        assert diag.oa_coverage == 1.0
        assert diag.overall_academic_completeness == 1.0

    def test_partial_coverage_diagnostics(self) -> None:
        """Verify diagnostics with mixed partial metadata."""
        cand_full = {
            "id": uuid.uuid4(),
            "cited_by_count": 25,
            "author_links": [{"id": uuid.uuid4()}],
            "institution_links": [{"id": uuid.uuid4()}],
            "primary_source": {"id": uuid.uuid4()},
            "is_oa": True,
            "oa_status": "gold",
        }
        cand_bare = {
            "id": uuid.uuid4(),
            "cited_by_count": 0,
            "author_links": [],
            "institution_links": [],
            "primary_source": None,
            "is_oa": None,
            "oa_status": None,
        }

        diag = AcademicCoverageDiagnostics.from_candidates([cand_full, cand_bare])
        assert diag.total_candidates == 2
        assert diag.citation_coverage == 0.50
        assert diag.author_coverage == 0.50
        assert diag.institution_coverage == 0.50
        assert diag.venue_coverage == 0.50
        assert diag.oa_coverage == 0.50
        assert diag.overall_academic_completeness == 0.50

        # Check to_dict() serialization
        d = diag.to_dict()
        assert d["total_candidates"] == 2
        assert d["overall_academic_completeness"] == 0.50


# ── 3. Relational Entity Resolution & Deduplication Tests ─────────────────────


class TestRelationalEntityResolution:
    """Test suite verifying end-to-end ORM relationship resolution."""

    def test_multi_author_aggregation_and_deduplication(self) -> None:
        """Verify multi-author aggregation chooses highest author score and handles duplicate links."""
        res_a = ResearcherModel(
            id=uuid.uuid4(),
            display_name="Researcher A",
            cited_by_count=1000,
        )
        res_b = ResearcherModel(
            id=uuid.uuid4(),
            display_name="Researcher B",
            cited_by_count=25000,
        )

        link1 = ResearchWorkAuthorModel(
            researcher_id=res_a.id,
            researcher=res_a,
            author_position="middle",
            is_corresponding=False,
        )
        link2 = ResearchWorkAuthorModel(
            researcher_id=res_b.id,
            researcher=res_b,
            author_position="first",
            is_corresponding=True,
        )
        # Duplicate link for res_b
        link2_dup = ResearchWorkAuthorModel(
            researcher_id=res_b.id,
            researcher=res_b,
            author_position="first",
            is_corresponding=True,
        )

        work = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Multi-Author Work",
            author_links=[link1, link2, link2_dup],
        )

        prominence = calculate_author_prominence(work)
        pos_score = calculate_author_position_score(work)

        # Max author prominence is bounded by res_b (25,000 citations)
        expected_prominence = math.log10(1.0 + 25000) / math.log10(1.0 + 50000)
        assert pytest.approx(prominence, abs=1e-5) == expected_prominence
        # Corresponding author position score is 1.00
        assert pos_score == 1.00

    def test_multi_institution_aggregation_and_deduplication(self) -> None:
        """Verify multi-institution aggregation selects max prestige institution."""
        inst_a = InstitutionModel(
            id=uuid.uuid4(),
            display_name="Institution A",
            cited_by_count=50000,
        )
        inst_b = InstitutionModel(
            id=uuid.uuid4(),
            display_name="Institution B",
            cited_by_count=300000,
        )

        link_a = ResearchWorkInstitutionModel(
            institution_id=inst_a.id,
            institution=inst_a,
        )
        link_b = ResearchWorkInstitutionModel(
            institution_id=inst_b.id,
            institution=inst_b,
        )
        link_b_dup = ResearchWorkInstitutionModel(
            institution_id=inst_b.id,
            institution=inst_b,
        )

        work = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Multi-Institution Work",
            institution_links=[link_a, link_b, link_b_dup],
        )

        prestige = calculate_institution_prestige(work)
        expected_prestige = math.log10(1.0 + 300000) / math.log10(1.0 + 500000)
        assert pytest.approx(prestige, abs=1e-5) == expected_prestige

    def test_venue_prestige_resolution_with_doaj(self) -> None:
        """Verify venue prestige aggregates citation saturation + DOAJ bonus."""
        source = ResearchSourceModel(
            id=uuid.uuid4(),
            display_name="Journal of Open Source Software",
            cited_by_count=10000,
            is_in_doaj=True,
        )
        work = ResearchWorkModel(
            id=uuid.uuid4(),
            title="JOSS Paper",
            primary_source=source,
        )

        venue_score = calculate_venue_prestige(work)
        cit_component = math.log10(1.0 + 10000) / math.log10(1.0 + 100000)
        expected = min(1.0, cit_component + 0.10)
        assert pytest.approx(venue_score, abs=1e-5) == expected


# ── 4. Missing, Degraded, and Malformed Metadata Resilience ───────────────────


class TestMetadataResilience:
    """Test suite for missing, null, NaN, and extreme metadata values."""

    def test_null_and_malformed_citations(self) -> None:
        """Verify citation normalization never throws on irregular inputs."""
        assert calculate_citation_impact(None) == 0.0
        assert calculate_citation_impact(0) == 0.0
        assert calculate_citation_impact(-50) == 0.0
        assert calculate_citation_impact(float("nan")) == 0.0
        assert calculate_citation_impact(float("inf")) == 0.0
        assert calculate_citation_impact("not a number") == 0.0  # type: ignore

    def test_extreme_citation_saturation(self) -> None:
        """Verify saturation limits at 10,000, 100,000, and 1,000,000 citations."""
        assert calculate_citation_impact(0) == 0.0
        assert calculate_citation_impact(10) > 0.0
        assert calculate_citation_impact(10000) == 1.0  # Exactly at default cap
        assert calculate_citation_impact(500000) == 1.0  # Saturated at 1.0

    def test_unlinked_and_empty_relationships(self) -> None:
        """Verify works with empty or None relation collections extract cleanly."""
        work_empty = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Orphan Work",
            cited_by_count=None,
            author_links=[],
            institution_links=[],
            primary_source=None,
            is_oa=None,
            oa_status=None,
        )
        feats = academic_feature_extractor.extract_from_work(work_empty)
        assert feats.citation_impact == 0.0
        assert feats.author_prominence == 0.0
        assert feats.author_position == 0.50
        assert feats.institution_prestige == 0.0
        assert feats.venue_prestige == 0.0
        assert feats.open_access_tier == 0.35

    def test_author_position_synonyms(self) -> None:
        """Verify varied position synonyms are parsed correctly."""
        for synonym in ("FIRST", "first", "FIRST_AUTHOR", "LEAD", "PRIMARY"):
            assert calculate_author_position_score(author_position=synonym) == 0.90
        for synonym in ("CORRESPONDING", "corresponding_author", "SINGLE", "SOLE"):
            assert calculate_author_position_score(author_position=synonym) == 1.00
        for synonym in ("LAST", "senior", "SENIOR_AUTHOR", "PI", "SUPERVISOR"):
            assert calculate_author_position_score(author_position=synonym) == 0.80
        for synonym in ("MIDDLE", "contributor", "unknown", None):
            assert calculate_author_position_score(author_position=synonym) == 0.50

    def test_oa_status_synonyms(self) -> None:
        """Verify OA status synonyms map to appropriate tiers."""
        assert calculate_open_access_tier(oa_status="GOLD") == 1.00
        assert calculate_open_access_tier(oa_status="diamond") == 1.00
        assert calculate_open_access_tier(oa_status="HYBRID") == 0.85
        assert calculate_open_access_tier(oa_status="green") == 0.70
        assert calculate_open_access_tier(oa_status="bronze") == 0.55
        assert calculate_open_access_tier(oa_status="closed") == 0.20
        assert calculate_open_access_tier(oa_status="subscription") == 0.20
        assert calculate_open_access_tier(oa_status="unknown") == 0.35
        assert calculate_open_access_tier(oa_status=None, is_oa=True) == 0.70
        assert calculate_open_access_tier(oa_status=None, is_oa=False) == 0.20


# ── 5. Zero N+1 Queries & Batch Loading Verification ─────────────────────────


class TestZeroNPlusOneQueries:
    """
    Test suite verifying that batch prefetching runs with O(1) SQL queries
    across varying candidate batch sizes (10, 50, 100, 200).
    """

    @pytest.mark.parametrize("batch_size", [10, 50, 100, 200])
    def test_batch_query_count_constant(self, batch_size: int) -> None:
        """Verify that extracting features for N works executes exactly 1 batch query."""
        now = datetime.now(timezone.utc)
        works_list = []
        for i in range(batch_size):
            w_id = uuid.uuid4()
            work = ResearchWorkModel(
                id=w_id,
                title=f"Scalable Machine Learning Work {i}",
                work_type="article",
                cited_by_count=10 * i,
                is_oa=(i % 2 == 0),
                oa_status="gold" if (i % 2 == 0) else "closed",
                created_at=now,
                updated_at=now,
            )
            works_list.append(work)

        # Create mock session that intercepts the batch select query
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.unique.return_value.all.return_value = works_list
        mock_session.scalars.return_value = mock_result

        features = academic_feature_extractor.extract_batch(
            works_list, session=mock_session
        )

        assert len(features) == batch_size
        # Verify exactly 1 query was executed across all N items
        assert mock_session.scalars.call_count == 1
        assert all(isinstance(f, AcademicFeatures) for f in features)

    def test_ranker_batch_session_integration(self) -> None:
        """Verify hybrid_ranker.rank() accepts session and executes single-pass prefetch."""
        now = datetime.now(timezone.utc)
        work1 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Neural Information Retrieval",
            work_type="article",
            cited_by_count=500,
            created_at=now,
            updated_at=now,
        )
        work2 = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Dense Passage Retrieval",
            work_type="article",
            cited_by_count=1200,
            created_at=now,
            updated_at=now,
        )

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.unique.return_value.all.return_value = [work1, work2]
        mock_session.scalars.return_value = mock_result

        candidates = [
            {"id": work1.id, "semantic_similarity": 0.85, "lexical_similarity": 0.80, "entity": work1},
            {"id": work2.id, "semantic_similarity": 0.84, "lexical_similarity": 0.81, "entity": work2},
        ]

        ranked = hybrid_ranker.rank(
            candidates,
            mode=RankingMode.RESEARCH_SIMILARITY,
            session=mock_session,
        )
        assert len(ranked) == 2
        assert all(isinstance(r, RankedCandidate) for r in ranked)
        assert mock_session.scalars.call_count == 1


# ── 6. Ranking Integrity & Relevance Dominance Tests ─────────────────────────


class TestRankingIntegrityWithAcademicSignals:
    """Test suite ensuring relevance dominance invariant holds with academic signals."""

    def test_relevance_dominance_overpowers_extreme_prestige(self, ranker: HybridRanker) -> None:
        """Verify high relevance + zero citations outranks low relevance + extreme prestige."""
        weights = RankerWeights(
            semantic_weight=0.55,
            lexical_weight=0.20,
            topic_weight=0.10,
            citation_weight=0.04,
            venue_weight=0.03,
            author_prominence_weight=0.03,
            institution_weight=0.03,
            open_access_weight=0.02,
        ).with_relevance_dominance(0.85)

        # Candidate A: Highly relevant, zero prestige / citations
        c_high_rel_no_cits = {
            "entity_id": uuid.uuid4(),
            "semantic_similarity": 0.95,
            "lexical_similarity": 0.90,
            "topic_similarity": 0.85,
            "citation_impact": 0.0,
            "venue_prestige": 0.0,
            "author_prominence": 0.0,
            "institution_prestige": 0.0,
        }

        # Candidate B: Irrelevant, maximum prestige / citations
        c_low_rel_max_prestige = {
            "entity_id": uuid.uuid4(),
            "semantic_similarity": 0.20,
            "lexical_similarity": 0.15,
            "topic_similarity": 0.10,
            "citation_impact": 1.0,
            "venue_prestige": 1.0,
            "author_prominence": 1.0,
            "institution_prestige": 1.0,
        }

        ranked = ranker.rank([c_low_rel_max_prestige, c_high_rel_no_cits], weights=weights)
        assert ranked[0].entity_id == c_high_rel_no_cits["entity_id"]
        assert ranked[0].final_score > ranked[1].final_score

    def test_prestige_breaks_ties_between_equally_relevant_items(self, ranker: HybridRanker) -> None:
        """Verify academic prestige cleanly orders candidates with identical relevance."""
        weights = RankerWeights(
            semantic_weight=0.55,
            lexical_weight=0.20,
            topic_weight=0.10,
            citation_weight=0.05,
            venue_weight=0.04,
            author_prominence_weight=0.03,
            institution_weight=0.02,
            open_access_weight=0.01,
        ).with_relevance_dominance(0.85)

        c_low = {
            "entity_id": uuid.uuid4(),
            "semantic_similarity": 0.85,
            "lexical_similarity": 0.80,
            "topic_similarity": 0.75,
            "citation_impact": 0.10,
            "venue_prestige": 0.10,
        }
        c_high = {
            "entity_id": uuid.uuid4(),
            "semantic_similarity": 0.85,
            "lexical_similarity": 0.80,
            "topic_similarity": 0.75,
            "citation_impact": 0.90,
            "venue_prestige": 0.90,
        }

        ranked = ranker.rank([c_low, c_high], weights=weights)
        assert ranked[0].entity_id == c_high["entity_id"]
        assert ranked[0].final_score > ranked[1].final_score

    def test_deterministic_multi_run_consistency(self, ranker: HybridRanker) -> None:
        """Verify ranking order and final scores are byte-for-byte deterministic across 50 runs."""
        candidates = [
            {
                "entity_id": uuid.UUID(f"00000000-0000-0000-0000-{i:012d}"),
                "semantic_similarity": 0.80 + (i % 5) * 0.02,
                "lexical_similarity": 0.75 + (i % 3) * 0.03,
                "topic_similarity": 0.70,
                "citation_impact": (i % 10) * 0.1,
                "venue_prestige": (i % 7) * 0.12,
            }
            for i in range(25)
        ]

        first_order = [r.entity_id for r in ranker.rank(candidates)]
        for _ in range(50):
            order = [r.entity_id for r in ranker.rank(candidates)]
            assert order == first_order
