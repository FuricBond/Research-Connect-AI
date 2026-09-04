"""
Phase 2.7G — Empirical Evaluation & Hardening Test Suite for Deadline Intelligence.

Verifies:
  1. Dataset quality audit, category distributions, and ground-truth semantics.
  2. Extraction, date parsing, and precision detection accuracy.
  3. Date & Timezone normalization (AoE, standard offsets, IANA zones, DST transitions).
  4. Urgency engine calibration, temporal statuses, and bounded score monotonicity.
  5. Multi-milestone isolation, precedence ordering, and event date separation.
  6. Revision lineage (extensions, moved-earlier, unchanged representations).
  7. Multi-source conflict resolution, authority tiers, and dispute preservation.
  8. Deterministic explainability and complete API/UI parity.
  9. All 20 Critical Architectural Safety Invariants.
  10. Strict 100-run reproducibility and determinism.
  11. Latency and scalability across N=10 to N=1,000 candidates with zero DB queries.
  12. Real-world scraped WikiCFP HTML fixture validation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import pytest

from app.evaluation.deadline_dataset import (
    DeadlineEvaluationCategory,
    DeadlineEvaluationDataset,
    deadline_evaluation_dataset,
)
from app.evaluation.deadline_runner import (
    DeadlineBenchmarkRunner,
    DeadlineEvaluationReport,
    deadline_benchmark_runner,
)
from app.ranking.deadline.extractors import DeadlineEvidenceExtractor
from app.ranking.deadline.models import (
    ConflictState,
    DeadlineAssessment,
    DeadlineObservation,
    DeadlineTemporalStatus,
    DeadlineType,
    NormalizationStatus,
    NormalizedDeadline,
    RevisionClassification,
    SourceAuthorityTier,
    TimezoneSource,
    UrgencyTier,
)
from app.ranking.deadline.normalizers import DeadlineNormalizer
from app.ranking.deadline.resolvers import DeadlineConflictResolver


@pytest.fixture(scope="module")
def runner() -> DeadlineBenchmarkRunner:
    return deadline_benchmark_runner


@pytest.fixture(scope="module")
def full_report(runner: DeadlineBenchmarkRunner) -> DeadlineEvaluationReport:
    return runner.run_full_evaluation()


# ── 1. Dataset Quality & Semantics Tests ───────────────────────────────────────


class TestDatasetQualityAndSemantics:
    """Verifies structure and labeling integrity of the Phase 2.7G dataset."""

    def test_dataset_size_and_composition(self, runner: DeadlineBenchmarkRunner):
        summary = runner.dataset.summary()
        assert summary["total_fixtures"] >= 30
        assert summary["category_distribution"][DeadlineEvaluationCategory.BASIC_DATES.value] >= 5
        assert summary["category_distribution"][DeadlineEvaluationCategory.ACADEMIC_CONVENTIONS.value] >= 5
        assert summary["category_distribution"][DeadlineEvaluationCategory.TIMEZONE_DST.value] >= 5
        assert summary["category_distribution"][DeadlineEvaluationCategory.INVALID_AMBIGUOUS.value] >= 5
        assert summary["category_distribution"][DeadlineEvaluationCategory.MULTI_MILESTONE.value] >= 3
        assert summary["category_distribution"][DeadlineEvaluationCategory.REVISIONS.value] >= 3
        assert summary["category_distribution"][DeadlineEvaluationCategory.SOURCE_CONFLICTS.value] >= 3
        assert summary["category_distribution"][DeadlineEvaluationCategory.SAFETY_INVARIANTS.value] >= 3

    def test_fixture_fields_integrity(self, runner: DeadlineBenchmarkRunner):
        for f in runner.dataset.fixtures:
            assert f.fixture_id
            assert f.description
            assert isinstance(f.category, DeadlineEvaluationCategory)
            assert isinstance(f.expected_deadline_type, DeadlineType)


# ── 2. Extraction & Normalization Tests ────────────────────────────────────────


class TestExtractionAndNormalization:
    """Verifies extraction and date/timezone normalization accuracy."""

    def test_extraction_metrics(self, full_report: DeadlineEvaluationReport):
        ext = full_report.extraction
        assert ext["deadline_type_accuracy"] == 1.00
        assert ext["presence_detection_accuracy"] == 1.00
        assert ext["precision_accuracy"] == 1.00
        assert ext["provenance_accuracy"] == 1.00

    def test_normalization_and_aoe_metrics(self, full_report: DeadlineEvaluationReport):
        norm = full_report.normalization
        assert norm["aoe_conversion_accuracy"] == 1.00
        assert norm["invalid_timezone_safety_rate"] == 1.00
        assert norm["ambiguous_date_safety_rate"] == 1.00
        assert norm["non_date_placeholder_safety_rate"] == 1.00

    def test_timezone_and_dst_metrics(self, full_report: DeadlineEvaluationReport):
        tz = full_report.timezone
        assert tz["iana_timezone_accuracy"] == 1.00
        assert tz["dst_transition_accuracy"] == 1.00
        assert tz["fractional_offset_accuracy"] == 1.00
        assert tz["negative_offset_accuracy"] == 1.00


# ── 3. Intelligence & Urgency Calibration Tests ───────────────────────────────


class TestIntelligenceAndUrgency:
    """Verifies temporal status and urgency calibration."""

    def test_temporal_status_and_tier_accuracy(self, full_report: DeadlineEvaluationReport):
        intel = full_report.intelligence
        assert intel["temporal_status_accuracy"] == 1.00
        assert intel["urgency_tier_accuracy"] == 1.00
        assert intel["score_bounds_adherence"] == 1.00
        assert intel["due_today_detection_accuracy"] == 1.00
        assert intel["expired_accuracy"] == 1.00


# ── 4. Multi-Milestone & Separation Tests ──────────────────────────────────────


class TestMultiMilestoneAndSeparation:
    """Verifies milestone isolation, precedence, and event date separation."""

    def test_multi_milestone_metrics(self, full_report: DeadlineEvaluationReport):
        mile = full_report.multi_milestone
        assert mile["primary_milestone_precedence_accuracy"] == 1.00
        assert mile["milestone_isolation_accuracy"] == 1.00
        assert mile["event_start_separation_rate"] == 1.00
        assert mile["notification_camera_ready_separation_rate"] == 1.00


# ── 5. Revisions & Source Conflicts Tests ─────────────────────────────────────


class TestRevisionsAndConflicts:
    """Verifies revision lineage, conflict detection, and source precedence."""

    def test_revision_classification(self, full_report: DeadlineEvaluationReport):
        rev = full_report.revision_detection
        assert rev["revision_classification_accuracy"] == 1.00
        assert rev["extension_detection_rate"] == 1.00
        assert rev["moved_earlier_detection_rate"] == 1.00
        assert rev["equivalent_detection_rate"] == 1.00

    def test_conflict_resolution_and_precedence(self, full_report: DeadlineEvaluationReport):
        conf = full_report.conflict_resolution
        prec = full_report.source_precedence
        assert conf["conflict_state_accuracy"] == 1.00
        assert conf["equal_authority_dispute_preservation"] == 1.00
        assert prec["authority_supersession_accuracy"] == 1.00
        assert prec["official_cfp_dominance"] == 1.00


# ── 6. Explainability & Parity Tests ──────────────────────────────────────────


class TestExplainabilityAndParity:
    """Verifies explainability determinism and API/UI parity."""

    def test_explainability_metrics(self, full_report: DeadlineEvaluationReport):
        exp = full_report.explainability
        assert exp["deterministic_synthesis_rate"] == 1.00
        assert exp["zero_llm_runtime_calls_verified"] is True
        assert exp["extension_narrative_truthfulness"] == 1.00
        assert exp["conflict_narrative_truthfulness"] == 1.00
        assert exp["countdown_narrative_accuracy"] == 1.00

    def test_api_and_frontend_parity(self, full_report: DeadlineEvaluationReport):
        api = full_report.api_parity
        ui = full_report.frontend_parity
        assert api["schema_lossless_serialization_rate"] == 1.00
        assert api["zero_null_ambiguity_rate"] == 1.00
        assert api["milestone_dictionary_roundtrip_integrity"] == 1.00
        assert ui["zero_client_side_urgency_math_verified"] is True
        assert ui["zero_client_side_timezone_conversion_verified"] is True
        assert ui["semantic_status_parity"] == 1.00


# ── 7. All 20 Safety Invariants Tests ─────────────────────────────────────────


class TestAllTwentySafetyInvariants:
    """Explicitly validates each of the 20 required architectural safety invariants."""

    def test_all_invariants_pass_in_report(self, full_report: DeadlineEvaluationReport):
        safety = full_report.safety_invariants
        assert safety["all_invariants_passed"] is True
        assert safety["passed_invariants"] == 20
        assert safety["total_invariants"] == 20

    def test_invariant_01_missing_not_expired(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_01_missing_not_expired"] is True

    def test_invariant_02_unknown_tz_not_utc(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_02_unknown_tz_not_utc"] is True

    def test_invariant_03_ambiguous_date_not_fabricated(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_03_ambiguous_date_not_fabricated"] is True

    def test_invariant_04_invalid_tz_no_silent_fallback(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_04_invalid_tz_no_silent_fallback"] is True

    def test_invariant_05_date_only_submission_uses_aoe(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_05_date_only_submission_uses_aoe"] is True

    def test_invariant_06_non_submission_date_only_not_aoe(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_06_non_submission_date_only_not_aoe"] is True

    def test_invariant_07_event_dates_never_substituted(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_07_event_dates_never_substituted"] is True

    def test_invariant_08_to_10_milestone_separation(self, full_report: DeadlineEvaluationReport):
        inv = full_report.safety_invariants["details"]
        assert inv["invariant_08_notification_not_submission"] is True
        assert inv["invariant_09_camera_ready_not_submission"] is True
        assert inv["invariant_10_registration_not_submission"] is True

    def test_invariant_11_extension_is_revision_not_new_milestone(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_11_extension_is_revision_not_new_milestone"] is True

    def test_invariant_12_missing_observation_not_retraction(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_12_missing_observation_not_retraction"] is True

    def test_invariant_13_equal_authority_conflict_preserved(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_13_equal_authority_conflict_preserved"] is True

    def test_invariant_14_higher_authority_supersedes(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_14_higher_authority_supersedes"] is True

    def test_invariant_15_to_17_orthogonality(self, full_report: DeadlineEvaluationReport):
        inv = full_report.safety_invariants["details"]
        assert inv["invariant_15_risk_does_not_influence_urgency"] is True
        assert inv["invariant_16_urgency_does_not_influence_risk"] is True
        assert inv["invariant_17_urgency_respects_relevance_dominance"] is True

    def test_invariant_18_frontend_is_presentation_only(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_18_frontend_is_presentation_only"] is True

    def test_invariant_19_strict_determinism(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_19_strict_determinism"] is True

    def test_invariant_20_backward_compatibility_preserved(self, full_report: DeadlineEvaluationReport):
        assert full_report.safety_invariants["details"]["invariant_20_backward_compatibility_preserved"] is True


# ── 8. Determinism & Performance Tests ────────────────────────────────────────


class TestDeterminismAndPerformance:
    """Verifies 100-run strict determinism and latency benchmarks."""

    def test_100_runs_identical(self, full_report: DeadlineEvaluationReport):
        det = full_report.determinism
        assert det["total_runs"] == 100
        assert det["identical_runs"] == 100
        assert det["determinism_percentage"] == 100.0
        assert det["is_fully_deterministic"] is True

    def test_performance_scalability_under_budget(self, full_report: DeadlineEvaluationReport):
        perf = full_report.performance
        for n_str in ["N=10", "N=50", "N=100", "N=200", "N=1000"]:
            entry = perf[n_str]
            # Average per-candidate processing latency must be < 2.0 ms
            assert entry["avg_per_candidate_ms"] < 2.0
            # P95 must be < 5.0 ms
            assert entry["p95_latency_ms"] < 5.0

    def test_database_and_network_safety(self, full_report: DeadlineEvaluationReport):
        db = full_report.database_safety
        assert db["runtime_db_queries_per_candidate"] == 0
        assert db["runtime_network_requests"] == 0
        assert db["n_plus_one_vulnerabilities"] == 0
        assert db["in_memory_evaluation_verified"] is True


# ── 9. Real-World WikiCFP Fixtures Tests ──────────────────────────────────────


class TestRealWorldWikiCFPFixtures:
    """Verifies extraction and resolution on repository HTML fixtures."""

    def test_wikicfp_fixtures_evaluated(self, full_report: DeadlineEvaluationReport):
        rw = full_report.real_world_fixture_validation
        assert rw["wikicfp_detail_fixture_found"] is True
        assert rw["wikicfp_list_fixture_found"] is True
        assert rw["detail_milestones_extracted"] == 4
        assert rw["list_entries_extracted"] >= 5
        assert rw["real_world_aoe_verified"] is True
        assert rw["real_world_multi_milestone_verified"] is True
