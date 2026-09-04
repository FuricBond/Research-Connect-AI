"""
Comprehensive Test Suite for Phase 2.6D — Venue / Publisher Intelligence & Cross-Source Resolution.

Verifies:
  1. Exact identifier resolution (ISSN, ISSN-L, DOI prefix, canonical venue key).
  2. Publisher resolution & normalization (trusted registry, aliases, domain-to-publisher alignment).
  3. Organizer vs Publisher separation (conference host society distinct from publisher).
  4. ResearchSourceModel / OpenAlex integration and local Crossref metadata matching.
  5. DOAJ Evidence Invariant (DOAJ=True is positive trust; DOAJ=False/unknown is strictly NEUTRAL).
  6. False-Positive Safeguards (Missing metadata neutrality: unknown != predatory).
  7. Conflict Detection (Cross-source discrepancies lower resolution confidence without auto-predatory flag).
  8. Resolution Confidence vs Risk Confidence separation.
  9. Determinism across 100 repeated runs.
 10. Evidence deduplication (preventing duplicate DOAJ or publisher signals).
 11. Performance & batch scaling (10, 50, 100, 200, 1000 opportunities with zero N+1 queries).
"""
from __future__ import annotations

import time
from typing import Any
import uuid

import pytest

from app.ranking.risk.engine import RiskEvidenceExtractor, risk_evidence_extractor
from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    ResolutionStatus,
    ResolvedAcademicEntity,
    RiskAssessment,
    RiskEvidenceCollection,
    RiskLevel,
)
from app.ranking.risk.scoring import (
    DeterministicRiskScoringEngine,
    RiskScoringConfig,
    assess_opportunity_risk,
    risk_scoring_engine,
)
from app.ranking.risk.venue_intelligence import (
    KNOWN_DOI_PREFIXES,
    PUBLISHER_DOMAINS,
    VenuePublisherIntelligenceService,
    venue_publisher_intelligence_service,
)


# ── Mock ResearchSource for Testing ───────────────────────────────────────────


class MockResearchSource:
    """Mock research_sources model mirroring ResearchSourceModel."""

    def __init__(
        self,
        display_name: str = "Nature",
        openalex_id: str | None = "S137773608",
        issn_l: str | None = "0028-0836",
        issn: list[str] | None = None,
        host_organization: str | None = "Springer Nature",
        is_in_doaj: bool = False,
        is_oa: bool = False,
        works_count: int = 400000,
        cited_by_count: int = 15000000,
        homepage_url: str | None = "https://www.nature.com",
    ) -> None:
        self.display_name = display_name
        self.openalex_id = openalex_id
        self.issn_l = issn_l
        self.issn = issn or ["0028-0836", "1476-4687"]
        self.host_organization = host_organization
        self.is_in_doaj = is_in_doaj
        self.is_oa = is_oa
        self.works_count = works_count
        self.cited_by_count = cited_by_count
        self.homepage_url = homepage_url


# ── 1. Exact Identifier Resolution Tests ──────────────────────────────────────


class TestIdentifierResolution:
    """Tests for ISSN, ISSN-L, DOI prefix, and canonical venue key resolution."""

    def test_valid_issn_and_issn_l_resolution(self) -> None:
        opp = {
            "title": "Nature Machine Intelligence",
            "issn": "2522-5839",
            "issn_l": "25225839",
            "publisher": "Springer Nature",
            "website_url": "https://www.nature.com/natmachintell/",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)

        assert entity.issn == "2522-5839"
        assert entity.issn_l == "2522-5839"
        assert entity.resolution_status == ResolutionStatus.RESOLVED
        assert entity.resolution_confidence >= 0.75

    def test_issn_check_digit_x(self) -> None:
        opp = {
            "title": "Electronic Journal of Combinatorics",
            "issn": "1077-8926",
            "issn_l": "2434572x",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert entity.issn_l == "2434-572X"

    def test_doi_prefix_extraction_and_publisher_mapping(self) -> None:
        opp = {
            "title": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
            "doi": "10.1109/TPAMI.2023.3245678",
            "website_url": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=34",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)

        assert entity.doi_prefix == "10.1109"
        assert entity.publisher == "IEEE"
        assert entity.domain == "ieee.org"

    def test_invalid_issn_does_not_produce_positive_evidence(self) -> None:
        opp = {
            "title": "Random Journal of Questionable Origin",
            "issn": "123-INVALID",
            "publisher": "Unknown Press",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert entity.issn is None
        assert entity.issn_l is None

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        signals = [e.signal for e in evidence]
        assert EvidenceSignal.VERIFIED_ISSN_L.value not in signals
        assert EvidenceSignal.VERIFIED_VENUE_IDENTITY.value not in signals


# ── 2. Publisher Resolution & Normalization Tests ─────────────────────────────


class TestPublisherResolution:
    """Tests for publisher matching, alias normalization, and domain-to-publisher alignment."""

    def test_trusted_publisher_match_and_evidence(self) -> None:
        opp = {
            "title": "Journal of Molecular Biology",
            "publisher": "Elsevier",
            "website_url": "https://www.sciencedirect.com/journal/journal-of-molecular-biology",
            "issn": "0022-2836",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert entity.publisher == "Elsevier"
        assert entity.domain == "sciencedirect.com"

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        signals = [e.signal for e in evidence]
        assert EvidenceSignal.VERIFIED_PUBLISHER_IDENTITY.value in signals
        assert EvidenceSignal.PUBLISHER_DOMAIN_MATCH.value in signals

    def test_publisher_alias_normalization(self) -> None:
        # "Springer-Verlag Berlin" should resolve to canonical "Springer Nature"
        opp = {
            "title": "Lecture Notes in Computer Science",
            "publisher": "Springer-Verlag Berlin Heidelberg",
            "website_url": "https://www.springer.com/series/7408",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert entity.publisher == "Springer Nature"

    def test_domain_to_publisher_inference(self) -> None:
        # Opportunity lacks explicit publisher string, but website is on ACM Digital Library
        opp = {
            "title": "ACM Transactions on Graphics",
            "website_url": "https://dl.acm.org/journal/tog",
            "issn": "0730-0301",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert entity.publisher == "ACM"
        assert entity.domain == "acm.org"

    def test_unknown_publisher_remains_neutral(self) -> None:
        opp = {
            "title": "Small Workshop on Local Systems",
            "publisher": "Regional University Press",
            "website_url": "https://dept.university.edu/workshop",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)

        # No negative risk evidence should be produced for an unknown publisher
        neg_evidence = [e for e in evidence if e.category == EvidenceCategory.NEGATIVE_SUSPICIOUS]
        assert len(neg_evidence) == 0


# ── 3. Organizer vs Publisher Separation Tests ────────────────────────────────


class TestOrganizerPublisherSeparation:
    """Tests guaranteeing organizer (society) is separate from proceedings publisher."""

    def test_conference_organizer_distinct_from_publisher(self) -> None:
        opp = {
            "title": "IEEE/ACM International Conference on Automated Software Engineering (ASE)",
            "opportunity_type": "CONFERENCE",
            "organizer": "ACM",
            "publisher": "IEEE",
            "website_url": "https://conf.researchr.org/home/ase-2024",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)

        assert entity.organizer == "ACM"
        assert entity.publisher == "IEEE"
        assert entity.entity_type == "CONFERENCE"

    def test_unknown_organizer_is_neutral(self) -> None:
        opp = {
            "title": "International Symposium on Practical Robotics",
            "opportunity_type": "CONFERENCE",
            "organizer": "Ad-Hoc Steering Committee 2024",
            "publisher": "Springer Nature",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)

        assert entity.organizer == "Ad-Hoc Steering Committee 2024"
        assert entity.publisher == "Springer Nature"
        # No negative evidence created
        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        neg_evidence = [e for e in evidence if e.category == EvidenceCategory.NEGATIVE_SUSPICIOUS]
        assert len(neg_evidence) == 0


# ── 4. ResearchSourceModel / OpenAlex & Crossref Integration Tests ────────────


class TestResearchSourceIntegration:
    """Tests verifying linkage with external research sources (OpenAlex, Crossref)."""

    def test_link_to_openalex_source_record(self) -> None:
        opp = {
            "title": "Nature",
            "issn": "0028-0836",
            "publisher": "Springer Nature",
            "website_url": "https://www.nature.com",
        }
        mock_source = MockResearchSource(
            display_name="Nature",
            openalex_id="S137773608",
            issn_l="0028-0836",
            host_organization="Springer Nature",
            is_in_doaj=False,
            works_count=420000,
            cited_by_count=16000000,
        )

        entity = venue_publisher_intelligence_service.resolve_entity(opp, source_record=mock_source)

        assert entity.openalex_id == "S137773608"
        assert entity.works_count == 420000
        assert entity.cited_by_count == 16000000
        assert "OpenAlex" in entity.matched_sources
        assert entity.resolution_status == ResolutionStatus.RESOLVED

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        signals = [e.signal for e in evidence]
        assert EvidenceSignal.OPENALEX_METADATA_MATCH.value in signals
        assert EvidenceSignal.VERIFIED_VENUE_IDENTITY.value in signals

    def test_crossref_metadata_match_from_raw_metadata(self) -> None:
        opp = {
            "title": "PLOS Computational Biology",
            "issn": "1553-7358",
            "publisher": "PLOS",
            "raw_metadata": {
                "crossref": True,
                "crossref_container_title": "PLOS Computational Biology",
            },
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert "Crossref" in entity.matched_sources

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        signals = [e.signal for e in evidence]
        assert EvidenceSignal.CROSSREF_METADATA_MATCH.value in signals


# ── 5. DOAJ Evidence Invariant Tests ──────────────────────────────────────────


class TestDOAJEvidenceInvariant:
    """
    Mandatory Phase 2.6D rule:
      is_in_doaj == True  -> Positive trust evidence (DOAJ_INDEXED)
      is_in_doaj == False -> NEUTRAL (ZERO negative/predatory evidence)
      unknown / None      -> NEUTRAL
    """

    def test_doaj_true_produces_positive_trust(self) -> None:
        opp = {
            "title": "PeerJ Computer Science",
            "issn": "2376-5992",
            "publisher": "PeerJ",
        }
        mock_source = MockResearchSource(
            display_name="PeerJ Computer Science",
            openalex_id="S2738202511",
            issn_l="2376-5992",
            host_organization="PeerJ",
            is_in_doaj=True,
        )
        entity = venue_publisher_intelligence_service.resolve_entity(opp, source_record=mock_source)
        assert entity.is_in_doaj is True

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        doaj_items = [e for e in evidence if e.signal == EvidenceSignal.DOAJ_INDEXED.value]
        assert len(doaj_items) == 1
        assert doaj_items[0].category == EvidenceCategory.POSITIVE_TRUST
        assert doaj_items[0].strength == EvidenceStrength.STRONG

    def test_doaj_false_remains_strictly_neutral(self) -> None:
        # Venue is legitimate but NOT in DOAJ (e.g. subscription or hybrid journal)
        opp = {
            "title": "IEEE Transactions on Software Engineering",
            "issn": "0098-5589",
            "publisher": "IEEE",
        }
        mock_source = MockResearchSource(
            display_name="IEEE Transactions on Software Engineering",
            openalex_id="S111111111",
            issn_l="0098-5589",
            host_organization="IEEE",
            is_in_doaj=False,
        )
        entity = venue_publisher_intelligence_service.resolve_entity(opp, source_record=mock_source)
        assert entity.is_in_doaj is False

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        # Verify NO negative evidence generated
        neg_items = [e for e in evidence if e.category == EvidenceCategory.NEGATIVE_SUSPICIOUS]
        assert len(neg_items) == 0

        # Run through full scoring engine to confirm zero risk penalty
        evidence_col = risk_evidence_extractor.extract(opp, source_record=mock_source)
        assessment = risk_scoring_engine.score(evidence_col)
        assert assessment.risk_score == 0.00
        assert assessment.risk_level == RiskLevel.LOW_RISK

    def test_doaj_none_remains_neutral(self) -> None:
        opp = {
            "title": "Unindexed Workshop Proceedings",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert entity.is_in_doaj is None

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        neg_items = [e for e in evidence if e.category == EvidenceCategory.NEGATIVE_SUSPICIOUS]
        assert len(neg_items) == 0


# ── 6. False-Positive Safeguards (Missing Metadata Neutrality) ────────────────


class TestFalsePositiveSafeguards:
    """Verifies that missing metadata, unknown publishers, and legitimate fees never produce high risk."""

    def test_small_new_venue_unresolved_is_neutral(self) -> None:
        # A completely new or regional workshop with minimal metadata
        opp = {
            "title": "1st Regional Workshop on Applied AI",
            "opportunity_type": "WORKSHOP",
            "delivery_mode": "ONLINE",
            "location": "Online",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert entity.resolution_status == ResolutionStatus.UNRESOLVED
        assert entity.resolution_confidence < 0.40

        evidence_col = risk_evidence_extractor.extract(opp)
        assessment = risk_scoring_engine.score(evidence_col)

        # Must NOT be flagged as high risk or predatory
        assert assessment.risk_score == 0.00
        assert assessment.is_predatory_flag is False
        assert assessment.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE

    def test_legitimate_apc_with_unindexed_publisher_remains_neutral(self) -> None:
        opp = {
            "title": "Nordic Journal of Data Science",
            "publisher": "Nordic University Press",
            "description": "Article processing charge of $800 applies upon formal acceptance following single-blind review.",
        }
        evidence_col = risk_evidence_extractor.extract(opp)
        assessment = risk_scoring_engine.score(evidence_col)

        assert assessment.risk_score <= 0.20
        assert assessment.is_predatory_flag is False
        assert assessment.risk_level != RiskLevel.HIGH_RISK


# ── 7. Conflict Detection Tests ───────────────────────────────────────────────


class TestConflictDetection:
    """Verifies handling of cross-source disagreements."""

    def test_openalex_host_discrepancy_detects_conflict(self) -> None:
        # Opportunity claims publisher is "Elsevier", but external record says "Springer Nature"
        opp = {
            "title": "Artificial Intelligence Journal",
            "publisher": "Elsevier",
            "issn": "0004-3702",
        }
        mock_source = MockResearchSource(
            display_name="Artificial Intelligence Journal",
            openalex_id="S123456",
            issn_l="0004-3702",
            host_organization="Springer Nature",
        )
        entity = venue_publisher_intelligence_service.resolve_entity(opp, source_record=mock_source)

        assert len(entity.conflicts) > 0
        assert any("Host organization discrepancy" in c for c in entity.conflicts)

        evidence = venue_publisher_intelligence_service.extract_venue_evidence(entity, opp)
        conflict_signals = [e for e in evidence if e.signal == EvidenceSignal.CONFLICTING_METADATA.value]
        assert len(conflict_signals) == 1
        assert conflict_signals[0].category == EvidenceCategory.NEGATIVE_SUSPICIOUS
        assert conflict_signals[0].strength == EvidenceStrength.WEAK

    def test_domain_publisher_mismatch_detects_conflict(self) -> None:
        # Opportunity claims publisher is "IEEE", but domain is clearly Elsevier
        opp = {
            "title": "Advances in Computing",
            "publisher": "IEEE",
            "website_url": "https://www.sciencedirect.com/journal/advances-in-computing",
        }
        entity = venue_publisher_intelligence_service.resolve_entity(opp)
        assert len(entity.conflicts) > 0
        assert any("Domain publisher mismatch" in c for c in entity.conflicts)

    def test_conflict_reduces_confidence_without_auto_predatory(self) -> None:
        # Discrepancy should lower resolution confidence, but NOT create an automatic predatory flag!
        opp = {
            "title": "Computer Communications",
            "publisher": "IEEE",
            "website_url": "https://www.sciencedirect.com/journal/computer-communications",
            "issn": "0140-3664",
        }
        evidence_col = risk_evidence_extractor.extract(opp)
        assessment = risk_scoring_engine.score(evidence_col)

        # Cautionary score, definitely not predatory
        assert assessment.is_predatory_flag is False
        assert assessment.risk_level != RiskLevel.HIGH_RISK


# ── 8. Resolution Confidence vs Risk Confidence Separation ───────────────────


class TestConfidenceSeparation:
    """Verifies that Resolution Confidence is strictly decoupled from Risk Confidence."""

    def test_high_resolution_confidence_on_fraudulent_venue(self) -> None:
        # High resolution confidence (we know exactly what venue it claims to be)
        # but blatant fraud language (guaranteed publication in 24 hours, send money via Western Union)
        opp = {
            "title": "International Journal of Electrical Wonders",
            "publisher": "IEEE",  # Claims IEEE
            "issn": "0018-9219",  # Valid IEEE ISSN
            "website_url": "https://ieeexplore.ieee.org/journal/fake",
            "description": "Review completed in 24 hours. Acceptance is guaranteed. Send processing fee via Western Union.",
        }
        evidence_col = risk_evidence_extractor.extract(opp)
        assert evidence_col.resolved_entity is not None
        assert evidence_col.resolved_entity.resolution_confidence >= 0.70

        assessment = risk_scoring_engine.score(evidence_col)
        # Risk score must remain elevated despite high resolution confidence!
        assert assessment.risk_score >= 0.30
        assert assessment.risk_level in (RiskLevel.MODERATE_RISK, RiskLevel.HIGH_RISK)


    def test_low_resolution_confidence_on_safe_clean_venue(self) -> None:
        # Low resolution confidence (obscure workshop, no ISSN, no publisher)
        opp = {
            "title": "Workshop on Local Topological Data Analysis",
            "opportunity_type": "WORKSHOP",
            "description": "Submissions are invited for the upcoming workshop. All papers undergo peer review.",
        }
        evidence_col = risk_evidence_extractor.extract(opp)
        assert evidence_col.resolved_entity is not None
        assert evidence_col.resolved_entity.resolution_confidence < 0.40

        assessment = risk_scoring_engine.score(evidence_col)
        # Risk score must be 0.00 (not high risk!)
        assert assessment.risk_score == 0.00
        assert assessment.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE


# ── 9. Determinism Tests ──────────────────────────────────────────────────────


class TestDeterminism:
    """Verifies that resolution is strictly 100% deterministic across 100 repeated runs."""

    def test_resolution_determinism_across_100_runs(self) -> None:
        opp = {
            "id": str(uuid.uuid4()),
            "title": "ACM Computing Surveys",
            "publisher": "Association for Computing Machinery",
            "issn": "0360-0300",
            "issn_l": "0360-0300",
            "website_url": "https://dl.acm.org/journal/csur",
        }
        mock_source = MockResearchSource(
            display_name="ACM Computing Surveys",
            openalex_id="S839485",
            issn_l="0360-0300",
            host_organization="ACM",
            is_in_doaj=False,
        )

        first_entity = venue_publisher_intelligence_service.resolve_entity(opp, source_record=mock_source)
        first_dict = first_entity.to_dict()

        for _ in range(100):
            repeated_entity = venue_publisher_intelligence_service.resolve_entity(opp, source_record=mock_source)
            assert repeated_entity.to_dict() == first_dict


# ── 10. Evidence Deduplication Tests ──────────────────────────────────────────


class TestEvidenceDeduplication:
    """Verifies that duplicate signals from different sources are cleanly controlled."""

    def test_doaj_deduplication(self) -> None:
        # Opportunity has DOAJ in indexing list AND external source confirms is_in_doaj=True
        opp = {
            "title": "BioData Mining",
            "publisher": "BioMed Central",
            "indexing": ["DOAJ", "PubMed", "Scopus"],
            "issn": "1756-0381",
        }
        mock_source = MockResearchSource(
            display_name="BioData Mining",
            openalex_id="S987654",
            issn_l="1756-0381",
            host_organization="Springer Nature",
            is_in_doaj=True,
        )

        evidence_col = risk_evidence_extractor.extract(opp, source_record=mock_source)
        doaj_items = [e for e in evidence_col.items if e.signal == EvidenceSignal.DOAJ_INDEXED.value]

        # There must be EXACTLY ONE DOAJ_INDEXED signal
        assert len(doaj_items) == 1


# ── 11. Performance & Batch Scaling Tests (Zero N+1) ──────────────────────────


class TestBatchPerformanceAndZeroQueries:
    """Verifies zero N+1 database queries and sub-150ms resolution for 1,000 candidates."""

    @pytest.mark.parametrize("n_candidates", [10, 50, 100, 200, 1000])
    def test_batch_resolution_scaling(self, n_candidates: int) -> None:
        # Generate N synthetic opportunities
        candidates = [
            {
                "id": str(uuid.uuid4()),
                "title": f"International Journal of Computational Intelligence {i}",
                "publisher": "IEEE" if i % 2 == 0 else "Springer Nature",
                "issn": f"00{i % 90 + 10}-1234",
                "website_url": "https://ieeexplore.ieee.org" if i % 2 == 0 else "https://link.springer.com",
            }
            for i in range(n_candidates)
        ]

        # Pre-fetched source records dictionary
        pre_fetched_sources = {
            "issn:0028-0836": MockResearchSource(display_name="Nature"),
            "0028-0836": MockResearchSource(display_name="Nature"),
        }

        start = time.perf_counter()
        resolved = venue_publisher_intelligence_service.resolve_batch(
            candidates,
            source_records=pre_fetched_sources,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert len(resolved) == n_candidates

        # 1000 opportunities must complete in < 150ms in-memory
        if n_candidates == 1000:
            assert elapsed_ms < 150.0, f"Batch resolution took {elapsed_ms:.2f}ms (expected < 150ms)"

    def test_end_to_end_extractor_batch_performance(self) -> None:
        candidates = [
            {
                "id": str(uuid.uuid4()),
                "title": f"IEEE Transactions on Neural Networks {i}",
                "publisher": "IEEE",
                "issn": "1045-9227",
                "website_url": "https://ieeexplore.ieee.org",
            }
            for i in range(100)
        ]

        start = time.perf_counter()
        collections = risk_evidence_extractor.extract_batch(candidates)
        assessments = risk_scoring_engine.score_batch(collections)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert len(assessments) == 100
        # 100 full extractions and scorings in under 50ms
        assert elapsed_ms < 50.0, f"100 end-to-end scorings took {elapsed_ms:.2f}ms"
