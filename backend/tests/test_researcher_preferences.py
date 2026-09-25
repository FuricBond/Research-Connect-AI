"""
Unit, Integration, and Regression Tests for Phase 3.3:
Personal Preference Intelligence.

Verifies:
  1. Explicit preferences CRUD, normalization, and duplicate prevention.
  2. Bounded mathematical scoring: strength in [0.0, 1.0], confidence in [0.0, 1.0].
  3. Strict Phase Boundary & Critical Invariant: Expertise != Preference.
  4. Activity-based inference strictly from SavedOpportunityModel with zero fabricated history.
  5. 10 canonical evaluation fixture scenarios (Section 25 of user request).
  6. Ownership authorization and 403 enforcement.
  7. Contradiction & conflict detection.
  8. Preference completeness scoring.
  9. Zero N+1 query performance.
  10. FastAPI REST endpoints (/preferences, /preference-intelligence).
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
from app.models.opportunity import OpportunityModel
from app.models.research_knowledge import InstitutionModel, ResearcherModel
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.researcher_preference import (
    PreferenceCategory,
    PreferenceSource,
    ResearcherPreferenceCreateSchema,
    ResearcherPreferenceUpdateSchema,
)
from app.services.researcher_preference_service import ResearcherPreferenceService

# ── SQLite In-Memory Database Fixture ─────────────────────────────────────────

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with Phase 3.3 tables."""
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
def setup_researcher(db_session: Session) -> tuple[UserModel, ResearchProfileModel]:
    """Helper creating a test user and research profile."""
    user = UserModel(
        id=uuid.uuid4(),
        email=f"scholar_{uuid.uuid4().hex[:6]}@domain.edu",
        full_name="Dr. Jane Doe",
        hashed_password="hashed_pw_test",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY",
        institution="Stanford University",
        department="Computer Science",
        keywords=["machine learning", "neural networks"],
        target_opportunity_types=["CONFERENCE"],
    )
    db_session.add(profile)
    db_session.commit()
    return user, profile


# ── Test Normalization ─────────────────────────────────────────────────────────

def test_normalization_opportunity_type(db_session: Session):
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        category="OPPORTUNITY_TYPE",
        raw_key=None,
        raw_value="conferences",
        raw_label=None,
        canonical_id=None,
        db=db_session,
    )
    assert cat == "OPPORTUNITY_TYPE"
    assert key == "opportunity_type"
    assert val == "CONFERENCE"
    assert label == "Conference"
    assert cid is None


def test_normalization_delivery_mode(db_session: Session):
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        category="DELIVERY_MODE",
        raw_key=None,
        raw_value="remote",
        raw_label=None,
        canonical_id=None,
        db=db_session,
    )
    assert cat == "DELIVERY_MODE"
    assert key == "delivery_mode"
    assert val == "ONLINE"
    assert label == "Online / Virtual"


def test_normalization_topic_taxonomy_match(db_session: Session):
    # Insert canonical topic
    topic = TopicModel(id=uuid.uuid4(), name="Computer Vision", slug="computer-vision")
    db_session.add(topic)
    db_session.commit()

    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        category="TOPIC",
        raw_key=None,
        raw_value="Computer Vision",
        raw_label=None,
        canonical_id=None,
        db=db_session,
    )
    assert cat == "TOPIC"
    assert key == "topic"
    assert val == "computer-vision"
    assert label == "Computer Vision"
    assert cid == topic.id


def test_normalization_deadline_and_open_access(db_session: Session):
    _, _, d_val, d_label, _ = ResearcherPreferenceService.normalize_preference(
        category="DEADLINE_WINDOW",
        raw_key=None,
        raw_value="14 days notice",
        db=db_session,
        canonical_id=None,
    )
    assert d_val == "14"
    assert "14 days" in d_label

    _, _, oa_val, oa_label, _ = ResearcherPreferenceService.normalize_preference(
        category="OPEN_ACCESS",
        raw_key=None,
        raw_value="yes",
        db=db_session,
        canonical_id=None,
    )
    assert oa_val == "true"
    assert "Prefer Open Access" in oa_label


# ── Test Explicit Preferences CRUD ───────────────────────────────────────────

def test_explicit_preference_crud(db_session: Session, setup_researcher):
    user, profile = setup_researcher

    # 1. Create
    payload = ResearcherPreferenceCreateSchema(
        category=PreferenceCategory.OPPORTUNITY_TYPE,
        preference_value="WORKSHOP",
        strength=0.9,
    )
    created = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=profile.id,
        payload=payload,
        current_user_id=user.id,
    )
    assert created.id is not None
    assert created.profile_id == profile.id
    assert created.category == "OPPORTUNITY_TYPE"
    assert created.preference_value == "WORKSHOP"
    assert created.strength == 0.9
    assert created.confidence == 0.95
    assert created.source == "EXPLICIT"
    assert created.is_active is True

    # 2. Duplicate prevention (upsert behavior)
    payload_dup = ResearcherPreferenceCreateSchema(
        category=PreferenceCategory.OPPORTUNITY_TYPE,
        preference_value="workshops",  # normalizes to WORKSHOP
        strength=1.0,
    )
    updated = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=profile.id,
        payload=payload_dup,
        current_user_id=user.id,
    )
    assert updated.id == created.id
    assert updated.strength == 1.0

    # 3. List
    items = ResearcherPreferenceService.list_preferences(db_session, profile.id)
    assert len(items) == 1
    assert items[0].preference_value == "WORKSHOP"

    # 4. Update
    up_payload = ResearcherPreferenceUpdateSchema(strength=0.75, display_label="Academic Workshops")
    modified = ResearcherPreferenceService.update_preference(
        db=db_session,
        profile_id=profile.id,
        preference_id=created.id,
        payload=up_payload,
        current_user_id=user.id,
    )
    assert modified is not None
    assert modified.strength == 0.75
    assert modified.display_label == "Academic Workshops"

    # 5. Delete
    deleted = ResearcherPreferenceService.delete_preference(
        db=db_session,
        profile_id=profile.id,
        preference_id=created.id,
        current_user_id=user.id,
    )
    assert deleted is True

    items_after = ResearcherPreferenceService.list_preferences(db_session, profile.id)
    assert len(items_after) == 0


# ── Test Ownership & Authorization ─────────────────────────────────────────────

def test_ownership_enforcement(db_session: Session, setup_researcher):
    user, profile = setup_researcher
    other_user_id = uuid.uuid4()

    payload = ResearcherPreferenceCreateSchema(
        category=PreferenceCategory.DELIVERY_MODE,
        preference_value="ONLINE",
    )

    # Unauthorized creation must raise PermissionError
    with pytest.raises(PermissionError):
        ResearcherPreferenceService.create_explicit_preference(
            db=db_session,
            profile_id=profile.id,
            payload=payload,
            current_user_id=other_user_id,
        )

    # Authorized creation succeeds
    pref = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=profile.id,
        payload=payload,
        current_user_id=user.id,
    )
    assert pref is not None

    # Unauthorized update fails
    with pytest.raises(PermissionError):
        ResearcherPreferenceService.update_preference(
            db=db_session,
            profile_id=profile.id,
            preference_id=pref.id,
            payload=ResearcherPreferenceUpdateSchema(strength=0.5),
            current_user_id=other_user_id,
        )

    # Unauthorized delete fails
    with pytest.raises(PermissionError):
        ResearcherPreferenceService.delete_preference(
            db=db_session,
            profile_id=profile.id,
            preference_id=pref.id,
            current_user_id=other_user_id,
        )


# ── 10 Evaluation Scenarios (Spec Section 25) ──────────────────────────────────

def test_scenario_1_explicit_preferences_only(db_session: Session, setup_researcher):
    """Scenario 1: Explicit preferences only (no activity, no expertise)."""
    user, profile = setup_researcher

    ResearcherPreferenceService.create_explicit_preference(
        db_session,
        profile.id,
        ResearcherPreferenceCreateSchema(category=PreferenceCategory.OPPORTUNITY_TYPE, preference_value="CONFERENCE"),
        current_user_id=user.id,
    )
    ResearcherPreferenceService.create_explicit_preference(
        db_session,
        profile.id,
        ResearcherPreferenceCreateSchema(category=PreferenceCategory.DELIVERY_MODE, preference_value="ONLINE"),
        current_user_id=user.id,
    )

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
    assert len(intel.explicit_preferences) == 2
    assert len(intel.inferred_preferences) == 0
    assert len(intel.derived_candidates) == 0
    assert intel.summary.explicit_count == 2
    assert intel.summary.confidence_level in ("HIGH", "MEDIUM")


def test_scenario_2_cold_start_no_preferences(db_session: Session):
    """Scenario 2: No preferences / cold start (graceful empty state, zero fabricated data)."""
    user = UserModel(
        id=uuid.uuid4(),
        email=f"scholar_cold_{uuid.uuid4().hex[:6]}@domain.edu",
        full_name="Dr. Cold Start",
        hashed_password="hashed_pw_test",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    cold_profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY",
        keywords=[],
        target_opportunity_types=[],
    )
    db_session.add(cold_profile)
    db_session.commit()

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, cold_profile.id)
    assert len(intel.explicit_preferences) == 0
    assert len(intel.inferred_preferences) == 0
    assert len(intel.derived_candidates) == 0
    assert intel.summary.total_preferences == 0
    assert intel.summary.confidence_level == "LOW"
    assert intel.completeness.score == 0.0
    assert intel.completeness.percentage == 0
    assert intel.completeness.is_complete is False



def test_scenario_3_strong_inferred_preference(db_session: Session, setup_researcher):
    """Scenario 3: Strong inferred preference from multiple saved opportunities."""
    user, profile = setup_researcher

    # Create 5 saved opportunities where 4 are WORKSHOP and ONLINE
    for i in range(5):
        opp_type = "WORKSHOP" if i < 4 else "CONFERENCE"
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title=f"Event {i}",
            opportunity_type=opp_type,
            delivery_mode="ONLINE",
            status="ACTIVE",
        )
        db_session.add(opp)
        db_session.flush()

        saved = SavedOpportunityModel(
            id=uuid.uuid4(),
            user_id=user.id,
            opportunity_id=opp.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        db_session.add(saved)
    db_session.commit()

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
    inferred_types = [p for p in intel.inferred_preferences if p.category == "OPPORTUNITY_TYPE"]
    workshop_inferred = next((p for p in inferred_types if p.preference_value == "WORKSHOP"), None)

    assert workshop_inferred is not None
    assert workshop_inferred.source == "INFERRED"
    assert workshop_inferred.strength >= 0.60
    assert workshop_inferred.confidence >= 0.70
    assert "4 of 5" in workshop_inferred.provenance_reasons[0]


def test_scenario_4_weak_inferred_preference(db_session: Session, setup_researcher):
    """Scenario 4: Weak inferred preference from sparse saved opportunity."""
    user, profile = setup_researcher

    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Single Saved CFP",
        opportunity_type="CALL_FOR_PAPERS",
        delivery_mode="HYBRID",
        status="ACTIVE",
    )
    db_session.add(opp)
    db_session.flush()

    saved = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=user.id,
        opportunity_id=opp.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(saved)
    db_session.commit()

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
    inferred = intel.inferred_preferences
    assert len(inferred) > 0
    cfp_inf = next((p for p in inferred if p.preference_value == "CALL_FOR_PAPERS"), None)
    assert cfp_inf is not None
    # Weak evidence has lower confidence than rich history
    assert cfp_inf.confidence <= 0.70


def test_scenario_5_conflicting_preferences(db_session: Session, setup_researcher):
    """Scenario 5: Conflicting preferences (contradictory open access / deadlines)."""
    user, profile = setup_researcher

    # Add contradictory Open Access declarations
    pref_true = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPEN_ACCESS",
        preference_key="prefer_open_access",
        preference_value="true",
        display_label="Prefer Open Access",
        strength=1.0,
        confidence=0.95,
        source="EXPLICIT",
        is_active=True,
    )
    pref_false = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPEN_ACCESS",
        preference_key="prefer_open_access",
        preference_value="false",
        display_label="No Open Access Preference",
        strength=1.0,
        confidence=0.95,
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add_all([pref_true, pref_false])
    db_session.commit()

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
    assert len(intel.conflicts) > 0
    assert intel.conflicts[0].category == "OPEN_ACCESS"
    assert intel.summary.has_conflicts is True


def test_scenario_6_stale_preference_evidence(db_session: Session, setup_researcher):
    """Scenario 6: Stale preference evidence exhibits bounded recency decay."""
    user, profile = setup_researcher

    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Old Event",
        opportunity_type="CONFERENCE",
        delivery_mode="ONLINE",
        status="ACTIVE",
    )
    db_session.add(opp)
    db_session.flush()

    # Saved 200 days ago
    saved = SavedOpportunityModel(
        id=uuid.uuid4(),
        user_id=user.id,
        opportunity_id=opp.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=200),
    )
    db_session.add(saved)
    db_session.commit()

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
    assert len(intel.inferred_preferences) > 0
    item = intel.inferred_preferences[0]
    # Recency decay should have brought recency_score below 0.6
    assert item.recency_score < 0.60


def test_scenario_7_multiple_preference_categories(db_session: Session, setup_researcher):
    """Scenario 7: Multiple preference categories across types, modes, topics, deadlines, locations."""
    user, profile = setup_researcher

    categories = [
        (PreferenceCategory.OPPORTUNITY_TYPE, "CONFERENCE"),
        (PreferenceCategory.DELIVERY_MODE, "ONLINE"),
        (PreferenceCategory.TOPIC, "machine-learning"),
        (PreferenceCategory.DEADLINE_WINDOW, "14"),
        (PreferenceCategory.LOCATION, "Europe"),
        (PreferenceCategory.OPEN_ACCESS, "true"),
    ]
    for cat, val in categories:
        ResearcherPreferenceService.create_explicit_preference(
            db_session,
            profile.id,
            ResearcherPreferenceCreateSchema(category=cat, preference_value=val),
            current_user_id=user.id,
        )

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
    assert len(intel.explicit_preferences) == 6
    assert intel.completeness.is_complete is True
    assert intel.completeness.percentage >= 85


def test_scenario_8_expertise_without_preference_invariant(db_session: Session, setup_researcher):
    """
    CRITICAL SAFETY INVARIANT: Expertise != Preference.
    Scholarly expertise from Phase 3.2 must NOT become an explicit preference.
    """
    user, profile = setup_researcher

    # Researcher has high scholarly expertise in Natural Language Processing
    nlp_interest = ResearcherInterestModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        topic_name="Natural Language Processing",
        topic_slug="natural-language-processing",
        strength=0.92,
        confidence=0.90,
        classification="PRIMARY_EXPERTISE",
        is_primary_expertise=True,
    )
    db_session.add(nlp_interest)
    db_session.commit()

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)

    # 1. No explicit preferences must exist
    assert len(intel.explicit_preferences) == 0

    # 2. It must ONLY appear under derived_candidates with source = DERIVED_FROM_EXPERTISE
    assert len(intel.derived_candidates) == 1
    cand = intel.derived_candidates[0]
    assert cand.source == "DERIVED_FROM_EXPERTISE"
    assert cand.preference_value == "natural-language-processing"
    assert cand.confidence == 0.45  # Discounted confidence for derived signals
    assert "Derived from scholarly expertise" in cand.provenance_reasons[0]


def test_scenario_9_preference_without_corresponding_expertise(db_session: Session, setup_researcher):
    """Scenario 9: Preference without corresponding scholarly expertise."""
    user, profile = setup_researcher

    # Declares explicit preference for Quantum Computing even without prior publications
    pref = ResearcherPreferenceService.create_explicit_preference(
        db_session,
        profile.id,
        ResearcherPreferenceCreateSchema(category=PreferenceCategory.TOPIC, preference_value="quantum-computing"),
        current_user_id=user.id,
    )
    assert pref.source == "EXPLICIT"
    assert pref.confidence == 0.95

    intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
    assert len(intel.explicit_preferences) == 1
    assert intel.explicit_preferences[0].preference_value == "quantum-computing"
    assert len(intel.derived_candidates) == 0


def test_scenario_10_missing_behavioral_evidence(db_session: Session, setup_researcher):
    """Scenario 10: Missing behavioral evidence produces zero inferred items (no mock data)."""
    user, profile = setup_researcher

    # User has 0 saved opportunities
    inferred = ResearcherPreferenceService.infer_preferences_from_activity(db_session, profile)
    assert inferred == []


# ── Test Zero N+1 Performance ─────────────────────────────────────────────────

def test_zero_n_plus_one_query_performance(db_session: Session, setup_researcher):
    """Verify constant query count regardless of number of saved opportunities."""
    user, profile = setup_researcher

    # Seed 20 saved opportunities and 5 explicit preferences
    for i in range(20):
        opp = OpportunityModel(
            id=uuid.uuid4(),
            title=f"Paper {i}",
            opportunity_type="CONFERENCE" if i % 2 == 0 else "WORKSHOP",
            delivery_mode="ONLINE" if i % 2 == 0 else "OFFLINE",
            status="ACTIVE",
        )
        db_session.add(opp)
        db_session.flush()

        saved = SavedOpportunityModel(
            id=uuid.uuid4(),
            user_id=user.id,
            opportunity_id=opp.id,
        )
        db_session.add(saved)

    for i, opt in enumerate(["CONFERENCE", "WORKSHOP", "JOURNAL"]):
        pref = ResearcherPreferenceModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            category="OPPORTUNITY_TYPE",
            preference_key="opportunity_type",
            preference_value=opt,
            display_label=opt.title(),
            strength=0.9,
            confidence=0.95,
            source="EXPLICIT",
            is_active=True,
        )
        db_session.add(pref)
    db_session.commit()

    query_count = 0

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_queries)

    try:
        intel = ResearcherPreferenceService.get_preference_intelligence(db_session, profile.id)
        # Should execute strictly <= 5 batch queries
        assert query_count <= 5, f"Expected <= 5 queries, got {query_count}"
        assert len(intel.explicit_preferences) == 3
        assert len(intel.inferred_preferences) >= 2
    finally:
        event.remove(engine, "before_cursor_execute", count_queries)


# ── Test FastAPI REST Endpoints ───────────────────────────────────────────────

def test_api_preference_endpoints(
    client: TestClient, db_session: Session, setup_researcher, intruder_identity: UserModel
):
    user, profile = setup_researcher

    # 1. GET /preference-intelligence
    res = client.get(
        f"/api/v1/researchers/{profile.id}/preference-intelligence",
        headers={"X-User-ID": str(user.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["profile_id"] == str(profile.id)
    assert data["summary"]["total_preferences"] == 0

    # 2. POST /preferences (Unauthorized)
    bad_payload = {
        "category": "OPPORTUNITY_TYPE",
        "preference_value": "JOURNAL",
        "strength": 0.8,
    }
    res_bad = client.post(
        f"/api/v1/researchers/{profile.id}/preferences",
        json=bad_payload,
        headers={"X-User-ID": str(intruder_identity.id)},
    )
    assert res_bad.status_code == 403

    # 3. POST /preferences (Authorized)
    res_create = client.post(
        f"/api/v1/researchers/{profile.id}/preferences",
        json=bad_payload,
        headers={"X-User-ID": str(user.id)},
    )
    assert res_create.status_code == 201
    created_item = res_create.json()
    assert created_item["preference_value"] == "JOURNAL"
    pref_id = created_item["id"]

    # 4. GET /preferences
    res_list = client.get(
        f"/api/v1/researchers/{profile.id}/preferences",
        headers={"X-User-ID": str(user.id)},
    )
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 5. PATCH /preferences/{id}
    res_patch = client.patch(
        f"/api/v1/researchers/{profile.id}/preferences/{pref_id}",
        json={"strength": 0.95, "display_label": "Peer-Reviewed Journals"},
        headers={"X-User-ID": str(user.id)},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["strength"] == 0.95
    assert res_patch.json()["display_label"] == "Peer-Reviewed Journals"

    # 6. DELETE /preferences/{id}
    res_del = client.delete(
        f"/api/v1/researchers/{profile.id}/preferences/{pref_id}",
        headers={"X-User-ID": str(user.id)},
    )
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True

    # 7. Verify deletion
    res_list_after = client.get(
        f"/api/v1/researchers/{profile.id}/preferences",
        headers={"X-User-ID": str(user.id)},
    )
    assert len(res_list_after.json()) == 0
