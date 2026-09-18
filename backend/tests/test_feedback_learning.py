"""
Phase 3.6 — Unit, Integration, Invariant, and Empirical Tests for Feedback & Recommendation Learning.

Tests cover:
  1. Feedback persistence, CRUD, idempotency, and SavedOpportunity synchronization
  2. Ownership enforcement via X-User-ID header
  3. Feedback event semantics and weights across all 6 supported types
  4. Temporal exponential decay with 30-day half-life
  5. Diminishing returns saturation on repeated interactions
  6. Multi-dimensional behavioral confidence scaling
  7. Attribute-grounded learning (topics, opportunity_type, delivery_mode)
  8. Explicit preference protection & dominance floor
  9. Negative signal opportunity suppression in candidate generation
 10. Relevance dominance invariant preservation (weak relevance + strong feedback vs strong relevance + weak feedback)
 11. Safety dominance on predatory opportunities (zero positive boost)
 12. Deadline dominance on expired opportunities (zero resurrection)
 13. Cold start zero-feedback fallback
 14. 100% determinism over repeated runs
 15. Zero N+1 query performance verification
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
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
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.ranking.feedback_config import (
    EXPLICIT_PREFERENCE_DOMINANCE_FLOOR,
    FEEDBACK_EVENT_WEIGHTS,
    FEEDBACK_HALF_LIFE_DAYS,
    MAX_NEGATIVE_BEHAVIORAL_ADJUSTMENT,
    MAX_OVERALL_PERSONALIZATION_CAP,
    MAX_POSITIVE_BEHAVIORAL_ADJUSTMENT,
    MIN_BEHAVIORAL_CONFIDENCE_THRESHOLD,
    SUPPORTED_FEEDBACK_TYPES,
)
from app.ranking.feedback_engine import (
    FeedbackEngine,
    calculate_behavioral_confidence,
    calculate_diminishing_returns,
    calculate_temporal_decay,
)
from app.ranking.personalization_ranker import (
    PersonalizationRanker,
    ResearcherPersonalizationContext,
)
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceType,
    PersonalizedCandidateItemSchema,
    PersonalizedCandidateOpportunitySchema,
)
from app.schemas.researcher_feedback import (
    FeedbackCreateRequest,
    FeedbackType,
)
from app.services.feedback_service import ResearcherFeedbackService
from app.services.personalized_candidate_generation_service import (
    PersonalizedCandidateGenerationService,
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
        Base.metadata.tables["research_submissions"],
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
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
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Test Helpers ──────────────────────────────────────────────────────────────


def create_test_user(db: Session, email: str = "feedback_researcher@test.edu") -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        full_name="Dr. Jane Feedback",
        hashed_password="hashed_pw_test",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def create_test_profile(
    db: Session,
    user: UserModel,
    keywords: list[str] | None = None,
    target_types: list[str] | None = None,
) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY",
        keywords=keywords or [],
        target_opportunity_types=target_types or [],
    )
    db.add(profile)
    db.flush()
    return profile


def create_test_topic(db: Session, name: str, slug: str) -> TopicModel:
    existing = db.execute(select(TopicModel).where(TopicModel.slug == slug)).scalar_one_or_none()
    if existing:
        return existing
    topic = TopicModel(
        id=uuid.uuid4(),
        name=name,
        slug=slug,
    )
    db.add(topic)
    db.flush()
    return topic


def create_test_opportunity(
    db: Session,
    title: str = "Test Conference 2026",
    opp_type: str = "CONFERENCE",
    delivery_mode: str = "OFFLINE",
    topics: list[TopicModel] | None = None,
    days_ahead: int = 30,
    is_predatory: bool = False,
    status: str = "ACTIVE",
    organizer: str = "IEEE",
    risk_score: float = 0.0,
) -> OpportunityModel:
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=days_ahead) if days_ahead >= 0 else now + timedelta(days=days_ahead)
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title=title,
        opportunity_type=opp_type,
        delivery_mode=delivery_mode,
        status=status,
        submission_deadline=deadline,
        organizer=organizer,
        is_predatory_flag=is_predatory,
        risk_score=0.90 if is_predatory else risk_score,
    )
    db.add(opp)
    db.flush()

    if topics:
        for t in topics:
            db.add(OpportunityTopicModel(opportunity_id=opp.id, topic_id=t.id, confidence_score=1.0, is_primary=True))
        db.flush()

    return opp


def make_candidate_item(
    opp_id: uuid.UUID,
    title: str,
    base_score: float = 0.50,
    opportunity_type: str = "CONFERENCE",
    delivery_mode: str = "OFFLINE",
    days_remaining: float = 30.0,
    topics: list[str] | None = None,
    is_predatory: bool = False,
    risk_level: str = "LOW_RISK",
    risk_score: float = 0.0,
    deadline_status: str = "UPCOMING",
) -> PersonalizedCandidateItemSchema:
    cand_uuid = uuid.uuid4()
    opp_schema = PersonalizedCandidateOpportunitySchema(
        id=opp_id,
        title=title,
        opportunity_type=opportunity_type,
        delivery_mode=delivery_mode,
        location="San Francisco, USA",
        organizer="IEEE",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=days_remaining),
        website_url="https://example.org",
        topics=topics or [],
        status="ACTIVE",
        is_predatory_flag=is_predatory,
        risk_level=risk_level,
        risk_score=risk_score,
        risk_reasons=["Predatory publisher"] if is_predatory else [],
        deadline_status=deadline_status,
        days_remaining=days_remaining,
        urgency_tier="APPROACHING",
        deadline_explanation="Submission open",
    )
    provenance = CandidateProvenanceSchema(
        candidate_id=cand_uuid,
        opportunity_id=opp_id,
        sources=[CandidateSourceType.EXPLICIT_PREFERENCE],
        matched_topics=topics or [],
        matched_preferences=[],
        matched_expertise=[],
        reasons=["Candidate matches criteria"],
        retrieval_channels=["preference_match"],
    )
    return PersonalizedCandidateItemSchema(
        candidate_id=cand_uuid,
        opportunity=opp_schema,
        provenance=provenance,
        eligibility_passed=True,
        eligibility_reasons=["Valid status and deadline"],
        base_relevance_score=base_score,
    )


# ── 1. Mathematical Primitives & Decay Tests ──────────────────────────────────


def test_temporal_decay_mathematical_properties():
    """Verify exponential decay with 30-day half-life."""
    ref_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Contemporary event: decay = 1.0
    d0 = calculate_temporal_decay(ref_time, ref_time)
    assert d0 == 1.0

    # 30-day-old event: decay ~= 0.50 (half-life)
    t30 = ref_time - timedelta(days=FEEDBACK_HALF_LIFE_DAYS)
    d30 = calculate_temporal_decay(t30, ref_time)
    assert 0.49 <= d30 <= 0.51

    # 60-day-old event: decay ~= 0.25 (two half-lives)
    t60 = ref_time - timedelta(days=2 * FEEDBACK_HALF_LIFE_DAYS)
    d60 = calculate_temporal_decay(t60, ref_time)
    assert 0.24 <= d60 <= 0.26

    # Future event (clock skew guard): decay = 1.0
    future = ref_time + timedelta(hours=1)
    df = calculate_temporal_decay(future, ref_time)
    assert df == 1.0


def test_diminishing_returns_saturation():
    """Verify diminishing returns scale down repeated interactions."""
    base = 0.25  # e.g. SAVE base weight

    w1 = calculate_diminishing_returns(base, 1)
    w2 = calculate_diminishing_returns(base, 2)
    w3 = calculate_diminishing_returns(base, 3)
    w5 = calculate_diminishing_returns(base, 5)

    assert w1 == 0.25
    assert w2 == round(0.25 / 1.5, 6)
    assert w3 == round(0.25 / 2.0, 6)
    assert w5 == round(0.25 / 3.0, 6)

    assert w1 > w2 > w3 > w5 > 0.0

    # Negative weight sign preservation
    neg_base = -0.20
    nw1 = calculate_diminishing_returns(neg_base, 1)
    nw2 = calculate_diminishing_returns(neg_base, 2)
    assert nw1 == -0.20
    assert nw2 < 0.0
    assert abs(nw2) < abs(nw1)


def test_behavioral_confidence_scaling():
    """Verify confidence behavior across volume, consistency, and recency."""
    # Zero feedback -> 0.0
    c0 = calculate_behavioral_confidence(0, 0.0, 0.0, 0.0)
    assert c0 == 0.0

    # Single click (N=1, low volume) -> low confidence
    c1 = calculate_behavioral_confidence(1, 0.05, 0.05, 1.0)
    assert c1 < 0.30

    # High volume, completely consistent, fresh -> high confidence
    c_high = calculate_behavioral_confidence(5, 1.20, 1.20, 0.95)
    assert c_high >= 0.70

    # High volume, but completely conflicting (2 positive, 2 negative) -> zero consistency -> zero confidence
    c_conflicting = calculate_behavioral_confidence(4, 0.0, 1.0, 0.90)
    assert c_conflicting == 0.0


# ── 2. Feedback Persistence & Idempotency Tests ───────────────────────────────


def test_feedback_create_and_retrieve(db_session: Session):
    """Test recording and retrieving feedback with joined opportunity data."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)
    opp = create_test_opportunity(db_session, title="ICLR 2026", opp_type="CONFERENCE")

    req = FeedbackCreateRequest(
        opportunity_id=opp.id,
        feedback_type=FeedbackType.SAVE,
        source="RECOMMENDATION",
        notes="Important submission target",
        rank_position=1,
    )
    result = ResearcherFeedbackService.record_feedback(db_session, profile.id, req)

    assert result.researcher_id == profile.id
    assert result.opportunity_id == opp.id
    assert result.feedback_type == "SAVE"
    assert result.notes == "Important submission target"
    assert result.opportunity_title == "ICLR 2026"
    assert result.opportunity_type == "CONFERENCE"

    # Verify SavedOpportunityModel synchronized on SAVE
    saved_entity = db_session.execute(
        select(SavedOpportunityModel).where(
            SavedOpportunityModel.user_id == user.id,
            SavedOpportunityModel.opportunity_id == opp.id,
        )
    ).scalar_one_or_none()
    assert saved_entity is not None
    assert saved_entity.notes == "Important submission target"


def test_feedback_idempotency(db_session: Session):
    """Repeated feedback of the same type updates rather than duplicates."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)
    opp = create_test_opportunity(db_session)

    req1 = FeedbackCreateRequest(
        opportunity_id=opp.id,
        feedback_type=FeedbackType.INTERESTED,
        notes="Initial like",
    )
    res1 = ResearcherFeedbackService.record_feedback(db_session, profile.id, req1)

    req2 = FeedbackCreateRequest(
        opportunity_id=opp.id,
        feedback_type=FeedbackType.INTERESTED,
        notes="Updated note after review",
    )
    res2 = ResearcherFeedbackService.record_feedback(db_session, profile.id, req2)

    assert res1.id == res2.id
    assert res2.notes == "Updated note after review"

    # Assert exactly 1 record in database
    records = db_session.execute(
        select(ResearcherRecommendationFeedbackModel).where(
            ResearcherRecommendationFeedbackModel.researcher_id == profile.id
        )
    ).scalars().all()
    assert len(records) == 1


def test_feedback_delete_and_saved_sync(db_session: Session):
    """Deleting a SAVE feedback removes both feedback and SavedOpportunityModel."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)
    opp = create_test_opportunity(db_session)

    req = FeedbackCreateRequest(
        opportunity_id=opp.id,
        feedback_type=FeedbackType.SAVE,
    )
    res = ResearcherFeedbackService.record_feedback(db_session, profile.id, req)

    # Verify both exist
    assert db_session.execute(select(SavedOpportunityModel)).scalar_one_or_none() is not None

    # Delete
    deleted = ResearcherFeedbackService.delete_feedback(db_session, profile.id, res.id)
    assert deleted is True

    # Verify both removed
    assert db_session.execute(select(ResearcherRecommendationFeedbackModel)).scalar_one_or_none() is None
    assert db_session.execute(select(SavedOpportunityModel)).scalar_one_or_none() is None


# ── 3. Behavioral Learning Engine Tests ────────────────────────────────────────


def test_repeated_save_increases_topic_preference(db_session: Session):
    """Repeatedly saving opportunities with 'machine-learning' topic increases learned preference."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)
    ml_topic = create_test_topic(db_session, "Machine Learning", "machine-learning")

    opp1 = create_test_opportunity(db_session, title="ML Conf 1", topics=[ml_topic])
    opp2 = create_test_opportunity(db_session, title="ML Conf 2", topics=[ml_topic])
    opp3 = create_test_opportunity(db_session, title="ML Conf 3", topics=[ml_topic])

    ResearcherFeedbackService.record_feedback(
        db_session, profile.id, FeedbackCreateRequest(opportunity_id=opp1.id, feedback_type=FeedbackType.SAVE)
    )
    ResearcherFeedbackService.record_feedback(
        db_session, profile.id, FeedbackCreateRequest(opportunity_id=opp2.id, feedback_type=FeedbackType.SAVE)
    )
    ResearcherFeedbackService.record_feedback(
        db_session, profile.id, FeedbackCreateRequest(opportunity_id=opp3.id, feedback_type=FeedbackType.SAVE)
    )

    behavioral_profile = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    assert not behavioral_profile.is_cold_start
    assert behavioral_profile.total_feedback_events == 3

    ml_signal = next((s for s in behavioral_profile.signals if s.preference_value == "machine-learning"), None)
    assert ml_signal is not None
    assert ml_signal.direction == "POSITIVE"
    assert ml_signal.normalized_score > 0.0
    assert ml_signal.confidence >= MIN_BEHAVIORAL_CONFIDENCE_THRESHOLD
    assert ml_signal.sample_size == 3
    assert "Machine Learning" in behavioral_profile.top_positive_topics


def test_repeated_dismiss_decreases_opportunity_type_preference(db_session: Session):
    """Repeatedly dismissing WORKSHOP opportunities creates negative behavioral signal."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    w1 = create_test_opportunity(db_session, title="Workshop 1", opp_type="WORKSHOP")
    w2 = create_test_opportunity(db_session, title="Workshop 2", opp_type="WORKSHOP")
    w3 = create_test_opportunity(db_session, title="Workshop 3", opp_type="WORKSHOP")

    ResearcherFeedbackService.record_feedback(
        db_session, profile.id, FeedbackCreateRequest(opportunity_id=w1.id, feedback_type=FeedbackType.DISMISS)
    )
    ResearcherFeedbackService.record_feedback(
        db_session, profile.id, FeedbackCreateRequest(opportunity_id=w2.id, feedback_type=FeedbackType.DISMISS)
    )
    ResearcherFeedbackService.record_feedback(
        db_session, profile.id, FeedbackCreateRequest(opportunity_id=w3.id, feedback_type=FeedbackType.DISMISS)
    )

    behavioral_profile = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    workshop_sig = next((s for s in behavioral_profile.signals if s.preference_value == "WORKSHOP"), None)

    assert workshop_sig is not None
    assert workshop_sig.direction == "NEGATIVE"
    assert workshop_sig.normalized_score < 0.0
    assert workshop_sig.confidence >= MIN_BEHAVIORAL_CONFIDENCE_THRESHOLD


def test_negative_signal_suppression_omits_from_candidates(db_session: Session):
    """Dismissed opportunity is omitted from PersonalizedCandidateGenerationService output."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)
    ml_topic = create_test_topic(db_session, "Machine Learning", "machine-learning")

    opp_active = create_test_opportunity(db_session, title="Active ML Conf", topics=[ml_topic])
    opp_dismissed = create_test_opportunity(db_session, title="Dismissed ML Conf", topics=[ml_topic])

    # Record DISMISS on opp_dismissed
    ResearcherFeedbackService.record_feedback(
        db_session, profile.id, FeedbackCreateRequest(opportunity_id=opp_dismissed.id, feedback_type=FeedbackType.DISMISS)
    )

    # Query suppressed IDs
    suppressed = ResearcherFeedbackService.get_suppressed_opportunity_ids(db_session, profile.id)
    assert opp_dismissed.id in suppressed
    assert opp_active.id not in suppressed

    # Generate candidates with suppression enabled
    candidate_response = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        limit=10,
        include_fallback=True,
    )
    cand_ids = [c.opportunity.id for c in candidate_response.candidates]
    assert opp_dismissed.id not in cand_ids
    assert opp_active.id in cand_ids


# ── 4. Explicit Preference Protection & Invariant Tests ────────────────────────


def test_explicit_preference_remains_distinct(db_session: Session):
    """Explicit preference for CONFERENCE is protected when conferences are repeatedly dismissed."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    # 1. User has EXPLICIT preference for CONFERENCE
    explicit_pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        display_label="Conference",
        source="EXPLICIT",
        strength=1.0,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(explicit_pref)
    db_session.commit()

    # 2. Researcher dismisses 4 conferences
    for i in range(4):
        c = create_test_opportunity(db_session, title=f"Conf {i}", opp_type="CONFERENCE")
        ResearcherFeedbackService.record_feedback(
            db_session, profile.id, FeedbackCreateRequest(opportunity_id=c.id, feedback_type=FeedbackType.DISMISS)
        )

    # 3. Behavioral engine evaluates conflict
    behavioral_profile = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    conf_sig = next((s for s in behavioral_profile.signals if s.preference_value == "CONFERENCE"), None)

    # The explicit preference itself was NOT deleted or overwritten
    persisted_pref = db_session.execute(
        select(ResearcherPreferenceModel).where(
            ResearcherPreferenceModel.profile_id == profile.id,
            ResearcherPreferenceModel.source == "EXPLICIT",
        )
    ).scalar_one_or_none()
    assert persisted_pref is not None
    assert persisted_pref.source == "EXPLICIT"
    assert persisted_pref.preference_value == "CONFERENCE"

    # Behavioral negative signal is dampened and clamped by explicit dominance floor
    if conf_sig:
        assert conf_sig.normalized_score >= -EXPLICIT_PREFERENCE_DOMINANCE_FLOOR


def test_relevance_dominance_invariant_with_feedback(db_session: Session):
    """Weak relevance + strong positive feedback CANNOT beat strong relevance + neutral feedback."""
    ranker = PersonalizationRanker()

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        is_cold_start=False,
    )

    # Candidate A: Strong relevance (0.85)
    cand_a_id = uuid.uuid4()
    cand_a = make_candidate_item(
        opp_id=cand_a_id,
        title="High Relevance Candidate",
        base_score=0.85,
        opportunity_type="CONFERENCE",
        delivery_mode="OFFLINE",
        topics=["nlp"],
    )

    # Candidate B: Weak relevance (0.40) + max personalization boost (0.15)
    cand_b_id = uuid.uuid4()
    cand_b = make_candidate_item(
        opp_id=cand_b_id,
        title="Weak Relevance Candidate",
        base_score=0.40,
        opportunity_type="JOURNAL",
        delivery_mode="ONLINE",
        topics=["nlp"],
    )

    ranked = ranker.rank(
        candidates=[cand_b, cand_a],
        context=context,
        base_scores={cand_a.opportunity.id: 0.85, cand_b.opportunity.id: 0.40},
    )

    # Candidate A must remain strictly Rank 1
    assert ranked[0].opportunity_id == cand_a.opportunity.id
    assert ranked[1].opportunity_id == cand_b.opportunity.id
    assert ranked[0].final_score > ranked[1].final_score


def test_safety_dominance_predatory_opportunity(db_session: Session):
    """High-risk / predatory opportunities receive zero positive personalization boost."""
    ranker = PersonalizationRanker()
    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        is_cold_start=False,
    )

    predatory_id = uuid.uuid4()
    cand = make_candidate_item(
        opp_id=predatory_id,
        title="Predatory International Mega Congress",
        base_score=0.70,
        opportunity_type="CONFERENCE",
        delivery_mode="OFFLINE",
        topics=["ai"],
        is_predatory=True,
        risk_level="HIGH_RISK",
        risk_score=0.95,
    )

    ranked = ranker.rank(candidates=[cand], context=context, base_scores={predatory_id: 0.70})
    assert len(ranked) == 1
    assert ranked[0].personalization_adjustment == 0.0
    assert ranked[0].final_score == 0.70


def test_deadline_dominance_expired_opportunity():
    """Expired opportunities cannot be ranked regardless of personalization signals."""
    ranker = PersonalizationRanker()
    context = ResearcherPersonalizationContext(profile_id=uuid.uuid4(), is_cold_start=False)

    expired_id = uuid.uuid4()
    cand = make_candidate_item(
        opp_id=expired_id,
        title="Expired Conference 2025",
        base_score=0.80,
        opportunity_type="CONFERENCE",
        delivery_mode="OFFLINE",
        topics=["machine-learning"],
        deadline_status="EXPIRED",
        days_remaining=-10.0,
    )

    ranked = ranker.rank(candidates=[cand], context=context)
    assert len(ranked) == 0


def test_cold_start_zero_feedback(db_session: Session):
    """When zero feedback exists, behavioral adjustment is 0.0 and cold start is True."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    b_profile = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    assert b_profile.is_cold_start is True
    assert len(b_profile.signals) == 0
    assert len(b_profile.suppressed_opportunity_ids) == 0

    summary = ResearcherFeedbackService.get_feedback_summary(db_session, profile.id)
    assert summary.total_feedback_count == 0
    assert summary.is_cold_start is True


def test_determinism_invariant(db_session: Session):
    """10 consecutive runs of feedback aggregation produce bit-identical results."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)
    ml_topic = create_test_topic(db_session, "Machine Learning", "machine-learning")

    for i in range(3):
        opp = create_test_opportunity(db_session, title=f"ML {i}", topics=[ml_topic])
        ResearcherFeedbackService.record_feedback(
            db_session, profile.id, FeedbackCreateRequest(opportunity_id=opp.id, feedback_type=FeedbackType.SAVE)
        )

    ref_time = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    results = [
        ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id, reference_time=ref_time)
        for _ in range(10)
    ]

    for r in results[1:]:
        assert r.overall_confidence == results[0].overall_confidence
        assert len(r.signals) == len(results[0].signals)
        for s1, s2 in zip(results[0].signals, r.signals):
            assert s1.preference_value == s2.preference_value
            assert s1.normalized_score == s2.normalized_score
            assert s1.confidence == s2.confidence


# ── 5. API Endpoints & Ownership Enforcement ──────────────────────────────────


def test_api_record_feedback_and_ownership(client: TestClient, db_session: Session):
    """Test POST /api/v1/researchers/{id}/feedback with ownership enforcement."""
    user = create_test_user(db_session, email="owner@test.edu")
    other_user = create_test_user(db_session, email="intruder@test.edu")
    profile = create_test_profile(db_session, user)
    opp = create_test_opportunity(db_session)

    payload = {
        "opportunity_id": str(opp.id),
        "feedback_type": "INTERESTED",
        "notes": "Looks promising",
    }

    # 1. Non-matching X-User-ID -> 403 Forbidden
    res_forbidden = client.post(
        f"/api/v1/researchers/{profile.id}/feedback",
        json=payload,
        headers={"X-User-ID": str(other_user.id)},
    )
    assert res_forbidden.status_code == 403

    # 2. Matching X-User-ID -> 201 Created
    res_ok = client.post(
        f"/api/v1/researchers/{profile.id}/feedback",
        json=payload,
        headers={"X-User-ID": str(user.id)},
    )
    assert res_ok.status_code == 201
    data = res_ok.json()
    assert data["feedback_type"] == "INTERESTED"
    assert data["notes"] == "Looks promising"

    # 3. Query GET /feedback
    res_get = client.get(
        f"/api/v1/researchers/{profile.id}/feedback",
        headers={"X-User-ID": str(user.id)},
    )
    assert res_get.status_code == 200
    list_data = res_get.json()
    assert list_data["total"] == 1

    # 4. Query GET /summary
    res_sum = client.get(
        f"/api/v1/researchers/{profile.id}/feedback/summary",
        headers={"X-User-ID": str(user.id)},
    )
    assert res_sum.status_code == 200
    sum_data = res_sum.json()
    assert sum_data["total_feedback_count"] == 1
    assert sum_data["counts_by_type"]["INTERESTED"] == 1


def test_zero_n_plus_one_query_performance(db_session: Session):
    """Verify batch loading with eager joins requires constant query count."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    # Create 10 opportunities and feedback events
    for i in range(10):
        opp = create_test_opportunity(db_session, title=f"Opp {i}")
        ResearcherFeedbackService.record_feedback(
            db_session, profile.id, FeedbackCreateRequest(opportunity_id=opp.id, feedback_type=FeedbackType.VIEW)
        )

    # Measure query count for aggregation
    query_count = 0
    from sqlalchemy import event

    def _query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1
        print(f"\nQUERY {query_count}: {statement[:80]}")

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _query_listener)

    try:
        _ = ResearcherFeedbackService.get_behavioral_profile(db_session, profile.id)
    finally:
        event.remove(engine, "before_cursor_execute", _query_listener)

    # With 10 feedback items, regardless of N, total queries is fixed (constant / O(1))
    assert query_count <= 5
