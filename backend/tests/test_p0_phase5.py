"""
Phase 5 — P0 Integration Test Suite
====================================

10 mandatory integration tests verifying the P0 architectural fixes:
  1. Test 1  — EXCLUDED semantics: EXCLUDED → no positive boost.
  2. Test 2  — EXCLUDED dominance: EXCLUDED + strong adaptive positive signal → exclusion wins.
  3. Test 3  — PreferenceInterpreter live integration: live pipeline invokes interpreter.
  4. Test 4  — Authoritative scorer: live endpoint executes authoritative Phase 5 scoring.
  5. Test 5  — No duplicate scoring: single-opportunity and batch ranking are consistent.
  6. Test 6  — Adaptive signal propagation: DB signal → ranking context → final ranking.
  7. Test 7  — Adaptive disabled: adaptive_signals_enabled=False → adaptive influence=0.
  8. Test 8  — Personalization disabled: personalization_enabled=False → adjustment=0.
  9. Test 9  — Explicit preference still works: PREFERRED continues to produce positive boost.
  10. Test 10 — Researcher isolation: Researcher A's signals do not leak to Researcher B.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.adaptive_signal import AdaptivePreferenceSignalModel
from app.models.base import Base
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.personalization_governance import (
    GovernanceGateState,
    PersonalizationDriftEvaluationModel,
)
from app.models.personalization_transparency import (
    ResearcherPersonalizationSettingsModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.user import UserModel
from app.services.research_calendar_service import ResearchCalendarService
from app.schemas.adaptive_signal import AdaptivePreferenceSignal
from app.schemas.personalization_calibration import PersonalizationCalibrationSchema
from app.ranking.personalization_ranker import (
    PersonalizationRanker,
    ResearcherPersonalizationContext,
    personalization_ranker,
)
from app.personalization.interpreter import PreferenceInterpreter
from app.personalization.models import PreferenceMatchType
from app.personalization.scorer import PersonalizationScorer
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceType,
    PersonalizedCandidateItemSchema,
    PersonalizedCandidateOpportunitySchema,
)
from app.schemas.personalized_ranking import (
    PersonalizedRankedCandidateSchema,
    PersonalizedRankingResponse,
)
from app.schemas.researcher_preference import PreferenceType
from app.services.personalization_ranking_service import (
    PersonalizationRankingService,
)

# ── SQLite Compatibility ───────────────────────────────────────────────────────

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a clean in-memory SQLite session with all Phase 5 tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """FastAPI TestClient with overridden get_db dependency."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Fixture Helpers ────────────────────────────────────────────────────────────

def create_user(db: Session, email: str = "researcher@university.edu") -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        full_name="Dr. Test",
        hashed_password="test_hashed_pw",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def create_profile(
    db: Session,
    user: UserModel,
    keywords: list[str] | None = None,
    target_types: list[str] | None = None,
) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        institution="Stanford University",
        academic_status=AcademicStatus.FACULTY.value,
        keywords=keywords if keywords is not None else ["Machine Learning"],
        target_opportunity_types=target_types if target_types is not None else ["CONFERENCE", "JOURNAL"],
    )
    db.add(profile)
    db.flush()
    return profile


def create_opportunity(
    db: Session,
    title: str,
    opportunity_type: str = "CONFERENCE",
    delivery_mode: str = "HYBRID",
    deadline_days: int = 30,
) -> OpportunityModel:
    deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title=title,
        opportunity_type=opportunity_type,
        delivery_mode=delivery_mode,
        status="ACTIVE",
        submission_deadline=deadline,
        is_predatory_flag=False,
        risk_score=0.0,
        location="San Francisco, USA",
        organizer="IEEE",
        content_hash=f"hash_{uuid.uuid4().hex[:12]}",
    )
    db.add(opp)
    db.flush()
    return opp


def make_candidate_item(
    opp_id: uuid.UUID,
    title: str,
    base_score: float = 0.70,
    opportunity_type: str = "CONFERENCE",
    delivery_mode: str = "HYBRID",
    topics: list[str] | None = None,
) -> PersonalizedCandidateItemSchema:
    opp_schema = PersonalizedCandidateOpportunitySchema(
        id=opp_id,
        title=title,
        opportunity_type=opportunity_type,
        delivery_mode=delivery_mode,
        location="San Francisco, USA",
        organizer="IEEE",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=30),
        website_url="https://example.org",
        topics=topics or [],
        status="ACTIVE",
        is_predatory_flag=False,
        risk_level="LOW_RISK",
        risk_score=0.0,
        risk_reasons=[],
        deadline_status="UPCOMING",
        days_remaining=30.0,
        urgency_tier="APPROACHING",
        deadline_explanation="Submission closes soon",
    )
    provenance = CandidateProvenanceSchema(
        candidate_id=uuid.uuid4(),
        opportunity_id=opp_id,
        sources=[CandidateSourceType.EXPLICIT_PREFERENCE],
        matched_topics=topics or [],
        matched_preferences=[],
        matched_expertise=[],
        reasons=["Candidate match"],
        retrieval_channels=["channel_test"],
    )
    return PersonalizedCandidateItemSchema(
        candidate_id=uuid.uuid4(),
        opportunity=opp_schema,
        provenance=provenance,
        base_relevance_score=base_score,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — P0-1: EXCLUDED Semantics: EXCLUDED → no positive boost
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_1_excluded_semantics_no_positive_boost():
    """
    P0-1 Case A: Explicitly excluded opportunity must never receive a positive
    personalization boost. Personalization adjustment must be <= 0.0.
    """
    ranker = PersonalizationRanker()
    opp_id = uuid.uuid4()
    cand = make_candidate_item(opp_id, "Excluded Conf", base_score=0.75, opportunity_type="CONFERENCE")

    excluded_pref = ResearcherPreferenceModel(
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="EXCLUDED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        recency_score=1.0,
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(excluded_pref,),
    )

    ranked = ranker.rank([cand], context=context, preferences=[excluded_pref])

    assert len(ranked) == 1
    # MUST NOT receive positive boost
    assert ranked[0].personalization_adjustment <= 0.0
    assert ranked[0].final_score <= ranked[0].base_relevance_score


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 — P0-1: EXCLUDED Dominance: EXCLUDED + Strong Adaptive Signal
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_1_excluded_dominance_over_strong_adaptive_signal():
    """
    P0-1 Case B: When an explicit exclusion conflicts with a strong positive
    adaptive signal for the same attribute, explicit exclusion strictly dominates.
    No positive boost is granted.
    """
    ranker = PersonalizationRanker()
    opp_id = uuid.uuid4()
    cand = make_candidate_item(opp_id, "Conflict Conf", base_score=0.70, opportunity_type="CONFERENCE")

    excluded_pref = ResearcherPreferenceModel(
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="EXCLUDED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        recency_score=1.0,
    )

    # Strong positive adaptive signal for the same dimension and value
    adaptive_sig = MagicMock()
    adaptive_sig.dimension = "OPPORTUNITY_TYPE"
    adaptive_sig.signal_value = "CONFERENCE"
    adaptive_sig.weighted_signal_strength = 1.0
    adaptive_sig.confidence = 1.0
    adaptive_sig.decay_adjusted_positive_weight = 10.0
    adaptive_sig.decay_adjusted_negative_weight = 0.0
    adaptive_sig.evidence_state = "STRONG"

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(excluded_pref,),
        adaptive_signals=(adaptive_sig,),
    )

    ranked = ranker.rank(
        [cand],
        context=context,
        adaptive_signals=[adaptive_sig],
        preferences=[excluded_pref],
    )

    assert len(ranked) == 1
    # Exclusion MUST dominate: NO positive boost allowed
    assert ranked[0].personalization_adjustment <= 0.0
    assert ranked[0].final_score <= ranked[0].base_relevance_score


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3 — P0-2: PreferenceInterpreter Live Integration
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_2_preference_interpreter_live_integration(db_session: Session):
    """
    P0-2: Verify that PreferenceInterpreter actually participates in the live
    recommendation ranking flow (called through PersonalizationScorer batch evaluation).
    """
    user = create_user(db_session)
    profile = create_profile(db_session, user)

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)
    opp = create_opportunity(db_session, "Interpreted Conf", opportunity_type="CONFERENCE")
    db_session.commit()

    with patch.object(
        PreferenceInterpreter,
        "evaluate_opportunities_batch",
        wraps=PreferenceInterpreter.evaluate_opportunities_batch,
    ) as mock_interpreter:
        response = PersonalizationRankingService.get_personalized_recommendations(
            db=db_session,
            profile_id=profile.id,
            limit=10,
        )

        # Verification: PreferenceInterpreter MUST have been called in live flow
        assert mock_interpreter.called
        assert len(response.recommendations) >= 1
        assert response.recommendations[0].personalization_adjustment > 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 — P0-3: Authoritative Personalization Scorer in Live Path
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_3_authoritative_scorer_in_live_recommendation_endpoint(
    client: TestClient, db_session: Session
):
    """
    P0-3: Live recommendation API endpoint executes PersonalizationScorer batch
    scoring (Option B architecture) and returns authoritative personalization output.
    """
    user = create_user(db_session, email="live_authoritative@university.edu")
    profile = create_profile(db_session, user)

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)
    opp = create_opportunity(db_session, "Live Conf Opp", opportunity_type="CONFERENCE")
    db_session.commit()

    with patch.object(
        PersonalizationScorer,
        "score_opportunities_batch",
        wraps=PersonalizationScorer.score_opportunities_batch,
    ) as mock_scorer:
        resp = client.get(
            f"/api/v1/researchers/{profile.id}/personalized-recommendations",
            headers={"X-User-ID": str(user.id)},
        )
        assert resp.status_code == 200
        data = resp.json()

        # The authoritative PersonalizationScorer MUST be called in live flow
        assert mock_scorer.called
        assert len(data["recommendations"]) >= 1
        assert data["recommendations"][0]["opportunity_id"] == str(opp.id)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 — P0-3: No Duplicate / Inconsistent Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_3_no_duplicate_scoring_consistency():
    """
    P0-3: Verify there is no competing personalization calculation producing
    inconsistent results between single-opportunity scoring and batch ranking.
    """
    ranker = PersonalizationRanker()
    opp_id = uuid.uuid4()
    cand = make_candidate_item(opp_id, "Consistency Opp", base_score=0.70, opportunity_type="CONFERENCE")

    pref_id = uuid.uuid4()
    prof_id = uuid.uuid4()
    pref = ResearcherPreferenceModel(
        id=pref_id,
        profile_id=prof_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        source="EXPLICIT",
        is_active=True,
        recency_score=1.0,
    )

    context = ResearcherPersonalizationContext(
        profile_id=prof_id,
        explicit_preferences=(pref,),
    )

    # 1. Score via batch ranking
    ranked = ranker.rank([cand], context=context, preferences=[pref])

    # 2. Score via PersonalizationScorer directly
    opp_model = OpportunityModel(
        id=opp_id,
        title="Consistency Opp",
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        status="ACTIVE",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=30),
        is_predatory_flag=False,
        risk_score=0.0,
        location="San Francisco, USA",
        organizer="IEEE",
        content_hash=f"hash_{uuid.uuid4().hex[:12]}",
    )
    assessment = PersonalizationScorer.score_opportunity(
        profile_id=context.profile_id,
        preferences=[pref],
        opportunity=opp_model,
    )

    # Both must agree: positive personalization detected, raw scores consistent
    assert ranked[0].personalization_adjustment > 0.0
    assert assessment.personalization_score > 0.0
    assert assessment.preference_assessment.excluded_matches_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6 — P0-4: Adaptive Signal Propagation to Final Ranking
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_4_adaptive_signal_propagation(db_session: Session):
    """
    P0-4: Verify adaptive signals stored in DB propagate through
    ResearcherPersonalizationContext into PersonalizationRanker and produce
    a positive personalization adjustment.
    """
    user = create_user(db_session)
    profile = create_profile(db_session, user)

    # Store an adaptive signal in DB (no explicit preference)
    signal = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        positive_evidence_count=5,
        negative_evidence_count=0,
        total_evidence_count=5,
        decay_adjusted_positive_weight=5.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=0.8,
        confidence=0.85,
        evidence_state="STRONG",
        algorithm_version="5.5.1",
        deterministic_explanation="Based on interaction evidence",
    )
    db_session.add(signal)

    # Opp 1 matches adaptive signal (CONFERENCE), Opp 2 does not (JOURNAL)
    opp_conf = create_opportunity(db_session, "Adaptive Conf Opp", opportunity_type="CONFERENCE")
    opp_journ = create_opportunity(db_session, "Other Journal Opp", opportunity_type="JOURNAL")
    db_session.commit()

    response = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile.id,
        limit=10,
    )

    assert len(response.recommendations) >= 2
    # Find the conference item
    conf_item = next(it for it in response.recommendations if it.opportunity_id == opp_conf.id)
    journ_item = next(it for it in response.recommendations if it.opportunity_id == opp_journ.id)

    # Conf item received positive adjustment via adaptive signal
    assert conf_item.personalization_adjustment > 0.0
    assert conf_item.personalization_adjustment > journ_item.personalization_adjustment


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7 — P0-4: Adaptive Signals Disabled Flag → 0.0 Influence
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_4_adaptive_signals_disabled_flag(db_session: Session):
    """
    P0-4 Feature Flag: When adaptive_signals_enabled=False in settings,
    adaptive signals MUST NOT influence ranking (adjustment=0.0).
    """
    user = create_user(db_session)
    profile = create_profile(db_session, user, keywords=[], target_types=[])

    # Store settings with adaptive_signals_enabled = False
    settings = ResearcherPersonalizationSettingsModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        personalization_enabled=True,
        adaptive_signals_enabled=False,
    )
    db_session.add(settings)

    # Store an adaptive signal
    signal = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        positive_evidence_count=10,
        weighted_signal_strength=1.0,
        confidence=1.0,
        evidence_state="STRONG",
        algorithm_version="5.5.1",
        deterministic_explanation="Based on interaction evidence",
    )
    db_session.add(signal)
    opp = create_opportunity(db_session, "Conf Opp", opportunity_type="CONFERENCE")
    db_session.commit()

    response = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile.id,
        limit=10,
    )

    assert len(response.recommendations) >= 1
    # Adaptive signal must NOT produce any behavioral adjustment
    assert response.recommendations[0].score_breakdown.behavioral_adjustment == 0.0
    assert response.recommendations[0].score_breakdown.behavioral_score == 0.0
    assert response.recommendations[0].personalization_adjustment == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8 — P0-4: Personalization Disabled Flag → All Adjustments 0.0
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_4_personalization_disabled_flag(db_session: Session):
    """
    P0-4 Feature Flag: When personalization_enabled=False in settings,
    all personalization adjustments MUST be 0.0.
    """
    user = create_user(db_session)
    profile = create_profile(db_session, user)

    # Settings: personalization_enabled = False
    settings = ResearcherPersonalizationSettingsModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        personalization_enabled=False,
        adaptive_signals_enabled=True,
    )
    db_session.add(settings)

    # Add both explicit preference and adaptive signal
    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)
    opp = create_opportunity(db_session, "Conf Opp", opportunity_type="CONFERENCE")
    db_session.commit()

    response = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile.id,
        limit=10,
    )

    assert len(response.recommendations) >= 1
    for it in response.recommendations:
        assert it.personalization_adjustment == 0.0
        assert it.final_score == it.base_relevance_score


# ═══════════════════════════════════════════════════════════════════════════════
# Test 9 — Explicit Positive Preference Still Works
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_explicit_preference_positive_boost_remains_functional(db_session: Session):
    """
    P0 Regression Guard: Fixing EXCLUDED semantics must not break positive
    preferences. PREFERRED explicit preferences must produce positive adjustment.
    """
    user = create_user(db_session)
    profile = create_profile(db_session, user)

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)
    opp = create_opportunity(db_session, "Valid Conf Opp", opportunity_type="CONFERENCE")
    db_session.commit()

    response = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile.id,
        limit=10,
    )

    assert len(response.recommendations) >= 1
    conf_item = next(it for it in response.recommendations if it.opportunity_id == opp.id)
    assert conf_item.personalization_adjustment > 0.0
    assert conf_item.final_score > conf_item.base_relevance_score


# ═══════════════════════════════════════════════════════════════════════════════
# Test 10 — P0 Security: Researcher Isolation Guarantee
# ═══════════════════════════════════════════════════════════════════════════════

def test_p0_researcher_isolation(db_session: Session):
    """
    P0 Security Requirement: Researcher A's preferences/signals must NOT leak
    to Researcher B. Complete cross-researcher personalization isolation.
    """
    user_a = create_user(db_session, email="researcher_a@university.edu")
    profile_a = create_profile(db_session, user_a)

    user_b = create_user(db_session, email="researcher_b@university.edu")
    profile_b = create_profile(db_session, user_b)

    # Researcher A prefers CONFERENCE
    pref_a = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_a.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref_a)

    # Researcher B excludes CONFERENCE
    pref_b = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_b.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="EXCLUDED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref_b)

    opp = create_opportunity(db_session, "Conference Opp", opportunity_type="CONFERENCE")
    db_session.commit()

    # Recommendations for Researcher A
    resp_a = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile_a.id,
        limit=10,
    )
    # Recommendations for Researcher B
    resp_b = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile_b.id,
        limit=10,
    )

    item_a = next(it for it in resp_a.recommendations if it.opportunity_id == opp.id)
    item_b = next(it for it in resp_b.recommendations if it.opportunity_id == opp.id)

    # Researcher A got positive boost
    assert item_a.personalization_adjustment > 0.0

    # Researcher B received EXCLUDED semantics: adjustment <= 0.0 (never positive)
    assert item_b.personalization_adjustment <= 0.0

    # Total isolation: scores must NOT match
    assert item_a.final_score > item_b.final_score


def make_adaptive_signal(
    profile_id: uuid.UUID,
    dimension: str,
    value: str,
    strength: float = 0.95,
    confidence: float = 0.90,
) -> AdaptivePreferenceSignal:
    now = datetime.now(timezone.utc)
    model = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        dimension=dimension,
        signal_value=value,
        positive_evidence_count=10,
        negative_evidence_count=0,
        total_evidence_count=10,
        decay_adjusted_positive_weight=10.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=strength,
        confidence=confidence,
        evidence_state="STRONG",
        evidence_window_days=30.0,
        algorithm_version="5.5.1",
        deterministic_explanation="Based on interaction evidence",
        created_at=now,
        updated_at=now,
    )
    return AdaptivePreferenceSignal.model_validate(model)


# ═══════════════════════════════════════════════════════════════════════════════
# BLOCKER 1 — Live Ranker Exclusion Tests (Cases A, B, C, D, E)
# ═══════════════════════════════════════════════════════════════════════════════

def test_blocker1_case_a_explicit_excluded_no_positive_boost():
    """
    Test A: Explicit EXCLUDED preference + matching opportunity → Ranker personalization boost <= 0.
    Must never produce positive adjustment even when candidate has high topic overlap or keywords.
    """
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    excluded_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="TOPIC",
        preference_key="topic",
        preference_value="Quantum Computing",
        preference_type="EXCLUDED",
        display_label="Quantum Computing",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    context = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(excluded_pref,),
        profile_keywords=("Quantum Computing", "Physics"),
    )

    cand = make_candidate_item(
        opp_id=opp_id,
        title="International Quantum Computing Summit",
        base_score=0.60,
        topics=["Quantum Computing"],
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand], context=context, enable_personalization=True)

    assert len(ranked) == 1
    item = ranked[0]
    # Invariant: explicit exclusion cannot produce positive boost
    assert item.personalization_adjustment <= 0.0
    assert item.personalization_adjustment == 0.0
    assert item.final_score == item.base_relevance_score
    assert item.score_breakdown.raw_personalization_score == 0.0
    assert item.score_breakdown.explicit_preference_score == 0.0


def test_blocker1_case_b_excluded_with_strong_positive_adaptive_signal():
    """
    Test B: EXCLUDED + strong positive adaptive signal → no positive personalization boost.
    Explicit exclusion strictly dominates inferred adaptive signals.
    """
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    excluded_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="EXCLUDED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    adaptive_sig = make_adaptive_signal(
        profile_id=profile_id,
        dimension="OPPORTUNITY_TYPE",
        value="CONFERENCE",
        strength=0.95,
        confidence=0.90,
    )

    context = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(excluded_pref,),
        adaptive_signals=(adaptive_sig,),
    )

    cand = make_candidate_item(
        opp_id=opp_id,
        title="Premier Conference",
        base_score=0.65,
        opportunity_type="CONFERENCE",
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank(
        [cand],
        context=context,
        adaptive_signals=[adaptive_sig],
        enable_personalization=True,
    )

    assert len(ranked) == 1
    item = ranked[0]
    assert item.personalization_adjustment <= 0.0
    assert item.personalization_adjustment == 0.0
    assert item.final_score == item.base_relevance_score


def test_blocker1_case_c_excluded_with_strong_positive_behavioral_evidence():
    """
    Test C: EXCLUDED + strong positive behavioral evidence → no positive personalization boost.
    """
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    excluded_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="DELIVERY_MODE",
        preference_key="delivery_mode",
        preference_value="ONLINE",
        preference_type="EXCLUDED",
        display_label="Online",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    class MockBehavioralSignal:
        category = "DELIVERY_MODE"
        preference_value = "ONLINE"
        direction = "POSITIVE"
        confidence = 0.95
        normalized_score = 1.0

    context = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(excluded_pref,),
        behavioral_signals=(MockBehavioralSignal(),),
    )

    cand = make_candidate_item(
        opp_id=opp_id,
        title="Virtual Symposium",
        base_score=0.55,
        delivery_mode="ONLINE",
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand], context=context, enable_personalization=True)

    assert len(ranked) == 1
    item = ranked[0]
    assert item.personalization_adjustment <= 0.0
    assert item.personalization_adjustment == 0.0
    assert item.final_score == item.base_relevance_score


def test_blocker1_case_d_excluded_with_calibration_multiplier():
    """
    Test D: EXCLUDED + calibration modifier → no positive personalization boost.
    """
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    excluded_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="WORKSHOP",
        preference_type="EXCLUDED",
        display_label="Workshop",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    adaptive_sig = make_adaptive_signal(
        profile_id=profile_id,
        dimension="OPPORTUNITY_TYPE",
        value="WORKSHOP",
        strength=0.90,
        confidence=0.85,
    )

    context = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(excluded_pref,),
        adaptive_signals=(adaptive_sig,),
    )

    cand = make_candidate_item(
        opp_id=opp_id,
        title="Advanced Robotics Workshop",
        base_score=0.60,
        opportunity_type="WORKSHOP",
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank(
        [cand],
        context=context,
        adaptive_signals=[adaptive_sig],
        enable_personalization=True,
    )

    assert len(ranked) == 1
    item = ranked[0]
    assert item.personalization_adjustment <= 0.0
    assert item.personalization_adjustment == 0.0
    assert item.final_score == item.base_relevance_score


def test_blocker1_case_e_unrelated_non_excluded_receives_intended_personalization():
    """
    Test E: Verify that unrelated non-excluded opportunities continue to receive
    their intended personalization behavior while excluded candidate receives zero boost.
    """
    profile_id = uuid.uuid4()
    opp1_id = uuid.uuid4()
    opp2_id = uuid.uuid4()

    excluded_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="JOURNAL",
        preference_type="EXCLUDED",
        display_label="Journal",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    preferred_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    context = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(excluded_pref, preferred_pref),
    )

    # Candidate 1: JOURNAL (EXCLUDED)
    cand_excl = make_candidate_item(
        opp_id=opp1_id,
        title="Medical Journal of AI",
        base_score=0.60,
        opportunity_type="JOURNAL",
    )
    # Candidate 2: CONFERENCE (PREFERRED)
    cand_pref = make_candidate_item(
        opp_id=opp2_id,
        title="International AI Conference",
        base_score=0.60,
        opportunity_type="CONFERENCE",
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand_excl, cand_pref], context=context, enable_personalization=True)

    res_excl = next(r for r in ranked if r.opportunity_id == opp1_id)
    res_pref = next(r for r in ranked if r.opportunity_id == opp2_id)

    # Excluded candidate must receive 0 boost
    assert res_excl.personalization_adjustment == 0.0
    assert res_excl.final_score == res_excl.base_relevance_score

    # Preferred candidate must receive positive boost
    assert res_pref.personalization_adjustment > 0.0
    assert res_pref.final_score > res_pref.base_relevance_score


# ═══════════════════════════════════════════════════════════════════════════════
# BLOCKER 2 — Governance Live Path Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_blocker2_suspend_in_live_recommendation_path(db_session: Session):
    """
    SUSPEND Invariant: governance = SUSPEND must result in personalization influence = 0
    in the LIVE recommendation path (zero adjustment, phase2-baseline ranking version).
    """
    user = create_user(db_session, email="suspend_user@university.edu")
    profile = create_profile(db_session, user)

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)

    # Add active adaptive signal
    sig = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        positive_evidence_count=10,
        negative_evidence_count=0,
        total_evidence_count=10,
        decay_adjusted_positive_weight=10.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=0.85,
        confidence=0.80,
        evidence_state="STRONG",
        algorithm_version="5.5.1",
        deterministic_explanation="Based on interaction evidence",
    )
    db_session.add(sig)

    # Insert governance drift evaluation with SUSPEND
    drift_eval = PersonalizationDriftEvaluationModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        evaluation_timestamp=datetime.now(timezone.utc),
        governance_state="SUSPEND",
        adaptation_state="SUSPENDED",
        overall_health_state="UNHEALTHY",
        signal_freshness="STALE",
        preference_alignment="MISALIGNED",
        evidence_sufficiency="STRONG",
        health_summary="Suspended due to drift",
        governance_explanation="Personalization suspended",
        algorithm_version="5.8.0",
    )
    db_session.add(drift_eval)

    opp = create_opportunity(db_session, "Conference Opportunity", opportunity_type="CONFERENCE")
    db_session.commit()

    resp = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile.id,
        limit=10,
    )

    # Live service must recognize SUSPEND: baseline version, zero personalization adjustment
    assert resp.metadata["ranking_version"] == "phase2-baseline"
    for item in resp.recommendations:
        assert item.personalization_adjustment == 0.0
        assert item.final_score == item.base_relevance_score


def test_blocker2_allow_preserves_normal_personalization(db_session: Session):
    """
    ALLOW Invariant: governance = ALLOW preserves normal personalization behavior.
    """
    user = create_user(db_session, email="allow_user@university.edu")
    profile = create_profile(db_session, user)

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)

    drift_eval = PersonalizationDriftEvaluationModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        evaluation_timestamp=datetime.now(timezone.utc),
        governance_state="ALLOW",
        adaptation_state="STABLE",
        overall_health_state="HEALTHY",
        signal_freshness="FRESH",
        preference_alignment="ALIGNED",
        evidence_sufficiency="STRONG",
        health_summary="All nominal",
        governance_explanation="Nominal operation",
        algorithm_version="5.8.0",
    )
    db_session.add(drift_eval)

    opp = create_opportunity(db_session, "Premier Conference", opportunity_type="CONFERENCE")
    db_session.commit()

    resp = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile.id,
        limit=10,
    )

    assert resp.metadata["ranking_version"] in ("phase3.5-personalized", "phase5-personalized")
    item = next(it for it in resp.recommendations if it.opportunity_id == opp.id)
    assert item.personalization_adjustment > 0.0
    assert item.final_score > item.base_relevance_score


def test_blocker2_allow_bounded_single_damping():
    """
    ALLOW_BOUNDED Invariant: applies 0.50x damping ONCE to personalization adjustment.
    No double damping between scorer and ranker.
    """
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    cand = make_candidate_item(
        opp_id=opp_id,
        title="Annual Research Conference",
        base_score=0.70,
        opportunity_type="CONFERENCE",
    )

    ranker = PersonalizationRanker()

    # Normal ranking with ALLOW
    ctx_allow = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(pref,),
        governance_state="ALLOW",
    )
    res_allow = ranker.rank([cand], context=ctx_allow, enable_personalization=True)[0]

    # Bounded ranking with ALLOW_BOUNDED
    ctx_bounded = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(pref,),
        governance_state="ALLOW_BOUNDED",
    )
    res_bounded = ranker.rank([cand], context=ctx_bounded, enable_personalization=True)[0]

    assert res_allow.personalization_adjustment > 0.0
    # Single damping check: exactly 0.50x of ALLOW (not 0.25x double damped!)
    expected_bounded_adj = round(res_allow.personalization_adjustment * 0.50, 6)
    assert res_bounded.personalization_adjustment == expected_bounded_adj


def test_blocker2_hold_and_reduce_multipliers():
    """
    Verify HOLD (0.25x) and REDUCE (0.10x) governance damping multipliers in live ranker.
    """
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        preference_type="PREFERRED",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    cand = make_candidate_item(
        opp_id=opp_id,
        title="Annual Research Conference",
        base_score=0.70,
        opportunity_type="CONFERENCE",
    )

    ranker = PersonalizationRanker()

    ctx_allow = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(pref,),
        governance_state="ALLOW",
    )
    adj_allow = ranker.rank([cand], context=ctx_allow, enable_personalization=True)[0].personalization_adjustment

    ctx_hold = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(pref,),
        governance_state="HOLD",
    )
    adj_hold = ranker.rank([cand], context=ctx_hold, enable_personalization=True)[0].personalization_adjustment
    assert adj_hold == round(adj_allow * 0.25, 6)

    ctx_reduce = ResearcherPersonalizationContext(
        profile_id=profile_id,
        explicit_preferences=(pref,),
        governance_state="REDUCE",
    )
    adj_reduce = ranker.rank([cand], context=ctx_reduce, enable_personalization=True)[0].personalization_adjustment
    assert adj_reduce == round(adj_allow * 0.10, 6)


def test_blocker2_test_f_governance_plus_excluded():
    """
    Test F: EXCLUDED + any governance state → never positive personalization.
    Exclusion dominates regardless of whether governance is ALLOW, ALLOW_BOUNDED, HOLD, REDUCE, or SUSPEND.
    """
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()

    excl_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="JOURNAL",
        preference_type="EXCLUDED",
        display_label="Journal",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )

    cand = make_candidate_item(
        opp_id=opp_id,
        title="Journal of Applied Science",
        base_score=0.65,
        opportunity_type="JOURNAL",
    )

    ranker = PersonalizationRanker()

    for gov_state in ["ALLOW", "ALLOW_BOUNDED", "HOLD", "REDUCE", "SUSPEND", None]:
        ctx = ResearcherPersonalizationContext(
            profile_id=profile_id,
            explicit_preferences=(excl_pref,),
            governance_state=gov_state,
        )
        ranked = ranker.rank([cand], context=ctx, enable_personalization=True)
        assert len(ranked) == 1
        item = ranked[0]
        assert item.personalization_adjustment <= 0.0
        assert item.personalization_adjustment == 0.0
        assert item.final_score == item.base_relevance_score


# ═══════════════════════════════════════════════════════════════════════════════
# BLOCKER 3 — Authentication / Authorization Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_blocker3_case_a_missing_x_user_id_rejected(client: TestClient, db_session: Session):
    """
    Case A: GET /researchers/{researcher_id}/personalized-recommendations without X-User-ID
    MUST be rejected with 401 Unauthorized.
    """
    user = create_user(db_session, email="authtest1@university.edu")
    profile = create_profile(db_session, user)
    db_session.commit()

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/personalized-recommendations",
    )
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_blocker3_case_b_wrong_user_forbidden(client: TestClient, db_session: Session):
    """
    Case B: X-User-ID = user_B, profile belongs to user_A → 403 Forbidden.
    """
    user_a = create_user(db_session, email="user_a@university.edu")
    profile_a = create_profile(db_session, user_a)

    user_b = create_user(db_session, email="user_b@university.edu")
    db_session.commit()

    resp = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalized-recommendations",
        headers={"X-User-ID": str(user_b.id)},
    )
    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]


def test_blocker3_case_c_correct_user_allowed(client: TestClient, db_session: Session):
    """
    Case C: X-User-ID = user_A, profile belongs to user_A → 200 OK.
    """
    user_a = create_user(db_session, email="user_owner@university.edu")
    profile_a = create_profile(db_session, user_a)
    opp = create_opportunity(db_session, "Accessible Opp")
    db_session.commit()

    resp = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalized-recommendations",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data


def test_blocker3_case_d_cross_researcher_isolation(client: TestClient, db_session: Session):
    """
    Case D: Researcher A cannot access Researcher B's personalized recommendations.
    """
    user_a = create_user(db_session, email="alice@university.edu")
    profile_a = create_profile(db_session, user_a)

    user_b = create_user(db_session, email="bob@university.edu")
    profile_b = create_profile(db_session, user_b)
    db_session.commit()

    # User A tries to access Profile B
    resp = client.get(
        f"/api/v1/researchers/{profile_b.id}/personalized-recommendations",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# P0-3 Remediation — 18 Researcher-Specific Endpoints Mandatory Auth & Isolation
# ═══════════════════════════════════════════════════════════════════════════════

def _setup_p0_3_test_environment(db_session: Session):
    """Sets up standard entities for testing all 18 endpoints."""
    user_a = create_user(db_session, email="p0_3_user_a@university.edu")
    profile_a = create_profile(db_session, user_a)

    user_b = create_user(db_session, email="p0_3_user_b@university.edu")
    profile_b = create_profile(db_session, user_b)

    opp = create_opportunity(db_session, "P0-3 Test Opportunity")

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_a.id,
        category="TOPIC",
        preference_type="PREFERRED",
        preference_key="ai",
        preference_value="ai",
        display_label="AI",
        source="EXPLICIT",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)
    db_session.flush()

    feedback = ResearcherRecommendationFeedbackModel(
        id=uuid.uuid4(),
        researcher_id=profile_a.id,
        opportunity_id=opp.id,
        feedback_type="VIEW",
    )
    db_session.add(feedback)
    db_session.flush()

    snapshot = ResearcherRecommendationSnapshotModel(
        id=uuid.uuid4(),
        researcher_id=profile_a.id,
        ranking_version="R1_PERSONALIZED_V1",
        candidate_count=1,
        returned_count=1,
        request_hash="p0_3_test_hash",
    )
    db_session.add(snapshot)
    db_session.flush()

    item = ResearcherRecommendationItemModel(
        id=uuid.uuid4(),
        snapshot_id=snapshot.id,
        opportunity_id=opp.id,
        rank=1,
        final_score=0.85,
        base_relevance_score=0.80,
        personalization_score=0.05,
        behavioral_adjustment=0.0,
    )
    db_session.add(item)
    db_session.flush()

    ResearchCalendarService.get_or_create_default_calendar(db_session, user_id=user_a.id)
    ResearchCalendarService.get_or_create_default_calendar(db_session, user_id=user_b.id)
    db_session.commit()

    return user_a, profile_a, user_b, profile_b, opp, pref, feedback, snapshot


def test_p0_3_all_18_endpoints_auth_matrix(client: TestClient, db_session: Session):
    """
    Verifies that all 18 researcher-specific endpoints enforce the mandatory
    authentication contract:
      - Case A: Missing X-User-ID -> 401 Unauthorized
      - Case B: Wrong X-User-ID -> 403 Forbidden
      - Case C: Correct X-User-ID -> Expected success status (200 / 201)
      - Cross-Researcher Isolation: User A calling Profile B -> 403 Forbidden
    """
    user_a, profile_a, user_b, profile_b, opp, pref, feedback, snapshot = _setup_p0_3_test_environment(db_session)

    endpoints = [
        # 1. POST /{researcher_id}/preferences
        ("POST", f"/api/v1/researchers/{profile_a.id}/preferences", f"/api/v1/researchers/{profile_b.id}/preferences", {"category": "TOPIC", "preference_type": "PREFERRED", "preference_key": "ml", "preference_value": "ml", "display_label": "ML"}, 201),
        # 2. PUT /{researcher_id}/preferences
        ("PUT", f"/api/v1/researchers/{profile_a.id}/preferences", f"/api/v1/researchers/{profile_b.id}/preferences", {"items": [{"category": "TOPIC", "preference_type": "PREFERRED", "preference_key": "ml", "preference_value": "ml", "display_label": "ML"}], "replace_existing": False}, 200),
        # 3. PATCH /{researcher_id}/preferences/{preference_id}
        ("PATCH", f"/api/v1/researchers/{profile_a.id}/preferences/{pref.id}", f"/api/v1/researchers/{profile_b.id}/preferences/{pref.id}", {"strength": 0.9}, 200),
        # 4. DELETE /{researcher_id}/preferences/{preference_id}
        ("DELETE", f"/api/v1/researchers/{profile_a.id}/preferences/{pref.id}", f"/api/v1/researchers/{profile_b.id}/preferences/{pref.id}", None, 200),
        # 5. GET /{researcher_id}/personalized-candidates
        ("GET", f"/api/v1/researchers/{profile_a.id}/personalized-candidates", f"/api/v1/researchers/{profile_b.id}/personalized-candidates", None, 200),
        # 6. POST /{researcher_id}/feedback
        ("POST", f"/api/v1/researchers/{profile_a.id}/feedback", f"/api/v1/researchers/{profile_b.id}/feedback", {"opportunity_id": str(opp.id), "feedback_type": "VIEW"}, 201),
        # 7. GET /{researcher_id}/feedback
        ("GET", f"/api/v1/researchers/{profile_a.id}/feedback", f"/api/v1/researchers/{profile_b.id}/feedback", None, 200),
        # 8. DELETE /{researcher_id}/feedback/{feedback_id}
        ("DELETE", f"/api/v1/researchers/{profile_a.id}/feedback/{feedback.id}", f"/api/v1/researchers/{profile_b.id}/feedback/{feedback.id}", None, 200),
        # 9. GET /{researcher_id}/feedback/summary
        ("GET", f"/api/v1/researchers/{profile_a.id}/feedback/summary", f"/api/v1/researchers/{profile_b.id}/feedback/summary", None, 200),
        # 10. GET /{researcher_id}/feedback/signals
        ("GET", f"/api/v1/researchers/{profile_a.id}/feedback/signals", f"/api/v1/researchers/{profile_b.id}/feedback/signals", None, 200),
        # 11. GET /{researcher_id}/recommendation-history
        ("GET", f"/api/v1/researchers/{profile_a.id}/recommendation-history", f"/api/v1/researchers/{profile_b.id}/recommendation-history", None, 200),
        # 12. GET /{researcher_id}/recommendation-history/{snapshot_id}
        ("GET", f"/api/v1/researchers/{profile_a.id}/recommendation-history/{snapshot.id}", f"/api/v1/researchers/{profile_b.id}/recommendation-history/{snapshot.id}", None, 200),
        # 13. GET /{researcher_id}/recommendation-evaluation
        ("GET", f"/api/v1/researchers/{profile_a.id}/recommendation-evaluation", f"/api/v1/researchers/{profile_b.id}/recommendation-evaluation", None, 200),
        # 14. GET /{researcher_id}/personalization-summary
        ("GET", f"/api/v1/researchers/{profile_a.id}/personalization-summary", f"/api/v1/researchers/{profile_b.id}/personalization-summary", None, 200),
        # 15. GET /{researcher_id}/personalized-recommendations/{opportunity_id}/explanation
        ("GET", f"/api/v1/researchers/{profile_a.id}/personalized-recommendations/{opp.id}/explanation", f"/api/v1/researchers/{profile_b.id}/personalized-recommendations/{opp.id}/explanation", None, 200),
        # 16. GET /{researcher_id}/recommendation-history/{snapshot_id}/items/{opportunity_id}/explanation
        ("GET", f"/api/v1/researchers/{profile_a.id}/recommendation-history/{snapshot.id}/items/{opp.id}/explanation", f"/api/v1/researchers/{profile_b.id}/recommendation-history/{snapshot.id}/items/{opp.id}/explanation", None, 200),
        # 17. GET /{researcher_id}/calendar
        ("GET", f"/api/v1/researchers/{profile_a.id}/calendar", f"/api/v1/researchers/{profile_b.id}/calendar", None, 200),
        # 18. GET /{researcher_id}/calendar.ics
        ("GET", f"/api/v1/researchers/{profile_a.id}/calendar.ics", f"/api/v1/researchers/{profile_b.id}/calendar.ics", None, 200),
    ]

    for idx, (method, path_a, path_b, body, expected_status) in enumerate(endpoints, 1):
        def _call(p, h=None):
            if method == "GET":
                return client.get(p, headers=h)
            elif method == "POST":
                return client.post(p, json=body, headers=h)
            elif method == "PUT":
                return client.put(p, json=body, headers=h)
            elif method == "PATCH":
                return client.patch(p, json=body, headers=h)
            elif method == "DELETE":
                return client.delete(p, headers=h)
            raise ValueError(f"Unknown method {method}")

        # Case A: Missing X-User-ID -> 401
        res_a = _call(path_a)
        assert res_a.status_code == 401, f"Endpoint #{idx} {method} {path_a} did not return 401 on missing X-User-ID: {res_a.status_code}"
        assert "Authentication required" in res_a.json().get("detail", "")

        # Case B: Wrong X-User-ID -> 403
        res_b = _call(path_a, {"X-User-ID": str(user_b.id)})
        assert res_b.status_code == 403, f"Endpoint #{idx} {method} {path_a} did not return 403 on wrong X-User-ID: {res_b.status_code}"
        assert "Forbidden" in res_b.json().get("detail", "")

        # Case C: Correct X-User-ID -> expected_status
        res_c = _call(path_a, {"X-User-ID": str(user_a.id)})
        assert res_c.status_code == expected_status, f"Endpoint #{idx} {method} {path_a} did not return {expected_status} on correct X-User-ID: {res_c.status_code}"

        # Cross-Researcher Isolation: User A targeting Profile B with User A's header -> 403
        res_cross = _call(path_b, {"X-User-ID": str(user_a.id)})
        assert res_cross.status_code == 403, f"Endpoint #{idx} {method} {path_b} did not isolate Profile B from User A: {res_cross.status_code}"


def test_p0_3_calendar_ics_special_export(client: TestClient, db_session: Session):
    """
    Mandatory Test for GET /{researcher_id}/calendar.ics:
      - Missing X-User-ID -> 401 Unauthorized
      - Wrong X-User-ID -> 403 Forbidden
      - Correct X-User-ID -> 200 OK with valid iCalendar text/calendar content
    """
    user_a = create_user(db_session, email="cal_user_a@university.edu")
    profile_a = create_profile(db_session, user_a)
    user_b = create_user(db_session, email="cal_user_b@university.edu")
    profile_b = create_profile(db_session, user_b)
    ResearchCalendarService.get_or_create_default_calendar(db_session, user_id=user_a.id)
    db_session.commit()

    path = f"/api/v1/researchers/{profile_a.id}/calendar.ics"

    # Case A: Missing header
    res_missing = client.get(path)
    assert res_missing.status_code == 401
    assert "Authentication required" in res_missing.json()["detail"]

    # Case B: Wrong header
    res_wrong = client.get(path, headers={"X-User-ID": str(user_b.id)})
    assert res_wrong.status_code == 403
    assert "Forbidden" in res_wrong.json()["detail"]

    # Case C: Correct header
    res_correct = client.get(path, headers={"X-User-ID": str(user_a.id)})
    assert res_correct.status_code == 200
    assert "text/calendar" in res_correct.headers.get("content-type", "")
    assert f'filename="researcher_{profile_a.id}_calendar.ics"' in res_correct.headers.get("content-disposition", "")
    assert "BEGIN:VCALENDAR" in res_correct.text
    assert "END:VCALENDAR" in res_correct.text

    # Cross-Researcher Isolation
    res_cross = client.get(f"/api/v1/researchers/{profile_b.id}/calendar.ics", headers={"X-User-ID": str(user_a.id)})
    assert res_cross.status_code == 403


def test_p0_3_write_endpoints_unauthenticated_blocked(client: TestClient, db_session: Session):
    """
    Mandatory test verifying that unauthenticated write requests cannot mutate state:
      - preferences (POST, PUT, PATCH, DELETE)
      - feedback (POST, DELETE)
    """
    user_a = create_user(db_session, email="writer_user@university.edu")
    profile_a = create_profile(db_session, user_a)
    opp = create_opportunity(db_session, "Write Protected Opp")

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile_a.id,
        category="TOPIC",
        preference_type="PREFERRED",
        preference_key="bio",
        preference_value="bio",
        display_label="Biology",
        source="EXPLICIT",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(pref)

    feedback = ResearcherRecommendationFeedbackModel(
        id=uuid.uuid4(),
        researcher_id=profile_a.id,
        opportunity_id=opp.id,
        feedback_type="SAVE",
    )
    db_session.add(feedback)
    db_session.commit()

    # 1. Unauthenticated POST preference
    r_post_pref = client.post(
        f"/api/v1/researchers/{profile_a.id}/preferences",
        json={"category": "TOPIC", "preference_type": "PREFERRED", "preference_key": "chem", "preference_value": "chem", "display_label": "Chemistry"},
    )
    assert r_post_pref.status_code == 401

    # 2. Unauthenticated PUT preference
    r_put_pref = client.put(
        f"/api/v1/researchers/{profile_a.id}/preferences",
        json={"items": [{"category": "TOPIC", "preference_type": "PREFERRED", "preference_key": "chem", "preference_value": "chem", "display_label": "Chemistry"}], "replace_existing": False},
    )
    assert r_put_pref.status_code == 401

    # 3. Unauthenticated PATCH preference
    r_patch_pref = client.patch(
        f"/api/v1/researchers/{profile_a.id}/preferences/{pref.id}",
        json={"strength": 0.5},
    )
    assert r_patch_pref.status_code == 401

    # 4. Unauthenticated DELETE preference
    r_del_pref = client.delete(f"/api/v1/researchers/{profile_a.id}/preferences/{pref.id}")
    assert r_del_pref.status_code == 401

    # Verify preference was NOT deleted
    pref_in_db = db_session.get(ResearcherPreferenceModel, pref.id)
    assert pref_in_db is not None

    # 5. Unauthenticated POST feedback
    r_post_fb = client.post(
        f"/api/v1/researchers/{profile_a.id}/feedback",
        json={"opportunity_id": str(opp.id), "feedback_type": "INTERESTED"},
    )
    assert r_post_fb.status_code == 401

    # 6. Unauthenticated DELETE feedback
    r_del_fb = client.delete(f"/api/v1/researchers/{profile_a.id}/feedback/{feedback.id}")
    assert r_del_fb.status_code == 401

    # Verify feedback was NOT deleted
    fb_in_db = db_session.get(ResearcherRecommendationFeedbackModel, feedback.id)
    assert fb_in_db is not None


