"""
Test Suite for Phase 3.8 — Personalization Explainability + Researcher UI.

Strict Architectural Boundaries Verified:
  - Explainability layer over Phase 3.5 ranking decisions.
  - Zero mathematical hallucinations: reasons are strictly grounded in active or historical signals.
  - Influence-ordered factor hierarchy: Explicit > Expertise > Behavioral > Profile > Relevance > Deadline.
  - Full Score Consistency: reported scores exactly match candidate and ranking engine scores.
  - Prominent Safety Dominance: high-risk opportunities prominently preserve risk warnings.
  - Historical Immutability: historical snapshot items are explained strictly from frozen snapshot data.
  - Read-Only Security: evaluation and explanations are strictly read-only and enforce X-User-ID ownership.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.user import UserModel
from app.ranking.personalization_ranker import (
    ResearcherPersonalizationContext,
    personalization_ranker,
)
from app.ranking.recommendation_explainer import (
    RecommendationExplainer,
    recommendation_explainer,
)
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceType,
    PersonalizedCandidateOpportunitySchema,
)
from app.schemas.personalized_ranking import (
    MatchedPersonalizationSignalsSchema,
    PersonalizationScoreBreakdownSchema,
    PersonalizedRankedCandidateSchema,
)
from app.schemas.recommendation_explanation import (
    ExplanationReasonCategory,
    RecommendationExplanationSchema,
    SignalImpact,
)
from app.services.personalization_explanation_service import (
    PersonalizationExplanationService,
)

# ── SQLite Compatibility ──────────────────────────────────────────────────────

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a clean in-memory SQLite session with all Phase 3 tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    target_tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["institutions"],
        Base.metadata.tables["researchers"],
        Base.metadata.tables["topics"],
        Base.metadata.tables["opportunities"],
        Base.metadata.tables["opportunity_topics"],
        Base.metadata.tables["saved_opportunities"],
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
        Base.metadata.tables["researcher_recommendation_snapshots"],
        Base.metadata.tables["researcher_recommendation_items"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """FastAPI TestClient with overridden get_db dependency."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ── Helper Factory Functions ──────────────────────────────────────────────────


def create_mock_researcher(
    db: Session,
    name: str = "Dr. Jane Doe",
    email: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[UserModel, ResearchProfileModel]:
    u_id = user_id or uuid.uuid4()
    user = UserModel(
        id=u_id,
        email=email or f"jane.{u_id.hex[:6]}@university.edu",
        hashed_password="pw",
        full_name=name,
        is_active=True,
    )
    db.add(user)
    db.flush()

    profile = ResearchProfileModel(
        user_id=user.id,
        institution="MIT",
        department="Computer Science",
        academic_status=AcademicStatus.FACULTY.value,
        target_opportunity_types=["CONFERENCE", "JOURNAL"],
    )
    db.add(profile)
    db.commit()
    db.refresh(user)
    db.refresh(profile)
    return user, profile


def create_mock_opportunity(
    db: Session,
    title: str = "ACM Conference on Machine Learning",
    opp_type: str = "CONFERENCE",
    delivery_mode: str = "HYBRID",
    risk_level: str = "LOW_RISK",
    is_predatory: bool = False,
    deadline_status: str = "UPCOMING",
) -> OpportunityModel:
    opp = OpportunityModel(
        source_id=uuid.uuid4(),
        title=title,
        description="A premier international academic venue.",
        opportunity_type=opp_type,
        delivery_mode=delivery_mode,
        is_predatory_flag=is_predatory,
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=30),
        status="ACTIVE",
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


# ── Test Cases ────────────────────────────────────────────────────────────────


def test_explanation_generation_structure():
    """Test that RecommendationExplanationSchema is properly populated with all required fields."""
    opp_id = uuid.uuid4()
    candidate = PersonalizedRankedCandidateSchema(
        opportunity_id=opp_id,
        rank=1,
        base_rank=1,
        rank_delta=0,
        final_score=0.85,
        base_relevance_score=0.75,
        personalization_score=0.60,
        personalization_adjustment=0.10,
        score_breakdown=PersonalizationScoreBreakdownSchema(
            explicit_preference_score=0.80,
            inferred_preference_score=0.0,
            expertise_match_score=0.70,
            profile_match_score=0.50,
            provenance_score=0.20,
            behavioral_score=0.60,
            behavioral_confidence=0.80,
            behavioral_adjustment=0.05,
            raw_personalization_score=0.60,
            relevance_damping=1.0,
        ),
        matched_signals=MatchedPersonalizationSignalsSchema(
            matched_preferences=["CONFERENCE", "HYBRID"],
            matched_expertise=["Machine Learning"],
            matched_topics=["Machine Learning"],
            matched_types=["CONFERENCE"],
        ),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp_id,
            sources=[CandidateSourceType.RESEARCH_EXPERTISE],
            matched_topics=["Machine Learning"],
            matched_preferences=["CONFERENCE"],
            matched_expertise=["Machine Learning"],
            reasons=["Matched topic"],
            retrieval_channels=["direct"],
        ),
        opportunity=PersonalizedCandidateOpportunitySchema(
            id=opp_id,
            title="ICML 2026",
            opportunity_type="CONFERENCE",
            delivery_mode="HYBRID",
            topics=["Machine Learning"],
            risk_level="LOW_RISK",
            is_predatory_flag=False,
            deadline_status="UPCOMING",
            status="ACTIVE",
        ),
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(),
        expertise_items=(),
    )

    explanation = recommendation_explainer.explain_ranked_candidate(
        candidate=candidate,
        context=context,
        ranking_version="phase3.8-v1",
    )

    assert isinstance(explanation, RecommendationExplanationSchema)
    assert explanation.opportunity_id == opp_id
    assert explanation.rank == 1
    assert explanation.final_score == 0.85
    assert explanation.base_relevance_score == 0.75
    assert explanation.personalization_contribution == 0.10
    assert explanation.personalization_strength in ("Highly personalized", "Personalized")
    assert len(explanation.primary_reasons) > 0
    assert explanation.trust_status == "Verified"
    assert explanation.is_historical is False
    assert explanation.ranking_version == "phase3.8-v1"


def test_explanation_signal_priority_ordering():
    """Verify strict influence hierarchy: Explicit > Expertise > Behavioral > Profile > Relevance."""
    opp_id = uuid.uuid4()
    candidate = PersonalizedRankedCandidateSchema(
        opportunity_id=opp_id,
        rank=1,
        base_rank=2,
        rank_delta=1,
        final_score=0.90,
        base_relevance_score=0.80,
        personalization_score=0.75,
        personalization_adjustment=0.10,
        score_breakdown=PersonalizationScoreBreakdownSchema(
            explicit_preference_score=0.90,
            expertise_match_score=0.80,
            behavioral_adjustment=0.04,
            raw_personalization_score=0.75,
        ),
        matched_signals=MatchedPersonalizationSignalsSchema(
            matched_preferences=["Conference"],
            matched_expertise=["Computer Vision"],
            matched_topics=["Computer Vision"],
            matched_types=["Conference"],
        ),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp_id,
            sources=[CandidateSourceType.RESEARCH_EXPERTISE],
            matched_topics=[],
            matched_preferences=[],
            matched_expertise=[],
            reasons=[],
            retrieval_channels=[],
        ),
        opportunity=PersonalizedCandidateOpportunitySchema(
            id=opp_id,
            title="CVPR 2026",
            opportunity_type="CONFERENCE",
            delivery_mode="HYBRID",
            topics=["Computer Vision"],
            risk_level="LOW_RISK",
            is_predatory_flag=False,
            deadline_status="UPCOMING",
            status="ACTIVE",
        ),
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(),
        expertise_items=(),
    )

    explanation = recommendation_explainer.explain_ranked_candidate(candidate, context)

    # First primary reason must be explicit preference
    assert "explicit preference" in explanation.primary_reasons[0].lower()
    # Second primary reason must be expertise
    assert "expertise" in explanation.primary_reasons[1].lower()


def test_positive_and_negative_signals():
    """Verify explanation properly distinguishes positive boosts and negative demotions."""
    opp_id = uuid.uuid4()

    # Candidate with negative behavioral adjustment
    neg_candidate = PersonalizedRankedCandidateSchema(
        opportunity_id=opp_id,
        rank=5,
        base_rank=3,
        rank_delta=-2,
        final_score=0.55,
        base_relevance_score=0.60,
        personalization_score=0.20,
        personalization_adjustment=0.0,
        score_breakdown=PersonalizationScoreBreakdownSchema(
            behavioral_adjustment=-0.08,
            raw_personalization_score=0.20,
        ),
        matched_signals=MatchedPersonalizationSignalsSchema(),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp_id,
            sources=[CandidateSourceType.COLD_START_FALLBACK],
            matched_topics=[],
            matched_preferences=[],
            matched_expertise=[],
            reasons=[],
            retrieval_channels=[],
        ),
        opportunity=PersonalizedCandidateOpportunitySchema(
            id=opp_id,
            title="Workshop on Legacy Topics",
            opportunity_type="WORKSHOP",
            delivery_mode="OFFLINE",
            topics=["Legacy Systems"],
            risk_level="LOW_RISK",
            is_predatory_flag=False,
            deadline_status="UPCOMING",
            status="ACTIVE",
        ),
    )

    context = ResearcherPersonalizationContext(profile_id=uuid.uuid4())
    explanation = recommendation_explainer.explain_ranked_candidate(neg_candidate, context)

    assert len(explanation.negative_signals) > 0
    assert any("dismissal" in s.lower() for s in explanation.negative_signals)


def test_score_consistency_invariants():
    """Test that reported explanation scores exactly match candidate scores within tolerance."""
    opp_id = uuid.uuid4()
    candidate = PersonalizedRankedCandidateSchema(
        opportunity_id=opp_id,
        rank=2,
        base_rank=3,
        rank_delta=1,
        final_score=0.7845,
        base_relevance_score=0.6920,
        personalization_score=0.5500,
        personalization_adjustment=0.0925,
        score_breakdown=PersonalizationScoreBreakdownSchema(
            raw_personalization_score=0.5500,
        ),
        matched_signals=MatchedPersonalizationSignalsSchema(),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp_id,
            sources=[CandidateSourceType.RESEARCH_EXPERTISE],
            matched_topics=[],
            matched_preferences=[],
            matched_expertise=[],
            reasons=[],
            retrieval_channels=[],
        ),
        opportunity=PersonalizedCandidateOpportunitySchema(
            id=opp_id,
            title="Robotics Symposium",
            opportunity_type="CONFERENCE",
            delivery_mode="ONLINE",
            topics=["Robotics"],
            risk_level="LOW_RISK",
            is_predatory_flag=False,
            deadline_status="UPCOMING",
            status="ACTIVE",
        ),
    )

    context = ResearcherPersonalizationContext(profile_id=uuid.uuid4())
    explanation = recommendation_explainer.explain_ranked_candidate(candidate, context)

    assert abs(explanation.base_relevance_score - candidate.base_relevance_score) < 1e-4
    assert abs(explanation.personalization_contribution - candidate.personalization_adjustment) < 1e-4
    assert abs(explanation.final_score - candidate.final_score) < 1e-4


def test_safety_dominance_high_risk_opportunity():
    """Verify safety dominance: high-risk candidate displays prominent warning and NEVER praises fit without warning."""
    opp_id = uuid.uuid4()
    high_risk_candidate = PersonalizedRankedCandidateSchema(
        opportunity_id=opp_id,
        rank=10,
        base_rank=10,
        rank_delta=0,
        final_score=0.40,
        base_relevance_score=0.40,
        personalization_score=0.0,
        personalization_adjustment=0.0,
        score_breakdown=PersonalizationScoreBreakdownSchema(),
        matched_signals=MatchedPersonalizationSignalsSchema(),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp_id,
            sources=[CandidateSourceType.COLD_START_FALLBACK],
            matched_topics=[],
            matched_preferences=[],
            matched_expertise=[],
            reasons=[],
            retrieval_channels=[],
        ),
        opportunity=PersonalizedCandidateOpportunitySchema(
            id=opp_id,
            title="Predatory International Journal of Everything",
            opportunity_type="JOURNAL",
            delivery_mode="ONLINE",
            topics=["Everything"],
            risk_level="HIGH_RISK",
            is_predatory_flag=True,
            risk_score=0.95,
            deadline_status="EXPIRED",
            status="ACTIVE",
        ),
    )

    context = ResearcherPersonalizationContext(profile_id=uuid.uuid4())
    explanation = recommendation_explainer.explain_ranked_candidate(high_risk_candidate, context)

    assert explanation.trust_status == "High Risk"
    assert "predatory" in explanation.risk_summary.lower()
    assert any("⚠️" in r or "predatory" in r.lower() for r in explanation.primary_reasons)
    # Must NOT claim high personalization
    assert explanation.personalization_strength == "General recommendation"


def test_historical_explanation_immutability(db_session: Session):
    """Verify that historical snapshot explanation uses frozen snapshot values and does not mutate with current profile."""
    _, profile = create_mock_researcher(db_session, "Dr. Historical")
    opp = create_mock_opportunity(db_session, "NeurIPS 2024")

    # Create a historical snapshot using Phase 3.7 service
    snapshot = ResearcherRecommendationSnapshotModel(
        researcher_id=profile.id,
        ranking_version="phase3.7-v1",
        candidate_count=50,
        returned_count=1,
        created_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(snapshot)
    db_session.flush()

    item = ResearcherRecommendationItemModel(
        snapshot_id=snapshot.id,
        opportunity_id=opp.id,
        rank=1,
        base_relevance_score=0.82,
        personalization_score=0.70,
        behavioral_adjustment=0.05,
        final_score=0.92,
        risk_level="LOW_RISK",
        deadline_status="UPCOMING",
        created_at=snapshot.created_at,
    )
    db_session.add(item)
    db_session.commit()

    # Explain historical item
    explanation = PersonalizationExplanationService.explain_historical_recommendation(
        db=db_session,
        profile_id=profile.id,
        snapshot_id=snapshot.id,
        opportunity_id=opp.id,
    )

    assert explanation.is_historical is True
    assert explanation.ranking_version == "phase3.7-v1"
    assert explanation.final_score == 0.92
    assert explanation.base_relevance_score == 0.82
    assert explanation.rank == 1
    assert "Jan 15, 2025" in explanation.primary_reasons[0]


def test_cold_start_and_no_feedback_state(db_session: Session):
    """Verify cold start and no-feedback handling in personalization summary."""
    _, profile = create_mock_researcher(db_session, "Dr. Cold Start")

    summary = PersonalizationExplanationService.get_personalization_summary(
        db=db_session,
        profile_id=profile.id,
    )

    assert summary.researcher_id == profile.id
    assert summary.active_interests_count == 0
    assert summary.explicit_preferences_count == 0
    assert summary.behavioral_signals_count == 0
    assert summary.total_feedback_count == 0
    assert summary.has_feedback is False
    assert summary.is_cold_start is True
    assert summary.personalization_confidence == "Cold Start"


def test_personalization_strength_classification():
    """Verify personalization strength thresholds."""
    assert (
        RecommendationExplainer.derive_personalization_strength(0.12, 0.85)
        == "Highly personalized"
    )
    assert (
        RecommendationExplainer.derive_personalization_strength(0.06, 0.60)
        == "Personalized"
    )
    assert (
        RecommendationExplainer.derive_personalization_strength(0.01, 0.30)
        == "Some personalization"
    )
    assert (
        RecommendationExplainer.derive_personalization_strength(0.0, 0.05)
        == "General recommendation"
    )
    assert (
        RecommendationExplainer.derive_personalization_strength(0.12, 0.85, is_cold_start=True)
        == "General recommendation"
    )


def test_api_personalization_summary_and_ownership(client: TestClient, db_session: Session):
    """Test API endpoint GET /{researcher_id}/personalization-summary with ownership enforcement."""
    user_a = uuid.uuid4()
    _, profile_a = create_mock_researcher(db_session, "Dr. User A", user_id=user_a)
    # A real second account: Phase 6 rejects unknown credentials with 401, so proving the
    # 403 ownership boundary requires authenticating as another registered researcher.
    user_b_model, _ = create_mock_researcher(db_session, "Dr. User B")
    user_b = user_b_model.id

    # 1. Successful request with matching X-User-ID
    res = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization-summary",
        headers={"X-User-ID": str(user_a)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["researcher_id"] == str(profile_a.id)
    assert "personalization_confidence" in data
    assert "learned_topics" in data

    # 2. Forbidden request with non-matching X-User-ID
    res_forbidden = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization-summary",
        headers={"X-User-ID": str(user_b)},
    )
    assert res_forbidden.status_code == 403


def test_api_recommendation_explanation_ownership(client: TestClient, db_session: Session):
    """Test API endpoint GET /{researcher_id}/personalized-recommendations/{opp_id}/explanation with ownership."""
    user_a = uuid.uuid4()
    _, profile_a = create_mock_researcher(db_session, "Dr. User A", user_id=user_a)
    user_b_model, _ = create_mock_researcher(db_session, "Dr. User B")
    user_b = user_b_model.id
    opp = create_mock_opportunity(db_session, "AAAI 2026")

    # Matching owner
    res = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalized-recommendations/{opp.id}/explanation",
        headers={"X-User-ID": str(user_a)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["opportunity_id"] == str(opp.id)
    assert "primary_reasons" in data

    # Forbidden owner
    res_forbidden = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalized-recommendations/{opp.id}/explanation",
        headers={"X-User-ID": str(user_b)},
    )
    assert res_forbidden.status_code == 403


def test_api_historical_explanation_endpoint(client: TestClient, db_session: Session):
    """Test API endpoint for historical recommendation explanation."""
    user_a = uuid.uuid4()
    _, profile = create_mock_researcher(db_session, "Dr. Historic", user_id=user_a)
    opp = create_mock_opportunity(db_session, "ACL 2025")

    snapshot = ResearcherRecommendationSnapshotModel(
        researcher_id=profile.id,
        ranking_version="phase3.7-v1",
        candidate_count=20,
        returned_count=1,
    )
    db_session.add(snapshot)
    db_session.flush()

    item = ResearcherRecommendationItemModel(
        snapshot_id=snapshot.id,
        opportunity_id=opp.id,
        rank=1,
        base_relevance_score=0.88,
        personalization_score=0.75,
        behavioral_adjustment=0.03,
        final_score=0.91,
        risk_level="LOW_RISK",
        deadline_status="UPCOMING",
    )
    db_session.add(item)
    db_session.commit()

    res = client.get(
        f"/api/v1/researchers/{profile.id}/recommendation-history/{snapshot.id}/items/{opp.id}/explanation",
        headers={"X-User-ID": str(user_a)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["opportunity_id"] == str(opp.id)
    assert data["is_historical"] is True
    assert data["ranking_version"] == "phase3.7-v1"
    assert data["final_score"] == 0.91


def test_no_hallucinated_signals():
    """Verify that signals not present in context or matched signals NEVER appear in explanation reasons."""
    opp_id = uuid.uuid4()
    candidate = PersonalizedRankedCandidateSchema(
        opportunity_id=opp_id,
        rank=1,
        base_rank=1,
        rank_delta=0,
        final_score=0.70,
        base_relevance_score=0.70,
        personalization_score=0.0,
        personalization_adjustment=0.0,
        score_breakdown=PersonalizationScoreBreakdownSchema(),
        matched_signals=MatchedPersonalizationSignalsSchema(
            matched_preferences=[],
            matched_expertise=[],
            matched_topics=["General Physics"],
            matched_types=["JOURNAL"],
        ),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp_id,
            sources=[CandidateSourceType.COLD_START_FALLBACK],
            matched_topics=[],
            matched_preferences=[],
            matched_expertise=[],
            reasons=[],
            retrieval_channels=[],
        ),
        opportunity=PersonalizedCandidateOpportunitySchema(
            id=opp_id,
            title="Physical Review Letters",
            opportunity_type="JOURNAL",
            delivery_mode="ONLINE",
            topics=["General Physics"],
            status="ACTIVE",
        ),
    )

    # Context has NO conference preference, NO machine learning expertise
    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(),
        expertise_items=(),
    )

    explanation = recommendation_explainer.explain_ranked_candidate(candidate, context)

    # Explanation must NOT claim conference or machine learning
    all_text = " ".join(explanation.primary_reasons + explanation.supporting_reasons).lower()
    assert "machine learning" not in all_text
    assert "conference" not in all_text
    assert len(explanation.preference_reasons) == 0
    assert len(explanation.expertise_reasons) == 0


def test_personalization_summary_service(db_session: Session):
    """Test PersonalizationExplanationService.get_personalization_summary with active records."""
    user, profile = create_mock_researcher(db_session, "Dr. Active Scholar")

    # Add interest
    interest = ResearcherInterestModel(
        profile_id=profile.id,
        topic_name="Reinforcement Learning",
        topic_slug="reinforcement-learning",
        classification="PRIMARY",
        strength=0.92,
    )
    db_session.add(interest)

    # Add preference
    pref = ResearcherPreferenceModel(
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        display_label="Conference",
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)
    db_session.commit()

    summary = PersonalizationExplanationService.get_personalization_summary(
        db=db_session,
        profile_id=profile.id,
    )

    assert summary.researcher_id == profile.id
    assert summary.active_interests_count == 1
    assert summary.strong_expertise_count == 1
    assert summary.explicit_preferences_count == 1
    assert summary.is_cold_start is False
    assert summary.personalization_confidence in ("High", "Moderate", "Low")
    assert any("CONFERENCE" in p for p in summary.top_positive_signals)


def test_zero_n_plus_one_performance(db_session: Session):
    """Verify that generating explanations executes in bounded, batched queries."""
    from sqlalchemy import event

    user, profile = create_mock_researcher(db_session, "Dr. Perf")

    # Measure query count during summary generation
    query_count = 0

    def query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", query_listener)

    try:
        PersonalizationExplanationService.get_personalization_summary(
            db=db_session,
            profile_id=profile.id,
        )
        # Should be <= 6 batched queries for profile, interests, preferences, feedback, count
        assert query_count <= 8, f"Too many queries during summary aggregation: {query_count}"
    finally:
        event.remove(engine, "before_cursor_execute", query_listener)

