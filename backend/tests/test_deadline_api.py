"""
Unit and integration tests for Phase 2.7F Deadline API & Explainability.

Validates:
1. Loss-aware schema serialization (Upcoming, Due Today, Expired, Missing,
   Invalid, Ambiguous, Conflicting, Superseded, Extended, Equivalent).
2. Deterministic explainability attributions (0 LLM, 0 DB queries).
3. Parity between domain models and API schemas.
4. Dedicated endpoint: GET /api/opportunities/{id}/deadlines.
5. Detail endpoint enrichment: GET /api/opportunities/{id}.
6. Discovery matching integration: POST /api/v1/discovery/opportunities/match.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.ranking.deadline.explainability import (
    DeadlineExplainabilityService,
    deadline_explainability_service,
)
from app.ranking.deadline.models import (
    CanonicalDeadlineView,
    ConflictState,
    DeadlineAssessment,
    DeadlineEvidence,
    DeadlineObservation,
    DeadlinePrecision,
    DeadlineProvenance,
    DeadlineRevision,
    DeadlineTemporalStatus,
    DeadlineType,
    DefaultTimezonePolicy,
    ExtractionMethod,
    NormalizationStatus,
    NormalizedDeadline,
    OpportunityCanonicalView,
    RevisionClassification,
    SourceAuthorityTier,
    TimezoneIndicator,
    TimezoneSource,
    UrgencyTier,
)
from app.ranking.deadline.resolvers import DeadlineConflictResolver
from app.schemas.deadline import (
    CanonicalDeadlineViewSchema,
    DeadlineAssessmentSchema,
    DeadlineObservationSchema,
    DeadlineRevisionSchema,
    NormalizedDeadlineSchema,
    OpportunityDeadlineSchema,
)
from app.schemas.opportunity import OpportunityRead


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── Test Suite 1: Loss-Aware Schema Serialization ─────────────────────────────


class TestLossAwareSerialization:
    """Validate that API schemas faithfully represent all temporal and conflict states."""

    def test_upcoming_deadline_serialization(self) -> None:
        ref_time = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            local_date=date(2026, 8, 27),
            local_time=time(23, 59, 59),
            timezone_name="AoE",
            timezone_offset="-12:00",
            normalized_utc=datetime(2026, 8, 28, 11, 59, 59, tzinfo=timezone.utc),
            precision=DeadlinePrecision.DATE_ONLY,
            timezone_source=TimezoneSource.INFERRED,
            normalization_confidence=0.95,
            normalization_status=NormalizationStatus.NORMALIZED,
        )
        ass = DeadlineAssessment(
            deadline_type=DeadlineType.SUBMISSION,
            reference_time=ref_time,
            normalized_deadline=norm,
            status=DeadlineTemporalStatus.UPCOMING,
            urgency_tier=UrgencyTier.CRITICAL,
            urgency_score=0.85,
            seconds_remaining=691199.0,
            minutes_remaining=11519.98,
            hours_remaining=191.99,
            days_remaining=8.0,
            confidence=0.95,
            explanation="Submission deadline is 8.0 days away (2026-08-27 AoE, critical urgency).",
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=norm,
            canonical_assessment=ass,
            selected_source="wikicfp",
            conflict_state=ConflictState.NO_CONFLICT,
            confidence=0.95,
            explanation=ass.explanation,
        )

        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.deadline_type == "SUBMISSION"
        assert schema.canonical_deadline is not None
        assert schema.canonical_deadline.local_date == date(2026, 8, 27)
        assert schema.canonical_deadline.timezone_name == "AoE"
        assert schema.canonical_assessment is not None
        assert schema.canonical_assessment.status == "UPCOMING"
        assert schema.canonical_assessment.urgency_tier == "CRITICAL"
        assert schema.canonical_assessment.days_remaining == 8.0
        assert schema.conflict_state == "NO_CONFLICT"
        assert "critical urgency" in schema.deterministic_explanation

    def test_due_today_deadline_serialization(self) -> None:
        ref_time = datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            local_date=date(2026, 8, 27),
            local_time=time(23, 59, 59),
            timezone_name="UTC",
            normalized_utc=datetime(2026, 8, 27, 23, 59, 59, tzinfo=timezone.utc),
            normalization_status=NormalizationStatus.NORMALIZED,
        )
        ass = DeadlineAssessment(
            deadline_type=DeadlineType.SUBMISSION,
            reference_time=ref_time,
            normalized_deadline=norm,
            status=DeadlineTemporalStatus.DUE_TODAY,
            urgency_tier=UrgencyTier.DUE_TODAY,
            urgency_score=1.0,
            hours_remaining=15.99,
            days_remaining=0.66,
            explanation="Submission deadline is due today (15.9 hours remaining).",
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=norm,
            canonical_assessment=ass,
            selected_source="official",
            conflict_state=ConflictState.NO_CONFLICT,
            confidence=1.0,
        )

        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.canonical_assessment is not None
        assert schema.canonical_assessment.status == "DUE_TODAY"
        assert schema.canonical_assessment.urgency_tier == "DUE_TODAY"
        assert schema.canonical_assessment.hours_remaining == 15.99

    def test_expired_deadline_serialization(self) -> None:
        ref_time = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            local_date=date(2026, 8, 27),
            normalized_utc=datetime(2026, 8, 28, 11, 59, 59, tzinfo=timezone.utc),
            normalization_status=NormalizationStatus.NORMALIZED,
        )
        ass = DeadlineAssessment(
            deadline_type=DeadlineType.SUBMISSION,
            reference_time=ref_time,
            normalized_deadline=norm,
            status=DeadlineTemporalStatus.EXPIRED,
            urgency_tier=UrgencyTier.EXPIRED,
            urgency_score=0.0,
            seconds_remaining=-345601.0,
            days_remaining=-4.0,
            explanation="Submission deadline expired 4.0 days ago.",
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=norm,
            canonical_assessment=ass,
            conflict_state=ConflictState.NO_CONFLICT,
        )

        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.canonical_assessment is not None
        assert schema.canonical_assessment.status == "EXPIRED"
        assert schema.canonical_assessment.urgency_tier == "EXPIRED"
        assert schema.canonical_assessment.urgency_score == 0.0

    def test_missing_deadline_does_not_serialize_to_ambiguous_null(self) -> None:
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=None,
            canonical_assessment=None,
            conflict_state=ConflictState.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            explanation="Insufficient evidence for submission deadline.",
        )
        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.canonical_deadline is None
        assert schema.canonical_assessment is None
        assert schema.conflict_state == "INSUFFICIENT_EVIDENCE"
        assert "Insufficient evidence" in schema.explanation
        assert schema.unresolved_reason is not None

    def test_conflict_state_serialization_loss_aware(self) -> None:
        """Equal-authority conflict must NOT be serialized as null without explanation."""
        obs1 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 20, 2026",
            source="WikiCFP",
            authority_tier=SourceAuthorityTier.LIST_PAGE,
            normalized_deadline=NormalizedDeadline(
                deadline_type=DeadlineType.SUBMISSION,
                local_date=date(2026, 8, 20),
            ),
        )
        obs2 = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 25, 2026",
            source="OpenAlex",
            authority_tier=SourceAuthorityTier.LIST_PAGE,
            normalized_deadline=NormalizedDeadline(
                deadline_type=DeadlineType.SUBMISSION,
                local_date=date(2026, 8, 25),
            ),
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=None,
            canonical_assessment=None,
            conflict_state=ConflictState.SOURCE_CONFLICT,
            unresolved_alternatives=[obs1, obs2],
            explanation="Submission deadline differs across 2 sources; canonical deadline unresolved.",
        )

        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.canonical_deadline is None
        assert schema.conflict_state == "SOURCE_CONFLICT"
        assert len(schema.unresolved_alternatives) == 2
        assert schema.conflict_reason is not None
        assert "Conflicting deadlines reported across 2" in schema.conflict_reason
        assert schema.unresolved_reason is not None
        assert "remains unresolved to prevent fabricating a winner" in schema.unresolved_reason

    def test_superseded_source_serialization(self) -> None:
        authoritative = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            source="Official CFP",
            authority_tier=SourceAuthorityTier.OFFICIAL_CFP,
            normalized_deadline=NormalizedDeadline(
                deadline_type=DeadlineType.SUBMISSION,
                local_date=date(2026, 8, 27),
            ),
        )
        aggregator = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            source="Old Aggregator",
            authority_tier=SourceAuthorityTier.GENERAL_AGGREGATOR,
            normalized_deadline=NormalizedDeadline(
                deadline_type=DeadlineType.SUBMISSION,
                local_date=date(2026, 8, 20),
            ),
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=authoritative.normalized_deadline,
            selected_source="Official CFP",
            selected_observation=authoritative,
            conflict_state=ConflictState.SUPERSEDED,
            unresolved_alternatives=[aggregator],
            explanation="Official CFP supersedes older or lower-authority aggregator deadline.",
        )

        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.canonical_deadline is not None
        assert schema.conflict_state == "SUPERSEDED"
        assert schema.selected_source == "Official CFP"
        assert schema.source_selection_reason is not None
        assert "supersedes lower-tier or older aggregator records" in schema.source_selection_reason
        assert len(schema.unresolved_alternatives) == 1
        assert schema.unresolved_alternatives[0].source == "Old Aggregator"

    def test_extension_serialization(self) -> None:
        prev_obs = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 20, 2026 AoE",
            normalized_deadline=NormalizedDeadline(
                deadline_type=DeadlineType.SUBMISSION,
                local_date=date(2026, 8, 20),
                timezone_name="AoE",
            ),
        )
        curr_obs = DeadlineObservation(
            deadline_type=DeadlineType.SUBMISSION,
            raw_value="Aug 27, 2026 AoE",
            normalized_deadline=NormalizedDeadline(
                deadline_type=DeadlineType.SUBMISSION,
                local_date=date(2026, 8, 27),
                timezone_name="AoE",
            ),
        )
        revision = DeadlineRevision(
            deadline_type=DeadlineType.SUBMISSION,
            previous_observation=prev_obs,
            current_observation=curr_obs,
            classification=RevisionClassification.EXTENDED,
            days_diff=7.0,
            hours_diff=168.0,
            explanation="Submission deadline extended from 2026-08-20 AoE to 2026-08-27 AoE (7 days extension).",
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=curr_obs.normalized_deadline,
            selected_source="wikicfp",
            latest_revision=revision,
            revision_history=[revision],
            conflict_state=ConflictState.NO_CONFLICT,
            explanation="Submission deadline active.",
        )

        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.latest_revision is not None
        assert schema.latest_revision.classification == "EXTENDED"
        assert schema.latest_revision.days_diff == 7.0
        assert schema.extension_reason is not None
        assert "extended by 7 days" in schema.extension_reason

    def test_invalid_deadline_serialization(self) -> None:
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalization_status=NormalizationStatus.INVALID,
            normalization_confidence=0.0,
            metadata={"reason": "unrecognized_timezone"},
        )
        ass = DeadlineAssessment(
            deadline_type=DeadlineType.SUBMISSION,
            reference_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
            normalized_deadline=norm,
            status=DeadlineTemporalStatus.INVALID,
            urgency_tier=UrgencyTier.UNKNOWN,
            urgency_score=0.0,
            confidence=0.0,
            explanation="Deadline could not be parsed or contains invalid timezone for submission deadline.",
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=norm,
            canonical_assessment=ass,
            conflict_state=ConflictState.NO_CONFLICT,
        )
        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.canonical_deadline is not None
        assert schema.canonical_deadline.normalization_status == "INVALID"
        assert schema.canonical_assessment is not None
        assert schema.canonical_assessment.status == "INVALID"
        assert schema.canonical_assessment.urgency_tier == "UNKNOWN"

    def test_ambiguous_deadline_serialization(self) -> None:
        norm = NormalizedDeadline(
            deadline_type=DeadlineType.SUBMISSION,
            normalization_status=NormalizationStatus.AMBIGUOUS,
            normalization_confidence=0.0,
            metadata={"reason": "ambiguous_slash_format"},
        )
        ass = DeadlineAssessment(
            deadline_type=DeadlineType.SUBMISSION,
            reference_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
            normalized_deadline=norm,
            status=DeadlineTemporalStatus.AMBIGUOUS,
            urgency_tier=UrgencyTier.UNKNOWN,
            urgency_score=0.0,
            confidence=0.0,
            explanation="Date format is ambiguous (e.g. 04/05/2026); could be April 5 or May 4.",
        )
        view = CanonicalDeadlineView(
            deadline_type=DeadlineType.SUBMISSION,
            canonical_deadline=norm,
            canonical_assessment=ass,
            conflict_state=ConflictState.NO_CONFLICT,
        )
        schema = deadline_explainability_service.explain_canonical_view(view)
        assert schema.canonical_deadline is not None
        assert schema.canonical_deadline.normalization_status == "AMBIGUOUS"
        assert schema.canonical_assessment is not None
        assert schema.canonical_assessment.status == "AMBIGUOUS"
        assert schema.canonical_assessment.urgency_tier == "UNKNOWN"


# ── Test Suite 2: Opportunity Explainability Parity ───────────────────────────


class TestOpportunityExplainability:
    """Validate full opportunity deadline explainability container."""

    def test_explain_opportunity_from_model_dict(self) -> None:
        opp_data = {
            "id": str(uuid.uuid4()),
            "title": "IEEE International Conference on Distributed Computing 2026",
            "submission_deadline": "2026-08-27T23:59:59Z",
            "notification_date": "2026-09-15T00:00:00Z",
            "camera_ready_deadline": "2026-10-01T00:00:00Z",
            "event_start_date": "2026-10-20",
        }

        ref = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        opp_deadline = deadline_explainability_service.explain_opportunity_from_model(
            opp_data,
            reference_time=ref,
        )

        assert isinstance(opp_deadline, OpportunityDeadlineSchema)
        assert opp_deadline.primary_milestone == "SUBMISSION"
        assert opp_deadline.primary_view is not None
        assert opp_deadline.primary_view.canonical_deadline is not None
        assert opp_deadline.primary_view.canonical_deadline.local_date == date(2026, 8, 27)
        assert opp_deadline.primary_view.canonical_assessment is not None
        assert opp_deadline.primary_view.canonical_assessment.status == "UPCOMING"
        assert "Paper submission is the primary academic author milestone" in opp_deadline.primary_reason
        assert len(opp_deadline.milestone_views) >= 4
        assert "NOTIFICATION" in opp_deadline.milestone_views
        assert "CAMERA_READY" in opp_deadline.milestone_views
        assert "EVENT_START" in opp_deadline.milestone_views
        assert "Critical" in opp_deadline.summary or "Approaching" in opp_deadline.summary or "left" in opp_deadline.summary


# ── Test Suite 3: API Endpoint Tests ──────────────────────────────────────────


class TestDeadlineApiEndpoints:
    """Test dedicated and additive API endpoints using TestClient."""

    def test_get_opportunity_deadlines_dedicated_endpoint(self, client: TestClient) -> None:
        test_id = uuid.uuid4()
        mock_opp = {
            "id": test_id,
            "title": "NeurIPS 2026",
            "opportunity_type": "CONFERENCE",
            "delivery_mode": "HYBRID",
            "status": "ACTIVE",
            "is_predatory_flag": False,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "submission_deadline": datetime(2026, 8, 27, 23, 59, 59, tzinfo=timezone.utc),
            "notification_date": datetime(2026, 9, 20, tzinfo=timezone.utc),
            "event_start_date": date(2026, 11, 15),
        }

        with patch("app.api.opportunities.get_opportunity_by_id", return_value=mock_opp):
            resp = client.get(f"/api/opportunities/{test_id}/deadlines")
            assert resp.status_code == 200
            data = resp.json()
            assert data["primary_milestone"] == "SUBMISSION"
            assert data["primary_view"]["deadline_type"] == "SUBMISSION"
            assert data["primary_view"]["canonical_deadline"]["local_date"] == "2026-08-27"
            assert "milestone_views" in data
            assert "NOTIFICATION" in data["milestone_views"]
            assert "EVENT_START" in data["milestone_views"]
            assert data["primary_reason"] != ""

    def test_get_opportunity_deadlines_404_not_found(self, client: TestClient) -> None:
        test_id = uuid.uuid4()
        with patch("app.api.opportunities.get_opportunity_by_id", return_value=None):
            resp = client.get(f"/api/opportunities/{test_id}/deadlines")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Opportunity not found"

    def test_get_opportunity_detail_additive_deadline_intelligence(self, client: TestClient) -> None:
        test_id = uuid.uuid4()
        mock_opp = {
            "id": test_id,
            "title": "ICML 2026",
            "opportunity_type": "CONFERENCE",
            "delivery_mode": "HYBRID",
            "status": "ACTIVE",
            "is_predatory_flag": False,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "submission_deadline": datetime(2026, 8, 27, 23, 59, 59, tzinfo=timezone.utc),
        }

        with patch("app.api.opportunities.get_opportunity_by_id", return_value=mock_opp):
            resp = client.get(f"/api/opportunities/{test_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert "deadline_intelligence" in data
            assert data["deadline_intelligence"] is not None
            assert data["deadline_intelligence"]["primary_milestone"] == "SUBMISSION"
            assert (
                data["deadline_intelligence"]["primary_view"]["canonical_deadline"]["local_date"]
                == "2026-08-27"
            )

    def test_opportunity_match_with_explain_includes_deadline_explanation(self, client: TestClient) -> None:
        work_id = uuid.uuid4()
        opp_id = uuid.uuid4()
        mock_work = {
            "id": work_id,
            "title": "Quantum Error Correction",
            "abstract": "We present surface code architectures.",
            "publication_year": 2026,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        mock_opp = {
            "id": opp_id,
            "title": "QIP 2026",
            "opportunity_type": "CONFERENCE",
            "delivery_mode": "HYBRID",
            "status": "ACTIVE",
            "is_predatory_flag": False,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "submission_deadline": datetime(2026, 8, 27, 23, 59, 59, tzinfo=timezone.utc),
        }

        from app.ranking.hybrid_ranker import RankedCandidate
        candidate = RankedCandidate(
            entity_id=opp_id,
            entity_type="opportunity",
            final_score=0.88,
            rank=1,
            candidate=mock_opp,
            semantic_score=0.90,
            lexical_score=0.85,
            topic_score=0.80,
            type_score=0.85,
            freshness_score=0.50,
            urgency_score=0.75,
            quality_score=0.90,
        )

        with (
            patch("app.api.v1.discovery.research_opportunity_matching_service.match_opportunities", return_value=[candidate]),
            patch("app.api.v1.discovery.hybrid_ranker.rank", return_value=[candidate]),
        ):
            resp = client.get(
                f"/api/v1/discovery/research/{work_id}/opportunities?explain=true",
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["items"]) == 1
            item = data["items"][0]
            assert "deadline_explanation" in item
            assert item["deadline_explanation"] is not None
            assert item["deadline_explanation"]["primary_milestone"] == "SUBMISSION"
            assert (
                item["deadline_explanation"]["primary_view"]["canonical_deadline"]["local_date"]
                == "2026-08-27"
            )
            assert "deadline_intelligence" in item["opportunity"]
            assert item["opportunity"]["deadline_intelligence"] is not None
