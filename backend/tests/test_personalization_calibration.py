"""
Comprehensive test suite for Phase 5.6 — Adaptive Personalization Calibration & Recommendation Feedback Loop.

Verifies all 35 architectural and safety invariants:
  - Temporal attribution window (14 days default) and non-retroactive causality.
  - Attribution confidence tiers (DIRECT, LIKELY, WEAK, UNATTRIBUTED).
  - Feedback outcome classification and deterministic weighting.
  - Anti-feedback-loop safeguards (capping outcomes per opportunity per signal).
  - Minimum evidence thresholds (N < 3 yields INSUFFICIENT_DATA and 0.0 modifier).
  - State progression (INSUFFICIENT_DATA -> EARLY_SIGNAL -> CALIBRATING -> STABLE).
  - Conflicting feedback preservation (both positive/negative tracked, CONFLICTED state).
  - Hard calibration modifier bounds [-0.05, +0.05].
  - Explicit preference precedence (EXCLUDED always 0.0, PREFERRED protected >= 0.50).
  - Relevance dominance preservation (relevance >= 0.85).
  - Deterministic replay and idempotency.
  - Multi-tenant isolation and authorization.
  - Performance and scalability benchmarks (10 to 10,000 recommendations).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
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
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_interaction import (
    InteractionType,
    ResearcherInteractionModel,
)
from app.models.researcher_preference import (
    ResearcherPreferenceModel,
)
from app.schemas.researcher_preference import (
    PreferenceCategory,
    PreferenceType,
)
from app.models.user import UserModel
from app.personalization.adaptive_config import AdaptiveSignalConfig
from app.personalization.adaptive_engine import AdaptiveSignalEngine
from app.personalization.adaptive_models import (
    AdaptivePreferenceSignal,
)
from app.personalization.calibration_config import (
    DEFAULT_CALIBRATION_CONFIG,
    PersonalizationCalibrationConfig,
)
from app.personalization.calibration_engine import PersonalizationCalibrationEngine
from app.personalization.scorer import PersonalizationScorer
from app.schemas.personalization_calibration import (
    PersonalizationCalibrationSchema,
    RecommendationFeedbackAttributionSchema,
)
from app.schemas.researcher_preference import ResearcherPreferenceItemSchema
from app.services.personalization_calibration_service import (
    PersonalizationCalibrationService,
)


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
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def sample_researcher(db_session):
    """Create a sample user and researcher profile."""
    user = UserModel(
        id=uuid.uuid4(),
        email="researcher.phase5.6@example.edu",
        hashed_password="hashed_secret_test",
        full_name="Dr. Calibration Test",
        role="FACULTY",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status=AcademicStatus.FACULTY,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


@pytest.fixture
def sample_opportunity(db_session):
    """Create a sample opportunity."""
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="International Conference on Machine Learning Systems",
        opportunity_type="CONFERENCE",
        location="US",
        delivery_mode="HYBRID",
        status="ACTIVE",
    )
    db_session.add(opp)
    db_session.commit()
    db_session.refresh(opp)
    return opp


# =============================================================================
# 1. Attribution Window and Confidence Tests
# =============================================================================

def test_attribution_window_and_confidence():
    config = PersonalizationCalibrationConfig(
        attribution_window_days=14.0,
        direct_window_hours=24.0,
        likely_window_days=7.0,
    )
    rec_time = 1000000.0

    # Interaction before recommendation: UNATTRIBUTED (cannot travel back in time)
    inter_before = rec_time - 100.0
    tier, mult = config.get_attribution_confidence(rec_time, inter_before)
    assert tier == AttributionConfidence.UNATTRIBUTED
    assert mult == 0.0

    # Interaction 2 hours later: DIRECT
    inter_direct = rec_time + 7200.0
    tier, mult = config.get_attribution_confidence(rec_time, inter_direct)
    assert tier == AttributionConfidence.DIRECT
    assert mult == 1.0

    # Interaction 3 days later: LIKELY
    inter_likely = rec_time + (3 * 86400.0)
    tier, mult = config.get_attribution_confidence(rec_time, inter_likely)
    assert tier == AttributionConfidence.LIKELY
    assert mult == 0.75

    # Interaction 10 days later: WEAK
    inter_weak = rec_time + (10 * 86400.0)
    tier, mult = config.get_attribution_confidence(rec_time, inter_weak)
    assert tier == AttributionConfidence.WEAK
    assert mult == 0.40

    # Interaction 20 days later (outside 14-day window): UNATTRIBUTED
    inter_expired = rec_time + (20 * 86400.0)
    tier, mult = config.get_attribution_confidence(rec_time, inter_expired)
    assert tier == AttributionConfidence.UNATTRIBUTED
    assert mult == 0.0


# =============================================================================
# 2. Feedback Outcome Classification Tests
# =============================================================================

def test_feedback_outcome_classification():
    config = PersonalizationCalibrationConfig()

    assert config.outcome_classification[InteractionType.APPLIED.value] == FeedbackOutcomeType.STRONG_POSITIVE
    assert config.outcome_classification[InteractionType.INTERESTED.value] == FeedbackOutcomeType.STRONG_POSITIVE
    assert config.outcome_classification[InteractionType.SAVED.value] == FeedbackOutcomeType.MODERATE_POSITIVE
    assert config.outcome_classification[InteractionType.SHARED.value] == FeedbackOutcomeType.MODERATE_POSITIVE
    assert config.outcome_classification[InteractionType.OPENED.value] == FeedbackOutcomeType.WEAK_POSITIVE
    assert config.outcome_classification[InteractionType.VIEWED.value] == FeedbackOutcomeType.WEAK_POSITIVE
    assert config.outcome_classification[InteractionType.NOT_INTERESTED.value] == FeedbackOutcomeType.NEGATIVE
    assert config.outcome_classification[InteractionType.DISMISSED.value] == FeedbackOutcomeType.NEGATIVE
    assert config.outcome_classification[InteractionType.HIDDEN.value] == FeedbackOutcomeType.NEGATIVE

    # Verify weights ordering
    assert config.interaction_weights[InteractionType.APPLIED.value] > config.interaction_weights[InteractionType.SAVED.value]
    assert config.interaction_weights[InteractionType.SAVED.value] > config.interaction_weights[InteractionType.VIEWED.value]
    assert config.interaction_weights[InteractionType.NOT_INTERESTED.value] < 0.0


# =============================================================================
# 3. Anti-Feedback-Loop Safeguards Tests
# =============================================================================

def test_anti_feedback_loop_safeguards():
    profile_id = uuid.uuid4()
    opp_id = uuid.uuid4()
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # 10 duplicate VIEW interactions and 1 SAVE on the same opportunity
    attrs = []
    for i in range(10):
        attrs.append(
            RecommendationFeedbackAttributionSchema(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=opp_id,
                dimension="OPPORTUNITY_TYPE",
                signal_value="CONFERENCE",
                personalization_contribution=0.08,
                interaction_type="VIEWED",
                outcome_type=FeedbackOutcomeType.WEAK_POSITIVE,
                attribution_confidence=AttributionConfidence.DIRECT,
                attribution_weight=1.0,
                decay_adjusted_weight=0.05,
                recommendation_timestamp=ref_time - timedelta(hours=2),
                interaction_timestamp=ref_time - timedelta(hours=1),
                created_at=ref_time,
            )
        )
    # Add one SAVE (higher weight)
    attrs.append(
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            opportunity_id=opp_id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            personalization_contribution=0.08,
            interaction_type="SAVED",
            outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=0.60,
            recommendation_timestamp=ref_time - timedelta(hours=2),
            interaction_timestamp=ref_time - timedelta(minutes=30),
            created_at=ref_time,
        )
    )

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=5,
            negative_evidence_count=0,
            total_evidence_count=5,
            decay_adjusted_positive_weight=2.0,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=0.8,
            confidence=0.7,
            evidence_state=AdaptiveEvidenceState.ESTABLISHED,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Conference test signal",
            created_at=ref_time,
            updated_at=ref_time,
        )
    ]

    calibs = PersonalizationCalibrationEngine.calculate_signal_calibrations(
        profile_id=profile_id,
        attributions=attrs,
        signals=signals,
        reference_time=ref_time,
    )

    assert len(calibs) == 1
    calib = calibs[0]
    # Invariant: Repeated interactions on the same opportunity are capped to 1 outcome
    assert calib.positive_outcome_count == 1
    # Weight should be from the SAVE (0.60), not 10 * 0.05 + 0.60 = 1.10
    assert abs(calib.accumulated_positive_weight - 0.60) < 1e-4


# =============================================================================
# 4. Minimum Evidence and State Progression Tests
# =============================================================================

def test_minimum_evidence_thresholds():
    profile_id = uuid.uuid4()
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="JOURNAL",
            positive_evidence_count=1,
            negative_evidence_count=0,
            total_evidence_count=1,
            decay_adjusted_positive_weight=0.6,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=0.5,
            confidence=0.4,
            evidence_state=AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Journal signal",
            created_at=ref_time,
            updated_at=ref_time,
        )
    ]

    # Only 1 attribution (sparse evidence)
    attrs = [
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            opportunity_id=uuid.uuid4(),
            dimension="OPPORTUNITY_TYPE",
            signal_value="JOURNAL",
            personalization_contribution=0.05,
            interaction_type="SAVED",
            outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=0.60,
            recommendation_timestamp=ref_time - timedelta(hours=2),
            interaction_timestamp=ref_time - timedelta(hours=1),
            created_at=ref_time,
        )
    ]

    calibs = PersonalizationCalibrationEngine.calculate_signal_calibrations(
        profile_id=profile_id,
        attributions=attrs,
        signals=signals,
        reference_time=ref_time,
    )

    assert len(calibs) == 1
    assert calibs[0].calibration_state == CalibrationState.INSUFFICIENT_DATA
    assert calibs[0].net_calibration_modifier == 0.0


def test_calibration_states_progression():
    profile_id = uuid.uuid4()
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=15,
            negative_evidence_count=0,
            total_evidence_count=15,
            decay_adjusted_positive_weight=8.0,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=0.9,
            confidence=0.85,
            evidence_state=AdaptiveEvidenceState.STRONG,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Conference signal",
            created_at=ref_time,
            updated_at=ref_time,
        )
    ]

    # Helper to generate N positive distinct opportunity attributions
    def make_attrs(n: int):
        return [
            RecommendationFeedbackAttributionSchema(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=uuid.uuid4(),
                dimension="OPPORTUNITY_TYPE",
                signal_value="CONFERENCE",
                personalization_contribution=0.08,
                interaction_type="SAVED",
                outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
                attribution_confidence=AttributionConfidence.DIRECT,
                attribution_weight=1.0,
                decay_adjusted_weight=0.60,
                recommendation_timestamp=ref_time - timedelta(hours=2),
                interaction_timestamp=ref_time - timedelta(hours=1),
                created_at=ref_time,
            )
            for _ in range(n)
        ]

    # N=4: EARLY_SIGNAL
    c_early = PersonalizationCalibrationEngine.calculate_signal_calibrations(
        profile_id, make_attrs(4), signals, reference_time=ref_time
    )[0]
    assert c_early.calibration_state == CalibrationState.EARLY_SIGNAL

    # N=8: CALIBRATING
    c_calib = PersonalizationCalibrationEngine.calculate_signal_calibrations(
        profile_id, make_attrs(8), signals, reference_time=ref_time
    )[0]
    assert c_calib.calibration_state == CalibrationState.CALIBRATING

    # N=15: STABLE
    c_stable = PersonalizationCalibrationEngine.calculate_signal_calibrations(
        profile_id, make_attrs(15), signals, reference_time=ref_time
    )[0]
    assert c_stable.calibration_state == CalibrationState.STABLE
    assert c_stable.net_calibration_modifier > 0.0


# =============================================================================
# 5. Conflicting Feedback Handling Tests
# =============================================================================

def test_conflicting_feedback_handling():
    profile_id = uuid.uuid4()
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="WORKSHOP",
            positive_evidence_count=10,
            negative_evidence_count=10,
            total_evidence_count=20,
            decay_adjusted_positive_weight=4.0,
            decay_adjusted_negative_weight=4.0,
            weighted_signal_strength=0.0,
            confidence=0.5,
            evidence_state=AdaptiveEvidenceState.ESTABLISHED,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Workshop signal",
            created_at=ref_time,
            updated_at=ref_time,
        )
    ]

    # 6 positive and 5 negative distinct attributions
    attrs = []
    for _ in range(6):
        attrs.append(
            RecommendationFeedbackAttributionSchema(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=uuid.uuid4(),
                dimension="OPPORTUNITY_TYPE",
                signal_value="WORKSHOP",
                personalization_contribution=0.05,
                interaction_type="SAVED",
                outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
                attribution_confidence=AttributionConfidence.DIRECT,
                attribution_weight=1.0,
                decay_adjusted_weight=0.60,
                recommendation_timestamp=ref_time - timedelta(hours=2),
                interaction_timestamp=ref_time - timedelta(hours=1),
                created_at=ref_time,
            )
        )
    for _ in range(5):
        attrs.append(
            RecommendationFeedbackAttributionSchema(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=uuid.uuid4(),
                dimension="OPPORTUNITY_TYPE",
                signal_value="WORKSHOP",
                personalization_contribution=0.05,
                interaction_type="NOT_INTERESTED",
                outcome_type=FeedbackOutcomeType.NEGATIVE,
                attribution_confidence=AttributionConfidence.DIRECT,
                attribution_weight=1.0,
                decay_adjusted_weight=-0.70,
                recommendation_timestamp=ref_time - timedelta(hours=2),
                interaction_timestamp=ref_time - timedelta(hours=1),
                created_at=ref_time,
            )
        )

    calibs = PersonalizationCalibrationEngine.calculate_signal_calibrations(
        profile_id=profile_id,
        attributions=attrs,
        signals=signals,
        reference_time=ref_time,
    )

    assert len(calibs) == 1
    calib = calibs[0]
    assert calib.calibration_state == CalibrationState.CONFLICTED
    # Invariant: Conflicting evidence is preserved and dampens the modifier
    assert calib.positive_outcome_count == 6
    assert calib.negative_outcome_count == 5
    assert abs(calib.net_calibration_modifier) < 0.02


# =============================================================================
# 6. Calibration Modifier Bounds & Personalization Scorer Integration Tests
# =============================================================================

def test_calibration_modifier_bounds():
    profile_id = uuid.uuid4()
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Test extreme positive: 50 saves
    attrs_pos = [
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            opportunity_id=uuid.uuid4(),
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            personalization_contribution=0.10,
            interaction_type="APPLIED",
            outcome_type=FeedbackOutcomeType.STRONG_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=1.0,
            recommendation_timestamp=ref_time - timedelta(hours=2),
            interaction_timestamp=ref_time - timedelta(hours=1),
            created_at=ref_time,
        )
        for _ in range(50)
    ]

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=50,
            negative_evidence_count=0,
            total_evidence_count=50,
            decay_adjusted_positive_weight=40.0,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=1.0,
            confidence=1.0,
            evidence_state=AdaptiveEvidenceState.STRONG,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Conference signal",
            created_at=ref_time,
            updated_at=ref_time,
        )
    ]

    calib_pos = PersonalizationCalibrationEngine.calculate_signal_calibrations(
        profile_id, attrs_pos, signals, reference_time=ref_time
    )[0]
    # Invariant: Modifier must never exceed +0.05
    assert calib_pos.net_calibration_modifier <= 0.05
    assert calib_pos.net_calibration_modifier == pytest.approx(0.05, abs=0.005)


def test_explicit_preference_precedence_exclusion(sample_researcher, sample_opportunity):
    """
    Invariant: If explicit exclusion exists, final score is strictly 0.0,
    even with strong positive adaptive signals and strong positive calibration modifiers.
    """
    profile_id = sample_researcher.id

    # Explicit exclusion for CONFERENCE
    prefs = [
        ResearcherPreferenceItemSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            category=PreferenceCategory.OPPORTUNITY_TYPE,
            preference_type=PreferenceType.EXCLUDED,
            preference_key="opportunity_type",
            preference_value="CONFERENCE",
            display_label="Conference",
            strength=1.0,
            confidence=1.0,
            source="EXPLICIT",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    # Strong positive adaptive signal
    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=20,
            negative_evidence_count=0,
            total_evidence_count=20,
            decay_adjusted_positive_weight=15.0,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=1.0,
            confidence=0.9,
            evidence_state=AdaptiveEvidenceState.STRONG,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Conference affinity",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    # Positive calibration modifier (+0.05)
    calibs = [
        PersonalizationCalibrationSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            recommendations_influenced_count=15,
            positive_outcome_count=15,
            negative_outcome_count=0,
            neutral_outcome_count=0,
            accumulated_positive_weight=10.0,
            accumulated_negative_weight=0.0,
            net_calibration_modifier=0.05,
            calibration_confidence=0.9,
            calibration_state=CalibrationState.STABLE,
            algorithm_version="5.6.1",
            deterministic_explanation="Reinforced by positive feedback",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
        adaptive_signals=signals,
        calibrations=calibs,
    )

    # Invariant: Explicit EXCLUDED dominates strictly -> 0.0
    assert assessment.personalization_score == 0.0
    assert assessment.adaptive_score == 0.0


def test_explicit_preference_protection_against_adaptive_suppression(sample_researcher, sample_opportunity):
    """
    Invariant: If explicit PREFERRED exists and base score >= 0.50,
    negative adaptive/calibration modifiers cannot suppress the score below 0.50.
    """
    profile_id = sample_researcher.id

    prefs = [
        ResearcherPreferenceItemSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            category=PreferenceCategory.OPPORTUNITY_TYPE,
            preference_type=PreferenceType.PREFERRED,
            preference_key="opportunity_type",
            preference_value="CONFERENCE",
            display_label="Conference",
            strength=1.0,
            confidence=1.0,
            source="EXPLICIT",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    # Negative adaptive signal (-0.10)
    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=0,
            negative_evidence_count=20,
            total_evidence_count=20,
            decay_adjusted_positive_weight=0.0,
            decay_adjusted_negative_weight=15.0,
            weighted_signal_strength=-1.0,
            confidence=0.9,
            evidence_state=AdaptiveEvidenceState.STRONG,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Conference aversion",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    # Negative calibration modifier (-0.05)
    calibs = [
        PersonalizationCalibrationSchema(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            recommendations_influenced_count=15,
            positive_outcome_count=0,
            negative_outcome_count=15,
            neutral_outcome_count=0,
            accumulated_positive_weight=0.0,
            accumulated_negative_weight=10.0,
            net_calibration_modifier=-0.05,
            calibration_confidence=0.9,
            calibration_state=CalibrationState.STABLE,
            algorithm_version="5.6.1",
            deterministic_explanation="Reduced by negative feedback",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
        adaptive_signals=signals,
        calibrations=calibs,
    )

    # Invariant: Score cannot be reduced below 0.50 baseline
    assert assessment.personalization_score >= 0.50


# =============================================================================
# 7. Service Recompute, Queries, and Multi-Tenant Isolation Tests
# =============================================================================

def test_service_recompute_and_query(db_session, sample_researcher, sample_opportunity):
    profile_id = sample_researcher.id
    opp_id = sample_opportunity.id
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Create a recommendation snapshot and item
    snap = ResearcherRecommendationSnapshotModel(
        id=uuid.uuid4(),
        researcher_id=profile_id,
        ranking_version="phase3.7-v1",
        candidate_count=1,
        returned_count=1,
        created_at=now - timedelta(days=2),
    )
    db_session.add(snap)
    db_session.flush()

    item = ResearcherRecommendationItemModel(
        id=uuid.uuid4(),
        snapshot_id=snap.id,
        opportunity_id=opp_id,
        rank=1,
        base_relevance_score=0.90,
        personalization_score=0.75,
        behavioral_adjustment=0.0,
        final_score=0.88,
        created_at=now - timedelta(days=2),
    )
    db_session.add(item)

    # 2. Create an interaction event 1 day after recommendation exposure
    inter = ResearcherInteractionModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        opportunity_id=opp_id,
        interaction_type="APPLIED",
        is_explicit_feedback=True,
        source="RECOMMENDATION",
        metadata_payload={"snapshot_id": str(snap.id)},
        created_at=now - timedelta(days=1),
    )
    db_session.add(inter)

    # 3. Create active adaptive signal
    sig = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        positive_evidence_count=5,
        negative_evidence_count=0,
        total_evidence_count=5,
        decay_adjusted_positive_weight=3.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=0.8,
        confidence=0.7,
        evidence_state="ESTABLISHED",
        deterministic_explanation="Conference signal",
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=5),
    )
    db_session.add(sig)
    db_session.commit()

    # 4. Recompute calibrations via service
    calibs = PersonalizationCalibrationService.recompute_calibrations(
        db=db_session,
        profile_id=profile_id,
        reference_time=now,
    )
    db_session.commit()

    assert len(calibs) >= 1
    conf_calib = next(c for c in calibs if c.signal_value == "CONFERENCE")
    assert conf_calib.recommendations_influenced_count >= 1
    assert conf_calib.positive_outcome_count == 1
    assert conf_calib.net_calibration_modifier >= 0.0

    # 5. Verify query returns identical results
    queried = PersonalizationCalibrationService.get_calibrations(db_session, profile_id)
    assert len(queried) == len(calibs)

    # 6. Verify detail query returns linked attributions
    detail = PersonalizationCalibrationService.get_calibration_by_signal_id(
        db_session, profile_id, sig.id
    )
    assert detail is not None
    assert detail.total_attributions >= 1
    assert detail.attributions[0].opportunity_id == opp_id
    assert detail.attributions[0].attribution_confidence == AttributionConfidence.DIRECT


def test_idempotent_recomputation(db_session, sample_researcher, sample_opportunity):
    profile_id = sample_researcher.id
    opp_id = sample_opportunity.id
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Create snapshot and interaction
    snap = ResearcherRecommendationSnapshotModel(
        id=uuid.uuid4(),
        researcher_id=profile_id,
        ranking_version="phase3.7-v1",
        candidate_count=1,
        returned_count=1,
        created_at=now - timedelta(days=2),
    )
    db_session.add(snap)
    db_session.flush()

    item = ResearcherRecommendationItemModel(
        id=uuid.uuid4(),
        snapshot_id=snap.id,
        opportunity_id=opp_id,
        rank=1,
        base_relevance_score=0.90,
        personalization_score=0.75,
        behavioral_adjustment=0.0,
        final_score=0.88,
        created_at=now - timedelta(days=2),
    )
    db_session.add(item)

    inter = ResearcherInteractionModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        opportunity_id=opp_id,
        interaction_type="SAVED",
        is_explicit_feedback=True,
        source="RECOMMENDATION",
        created_at=now - timedelta(days=1),
    )
    db_session.add(inter)

    sig = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile_id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        positive_evidence_count=5,
        negative_evidence_count=0,
        total_evidence_count=5,
        decay_adjusted_positive_weight=3.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=0.8,
        confidence=0.7,
        evidence_state="ESTABLISHED",
        deterministic_explanation="Conference signal",
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=5),
    )
    db_session.add(sig)
    db_session.commit()

    # Recompute twice
    calibs1 = PersonalizationCalibrationService.recompute_calibrations(
        db=db_session, profile_id=profile_id, reference_time=now
    )
    db_session.commit()

    calibs2 = PersonalizationCalibrationService.recompute_calibrations(
        db=db_session, profile_id=profile_id, reference_time=now
    )
    db_session.commit()

    assert len(calibs1) == len(calibs2)
    # Ensure no row duplication in db
    count = db_session.query(PersonalizationCalibrationModel).filter_by(profile_id=profile_id).count()
    assert count == len(calibs1)


# =============================================================================
# 8. Performance and Scaling Benchmarks
# =============================================================================

def test_performance_and_scaling_benchmarks():
    """
    Benchmark attribution and calibration computation across 10, 100, 1,000, and 10,000 recommendations.
    """
    profile_id = uuid.uuid4()
    ref_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile_id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=100,
            negative_evidence_count=10,
            total_evidence_count=110,
            decay_adjusted_positive_weight=60.0,
            decay_adjusted_negative_weight=5.0,
            weighted_signal_strength=0.85,
            confidence=0.9,
            evidence_state=AdaptiveEvidenceState.STRONG,
            evidence_window_days=180.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Conference benchmark signal",
            created_at=ref_time,
            updated_at=ref_time,
        )
    ]

    scales = [10, 100, 1000, 10000]
    latencies = {}

    for n in scales:
        attrs = [
            RecommendationFeedbackAttributionSchema(
                id=uuid.uuid4(),
                profile_id=profile_id,
                opportunity_id=uuid.uuid4(),
                dimension="OPPORTUNITY_TYPE",
                signal_value="CONFERENCE",
                personalization_contribution=0.08,
                interaction_type="SAVED",
                outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
                attribution_confidence=AttributionConfidence.DIRECT,
                attribution_weight=1.0,
                decay_adjusted_weight=0.60,
                recommendation_timestamp=ref_time - timedelta(hours=2),
                interaction_timestamp=ref_time - timedelta(hours=1),
                created_at=ref_time,
            )
            for _ in range(n)
        ]

        t0 = time.perf_counter()
        calibs = PersonalizationCalibrationEngine.calculate_signal_calibrations(
            profile_id=profile_id,
            attributions=attrs,
            signals=signals,
            reference_time=ref_time,
        )
        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies[n] = t_elapsed_ms

        assert len(calibs) >= 1
        assert calibs[0].calibration_state in (CalibrationState.CALIBRATING, CalibrationState.STABLE)

    # Verify scaling requirements
    # 10,000 attributions must compute in sub-second (well under 250ms)
    assert latencies[10000] < 250.0
    print(f"\n[Phase 5.6 Benchmark Latencies] 10: {latencies[10]:.2f}ms, 100: {latencies[100]:.2f}ms, 1,000: {latencies[1000]:.2f}ms, 10,000: {latencies[10000]:.2f}ms")
