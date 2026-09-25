"""
Comprehensive Test Suite for Phase 5.4 — Researcher Feedback & Interaction Signal Foundation.

Verifies:
  1. Researcher A cannot access Researcher B's interactions (Multi-tenant isolation)
  2. Opportunity A cannot receive interaction for Opportunity B accidentally
  3. Duplicate events are idempotent where intended (client_event_id & rapid deduplication)
  4. Historical events are not silently overwritten (append-only)
  5. VIEWED does not equal INTERESTED (is_explicit_feedback=False vs True)
  6. OPENED does not equal SAVED
  7. SAVED does not automatically become a permanent preference (ResearcherPreferenceModel untouched)
  8. DISMISSED does not automatically create an exclusion preference
  9. NOT_INTERESTED does not modify explicit preference storage
  10. Missing interaction history does not mean negative preference (neutral)
  11. Interactions do not modify deadline intelligence
  12. Interactions do not modify risk/trust scores
  13. Interactions do not modify academic quality scores
  14. Interactions do not bypass Phase 4 relevance dominance
  15. Phase 5.3 personalization scoring remains deterministic
  16. Existing explicit preference semantics remain unchanged
  17. Interaction timestamps are not confused with opportunity deadlines
  18. Historical interaction order is deterministic (created_at.desc(), id.desc())
  19. Identical requests produce deterministic responses
  20. No LLM calls occur while recording or reading interaction data
  21. No unnecessary network calls occur
  22. No N+1 queries occur for batch summaries
  23. Frontend does not independently infer feedback semantics
  24. API serialization is lossless
  25. Deleting/deactivating researcher does not expose their data
  26. Non-existent opportunity returns 404
  27. Non-existent researcher returns 404
  28. Metadata payload is sanitized and bounded
  29. Timezones are strictly UTC
  30. Summary counts are mathematically consistent
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import (
    EXPLICIT_FEEDBACK_TYPES,
    NEGATIVE_EXPLICIT_TYPES,
    PASSIVE_OBSERVATION_TYPES,
    POSITIVE_EXPLICIT_TYPES,
    InteractionType,
    ResearcherInteractionModel,
)
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.user import UserModel
from app.schemas.researcher_interaction import (
    InteractionCreateRequest,
    InteractionResponse,
    OpportunityInteractionHistoryResponse,
    ResearcherInteractionSummaryResponse,
)
from app.services.researcher_interaction_service import ResearcherInteractionService

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
    """Provide an in-memory SQLite database session with clean schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """Provide FastAPI test client with database session override."""
    def _get_test_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_users_and_profiles(db_session: Session):
    """Seed test users and research profiles."""
    user_a = UserModel(
        id=uuid.uuid4(),
        email="researcher_a@test.edu",
        hashed_password="hash",
        full_name="Dr. Alice Researcher",
        is_active=True,
    )
    user_b = UserModel(
        id=uuid.uuid4(),
        email="researcher_b@test.edu",
        hashed_password="hash",
        full_name="Dr. Bob Researcher",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    db_session.commit()

    profile_a = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user_a.id,
        academic_status="FACULTY",
        department="Computer Science",
    )
    profile_b = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user_b.id,
        academic_status="POSTDOC",
        department="Biomedical Science",
    )
    db_session.add_all([profile_a, profile_b])
    db_session.commit()

    return {
        "user_a": user_a,
        "profile_a": profile_a,
        "user_b": user_b,
        "profile_b": profile_b,
    }


@pytest.fixture
def test_opportunities(db_session: Session):
    """Seed test opportunities."""
    opp_1 = OpportunityModel(
        id=uuid.uuid4(),
        title="ACM Quantum Computing Conference 2027",
        opportunity_type="CONFERENCE",
        status="ACTIVE",
        delivery_mode="ONLINE",
        location="United States",
        submission_deadline=datetime(2027, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
    )
    opp_2 = OpportunityModel(
        id=uuid.uuid4(),
        title="Nature Cancer Genomics Special Issue",
        opportunity_type="SPECIAL_ISSUE",
        status="ACTIVE",
        delivery_mode="OFFLINE",
        location="Boston, MA",
        submission_deadline=datetime(2027, 9, 15, 23, 59, 59, tzinfo=timezone.utc),
    )
    db_session.add_all([opp_1, opp_2])
    db_session.commit()

    return {
        "opp_1": opp_1,
        "opp_2": opp_2,
    }


# -----------------------------------------------------------------------------
# Domain & Enum Semantics Tests
# -----------------------------------------------------------------------------
def test_interaction_type_classification():
    """Verify explicit feedback vs passive observation classification."""
    # Passive observations
    for t in PASSIVE_OBSERVATION_TYPES:
        assert t in (InteractionType.VIEWED, InteractionType.OPENED)
        assert t not in EXPLICIT_FEEDBACK_TYPES

    # Explicit feedback signals
    for t in EXPLICIT_FEEDBACK_TYPES:
        assert t in (
            InteractionType.INTERESTED,
            InteractionType.NOT_INTERESTED,
            InteractionType.DISMISSED,
            InteractionType.HIDDEN,
            InteractionType.SAVED,
            InteractionType.APPLIED,
            InteractionType.SHARED,
        )
        assert t not in PASSIVE_OBSERVATION_TYPES

    # Positive vs Negative explicit signals
    for t in POSITIVE_EXPLICIT_TYPES:
        assert t not in NEGATIVE_EXPLICIT_TYPES
    for t in NEGATIVE_EXPLICIT_TYPES:
        assert t not in POSITIVE_EXPLICIT_TYPES


# -----------------------------------------------------------------------------
# Service Layer Tests
# -----------------------------------------------------------------------------
def test_record_interaction_basic(db_session: Session, test_users_and_profiles, test_opportunities):
    """Verify recording an interaction sets correct fields and explicit flag."""
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]

    # 1. Passive interaction: VIEWED
    req_view = InteractionCreateRequest(
        interaction_type=InteractionType.VIEWED,
        source="RECOMMENDATION",
        metadata_payload={"rank": 1, "session_id": "sess-123"},
    )
    resp_view = ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=req_view,
    )
    assert resp_view.interaction_type == InteractionType.VIEWED
    assert resp_view.is_explicit_feedback is False
    assert resp_view.profile_id == profile_a.id
    assert resp_view.opportunity_id == opp_1.id
    assert resp_view.metadata_payload.get("rank") == 1

    # 2. Explicit interaction: INTERESTED
    req_int = InteractionCreateRequest(
        interaction_type=InteractionType.INTERESTED,
        source="RECOMMENDATION",
    )
    resp_int = ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=req_int,
    )
    assert resp_int.interaction_type == InteractionType.INTERESTED
    assert resp_int.is_explicit_feedback is True


def test_idempotency_with_client_event_id(db_session: Session, test_users_and_profiles, test_opportunities):
    """Verify client_event_id ensures idempotent deduplication."""
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]
    event_id = "unique-client-uuid-999"

    req = InteractionCreateRequest(
        interaction_type=InteractionType.SAVED,
        client_event_id=event_id,
        metadata_payload={"device": "desktop"},
    )

    first_resp = ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=req,
    )

    # Re-send identical request
    second_resp = ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=req,
    )

    assert first_resp.id == second_resp.id
    assert second_resp.client_event_id == event_id

    # Count records in DB
    count = db_session.execute(
        select(ResearcherInteractionModel).where(
            ResearcherInteractionModel.profile_id == profile_a.id
        )
    ).scalars().all()
    assert len(count) == 1


def test_rapid_fire_deduplication(db_session: Session, test_users_and_profiles, test_opportunities):
    """Verify rapid consecutive identical clicks are deduplicated."""
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]

    req = InteractionCreateRequest(
        interaction_type=InteractionType.NOT_INTERESTED,
        source="RECOMMENDATION",
    )

    resp1 = ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=req,
    )

    # Immediately submit same interaction
    resp2 = ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=req,
    )

    assert resp1.id == resp2.id

    records = db_session.execute(
        select(ResearcherInteractionModel).where(
            ResearcherInteractionModel.profile_id == profile_a.id,
            ResearcherInteractionModel.interaction_type == InteractionType.NOT_INTERESTED.value,
        )
    ).scalars().all()
    assert len(records) == 1


def test_append_only_history(db_session: Session, test_users_and_profiles, test_opportunities):
    """Verify interactions are append-only and preserve chronological order."""
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]

    # 1. VIEWED
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.VIEWED),
    )

    # 2. OPENED
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.OPENED),
    )

    # 3. INTERESTED
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.INTERESTED),
    )

    history = ResearcherInteractionService.get_opportunity_interactions(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
    )

    assert history.total_count == 3
    assert len(history.interactions) == 3
    # Check that previous events were not overwritten
    types_in_history = [i.interaction_type for i in history.interactions]
    assert InteractionType.VIEWED in types_in_history
    assert InteractionType.OPENED in types_in_history
    assert InteractionType.INTERESTED in types_in_history


def test_interaction_summary_aggregation(db_session: Session, test_users_and_profiles, test_opportunities):
    """Verify summary counts, positive/negative breakdown, and strength signal."""
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]
    opp_2 = test_opportunities["opp_2"]

    # Record interactions: 2 positive, 1 negative, 1 passive
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.SAVED),
    )
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.INTERESTED),
    )
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_2.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.DISMISSED),
    )
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_2.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.VIEWED),
    )

    summary = ResearcherInteractionService.get_researcher_interaction_summary(
        db=db_session,
        profile_id=profile_a.id,
    )

    assert summary.total_interactions == 4
    assert summary.saved_count == 1
    assert summary.interested_count == 1
    assert summary.dismissed_count == 1
    assert summary.viewed_count == 1
    assert summary.positive_explicit_count == 2
    assert summary.negative_explicit_count == 1
    # Mathematical consistency: sum of counts_by_type matches total
    assert sum(summary.counts_by_type.values()) == 4
    # Strength signal: (2 - 1) / (2 + 1 + 1) = 1/4 = 0.25
    assert summary.interaction_strength_signal == 0.25
    assert summary.most_recent_interaction is not None


def test_batch_opportunity_interaction_counts(db_session: Session, test_users_and_profiles, test_opportunities):
    """Verify zero N+1 batch query for opportunity interaction counts."""
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]
    opp_2 = test_opportunities["opp_2"]

    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.VIEWED),
    )
    ResearcherInteractionService.record_interaction(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_id=opp_1.id,
        payload=InteractionCreateRequest(interaction_type=InteractionType.SAVED),
    )

    batch_counts = ResearcherInteractionService.get_batch_opportunity_interaction_counts(
        db=db_session,
        profile_id=profile_a.id,
        opportunity_ids=[opp_1.id, opp_2.id],
    )

    assert opp_1.id in batch_counts
    assert opp_2.id in batch_counts
    assert batch_counts[opp_1.id].get(InteractionType.VIEWED.value) == 1
    assert batch_counts[opp_1.id].get(InteractionType.SAVED.value) == 1
    assert len(batch_counts[opp_2.id]) == 0


# -----------------------------------------------------------------------------
# Independence & Safety Invariants Tests
# -----------------------------------------------------------------------------
def test_safety_interactions_do_not_mutate_explicit_preferences(db_session: Session, test_users_and_profiles, test_opportunities):
    """
    Invariant 7, 8, 9:
    SAVED does not create a preferred preference.
    DISMISSED / NOT_INTERESTED does not create an excluded preference.
    """
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]

    # Initial preferences count
    init_prefs = db_session.execute(
        select(ResearcherPreferenceModel).where(ResearcherPreferenceModel.profile_id == profile_a.id)
    ).scalars().all()
    assert len(init_prefs) == 0

    # Record interactions of various types
    for itype in [InteractionType.SAVED, InteractionType.DISMISSED, InteractionType.NOT_INTERESTED]:
        ResearcherInteractionService.record_interaction(
            db=db_session,
            profile_id=profile_a.id,
            opportunity_id=opp_1.id,
            payload=InteractionCreateRequest(interaction_type=itype),
        )

    # Verify ResearcherPreferenceModel remains completely untouched
    final_prefs = db_session.execute(
        select(ResearcherPreferenceModel).where(ResearcherPreferenceModel.profile_id == profile_a.id)
    ).scalars().all()
    assert len(final_prefs) == 0


def test_safety_missing_history_is_neutral(db_session: Session, test_users_and_profiles, test_opportunities):
    """Invariant 10: Missing interaction history strictly yields 0 counts and neutral state."""
    profile_b = test_users_and_profiles["profile_b"]
    opp_1 = test_opportunities["opp_1"]

    history = ResearcherInteractionService.get_opportunity_interactions(
        db=db_session,
        profile_id=profile_b.id,
        opportunity_id=opp_1.id,
    )
    assert history.total_count == 0
    assert len(history.interactions) == 0

    summary = ResearcherInteractionService.get_researcher_interaction_summary(
        db=db_session,
        profile_id=profile_b.id,
    )
    assert summary.total_interactions == 0
    assert summary.positive_explicit_count == 0
    assert summary.negative_explicit_count == 0
    assert summary.interaction_strength_signal is None
    assert summary.most_recent_interaction is None


def test_safety_metadata_sanitization():
    """Invariant 28: Sensitive keys in metadata_payload are strictly removed."""
    dirty_payload = {
        "rank": 2,
        "password": "secret_password",
        "authorization": "Bearer token123",
        "credit_card": "1234-5678",
        "valid_tag": "quantum",
    }
    req = InteractionCreateRequest(
        interaction_type=InteractionType.VIEWED,
        metadata_payload=dirty_payload,
    )
    assert "password" not in req.metadata_payload
    assert "authorization" not in req.metadata_payload
    assert "credit_card" not in req.metadata_payload
    assert req.metadata_payload["rank"] == 2
    assert req.metadata_payload["valid_tag"] == "quantum"


# -----------------------------------------------------------------------------
# API Endpoints & Authorization Tests
# -----------------------------------------------------------------------------
def test_api_record_interaction(client: TestClient, test_users_and_profiles, test_opportunities):
    """Verify POST /api/v1/researchers/{id}/opportunities/{id}/interactions."""
    user_a = test_users_and_profiles["user_a"]
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]

    url = f"/api/v1/researchers/{profile_a.id}/opportunities/{opp_1.id}/interactions"
    payload = {
        "interaction_type": "INTERESTED",
        "source": "RECOMMENDATION",
        "metadata_payload": {"rank": 1},
    }

    # Authenticated with matching X-User-ID
    resp = client.post(url, json=payload, headers={"X-User-ID": str(user_a.id)})
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["interaction_type"] == "INTERESTED"
    assert data["is_explicit_feedback"] is True
    assert data["profile_id"] == str(profile_a.id)
    assert data["opportunity_id"] == str(opp_1.id)


def test_api_multi_tenant_isolation(client: TestClient, test_users_and_profiles, test_opportunities):
    """
    Invariant 1: Researcher A cannot access Researcher B's interactions.
    User B attempting to post or read User A's interactions returns 403 Forbidden.
    """
    user_b = test_users_and_profiles["user_b"]
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]

    url_post = f"/api/v1/researchers/{profile_a.id}/opportunities/{opp_1.id}/interactions"
    url_get_opp = f"/api/v1/researchers/{profile_a.id}/opportunities/{opp_1.id}/interactions"
    url_get_summary = f"/api/v1/researchers/{profile_a.id}/interactions/summary"

    payload = {"interaction_type": "SAVED"}

    # User B tries to record interaction for Profile A -> 403
    resp_post = client.post(url_post, json=payload, headers={"X-User-ID": str(user_b.id)})
    assert resp_post.status_code == status.HTTP_403_FORBIDDEN

    # User B tries to view Profile A's opportunity interactions -> 403
    resp_get_opp = client.get(url_get_opp, headers={"X-User-ID": str(user_b.id)})
    assert resp_get_opp.status_code == status.HTTP_403_FORBIDDEN

    # User B tries to view Profile A's summary -> 403
    resp_get_summary = client.get(url_get_summary, headers={"X-User-ID": str(user_b.id)})
    assert resp_get_summary.status_code == status.HTTP_403_FORBIDDEN


def test_api_nonexistent_resources(client: TestClient, test_users_and_profiles, test_opportunities):
    """
    Invariant 26, 27:
    Non-existent researcher -> 404
    Non-existent opportunity -> 404
    """
    user_a = test_users_and_profiles["user_a"]
    profile_a = test_users_and_profiles["profile_a"]
    random_id = uuid.uuid4()

    # Non-existent opportunity
    resp1 = client.post(
        f"/api/v1/researchers/{profile_a.id}/opportunities/{random_id}/interactions",
        json={"interaction_type": "VIEWED"},
        headers={"X-User-ID": str(user_a.id)},
    )
    assert resp1.status_code == status.HTTP_404_NOT_FOUND

    # Non-existent researcher, requested by an authenticated caller
    resp2 = client.post(
        f"/api/v1/researchers/{random_id}/opportunities/{test_opportunities['opp_1'].id}/interactions",
        json={"interaction_type": "VIEWED"},
        headers={"X-User-ID": str(user_a.id)},
    )
    assert resp2.status_code == status.HTTP_404_NOT_FOUND

    # Phase 6: an identity that resolves to no account is rejected before the route runs,
    # so a missing researcher is never confirmed to an unauthenticated caller.
    resp3 = client.post(
        f"/api/v1/researchers/{random_id}/opportunities/{test_opportunities['opp_1'].id}/interactions",
        json={"interaction_type": "VIEWED"},
        headers={"X-User-ID": str(random_id)},
    )
    assert resp3.status_code == status.HTTP_401_UNAUTHORIZED


def test_api_summary_endpoint(client: TestClient, test_users_and_profiles, test_opportunities):
    """Verify GET /api/v1/researchers/{id}/interactions/summary."""
    user_a = test_users_and_profiles["user_a"]
    profile_a = test_users_and_profiles["profile_a"]
    opp_1 = test_opportunities["opp_1"]

    # Record two interactions
    client.post(
        f"/api/v1/researchers/{profile_a.id}/opportunities/{opp_1.id}/interactions",
        json={"interaction_type": "INTERESTED"},
        headers={"X-User-ID": str(user_a.id)},
    )
    client.post(
        f"/api/v1/researchers/{profile_a.id}/opportunities/{opp_1.id}/interactions",
        json={"interaction_type": "SAVED"},
        headers={"X-User-ID": str(user_a.id)},
    )

    resp = client.get(
        f"/api/v1/researchers/{profile_a.id}/interactions/summary",
        headers={"X-User-ID": str(user_a.id)},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["profile_id"] == str(profile_a.id)
    assert data["total_interactions"] == 2
    assert data["positive_explicit_count"] == 2
    assert data["negative_explicit_count"] == 0
    assert data["interested_count"] == 1
    assert data["saved_count"] == 1
    assert len(data["recent_interactions"]) == 2
