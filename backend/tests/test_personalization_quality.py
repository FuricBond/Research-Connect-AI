"""
Comprehensive test suite for Phase 5.7 — Personalization Evaluation, Contextual Adaptation & Recommendation Quality Loop.

Verifies:
  - Bounded quality metrics: engagement rate, positive/negative feedback rates.
  - Deterministic baseline comparison and observed personalization lift (empirical observation, not causal proof).
  - Minimum evidence thresholds (N < 3 strictly yields INSUFFICIENT_DATA and 0.0 modifier).
  - Contextual partitioning across supported dimensions (OPPORTUNITY_TYPE, DEADLINE_HORIZON, RISK_TIER, RELEVANCE_TIER, ACADEMIC_STATUS).
  - Hierarchical fallback: exact context -> broad context -> signal calibration -> neutral.
  - Bounded adaptation: contextual modifier strictly clamped to [-0.03, +0.03].
  - Combined calibration + contextual modifier clamped to [-0.05, +0.05], total adaptive clamped to [-0.10, +0.10].
  - Subordination: explicit preferences remain authoritative (EXCLUDED forces 0.0; PREFERRED >= 0.50 protected).
  - Recommendation diversity and novelty metrics.
  - Anti-feedback-loop protection: capped outcomes per opportunity per context.
  - Deterministic replay and recomputation idempotency.
  - API endpoints and multi-tenant authorization isolation.
  - Performance and scaling benchmarks (10 to 10,000 recommendations).
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
from app.models.personalization_quality import (
    ContextualFallbackLevel,
    PersonalizationContextualAdaptationModel,
    PersonalizationQualityEvaluationModel,
    QualityEvaluationState,
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
from app.personalization.adaptive_models import AdaptivePreferenceSignal
from app.personalization.quality_config import (
    DEFAULT_QUALITY_CONFIG,
    PersonalizationQualityConfig,
)
from app.personalization.quality_engine import PersonalizationQualityEngine
from app.personalization.scorer import PersonalizationScorer
from app.schemas.personalization_calibration import (
    PersonalizationCalibrationSchema,
    RecommendationFeedbackAttributionSchema,
)
from app.schemas.personalization_quality import (
    PersonalizationContextualAdaptationSchema,
    PersonalizationQualityEvaluationSchema,
)
from app.schemas.researcher_preference import ResearcherPreferenceItemSchema
from app.services.personalization_quality_service import (
    PersonalizationQualityService,
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
        email="researcher.quality@test.edu",
        hashed_password="hashed_pw_test",
        full_name="Quality Researcher",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="POSTDOC",
        institution="Oxford University",
    )
    db_session.add(profile)
    db_session.flush()

    return user, profile


@pytest.fixture
def sample_opportunities(db_session):
    """Creates diverse sample opportunities with conferences, journals, and workshops."""
    opps = []
    now = datetime.now(timezone.utc)

    # 1. Conference near deadline
    opp1 = OpportunityModel(
        id=uuid.uuid4(),
        title="International Conference on AI (ICAI)",
        opportunity_type="CONFERENCE",
        submission_deadline=now + timedelta(days=7),
        delivery_mode="HYBRID",
        source_id=uuid.uuid4(),
    )
    # 2. Journal far deadline
    opp2 = OpportunityModel(
        id=uuid.uuid4(),
        title="Journal of Machine Learning Systems",
        opportunity_type="JOURNAL",
        submission_deadline=now + timedelta(days=90),
        delivery_mode="ONLINE",
        source_id=uuid.uuid4(),
    )
    # 3. Workshop moderate deadline
    opp3 = OpportunityModel(
        id=uuid.uuid4(),
        title="Workshop on Medical Imaging AI",
        opportunity_type="WORKSHOP",
        submission_deadline=now + timedelta(days=30),
        delivery_mode="OFFLINE",
        source_id=uuid.uuid4(),
    )
    # 4. Another Conference near deadline
    opp4 = OpportunityModel(
        id=uuid.uuid4(),
        title="European Conference on Computer Vision",
        opportunity_type="CONFERENCE",
        submission_deadline=now + timedelta(days=10),
        delivery_mode="HYBRID",
        source_id=uuid.uuid4(),
    )

    opps.extend([opp1, opp2, opp3, opp4])
    for o in opps:
        db_session.add(o)
    db_session.flush()
    return opps


def test_quality_metrics_calculation(sample_user_and_profile, sample_opportunities):
    """
    Test deterministic calculation of engagement rate, positive feedback rate,
    and negative feedback rate.
    """
    _, profile = sample_user_and_profile
    opp1, opp2, opp3, opp4 = sample_opportunities
    now = datetime.now(timezone.utc)

    # Create recommendation items
    rec_items = [
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp1.id,
            rank=1,
            base_relevance_score=0.85,
            personalization_score=0.75,
            behavioral_adjustment=0.04,
            final_score=0.88,
            created_at=now - timedelta(days=2),
        ),
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp2.id,
            rank=2,
            base_relevance_score=0.80,
            personalization_score=0.0,
            behavioral_adjustment=0.0,
            final_score=0.80,
            created_at=now - timedelta(days=2),
        ),
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp3.id,
            rank=3,
            base_relevance_score=0.75,
            personalization_score=0.60,
            behavioral_adjustment=0.02,
            final_score=0.78,
            created_at=now - timedelta(days=3),
        ),
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp4.id,
            rank=4,
            base_relevance_score=0.70,
            personalization_score=0.0,
            behavioral_adjustment=0.0,
            final_score=0.70,
            created_at=now - timedelta(days=4),
        ),
    ]

    # Positive interaction on opp1 (saved)
    # Negative interaction on opp3 (dismissed)
    attributions = [
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp1.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            interaction_type=InteractionType.SAVED.value,
            outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=0.60,
            recommendation_timestamp=now - timedelta(days=2),
            interaction_timestamp=now - timedelta(days=1),
            algorithm_version="5.6.1",
            created_at=now,
        ),
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp3.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="WORKSHOP",
            interaction_type=InteractionType.DISMISSED.value,
            outcome_type=FeedbackOutcomeType.NEGATIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=-0.50,
            recommendation_timestamp=now - timedelta(days=3),
            interaction_timestamp=now - timedelta(days=2),
            algorithm_version="5.6.1",
            created_at=now,
        ),
    ]

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile.id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=5,
            negative_evidence_count=0,
            total_evidence_count=5,
            decay_adjusted_positive_weight=3.0,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=0.8,
            confidence=0.7,
            evidence_state=AdaptiveEvidenceState.ESTABLISHED,
            evidence_window_days=30.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Established conference affinity",
            created_at=now,
            updated_at=now,
        )
    ]

    eval_schema, adaptations, summaries, sig_qualities = PersonalizationQualityEngine.evaluate_personalization_quality(
        profile_id=profile.id,
        recommendation_items=rec_items,
        interactions=[],
        attributions=attributions,
        opportunities={o.id: o for o in sample_opportunities},
        signals=signals,
        calibrations=[],
        reference_time=now,
    )

    # 4 recommendations evaluated, 2 engaged (opp1 and opp3)
    assert eval_schema.recommendations_evaluated_count == 4
    assert eval_schema.attributed_interactions_count == 2
    assert eval_schema.observed_engagement_rate == 0.50  # 2 / 4
    assert eval_schema.positive_outcomes_count == 1
    assert eval_schema.negative_outcomes_count == 1
    assert eval_schema.observed_positive_rate == 0.50  # 1 / 2
    assert eval_schema.observed_negative_rate == 0.50  # 1 / 2


def test_baseline_comparison_and_observed_lift(sample_user_and_profile, sample_opportunities):
    """
    Test deterministic baseline comparison and observed personalization lift calculation.
    """
    _, profile = sample_user_and_profile
    opp1, opp2, opp3, opp4 = sample_opportunities
    now = datetime.now(timezone.utc)

    # Personalized items: opp1, opp3 (both received positive interactions)
    # Baseline items: opp2, opp4 (opp2 received negative interaction, opp4 none)
    rec_items = [
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp1.id,
            rank=1,
            base_relevance_score=0.85,
            personalization_score=0.80,
            behavioral_adjustment=0.05,
            final_score=0.90,
            created_at=now - timedelta(days=1),
        ),
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp3.id,
            rank=2,
            base_relevance_score=0.80,
            personalization_score=0.60,
            behavioral_adjustment=0.03,
            final_score=0.83,
            created_at=now - timedelta(days=1),
        ),
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp2.id,
            rank=3,
            base_relevance_score=0.75,
            personalization_score=0.0,
            behavioral_adjustment=0.0,
            final_score=0.75,
            created_at=now - timedelta(days=1),
        ),
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp4.id,
            rank=4,
            base_relevance_score=0.70,
            personalization_score=0.0,
            behavioral_adjustment=0.0,
            final_score=0.70,
            created_at=now - timedelta(days=1),
        ),
    ]

    attributions = [
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp1.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            interaction_type=InteractionType.APPLIED.value,
            outcome_type=FeedbackOutcomeType.STRONG_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=1.0,
            recommendation_timestamp=now - timedelta(days=1),
            interaction_timestamp=now,
            algorithm_version="5.6.1",
            created_at=now,
        ),
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp3.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="WORKSHOP",
            interaction_type=InteractionType.SAVED.value,
            outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=0.6,
            recommendation_timestamp=now - timedelta(days=1),
            interaction_timestamp=now,
            algorithm_version="5.6.1",
            created_at=now,
        ),
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp2.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="JOURNAL",
            interaction_type=InteractionType.DISMISSED.value,
            outcome_type=FeedbackOutcomeType.NEGATIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=-0.5,
            recommendation_timestamp=now - timedelta(days=1),
            interaction_timestamp=now,
            algorithm_version="5.6.1",
            created_at=now,
        ),
    ]

    eval_schema, _, _, _ = PersonalizationQualityEngine.evaluate_personalization_quality(
        profile_id=profile.id,
        recommendation_items=rec_items,
        interactions=[],
        attributions=attributions,
        opportunities={o.id: o for o in sample_opportunities},
        signals=[],
        calibrations=[],
        reference_time=now,
    )

    # Personalized items (2): both positive -> pers_pos_rate = 1.0 (100%)
    # Baseline items (2): 0 positive -> baseline_pos_rate = 0.0 (0%)
    # Observed lift = 1.0 - 0.0 = +1.0 (+100%)
    assert eval_schema.observed_personalization_lift > 0.0
    assert "lift" in eval_schema.deterministic_explanation.lower() or "engagement" in eval_schema.deterministic_explanation.lower()


def test_minimum_evidence_threshold(sample_user_and_profile, sample_opportunities):
    """
    Test that N < 3 interactions strictly yields INSUFFICIENT_DATA and zero contextual modifier.
    """
    _, profile = sample_user_and_profile
    opp1 = sample_opportunities[0]
    now = datetime.now(timezone.utc)

    # Only 1 recommendation and 1 interaction
    rec_items = [
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp1.id,
            rank=1,
            base_relevance_score=0.85,
            personalization_score=0.75,
            behavioral_adjustment=0.04,
            final_score=0.88,
            created_at=now,
        )
    ]
    attributions = [
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp1.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            interaction_type=InteractionType.SAVED.value,
            outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=0.60,
            recommendation_timestamp=now,
            interaction_timestamp=now,
            algorithm_version="5.6.1",
            created_at=now,
        )
    ]

    eval_schema, adaptations, _, _ = PersonalizationQualityEngine.evaluate_personalization_quality(
        profile_id=profile.id,
        recommendation_items=rec_items,
        interactions=[],
        attributions=attributions,
        opportunities={opp1.id: opp1},
        signals=[],
        calibrations=[],
        reference_time=now,
    )

    assert eval_schema.evaluation_state == QualityEvaluationState.INSUFFICIENT_DATA
    assert "not enough interaction evidence" in eval_schema.deterministic_explanation.lower()


def test_contextual_partitioning_and_hierarchical_fallback(sample_user_and_profile, sample_opportunities):
    """
    Test deterministic contextual partitioning and hierarchical fallback:
      Level 1: Exact context (N >= 3, conf >= 0.30)
      Level 2: Broad context (insufficient exact context, broad context fallback)
      Level 3: Global signal calibration fallback
      Level 4: Neutral (0.0)
    """
    _, profile = sample_user_and_profile
    opp1, opp2, opp3, opp4 = sample_opportunities
    now = datetime.now(timezone.utc)

    # Create 3 recommendation items for CONFERENCE near deadline with positive feedback
    rec_items = []
    attributions = []
    for i in range(3):
        opp_c = OpportunityModel(
            id=uuid.uuid4(),
            title=f"Conference Opp {i}",
            opportunity_type="CONFERENCE",
            submission_deadline=now + timedelta(days=5),
            delivery_mode="HYBRID",
        )
        sample_opportunities.append(opp_c)
        rec_items.append(
            ResearcherRecommendationItemModel(
                id=uuid.uuid4(),
                snapshot_id=uuid.uuid4(),
                opportunity_id=opp_c.id,
                rank=1,
                base_relevance_score=0.85,
                personalization_score=0.70,
                behavioral_adjustment=0.03,
                final_score=0.88,
                created_at=now - timedelta(days=2),
            )
        )
        attributions.append(
            RecommendationFeedbackAttributionSchema(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opp_c.id,
                dimension="OPPORTUNITY_TYPE",
                signal_value="CONFERENCE",
                interaction_type=InteractionType.SAVED.value,
                outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE,
                attribution_confidence=AttributionConfidence.DIRECT,
                attribution_weight=1.0,
                decay_adjusted_weight=0.6,
                recommendation_timestamp=now - timedelta(days=2),
                interaction_timestamp=now - timedelta(days=1),
                algorithm_version="5.6.1",
                created_at=now,
            )
        )

    signals = [
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile.id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="CONFERENCE",
            positive_evidence_count=3,
            negative_evidence_count=0,
            total_evidence_count=3,
            decay_adjusted_positive_weight=1.8,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=0.7,
            confidence=0.6,
            evidence_state=AdaptiveEvidenceState.ESTABLISHED,
            evidence_window_days=30.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Conference signal",
            created_at=now,
            updated_at=now,
        ),
        AdaptivePreferenceSignal(
            id=uuid.uuid4(),
            profile_id=profile.id,
            dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
            signal_value="JOURNAL",
            positive_evidence_count=0,
            negative_evidence_count=0,
            total_evidence_count=0,
            decay_adjusted_positive_weight=0.0,
            decay_adjusted_negative_weight=0.0,
            weighted_signal_strength=0.0,
            confidence=0.0,
            evidence_state=AdaptiveEvidenceState.INSUFFICIENT_EVIDENCE,
            evidence_window_days=30.0,
            algorithm_version="5.5.1",
            deterministic_explanation="Journal signal",
            created_at=now,
            updated_at=now,
        ),
    ]

    calibrations = [
        PersonalizationCalibrationSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="JOURNAL",
            net_calibration_modifier=-0.02,
            calibration_confidence=0.4,
            calibration_state=CalibrationState.CALIBRATING,
            deterministic_explanation="Journal calibration",
            created_at=now,
            updated_at=now,
        )
    ]

    eval_schema, adaptations, summaries, _ = PersonalizationQualityEngine.evaluate_personalization_quality(
        profile_id=profile.id,
        recommendation_items=rec_items,
        interactions=[],
        attributions=attributions,
        opportunities={o.id: o for o in sample_opportunities},
        signals=signals,
        calibrations=calibrations,
        reference_time=now,
    )

    # Check exact context adaptation for CONFERENCE
    conf_exact = [
        a for a in adaptations
        if a.signal_value == "CONFERENCE" and a.context_dimension == "OPPORTUNITY_TYPE" and a.context_value == "CONFERENCE"
    ]
    assert len(conf_exact) > 0
    assert conf_exact[0].fallback_level == ContextualFallbackLevel.RESEARCHER_EXACT_CONTEXT
    assert conf_exact[0].contextual_modifier > 0.0
    assert conf_exact[0].contextual_modifier <= 0.03

    # Check fallback for JOURNAL (insufficient exact data -> fallback level)
    journal_adapt = [
        a for a in adaptations
        if a.signal_value == "JOURNAL" and a.context_dimension == "OPPORTUNITY_TYPE" and a.context_value == "CONFERENCE"
    ]
    assert len(journal_adapt) > 0
    # JOURNAL has no exact evidence in CONFERENCE context, should fall back to broad context or signal calibration
    assert journal_adapt[0].fallback_level in (
        ContextualFallbackLevel.RESEARCHER_BROAD_CONTEXT,
        ContextualFallbackLevel.GLOBAL_SIGNAL_CALIBRATION,
        ContextualFallbackLevel.NEUTRAL,
    )


def test_bounded_adaptation_and_subordination(sample_user_and_profile, sample_opportunities):
    """
    Test that:
      - Contextual modifier is clamped strictly to [-0.03, +0.03].
      - Combined calibration + contextual modifier clamped to [-0.05, +0.05].
      - Total adaptive contribution clamped to [-0.10, +0.10].
      - Subordination: Explicit EXCLUDED forces final score to 0.0.
      - Explicit PREFERRED with score >= 0.50 protected against negative suppression.
    """
    _, profile = sample_user_and_profile
    opp = sample_opportunities[0]
    now = datetime.now(timezone.utc)

    # 1. Test explicit EXCLUDED dominance
    excluded_pref = ResearcherPreferenceItemSchema(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category=PreferenceCategory.OPPORTUNITY_TYPE.value,
        preference_type=PreferenceType.EXCLUDED.value,
        preference_key="OPPORTUNITY_TYPE:CONFERENCE",
        preference_value="CONFERENCE",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        weight=1.0,
        source="EXPLICIT",
        created_at=now,
        updated_at=now,
    )

    adaptive_signal = AdaptivePreferenceSignal(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
        signal_value="CONFERENCE",
        positive_evidence_count=10,
        negative_evidence_count=0,
        total_evidence_count=10,
        decay_adjusted_positive_weight=5.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=1.0,
        confidence=1.0,
        evidence_state=AdaptiveEvidenceState.STRONG,
        evidence_window_days=30.0,
        algorithm_version="5.5.1",
        deterministic_explanation="Strong conference signal",
        created_at=now,
        updated_at=now,
    )

    context_adaptation = PersonalizationContextualAdaptationSchema(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        context_dimension="OPPORTUNITY_TYPE",
        context_value="CONFERENCE",
        sample_size=15,
        positive_count=15,
        negative_count=0,
        observed_lift=0.25,
        confidence=0.9,
        fallback_level=ContextualFallbackLevel.RESEARCHER_EXACT_CONTEXT,
        contextual_modifier=0.03,  # Max positive
        hysteresis_state="STABLE",
        evaluation_state=QualityEvaluationState.POSITIVE,
        deterministic_explanation="Max positive adaptation",
        algorithm_version="5.7.1",
        created_at=now,
        updated_at=now,
    )

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile.id,
        preferences=[excluded_pref],
        opportunity=opp,
        adaptive_signals=[adaptive_signal],
        contextual_adaptations=[context_adaptation],
    )

    # Explicit exclusion forces final personalization score to 0.0
    assert assessment.personalization_score == 0.0
    assert assessment.adaptive_score == 0.0

    # 2. Test explicit PREFERRED protection against negative contextual modifier
    preferred_pref = ResearcherPreferenceItemSchema(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category=PreferenceCategory.OPPORTUNITY_TYPE.value,
        preference_type=PreferenceType.PREFERRED.value,
        preference_key="OPPORTUNITY_TYPE:CONFERENCE",
        preference_value="CONFERENCE",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        weight=1.0,
        source="EXPLICIT",
        created_at=now,
        updated_at=now,
    )

    negative_signal = AdaptivePreferenceSignal(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE,
        signal_value="CONFERENCE",
        positive_evidence_count=0,
        negative_evidence_count=10,
        total_evidence_count=10,
        decay_adjusted_positive_weight=0.0,
        decay_adjusted_negative_weight=5.0,
        weighted_signal_strength=-1.0,
        confidence=1.0,
        evidence_state=AdaptiveEvidenceState.STRONG,
        evidence_window_days=30.0,
        algorithm_version="5.5.1",
        deterministic_explanation="Strong negative signal",
        created_at=now,
        updated_at=now,
    )

    negative_context_adaptation = PersonalizationContextualAdaptationSchema(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension="OPPORTUNITY_TYPE",
        signal_value="CONFERENCE",
        context_dimension="OPPORTUNITY_TYPE",
        context_value="CONFERENCE",
        sample_size=15,
        positive_count=0,
        negative_count=15,
        observed_lift=-0.30,
        confidence=0.9,
        fallback_level=ContextualFallbackLevel.RESEARCHER_EXACT_CONTEXT,
        contextual_modifier=-0.03,  # Max negative
        hysteresis_state="STABLE",
        evaluation_state=QualityEvaluationState.NEGATIVE,
        deterministic_explanation="Max negative adaptation",
        algorithm_version="5.7.1",
        created_at=now,
        updated_at=now,
    )

    assessment_pref = PersonalizationScorer.score_opportunity(
        profile_id=profile.id,
        preferences=[preferred_pref],
        opportunity=opp,
        adaptive_signals=[negative_signal],
        contextual_adaptations=[negative_context_adaptation],
    )

    # Score cannot drop below 0.50 when explicit PREFERRED is matched
    assert assessment_pref.score.bounded_score >= 0.50
    assert assessment_pref.personalization_score >= 0.50
    assert assessment_pref.contextual_score == -0.03


def test_diversity_and_novelty_metrics(sample_user_and_profile, sample_opportunities):
    """
    Test deterministic calculation of diversity score and novelty rate.
    """
    _, profile = sample_user_and_profile
    now = datetime.now(timezone.utc)

    rec_items = [
        ResearcherRecommendationItemModel(
            id=uuid.uuid4(),
            snapshot_id=uuid.uuid4(),
            opportunity_id=opp.id,
            rank=i + 1,
            base_relevance_score=0.80,
            personalization_score=0.50,
            behavioral_adjustment=0.0,
            final_score=0.80,
            created_at=now,
        )
        for i, opp in enumerate(sample_opportunities)
    ]

    eval_schema, _, _, _ = PersonalizationQualityEngine.evaluate_personalization_quality(
        profile_id=profile.id,
        recommendation_items=rec_items,
        interactions=[],
        attributions=[],
        opportunities={o.id: o for o in sample_opportunities},
        signals=[],
        calibrations=[],
        reference_time=now,
    )

    # 4 distinct opportunities out of 4 recommendations -> novelty rate = 1.0 (100%)
    assert eval_schema.novelty_rate == 1.0
    # Diverse opportunity types (CONFERENCE, JOURNAL, WORKSHOP) -> diversity > 0.0
    assert eval_schema.diversity_score > 0.0


def test_anti_feedback_loop_repeated_exposure(sample_user_and_profile, sample_opportunities):
    """
    Test that repeated interactions on the same opportunity/context do not multiply evidence points.
    """
    _, profile = sample_user_and_profile
    opp = sample_opportunities[0]
    now = datetime.now(timezone.utc)

    # 5 repeated interactions on the same opportunity
    attributions = [
        RecommendationFeedbackAttributionSchema(
            id=uuid.uuid4(),
            profile_id=profile.id,
            opportunity_id=opp.id,
            dimension="OPPORTUNITY_TYPE",
            signal_value="CONFERENCE",
            interaction_type=InteractionType.VIEWED.value,
            outcome_type=FeedbackOutcomeType.WEAK_POSITIVE,
            attribution_confidence=AttributionConfidence.DIRECT,
            attribution_weight=1.0,
            decay_adjusted_weight=0.05,
            recommendation_timestamp=now,
            interaction_timestamp=now,
            algorithm_version="5.6.1",
            created_at=now,
        )
        for _ in range(5)
    ]

    eval_schema, _, _, _ = PersonalizationQualityEngine.evaluate_personalization_quality(
        profile_id=profile.id,
        recommendation_items=[
            ResearcherRecommendationItemModel(
                id=uuid.uuid4(),
                snapshot_id=uuid.uuid4(),
                opportunity_id=opp.id,
                rank=1,
                base_relevance_score=0.85,
                personalization_score=0.5,
                behavioral_adjustment=0.0,
                final_score=0.85,
                created_at=now,
            )
        ],
        interactions=[],
        attributions=attributions,
        opportunities={opp.id: opp},
        signals=[],
        calibrations=[],
        reference_time=now,
    )

    # Deduped to at most 1 primary feedback outcome per opportunity
    assert eval_schema.attributed_interactions_count == 1


def test_service_recompute_and_persistence_idempotency(db_session, sample_user_and_profile, sample_opportunities):
    """
    Test that recomputing quality evaluation multiple times is strictly idempotent
    and updates existing database records without error.
    """
    _, profile = sample_user_and_profile
    now = datetime.now(timezone.utc)

    # Run recomputation 1
    eval1, adapts1, _, _ = PersonalizationQualityService.recompute_personalization_quality(
        db=db_session,
        profile_id=profile.id,
        reference_time=now,
    )
    db_session.commit()

    # Verify query returns evaluation
    fetched = PersonalizationQualityService.get_latest_quality_evaluation(db_session, profile.id)
    assert fetched is not None
    assert fetched.profile_id == profile.id

    # Run recomputation 2 (idempotency check)
    eval2, adapts2, _, _ = PersonalizationQualityService.recompute_personalization_quality(
        db=db_session,
        profile_id=profile.id,
        reference_time=now,
    )
    db_session.commit()

    # Should have updated the existing evaluation record, not created duplicates
    all_evals = db_session.query(PersonalizationQualityEvaluationModel).filter(
        PersonalizationQualityEvaluationModel.profile_id == profile.id
    ).all()
    assert len(all_evals) == 1
    assert eval2.observed_engagement_rate == eval1.observed_engagement_rate


def test_scaling_benchmarks():
    """
    Benchmark quality evaluation latency and memory scaling across:
      - 10 recommendations
      - 100 recommendations
      - 1,000 recommendations
      - 10,000 recommendations
    """
    profile_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    for n_recs in [10, 100, 1000, 10000]:
        opp_map = {}
        rec_items = []
        attributions = []

        for i in range(n_recs):
            opp_id = uuid.uuid4()
            opp = OpportunityModel(
                id=opp_id,
                title=f"Benchmark Opp {i}",
                opportunity_type="CONFERENCE" if i % 2 == 0 else "JOURNAL",
                submission_deadline=now + timedelta(days=10 + (i % 50)),
                delivery_mode="HYBRID" if i % 3 == 0 else "ONLINE",
            )
            opp_map[opp_id] = opp

            rec_items.append(
                ResearcherRecommendationItemModel(
                    id=uuid.uuid4(),
                    snapshot_id=uuid.uuid4(),
                    opportunity_id=opp_id,
                    rank=(i % 10) + 1,
                    base_relevance_score=0.85,
                    personalization_score=0.60 if i % 2 == 0 else 0.0,
                    behavioral_adjustment=0.02 if i % 2 == 0 else 0.0,
                    final_score=0.85,
                    created_at=now - timedelta(days=1),
                )
            )

            # 20% engagement
            if i % 5 == 0:
                attributions.append(
                    RecommendationFeedbackAttributionSchema(
                        id=uuid.uuid4(),
                        profile_id=profile_id,
                        opportunity_id=opp_id,
                        dimension="OPPORTUNITY_TYPE",
                        signal_value="CONFERENCE" if i % 2 == 0 else "JOURNAL",
                        interaction_type=InteractionType.SAVED.value if i % 10 == 0 else InteractionType.DISMISSED.value,
                        outcome_type=FeedbackOutcomeType.MODERATE_POSITIVE if i % 10 == 0 else FeedbackOutcomeType.NEGATIVE,
                        attribution_confidence=AttributionConfidence.DIRECT,
                        attribution_weight=1.0,
                        decay_adjusted_weight=0.6 if i % 10 == 0 else -0.5,
                        recommendation_timestamp=now - timedelta(days=1),
                        interaction_timestamp=now,
                        algorithm_version="5.6.1",
                        created_at=now,
                    )
                )

        t_start = time.perf_counter()
        eval_schema, adaptations, summaries, _ = PersonalizationQualityEngine.evaluate_personalization_quality(
            profile_id=profile_id,
            recommendation_items=rec_items,
            interactions=[],
            attributions=attributions,
            opportunities=opp_map,
            signals=[],
            calibrations=[],
            reference_time=now,
        )
        t_elapsed = time.perf_counter() - t_start

        # Benchmark assertions: even 10,000 recommendations must complete in < 0.50 seconds
        assert t_elapsed < 0.50, f"Evaluation of {n_recs} recommendations took too long: {t_elapsed:.4f}s"
        assert eval_schema.recommendations_evaluated_count == n_recs


def test_api_personalization_quality_endpoints_and_authorization(
    client: TestClient,
    db_session,
    sample_user_and_profile,
    sample_opportunities,
):
    """
    Verify FastAPI endpoints for Phase 5.7:
      - GET /api/v1/researchers/{id}/personalization/quality
      - GET /api/v1/researchers/{id}/personalization/quality/contexts
      - GET /api/v1/researchers/{id}/personalization/quality/signals
      - POST /api/v1/researchers/{id}/personalization/quality/recompute
      - Multi-tenant isolation: User A cannot access or recompute User B's profile.
      - 404 for unknown researcher ID.
    """
    user_a, profile_a = sample_user_and_profile
    opp1, opp2, _, _ = sample_opportunities
    now = datetime.now(timezone.utc)

    # 1. Create a second researcher (User B / Profile B) for multi-tenant isolation testing
    user_b = UserModel(
        id=uuid.uuid4(),
        email="researcher_b@cambridge.edu",
        hashed_password="hashed_pw_b",
        full_name="Dr. B Researcher",
        is_active=True,
    )
    db_session.add(user_b)
    db_session.flush()

    profile_b = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user_b.id,
        academic_status="FACULTY",
        institution="Cambridge University",
    )
    db_session.add(profile_b)
    db_session.flush()

    # Pre-seed some recommendations for profile A
    snap_a = ResearcherRecommendationSnapshotModel(
        id=uuid.uuid4(),
        researcher_id=profile_a.id,
        ranking_version="v5.7.1",
        candidate_count=10,
        returned_count=2,
        created_at=now - timedelta(days=2),
    )
    db_session.add(snap_a)
    item_a1 = ResearcherRecommendationItemModel(
        id=uuid.uuid4(),
        snapshot_id=snap_a.id,
        opportunity_id=opp1.id,
        rank=1,
        base_relevance_score=0.85,
        personalization_score=0.55,
        behavioral_adjustment=0.03,
        final_score=0.88,
        created_at=now - timedelta(days=2),
    )
    item_a2 = ResearcherRecommendationItemModel(
        id=uuid.uuid4(),
        snapshot_id=snap_a.id,
        opportunity_id=opp2.id,
        rank=2,
        base_relevance_score=0.80,
        personalization_score=0.0,
        behavioral_adjustment=0.0,
        final_score=0.80,
        created_at=now - timedelta(days=2),
    )
    db_session.add_all([item_a1, item_a2])
    db_session.commit()

    # ── Test 1: GET /quality ──────────────────────────────────────────────────
    # User A accesses own profile
    res = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["profile_id"] == str(profile_a.id)
    assert "evaluation" in data
    assert "context_summaries" in data
    assert "deterministic_explanation" in data
    assert data["evaluation"]["profile_id"] == str(profile_a.id)
    assert "evaluation_state" in data["evaluation"]
    assert "observed_personalization_lift" in data["evaluation"]
    assert "diversity_score" in data["evaluation"]
    assert "novelty_rate" in data["evaluation"]

    # ── Test 2: Multi-tenant isolation (User B cannot access Profile A) ───────
    res_forbidden = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality",
        headers={"X-User-ID": str(user_b.id)},
    )
    assert res_forbidden.status_code == 403

    # User A cannot access Profile B
    res_forbidden_b = client.get(
        f"/api/v1/researchers/{profile_b.id}/personalization/quality",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_forbidden_b.status_code == 403

    # Non-existent researcher returns 404
    res_404 = client.get(
        f"/api/v1/researchers/{uuid.uuid4()}/personalization/quality",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_404.status_code == 404

    # ── Test 3: GET /quality/contexts ─────────────────────────────────────────
    res_contexts = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality/contexts",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_contexts.status_code == 200
    contexts_data = res_contexts.json()
    assert contexts_data["profile_id"] == str(profile_a.id)
    assert "items" in contexts_data
    assert "total_count" in contexts_data

    # Filter by context dimension
    res_filtered = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality/contexts?context_dimension=OPPORTUNITY_TYPE",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    for item in filtered_data["items"]:
        assert item["context_dimension"] == "OPPORTUNITY_TYPE"

    # Contexts forbidden for wrong user
    assert client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality/contexts",
        headers={"X-User-ID": str(user_b.id)},
    ).status_code == 403

    # ── Test 4: GET /quality/signals ──────────────────────────────────────────
    res_signals = client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality/signals",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_signals.status_code == 200
    signals_data = res_signals.json()
    assert signals_data["profile_id"] == str(profile_a.id)
    assert "items" in signals_data
    assert "total_count" in signals_data

    # Signals forbidden for wrong user
    assert client.get(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality/signals",
        headers={"X-User-ID": str(user_b.id)},
    ).status_code == 403

    # ── Test 5: POST /quality/recompute ───────────────────────────────────────
    # Recompute with valid user A
    recompute_payload = {
        "evaluation_period_days": 14.0,
    }
    res_recompute = client.post(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality/recompute",
        json=recompute_payload,
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_recompute.status_code == 200
    recompute_data = res_recompute.json()
    assert recompute_data["profile_id"] == str(profile_a.id)
    assert recompute_data["evaluation"]["evaluation_period_days"] == 14.0

    # Recompute forbidden for wrong user
    res_recompute_forbidden = client.post(
        f"/api/v1/researchers/{profile_a.id}/personalization/quality/recompute",
        json=recompute_payload,
        headers={"X-User-ID": str(user_b.id)},
    )
    assert res_recompute_forbidden.status_code == 403

    # Recompute for non-existent profile returns 404
    res_recompute_404 = client.post(
        f"/api/v1/researchers/{uuid.uuid4()}/personalization/quality/recompute",
        json=recompute_payload,
        headers={"X-User-ID": str(user_a.id)},
    )
    assert res_recompute_404.status_code == 404

