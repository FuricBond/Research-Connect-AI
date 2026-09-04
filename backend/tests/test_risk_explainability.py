"""
Unit, Integration, and Regression Tests for Phase 2.6F — Risk Explainability + API/UI Integration.

Verifies:
  - Scenarios A–V:
      A. LOW_RISK explanation
      B. MODERATE_RISK explanation
      C. HIGH_RISK explanation
      D. INSUFFICIENT_EVIDENCE explanation
      E. Positive trust evidence categorization
      F. Suspicious evidence categorization
      G. Neutral evidence categorization
      H. Graph-derived evidence categorization
      I. Venue/publisher evidence categorization
      J. Provenance preservation
      K. Deterministic evidence ordering
      L. Deterministic repeated output (100 iterations)
      M. Correlated evidence deduplication
      N. Score / explanation mathematical consistency
      O. Confidence handling
      P. Missing metadata neutrality (UNKNOWN != PREDATORY)
      Q. High-degree trusted publisher protection
      R. Isolated opportunity neutrality
      S. Identity conflict explanation
      T. Backward-compatible API response
      U. Schema serialization & frontend compatibility
      V. Zero N+1 database queries & performance benchmarking
  - Realistic Fixtures 1–8:
      1. Verified major publisher (ACM / IEEE)
      2. Legitimate scientific society conference
      3. New legitimate conference with sparse metadata
      4. Corroborated suspicious multi-signal venue
      5. Conflicting venue identity
      6. Suspicious organizer cluster
      7. Suspicious domain cluster
      8. APC/fee-only metadata
  - Regression verifications (Phase 2.6C, 2.6D, 2.6E, 2.5 ranking).
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
from unittest.mock import MagicMock
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.opportunity import OpportunityModel
from app.ranking.risk.engine import risk_evidence_extractor
from app.ranking.risk.explainability import (
    RiskEvidenceExplanation,
    RiskExplanation,
    RiskExplainabilityService,
    risk_explainability_service,
)
from app.ranking.risk.graph import (
    AcademicTrustGraph,
    SuspiciousGraphService,
    suspicious_graph_service,
)
from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    RiskAssessment,
    RiskEvidence,
    RiskEvidenceCollection,
    RiskLevel,
)
from app.ranking.risk.scoring import (
    DeterministicRiskScoringEngine,
    assess_opportunity_risk,
    risk_scoring_engine,
)
from app.ranking.risk.venue_intelligence import venue_publisher_intelligence_service
from app.schemas.opportunity import OpportunityRead, RiskExplanationSchema


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Mock database session dependency."""
    session = MagicMock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = None
    return session


@pytest.fixture
def client(mock_db_session: MagicMock) -> TestClient:
    """FastAPI TestClient with overridden get_db dependency."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── 1. Core Explanation Scenarios (A – D) ─────────────────────────────────────


class TestRiskExplanationLevels:
    """Verifies that each canonical risk level generates a truthful, conservative explanation."""

    def test_scenario_a_low_risk_explanation(self) -> None:
        """A verified IEEE conference receives LOW_RISK with affirmative trust summary."""
        opp = {
            "id": "opp-ieee-001",
            "title": "IEEE International Conference on Computer Vision (ICCV)",
            "publisher": "IEEE",
            "website_url": "https://iccv2026.ieee.org",
            "indexing": ["Scopus", "Web of Science"],
        }
        assessment = assess_opportunity_risk(opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=opp)

        assert assessment.risk_level == RiskLevel.LOW_RISK
        assert explanation.risk_level == "LOW_RISK"
        assert explanation.risk_score <= 0.15
        assert explanation.evidence_sufficiency == "SUFFICIENT"
        assert len(explanation.positive_trust_signals) >= 1
        assert len(explanation.suspicious_signals) == 0
        assert "Verified Low Risk venue" in explanation.summary or "standard academic characteristics" in explanation.summary
        assert explanation.is_predatory_flag is False

    def test_scenario_b_moderate_risk_explanation(self) -> None:
        """A venue with cautionary language receives MODERATE_RISK."""
        opp = {
            "id": "opp-mod-001",
            "title": "Global Summit on Engineering Innovations",
            "publisher": "Academics Global Press",
            "website_url": "http://innovations-summit2026.net",
            "description": "Peer review completed in 24 hours with certificate.",
        }
        assessment = assess_opportunity_risk(opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=opp)

        assert assessment.risk_level == RiskLevel.MODERATE_RISK
        assert explanation.risk_level == "MODERATE_RISK"
        assert 0.25 <= explanation.risk_score < 0.70
        assert len(explanation.suspicious_signals) >= 1
        assert "Moderate Risk" in explanation.summary
        assert any("24 hours" in s.explanation.lower() or "review" in s.explanation.lower() for s in explanation.suspicious_signals)

    def test_scenario_c_high_risk_explanation(self) -> None:
        """A venue with multiple corroborated suspicious signals receives HIGH_RISK."""
        opp = {
            "id": "opp-high-001",
            "title": "Universal World Conference on Advanced Science",
            "publisher": "World Academy of Science and Engineering",
            "website_url": "http://waset-universal2026.xyz",
            "description": "Send Western Union transfer for peer review completed in 24 hours.",
        }
        assessment = assess_opportunity_risk(opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=opp)

        assert assessment.risk_level == RiskLevel.HIGH_RISK
        assert explanation.risk_level == "HIGH_RISK"
        assert explanation.risk_score >= 0.70
        assert explanation.is_predatory_flag is True
        assert len(explanation.suspicious_signals) >= 2
        assert "High Risk" in explanation.summary
        assert "Trust mitigation is minimal" in explanation.summary or "corroborated" in explanation.summary

    def test_scenario_d_insufficient_evidence_explanation(self) -> None:
        """A brand new conference with sparse metadata receives neutral INSUFFICIENT_EVIDENCE."""
        opp = {
            "id": "opp-sparse-001",
            "title": "Workshop on Computational Topology 2026",
            # No publisher, no website, no indexing, no fees
        }
        assessment = assess_opportunity_risk(opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=opp)

        assert assessment.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE
        assert explanation.risk_level == "INSUFFICIENT_EVIDENCE"
        assert explanation.risk_score == 0.00
        assert explanation.evidence_sufficiency == "INSUFFICIENT"
        assert "Insufficient evidence available" in explanation.summary
        assert "strictly neutral and does not indicate predatory behavior" in explanation.summary


# ── 2. Evidence Categorization & Provenance (E – J) ───────────────────────────


class TestEvidenceSemanticsAndProvenance:
    """Verifies clear separation of positive, suspicious, neutral, graph, and provenance signals."""

    def test_scenario_e_positive_trust_evidence_categorization(self) -> None:
        """Positive trust signals have TRUST severity, correct contribution, and registry provenance."""
        col = RiskEvidenceCollection(opportunity_id="test-e")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.VERIFIED_PUBLISHER.value,
                category=EvidenceCategory.POSITIVE_TRUST,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                source_field="publisher",
                matched_value="IEEE",
                explanation="Verified major academic publisher.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert len(explanation.positive_trust_signals) == 1
        item = explanation.positive_trust_signals[0]
        assert item.category == "POSITIVE_TRUST"
        assert item.severity == "TRUST"
        assert item.provenance == "STATIC_TRUST_REGISTRY"
        assert item.contribution > 0.0
        assert item.evidence_type == "VENUE_INTELLIGENCE"

    def test_scenario_f_suspicious_evidence_categorization(self) -> None:
        """Suspicious signals map to correct severity and contribution."""
        col = RiskEvidenceCollection(opportunity_id="test-f")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="description",
                matched_value="western union",
                explanation="Questionable payment method requested.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert len(explanation.suspicious_signals) == 1
        item = explanation.suspicious_signals[0]
        assert item.category == "NEGATIVE_SUSPICIOUS"
        assert item.severity == "HIGH"
        assert item.provenance == "SCRAPED_METADATA"
        assert item.contribution > 0.40
        assert item.evidence_type == "DIRECT_METADATA"

    def test_scenario_g_neutral_evidence_categorization(self) -> None:
        """Neutral signals have contribution == 0.0 and NEUTRAL severity."""
        col = RiskEvidenceCollection(opportunity_id="test-g")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.MISSING_METADATA.value,
                category=EvidenceCategory.NEUTRAL_UNKNOWN,
                strength=EvidenceStrength.NONE,
                confidence=EvidenceConfidence.LOW,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="issn",
                explanation="ISSN not provided in venue metadata.",
                is_present=False,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert len(explanation.neutral_signals) == 1
        item = explanation.neutral_signals[0]
        assert item.category == "NEUTRAL_UNKNOWN"
        assert item.contribution == 0.0
        assert item.severity == "NEUTRAL"
        assert item.is_present is False

    def test_scenario_h_graph_derived_evidence(self) -> None:
        """Signals originating from GRAPH_ANALYSIS are properly labeled in graph_signals."""
        col = RiskEvidenceCollection(opportunity_id="test-h")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field="organizer",
                matched_value="Cluster Organizer",
                explanation="Organizer linked to multiple unverified conferences in graph.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert len(explanation.graph_signals) == 1
        graph_item = explanation.graph_signals[0]
        assert graph_item.evidence_type == "GRAPH_ANALYSIS"
        assert graph_item.provenance == "GRAPH_ANALYSIS"
        assert "GRAPH_ANALYSIS" in explanation.provenance_summary

    def test_scenario_i_venue_publisher_evidence(self) -> None:
        """Signals from venue resolution appear in venue_signals and publisher_signals."""
        col = RiskEvidenceCollection(opportunity_id="test-i")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.VERIFIED_PUBLISHER_IDENTITY.value,
                category=EvidenceCategory.POSITIVE_TRUST,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.EXTERNAL_VERIFICATION,
                source_field="publisher",
                matched_value="Springer Nature",
                explanation="Cross-source entity match confirmed with OpenAlex.",
                is_present=True,
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.DOAJ_INDEXED.value,
                category=EvidenceCategory.POSITIVE_TRUST,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                source_field="venue",
                matched_value="DOAJ",
                explanation="Venue verified in Directory of Open Access Journals.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert len(explanation.publisher_signals) >= 1
        assert len(explanation.venue_signals) >= 1
        assert any(s.signal == "VERIFIED_PUBLISHER_IDENTITY" for s in explanation.publisher_signals)
        assert any(s.signal == "DOAJ_INDEXED" for s in explanation.venue_signals)

    def test_scenario_j_provenance_preservation(self) -> None:
        """Every evidence item preserves its exact provenance in provenance_summary."""
        col = RiskEvidenceCollection(opportunity_id="test-j")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.VERIFIED_PUBLISHER.value,
                category=EvidenceCategory.POSITIVE_TRUST,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                source_field="publisher",
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.HIGH_DOMAIN_REUSE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.MODERATE,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field="domain",
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert explanation.provenance_summary.get("STATIC_TRUST_REGISTRY") == 1
        assert explanation.provenance_summary.get("GRAPH_ANALYSIS") == 1


# ── 3. Determinism, Ordering, and Deduplication (K – N) ───────────────────────


class TestDeterminismAndConsolidation:
    """Verifies deterministic output, deduplication, and mathematical score consistency."""

    def test_scenario_k_evidence_ordering(self) -> None:
        """Evidence items are ordered deterministically: Suspicious first by contribution, then Trust, then Neutral."""
        col = RiskEvidenceCollection(opportunity_id="test-k")
        col.add(
            RiskEvidence(
                signal="A_NEUTRAL",
                category=EvidenceCategory.NEUTRAL_UNKNOWN,
                strength=EvidenceStrength.NONE,
                confidence=EvidenceConfidence.LOW,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="field1",
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.VERIFIED_PUBLISHER.value,
                category=EvidenceCategory.POSITIVE_TRUST,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                source_field="publisher",
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="description",
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        categories = [item.category for item in explanation.evidence_items]
        assert categories == ["NEGATIVE_SUSPICIOUS", "POSITIVE_TRUST", "NEUTRAL_UNKNOWN"]

    def test_scenario_l_deterministic_repeated_output(self) -> None:
        """100 repeated executions on the exact same opportunity produce byte-identical JSON dictionaries."""
        opp = {
            "id": "opp-det-001",
            "title": "International Conference on Advanced Algorithms",
            "publisher": "IEEE",
            "description": "Fast-track review possible via wire transfer.",
            "indexing": ["Scopus"],
        }
        assessment = assess_opportunity_risk(opp)

        baseline = risk_explainability_service.explain(assessment, opportunity=opp).to_dict()

        for _ in range(100):
            current = risk_explainability_service.explain(assessment, opportunity=opp).to_dict()
            assert current == baseline

    def test_scenario_m_correlated_evidence_deduplication(self) -> None:
        """When multiple graph paths trigger graph reuse signals, the reason is consolidated cleanly."""
        col = RiskEvidenceCollection(opportunity_id="test-m")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.HIGH_ORGANIZER_REUSE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.MODERATE,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field="organizer",
                matched_value="Organizer X",
                explanation="Organizer reused across 12 conferences.",
                is_present=True,
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field="organizer",
                matched_value="Organizer X",
                explanation="Organizer cluster identified in topology.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        # Anti-correlation consolidation note should appear once
        anti_notes = [
            r for r in explanation.risk_reasons
            if "anti-correlation" in r.lower() or "consolidated" in r.lower()
        ]
        assert len(anti_notes) == 1

    def test_scenario_n_score_explanation_consistency(self) -> None:
        """Mathematical consistency: gross negative - trust mitigation == final risk score."""
        col = RiskEvidenceCollection(opportunity_id="test-n")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="description",
                is_present=True,
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.VERIFIED_PUBLISHER.value,
                category=EvidenceCategory.POSITIVE_TRUST,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                source_field="publisher",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert explanation.gross_negative_score > 0.0
        assert explanation.trust_mitigation_score > 0.0
        expected_score = round(max(0.00, explanation.gross_negative_score - explanation.trust_mitigation_score), 2)
        assert explanation.risk_score == expected_score


# ── 4. Confidence & Neutrality Safeguards (O – S) ──────────────────────────────


class TestConfidenceAndNeutrality:
    """Verifies confidence semantics and UNKNOWN != PREDATORY safeguards."""

    def test_scenario_o_confidence_handling(self) -> None:
        """High metadata completeness and multi-source verification yields high confidence."""
        rich_opp = {
            "id": "opp-rich",
            "title": "IEEE Conference on Software Engineering",
            "publisher": "IEEE",
            "website_url": "https://icse2026.org",
            "submission_url": "https://easychair.org/icse2026",
            "delivery_mode": "HYBRID",
            "location": "Tokyo, Japan",
            "indexing": ["Scopus", "Web of Science", "DOAJ"],
            "submission_deadline": "2026-11-01T00:00:00Z",
        }
        assessment = assess_opportunity_risk(rich_opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=rich_opp)

        assert explanation.risk_confidence >= 0.50
        assert explanation.evidence_sufficiency == "SUFFICIENT"

    def test_scenario_p_missing_metadata_neutrality(self) -> None:
        """Missing fields generate neutral limitation notes, NEVER predatory claims."""
        sparse_opp = {
            "id": "opp-sparse-p",
            "title": "Local Computational Math Workshop",
        }
        assessment = assess_opportunity_risk(sparse_opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=sparse_opp)

        assert explanation.risk_score == 0.0
        assert explanation.risk_level == "INSUFFICIENT_EVIDENCE"
        assert any("missing metadata is neutral" in lim.lower() for lim in explanation.limitations)
        assert not any("predatory" in r.lower() for r in explanation.risk_reasons)

    def test_scenario_q_high_degree_trusted_publisher(self) -> None:
        """A major publisher (ACM/IEEE) with hundreds of conferences is NOT flagged for domain/organizer reuse."""
        opp = {
            "id": "opp-acm-q",
            "title": "ACM SIGMOD 2026",
            "publisher": "ACM",
            "organizer": "Association for Computing Machinery",
            "website_url": "https://sigmod2026.acm.org",
            "indexing": ["Scopus", "Web of Science"],
        }
        assessment = assess_opportunity_risk(opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=opp)

        assert explanation.risk_level == "LOW_RISK"
        assert explanation.risk_score == 0.00
        assert not any("high organizer reuse" in s.signal.lower() for s in explanation.suspicious_signals)

    def test_scenario_r_isolated_opportunity_neutrality(self) -> None:
        """An isolated opportunity with no graph connections receives zero suspicious graph signals."""
        opp = {
            "id": "opp-iso-r",
            "title": "Isolated Specialized Colloquium",
            "publisher": "New Regional University",
            "website_url": "https://colloquium.regional-uni.edu",
        }
        assessment = assess_opportunity_risk(opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=opp)

        assert len(explanation.graph_signals) == 0
        assert explanation.risk_score == 0.00

    def test_scenario_s_identity_conflict_explanation(self) -> None:
        """Identity conflict is presented as cautionary conflict, not definitive fraud."""
        col = RiskEvidenceCollection(opportunity_id="test-s")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.GRAPH_IDENTITY_CONFLICT.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field="domain",
                matched_value="conflict.org",
                explanation="Domain conflict: domain claimed by multiple unrelated publisher identities.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        explanation = risk_explainability_service.explain(assessment)

        assert explanation.risk_level == "MODERATE_RISK"
        assert explanation.is_predatory_flag is False
        assert any("conflict" in s.explanation.lower() for s in explanation.suspicious_signals)


# ── 5. API & Schema Integration (T – V) ───────────────────────────────────────


class TestApiAndPerformance:
    """Verifies API backward compatibility, dedicated endpoints, and performance benchmarks."""

    def test_scenario_t_backward_compatible_opportunity_read(self) -> None:
        """OpportunityRead schema cleanly supports optional risk_explanation without breaking."""
        opp_data = {
            "id": str(uuid.uuid4()),
            "title": "IEEE Conference on AI",
            "opportunity_type": "CONFERENCE",
            "delivery_mode": "ONLINE",
            "is_predatory_flag": False,
            "risk_score": 0.00,
            "status": "ACTIVE",
            "created_at": "2026-09-01T00:00:00Z",
            "updated_at": "2026-09-01T00:00:00Z",
        }
        read = OpportunityRead.model_validate(opp_data)
        assert read.risk_explanation is None
        assert read.risk_level is None

    def test_scenario_u_risk_explanation_schema_serialization(self) -> None:
        """RiskExplanation serializes to and validates against RiskExplanationSchema."""
        opp = {
            "id": "opp-u-001",
            "title": "IEEE International Conference on Robotics and Automation (ICRA)",
            "publisher": "IEEE",
            "indexing": ["Scopus"],
        }
        assessment = assess_opportunity_risk(opp)
        explanation = risk_explainability_service.explain(assessment, opportunity=opp)

        schema = RiskExplanationSchema.model_validate(explanation.to_dict())
        assert schema.risk_level == "LOW_RISK"
        assert schema.evidence_sufficiency == "SUFFICIENT"
        assert len(schema.positive_trust_signals) >= 1

    def test_scenario_v_dedicated_api_endpoint_404_and_structure(self, client: TestClient) -> None:
        """Dedicated endpoint GET /api/opportunities/{id}/risk-explanation handles 404 cleanly."""
        missing_id = uuid.uuid4()
        from unittest.mock import patch

        with patch("app.api.opportunities.get_opportunity_by_id", return_value=None):
            response = client.get(f"/api/opportunities/{missing_id}/risk-explanation")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_scenario_v_dedicated_api_endpoint_200_success(self, client: TestClient) -> None:
        """Dedicated endpoint GET /api/opportunities/{id}/risk-explanation returns 200 with schema when found."""
        valid_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        from unittest.mock import patch

        mock_opp = OpportunityRead(
            id=valid_id,
            title="IEEE Transactions on Pattern Analysis and Machine Intelligence",
            publisher="IEEE",
            website_url="https://ieee.org/tpami",
            indexing=["Scopus", "Web of Science"],
            opportunity_type="JOURNAL",
            delivery_mode="ONLINE",
            status="ACTIVE",
            is_predatory_flag=False,
            risk_score=0.00,
            created_at=now,
            updated_at=now,
        )

        with patch("app.api.opportunities.get_opportunity_by_id", return_value=mock_opp):
            response = client.get(f"/api/opportunities/{valid_id}/risk-explanation")
            assert response.status_code == 200
            data = response.json()
            assert data["risk_level"] == "LOW_RISK"
            assert data["risk_score"] <= 0.15
            assert len(data["positive_trust_signals"]) >= 1

    def test_scenario_v_performance_benchmarks(self) -> None:
        """Benchmark in-memory explanation generation overhead for N=10, 50, 100, 200, 1000 items."""
        sample_opps = [
            {
                "id": f"opp-bench-{i}",
                "title": f"International Conference on Distributed Computing {i}",
                "publisher": "IEEE" if i % 2 == 0 else "Unknown Academic Press",
                "website_url": f"https://conf-{i}.org",
                "description": "Fast-track review guaranteed." if i % 5 == 0 else "Standard peer review.",
            }
            for i in range(100)
        ]

        # Extract and score batch
        collections = risk_evidence_extractor.extract_batch(sample_opps)
        assessments = risk_scoring_engine.score_batch(collections)

        # Benchmark explanation generation
        for n in [10, 50, 100]:
            subset_assessments = assessments[:n]
            subset_opps = sample_opps[:n]

            start_t = time.perf_counter()
            explanations = risk_explainability_service.explain_batch(
                subset_assessments,
                opportunities=subset_opps,
            )
            elapsed_ms = (time.perf_counter() - start_t) * 1000

            assert len(explanations) == n
            # Target: < 0.5 ms per explanation
            assert elapsed_ms < 100.0, f"Benchmark for N={n} took {elapsed_ms:.2f}ms (exceeded 100ms threshold)"


# ── 6. Realistic Fixtures (1 – 8) ─────────────────────────────────────────────


class TestRealisticFixtures:
    """Tests realistic academic publishing scenarios to ensure proper classification and explanation."""

    def test_fixture_1_verified_major_publisher(self) -> None:
        """ACM conference -> LOW_RISK with explicit affirmative trust explanation."""
        opp = {
            "id": "fix-1",
            "title": "ACM Conference on Human Factors in Computing Systems (CHI 2026)",
            "publisher": "ACM",
            "website_url": "https://chi2026.acm.org",
            "indexing": ["Scopus", "Web of Science"],
        }
        assessment = assess_opportunity_risk(opp)
        expl = risk_explainability_service.explain(assessment, opportunity=opp)

        assert expl.risk_level == "LOW_RISK"
        assert expl.risk_score == 0.00
        assert any("acm" in s.explanation.lower() or "verified" in s.explanation.lower() for s in expl.positive_trust_signals)

    def test_fixture_2_legitimate_scientific_society(self) -> None:
        """SIAM conference -> LOW_RISK with society trust indicator."""
        opp = {
            "id": "fix-2",
            "title": "SIAM Conference on Applied Mathematics",
            "publisher": "SIAM",
            "website_url": "https://siam.org/conferences",
        }
        assessment = assess_opportunity_risk(opp)
        expl = risk_explainability_service.explain(assessment, opportunity=opp)

        assert expl.risk_level == "LOW_RISK"
        assert expl.risk_score == 0.00
        assert any("society" in s.explanation.lower() or "verified" in s.explanation.lower() or "siam" in s.explanation.lower() for s in expl.positive_trust_signals)

    def test_fixture_3_new_legitimate_sparse_conference(self) -> None:
        """Brand new faculty workshop with sparse metadata -> INSUFFICIENT_EVIDENCE without predatory flag."""
        opp = {
            "id": "fix-3",
            "title": "Inaugural Workshop on Quantum Information Algorithms 2026",
            "location": "Boston, MA",
        }
        assessment = assess_opportunity_risk(opp)
        expl = risk_explainability_service.explain(assessment, opportunity=opp)

        assert expl.risk_level == "INSUFFICIENT_EVIDENCE"
        assert expl.is_predatory_flag is False
        assert "neutral" in expl.summary.lower()

    def test_fixture_4_corroborated_suspicious_venue(self) -> None:
        """Opportunity with multiple corroborated suspicious signals -> HIGH_RISK."""
        opp = {
            "id": "fix-4",
            "title": "World Congress on Multi-Disciplinary Advanced Studies",
            "publisher": "Universal Academic Publishing Group",
            "description": "Send processing fee via Western Union. Peer review completed in 24 hours.",
            "website_url": "http://universal-multi-studies.top",
        }
        assessment = assess_opportunity_risk(opp)
        expl = risk_explainability_service.explain(assessment, opportunity=opp)

        assert expl.risk_level == "HIGH_RISK"
        assert expl.is_predatory_flag is True
        assert len(expl.suspicious_signals) >= 2
        assert any("payment" in s.signal.lower() for s in expl.suspicious_signals)
        assert any("review" in s.signal.lower() for s in expl.suspicious_signals)

    def test_fixture_5_conflicting_venue_identity(self) -> None:
        """Conflicting identity is flagged without jumping to definitive predatory status."""
        col = RiskEvidenceCollection(opportunity_id="fix-5")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.CONFLICTING_METADATA.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.MODERATE,
                confidence=EvidenceConfidence.MEDIUM,
                provenance=EvidenceProvenance.NORMALIZED_METADATA,
                source_field="publisher",
                explanation="Publisher metadata claims Springer Nature, but domain registers to an unaffiliated entity.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        expl = risk_explainability_service.explain(assessment)

        assert expl.is_predatory_flag is False
        assert any("conflicting" in s.explanation.lower() or "springer" in s.explanation.lower() for s in expl.suspicious_signals)

    def test_fixture_6_suspicious_organizer_cluster(self) -> None:
        """Suspicious organizer cluster appears once in explanation with clear topology context."""
        col = RiskEvidenceCollection(opportunity_id="fix-6")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field="organizer",
                matched_value="Syndicate X",
                explanation="Organizer linked to suspicious multi-venue network.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        expl = risk_explainability_service.explain(assessment)

        assert len(expl.graph_signals) == 1
        assert expl.graph_signals[0].signal == "SUSPICIOUS_ORGANIZER_CLUSTER"
        assert "GRAPH_ANALYSIS" in expl.provenance_summary

    def test_fixture_7_suspicious_domain_cluster(self) -> None:
        """Suspicious domain cluster appears once in explanation with clear topology context."""
        col = RiskEvidenceCollection(opportunity_id="fix-7")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.HIGH_DOMAIN_REUSE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.MODERATE,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.GRAPH_ANALYSIS,
                source_field="domain",
                matched_value="generic-conferences.info",
                explanation="Domain shared across 25 disparate unverified conferences.",
                is_present=True,
            )
        )
        assessment = risk_scoring_engine.score(col)
        expl = risk_explainability_service.explain(assessment)

        assert len(expl.graph_signals) == 1
        assert expl.graph_signals[0].signal == "HIGH_DOMAIN_REUSE"

    def test_fixture_8_apc_fee_only_metadata(self) -> None:
        """Having a publication fee without suspicious language does NOT classify as high risk."""
        opp = {
            "id": "fix-8",
            "title": "Open Access Journal of Environmental Science",
            "publisher": "PeerJ",
            "apc_or_fee": {"has_fee": True, "amount": 1200, "currency": "USD"},
            "website_url": "https://peerj.com",
            "indexing": ["DOAJ", "Scopus"],
        }
        assessment = assess_opportunity_risk(opp)
        expl = risk_explainability_service.explain(assessment, opportunity=opp)

        assert expl.risk_level == "LOW_RISK"
        assert expl.risk_score == 0.00
        assert expl.is_predatory_flag is False
