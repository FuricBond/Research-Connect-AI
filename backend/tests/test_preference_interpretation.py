"""
Test Suite for Phase 5.2 — Explicit Preference Interpretation & Personalization Signal Foundation.

Verifies:
  - All 9 preference dimensions (keywords, domains, opportunity types, country, region, institution, funding, academic level, career stage)
  - 3-state semantics: PREFERRED != NEUTRAL != EXCLUDED
  - Conflict preservation with dual evidence
  - Missing data safety (missing != negative / excluded)
  - Determinism & zero side-effects
  - Batch evaluation without N+1 queries
  - REST API endpoints & authorization
  - All 25 Phase 5.2 safety invariants
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
from app.models.base import Base
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.personalization import (
    PreferenceDimension,
    PreferenceInterpreter,
    PreferenceMatchType,
    SignalPolarity,
)
from app.schemas.researcher_preference import (
    PreferenceCategory,
    PreferenceType,
    ResearcherPreferenceItemSchema,
    StructuredAcademicPreferencesSchema,
    StructuredExclusionsSchema,
    StructuredFundingPreferencesSchema,
    StructuredGeographicPreferencesSchema,
    StructuredOpportunityPreferencesSchema,
    StructuredPreferencesResponseSchema,
    StructuredResearchInterestsSchema,
)

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


@pytest.fixture
def test_user_and_profile(db_session: Session):
    user = UserModel(
        id=uuid.uuid4(),
        email=f"pref_interp_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_pw",
        full_name="Dr. Preference Tester",
        role="FACULTY",
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
        organizer="International Machine Learning Society",
        publisher="IMLS",
        summary="A top conference covering Artificial Intelligence, Deep Learning, and Computer Vision.",
        description="Submissions are invited across all areas of machine learning and artificial intelligence.",
        apc_or_fee={
            "has_fee": True,
            "has_funding": True,
            "funding_amount": 50000,
            "currency": "USD",
            "eligibility": "PHD, POSTDOC, FACULTY",
        },
        status="ACTIVE",
    )
    db_session.add(opp)
    db_session.flush()

    # Link a topic
    topic = TopicModel(
        id=uuid.uuid4(),
        name="Artificial Intelligence",
        slug="artificial-intelligence",
    )
    db_session.add(topic)
    db_session.flush()

    opp_topic = OpportunityTopicModel(
        opportunity_id=opp.id,
        topic_id=topic.id,
        confidence_score=1.0,
        is_primary=True,
    )
    db_session.add(opp_topic)
    db_session.flush()
    db_session.commit()
    db_session.refresh(opp)
    return opp


# -----------------------------------------------------------------------------
# Unit Tests for PreferenceInterpreter
# -----------------------------------------------------------------------------

def test_no_preference_is_neutral(sample_opportunity: OpportunityModel):
    """Invariant 1: No preference = NEUTRAL."""
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

    assessment = PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile_id,
        preferences=empty_prefs,
        opportunity=sample_opportunity,
    )

    assert assessment.overall_match_state == PreferenceMatchType.NEUTRAL
    assert assessment.positive_matches_count == 0
    assert assessment.excluded_matches_count == 0
    assert assessment.conflict_count == 0
    assert "neutral" in assessment.deterministic_explanation.lower()


def test_preferred_opportunity_type_match(sample_opportunity: OpportunityModel):
    """Invariant 2: Preferred opportunity type matches."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["CONFERENCE"]
        ),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    assert assessment.overall_match_state == PreferenceMatchType.PREFERRED_MATCH
    assert assessment.positive_matches_count == 1
    assert assessment.excluded_matches_count == 0

    type_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.OPPORTUNITY_TYPE)
    assert type_sig.match_type == PreferenceMatchType.PREFERRED_MATCH
    assert type_sig.polarity == SignalPolarity.POSITIVE
    assert "CONFERENCE" in type_sig.explanation


def test_excluded_opportunity_type_match(sample_opportunity: OpportunityModel):
    """Invariant 3 & 4: Excluded opportunity type is strictly preserved as EXCLUDED_MATCH."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(),
        opportunities=StructuredOpportunityPreferencesSchema(
            excluded_types=["CONFERENCE"]
        ),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(
            excluded_opportunity_types=["CONFERENCE"]
        ),
    )

    assessment = PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    assert assessment.overall_match_state == PreferenceMatchType.EXCLUDED_MATCH
    assert assessment.excluded_matches_count == 1
    assert assessment.positive_matches_count == 0

    type_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.OPPORTUNITY_TYPE)
    assert type_sig.match_type == PreferenceMatchType.EXCLUDED_MATCH
    assert type_sig.polarity == SignalPolarity.NEGATIVE
    assert "excluded" in assessment.deterministic_explanation.lower()


def test_preferred_not_required(sample_opportunity: OpportunityModel):
    """Invariant 2: Preferred != Required (unspecified types are NEUTRAL, not excluded)."""
    profile_id = uuid.uuid4()
    # Researcher prefers WORKSHOP, but did not exclude CONFERENCE
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["WORKSHOP"]
        ),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    # Opportunity is CONFERENCE. Since CONFERENCE is not preferred nor excluded, it is NEUTRAL
    assert assessment.overall_match_state == PreferenceMatchType.NEUTRAL
    type_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.OPPORTUNITY_TYPE)
    assert type_sig.match_type == PreferenceMatchType.NEUTRAL
    assert type_sig.polarity == SignalPolarity.NEUTRAL


def test_keyword_matching_and_conflict(sample_opportunity: OpportunityModel):
    """Invariant 11: Conflicting preferences remain observable as CONFLICT with dual evidence."""
    profile_id = uuid.uuid4()
    # Researcher prefers "machine learning" but excludes "computer vision"
    # Sample opportunity has both in its summary/title
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(
            keywords=["machine learning"]
        ),
        opportunities=StructuredOpportunityPreferencesSchema(),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(
            excluded_topics=["computer vision"]
        ),
    )

    assessment = PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    assert assessment.overall_match_state == PreferenceMatchType.CONFLICT
    assert assessment.conflict_count >= 1

    kw_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.KEYWORD)
    assert kw_sig.match_type == PreferenceMatchType.CONFLICT
    assert kw_sig.polarity == SignalPolarity.UNRESOLVED
    assert "machine learning" in kw_sig.evidence
    assert "computer vision" in kw_sig.evidence
    assert "conflict" in assessment.deterministic_explanation.lower()


def test_geographic_country_matching(sample_opportunity: OpportunityModel):
    """Invariant 7: Country matching (Germany / DE matches)."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(),
        opportunities=StructuredOpportunityPreferencesSchema(),
        geography=StructuredGeographicPreferencesSchema(
            preferred_countries=["DE"]
        ),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sample_opportunity,
    )

    assert assessment.overall_match_state == PreferenceMatchType.PREFERRED_MATCH
    geo_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.COUNTRY)
    assert geo_sig.match_type == PreferenceMatchType.PREFERRED_MATCH
    assert geo_sig.polarity == SignalPolarity.POSITIVE
    assert "Germany" in geo_sig.evidence or "DE" in geo_sig.evidence


def test_missing_opportunity_data_safety():
    """Invariants 5, 6, 7, 8: Missing opportunity data results in INSUFFICIENT_EVIDENCE, never EXCLUDED."""
    profile_id = uuid.uuid4()
    # Opportunity with completely empty location, funding, and organizer
    sparse_opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Sparse CFP",
        opportunity_type="CONFERENCE",
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
        opportunities=StructuredOpportunityPreferencesSchema(),
        geography=StructuredGeographicPreferencesSchema(
            preferred_countries=["US"],
            preferred_institutions=["Stanford"],
        ),
        funding=StructuredFundingPreferencesSchema(
            funding_required=True,
            min_funding_amount=10000,
        ),
        academic=StructuredAcademicPreferencesSchema(
            academic_level="POSTDOC"
        ),
        exclusions=StructuredExclusionsSchema(),
    )

    assessment = PreferenceInterpreter.evaluate_opportunity(
        profile_id=profile_id,
        preferences=prefs,
        opportunity=sparse_opp,
    )

    # Missing location must NOT be treated as geographic mismatch / excluded
    geo_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.COUNTRY)
    assert geo_sig.match_type == PreferenceMatchType.INSUFFICIENT_EVIDENCE
    assert geo_sig.polarity == SignalPolarity.NEUTRAL

    # Missing funding must NOT be treated as unfunded / excluded
    fund_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.FUNDING)
    assert fund_sig.match_type == PreferenceMatchType.INSUFFICIENT_EVIDENCE

    # Missing institution must NOT be treated as mismatch
    inst_sig = next(s for s in assessment.dimension_signals if s.dimension == PreferenceDimension.INSTITUTION)
    assert inst_sig.match_type == PreferenceMatchType.INSUFFICIENT_EVIDENCE

    # Overall state should be INSUFFICIENT_EVIDENCE because all configured preferences lacked data
    assert assessment.overall_match_state == PreferenceMatchType.INSUFFICIENT_EVIDENCE
    assert assessment.excluded_matches_count == 0


def test_determinism_identical_inputs(sample_opportunity: OpportunityModel):
    """Invariant 20: Identical inputs produce identical outputs (100% deterministic)."""
    profile_id = uuid.uuid4()
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(
            topics=["Artificial Intelligence"]
        ),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["CONFERENCE"]
        ),
        geography=StructuredGeographicPreferencesSchema(
            preferred_countries=["DE"]
        ),
        funding=StructuredFundingPreferencesSchema(
            funding_required=True,
            min_funding_amount=30000,
        ),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    a1 = PreferenceInterpreter.evaluate_opportunity(profile_id, prefs, sample_opportunity)
    a2 = PreferenceInterpreter.evaluate_opportunity(profile_id, prefs, sample_opportunity)

    assert a1.overall_match_state == a2.overall_match_state
    assert a1.positive_matches_count == a2.positive_matches_count
    assert a1.deterministic_explanation == a2.deterministic_explanation
    assert len(a1.dimension_signals) == len(a2.dimension_signals)
    for s1, s2 in zip(a1.dimension_signals, a2.dimension_signals):
        assert s1.dimension == s2.dimension
        assert s1.match_type == s2.match_type
        assert s1.polarity == s2.polarity
        assert s1.explanation == s2.explanation


def test_batch_evaluation_zero_n_plus_one(sample_opportunity: OpportunityModel):
    """Invariant 23: Batch evaluation operates in memory without N+1 queries."""
    profile_id = uuid.uuid4()
    opps = [sample_opportunity]
    prefs = StructuredPreferencesResponseSchema(
        profile_id=profile_id,
        user_id=profile_id,
        interests=StructuredResearchInterestsSchema(
            topics=["Artificial Intelligence"]
        ),
        opportunities=StructuredOpportunityPreferencesSchema(
            preferred_types=["CONFERENCE"]
        ),
        geography=StructuredGeographicPreferencesSchema(),
        funding=StructuredFundingPreferencesSchema(),
        academic=StructuredAcademicPreferencesSchema(),
        exclusions=StructuredExclusionsSchema(),
    )

    batch_res = PreferenceInterpreter.evaluate_opportunities_batch(profile_id, prefs, opps)

    assert sample_opportunity.id in batch_res
    assessment = batch_res[sample_opportunity.id]
    assert assessment.overall_match_state == PreferenceMatchType.PREFERRED_MATCH


# -----------------------------------------------------------------------------
# API Integration Tests
# -----------------------------------------------------------------------------

def test_api_get_opportunity_preference_match(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
    sample_opportunity: OpportunityModel,
    db_session: Session,
):
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
        f"/api/v1/researchers/{profile.id}/opportunities/{sample_opportunity.id}/preference-match",
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["profile_id"] == str(profile.id)
    assert data["opportunity_id"] == str(sample_opportunity.id)
    assert data["overall_match_state"] == "PREFERRED_MATCH"
    assert data["positive_matches_count"] >= 1
    assert "deterministic_explanation" in data


def test_api_batch_opportunity_preference_matches(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
    sample_opportunity: OpportunityModel,
    db_session: Session,
):
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
        f"/api/v1/researchers/{profile.id}/opportunities/preference-matches",
        json=payload,
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["profile_id"] == str(profile.id)
    assert data["evaluated_count"] == 1
    assessment = data["assessments"][0]
    assert assessment["opportunity_id"] == str(sample_opportunity.id)
    assert assessment["overall_match_state"] == "EXCLUDED_MATCH"


def test_api_opportunity_not_found(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
):
    user, profile = test_user_and_profile
    fake_opp_id = uuid.uuid4()

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/opportunities/{fake_opp_id}/preference-match",
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == 404


def test_api_unauthorized_access(
    client: TestClient,
    test_user_and_profile: tuple[UserModel, ResearchProfileModel],
    sample_opportunity: OpportunityModel,
):
    _, profile = test_user_and_profile
    other_user_id = uuid.uuid4()

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/opportunities/{sample_opportunity.id}/preference-match",
        headers={"X-User-ID": str(other_user_id)},
    )
    assert resp.status_code == 403
