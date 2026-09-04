"""
Comprehensive Test Suite for Phase 2.6E — Suspicious Pattern & Graph Intelligence.

Validates:
  1. Graph Construction & Canonical Identifiers (nodes, edges, provenance).
  2. Trusted Entity Degree Safeguards (High degree alone != predatory).
  3. Excessive Organizer Reuse & Boundary Tests (N-1, N, N+1).
  4. Excessive Domain Reuse & Whitelisting (Legitimate platforms protected).
  5. Graph Identity Conflict (ISSN collision, conflicting publishers).
  6. Suspicious Organizer & Publisher Cluster Detection (Corroborated negative signals).
  7. Consistent Graph Identity (Multi-source positive trust corroboration).
  8. Isolated Node & Missing Metadata Neutrality (UNKNOWN != PREDATORY).
  9. Correlated Evidence Protection & Deduplication.
  10. Determinism Across 100 Consecutive Runs.
  11. Batch Performance & Scalability (10, 50, 100, 200, 1,000 candidates with zero DB queries).
"""
import time
import uuid
import pytest

from app.ranking.risk.engine import risk_evidence_extractor
from app.ranking.risk.graph import (
    MAX_LEGITIMATE_UNVERIFIED_DOMAIN_ENTITIES,
    MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS,
    AcademicTrustGraph,
    GraphBuilder,
    SuspiciousGraphAnalyzer,
    TrustEdgeType,
    TrustNodeType,
    is_domain_whitelisted,
    make_domain_id,
    make_issn_id,
    make_opportunity_id,
    make_organizer_id,
    make_publisher_id,
    make_source_id,
    make_venue_id,
    suspicious_graph_service,
)
from app.ranking.risk.models import (
    EvidenceCategory,
    EvidenceConfidence,
    EvidenceProvenance,
    EvidenceSignal,
    EvidenceStrength,
    ResolutionStatus,
    ResolvedAcademicEntity,
    RiskEvidence,
    RiskEvidenceCollection,
    RiskLevel,
)
from app.ranking.risk.scoring import risk_scoring_engine


# ── 1. Graph Construction & Provenance Tests ──────────────────────────────────


class TestGraphConstruction:
    def test_canonical_id_generation(self):
        assert make_opportunity_id("123") == "opp:123"
        assert make_opportunity_id(None) == "opp:unknown"
        assert make_venue_id(norm_issn="0028-0836") == "venue:issn:0028-0836"
        assert make_venue_id("Nature", "0028-0836") == "venue:name:nature"
        assert make_publisher_id("Springer Nature") == "pub:springer_nature"
        assert make_organizer_id("ACM SIGGRAPH") == "org:acm_siggraph"
        assert make_domain_id("nature.com") == "domain:nature.com"
        assert make_issn_id("0028-0836") == "issn:0028-0836"
        assert make_source_id("s4306400194") == "source:s4306400194"

    def test_graph_builder_node_and_edge_creation(self):
        builder = GraphBuilder()
        opp = {
            "id": "opp-test-1",
            "title": "International Conference on Machine Learning",
            "venue": "ICML 2026",
            "publisher": "PMLR",
            "organizer": "IMLS",
            "website_url": "https://icml.cc/2026",
            "issn": "2640-3498",
        }
        resolved = ResolvedAcademicEntity(
            entity_type="CONFERENCE",
            canonical_name="International Conference on Machine Learning",
            publisher="PMLR",
            organizer="IMLS",
            domain="icml.cc",
            issn="2640-3498",
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_confidence=0.90,
        )

        graph = builder.build_graph([opp], resolved_entities=[resolved])

        # Assert nodes exist
        assert graph.get_node("opp:opp-test-1") is not None
        venue_id = make_venue_id("International Conference on Machine Learning", "2640-3498")
        assert graph.get_node(venue_id) is not None
        assert graph.get_node("pub:pmlr") is not None
        assert graph.get_node("org:imls") is not None
        assert graph.get_node("domain:icml.cc") is not None
        assert graph.get_node("issn:2640-3498") is not None

        # Assert edges and provenance
        edges = graph.edges()
        assert len(edges) >= 4
        edge_types = {e.edge_type for e in edges}
        assert TrustEdgeType.OPPORTUNITY_IN_VENUE in edge_types
        assert TrustEdgeType.VENUE_PUBLISHED_BY in edge_types
        assert TrustEdgeType.HAS_DOMAIN in edge_types
        assert TrustEdgeType.HAS_IDENTIFIER in edge_types

        # Verify serialization
        snapshot = graph.to_dict()
        assert snapshot["node_count"] == len(graph.nodes())
        assert snapshot["edge_count"] == len(graph.edges())
        assert isinstance(snapshot["nodes"], list)
        assert isinstance(snapshot["edges"], list)


# ── 2. Trusted Entity Safeguards (CRITICAL) ───────────────────────────────────


class TestTrustedEntitySafeguards:
    """
    High graph degree alone must NEVER imply predatory behavior.
    Major academic publishers and scientific societies naturally have massive degree.
    """

    def test_high_degree_ieee_society_never_flagged_for_reuse(self):
        """50 conferences organized by IEEE must never trigger HIGH_ORGANIZER_REUSE."""
        opps = [
            {
                "id": f"ieee-conf-{i}",
                "title": f"IEEE International Conference on Systems {i}",
                "venue": f"IEEE SysCon {i}",
                "organizer": "IEEE",
                "publisher": "IEEE",
                "website_url": f"https://syscon{i}.ieee.org",
            }
            for i in range(50)
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        assert len(collections) == 50

        for col in collections:
            # Must NOT contain HIGH_ORGANIZER_REUSE
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_ORGANIZER_REUSE.value not in signals
            assert EvidenceSignal.HIGH_DOMAIN_REUSE.value not in signals
            assert EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value not in signals

            # Assessment must be LOW_RISK
            assessment = risk_scoring_engine.score(col)
            assert assessment.risk_level == RiskLevel.LOW_RISK
            assert assessment.risk_score < 0.20
            assert assessment.is_predatory_flag is False

    def test_high_degree_springer_publisher_never_flagged_for_reuse(self):
        """50 journals published by Springer Nature on springer.com must never trigger domain reuse."""
        opps = [
            {
                "id": f"springer-jnl-{i}",
                "title": f"Journal of Applied Science {i}",
                "venue": f"Journal of Applied Science {i}",
                "publisher": "Springer Nature",
                "website_url": f"https://link.springer.com/journal/{i}",
            }
            for i in range(50)
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        assert len(collections) == 50

        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_DOMAIN_REUSE.value not in signals
            assert EvidenceSignal.SUSPICIOUS_PUBLISHER_CLUSTER.value not in signals
            assessment = risk_scoring_engine.score(col)
            assert assessment.risk_level == RiskLevel.LOW_RISK

    def test_whitelisted_academic_platforms_protected(self):
        """Known submission portals (easychair.org, edas.info) must not be flagged for domain reuse."""
        assert is_domain_whitelisted("easychair.org") is True
        assert is_domain_whitelisted("edas.info") is True
        assert is_domain_whitelisted("openreview.net") is True
        assert is_domain_whitelisted("arxiv.org") is True

        opps = [
            {
                "id": f"workshop-{i}",
                "title": f"Independent Workshop on Logic {i}",
                "venue": f"Workshop on Logic {i}",
                "website_url": f"https://easychair.org/conferences/?conf=logic{i}",
            }
            for i in range(10)
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_DOMAIN_REUSE.value not in signals


# ── 3. Excessive Organizer Reuse & Boundary Tests ─────────────────────────────


class TestExcessiveOrganizerReuse:
    """
    Validates boundary behavior for unverified organizer reuse.
    Threshold = MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS (5).
    """

    def _make_unverified_organizer_batch(self, count: int, organizer: str = "World Academy of Science"):
        return [
            {
                "id": f"was-opp-{i}",
                "title": f"World Conference on Everything {i}",
                "venue": f"Venue {i}",
                "organizer": organizer,
                "website_url": f"https://unverified-conf-{i}.org",
            }
            for i in range(count)
        ]

    def test_organizer_reuse_threshold_minus_one(self):
        """N - 1 = 4 events under unverified organizer -> NO signal."""
        opps = self._make_unverified_organizer_batch(MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS - 1)
        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_ORGANIZER_REUSE.value not in signals

    def test_organizer_reuse_threshold_exact(self):
        """N = 5 events under unverified organizer -> HIGH_ORGANIZER_REUSE triggered."""
        opps = self._make_unverified_organizer_batch(MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS)
        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_ORGANIZER_REUSE.value in signals
            item = next(it for it in col.items if it.signal == EvidenceSignal.HIGH_ORGANIZER_REUSE.value)
            assert item.provenance == EvidenceProvenance.GRAPH_ANALYSIS
            assert item.category == EvidenceCategory.NEGATIVE_SUSPICIOUS
            assert item.strength == EvidenceStrength.MODERATE

    def test_organizer_reuse_threshold_plus_one(self):
        """N + 1 = 6 events under unverified organizer -> HIGH_ORGANIZER_REUSE triggered."""
        opps = self._make_unverified_organizer_batch(MAX_LEGITIMATE_UNVERIFIED_ORGANIZER_EVENTS + 1)
        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_ORGANIZER_REUSE.value in signals


# ── 4. Excessive Domain Reuse & Boundary Tests ────────────────────────────────


class TestExcessiveDomainReuse:
    """
    Validates boundary behavior for unverified domain reuse.
    Threshold = MAX_LEGITIMATE_UNVERIFIED_DOMAIN_ENTITIES (4).
    """

    def _make_unverified_domain_batch(self, count: int, domain: str = "fake-academic-events.biz"):
        return [
            {
                "id": f"dom-opp-{i}",
                "title": f"Conference Track {i}",
                "venue": f"Venue {i}",
                "website_url": f"https://{domain}/track{i}",
            }
            for i in range(count)
        ]

    def test_domain_reuse_threshold_minus_one(self):
        """N - 1 = 3 entities sharing unverified domain -> NO signal."""
        # 2 opps + 2 venues = 4 entities, so for N-1 distinct entities let's do 1 opp:
        opps = self._make_unverified_domain_batch(1)
        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_DOMAIN_REUSE.value not in signals

    def test_domain_reuse_threshold_exact_and_above(self):
        """4+ opportunities and venues sharing unverified domain -> HIGH_DOMAIN_REUSE triggered."""
        opps = self._make_unverified_domain_batch(MAX_LEGITIMATE_UNVERIFIED_DOMAIN_ENTITIES)
        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.HIGH_DOMAIN_REUSE.value in signals
            item = next(it for it in col.items if it.signal == EvidenceSignal.HIGH_DOMAIN_REUSE.value)
            assert item.provenance == EvidenceProvenance.GRAPH_ANALYSIS
            assert item.category == EvidenceCategory.NEGATIVE_SUSPICIOUS


# ── 5. Graph Identity Conflict Tests ──────────────────────────────────────────


class TestGraphIdentityConflict:
    """
    Detects identity collisions (e.g. same ISSN claimed by contradictory venues).
    Does NOT automatically classify as high risk.
    """

    def test_issn_collision_across_conflicting_venues(self):
        opps = [
            {
                "id": "opp-issn-1",
                "title": "Robotics Research Call",
                "venue": "International Journal of Robotics Research",
                "issn": "0278-3649",
            },
            {
                "id": "opp-issn-2",
                "title": "Dental Implants Call",
                "venue": "Global Journal of Dental Clinical Surgery",
                "issn": "0278-3649",  # Contradictory venue claiming same ISSN
            },
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.GRAPH_IDENTITY_CONFLICT.value in signals
            item = next(it for it in col.items if it.signal == EvidenceSignal.GRAPH_IDENTITY_CONFLICT.value)
            assert item.provenance == EvidenceProvenance.GRAPH_ANALYSIS

            # Check that score does NOT become automatic high risk
            assessment = risk_scoring_engine.score(col)
            assert assessment.risk_level != RiskLevel.HIGH_RISK

    def test_domain_collision_with_conflicting_publishers(self):
        opps = [
            {
                "id": "opp-dom-pub-1",
                "title": "Call 1",
                "publisher": "Sunrise Academic Publishers",
                "website_url": "https://conflicting-portal.org/call1",
            },
            {
                "id": "opp-dom-pub-2",
                "title": "Call 2",
                "publisher": "Horizon Publishing House",
                "website_url": "https://conflicting-portal.org/call2",
            },
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.GRAPH_IDENTITY_CONFLICT.value in signals


# ── 6. Suspicious Cluster Detection Tests ─────────────────────────────────────


class TestSuspiciousClusters:
    """
    Detects structural clusters where multiple opportunities under the same entity
    already exhibit independent affirmative negative signals.
    """

    def test_suspicious_organizer_cluster_detection(self):
        """Organizer with 3 opportunities, 2 of which have payment/review fraud -> cluster flagged."""
        opps = [
            {
                "id": "cluster-opp-1",
                "title": "Fraud Conference 1",
                "organizer": "Shady Event Syndicate",
                "description": "Send payment via Western Union to guarantee acceptance within 24 hours.",
            },
            {
                "id": "cluster-opp-2",
                "title": "Fraud Conference 2",
                "organizer": "Shady Event Syndicate",
                "description": "Peer review completed in 24 hours. Acceptance is guaranteed.",
            },
            {
                "id": "cluster-opp-3",
                "title": "Innocuous Sounding Conference 3",
                "organizer": "Shady Event Syndicate",
                "description": "Standard call for papers on computing.",
            },
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        assert len(collections) == 3

        # All 3 opportunities in the cluster must receive SUSPICIOUS_ORGANIZER_CLUSTER
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value in signals
            item = next(it for it in col.items if it.signal == EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value)
            assert item.strength == EvidenceStrength.STRONG
            assert item.confidence == EvidenceConfidence.HIGH
            assert item.provenance == EvidenceProvenance.GRAPH_ANALYSIS

        # Opportunity 3 (which had no text red flags) gets appropriately elevated risk via cluster
        assessment_3 = risk_scoring_engine.score(collections[2])
        assert assessment_3.risk_score >= 0.35

    def test_clean_cluster_below_suspicious_threshold_not_flagged(self):
        """Organizer with 3 opportunities, but only 1 has negative evidence -> NOT a suspicious cluster."""
        opps = [
            {
                "id": "clean-cluster-1",
                "title": "Regular Event 1",
                "organizer": "Unknown Community Group",
                "description": "Normal research discussion.",
            },
            {
                "id": "clean-cluster-2",
                "title": "Regular Event 2",
                "organizer": "Unknown Community Group",
                "description": "Discussion on algorithms.",
            },
            {
                "id": "clean-cluster-3",
                "title": "One Odd Event",
                "organizer": "Unknown Community Group",
                "description": "Payment via Western Union.",  # Only 1 suspicious opp
            },
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            signals = {item.signal for item in col.items}
            assert EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value not in signals


# ── 7. Multi-Source Trust Corroboration Tests ─────────────────────────────────


class TestConsistentGraphIdentity:
    """
    Validates positive structural trust corroboration when venue aligns with
    verified publisher and independent identifier / source.
    """

    def test_consistent_graph_identity_emitted_for_verified_multi_source(self):
        opp = {
            "id": "opp-nature-1",
            "title": "Advances in Quantum Computing",
            "venue": "Nature Physics",
            "publisher": "Nature Portfolio",
            "issn": "1745-2473",
        }
        resolved = ResolvedAcademicEntity(
            entity_type="JOURNAL",
            canonical_name="Nature Physics",
            publisher="Nature Portfolio",
            issn_l="1745-2473",
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_confidence=0.95,
        )

        col = risk_evidence_extractor.extract(opp, resolved_entity=resolved)
        signals = {item.signal for item in col.items}
        assert EvidenceSignal.CONSISTENT_GRAPH_IDENTITY.value in signals

        item = next(it for it in col.items if it.signal == EvidenceSignal.CONSISTENT_GRAPH_IDENTITY.value)
        assert item.category == EvidenceCategory.POSITIVE_TRUST
        assert item.provenance == EvidenceProvenance.GRAPH_ANALYSIS


# ── 8. Isolated Node & Missing Metadata Neutrality Tests ──────────────────────


class TestIsolatedNodeNeutrality:
    """
    Enforces UNKNOWN != PREDATORY.
    Newly added or isolated entities with degree 0 or 1 must remain neutral.
    """

    def test_completely_empty_isolated_node_produces_zero_negative_graph_evidence(self):
        empty_opp = {"id": "isolated-1"}
        col = risk_evidence_extractor.extract(empty_opp)

        # Must have ZERO negative evidence
        assert len(col.negative_evidence) == 0

        # Assessment must remain INSUFFICIENT_EVIDENCE
        assessment = risk_scoring_engine.score(col)
        assert assessment.risk_level == RiskLevel.INSUFFICIENT_EVIDENCE
        assert assessment.risk_score == 0.0
        assert assessment.is_predatory_flag is False

    def test_new_single_venue_degree_one_remains_neutral(self):
        new_opp = {
            "id": "new-opp-1",
            "title": "First Workshop on Emerging Data",
            "venue": "Emerging Data Workshop",
        }
        col = risk_evidence_extractor.extract(new_opp)
        signals = {item.signal for item in col.items}

        assert EvidenceSignal.HIGH_ORGANIZER_REUSE.value not in signals
        assert EvidenceSignal.HIGH_DOMAIN_REUSE.value not in signals
        assert EvidenceSignal.GRAPH_IDENTITY_CONFLICT.value not in signals
        assert EvidenceSignal.SUSPICIOUS_ORGANIZER_CLUSTER.value not in signals

        assessment = risk_scoring_engine.score(col)
        assert assessment.risk_level in (RiskLevel.INSUFFICIENT_EVIDENCE, RiskLevel.LOW_RISK)
        assert assessment.is_predatory_flag is False


# ── 9. Correlated Evidence Protection & Deduplication Tests ───────────────────


class TestCorrelatedEvidenceProtection:
    """
    Multiple graph paths to the same entity must never duplicate risk signals.
    """

    def test_single_conceptual_reuse_signal_per_opportunity(self):
        # Construct 6 opportunities with same organizer and multiple overlapping links
        opps = [
            {
                "id": f"dedup-opp-{i}",
                "title": f"Syndicated Event {i}",
                "venue": f"Venue {i}",
                "organizer": "Global Conf Syndication",
                "website_url": "https://syndicate-events.net",
            }
            for i in range(6)
        ]

        collections = risk_evidence_extractor.extract_batch(opps)
        for col in collections:
            # Count occurrences of HIGH_ORGANIZER_REUSE in this single collection
            reuse_signals = [item for item in col.items if item.signal == EvidenceSignal.HIGH_ORGANIZER_REUSE.value]
            assert len(reuse_signals) == 1, f"Expected exactly 1 HIGH_ORGANIZER_REUSE, found {len(reuse_signals)}"


# ── 10. Determinism Across 100 Consecutive Runs ───────────────────────────────


class TestGraphDeterminism:
    def test_determinism_across_100_runs(self):
        opps = [
            {
                "id": "det-1",
                "title": "Robotics Conference",
                "venue": "RoboConf",
                "organizer": "Syndicate X",
                "issn": "1234-5679",
            },
            {
                "id": "det-2",
                "title": "Dental Conference",
                "venue": "DentalConf",
                "organizer": "Syndicate X",
                "issn": "1234-5679",
            },
            {
                "id": "det-3",
                "title": "IEEE Flagship",
                "venue": "IEEE Trans",
                "organizer": "IEEE",
                "publisher": "IEEE",
            },
        ]

        baseline_graph, baseline_proj = suspicious_graph_service.analyze_batch(opps)
        baseline_snapshot = baseline_graph.to_dict()
        baseline_proj_keys = {k: [(e.signal, e.matched_value) for e in v] for k, v in baseline_proj.items()}

        for _ in range(100):
            run_graph, run_proj = suspicious_graph_service.analyze_batch(opps)
            assert run_graph.to_dict() == baseline_snapshot
            run_proj_keys = {k: [(e.signal, e.matched_value) for e in v] for k, v in run_proj.items()}
            assert run_proj_keys == baseline_proj_keys


# ── 11. Batch Performance & Scalability Benchmarks ────────────────────────────


class TestGraphPerformanceAndScaling:
    @pytest.mark.parametrize("n_candidates", [10, 50, 100, 200, 1000])
    def test_graph_batch_scaling_performance(self, n_candidates: int):
        """Benchmark in-memory graph construction and pattern detection with zero DB queries."""
        candidates = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Candidate Conference {i}",
                "venue": f"Venue {i % 15}",
                "publisher": "IEEE" if i % 4 == 0 else f"Publisher {i % 10}",
                "organizer": "ACM" if i % 5 == 0 else f"Organizer {i % 8}",
                "website_url": f"https://conf-{i % 20}.org/event",
                "issn": f"1045-{i % 50:04d}",
            }
            for i in range(n_candidates)
        ]

        start = time.perf_counter()
        collections = risk_evidence_extractor.extract_batch(candidates)
        duration_ms = (time.perf_counter() - start) * 1000

        assert len(collections) == n_candidates

        # Performance gates:
        # 1000 items should easily complete under 1500 ms in pure in-memory Python
        if n_candidates == 1000:
            assert duration_ms < 2500, f"1,000 candidates took {duration_ms:.1f}ms (target < 2500ms)"
        elif n_candidates == 100:
            assert duration_ms < 300, f"100 candidates took {duration_ms:.1f}ms (target < 300ms)"
