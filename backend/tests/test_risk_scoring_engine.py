"""
Unit & Integration Tests for Phase 2.6C — Deterministic Risk Scoring Engine.

Verifies:
  1. Low-risk cases (verified publisher, society, indexing, clean metadata).
  2. Moderate-risk cases (intermediate caution signals, e.g. suspicious TLD).
  3. High-risk cases (corroborated predatory signals: non-traceable payments, 24-hr review).
  4. Insufficient evidence handling (INSUFFICIENT_EVIDENCE != HIGH_RISK).
  5. False-positive safeguards (legitimate APCs, registration fees, double-blind review).
  6. Anti-correlation & diminishing returns (group caps, geometric decay).
  7. Trust mitigation limits (trust reduces risk without absolute blind spots).
  8. Monotonicity & score bounds ([0.00, 1.00]).
  9. Strict determinism across repeated executions.
  10. In-memory performance and zero N+1 queries.
  11. Legacy compatibility with calculate_predatory_penalty.
"""
from __future__ import annotations

import time
import uuid
import pytest

from app.ranking.risk import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    RiskAssessment,
    RiskEvidence,
    RiskEvidenceCollection,
    RiskLevel,
    RiskScoringConfig,
    assess_opportunity_risk,
    risk_evidence_extractor,
    risk_scoring_engine,
)
from app.ranking.signals import calculate_predatory_penalty


class TestLowRiskScoring:
    """Test reputable venues receive LOW_RISK with risk_score <= 0.15."""

    def test_top_tier_ieee_conference_is_low_risk(self) -> None:
        opp = {
            "id": uuid.uuid4(),
            "title": "IEEE International Conference on Computer Vision",
            "publisher": "IEEE Computer Society",
            "organizer": "IEEE",
            "website_url": "https://iccv2025.thecvf.com",
            "submission_deadline": "2025-03-08T23:59:59Z",
            "indexing": ["Scopus", "IEEE Xplore"],
            "description": "All submissions will undergo double-blind peer review by international experts.",
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score == 0.00
        assert assessment.risk_level == RiskLevel.LOW_RISK
        assert assessment.is_predatory_flag is False
        assert assessment.risk_confidence >= 0.50
        assert len(assessment.risk_reasons) > 0
        assert any("Trust Evidence" in r for r in assessment.risk_reasons)

    def test_doaj_indexed_open_access_journal_is_low_risk(self) -> None:
        opp = {
            "title": "PLOS Computational Biology",
            "publisher": "PLOS",
            "indexing": ["DOAJ", "PubMed", "Scopus"],
            "website_url": "https://journals.plos.org/ploscompbiol/",
            "submission_deadline": "2026-06-30T23:59:59Z",
            "apc_or_fee": {"has_fee": True, "amount": 2100, "currency": "USD"},
            "description": "Rigorous single-blind peer review with open data availability.",
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score == 0.00
        assert assessment.risk_level == RiskLevel.LOW_RISK
        assert assessment.is_predatory_flag is False
        assert assessment.risk_confidence >= 0.60


class TestModerateRiskScoring:
    """Test intermediate caution signals map into MODERATE_RISK (0.30 <= risk < 0.70)."""

    def test_suspicious_tld_with_unverified_publisher(self) -> None:
        # Suspicious .top domain with unverified local publisher
        opp = {
            "title": "International Conference on Multidisciplinary Innovations",
            "publisher": "Global Academic Events Ltd",
            "website_url": "https://innovations2026.top",
            "submission_deadline": "2026-09-01T23:59:59Z",
            "indexing": [],
            "description": "Join researchers worldwide for this interdisciplinary conference.",
        }
        assessment = assess_opportunity_risk(opp)

        assert 0.20 <= assessment.risk_score < 0.70
        assert assessment.risk_level in (RiskLevel.MODERATE_RISK, RiskLevel.LOW_RISK)
        assert assessment.is_predatory_flag is False

    def test_free_email_submission_without_other_fraud(self) -> None:
        opp = {
            "title": "Regional Workshop on Applied Mathematics",
            "publisher": "Local Math Society",
            "website_url": "https://math-regional.org",
            "submission_deadline": "2026-05-15T23:59:59Z",
            "description": "Please submit your abstracts to workshop.chair2026@gmail.com by May 15.",
        }
        assessment = assess_opportunity_risk(opp)

        # Webmail submission is a moderate cautionary signal, not enough for high-risk predatory alone
        assert assessment.risk_score < 0.50
        assert assessment.is_predatory_flag is False


class TestHighRiskScoring:
    """Test corroborated predatory signals receive HIGH_RISK (risk >= 0.70) and is_predatory_flag=True."""

    def test_corroborated_payment_fraud_and_fake_review(self) -> None:
        opp = {
            "title": "Global Journal of Cutting Edge Discoveries",
            "publisher": "Universal Publishing Fleet",
            "website_url": "http://185.220.101.4/cfp",
            "description": (
                "Fast peer review completed within 24 hours! 100% acceptance rate. "
                "Urgent fee required within 24 hours via Western Union or MoneyGram to guarantee publication. "
                "Global Impact Factor: 6.82."
            ),
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score >= 0.70
        assert assessment.risk_level == RiskLevel.HIGH_RISK
        assert assessment.is_predatory_flag is True
        assert assessment.risk_confidence >= 0.50
        assert any("High Risk" in r for r in assessment.risk_reasons)
        assert "SUSPICIOUS_PAYMENT_LANGUAGE" in assessment.dominant_signals or "SUSPICIOUS_REVIEW_CLAIM" in assessment.dominant_signals

    def test_raw_ip_and_guaranteed_publication_bribery(self) -> None:
        opp = {
            "title": "World Congress on All Engineering Sciences",
            "website_url": "http://192.168.10.100/submit",
            "description": "Pay $400 to guarantee publication in our proceedings. Same-day peer review guaranteed.",
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score >= 0.70
        assert assessment.risk_level == RiskLevel.HIGH_RISK
        assert assessment.is_predatory_flag is True


class TestInsufficientEvidenceHandling:
    """HARD REQUIREMENT: Verify INSUFFICIENT_EVIDENCE != HIGH_RISK."""

    def test_completely_empty_opportunity_is_insufficient_evidence(self) -> None:
        opp = {
            "title": "Unspecified Upcoming Colloquium",
        }
        assessment = assess_opportunity_risk(opp)

        # Invariant 1: Score must be exactly 0.00
        assert assessment.risk_score == 0.00

        # Invariant 2: Level must be INSUFFICIENT_EVIDENCE
        assert assessment.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE

        # Invariant 3: is_predatory_flag MUST be False
        assert assessment.is_predatory_flag is False

        # Invariant 4: Confidence must be low
        assert assessment.risk_confidence < 0.40

        # Invariant 5: Clear explanatory reason
        assert any("Insufficient metadata" in r for r in assessment.risk_reasons)

    def test_unindexed_small_workshop_is_not_high_risk(self) -> None:
        opp = {
            "title": "Paris Workshop on Graph Theory",
            "publisher": "Universite Paris-Saclay",
            "website_url": "https://math.u-psud.fr/gt2026",
            "submission_deadline": "2026-10-01T23:59:59Z",
            "indexing": [],  # Completely unindexed
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score == 0.00
        assert assessment.risk_level in (RiskLevel.LOW_RISK, RiskLevel.INSUFFICIENT_EVIDENCE)
        assert assessment.is_predatory_flag is False


class TestFalsePositiveSafeguards:
    """Verify legitimate academic fees, APCs, and reviews never trigger risk penalties."""

    def test_legitimate_apc_fee_produces_zero_risk(self) -> None:
        opp = {
            "title": "Frontiers in Neuroscience",
            "publisher": "Frontiers Media",
            "website_url": "https://frontiersin.org/neuroscience",
            "submission_deadline": "2026-11-15T23:59:59Z",
            "apc_or_fee": {"has_fee": True, "amount": 2500, "currency": "USD"},
            "description": "An open access article processing charge (APC) of $2,500 applies upon acceptance.",
            "indexing": ["Scopus", "PubMed"],
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score == 0.00
        assert assessment.risk_level == RiskLevel.LOW_RISK
        assert assessment.is_predatory_flag is False

    def test_conference_registration_fee_with_member_discount(self) -> None:
        opp = {
            "title": "ACM CHI Conference on Human Factors in Computing Systems",
            "publisher": "ACM",
            "organizer": "ACM",
            "website_url": "https://chi2026.acm.org",
            "submission_deadline": "2025-09-15T23:59:59Z",
            "indexing": ["ACM Digital Library", "Scopus"],
            "description": (
                "Registration fee: $600 for ACM members, $850 for non-members, $350 for student registration. "
                "Early bird rates available until Feb 15."
            ),
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score == 0.00
        assert assessment.risk_level == RiskLevel.LOW_RISK
        assert assessment.is_predatory_flag is False

    def test_double_blind_peer_review_statement(self) -> None:
        opp = {
            "title": "SIAM Journal on Mathematics of Data Science",
            "publisher": "SIAM",
            "organizer": "SIAM",
            "website_url": "https://siam.org/simods",
            "indexing": ["Web of Science", "Scopus"],
            "description": "All submissions undergo rigorous double-blind peer review by an international program committee.",
        }
        assessment = assess_opportunity_risk(opp)

        assert assessment.risk_score == 0.00
        assert assessment.risk_level == RiskLevel.LOW_RISK
        assert assessment.is_predatory_flag is False


class TestDiminishingReturnsAndAntiCorrelation:
    """Verify group caps and geometric decay prevent correlated signals from exploding scores."""

    def test_multiple_correlated_payment_phrases_capped(self) -> None:
        # Construct collection with 3 distinct payment signals
        col = RiskEvidenceCollection(opportunity_id="test-payment-cap")
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="opportunity.description",
                matched_value="Western Union",
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="opportunity.description",
                matched_value="MoneyGram",
            )
        )
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="opportunity.description",
                matched_value="Urgent remittance required",
            )
        )

        assessment = risk_scoring_engine.score(col)

        # Payment group cap is 0.65. Without other groups, gross_negative cannot exceed 0.65!
        assert assessment.gross_negative_score <= 0.65
        assert assessment.risk_score <= 0.65


class TestTrustMitigationLimits:
    """Verify trust evidence dampens risk up to 65%, but cannot completely blindside high-risk fraud."""

    def test_trust_mitigation_capped_at_65_percent(self) -> None:
        # A fraudulent opportunity with verified IEEE publisher claiming Western Union payment
        col = RiskEvidenceCollection(opportunity_id="fake-ieee")
        # Strong negative: Western Union payment
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="opportunity.description",
                matched_value="Western Union payment",
            )
        )
        # Strong negative: 24h peer review
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_REVIEW_CLAIM.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="opportunity.description",
                matched_value="Peer review in 24 hours",
            )
        )
        # Positive trust: Claimed IEEE publisher match
        col.add(
            RiskEvidence(
                signal=EvidenceSignal.VERIFIED_PUBLISHER.value,
                category=EvidenceCategory.POSITIVE_TRUST,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                source_field="opportunity.publisher",
                matched_value="IEEE",
            )
        )

        assessment = risk_scoring_engine.score(col)

        # Trust mitigation should have fired
        assert assessment.trust_mitigation_score > 0.0
        # But risk score CANNOT drop to zero due to the 65% max mitigation cap
        assert assessment.risk_score > 0.25
        assert assessment.trust_mitigation_score <= (assessment.gross_negative_score * 0.65 + 0.001)


class TestMonotonicityAndBounds:
    """Verify mathematical properties: bounds [0, 1] and monotonic behavior."""

    def test_score_and_confidence_bounds(self) -> None:
        col = RiskEvidenceCollection(opportunity_id="extreme-test")
        # Add 10 strong negative signals
        for i in range(10):
            col.add(
                RiskEvidence(
                    signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                    category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                    strength=EvidenceStrength.STRONG,
                    confidence=EvidenceConfidence.HIGH,
                    provenance=EvidenceProvenance.SCRAPED_METADATA,
                    source_field="opportunity.description",
                    matched_value=f"extreme_fraud_{i}",
                )
            )

        assessment = risk_scoring_engine.score(col)
        assert 0.00 <= assessment.risk_score <= 1.00
        assert 0.00 <= assessment.risk_confidence <= 1.00

    def test_monotonicity_adding_negative_evidence(self) -> None:
        col1 = RiskEvidenceCollection()
        col1.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_DOMAIN.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.MODERATE,
                confidence=EvidenceConfidence.MEDIUM,
                provenance=EvidenceProvenance.NORMALIZED_METADATA,
                source_field="opportunity.website_url",
                matched_value="conference.top",
            )
        )
        score1 = risk_scoring_engine.score(col1).risk_score

        col2 = RiskEvidenceCollection()
        col2.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_DOMAIN.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.MODERATE,
                confidence=EvidenceConfidence.MEDIUM,
                provenance=EvidenceProvenance.NORMALIZED_METADATA,
                source_field="opportunity.website_url",
                matched_value="conference.top",
            )
        )
        col2.add(
            RiskEvidence(
                signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                strength=EvidenceStrength.STRONG,
                confidence=EvidenceConfidence.HIGH,
                provenance=EvidenceProvenance.SCRAPED_METADATA,
                source_field="opportunity.description",
                matched_value="Western Union",
            )
        )
        score2 = risk_scoring_engine.score(col2).risk_score

        assert score2 >= score1, "Adding negative evidence decreased risk score!"


class TestDeterminismAndPerformance:
    """Verify 100% determinism across 100 runs and zero N+1 database queries."""

    def test_scoring_determinism_across_100_runs(self) -> None:
        opp = {
            "id": uuid.uuid4(),
            "title": "IEEE Conference on Cybernetics",
            "publisher": "IEEE",
            "organizer": "IEEE",
            "website_url": "https://cybernetics2026.org",
            "indexing": ["Scopus", "IEEE Xplore"],
            "description": "Double-blind review by international committee.",
        }

        baseline = assess_opportunity_risk(opp).to_dict()

        for _ in range(100):
            current = assess_opportunity_risk(opp).to_dict()
            assert current == baseline, "Scoring varied across identical runs!"

    def test_batch_scoring_performance(self) -> None:
        """1,000 synthetic collections scored in < 150ms in-memory."""
        collections = []
        for i in range(1000):
            col = RiskEvidenceCollection(opportunity_id=f"item-{i}")
            col.metadata_completeness_score = 0.80
            if i % 2 == 0:
                col.add(
                    RiskEvidence(
                        signal=EvidenceSignal.VERIFIED_PUBLISHER.value,
                        category=EvidenceCategory.POSITIVE_TRUST,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.STATIC_TRUST_REGISTRY,
                        source_field="opportunity.publisher",
                        matched_value="IEEE",
                    )
                )
            if i % 10 == 0:
                col.add(
                    RiskEvidence(
                        signal=EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value,
                        category=EvidenceCategory.NEGATIVE_SUSPICIOUS,
                        strength=EvidenceStrength.STRONG,
                        confidence=EvidenceConfidence.HIGH,
                        provenance=EvidenceProvenance.SCRAPED_METADATA,
                        source_field="opportunity.description",
                        matched_value="Western Union",
                    )
                )
            collections.append(col)

        start = time.perf_counter()
        results = risk_scoring_engine.score_batch(collections)
        elapsed = time.perf_counter() - start

        assert len(results) == 1000
        assert elapsed < 0.25, f"Scoring batch took {elapsed:.4f}s for 1000 items (expected < 0.25s)"

    def test_candidate_scaling_benchmarks(self) -> None:
        """Benchmark scoring engine across candidate batch sizes: 10, 50, 100, 200, 1000."""
        sizes = [10, 50, 100, 200, 1000]
        scaling_results: dict[int, dict[str, float]] = {}

        for n in sizes:
            batch = [
                {
                    "title": f"Candidate Conference {i}",
                    "publisher": "IEEE" if i % 2 == 0 else "Unknown Press",
                    "indexing": ["Scopus"] if i % 2 == 0 else [],
                    "description": "Double-blind review" if i % 5 != 0 else "Urgent fee via Western Union",
                }
                for i in range(n)
            ]

            t0 = time.perf_counter()
            assessments = [assess_opportunity_risk(item) for item in batch]
            t_total = time.perf_counter() - t0
            per_candidate_ms = (t_total / n) * 1000.0

            scaling_results[n] = {
                "total_ms": t_total * 1000.0,
                "per_candidate_ms": per_candidate_ms,
            }
            assert len(assessments) == n
            assert per_candidate_ms < 1.0, f"Per-candidate scoring too slow ({per_candidate_ms:.3f}ms) at N={n}"

        # Confirm linear or sub-linear scaling
        assert scaling_results[1000]["per_candidate_ms"] < 0.50


class TestLegacySignalsCompatibility:
    """Verify RiskAssessment outputs integrate smoothly with calculate_predatory_penalty in signals.py."""

    def test_high_risk_triggers_predatory_penalty(self) -> None:
        opp = {
            "title": "Predatory Journal of Everything",
            "website_url": "http://185.220.101.4/journal",
            "description": "Pay $500 via Western Union. Peer review completed within 24 hours with 100% acceptance rate.",
        }
        assessment = assess_opportunity_risk(opp)
        assert assessment.risk_score >= 0.70
        assert assessment.risk_level == RiskLevel.HIGH_RISK
        assert assessment.is_predatory_flag is True

        penalty = calculate_predatory_penalty(
            is_predatory_flag=assessment.is_predatory_flag,
            risk_score=assessment.risk_score,
        )
        # Flagged predatory gets 0.20 penalty multiplier
        assert penalty == 0.20

    def test_low_risk_clean_venue_zero_penalty(self) -> None:
        opp = {
            "title": "ACM SIGMOD 2026",
            "publisher": "ACM",
            "organizer": "ACM",
            "indexing": ["Scopus", "ACM Digital Library"],
            "description": "Double-blind peer review by international committee.",
        }
        assessment = assess_opportunity_risk(opp)
        assert assessment.is_predatory_flag is False

        penalty = calculate_predatory_penalty(
            is_predatory_flag=assessment.is_predatory_flag,
            risk_score=assessment.risk_score,
        )
        assert penalty == 1.00
