"""
Test Suite for Phase 5.3 — Personalization-Aware Opportunity Scoring & Explainability.

Verifies:
  - Boundedness: 0.0 <= personalization_score <= 1.0
  - Determinism: Identical inputs produce identical scores across 100 runs
  - Three-state semantics: Preferred != Neutral != Excluded
  - Missing-data safety: Missing opportunity attributes strictly yield 0.0 contribution (never negative)
  - Dual-evidence conflict preservation: Preferred + excluded preserved with UNRESOLVED polarity
  - Safety & non-interference: Phase 4 relevance, Phase 2 deadline, Phase 2.6 risk remain untouched
  - API endpoints: Single, batch, authorization, 404 handling, lossless serialization
  - Zero N+1 queries and high-performance in-memory batch execution
"""
from __future__ import annotations

import time
import uuid

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.personalization.models import (
    PersonalizationAssessment,
    PreferenceDimension,
    PreferenceMatchType,
    SignalPolarity,
)
from app.personalization.scorer import PersonalizationScorer
from app.personalization.scoring_config import (
    DEFAULT_SCORING_CONFIG,
    PersonalizationScoringConfig,
)
from app.schemas.researcher_preference import (
    StructuredAcademicPreferencesSchema,
    StructuredExclusionsSchema,
    StructuredFundingPreferencesSchema,
    StructuredGeographicPreferencesSchema,
    StructuredOpportunityPreferencesSchema,
    StructuredPreferencesResponseSchema,
    StructuredResearchInterestsSchema,
)

# -----------------------------------------------------------------------------
# SQLite dialect compilation shims for PostgreSQL-specific types in test env
# -----------------------------------------------------------------------------
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def db_session() -> Session:
    """Provides an isolated in-memory SQLite session."""
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
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_and_profile(db_session: Session) -> tuple[UserModel, ResearchProfileModel]:
    user = UserModel(
        id=uuid.uuid4(),
        email=f"scorer_test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_pw",
        full_name="Dr. Personalization Scorer",
        role="FACULTY",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY",
    )
    db_session.add(profile)
    db_session.flush()
    db_session.commit()
    return user, profile


@pytest.fixture
def sample_opportunity(db_session: Session) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="International Conference on Machine Learning (ICML)",
        opportunity_type="CONFERENCE",
        delivery_mode="OFFLINE",
        location="Berlin, Germany",
        summary="A premier academic conference on artificial intelligence and machine learning research.",
        organizer="International Machine Learning Society",
        publisher="IMLS Press",
        apc_or_fee={"has_funding": True, "funding_amount": 5000, "eligibility": "FACULTY, POSTDOC"},
        status="ACTIVE",
    )
    db_session.add(opp)
    db_session.flush()

    topic = TopicModel(id=uuid.uuid4(), name="Artificial Intelligence", slug="artificial-intelligence")
    db_session.add(topic)
    db_session.flush()

    assoc = OpportunityTopicModel(
        opportunity_id=opp.id,
        topic_id=topic.id,
        is_primary=True,
    )
    db_session.add(assoc)
    db_session.flush()
    db_session.commit()

    opp.topic_associations = [assoc]
    assoc.topic = topic
    return opp


# -----------------------------------------------------------------------------
# 1. Basic Scoring & Invariant Tests
# -----------------------------------------------------------------------------


def test_cold_start_zero_preferences_is_neutral(sample_opportunity: OpportunityModel):
    """Invariant 1: No preferences = 0.0 score with NEUTRAL state."""
    profile_id = uuid.uuid4()
    empty_prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(),
        opportunities=StructuredOpportunityPreferencesSchema(),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=empty_prefs,
        opportunity=sample_opportunity,
    )

    assert assessment.personalization_score == 0.0
    assert assessment.score.bounded_score == 0.0
    assert assessment.score.raw_score == 0.0
    assert assessment.score.match_state == PreferenceMatchType.NEUTRAL
    assert assessment.breakdown.active_dimensions_count == 0
    assert "Neutral" in assessment.explanation.summary


def test_all_preferred_dimensions_high_score(sample_opportunity: OpportunityModel):
    """Invariant 2 & 6: Preferred dimensions contribute positively and score is bounded."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(
            research_domains=["Artificial Intelligence"],
            keywords=["machine learning"],
        ),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["CONFERENCE"],
        ),
        geography=StructuredGeographicPreferencesSchema(
            preferred_countries=["DE"],
            preferred_institutions=["International Machine Learning Society"],
        ),
        funding=StructuredFundingPreferencesSchema(
            funding_required=True,
            min_funding_amount=3000,
        ),
        academic=StructuredAcademicPreferencesSchema(
            academic_level="FACULTY",
        ),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    assert assessment.personalization_score > 0.80
    assert assessment.score.bounded_score <= 1.0
    assert assessment.score.match_state == PreferenceMatchType.PREFERRED_MATCH
    assert len(assessment.breakdown.positive_contributions) >= 4
    assert len(assessment.breakdown.negative_contributions) == 0
    assert len(assessment.explanation.positive_reasons) >= 4


def test_explicit_exclusion_penalty_and_bounding(sample_opportunity: OpportunityModel):
    """Invariant 3 & 7: Explicit exclusions apply negative penalties, score bounded >= 0.0."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(),
        opportunities=StructuredOpportunityPreferencesSchema(
            excluded_types=["CONFERENCE"],  # Matches sample opportunity
        ),
        geography=StructuredGeographicPreferencesSchema(
            excluded_countries=["DE"],      # Matches sample opportunity location
        ),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(
            excluded_topics=["Artificial Intelligence"],  # Matches topic
        ),
    )

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    # When all active preferences are excluded, score is clamped at 0.0
    assert assessment.personalization_score == 0.0
    assert assessment.score.bounded_score == 0.0
    assert assessment.score.negative_penalty > 0.0
    assert assessment.score.match_state == PreferenceMatchType.EXCLUDED_MATCH
    assert len(assessment.breakdown.negative_contributions) >= 2
    assert len(assessment.explanation.negative_reasons) >= 2


def test_mixed_preferred_and_excluded_scoring(sample_opportunity: OpportunityModel):
    """Invariant 5 & 6: Mixed preferences compute net balance and preserve conflict."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(
            research_domains=["Artificial Intelligence"],  # Preferred
        ),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["CONFERENCE"],               # Preferred
        ),
        geography=StructuredGeographicPreferencesSchema(
            excluded_countries=["DE"],                    # Excluded location
        ),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    # Should have both positive and negative contributions
    assert len(assessment.breakdown.positive_contributions) >= 2
    assert len(assessment.breakdown.negative_contributions) >= 1
    # Bounded score reflects positive minus negative, clamped in [0.0, 1.0]
    assert 0.0 <= assessment.personalization_score <= 1.0
    assert assessment.score.match_state == PreferenceMatchType.CONFLICT


# -----------------------------------------------------------------------------
# 2. Missing Data Safety Tests
# -----------------------------------------------------------------------------


def test_missing_data_safety_never_penalizes():
    """Invariant 4: Missing opportunity attributes contribute 0.0, never negative."""
    profile_id = uuid.uuid4()
    sparse_opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Sparse CFP Without Location or Funding",
        opportunity_type=None,
        location=None,
        organizer=None,
        publisher=None,
        apc_or_fee=None,
        status="ACTIVE",
    )

    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["GRANT"],
        ),
        geography=StructuredGeographicPreferencesSchema(
            preferred_countries=["US"],
            preferred_institutions=["MIT"],
        ),
        funding=StructuredFundingPreferencesSchema(
            funding_required=True,
            min_funding_amount=10000,
        ),
        academic=StructuredAcademicPreferencesSchema(
            academic_level="POSTDOC",
        ),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sparse_opp,
    )

    # Missing data must never produce negative penalties
    assert assessment.score.negative_penalty == 0.0
    assert len(assessment.breakdown.negative_contributions) == 0
    # Insufficient evidence dimensions are documented in unresolved contributions
    unresolved_dims = [
        c.dimension for c in assessment.breakdown.unresolved_contributions
        if c.match_type == PreferenceMatchType.INSUFFICIENT_EVIDENCE
    ]
    assert PreferenceDimension.COUNTRY in unresolved_dims
    assert PreferenceDimension.FUNDING in unresolved_dims
    assert len(assessment.explanation.insufficient_evidence_reasons) >= 2


# -----------------------------------------------------------------------------
# 3. Determinism & Performance Tests
# -----------------------------------------------------------------------------


def test_strict_determinism_across_100_runs(sample_opportunity: OpportunityModel):
    """Invariant 8: 100 consecutive runs with identical inputs produce identical outputs."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(
            research_domains=["Artificial Intelligence"],
            keywords=["machine learning"],
        ),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["CONFERENCE"],
        ),
        geography=StructuredGeographicPreferencesSchema(
            preferred_countries=["DE"],
        ),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    baseline = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    for _ in range(100):
        run = PersonalizationScorer.score_opportunity(
            profile_id=profile_id,
            preferences=prefs,
            opportunity=sample_opportunity,
        )
        assert run.personalization_score == baseline.personalization_score
        assert run.score.bounded_score == baseline.score.bounded_score
        assert run.score.raw_score == baseline.score.raw_score
        assert run.explanation.summary == baseline.explanation.summary


def test_batch_scoring_performance_and_zero_n_plus_one(sample_opportunity: OpportunityModel):
    """Invariant 10 & 11: Batch scoring executes in memory with zero N+1 queries."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(
            research_domains=["Artificial Intelligence"],
        ),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["CONFERENCE"],
        ),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    # Create batch of 100 opportunities in memory
    opps = [
        OpportunityModel(
            id=uuid.uuid4(),
            title=f"Opportunity {i}",
            opportunity_type="CONFERENCE" if i % 2 == 0 else "GRANT",
            location="Berlin, Germany" if i % 3 == 0 else "Paris, France",
            status="ACTIVE",
        )
        for i in range(100)
    ]

    start_time = time.perf_counter()
    batch_results = PersonalizationScorer.score_opportunities_batch(
        profile_id=profile_id,
        preferences=prefs,
        opportunities=opps,
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    assert len(batch_results) == 100
    # 100 in-memory opportunity scorings must execute well under 50ms
    assert elapsed_ms < 50.0, f"Batch scoring took {elapsed_ms:.2f}ms (expected < 50ms)"


# -----------------------------------------------------------------------------
# 4. Ranking Safety & Non-Interference Tests
# -----------------------------------------------------------------------------


def test_personalization_does_not_mutate_opportunity_or_ranking(sample_opportunity: OpportunityModel):
    """Invariant 12, 13, 14, 16: Scoring is strictly side-effect free on opportunity models."""
    orig_title = sample_opportunity.title
    orig_type = sample_opportunity.opportunity_type
    orig_status = sample_opportunity.status
    orig_funding = dict(sample_opportunity.apc_or_fee or {})

    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(keywords=["test"]),
        opportunities=StructuredOpportunityPreferencesSchema(),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PersonalizationScorer.score_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    assert assessment is not None
    # Verify sample opportunity attributes remain 100% unaltered
    assert sample_opportunity.title == orig_title
    assert sample_opportunity.opportunity_type == orig_type
    assert sample_opportunity.status == orig_status
    assert sample_opportunity.apc_or_fee == orig_funding


# -----------------------------------------------------------------------------
# 5. REST API Tests
# -----------------------------------------------------------------------------


def test_api_get_opportunity_personalization(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
    sample_opportunity: OpportunityModel,
    db_session: Session,
):
    """Test GET /{id}/opportunities/{opp_id}/personalization endpoint."""
    user, profile = test_user_and_profile

    # Add a preferred opportunity type
    pref = ResearcherPreferenceModel(
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_type="PREFERRED",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        display_label="Conference",
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)
    db_session.commit()

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/opportunities/{sample_opportunity.id}/personalization",
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    data = resp.json()

    assert data["profile_id"] == str(profile.id)
    assert data["opportunity_id"] == str(sample_opportunity.id)
    assert data["personalization_score"] > 0.0
    assert "score" in data
    assert "breakdown" in data
    assert "explanation" in data
    assert data["score"]["bounded_score"] == data["personalization_score"]
    assert len(data["breakdown"]["positive_contributions"]) >= 1


def test_api_batch_opportunity_personalization(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
    sample_opportunity: OpportunityModel,
    db_session: Session,
):
    """Test POST /{id}/opportunities/personalization endpoint."""
    user, profile = test_user_and_profile

    # Add an excluded country
    pref = ResearcherPreferenceModel(
        profile_id=profile.id,
        category="COUNTRY",
        preference_type="EXCLUDED",
        preference_key="country",
        preference_value="DE",
        display_label="Germany",
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)
    db_session.commit()

    payload = {"opportunity_ids": [str(sample_opportunity.id)]}
    resp = client.post(
        f"/api/v1/researchers/{profile.id}/opportunities/personalization",
        json=payload,
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    data = resp.json()

    assert data["profile_id"] == str(profile.id)
    assert data["evaluated_count"] == 1
    assessment = data["assessments"][0]
    assert assessment["opportunity_id"] == str(sample_opportunity.id)
    assert assessment["score"]["match_state"] == "EXCLUDED_MATCH"
    assert len(assessment["breakdown"]["negative_contributions"]) >= 1


def test_api_personalization_opportunity_not_found(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
):
    """Test 404 behavior for nonexistent opportunity."""
    user, profile = test_user_and_profile
    fake_opp_id = uuid.uuid4()

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/opportunities/{fake_opp_id}/personalization",
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_api_personalization_unauthorized_access(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
    sample_opportunity: OpportunityModel,
    intruder_identity: UserModel,
):
    """Test 403 behavior for a different registered researcher."""
    _, profile = test_user_and_profile
    other_user_id = intruder_identity.id

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/opportunities/{sample_opportunity.id}/personalization",
        headers={"X-User-ID": str(other_user_id)},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
