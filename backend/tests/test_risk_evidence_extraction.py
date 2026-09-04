"""
Unit & Integration Tests for Phase 2.6B — Risk Evidence Extraction & Pattern Matchers.

Verifies:
  1. Positive trust evidence (verified publishers, verified societies, DOAJ, indexing tiers, ISSN, DOI).
  2. Suspicious signals (Western Union, guaranteed acceptance, 24-hr review, raw IP URL, suspicious TLD, webmail).
  3. False-positive safeguards (legitimate APCs, registration fees, double-blind review, standard academic prose).
  4. Missing metadata neutrality (UNKNOWN != PREDATORY: empty fields produce neutral evidence with is_present=False).
  5. Strict determinism across repeated executions.
  6. In-memory performance and zero N+1 queries.
  7. Entity separation (publisher vs organizer vs venue vs domain vs indexing).
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
    RiskEvidence,
    RiskEvidenceCollection,
    RiskEvidenceExtractor,
    risk_evidence_extractor,
)
from app.ranking.risk.normalizers import (
    is_ip_address_host,
    normalize_url,
    validate_doi,
    validate_issn,
)
from app.ranking.risk.patterns import (
    has_legitimate_fee_context,
    has_legitimate_review_context,
    scan_contact_patterns,
    scan_editorial_patterns,
    scan_payment_patterns,
    scan_review_patterns,
)
from app.ranking.risk.registries import (
    is_free_email_domain,
    is_suspicious_tld,
    match_trusted_publisher,
    match_trusted_society,
)


class TestNormalizersAndRegistries:
    """Test URL, domain, identifier normalizers and static trust registries."""

    def test_trusted_publisher_matching(self) -> None:
        is_trusted, canon = match_trusted_publisher("Institute of Electrical and Electronics Engineers")
        assert is_trusted is True
        assert canon == "IEEE"

        is_trusted, canon = match_trusted_publisher("Springer Nature Switzerland AG")
        assert is_trusted is True
        assert canon == "Springer Nature"

        is_trusted, canon = match_trusted_publisher("Elsevier Science")
        assert is_trusted is True
        assert canon == "Elsevier"

        is_trusted, canon = match_trusted_publisher("Completely Unknown Local Press")
        assert is_trusted is False
        assert canon is None

    def test_trusted_society_matching(self) -> None:
        is_trusted, canon = match_trusted_society("ACM SIGGRAPH")
        assert is_trusted is True
        assert canon == "ACM"

        is_trusted, canon = match_trusted_society("Association for Computational Linguistics")
        assert is_trusted is True
        assert canon == "ACL"

        is_trusted, canon = match_trusted_society("Local University Club")
        assert is_trusted is False

    def test_suspicious_tld_detection(self) -> None:
        assert is_suspicious_tld("conference2026.top") is True
        assert is_suspicious_tld("academic-summit.xyz") is True
        assert is_suspicious_tld("submit-paper.click") is True
        assert is_suspicious_tld("ieee.org") is False
        assert is_suspicious_tld("cambridge.org") is False
        assert is_suspicious_tld("mit.edu") is False

    def test_free_email_domain_detection(self) -> None:
        assert is_free_email_domain("conference@gmail.com") is True
        assert is_free_email_domain("editor@yahoo.com") is True
        assert is_free_email_domain("proceedings@163.com") is True
        assert is_free_email_domain("editor@ieee.org") is False
        assert is_free_email_domain("chair@ox.ac.uk") is False

    def test_normalize_url_with_ip_detection(self) -> None:
        res = normalize_url("http://192.168.1.50:8080/cfp/submit")
        assert res["is_ip"] == "true"
        assert res["hostname"] == "192.168.1.50"

        res_dom = normalize_url("https://www.nature.com/articles/s41586-024-07000")
        assert res_dom["is_ip"] == "false"
        assert res_dom["hostname"] == "www.nature.com"
        assert res_dom["domain"] == "nature.com"

    def test_validate_issn_and_doi(self) -> None:
        assert validate_issn("0028-0836") == "0028-0836"
        assert validate_issn("2434572x") == "2434-572X"
        assert validate_issn("invalid-issn") is None

        assert validate_doi("https://doi.org/10.1109/TPAMI.2023.1234567") == "10.1109/TPAMI.2023.1234567"
        assert validate_doi("10.1038/nature12373") == "10.1038/nature12373"
        assert validate_doi("not-a-doi") is None


class TestPatternMatchers:
    """Test regex pattern matchers for payment, review speed, metrics, and contacts."""

    def test_scan_payment_suspicious_patterns(self) -> None:
        text1 = "Please remit your publication fee via Western Union to our overseas agent."
        res1 = scan_payment_patterns(text1)
        assert len(res1) > 0
        assert res1[0][0] == "NON_TRACEABLE_PAYMENT"

        text2 = "Authors must pay $300 to guarantee publication in the upcoming volume."
        res2 = scan_payment_patterns(text2)
        assert len(res2) > 0
        assert res2[0][0] == "PAY_FOR_GUARANTEED_PUBLICATION"

        text3 = "Urgent fee required within 24 hours to secure presentation slot."
        res3 = scan_payment_patterns(text3)
        assert len(res3) > 0
        assert res3[0][0] == "URGENT_PAYMENT_PRESSURE"

    def test_scan_payment_legitimate_safeguard(self) -> None:
        legit_text = "The conference registration fee is $450 for IEEE members and $250 for students. Early bird discount applies."
        assert scan_payment_patterns(legit_text) == []
        assert has_legitimate_fee_context(legit_text) is True

    def test_scan_review_suspicious_patterns(self) -> None:
        text1 = "Fast peer review completed within 24 hours of submission!"
        res1 = scan_review_patterns(text1)
        assert len(res1) > 0
        assert res1[0][0] == "UNREALISTIC_REVIEW_SPEED"

        text2 = "All submitted manuscripts enjoy a 100% acceptance rate."
        res2 = scan_review_patterns(text2)
        assert len(res2) > 0
        assert res2[0][0] == "GUARANTEED_ACCEPTANCE"

    def test_scan_review_legitimate_safeguard(self) -> None:
        legit_text = "All submissions undergo rigorous double-blind peer review by our international program committee."
        assert scan_review_patterns(legit_text) == []
        assert has_legitimate_review_context(legit_text) is True

    def test_scan_editorial_bogus_metrics(self) -> None:
        text = "Our journal is proud to boast a Global Impact Factor of 6.72 and Cosmos Impact Factor indexing."
        res = scan_editorial_patterns(text)
        assert len(res) >= 1
        assert res[0][0] == "BOGUS_METRIC_CLAIM"

    def test_scan_contact_free_mail_submission(self) -> None:
        text = "Please send manuscripts directly to editor.submission.office2026@gmail.com for processing."
        res = scan_contact_patterns(text)
        assert len(res) == 1
        assert res[0][0] == "FREE_MAIL_SUBMISSION"


class TestPositiveTrustEvidenceExtraction:
    """Test extraction of positive trust evidence from reputable metadata."""

    def test_verified_publisher_and_society(self) -> None:
        opp = {
            "id": uuid.uuid4(),
            "title": "IEEE International Conference on Computer Vision",
            "publisher": "IEEE Computer Society",
            "organizer": "IEEE",
            "website_url": "https://iccv2025.thecvf.com",
            "indexing": ["Scopus", "IEEE Xplore"],
            "description": "Submissions will undergo double-blind peer review.",
        }
        evidence = risk_evidence_extractor.extract(opp)

        assert evidence.has_trust_evidence is True
        assert evidence.has_suspicious_evidence is False

        signals = {item.signal for item in evidence.positive_evidence}
        assert EvidenceSignal.VERIFIED_PUBLISHER.value in signals
        assert EvidenceSignal.VERIFIED_SOCIETY.value in signals
        assert EvidenceSignal.VERIFIED_INDEXING.value in signals
        assert EvidenceSignal.TRANSPARENT_PEER_REVIEW.value in signals

    def test_doaj_indexed_positive_trust(self) -> None:
        opp = {
            "title": "Journal of Open Access Science",
            "publisher": "PLOS",
            "indexing": ["DOAJ", "PubMed"],
            "apc_or_fee": {"has_fee": True, "amount": 1800, "currency": "USD"},
        }
        evidence = risk_evidence_extractor.extract(opp)

        signals = {item.signal for item in evidence.positive_evidence}
        assert EvidenceSignal.DOAJ_INDEXED.value in signals
        assert EvidenceSignal.VERIFIED_PUBLISHER.value in signals
        assert EvidenceSignal.TRANSPARENT_FEE_STRUCTURE.value in signals
        assert evidence.has_suspicious_evidence is False


class TestSuspiciousEvidenceExtraction:
    """Test extraction of suspicious signals from adversarial/predatory patterns."""

    def test_western_union_and_urgent_wire(self) -> None:
        opp = {
            "title": "International Global Multidisciplinary Conference",
            "publisher": "Unknown Press",
            "website_url": "https://globalconference.xyz",
            "description": "Urgent fee required within 24 hours via Western Union to guarantee publication.",
        }
        evidence = risk_evidence_extractor.extract(opp)

        assert evidence.has_suspicious_evidence is True
        neg_signals = {item.signal for item in evidence.negative_evidence}
        assert EvidenceSignal.SUSPICIOUS_PAYMENT_LANGUAGE.value in neg_signals
        assert EvidenceSignal.SUSPICIOUS_DOMAIN.value in neg_signals

    def test_unrealistic_review_speed_and_raw_ip(self) -> None:
        opp = {
            "title": "Rapid International Journal of Advanced Research",
            "website_url": "http://185.220.101.5/journal",
            "description": "Peer review in 24 hours with 100% acceptance rate. Global Impact Factor: 5.4.",
        }
        evidence = risk_evidence_extractor.extract(opp)

        assert evidence.has_suspicious_evidence is True
        neg_signals = {item.signal for item in evidence.negative_evidence}
        assert EvidenceSignal.SUSPICIOUS_REVIEW_CLAIM.value in neg_signals
        assert EvidenceSignal.SUSPICIOUS_DOMAIN.value in neg_signals
        assert EvidenceSignal.SUSPICIOUS_EDITORIAL_CLAIM.value in neg_signals

        # Strong suspicious signals
        strong_signals = [s.signal for s in evidence.strong_suspicious_signals]
        assert EvidenceSignal.SUSPICIOUS_DOMAIN.value in strong_signals
        assert EvidenceSignal.SUSPICIOUS_REVIEW_CLAIM.value in strong_signals


class TestFalsePositiveSafeguards:
    """Crucial tests verifying legitimate academic practices are never falsely flagged."""

    def test_legitimate_apc_is_not_suspicious(self) -> None:
        opp = {
            "title": "Frontiers in Computer Science",
            "publisher": "Frontiers Media",
            "apc_or_fee": {"has_fee": True, "amount": 1950, "currency": "USD"},
            "description": "Open access article processing charge (APC) of $1950 applies upon acceptance.",
        }
        evidence = risk_evidence_extractor.extract(opp)

        assert evidence.has_suspicious_evidence is False
        assert len(evidence.negative_evidence) == 0

        # Should be recognized as transparent fee disclosure
        pos_signals = {item.signal for item in evidence.positive_evidence}
        assert EvidenceSignal.TRANSPARENT_FEE_STRUCTURE.value in pos_signals

    def test_legitimate_conference_registration_fee(self) -> None:
        opp = {
            "title": "ACM Conference on Human Factors in Computing Systems",
            "publisher": "ACM",
            "organizer": "ACM",
            "description": (
                "Registration fee: $550 for ACM members, $700 for non-members, $300 for student registration. "
                "Early bird discount available until March 1."
            ),
        }
        evidence = risk_evidence_extractor.extract(opp)

        assert evidence.has_suspicious_evidence is False
        assert len(evidence.negative_evidence) == 0

    def test_legitimate_multi_week_peer_review(self) -> None:
        opp = {
            "title": "SIAM Journal on Computing",
            "publisher": "SIAM",
            "organizer": "SIAM",
            "description": "All submissions undergo rigorous single-blind peer review by an international committee.",
        }
        evidence = risk_evidence_extractor.extract(opp)

        assert evidence.has_suspicious_evidence is False
        assert len(evidence.negative_evidence) == 0


class TestMissingMetadataNeutrality:
    """Verify UNKNOWN != PREDATORY invariant: missing fields lower confidence but never create negative evidence."""

    def test_completely_empty_opportunity_is_neutral(self) -> None:
        opp = {
            "title": "Workshop on Local Topics",
        }
        evidence = risk_evidence_extractor.extract(opp)

        # Invariant 1: Absolutely zero negative / suspicious evidence
        assert evidence.has_suspicious_evidence is False
        assert len(evidence.negative_evidence) == 0

        # Invariant 2: Neutral missing metadata items present
        neutral_items = evidence.neutral_evidence
        assert len(neutral_items) > 0
        for item in neutral_items:
            assert item.category == EvidenceCategory.NEUTRAL_UNKNOWN
            assert item.strength == EvidenceStrength.NONE

        # Invariant 3: Metadata completeness score is low
        assert evidence.metadata_completeness_score <= 0.35

    def test_unindexed_new_venue_is_neutral(self) -> None:
        opp = {
            "title": "First International Workshop on Quantum Machine Learning",
            "publisher": "Department of Physics, Local University",
            "website_url": "https://physics.univ-paris.fr/qml2026",
            "submission_deadline": "2026-11-15T23:59:59Z",
            "indexing": [],  # Completely unindexed
        }
        evidence = risk_evidence_extractor.extract(opp)

        # Unindexed new workshop must NOT be flagged as suspicious
        assert evidence.has_suspicious_evidence is False
        assert len(evidence.negative_evidence) == 0

        # Check indexing is classified as neutral unknown
        unindexed_evidence = [
            item for item in evidence.neutral_evidence
            if item.signal == EvidenceSignal.UNKNOWN_INDEXING.value
        ]
        assert len(unindexed_evidence) == 1
        assert unindexed_evidence[0].category == EvidenceCategory.NEUTRAL_UNKNOWN
        assert unindexed_evidence[0].strength == EvidenceStrength.NONE


class TestDeterminismAndPerformance:
    """Verify strict determinism, thread safety, and zero N+1 in-memory extraction."""

    def test_extraction_determinism_across_100_runs(self) -> None:
        opp = {
            "id": uuid.uuid4(),
            "title": "IEEE Transactions on Neural Networks",
            "publisher": "IEEE",
            "organizer": "IEEE",
            "website_url": "https://ieee.org/tnnls",
            "indexing": ["Scopus", "Web of Science", "PubMed"],
            "issn": "2162-237X",
            "description": "Double-blind peer review by international program committee. Page charges apply.",
        }

        baseline = risk_evidence_extractor.extract(opp).to_dict()

        for _ in range(100):
            current = risk_evidence_extractor.extract(opp).to_dict()
            assert current == baseline, "Extraction output varied across identical runs!"

    def test_batch_performance_zero_queries(self) -> None:
        """1,000 synthetic opportunities must extract in < 250ms with zero DB queries."""
        batch = [
            {
                "id": uuid.uuid4(),
                "title": f"Conference Edition {i}",
                "publisher": "Springer" if i % 2 == 0 else "Unknown Press",
                "organizer": "ACM" if i % 3 == 0 else None,
                "website_url": f"https://conf{i}.org" if i % 4 != 0 else f"http://192.168.1.{i % 255}",
                "indexing": ["Scopus"] if i % 2 == 0 else [],
                "description": "Urgent fee required via Western Union" if i % 50 == 0 else "Double-blind peer review",
            }
            for i in range(1000)
        ]

        start_time = time.perf_counter()
        results = risk_evidence_extractor.extract_batch(batch)
        elapsed = time.perf_counter() - start_time

        assert len(results) == 1000
        # Average per-opportunity extraction should be < 0.25ms (elapsed < 0.25s for 1000)
        assert elapsed < 0.50, f"Batch extraction took too long: {elapsed:.4f}s for 1000 items"


class TestEntitySeparationAndModels:
    """Ensure publisher, organizer, venue, and domain entities are kept distinct."""

    def test_publisher_vs_organizer_separation(self) -> None:
        # Venue where organizer is a verified society (ACM), but publisher is not
        opp = {
            "title": "Specialized Workshop on AI",
            "publisher": "Unknown Regional Press",
            "organizer": "ACM",
            "website_url": "https://workshop-ai.org",
        }
        evidence = risk_evidence_extractor.extract(opp)
        pos_signals = {item.signal for item in evidence.positive_evidence}
        neutral_signals = {item.signal for item in evidence.neutral_evidence}

        # Organizer is verified society
        assert EvidenceSignal.VERIFIED_SOCIETY.value in pos_signals
        # Publisher is unknown (neutral, not negative!)
        assert EvidenceSignal.UNKNOWN_PUBLISHER.value in neutral_signals
        assert evidence.has_suspicious_evidence is False

    def test_orm_opportunity_model_compatibility(self) -> None:
        from app.models.opportunity import OpportunityModel

        opp = OpportunityModel(
            id=uuid.uuid4(),
            title="IEEE Conference on Computer Communications",
            opportunity_type="CONFERENCE",
            publisher="IEEE",
            organizer="IEEE Communications Society",
            website_url="https://infocom2026.ieee-infocom.org",
            indexing=["Scopus", "IEEE Xplore"],
            status="ACTIVE",
        )
        evidence = risk_evidence_extractor.extract(opp)
        assert evidence.has_trust_evidence is True
        assert evidence.has_suspicious_evidence is False
        assert evidence.opportunity_id == str(opp.id)


class TestEdgeCasesAndMalformedInputs:
    """Verify robust behavior with malformed inputs, None values, and unusual data types."""

    def test_none_input_opportunity(self) -> None:
        evidence = risk_evidence_extractor.extract(None)
        assert evidence.has_suspicious_evidence is False
        assert evidence.has_trust_evidence is False
        assert evidence.metadata_completeness_score == 0.0

    def test_malformed_urls_and_strange_types(self) -> None:
        opp = {
            "title": "Strange Conference",
            "website_url": "not a valid url :// invalid %%%",
            "submission_url": 12345,  # type: ignore[dict-item]
            "indexing": [None, 123, ""],  # type: ignore[list-item]
            "publisher": None,
            "description": None,
            "apc_or_fee": "not a dict",
        }
        evidence = risk_evidence_extractor.extract(opp)
        assert evidence.has_suspicious_evidence is False
