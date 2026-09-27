"""
Negative feedback must not break the Phase 3.5 personalized ranking.

A researcher who marks opportunities "not interested" gets a negative adaptive adjustment
(Phase 5.5 allows -0.10 to +0.10). The ranker wrote that signed value into
`inferred_preference_score`, a 0-1 match score, so the response failed validation and the
route, catching ValueError, answered 404 "not found": the researcher's ranking preview
disappeared after their first few dislikes. The signed value belongs in
`behavioral_adjustment`, which is where it is still reported.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

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
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import InteractionType, ResearcherInteractionModel
from app.models.user import UserModel

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_not_interested_feedback_keeps_the_personalized_ranking_available(client, db_session):
    user = UserModel(id=uuid.uuid4(), email="dislikes@univ.edu", full_name="Dana Dislikes",
                     hashed_password="x", role="STUDENT", is_active=True)
    profile = ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, keywords=["information retrieval"],
                                   target_opportunity_types=["CONFERENCE", "WORKSHOP"])
    conferences = [
        OpportunityModel(id=uuid.uuid4(), title=f"Conference on Information Retrieval {i}", opportunity_type="CONFERENCE",
                         delivery_mode="ONLINE", status="ACTIVE", publisher="ACM")
        for i in range(3)
    ]
    workshop = OpportunityModel(id=uuid.uuid4(), title="Workshop on Information Retrieval Evaluation",
                                opportunity_type="WORKSHOP", delivery_mode="ONLINE", status="ACTIVE", publisher="ACM")
    db_session.add_all([user, profile, *conferences, workshop])
    for opportunity in conferences:
        for _ in range(2):
            db_session.add(ResearcherInteractionModel(
                id=uuid.uuid4(), profile_id=profile.id, opportunity_id=opportunity.id,
                interaction_type=InteractionType.NOT_INTERESTED, is_explicit_feedback=True,
                created_at=datetime.now(timezone.utc),
            ))
    db_session.commit()
    headers = {"X-User-ID": str(user.id)}  # developer identity is on in the test suite

    recompute = client.post(f"/api/v1/researchers/{profile.id}/adaptive-signals/recompute", headers=headers)
    assert recompute.status_code == 200, recompute.text

    response = client.get(
        f"/api/v1/researchers/{profile.id}/personalized-recommendations"
        "?limit=20&include_inferred=true&include_expertise=true&enable_personalization=true",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["recommendations"]
    assert items, "the ranking must still list opportunities"
    breakdowns = [item["score_breakdown"] for item in items]
    assert all(0.0 <= b["inferred_preference_score"] <= 1.0 for b in breakdowns)
    assert any(b["behavioral_adjustment"] < 0 for b in breakdowns), "the negative evidence is still reported, signed"
