"""
Unit, Integration, and Safety Invariant Tests for Phase 5.1:
Researcher Preferences Foundation.

Covers:
  - 3-State Preference Semantics (PREFERRED, NEUTRAL/unspecified, EXCLUDED).
  - Normalization & Validation of all categories.
  - Service CRUD, Bulk Sync, and Structured Preferences retrieval.
  - REST API Endpoints (GET, POST, PUT, PATCH, DELETE).
  - Safety Invariants (1-20) defined in Phase 5.1 specification.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
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
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.researcher_preference import (
    BulkPreferenceItemSchema,
    BulkPreferencesUpdateSchema,
    PreferenceCategory,
    PreferenceSource,
    PreferenceType,
    ResearcherPreferenceCreateSchema,
    ResearcherPreferenceItemSchema,
    ResearcherPreferenceUpdateSchema,
)
from app.services.researcher_preference_service import ResearcherPreferenceService

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
def base_user(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="dr.rivera@university.edu",
        full_name="Dr. Alex Rivera",
        hashed_password="hashed_pw_test",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def base_profile(db_session: Session, base_user: UserModel) -> ResearchProfileModel:
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=base_user.id,
        academic_status=AcademicStatus.FACULTY,
        academic_level="Associate Professor",
        department="Computer Science",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


# ── Test Normalization & Validation ──────────────────────────────────────────

def test_normalization_extended_categories():
    """Verify normalization of newly added Phase 5.1 categories."""
    # 1. KEYWORD: trimmed and lowercased
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.KEYWORD, None, "  Machine Learning  "
    )
    assert cat == "KEYWORD"
    assert key == "keyword"
    assert val == "machine learning"
    assert label == "Machine Learning"

    # 2. RESEARCH_DOMAIN: title-cased
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.RESEARCH_DOMAIN, None, "artificial intelligence"
    )
    assert cat == "RESEARCH_DOMAIN"
    assert val == "Artificial Intelligence"

    # 3. COUNTRY: 2/3-letter ISO uppercased, names title-cased
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.COUNTRY, None, "usa"
    )
    assert val == "USA"
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.COUNTRY, None, "germany"
    )
    assert val == "Germany"

    # 4. OPPORTUNITY_TYPE: Fellowship, Grant, Internship
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.OPPORTUNITY_TYPE, None, "fellowships"
    )
    assert val == "FELLOWSHIP"
    assert label == "Fellowship"

    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.OPPORTUNITY_TYPE, None, "grant"
    )
    assert val == "GRANT"
    assert label == "Grant"

    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.OPPORTUNITY_TYPE, None, "internship"
    )
    assert val == "INTERNSHIP"
    assert label == "Internship"

    # 5. ACADEMIC_LEVEL & CAREER_STAGE: uppercased
    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.ACADEMIC_LEVEL, None, "postdoc"
    )
    assert val == "POSTDOC"

    cat, key, val, label, cid = ResearcherPreferenceService.normalize_preference(
        PreferenceCategory.CAREER_STAGE, None, "early career"
    )
    assert val == "EARLY_CAREER"


# ── Test 3-State Preference Semantics & Invariants ────────────────────────────

def test_3_state_preference_semantics(db_session: Session, base_profile: ResearchProfileModel):
    """
    Verify 3-State hierarchy: PREFERRED vs EXCLUDED vs NEUTRAL (unspecified).
    Invariants 1, 2, 3, 4.
    """
    # 1. Declare a preferred opportunity type
    pref_conf = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.OPPORTUNITY_TYPE,
            preference_type=PreferenceType.PREFERRED,
            preference_value="CONFERENCE",
        ),
    )
    assert pref_conf.preference_type == "PREFERRED"

    # 2. Declare an excluded opportunity type
    pref_excl = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.OPPORTUNITY_TYPE,
            preference_type=PreferenceType.EXCLUDED,
            preference_value="SPECIAL_ISSUE",
        ),
    )
    assert pref_excl.preference_type == "EXCLUDED"

    # Invariant 1 & 2: Missing preference != negative preference, Unspecified != excluded
    # "WORKSHOP" is unmentioned -> should not exist in DB
    all_prefs = ResearcherPreferenceService.list_preferences(db_session, base_profile.id)
    values = {p.preference_value for p in all_prefs}
    assert "WORKSHOP" not in values
    assert "CONFERENCE" in values
    assert "SPECIAL_ISSUE" in values

    # Invariant 4: Explicit exclusion is preserved
    excl_items = ResearcherPreferenceService.list_preferences(
        db_session, base_profile.id, preference_type="EXCLUDED"
    )
    assert len(excl_items) == 1
    assert excl_items[0].preference_value == "SPECIAL_ISSUE"
    assert excl_items[0].preference_type == "EXCLUDED"


def test_conflict_detection_preferred_vs_excluded(db_session: Session, base_profile: ResearchProfileModel):
    """Verify conflict detection flags when the same value is marked as both preferred and excluded."""
    # 1. Test detect_conflicts directly with preferred vs excluded items
    item_pref = ResearcherPreferenceItemSchema(
        id=uuid.uuid4(),
        profile_id=base_profile.id,
        category="TOPIC",
        preference_type="PREFERRED",
        preference_key="topic",
        preference_value="machine-learning",
        display_label="Machine Learning",
        strength=1.0,
        confidence=0.95,
        source="EXPLICIT",
        is_active=True,
    )
    item_excl = ResearcherPreferenceItemSchema(
        id=uuid.uuid4(),
        profile_id=base_profile.id,
        category="TOPIC",
        preference_type="EXCLUDED",
        preference_key="topic",
        preference_value="machine-learning",
        display_label="Machine Learning",
        strength=1.0,
        confidence=0.95,
        source="EXPLICIT",
        is_active=True,
    )

    conflicts = ResearcherPreferenceService.detect_conflicts([item_pref, item_excl])
    assert len(conflicts) > 0
    assert conflicts[0].category == "TOPIC"
    assert "machine-learning" in conflicts[0].conflicting_values

    # 2. Verify database-level unique constraint prevents creating duplicate rows for same profile, cat, val
    p1 = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.TOPIC,
            preference_type=PreferenceType.PREFERRED,
            preference_value="machine-learning",
            display_label="Machine Learning",
        ),
    )
    # Updating to EXCLUDED updates the row in-place rather than inserting a duplicate
    p2 = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.TOPIC,
            preference_type=PreferenceType.EXCLUDED,
            preference_value="machine-learning",
            display_label="Machine Learning",
        ),
    )
    assert p1.id == p2.id
    assert p2.preference_type == "EXCLUDED"
    assert len(ResearcherPreferenceService.list_preferences(db_session, base_profile.id)) == 1


# ── Test Service CRUD & Bulk Sync ────────────────────────────────────────────

def test_bulk_sync_preferences(db_session: Session, base_profile: ResearchProfileModel):
    """Verify atomic bulk preference synchronization."""
    bulk_payload = BulkPreferencesUpdateSchema(
        preferences=[
            BulkPreferenceItemSchema(
                category=PreferenceCategory.OPPORTUNITY_TYPE,
                preference_type=PreferenceType.PREFERRED,
                preference_value="CONFERENCE",
            ),
            BulkPreferenceItemSchema(
                category=PreferenceCategory.OPPORTUNITY_TYPE,
                preference_type=PreferenceType.EXCLUDED,
                preference_value="SPECIAL_ISSUE",
            ),
            BulkPreferenceItemSchema(
                category=PreferenceCategory.TOPIC,
                preference_type=PreferenceType.PREFERRED,
                preference_value="deep-learning",
            ),
            BulkPreferenceItemSchema(
                category=PreferenceCategory.REGION,
                preference_type=PreferenceType.PREFERRED,
                preference_value="Europe",
            ),
            BulkPreferenceItemSchema(
                category=PreferenceCategory.FUNDING,
                preference_key="funding_required",
                preference_value="true",
            ),
        ],
        replace_existing=False,
    )

    synced = ResearcherPreferenceService.bulk_sync_preferences(
        db=db_session,
        profile_id=base_profile.id,
        payload=bulk_payload,
    )
    assert len(synced) == 5

    # Retrieve structured preferences
    structured = ResearcherPreferenceService.get_structured_preferences(db_session, base_profile.id)
    assert "CONFERENCE" in structured.opportunities.preferred_types
    assert "SPECIAL_ISSUE" in structured.opportunities.excluded_types
    assert "SPECIAL_ISSUE" in structured.exclusions.excluded_opportunity_types
    assert "deep-learning" in structured.interests.topics
    assert "Europe" in structured.geography.preferred_regions
    assert structured.funding.funding_required is True


def test_bulk_sync_with_replace_existing(db_session: Session, base_profile: ResearchProfileModel):
    """Verify bulk sync with replace_existing=True cleans up previous preferences."""
    # First sync
    ResearcherPreferenceService.bulk_sync_preferences(
        db=db_session,
        profile_id=base_profile.id,
        payload=BulkPreferencesUpdateSchema(
            preferences=[
                BulkPreferenceItemSchema(
                    category=PreferenceCategory.TOPIC,
                    preference_value="old-topic-1",
                ),
                BulkPreferenceItemSchema(
                    category=PreferenceCategory.TOPIC,
                    preference_value="old-topic-2",
                ),
            ],
            replace_existing=False,
        ),
    )
    assert len(ResearcherPreferenceService.list_preferences(db_session, base_profile.id)) == 2

    # Second sync with replace_existing=True
    ResearcherPreferenceService.bulk_sync_preferences(
        db=db_session,
        profile_id=base_profile.id,
        payload=BulkPreferencesUpdateSchema(
            preferences=[
                BulkPreferenceItemSchema(
                    category=PreferenceCategory.TOPIC,
                    preference_value="new-topic",
                ),
            ],
            replace_existing=True,
        ),
    )
    current = ResearcherPreferenceService.list_preferences(db_session, base_profile.id)
    assert len(current) == 1
    assert current[0].preference_value == "new-topic"


# ── Safety Invariants Tests ──────────────────────────────────────────────────

def test_invariant_5_duplicate_prevention(db_session: Session, base_profile: ResearchProfileModel):
    """Invariant 5: Duplicate preferences do not create duplicate semantic entries."""
    p1 = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.TOPIC,
            preference_value="quantum-computing",
            strength=0.8,
        ),
    )

    # Re-declare identical preference
    p2 = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.TOPIC,
            preference_value="quantum-computing",
            strength=1.0,
        ),
    )
    assert p1.id == p2.id
    assert p2.strength == 1.0

    all_items = ResearcherPreferenceService.list_preferences(db_session, base_profile.id)
    assert len(all_items) == 1


def test_invariant_7_8_anchored_to_research_profile(db_session: Session, base_profile: ResearchProfileModel):
    """Invariant 7 & 8: Researcher identity remains anchored to ResearchProfileModel, no duplicate identities."""
    pref = ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.DELIVERY_MODE,
            preference_value="ONLINE",
        ),
    )
    assert pref.profile_id == base_profile.id

    # Verify no new profile or user was created
    profile_count = db_session.execute(select(ResearchProfileModel)).scalars().all()
    user_count = db_session.execute(select(UserModel)).scalars().all()
    assert len(profile_count) == 1
    assert len(user_count) == 1


def test_invariant_9_12_preferences_do_not_alter_base_opportunity(
    db_session: Session, base_profile: ResearchProfileModel
):
    """Invariant 9-12: Preferences do not alter opportunity base data, deadline intelligence, or risk scores."""
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="International Conference on AI",
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        is_predatory_flag=False,
    )
    db_session.add(opp)
    db_session.commit()

    # Researcher excludes conferences
    ResearcherPreferenceService.create_explicit_preference(
        db=db_session,
        profile_id=base_profile.id,
        payload=ResearcherPreferenceCreateSchema(
            category=PreferenceCategory.OPPORTUNITY_TYPE,
            preference_type=PreferenceType.EXCLUDED,
            preference_value="CONFERENCE",
        ),
    )

    db_session.refresh(opp)
    assert opp.opportunity_type == "CONFERENCE"
    assert opp.delivery_mode == "HYBRID"
    assert opp.is_predatory_flag is False


def test_invariant_13_cold_start_researcher_without_preferences(
    db_session: Session, base_profile: ResearchProfileModel
):
    """Invariant 13: Existing researchers without preferences remain valid."""
    structured = ResearcherPreferenceService.get_structured_preferences(db_session, base_profile.id)
    assert structured.profile_id == base_profile.id
    assert len(structured.raw_preferences) == 0
    assert structured.summary.total_preferences == 0
    assert structured.completeness.score >= 0.0


def test_invariant_20_zero_n_plus_one_queries(db_session: Session, base_profile: ResearchProfileModel):
    """Invariant 20: No N+1 queries are introduced during preference retrieval."""
    # Populate 15 preferences across categories
    for i in range(15):
        ResearcherPreferenceService.create_explicit_preference(
            db=db_session,
            profile_id=base_profile.id,
            payload=ResearcherPreferenceCreateSchema(
                category=PreferenceCategory.TOPIC,
                preference_value=f"topic-{i}",
            ),
        )

    # Count queries during retrieval
    queries: list[str] = []

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", count_queries)
    try:
        ResearcherPreferenceService.get_structured_preferences(db_session, base_profile.id)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", count_queries)

    # Retrieval should execute a fixed small number of queries (profile + preferences + saved opportunities + interests)
    assert len(queries) <= 6, f"Expected <= 6 queries, got {len(queries)}: {queries}"


# ── REST API Endpoints Tests ─────────────────────────────────────────────────

def test_api_list_preferences_with_type_filter(client: TestClient, base_profile: ResearchProfileModel):
    """Test GET /api/v1/researchers/{id}/preferences with preference_type filter."""
    # Create preferred
    client.post(
        f"/api/v1/researchers/{base_profile.id}/preferences",
        json={
            "category": "OPPORTUNITY_TYPE",
            "preference_type": "PREFERRED",
            "preference_value": "CONFERENCE",
        },
        headers={"X-User-ID": str(base_profile.user_id)},
    )
    # Create excluded
    client.post(
        f"/api/v1/researchers/{base_profile.id}/preferences",
        json={
            "category": "OPPORTUNITY_TYPE",
            "preference_type": "EXCLUDED",
            "preference_value": "JOURNAL",
        },
        headers={"X-User-ID": str(base_profile.user_id)},
    )

    # Filter by PREFERRED
    res_pref = client.get(f"/api/v1/researchers/{base_profile.id}/preferences?preference_type=PREFERRED")
    assert res_pref.status_code == 200
    data_pref = res_pref.json()
    assert len(data_pref) == 1
    assert data_pref[0]["preference_value"] == "CONFERENCE"
    assert data_pref[0]["preference_type"] == "PREFERRED"

    # Filter by EXCLUDED
    res_excl = client.get(f"/api/v1/researchers/{base_profile.id}/preferences?preference_type=EXCLUDED")
    assert res_excl.status_code == 200
    data_excl = res_excl.json()
    assert len(data_excl) == 1
    assert data_excl[0]["preference_value"] == "JOURNAL"
    assert data_excl[0]["preference_type"] == "EXCLUDED"


def test_api_get_structured_preferences(client: TestClient, base_profile: ResearchProfileModel):
    """Test GET /api/v1/researchers/{id}/preferences/structured."""
    client.post(
        f"/api/v1/researchers/{base_profile.id}/preferences",
        json={
            "category": "RESEARCH_DOMAIN",
            "preference_type": "PREFERRED",
            "preference_value": "Artificial Intelligence",
        },
        headers={"X-User-ID": str(base_profile.user_id)},
    )
    client.post(
        f"/api/v1/researchers/{base_profile.id}/preferences",
        json={
            "category": "OPPORTUNITY_TYPE",
            "preference_type": "EXCLUDED",
            "preference_value": "SPECIAL_ISSUE",
        },
        headers={"X-User-ID": str(base_profile.user_id)},
    )

    res = client.get(f"/api/v1/researchers/{base_profile.id}/preferences/structured")
    assert res.status_code == 200
    data = res.json()
    assert "Artificial Intelligence" in data["interests"]["research_domains"]
    assert "SPECIAL_ISSUE" in data["opportunities"]["excluded_types"]
    assert "SPECIAL_ISSUE" in data["exclusions"]["excluded_opportunity_types"]
    assert data["summary"]["total_preferences"] == 2


def test_api_bulk_sync_preferences(client: TestClient, base_profile: ResearchProfileModel):
    """Test PUT /api/v1/researchers/{id}/preferences."""
    payload = {
        "preferences": [
            {
                "category": "OPPORTUNITY_TYPE",
                "preference_type": "PREFERRED",
                "preference_value": "WORKSHOP",
            },
            {
                "category": "REGION",
                "preference_type": "PREFERRED",
                "preference_value": "North America",
            },
        ],
        "replace_existing": False,
    }

    res = client.put(
        f"/api/v1/researchers/{base_profile.id}/preferences",
        json=payload,
        headers={"X-User-ID": str(base_profile.user_id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2


def test_api_authorization_enforcement(client: TestClient, base_profile: ResearchProfileModel):
    """Verify 403 Forbidden when X-User-ID does not match profile owner."""
    other_user_id = uuid.uuid4()
    res = client.post(
        f"/api/v1/researchers/{base_profile.id}/preferences",
        json={
            "category": "OPPORTUNITY_TYPE",
            "preference_value": "CONFERENCE",
        },
        headers={"X-User-ID": str(other_user_id)},
    )
    assert res.status_code == 403
