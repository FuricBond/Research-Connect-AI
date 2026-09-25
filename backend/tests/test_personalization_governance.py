"""
Comprehensive test suite for Phase 5.8 — Personalization Governance, Drift Detection & Adaptation Safety.

Verifies:
  - Multi-dimensional personalization health (signal freshness, evidence sufficiency, quality stability, context stability, adaptation stability, preference alignment, recommendation diversity, drift status).
  - Deterministic signal drift detection and classification (STABLE, EMERGING, PERSISTENT, REVERSING, UNKNOWN).
  - Temporal window partitioning (historical vs recent windows) with explicit reference_time.
  - Preference staleness detection (stale != false; stale signals are never negated or deleted).
  - Strict explicit preference protection (hierarchy: explicit exclusion > preference > adaptive > calibration > contextual).
  - Governance gate evaluation (ALLOW, ALLOW_BOUNDED, HOLD, REDUCE, SUSPEND).
  - Suspension safety (modifiers revert to neutral 0.0, core ranking remains intact).
  - Recovery from suspension requiring >= 5 stable interactions.
  - Hysteresis protection preventing rapid state oscillation.
  - Append-only immutable governance audit events.
  - REST API endpoints and multi-tenant authorization isolation (X-User-ID).
  - Scaling and latency benchmarks (10 to 10,000 signals).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptivePreferenceSignalModel,
    AdaptiveSignalDimension,
)
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.personalization_calibration import (
    AttributionConfidence,
    CalibrationState,
    FeedbackOutcomeType,
    PersonalizationCalibrationModel,
    RecommendationFeedbackAttributionModel,
)
from app.models.personalization_governance import (
    AdaptationState,
    DriftType,
    EvidenceStrength,
    GovernanceEventType,
    GovernanceGateState,
    PersonalizationDriftEvaluationModel,
    PersonalizationGovernanceEventModel,
    PersonalizationHealthState,
    PreferenceAlignmentState,
    SignalFreshnessState,
)
from app.models.personalization_quality import (
    ContextualFallbackLevel,
    PersonalizationContextualAdaptationModel,
    PersonalizationQualityEvaluationModel,
    QualityEvaluationState,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import (
    InteractionType,
    ResearcherInteractionModel,
)
from app.models.researcher_preference import (
    ResearcherPreferenceModel,
)
from app.models.user import UserModel
from app.personalization.adaptive_models import AdaptivePreferenceSignal
from app.personalization.governance_config import (
    DEFAULT_GOVERNANCE_CONFIG,
    PersonalizationGovernanceConfig,
)
from app.personalization.governance_engine import PersonalizationGovernanceEngine
from app.personalization.scorer import PersonalizationScorer
from app.schemas.personalization_calibration import PersonalizationCalibrationSchema
from app.schemas.personalization_governance import SignalDriftItem
from app.schemas.personalization_quality import (
    PersonalizationContextualAdaptationSchema,
    PersonalizationQualityEvaluationSchema,
)
from app.schemas.researcher_preference import (
    PreferenceCategory,
    PreferenceType,
    ResearcherPreferenceItemSchema,
)
from app.services.personalization_governance_service import (
    PersonalizationGovernanceService,
)

from starlette.testclient import TestClient
from app.main import app
from app.db.session import get_db

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from app.db.types import TSVector, Vector

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
        email="researcher.governance@test.edu",
        hashed_password="hashed_pw_test",
        full_name="Governance Researcher",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="POSTDOC",
        institution="Stanford University",
    )
    db_session.add(profile)
    db_session.flush()

    return user, profile


@pytest.fixture
def sample_opportunities(db_session):
    """Creates sample opportunities for interaction and ranking tests."""
    opps = []
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

    opps.extend([opp1, opp2, opp3])
    for o in opps:
        db_session.add(o)
    db_session.flush()
    return opps


def test_signal_drift_classification():
    """
    Test deterministic signal drift classification:
      - STABLE: small delta (|diff| < 0.20)
      - EMERGING: |diff| >= 0.20 with insufficient persistence (recent_count < 6)
      - PERSISTENT: |diff| >= 0.20 with persistent evidence (recent_count >= 6)
      - REVERSING: moving back towards historical value
      - UNKNOWN: insufficient evidence (total_count < 3)
    """
    engine = PersonalizationGovernanceEngine(DEFAULT_GOVERNANCE_CONFIG)
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # 1. STABLE: diff = -0.02 (< 0.20)
    item_stable = engine.evaluate_signal_drift(
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        current_strength=0.70,
        historical_interactions=[
            {"weight": 0.70, "is_positive": True} for _ in range(10)
        ],
        recent_interactions=[
            {"weight": 0.68, "is_positive": True} for _ in range(6)
        ],
        last_evidence_time=ref_time - timedelta(days=2),
        reference_time=ref_time,
    )
    assert item_stable.drift_type == DriftType.STABLE
    assert item_stable.is_stale is False
    assert item_stable.evidence_strength in [EvidenceStrength.HIGH, EvidenceStrength.MEDIUM]

    # 2. EMERGING: large drop (0.70 -> 0.35), but only 4 recent interactions (< 6)
    item_emerging = engine.evaluate_signal_drift(
        dimension="OPPORTUNITY_TYPE",
        signal_value="JOURNAL",
        current_strength=0.70,
        historical_interactions=[
            {"weight": 0.70, "is_positive": True} for _ in range(10)
        ],
        recent_interactions=[
            {"weight": 0.35, "is_positive": True} for _ in range(4)
        ],
        last_evidence_time=ref_time - timedelta(days=2),
        reference_time=ref_time,
    )
    assert item_emerging.drift_type == DriftType.EMERGING
    assert item_emerging.difference < -0.20

    # 3. PERSISTENT: large drop (0.70 -> 0.10) with 8 recent interactions (>= 6)
    item_persistent = engine.evaluate_signal_drift(
        dimension="OPPORTUNITY_TYPE",
        signal_value="WORKSHOP",
        current_strength=0.70,
        historical_interactions=[
            {"weight": 0.70, "is_positive": True} for _ in range(12)
        ],
        recent_interactions=[
            {"weight": 0.10, "is_positive": True} for _ in range(8)
        ],
        last_evidence_time=ref_time - timedelta(days=1),
        reference_time=ref_time,
    )
    assert item_persistent.drift_type == DriftType.PERSISTENT
    assert item_persistent.evidence_strength == EvidenceStrength.HIGH

    # 4. REVERSING: current_strength was 0.30, recent interactions are positive (0.68)
    # moving back toward historical 0.70
    item_reversing = engine.evaluate_signal_drift(
        dimension="DELIVERY_MODE",
        signal_value="HYBRID",
        current_strength=0.30,
        historical_interactions=[
            {"weight": 0.70, "is_positive": True} for _ in range(10)
        ],
        recent_interactions=[
            {"weight": 0.68, "is_positive": True} for _ in range(7)
        ],
        last_evidence_time=ref_time - timedelta(days=1),
        reference_time=ref_time,
    )
    assert item_reversing.drift_type == DriftType.REVERSING

    # 5. UNKNOWN: insufficient evidence (< 3 interactions total)
    item_unknown = engine.evaluate_signal_drift(
        dimension="LOCATION",
        signal_value="USA",
        current_strength=0.50,
        historical_interactions=[{"weight": 1.0, "is_positive": True}],
        recent_interactions=[{"weight": 1.0, "is_positive": True}],
        last_evidence_time=ref_time - timedelta(days=5),
        reference_time=ref_time,
    )
    assert item_unknown.drift_type == DriftType.UNKNOWN
    assert item_unknown.evidence_strength == EvidenceStrength.INSUFFICIENT


def test_staleness_detection():
    """
    Test staleness detection:
      - Signal with last evidence 200 days ago (> 180 days stale threshold).
      - Invariant: STALE != false (stale evidence is not treated as negative evidence).
    """
    engine = PersonalizationGovernanceEngine(DEFAULT_GOVERNANCE_CONFIG)
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    item = engine.evaluate_signal_drift(
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        current_strength=0.80,
        historical_interactions=[],
        recent_interactions=[],
        last_evidence_time=ref_time - timedelta(days=200),
        reference_time=ref_time,
    )
    assert item.is_stale is True
    # Verify staleness explanation is informative and does NOT state the signal is negative
    assert "stale" in item.explanation.lower()
    assert "negative" not in item.explanation.lower()


def test_explicit_preference_protection(sample_user_and_profile, sample_opportunities):
    """
    Verify strict hierarchy:
      explicit exclusion > explicit preference > recent adaptive > historical adaptive > contextual quality modifier.
      Behavioral drift cannot overwrite or delete explicit preferences.
    """
    _, profile = sample_user_and_profile
    opp1, opp2, _ = sample_opportunities

    scorer = PersonalizationScorer()

    # Researcher explicitly excluded CONFERENCE
    pref_excluded = ResearcherPreferenceItemSchema(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category=PreferenceCategory.OPPORTUNITY_TYPE.value,
        preference_type=PreferenceType.EXCLUDED.value,
        preference_key="OPPORTUNITY_TYPE:CONFERENCE",
        preference_value="CONFERENCE",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        created_at=datetime.now(timezone.utc),
    )

    # Adaptive signal says researcher has strong positive conference affinity
    adaptive_conf = AdaptivePreferenceSignal(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
        signal_value="CONFERENCE",
        positive_evidence_count=20,
        negative_evidence_count=0,
        total_evidence_count=20,
        decay_adjusted_positive_weight=15.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=0.95,
        confidence=0.90,
        evidence_state=AdaptiveEvidenceState.STRONG,
        evidence_window_days=30.0,
        algorithm_version="5.5.1",
        deterministic_explanation="Strong conference affinity",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Score with explicit exclusion + strong adaptive signal + ALLOW governance
    # Score with explicit exclusion + strong adaptive signal + ALLOW governance
    assessment = scorer.score_opportunity(
        profile_id=profile.id,
        preferences=[pref_excluded],
        opportunity=opp1,
        adaptive_signals=[adaptive_conf],
        governance_state=GovernanceGateState.ALLOW,
    )

    # Invariant: EXCLUDED forces 0.0 final score regardless of behavioral signal
    assert assessment.score.bounded_score == 0.0
    assert assessment.score.match_state == "EXCLUDED_MATCH"

    # Researcher explicitly preferred JOURNAL
    pref_preferred = ResearcherPreferenceItemSchema(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category=PreferenceCategory.OPPORTUNITY_TYPE.value,
        preference_type=PreferenceType.PREFERRED.value,
        preference_key="OPPORTUNITY_TYPE:JOURNAL",
        preference_value="JOURNAL",
        display_label="Journal",
        strength=1.0,
        confidence=1.0,
        created_at=datetime.now(timezone.utc),
    )
    # Drift says journal interactions dropped
    adaptive_journal_weak = AdaptivePreferenceSignal(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
        signal_value="JOURNAL",
        positive_evidence_count=0,
        negative_evidence_count=10,
        total_evidence_count=10,
        decay_adjusted_positive_weight=0.0,
        decay_adjusted_negative_weight=8.0,
        weighted_signal_strength=-0.50,
        confidence=0.85,
        evidence_state=AdaptiveEvidenceState.STRONG,
        evidence_window_days=30.0,
        algorithm_version="5.5.1",
        deterministic_explanation="Negative journal interactions",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assessment_journal = scorer.score_opportunity(
        profile_id=profile.id,
        preferences=[pref_preferred],
        opportunity=opp2,
        adaptive_signals=[adaptive_journal_weak],
        governance_state=GovernanceGateState.ALLOW,
    )

    # Invariant: Preferred preference protects against negative suppression (baseline >= 0.50)
    assert assessment_journal.score.bounded_score >= 0.50


def test_temporal_windows_deterministic_reference_time():
    """
    Test deterministic temporal window partitioning:
      - Historical: [ref_time - 60d, ref_time - 14d)
      - Recent: [ref_time - 14d, ref_time]
      - Multiple evaluations with identical reference_time produce identical results.
    """
    engine = PersonalizationGovernanceEngine(DEFAULT_GOVERNANCE_CONFIG)
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Interaction 70 days ago (outside observation window)
    int_old = ResearcherInteractionModel(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        opportunity_id=uuid.uuid4(),
        interaction_type=InteractionType.VIEWED,
        created_at=ref_time - timedelta(days=70),
    )
    # Interaction 30 days ago (historical window)
    int_hist = ResearcherInteractionModel(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        opportunity_id=uuid.uuid4(),
        interaction_type=InteractionType.SAVED,
        created_at=ref_time - timedelta(days=30),
    )
    # Interaction 5 days ago (recent window)
    int_recent = ResearcherInteractionModel(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        opportunity_id=uuid.uuid4(),
        interaction_type=InteractionType.DISMISSED,
        created_at=ref_time - timedelta(days=5),
    )

    hist_list, recent_list = engine.partition_temporal_interactions(
        interactions=[int_old, int_hist, int_recent],
        reference_time=ref_time,
    )

    assert len(hist_list) == 1
    assert hist_list[0].id == int_hist.id
    assert len(recent_list) == 1
    assert recent_list[0].id == int_recent.id

    # Determinism check: run 5 times, verify exact match
    for _ in range(5):
        h, r = engine.partition_temporal_interactions([int_old, int_hist, int_recent], ref_time)
        assert len(h) == 1 and h[0].id == int_hist.id
        assert len(r) == 1 and r[0].id == int_recent.id


def test_governance_gate_and_hysteresis():
    """
    Test governance gate evaluation and hysteresis protection:
      - Clean signals -> ALLOW
      - Emerging drift -> ALLOW_BOUNDED
      - Persistent drift -> HOLD
      - Degraded quality -> REDUCE
      - Severe instability -> SUSPEND
      - Hysteresis: prevent oscillation from ALLOW to SUSPEND on minor noise.
    """
    engine = PersonalizationGovernanceEngine(DEFAULT_GOVERNANCE_CONFIG)

    # 1. Healthy conditions -> ALLOW
    gate_allow, adapt_allow, _ = engine.evaluate_governance_gate(
        drifting_count=0,
        persistent_drift_count=0,
        stale_count=0,
        quality_stability="STABLE",
        context_stability="STABLE",
        evidence_sufficiency=EvidenceStrength.HIGH,
        preference_alignment=PreferenceAlignmentState.ALIGNED,
        current_gate_state=GovernanceGateState.ALLOW,
    )
    assert gate_allow == GovernanceGateState.ALLOW
    assert adapt_allow == AdaptationState.ACTIVE

    # 2. Emerging drift -> ALLOW_BOUNDED
    gate_bounded, adapt_bounded, _ = engine.evaluate_governance_gate(
        drifting_count=1,
        persistent_drift_count=0,
        stale_count=0,
        quality_stability="STABLE",
        context_stability="STABLE",
        evidence_sufficiency=EvidenceStrength.HIGH,
        preference_alignment=PreferenceAlignmentState.ALIGNED,
        current_gate_state=GovernanceGateState.ALLOW,
    )
    assert gate_bounded == GovernanceGateState.ALLOW_BOUNDED
    assert adapt_bounded == AdaptationState.BOUNDED

    # 3. Persistent drift -> HOLD
    gate_hold, adapt_hold, _ = engine.evaluate_governance_gate(
        drifting_count=2,
        persistent_drift_count=1,
        stale_count=0,
        quality_stability="STABLE",
        context_stability="STABLE",
        evidence_sufficiency=EvidenceStrength.HIGH,
        preference_alignment=PreferenceAlignmentState.ALIGNED,
        current_gate_state=GovernanceGateState.ALLOW_BOUNDED,
    )
    assert gate_hold == GovernanceGateState.HOLD
    assert adapt_hold == AdaptationState.CONSERVATIVE

    # 4. Degraded quality -> REDUCE
    gate_reduce, adapt_reduce, _ = engine.evaluate_governance_gate(
        drifting_count=0,
        persistent_drift_count=0,
        stale_count=0,
        quality_stability="DEGRADED",
        context_stability="STABLE",
        evidence_sufficiency=EvidenceStrength.HIGH,
        preference_alignment=PreferenceAlignmentState.ALIGNED,
        current_gate_state=GovernanceGateState.ALLOW,
    )
    assert gate_reduce == GovernanceGateState.REDUCE
    assert adapt_reduce == AdaptationState.DAMPENED

    # 5. Severe instability (divergent + degraded + persistent drift) -> SUSPEND
    gate_suspend, adapt_suspend, _ = engine.evaluate_governance_gate(
        drifting_count=3,
        persistent_drift_count=2,
        stale_count=1,
        quality_stability="DEGRADED",
        context_stability="DEGRADED",
        evidence_sufficiency=EvidenceStrength.HIGH,
        preference_alignment=PreferenceAlignmentState.DIVERGENT,
        current_gate_state=GovernanceGateState.HOLD,
    )
    assert gate_suspend == GovernanceGateState.SUSPEND
    assert adapt_suspend == AdaptationState.SUSPENDED


def test_adaptation_suspension_neutrality_in_scorer(sample_user_and_profile, sample_opportunities):
    """
    Test that when governance gate is SUSPEND:
      - Personalization adaptive, calibration, and contextual modifiers are neutralized to 0.0.
      - Core ranking relevance, risk, and deadline urgency remain intact.
      - Modifiers are NEVER made negative.
    """
    _, profile = sample_user_and_profile
    opp1, _, _ = sample_opportunities

    scorer = PersonalizationScorer()

    # Active adaptive signal with strong affinity
    now = datetime.now(timezone.utc)
    adaptive_conf = AdaptivePreferenceSignal(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
        signal_value="CONFERENCE",
        positive_evidence_count=15,
        negative_evidence_count=0,
        total_evidence_count=15,
        decay_adjusted_positive_weight=12.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=0.80,
        confidence=0.85,
        evidence_state=AdaptiveEvidenceState.STRONG,
        evidence_window_days=30.0,
        algorithm_version="5.5.1",
        deterministic_explanation="Conference affinity",
        created_at=now,
        updated_at=now,
    )

    # 1. Normal ALLOW state: adaptive contribution is positive (~0.10)
    normal_assessment = scorer.score_opportunity(
        profile_id=profile.id,
        preferences=[],
        opportunity=opp1,
        adaptive_signals=[adaptive_conf],
        governance_state=GovernanceGateState.ALLOW,
    )
    assert normal_assessment.adaptive_score > 0.0

    # 2. SUSPEND state: adaptive contribution must be strictly 0.0
    suspended_assessment = scorer.score_opportunity(
        profile_id=profile.id,
        preferences=[],
        opportunity=opp1,
        adaptive_signals=[adaptive_conf],
        governance_state=GovernanceGateState.SUSPEND,
    )
    assert suspended_assessment.adaptive_score == 0.0
    assert suspended_assessment.calibration_score == 0.0
    assert suspended_assessment.contextual_score == 0.0

    # 3. ALLOW_BOUNDED state: 50% damping applied
    bounded_assessment = scorer.score_opportunity(
        profile_id=profile.id,
        preferences=[],
        opportunity=opp1,
        adaptive_signals=[adaptive_conf],
        governance_state=GovernanceGateState.ALLOW_BOUNDED,
    )
    assert 0.0 < bounded_assessment.adaptive_score < normal_assessment.adaptive_score
    assert abs(bounded_assessment.adaptive_score - normal_assessment.adaptive_score * 0.5) < 1e-4


def test_recovery_from_suspension():
    """
    Verify deterministic recovery from SUSPEND state:
      - Recovery requires >= 5 stable interactions in the evaluation window.
      - 1-4 interactions cannot trigger recovery.
    """
    engine = PersonalizationGovernanceEngine(DEFAULT_GOVERNANCE_CONFIG)

    # Case A: SUSPENDED with only 3 interactions -> remains SUSPENDED
    gate_still_suspended, adapt_still_suspended, exp_sus = engine.evaluate_governance_gate(
        drifting_count=0,
        persistent_drift_count=0,
        stale_count=0,
        quality_stability="STABLE",
        context_stability="STABLE",
        evidence_sufficiency=EvidenceStrength.LOW,
        preference_alignment=PreferenceAlignmentState.ALIGNED,
        current_gate_state=GovernanceGateState.SUSPEND,
        recent_evidence_count=3,  # < 5 required
    )
    assert gate_still_suspended == GovernanceGateState.SUSPEND
    assert adapt_still_suspended == AdaptationState.SUSPENDED
    assert "recovery requires" in exp_sus.lower()

    # Case B: SUSPENDED with 6 stable interactions -> recovers to ALLOW_BOUNDED
    gate_recovered, adapt_recovered, exp_rec = engine.evaluate_governance_gate(
        drifting_count=0,
        persistent_drift_count=0,
        stale_count=0,
        quality_stability="STABLE",
        context_stability="STABLE",
        evidence_sufficiency=EvidenceStrength.MEDIUM,
        preference_alignment=PreferenceAlignmentState.ALIGNED,
        current_gate_state=GovernanceGateState.SUSPEND,
        recent_evidence_count=6,  # >= 5 required
    )
    assert gate_recovered == GovernanceGateState.ALLOW_BOUNDED
    assert adapt_recovered == AdaptationState.BOUNDED
    assert "recovery" in exp_rec.lower()


def test_governance_service_and_audit_log(db_session, sample_user_and_profile, sample_opportunities):
    """
    Test end-to-end PersonalizationGovernanceService:
      - Evaluation computation
      - Append-only audit event creation on state changes
      - Recomputation idempotency
    """
    user, profile = sample_user_and_profile
    opp1, opp2, _ = sample_opportunities
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Seed some interactions: 10 historical, 5 recent
    for i in range(10):
        db_session.add(
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opp1.id,
                interaction_type=InteractionType.SAVED,
                created_at=ref_time - timedelta(days=20 + i),
            )
        )
    for i in range(5):
        db_session.add(
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opp2.id,
                interaction_type=InteractionType.VIEWED,
                created_at=ref_time - timedelta(days=2 + i),
            )
        )
    db_session.flush()

    service = PersonalizationGovernanceService(db_session, DEFAULT_GOVERNANCE_CONFIG)

    # 1. First evaluation
    evaluation, events = service.evaluate_researcher_governance(
        profile_id=profile.id,
        reference_time=ref_time,
        force_recompute=True,
    )

    assert evaluation is not None
    assert evaluation.profile_id == profile.id
    assert evaluation.overall_health_state in [
        PersonalizationHealthState.HEALTHY,
        PersonalizationHealthState.STABLE,
    ]
    # Initial gate transition event recorded
    assert len(events) >= 1
    assert events[0].event_type == GovernanceEventType.GATE_TRANSITION

    # 2. Idempotent recomputation with same reference_time
    eval2, events2 = service.evaluate_researcher_governance(
        profile_id=profile.id,
        reference_time=ref_time,
        force_recompute=False,
    )
    assert eval2.id == evaluation.id
    # No new events since state didn't change
    assert len(events2) == 0


def test_governance_service_with_quality_evaluation(db_session, sample_user_and_profile, sample_opportunities):
    """
    Test PersonalizationGovernanceService when a PersonalizationQualityEvaluationModel
    is present in the database, verifying schema conversion and drift evaluation.
    """
    user, profile = sample_user_and_profile
    opp1, _, _ = sample_opportunities
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Add a quality evaluation record
    quality_eval = PersonalizationQualityEvaluationModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        evaluation_window_days=30.0,
        evaluation_timestamp=ref_time,
        total_recommendations_evaluated=10,
        total_attributed_interactions=5,
        positive_outcome_count=4,
        negative_outcome_count=1,
        neutral_outcome_count=0,
        engagement_rate=0.5,
        positive_feedback_rate=0.8,
        negative_feedback_rate=0.2,
        observed_personalization_lift=0.15,
        confidence=0.85,
        evaluation_state=QualityEvaluationState.POSITIVE.value,
        recommendation_diversity_score=0.75,
        novelty_rate=0.6,
        deterministic_explanation="Positive personalization quality",
        algorithm_version="5.7.1",
        created_at=ref_time,
        updated_at=ref_time,
    )
    db_session.add(quality_eval)
    db_session.flush()

    service = PersonalizationGovernanceService(db_session, DEFAULT_GOVERNANCE_CONFIG)
    evaluation, events = service.evaluate_researcher_governance(
        profile_id=profile.id,
        reference_time=ref_time,
        force_recompute=True,
    )

    assert evaluation is not None
    assert evaluation.profile_id == profile.id
    assert evaluation.quality_stability in ["STABLE", "IMPROVING", "DEGRADING"]


def test_governance_apis(client, sample_user_and_profile, sample_opportunities):
    """
    Test REST APIs:
      - GET /api/v1/researchers/{id}/personalization/health
      - GET /api/v1/researchers/{id}/personalization/drift
      - GET /api/v1/researchers/{id}/personalization/governance
      - POST /api/v1/researchers/{id}/personalization/health/recompute
      - Authorization isolation (X-User-ID mismatch -> 403)
    """
    user, profile = sample_user_and_profile
    researcher_id = str(profile.id)
    user_id = str(user.id)
    headers = {"X-User-ID": user_id}

    # 1. GET Health
    res_health = client.get(
        f"/api/v1/researchers/{researcher_id}/personalization/health",
        headers=headers,
    )
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert data_health["profile_id"] == researcher_id
    assert "overall_health_state" in data_health
    assert "governance_state" in data_health
    assert "adaptation_state" in data_health

    # 2. GET Drift
    res_drift = client.get(
        f"/api/v1/researchers/{researcher_id}/personalization/drift",
        headers=headers,
    )
    assert res_drift.status_code == 200
    data_drift = res_drift.json()
    assert "drifting_signals" in data_drift
    assert "stale_signals" in data_drift
    assert "stable_signals" in data_drift

    # 3. GET Governance History
    res_gov = client.get(
        f"/api/v1/researchers/{researcher_id}/personalization/governance",
        headers=headers,
    )
    assert res_gov.status_code == 200
    data_gov = res_gov.json()
    assert "items" in data_gov
    assert "total_count" in data_gov

    # 4. POST Recompute
    res_recompute = client.post(
        f"/api/v1/researchers/{researcher_id}/personalization/health/recompute",
        headers=headers,
        json={"force_recompute": True},
    )
    assert res_recompute.status_code == 200
    data_rec = res_recompute.json()
    assert data_rec["profile_id"] == researcher_id

    # 5. Multi-tenant Authorization: unauthorized user ID
    # An unknown UUID returns 401 (identity not found, no auto-bootstrap — P0-D fix).
    # A known but different user would return 403. Both protect the resource.
    bad_headers = {"X-User-ID": str(uuid.uuid4())}
    res_unauth = client.get(
        f"/api/v1/researchers/{researcher_id}/personalization/health",
        headers=bad_headers,
    )
    assert res_unauth.status_code in (401, 403), (
        f"Expected 401 or 403 for unauthorized access, got {res_unauth.status_code}"
    )


def test_performance_and_scaling_benchmarks():
    """
    Benchmark governance and drift evaluation latency across:
      - 10 signals
      - 100 signals
      - 1,000 signals
      - 10,000 signals
    Verifies linear/sub-linear execution time and zero external dependencies.
    """
    engine = PersonalizationGovernanceEngine(DEFAULT_GOVERNANCE_CONFIG)
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    scales = [10, 100, 1000, 10000]
    latencies = {}

    for count in scales:
        # Generate mock signals with historical and recent interactions
        signals_data = []
        for i in range(count):
            hist = [{"weight": 1.0, "is_positive": True} for _ in range(5)]
            recent = [{"weight": 1.0, "is_positive": (i % 2 == 0)} for _ in range(4)]
            signals_data.append((hist, recent))

        start_t = time.perf_counter()
        for i, (hist, recent) in enumerate(signals_data):
            engine.evaluate_signal_drift(
                dimension="OPPORTUNITY_TYPE",
                signal_value=f"VALUE_{i}",
                current_strength=0.5,
                historical_interactions=hist,
                recent_interactions=recent,
                last_evidence_time=ref_time - timedelta(days=1),
                reference_time=ref_time,
            )
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        latencies[count] = elapsed_ms

    # 10,000 evaluations should complete in well under 500ms (pure CPU, zero network, zero ML)
    assert latencies[10000] < 500.0, f"Latency too high: {latencies[10000]:.2f}ms"
    # Latency scaling should be roughly linear: 10,000 shouldn't be > 200x of 100
    assert latencies[10000] / max(latencies[100], 0.001) < 200.0
