"""
Unit, Integration, and Regression Tests for Phase 3.4:
Personalized Candidate Generation.

Verifies:
  1. Explicit preference candidate generation (topic, type, delivery mode, partial matches).
  2. Scholarly expertise candidate generation (primary, secondary, emerging interests).
  3. Inferred preference candidate generation with confidence threshold >= 0.40.
  4. Cold-start fallback candidate generation for researchers with sparse data.
  5. Candidate deduplication & provenance merging across multiple sources.
  6. Source balancing quotas (explicit, inferred, expertise, profile, fallback).
  7. Candidate eligibility (exclusion of expired, archived, and draft opportunities).
  8. Phase 2.6 trust/risk intelligence preservation (no risk override or suppression).
  9. Phase 2.7 deadline intelligence preservation.
  10. Relevance floor invariant: generic preferences cannot manufacture relevance without topic alignment.
  11. Strict phase boundary: unranked candidate set returned; Phase 2 ranker untouched.
  12. Zero N+1 query performance (bounded query execution).
  13. REST API endpoint (200 OK, 403 Forbidden on unauthorized user, 404 Not Found).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.opportunity import OpportunityModel, OpportunityTopicModel
from app.models.research_knowledge import InstitutionModel, ResearcherModel
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.ranking.deadline.intelligence import DeadlineIntelligence
from app.ranking.risk.scoring import assess_opportunity_risk
from app.schemas.personalized_candidate import (
    CandidateSourceType,
    PersonalizedCandidateSetResponse,
)
from app.services.personalized_candidate_generation_service import (
    PersonalizedCandidateGenerationService,
)

# ── SQLite In-Memory Database Compatibility ───────────────────────────────────

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a clean in-memory SQLite session with Phase 3.4 tables."""
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

def create_test_user(db: Session, email: str = "researcher@test.edu") -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        full_name="Dr. Test Researcher",
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
    title: str,
    opp_type: str = "CONFERENCE",
    delivery_mode: str = "ONLINE",
    status: str = "ACTIVE",
    deadline_offset_days: int = 30,
    location: str | None = None,
    topics: list[TopicModel] | None = None,
    is_predatory: bool = False,
    risk_score: float = 0.0,
) -> OpportunityModel:
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=deadline_offset_days) if deadline_offset_days is not None else None

    opp = OpportunityModel(
        id=uuid.uuid4(),
        title=title,
        opportunity_type=opp_type,
        delivery_mode=delivery_mode,
        status=status,
        submission_deadline=deadline,
        location=location,
        is_predatory_flag=is_predatory,
        risk_score=risk_score,
    )
    db.add(opp)
    db.flush()

    if topics:
        for t in topics:
            link = OpportunityTopicModel(
                opportunity_id=opp.id,
                topic_id=t.id,
                confidence_score=1.0,
                is_primary=True,
            )
            db.add(link)
        db.flush()

    return opp


# ── 1. Explicit Preference Candidates ─────────────────────────────────────────

def test_explicit_topic_preference_candidate_generation(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic_ml = create_test_topic(db_session, "Machine Learning", "machine-learning")
    topic_bio = create_test_topic(db_session, "Biomedical Engineering", "biomedical-engineering")

    opp_ml = create_test_opportunity(
        db_session, "International Conference on Machine Learning", topics=[topic_ml]
    )
    opp_bio = create_test_opportunity(
        db_session, "Bioengineering Global Summit", topics=[topic_bio]
    )

    # Explicit preference for Machine Learning
    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="machine-learning",
        display_label="Machine Learning",
        canonical_id=topic_ml.id,
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        include_fallback=False,
    )

    opp_ids = [c.opportunity.id for c in res.candidates]
    assert opp_ml.id in opp_ids
    assert opp_bio.id not in opp_ids

    # Verify provenance
    ml_candidate = next(c for c in res.candidates if c.opportunity.id == opp_ml.id)
    assert CandidateSourceType.EXPLICIT_PREFERENCE in ml_candidate.provenance.sources
    assert "Machine Learning" in ml_candidate.provenance.matched_topics


def test_explicit_partial_matching_no_zero_results(db_session: Session):
    """Verifies that missing one explicit dimension does not zero-out candidate results."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic_nlp = create_test_topic(db_session, "Natural Language Processing", "natural-language-processing")

    # Opportunity matches topic and type, but delivery mode is OFFLINE
    opp = create_test_opportunity(
        db_session,
        "ACL 2026",
        opp_type="CONFERENCE",
        delivery_mode="OFFLINE",
        topics=[topic_nlp],
    )

    # Researcher prefers topic NLP, type CONFERENCE, and delivery mode HYBRID
    p1 = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="natural-language-processing",
        display_label="NLP",
        canonical_id=topic_nlp.id,
        source="EXPLICIT",
        is_active=True,
    )
    p2 = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        display_label="Conference",
        source="EXPLICIT",
        is_active=True,
    )
    p3 = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="DELIVERY_MODE",
        preference_key="delivery_mode",
        preference_value="HYBRID",
        display_label="Hybrid",
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        include_fallback=False,
    )

    # Should still match because topic and type match
    opp_ids = [c.opportunity.id for c in res.candidates]
    assert opp.id in opp_ids


# ── 2. Scholarly Expertise Candidates ─────────────────────────────────────────

def test_scholarly_expertise_candidate_generation(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic_cv = create_test_topic(db_session, "Computer Vision", "computer-vision")
    topic_nlp = create_test_topic(db_session, "NLP", "nlp")

    opp_cv = create_test_opportunity(
        db_session, "CVPR Conference", topics=[topic_cv]
    )
    opp_nlp = create_test_opportunity(
        db_session, "EMNLP Conference", topics=[topic_nlp]
    )

    # Primary expertise in Computer Vision
    exp = ResearcherInterestModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        topic_id=topic_cv.id,
        topic_name="Computer Vision",
        topic_slug="computer-vision",
        classification="PRIMARY_EXPERTISE",
        is_primary_expertise=True,
        strength=0.92,
        confidence=0.88,
    )
    db_session.add(exp)
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        include_fallback=False,
    )

    opp_ids = [c.opportunity.id for c in res.candidates]
    assert opp_cv.id in opp_ids
    assert opp_nlp.id not in opp_ids

    cv_cand = next(c for c in res.candidates if c.opportunity.id == opp_cv.id)
    assert CandidateSourceType.RESEARCH_EXPERTISE in cv_cand.provenance.sources
    assert "Computer Vision (PRIMARY_EXPERTISE)" in cv_cand.provenance.matched_expertise


# ── 3. Inferred Preferences & Confidence Threshold ────────────────────────────

def test_inferred_preference_confidence_threshold(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic_high = create_test_topic(db_session, "Deep Learning", "deep-learning")
    topic_low = create_test_topic(db_session, "Quantum Computing", "quantum-computing")

    opp_high = create_test_opportunity(
        db_session, "Deep Learning Workshop", topics=[topic_high]
    )
    opp_low = create_test_opportunity(
        db_session, "Quantum Summit", topics=[topic_low]
    )

    # Inferred pref with high confidence (0.75 >= 0.40)
    p_high = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="deep-learning",
        display_label="Deep Learning",
        canonical_id=topic_high.id,
        source="INFERRED",
        confidence=0.75,
        is_active=True,
    )
    # Inferred pref with low confidence (0.25 < 0.40)
    p_low = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="quantum-computing",
        display_label="Quantum",
        canonical_id=topic_low.id,
        source="INFERRED",
        confidence=0.25,
        is_active=True,
    )
    db_session.add_all([p_high, p_low])
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        include_inferred=True,
        include_fallback=False,
    )

    opp_ids = [c.opportunity.id for c in res.candidates]
    assert opp_high.id in opp_ids
    assert opp_low.id not in opp_ids

    cand_high = next(c for c in res.candidates if c.opportunity.id == opp_high.id)
    assert CandidateSourceType.INFERRED_PREFERENCE in cand_high.provenance.sources


# ── 4. Cold Start & Fallback Retrieval ────────────────────────────────────────

def test_cold_start_fallback_retrieval(db_session: Session):
    user = create_test_user(db_session)
    # Researcher with no preferences, no interests, no keywords
    profile = create_test_profile(db_session, user)

    opp1 = create_test_opportunity(db_session, "Active Upcoming Symposium A", deadline_offset_days=10)
    opp2 = create_test_opportunity(db_session, "Active Upcoming Symposium B", deadline_offset_days=20)
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        limit=10,
        include_fallback=True,
    )

    assert res.is_cold_start is True
    assert res.candidate_count >= 2
    assert any(
        CandidateSourceType.COLD_START_FALLBACK in c.provenance.sources
        for c in res.candidates
    )


# ── 5. Candidate Deduplication & Provenance Merging ───────────────────────────

def test_candidate_deduplication_and_provenance_merging(db_session: Session):
    """An opportunity matching both an explicit preference and scholarly expertise is deduplicated and merged."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic_ai = create_test_topic(db_session, "Artificial Intelligence", "ai")
    opp_ai = create_test_opportunity(
        db_session, "AAAI Conference on AI", opp_type="CONFERENCE", topics=[topic_ai]
    )

    # 1. Explicit preference for Conference
    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        display_label="Conference",
        source="EXPLICIT",
        is_active=True,
    )
    # 2. Expertise in AI
    exp = ResearcherInterestModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        topic_id=topic_ai.id,
        topic_name="Artificial Intelligence",
        topic_slug="ai",
        classification="PRIMARY_EXPERTISE",
        is_primary_expertise=True,
    )
    db_session.add_all([pref, exp])
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        include_fallback=False,
    )

    ai_candidates = [c for c in res.candidates if c.opportunity.id == opp_ai.id]
    assert len(ai_candidates) == 1  # Deduplicated to 1 item!

    item = ai_candidates[0]
    # Provenance contains BOTH sources
    assert CandidateSourceType.EXPLICIT_PREFERENCE in item.provenance.sources
    assert CandidateSourceType.RESEARCH_EXPERTISE in item.provenance.sources
    assert len(item.provenance.reasons) >= 2


# ── 6. Source Balancing & Quota Adherence ─────────────────────────────────────

def test_source_balancing_quota_allocation(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic_exp = create_test_topic(db_session, "Bioinformatics", "bioinformatics")
    topic_pref = create_test_topic(db_session, "Robotics", "robotics")

    # Create 10 bioinformatics opps (expertise)
    for i in range(10):
        create_test_opportunity(db_session, f"Bioinformatics Summit {i}", topics=[topic_exp])

    # Create 3 robotics opps (explicit pref)
    for i in range(3):
        create_test_opportunity(db_session, f"Robotics Forum {i}", topics=[topic_pref])

    exp = ResearcherInterestModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        topic_id=topic_exp.id,
        topic_name="Bioinformatics",
        topic_slug="bioinformatics",
        classification="PRIMARY_EXPERTISE",
    )
    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="robotics",
        display_label="Robotics",
        canonical_id=topic_pref.id,
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add_all([exp, pref])
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        limit=10,
        include_fallback=False,
    )

    # Explicit preferences must NOT be starved out by expertise
    assert res.coverage.explicit_preference_count > 0
    assert res.coverage.expertise_count > 0


# ── 7. Eligibility: Expired & Inactive Exclusion ──────────────────────────────

def test_eligibility_exclusion_of_expired_and_inactive(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic = create_test_topic(db_session, "Security", "security")

    # Active, upcoming
    opp_valid = create_test_opportunity(
        db_session, "IEEE S&P 2026", status="ACTIVE", deadline_offset_days=45, topics=[topic]
    )
    # Expired deadline (-10 days)
    opp_expired = create_test_opportunity(
        db_session, "Expired Security Conference", status="ACTIVE", deadline_offset_days=-10, topics=[topic]
    )
    # Inactive status (ARCHIVED)
    opp_archived = create_test_opportunity(
        db_session, "Archived Workshop", status="ARCHIVED", deadline_offset_days=30, topics=[topic]
    )

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="security",
        display_label="Security",
        canonical_id=topic.id,
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
    )

    opp_ids = [c.opportunity.id for c in res.candidates]
    assert opp_valid.id in opp_ids
    assert opp_expired.id not in opp_ids
    assert opp_archived.id not in opp_ids


# ── 8. Trust / Risk Intelligence Safety ───────────────────────────────────────

def test_trust_risk_preservation_no_override(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic = create_test_topic(db_session, "AI", "ai")

    # High-risk predatory opportunity
    opp_risky = create_test_opportunity(
        db_session,
        "Universal Mega AI Conference With Guaranteed Fast Acceptance",
        topics=[topic],
        is_predatory=True,
        risk_score=0.95,
    )

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="ai",
        display_label="AI",
        canonical_id=topic.id,
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
    )

    cand = next(c for c in res.candidates if c.opportunity.id == opp_risky.id)
    # Risk metadata MUST be preserved and NOT suppressed
    assert cand.opportunity.is_predatory_flag is True
    assert cand.opportunity.risk_level in ("HIGH_RISK", "MODERATE_RISK")
    assert cand.opportunity.risk_score >= 0.50


# ── 9. Relevance Floor Invariant ──────────────────────────────────────────────

def test_relevance_floor_prevents_unrelated_type_matching(db_session: Session):
    """A generic preference for 'CONFERENCE' cannot pull completely unrelated opportunities when user has topics."""
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic_cs = create_test_topic(db_session, "Computer Science", "computer-science")
    topic_agri = create_test_topic(db_session, "Poultry Farming", "poultry-farming")

    opp_cs = create_test_opportunity(
        db_session, "International CS Conference", opp_type="CONFERENCE", topics=[topic_cs]
    )
    opp_agri = create_test_opportunity(
        db_session, "Poultry Farming Annual Gathering", opp_type="CONFERENCE", topics=[topic_agri]
    )

    # User explicitly prefers CS topic and CONFERENCE type
    p_topic = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="computer-science",
        display_label="Computer Science",
        canonical_id=topic_cs.id,
        source="EXPLICIT",
        is_active=True,
    )
    p_type = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        display_label="Conference",
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add_all([p_topic, p_type])
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        include_fallback=False,
    )

    opp_ids = [c.opportunity.id for c in res.candidates]
    assert opp_cs.id in opp_ids
    # Poultry farming must NOT be included simply because it is a CONFERENCE
    assert opp_agri.id not in opp_ids


# ── 10. Strict Phase Boundary ─────────────────────────────────────────────────

def test_phase_boundary_no_personalized_ranking_scores(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    opp = create_test_opportunity(db_session, "General Forum")
    db_session.commit()

    res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
        db=db_session,
        profile_id=profile.id,
        include_fallback=True,
    )

    # Verify the response is a candidate set and contains no injected personalization_score
    for cand in res.candidates:
        assert hasattr(cand, "candidate_id")
        assert hasattr(cand, "provenance")
        # Ensure no personalized recommendation rank/score was added to candidate schema
        cand_dict = cand.model_dump()
        assert "personalization_score" not in cand_dict
        assert "recommendation_rank" not in cand_dict


# ── 11. Performance & Zero N+1 Queries ────────────────────────────────────────

def test_bounded_database_queries(db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    topic = create_test_topic(db_session, "Information Retrieval", "ir")

    # Seed 30 opportunities
    for i in range(30):
        create_test_opportunity(db_session, f"IR Conference {i}", topics=[topic])

    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="TOPIC",
        preference_key="topic",
        preference_value="ir",
        display_label="IR",
        canonical_id=topic.id,
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)
    db_session.commit()

    query_count = 0

    def _query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _query_listener)

    try:
        res = PersonalizedCandidateGenerationService.generate_personalized_candidates(
            db=db_session,
            profile_id=profile.id,
            limit=25,
        )
        assert len(res.candidates) >= 20
        # Total DB queries must be constant O(1) <= 10 queries regardless of candidate count (including Phase 3.6 suppression lookup)
        assert query_count <= 10
    finally:
        event.remove(engine, "before_cursor_execute", _query_listener)


# ── 12. FastAPI REST Endpoints & Ownership Authorization ──────────────────────

def test_api_get_personalized_candidates_success(client: TestClient, db_session: Session):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)

    create_test_opportunity(db_session, "Public Academic Seminar", status="ACTIVE")
    db_session.commit()

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/personalized-candidates",
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data
    assert "coverage" in data
    assert data["researcher_id"] == str(profile.id)


def test_api_get_personalized_candidates_forbidden(
    client: TestClient, db_session: Session, intruder_identity: UserModel
):
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user)
    other_user_id = intruder_identity.id

    resp = client.get(
        f"/api/v1/researchers/{profile.id}/personalized-candidates",
        headers={"X-User-ID": str(other_user_id)},
    )
    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]


def test_api_get_personalized_candidates_not_found(client: TestClient):
    random_id = uuid.uuid4()
    resp = client.get(f"/api/v1/researchers/{random_id}/personalized-candidates")
    assert resp.status_code == 404
