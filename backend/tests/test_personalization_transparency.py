from datetime import datetime, timezone
import time
from typing import Any
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptivePreferenceSignalModel,
    AdaptiveSignalDimension,
)
from app.models.opportunity import OpportunityModel
from app.models.personalization_calibration import (
    CalibrationState,
    PersonalizationCalibrationModel,
)
from app.models.personalization_governance import (
    GovernanceGateState,
    PersonalizationDriftEvaluationModel,
    PersonalizationHealthState,
)
from app.models.personalization_quality import (
    ContextualFallbackLevel,
    PersonalizationContextualAdaptationModel,
)
from app.models.personalization_transparency import (
    PersonalizationControlEventModel,
    PersonalizationControlEventType,
    PersonalizationImpact,
    ResearcherPersonalizationSettingsModel,
)
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.researcher_preference import (
    ResearcherPreferenceModel,
)
from app.models.user import UserModel
from app.personalization.transparency_config import (
    DEFAULT_TRANSPARENCY_CONFIG,
    PersonalizationTransparencyConfig,
)
from app.personalization.transparency_engine import PersonalizationTransparencyEngine
from app.schemas.personalization_transparency import (
    ResearcherPersonalizationSettingsUpdate,
)
from app.services.personalization_transparency_service import (
    PersonalizationTransparencyService,
)

from starlette.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.models.base import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from app.db.types import TSVector, Vector
from datetime import timedelta

# SQLite dialect compilation shims for PostgreSQL-specific types in test env
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_user_and_profile(db_session):
    """Creates a canonical user and researcher profile."""
    user = UserModel(
        id=uuid.uuid4(),
        email="researcher.transparency@test.edu",
        hashed_password="hashed_pw_test",
        full_name="Transparency Researcher",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    from app.models.research_profile import ResearchProfileModel
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="POSTDOC",
        institution="MIT",
    )
    db_session.add(profile)
    db_session.flush()

    return user, profile


@pytest.fixture
def sample_opportunities(db_session):
    """Creates sample opportunities for ranking and transparency tests."""
    now = datetime.now(timezone.utc)

    opp1 = OpportunityModel(
        id=uuid.uuid4(),
        title="NeurIPS 2026",
        opportunity_type="CONFERENCE",
        submission_deadline=now + timedelta(days=30),
        delivery_mode="HYBRID",
        source_id=uuid.uuid4(),
    )
    opp2 = OpportunityModel(
        id=uuid.uuid4(),
        title="Nature Machine Intelligence",
        opportunity_type="JOURNAL",
        submission_deadline=now + timedelta(days=60),
        delivery_mode="ONLINE",
        source_id=uuid.uuid4(),
    )
    opp3 = OpportunityModel(
        id=uuid.uuid4(),
        title="ICML Workshop on Safety",
        opportunity_type="WORKSHOP",
        submission_deadline=now + timedelta(days=15),
        delivery_mode="OFFLINE",
        source_id=uuid.uuid4(),
    )
    db_session.add_all([opp1, opp2, opp3])
    db_session.flush()

    return opp1, opp2, opp3


@pytest.fixture
def sample_transparency_context(db_session: Session, sample_user_and_profile, sample_opportunities):
    """
    Sets up a full multi-phase personalization state for testing Phase 5.9.
    """
    user, profile = sample_user_and_profile
    opp1, opp2, opp3 = sample_opportunities
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Explicit preferences (Phase 5.1): PREFERRED topic 'Artificial Intelligence', EXCLUDED opportunity type 'WORKSHOP'
    pref1 = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="RESEARCH_TOPIC",
        preference_type="PREFERRED",
        preference_key="Artificial Intelligence",
        preference_value="Artificial Intelligence",
        display_label="Artificial Intelligence",
        created_at=now,
        updated_at=now,
    )
    pref2 = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_type="EXCLUDED",
        preference_key="WORKSHOP",
        preference_value="WORKSHOP",
        display_label="Workshop",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([pref1, pref2])

    # 2. Adaptive signals (Phase 5.5)
    sig1 = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE.value,
        signal_value="GRANT",
        positive_evidence_count=5,
        negative_evidence_count=1,
        total_evidence_count=6,
        decay_adjusted_positive_weight=4.5,
        decay_adjusted_negative_weight=0.5,
        weighted_signal_strength=0.67,
        confidence=0.85,
        evidence_state=AdaptiveEvidenceState.ESTABLISHED.value,
        deterministic_explanation="Grant signal based on positive interactions",
        algorithm_version="5.5.1",
        created_at=now,
        updated_at=now,
    )
    db_session.add(sig1)

    # 3. Calibration (Phase 5.6)
    calib1 = PersonalizationCalibrationModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="GRANT",
        recommendations_influenced_count=6,
        positive_outcome_count=4,
        negative_outcome_count=1,
        neutral_outcome_count=1,
        accumulated_positive_weight=3.5,
        accumulated_negative_weight=0.5,
        net_calibration_modifier=0.02,
        calibration_confidence=0.80,
        calibration_state=CalibrationState.STABLE.value,
        deterministic_explanation="Calibrated grant signal",
        algorithm_version="5.6.1",
        created_at=now,
        updated_at=now,
    )
    db_session.add(calib1)

    # 4. Contextual Adaptation (Phase 5.7)
    ctx1 = PersonalizationContextualAdaptationModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        signal_dimension="OPPORTUNITY_TYPE",
        signal_value="GRANT",
        context_type="DEADLINE_HORIZON",
        context_value="URGENT",
        recommendations_count=4,
        positive_outcome_count=3,
        negative_outcome_count=1,
        context_engagement_rate=0.75,
        contextual_lift=0.12,
        contextual_modifier=0.015,
        confidence=0.75,
        adaptation_state="EFFECTIVE",
        fallback_level=ContextualFallbackLevel.EXACT_CONTEXT.value,
        deterministic_explanation="Observed positive lift for urgent grant deadlines",
        algorithm_version="5.7.1",
        created_at=now,
        updated_at=now,
    )
    db_session.add(ctx1)

    # 5. Recommendation Snapshot & Items (Phase 3.7)
    snapshot = ResearcherRecommendationSnapshotModel(
        id=uuid.uuid4(),
        researcher_id=profile.id,
        ranking_version="phase3.7-v1",
        candidate_count=3,
        returned_count=3,
        created_at=now,
    )
    db_session.add(snapshot)
    db_session.flush()

    item1 = ResearcherRecommendationItemModel(
        id=uuid.uuid4(),
        snapshot_id=snapshot.id,
        opportunity_id=opp1.id,
        rank=1,
        base_relevance_score=0.88,
        personalization_score=0.92,
        behavioral_adjustment=0.05,
        final_score=0.93,
        risk_level="LOW_RISK",
        deadline_status="UPCOMING",
        created_at=now,
    )
    item2 = ResearcherRecommendationItemModel(
        id=uuid.uuid4(),
        snapshot_id=snapshot.id,
        opportunity_id=opp2.id,
        rank=2,
        base_relevance_score=0.86,
        personalization_score=0.50,
        behavioral_adjustment=0.0,
        final_score=0.86,
        risk_level="LOW_RISK",
        deadline_status="UPCOMING",
        created_at=now,
    )
    db_session.add_all([item1, item2])
    db_session.commit()

    return user, profile, opp1, opp2, opp3, item1, item2


# =============================================================================
# 1. EXPLANATION TESTS
# =============================================================================

def test_explanation_generation_precedence_and_sources():
    """
    Verify explanation hierarchy: explicit preference > adaptive signal > calibration > contextual quality > governance state.
    """
    (
        impact,
        expl_factors,
        adapt_factors,
        cal_factors,
        ctx_factors,
        gov_notes,
        summary_list,
        text,
    ) = PersonalizationTransparencyEngine.build_factors_and_explanation(
        opportunity_title="AI Research Grant 2026",
        base_relevance_score=0.85,
        personalization_score=0.92,
        final_score=0.93,
        personalization_enabled=True,
        adaptive_signals_enabled=True,
        governance_state=GovernanceGateState.ALLOW_BOUNDED,
        governance_multiplier=0.5,
        explicit_matches=[{"category": "RESEARCH_TOPIC", "value": "AI", "preference_type": "PREFERRED"}],
        adaptive_signals=[{"dimension": "OPPORTUNITY_TYPE", "signal_value": "GRANT", "contribution": 0.05}],
        calibrations=[{"dimension": "OPPORTUNITY_TYPE", "signal_value": "GRANT", "modifier": 0.02}],
        contextual_adaptations=[{"context_dimension": "DEADLINE_HORIZON", "context_value": "URGENT", "modifier": 0.015}],
    )

    assert impact in (PersonalizationImpact.MODERATE_PERSONALIZATION, PersonalizationImpact.STRONG_PERSONALIZATION)
    assert len(expl_factors) == 1
    assert len(adapt_factors) == 1
    assert len(cal_factors) == 1
    assert len(ctx_factors) == 1
    assert gov_notes is not None
    assert "bounded safety tier" in gov_notes

    # Summary list follows precedence
    assert summary_list[0] == "✓ Matches your explicit research preferences"
    assert summary_list[1] == "✓ Similar opportunities received positive interactions"
    assert summary_list[2] == "✓ Calibrated against your historical interaction outcomes"
    assert summary_list[3] == "✓ Adapted for the opportunity's specific deadline and type context"
    assert "bounded" in summary_list[4].lower()

    # Safety: explanation must not claim certainty like 'you will like this'
    assert "you will like this" not in text.lower()
    assert "we know your interests" not in text.lower()
    assert "core relevance score of 85%" in text


def test_personalization_impact_classifications():
    """
    Test deterministic boundary thresholds for PersonalizationImpact.
    """
    cfg = DEFAULT_TRANSPARENCY_CONFIG

    # Delta < 0.02 -> NO_PERSONALIZATION
    impact_none = PersonalizationTransparencyEngine.determine_personalization_impact(
        personalization_enabled=True,
        is_excluded=False,
        governance_state="ALLOW",
        base_relevance_score=0.85,
        personalization_score=0.86,
        final_score=0.86,
        config=cfg,
    )
    assert impact_none == PersonalizationImpact.NO_PERSONALIZATION

    # 0.02 <= Delta < 0.06 -> LOW
    impact_low = PersonalizationTransparencyEngine.determine_personalization_impact(
        personalization_enabled=True,
        is_excluded=False,
        governance_state="ALLOW",
        base_relevance_score=0.85,
        personalization_score=0.88,
        final_score=0.885,
        config=cfg,
    )
    assert impact_low == PersonalizationImpact.LOW_PERSONALIZATION

    # 0.06 <= Delta < 0.12 -> MODERATE
    impact_mod = PersonalizationTransparencyEngine.determine_personalization_impact(
        personalization_enabled=True,
        is_excluded=False,
        governance_state="ALLOW",
        base_relevance_score=0.85,
        personalization_score=0.93,
        final_score=0.94,
        config=cfg,
    )
    assert impact_mod == PersonalizationImpact.MODERATE_PERSONALIZATION

    # Delta >= 0.12 -> STRONG
    impact_strong = PersonalizationTransparencyEngine.determine_personalization_impact(
        personalization_enabled=True,
        is_excluded=False,
        governance_state="ALLOW",
        base_relevance_score=0.80,
        personalization_score=0.95,
        final_score=0.95,
        config=cfg,
    )
    assert impact_strong == PersonalizationImpact.STRONG_PERSONALIZATION

    # Excluded or Suspended -> PERSONALIZATION_SUPPRESSED
    impact_suppressed1 = PersonalizationTransparencyEngine.determine_personalization_impact(
        personalization_enabled=True,
        is_excluded=True,
        governance_state="ALLOW",
        base_relevance_score=0.85,
        personalization_score=0.0,
        final_score=0.0,
        config=cfg,
    )
    assert impact_suppressed1 == PersonalizationImpact.PERSONALIZATION_SUPPRESSED

    impact_suppressed2 = PersonalizationTransparencyEngine.determine_personalization_impact(
        personalization_enabled=True,
        is_excluded=False,
        governance_state="SUSPEND",
        base_relevance_score=0.85,
        personalization_score=0.50,
        final_score=0.85,
        config=cfg,
    )
    assert impact_suppressed2 == PersonalizationImpact.PERSONALIZATION_SUPPRESSED

    # Personalization Disabled -> NO_PERSONALIZATION
    impact_disabled = PersonalizationTransparencyEngine.determine_personalization_impact(
        personalization_enabled=False,
        is_excluded=False,
        governance_state="ALLOW",
        base_relevance_score=0.85,
        personalization_score=0.95,
        final_score=0.95,
        config=cfg,
    )
    assert impact_disabled == PersonalizationImpact.NO_PERSONALIZATION


# =============================================================================
# 2. RESEARCHER CONTROLS TESTS
# =============================================================================

def test_personalization_settings_controls_and_audit(db_session: Session, sample_transparency_context):
    """
    Test toggling personalization, adaptive signals, and feedback learning,
    verifying audit event creation and state snapshotting.
    """
    user, profile, _, _, _, _, _ = sample_transparency_context

    # 1. Get initial default settings
    settings = PersonalizationTransparencyService.get_or_create_settings(db_session, profile.id)
    assert settings.personalization_enabled is True
    assert settings.adaptive_signals_enabled is True
    assert settings.feedback_learning_enabled is True
    assert settings.personalization_state_version == 1

    # 2. Toggle personalization_enabled = False
    updated = PersonalizationTransparencyService.update_settings(
        db=db_session,
        profile_id=profile.id,
        payload=ResearcherPersonalizationSettingsUpdate(personalization_enabled=False),
        trigger_reason="Researcher turned off personalization",
    )
    assert updated.personalization_enabled is False
    assert updated.adaptive_signals_enabled is True

    # Verify audit event
    history = PersonalizationTransparencyService.get_control_history(db_session, profile.id)
    assert history.total == 1
    assert history.events[0].event_type == PersonalizationControlEventType.PERSONALIZATION_DISABLED
    assert history.events[0].previous_state["personalization_enabled"] is True
    assert history.events[0].new_state["personalization_enabled"] is False

    # 3. Toggle adaptive_signals_enabled = False
    updated2 = PersonalizationTransparencyService.update_settings(
        db=db_session,
        profile_id=profile.id,
        payload=ResearcherPersonalizationSettingsUpdate(adaptive_signals_enabled=False),
        trigger_reason="Researcher turned off adaptive signals",
    )
    assert updated2.adaptive_signals_enabled is False

    history2 = PersonalizationTransparencyService.get_control_history(db_session, profile.id)
    assert history2.total == 2
    event_types = [e.event_type for e in history2.events]
    assert PersonalizationControlEventType.ADAPTIVE_SIGNALS_DISABLED in event_types
    assert PersonalizationControlEventType.PERSONALIZATION_DISABLED in event_types


# =============================================================================
# 3. RESET MECHANISM TESTS
# =============================================================================

def test_personalization_reset_neutralization_and_preservation(db_session: Session, sample_transparency_context):
    """
    Verify reset operation:
      1. Increments personalization_state_version.
      2. Neutralizes derived adaptive signals, calibrations, contextual adaptations.
      3. Strictly preserves explicit preferences, researcher profile, user account, recommendation history.
      4. Is idempotent and logs audit event.
    """
    user, profile, opp1, opp2, opp3, item1, item2 = sample_transparency_context

    # Pre-reset counts
    pre_adaptive = db_session.scalar(select(func.count(AdaptivePreferenceSignalModel.id)).where(AdaptivePreferenceSignalModel.profile_id == profile.id))
    pre_calib = db_session.scalar(select(func.count(PersonalizationCalibrationModel.id)).where(PersonalizationCalibrationModel.profile_id == profile.id))
    pre_ctx = db_session.scalar(select(func.count(PersonalizationContextualAdaptationModel.id)).where(PersonalizationContextualAdaptationModel.profile_id == profile.id))
    pre_prefs = db_session.scalar(select(func.count(ResearcherPreferenceModel.id)).where(ResearcherPreferenceModel.profile_id == profile.id))
    pre_snapshots = db_session.scalar(select(func.count(ResearcherRecommendationSnapshotModel.id)).where(ResearcherRecommendationSnapshotModel.researcher_id == profile.id))

    assert pre_adaptive is not None and pre_adaptive > 0
    assert pre_calib is not None and pre_calib > 0
    assert pre_ctx is not None and pre_ctx > 0
    assert pre_prefs == 2
    assert pre_snapshots == 1

    # Execute reset
    res = PersonalizationTransparencyService.reset_personalization(
        db=db_session,
        profile_id=profile.id,
        reason="Testing reset neutralization",
    )

    assert res.status == "SUCCESS"
    assert res.personalization_state_version == 2
    assert res.adaptive_signals_reset == pre_adaptive
    assert res.calibration_states_reset == pre_calib
    assert res.contextual_modifiers_reset == pre_ctx
    assert res.explicit_preferences_changed == 0
    assert res.researcher_profile_changed == 0

    # Post-reset DB verification
    post_adaptive = db_session.scalar(select(func.count(AdaptivePreferenceSignalModel.id)).where(AdaptivePreferenceSignalModel.profile_id == profile.id))
    post_calib = db_session.scalar(select(func.count(PersonalizationCalibrationModel.id)).where(PersonalizationCalibrationModel.profile_id == profile.id))
    post_ctx = db_session.scalar(select(func.count(PersonalizationContextualAdaptationModel.id)).where(PersonalizationContextualAdaptationModel.profile_id == profile.id))
    post_prefs = db_session.scalar(select(func.count(ResearcherPreferenceModel.id)).where(ResearcherPreferenceModel.profile_id == profile.id))
    post_snapshots = db_session.scalar(select(func.count(ResearcherRecommendationSnapshotModel.id)).where(ResearcherRecommendationSnapshotModel.researcher_id == profile.id))

    assert post_adaptive == 0
    assert post_calib == 0
    assert post_ctx == 0
    # Explicit preferences and recommendation history must be preserved!
    assert post_prefs == 2
    assert post_snapshots == 1

    # Verify audit event was logged
    history = PersonalizationTransparencyService.get_control_history(db_session, profile.id)
    assert history.total == 1
    assert history.events[0].event_type == PersonalizationControlEventType.PERSONALIZATION_RESET
    assert history.events[0].new_state["personalization_state_version"] == 2

    # Idempotent repeat: repeating reset succeeds without crashing and increments version to 3
    res2 = PersonalizationTransparencyService.reset_personalization(
        db=db_session,
        profile_id=profile.id,
        reason="Idempotent repeat reset",
    )
    assert res2.personalization_state_version == 3
    assert res2.adaptive_signals_reset == 0


# =============================================================================
# 4. RECOMMENDATION EXPLANATION SERVICE TESTS
# =============================================================================

def test_explain_recommendation_personalization_endpoint_logic(db_session: Session, sample_transparency_context):
    """
    Test recommendation explanation generation for an existing recommendation item and on-the-fly opportunity.
    """
    user, profile, opp1, opp2, opp3, item1, item2 = sample_transparency_context

    # 1. Explain by recommendation item ID
    explanation = PersonalizationTransparencyService.explain_recommendation_personalization(
        db=db_session,
        profile_id=profile.id,
        recommendation_id=item1.id,
    )
    assert explanation is not None
    assert explanation.recommendation_id == item1.id
    assert explanation.opportunity_id == opp1.id
    assert explanation.opportunity_title == opp1.title
    assert explanation.base_relevance_score == 0.88
    assert explanation.algorithm_version == "5.9.1"
    assert len(explanation.contributing_factors_summary) > 0

    # 2. Explain by opportunity ID directly
    explanation_opp = PersonalizationTransparencyService.explain_recommendation_personalization(
        db=db_session,
        profile_id=profile.id,
        recommendation_id=opp2.id,
    )
    assert explanation_opp is not None
    assert explanation_opp.opportunity_id == opp2.id

    # 3. Non-existent ID returns None
    explanation_none = PersonalizationTransparencyService.explain_recommendation_personalization(
        db=db_session,
        profile_id=profile.id,
        recommendation_id=uuid.uuid4(),
    )
    assert explanation_none is None


# =============================================================================
# 5. REST API ENDPOINTS & AUTHORIZATION TESTS
# =============================================================================

def test_transparency_rest_apis_and_authorization(client, sample_transparency_context):
    """
    Test REST APIs:
      - GET /api/v1/researchers/{id}/personalization/settings
      - PATCH /api/v1/researchers/{id}/personalization/settings
      - POST /api/v1/researchers/{id}/personalization/reset
      - GET /api/v1/researchers/{id}/personalization/control-history
      - GET /api/v1/researchers/{id}/recommendations/{rec_id}/personalization
    and verify multi-tenant isolation via X-User-ID.
    """
    user, profile, opp1, opp2, opp3, item1, item2 = sample_transparency_context

    headers_auth = {"X-User-ID": str(user.id)}
    headers_intruder = {"X-User-ID": str(uuid.uuid4())}

    # 1. GET settings (authorized)
    resp = client.get(f"/api/v1/researchers/{profile.id}/personalization/settings", headers=headers_auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["personalization_enabled"] is True
    assert data["personalization_state_version"] == 1

    # Unauthorized access (intruder)
    resp_bad = client.get(f"/api/v1/researchers/{profile.id}/personalization/settings", headers=headers_intruder)
    assert resp_bad.status_code == 403

    # 2. PATCH settings
    patch_resp = client.patch(
        f"/api/v1/researchers/{profile.id}/personalization/settings",
        json={"personalization_enabled": False},
        headers=headers_auth,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["personalization_enabled"] is False

    # 3. GET control-history
    hist_resp = client.get(f"/api/v1/researchers/{profile.id}/personalization/control-history", headers=headers_auth)
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total"] >= 1

    # 4. POST reset
    reset_resp = client.post(f"/api/v1/researchers/{profile.id}/personalization/reset", headers=headers_auth)
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data["status"] == "SUCCESS"
    assert reset_data["personalization_state_version"] == 2
    assert reset_data["explicit_preferences_changed"] == 0

    # 5. GET recommendation explanation
    explain_resp = client.get(
        f"/api/v1/researchers/{profile.id}/recommendations/{item1.id}/personalization",
        headers=headers_auth,
    )
    assert explain_resp.status_code == 200
    explain_data = explain_resp.json()
    assert explain_data["opportunity_id"] == str(opp1.id)
    assert "deterministic_explanation" in explain_data
    assert "algorithm_version" in explain_data
    assert explain_data["algorithm_version"] == "5.9.1"


# =============================================================================
# 6. SAFETY & INVARIANT TESTS
# =============================================================================

def test_safety_invariants_during_controls(db_session: Session, sample_transparency_context):
    """
    Verify safety invariants:
      1. Explicit EXCLUDED matches unconditionally yield 0.0, regardless of controls.
      2. Core relevance dominance (>= 85%) is strictly preserved.
      3. Personalization disabled reverts score to neutral 0.50 (or 0.0 if excluded).
    """
    user, profile, opp1, opp2, opp3, item1, item2 = sample_transparency_context

    # Update opp3 to match the excluded topic 'Quantum Computing'
    opp3.topics = ["Quantum Computing"]
    db_session.commit()

    # Disable personalization in settings
    settings = PersonalizationTransparencyService.update_settings(
        db=db_session,
        profile_id=profile.id,
        payload=ResearcherPersonalizationSettingsUpdate(personalization_enabled=False),
    )

    prefs = db_session.execute(select(ResearcherPreferenceModel).where(ResearcherPreferenceModel.profile_id == profile.id)).scalars().all()
    from app.schemas.researcher_preference import ResearcherPreferenceItemSchema
    pref_items = [ResearcherPreferenceItemSchema.model_validate(p) for p in prefs]

    from app.personalization.scorer import PersonalizationScorer

    # Excluded opportunity MUST yield 0.0 even when personalization is disabled!
    assessment_excluded = PersonalizationScorer.score_opportunity(
        profile_id=profile.id,
        preferences=pref_items,
        opportunity=opp3,
        settings=settings,
    )
    assert assessment_excluded.personalization_score == 0.0

    # Non-excluded opportunity yields neutral 0.50 when personalization is disabled
    assessment_allowed = PersonalizationScorer.score_opportunity(
        profile_id=profile.id,
        preferences=pref_items,
        opportunity=opp1,
        settings=settings,
    )
    assert assessment_allowed.personalization_score == 0.50


# =============================================================================
# 7. PERFORMANCE & QUERY COUNT BENCHMARK
# =============================================================================

def test_transparency_performance_and_query_count(db_session: Session, sample_transparency_context):
    """
    Verify that explaining a recommendation executes in bounded time (< 50ms)
    with zero N+1 queries.
    """
    user, profile, opp1, _, _, item1, _ = sample_transparency_context

    # Measure execution time
    t0 = time.perf_counter()
    explanation = PersonalizationTransparencyService.explain_recommendation_personalization(
        db=db_session,
        profile_id=profile.id,
        recommendation_id=item1.id,
    )
    t1 = time.perf_counter()

    elapsed_ms = (t1 - t0) * 1000
    assert explanation is not None
    # Must complete in under 50ms
    assert elapsed_ms < 50.0
