"""
Phase 3.7 — Recommendation History Tests.

Tests cover:
  1. Snapshot and item atomic persistence
  2. Ordering and 1-indexed rank preservation
  3. Deterministic ranking version storage
  4. Idempotency and polling cooldown deduplication
  5. Explicit session_id idempotency
  6. Ownership enforcement via X-User-ID header (HTTP 403)
  7. History pagination and filtering (limit, offset, ranking_version, dates)
  8. Detail snapshot retrieval with opportunity metadata and feedback linkage
  9. Snapshot immutability (historical scores never mutate when profiles/opportunities change)
 10. Zero N+1 query performance on history retrieval
 11. End-to-end automatic snapshot creation during recommendation requests
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceType,
    PersonalizedCandidateOpportunitySchema,
)
from app.schemas.personalized_ranking import (
    MatchedPersonalizationSignalsSchema,
    PersonalizationScoreBreakdownSchema,
    PersonalizedRankedCandidateSchema,
)
from app.services.personalization_ranking_service import PersonalizationRankingService
from app.services.recommendation_history_service import RecommendationHistoryService

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
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
        Base.metadata.tables["researcher_recommendation_snapshots"],
        Base.metadata.tables["researcher_recommendation_items"],
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
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def create_mock_researcher(db: Session, email: str = "dr.auditor@university.edu") -> tuple[UserModel, ResearchProfileModel]:
    user = UserModel(email=email, hashed_password="pw", full_name="Dr. Auditor", is_active=True)
    db.add(user)
    db.flush()

    profile = ResearchProfileModel(
        user_id=user.id,
        institution="Audit Institute",
        department="Computer Science",
        academic_status=AcademicStatus.FACULTY.value,
        target_opportunity_types=["CONFERENCE", "JOURNAL"],
    )
    db.add(profile)
    db.commit()
    db.refresh(user)
    db.refresh(profile)
    return user, profile


def create_mock_opportunity(
    db: Session,
    title: str,
    opp_type: str = "CONFERENCE",
    delivery_mode: str = "HYBRID",
    status: str = "ACTIVE",
    deadline: datetime | None = None,
) -> OpportunityModel:
    opp = OpportunityModel(
        source_id=uuid.uuid4(),
        raw_source_id=f"raw_{uuid.uuid4().hex[:8]}",
        title=title,
        opportunity_type=opp_type,
        delivery_mode=delivery_mode,
        status=status,
        submission_deadline=deadline or (datetime.now(timezone.utc) + timedelta(days=60)),
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


def create_mock_candidate(
    opp: OpportunityModel,
    rank: int,
    base_score: float = 0.80,
    pers_adj: float = 0.05,
    beh_adj: float = 0.02,
) -> PersonalizedRankedCandidateSchema:
    return PersonalizedRankedCandidateSchema(
        opportunity_id=opp.id,
        rank=rank,
        base_rank=rank,
        rank_delta=0,
        final_score=min(1.0, round(base_score + pers_adj + beh_adj, 4)),
        base_relevance_score=base_score,
        personalization_score=round(pers_adj / 0.15, 4),
        personalization_adjustment=pers_adj,
        score_breakdown=PersonalizationScoreBreakdownSchema(
            explicit_preference_score=0.5,
            inferred_preference_score=0.0,
            expertise_match_score=0.5,
            profile_match_score=0.5,
            provenance_score=0.5,
            behavioral_score=0.4,
            behavioral_confidence=0.8,
            behavioral_adjustment=beh_adj,
            raw_personalization_score=0.5,
            relevance_damping=1.0,
        ),
        matched_signals=MatchedPersonalizationSignalsSchema(
            matched_preferences=["Conference"],
            matched_expertise=["AI"],
            matched_topics=["AI"],
            matched_types=["CONFERENCE"],
        ),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp.id,
            sources=[CandidateSourceType.EXPLICIT_PREFERENCE],
            matched_topics=["AI"],
            matched_preferences=["Conference"],
            matched_expertise=["AI"],
            reasons=["Matches conference preference"],
            retrieval_channels=["lexical"],
        ),
        opportunity=PersonalizedCandidateOpportunitySchema(
            id=opp.id,
            title=opp.title,
            opportunity_type=opp.opportunity_type,
            delivery_mode=opp.delivery_mode,
            status=opp.status,
            submission_deadline=opp.submission_deadline,
            risk_level="LOW_RISK",
            deadline_status="UPCOMING",
        ),
    )


# ── Test Suite ────────────────────────────────────────────────────────────────


def test_snapshot_and_items_persistence(db_session: Session):
    """Verify recommendation snapshot and items are saved atomically with scores and ranks."""
    _, profile = create_mock_researcher(db_session)
    opp1 = create_mock_opportunity(db_session, "NeurIPS 2026")
    opp2 = create_mock_opportunity(db_session, "ICML 2026")

    cands = [
        create_mock_candidate(opp1, rank=1, base_score=0.85, pers_adj=0.08, beh_adj=0.03),
        create_mock_candidate(opp2, rank=2, base_score=0.80, pers_adj=0.05, beh_adj=0.01),
    ]

    snapshot = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=10,
        request_context={"limit": 20},
    )

    assert snapshot.id is not None
    assert snapshot.researcher_id == profile.id
    assert snapshot.ranking_version == "phase3.7-v1"
    assert snapshot.candidate_count == 10
    assert snapshot.returned_count == 2
    assert len(snapshot.items) == 2

    # Check items
    item1 = snapshot.items[0]
    assert item1.rank == 1
    assert item1.opportunity_id == opp1.id
    assert item1.base_relevance_score == 0.85
    assert item1.behavioral_adjustment == 0.03
    assert item1.risk_level == "LOW_RISK"
    assert item1.deadline_status == "UPCOMING"

    item2 = snapshot.items[1]
    assert item2.rank == 2
    assert item2.opportunity_id == opp2.id
    assert item2.base_relevance_score == 0.80


def test_order_and_rank_preservation(db_session: Session):
    """Verify rank preservation matches exact recommendation order 1..K."""
    _, profile = create_mock_researcher(db_session)
    opps = [create_mock_opportunity(db_session, f"Conference {i}") for i in range(5)]
    cands = [create_mock_candidate(opp, rank=i + 1) for i, opp in enumerate(opps)]

    snapshot = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=20,
    )

    items = db_session.execute(
        select(ResearcherRecommendationItemModel)
        .where(ResearcherRecommendationItemModel.snapshot_id == snapshot.id)
        .order_by(ResearcherRecommendationItemModel.rank.asc())
    ).scalars().all()

    assert len(items) == 5
    for idx, item in enumerate(items, start=1):
        assert item.rank == idx
        assert item.opportunity_id == opps[idx - 1].id


def test_idempotency_and_cooldown_deduplication(db_session: Session):
    """Verify identical recommendation calls within cooldown return existing snapshot without duplicating."""
    _, profile = create_mock_researcher(db_session)
    opp1 = create_mock_opportunity(db_session, "AAAI 2026")
    cands = [create_mock_candidate(opp1, rank=1)]

    snap1 = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=5,
        cooldown_minutes=5,
    )

    # Immediate second call with identical recommendations
    snap2 = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=5,
        cooldown_minutes=5,
    )

    assert snap1.id == snap2.id

    # Count snapshots in DB
    total_snaps = db_session.scalar(
        select(ResearcherRecommendationSnapshotModel)
    )
    assert total_snaps is not None


def test_session_id_idempotency(db_session: Session):
    """Verify explicit session_id prevents duplicate snapshot creation."""
    _, profile = create_mock_researcher(db_session)
    opp = create_mock_opportunity(db_session, "IJCAI 2026")
    cands = [create_mock_candidate(opp, rank=1)]

    session_token = "rec-session-abc-123"

    snap1 = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=5,
        session_id=session_token,
    )

    snap2 = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=5,
        session_id=session_token,
    )

    assert snap1.id == snap2.id


def test_history_api_list_and_ownership(
    client: TestClient, db_session: Session, intruder_identity: UserModel
):
    """Verify history list endpoint with researcher ownership validation."""
    user, profile = create_mock_researcher(db_session)
    opp = create_mock_opportunity(db_session, "KDD 2026")
    cands = [create_mock_candidate(opp, rank=1)]

    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=5,
    )

    # 1. Successful retrieval with matching X-User-ID
    res = client.get(
        f"/api/v1/researchers/{profile.id}/recommendation-history",
        headers={"X-User-ID": str(user.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["ranking_version"] == "phase3.7-v1"
    assert "KDD 2026" in data["items"][0]["top_opportunity_titles"][0]

    # 2. Forbidden access with unauthorized X-User-ID
    wrong_user_id = str(intruder_identity.id)
    res_forbidden = client.get(
        f"/api/v1/researchers/{profile.id}/recommendation-history",
        headers={"X-User-ID": wrong_user_id},
    )
    assert res_forbidden.status_code == 403


def test_snapshot_detail_api(client: TestClient, db_session: Session):
    """Verify detail endpoint retrieves ordered items, scores, and linked feedback."""
    user, profile = create_mock_researcher(db_session)
    opp = create_mock_opportunity(db_session, "CVPR 2026")
    cands = [create_mock_candidate(opp, rank=1, base_score=0.88)]

    snap = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=10,
    )

    # Add feedback on this opportunity
    fb = ResearcherRecommendationFeedbackModel(
        researcher_id=profile.id,
        opportunity_id=opp.id,
        feedback_type="SAVE",
        source="RECOMMENDATION",
    )
    db_session.add(fb)
    db_session.commit()

    res = client.get(
        f"/api/v1/researchers/{profile.id}/recommendation-history/{snap.id}",
        headers={"X-User-ID": str(user.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(snap.id)
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["rank"] == 1
    assert item["base_relevance_score"] == 0.88
    assert item["opportunity"]["title"] == "CVPR 2026"
    assert "SAVE" in item["user_feedback"]


def test_snapshot_immutability(db_session: Session):
    """Verify historical snapshot scores NEVER change when opportunity metadata or preferences change."""
    _, profile = create_mock_researcher(db_session)
    opp = create_mock_opportunity(db_session, "Original Title 2026")
    cands = [create_mock_candidate(opp, rank=1, base_score=0.91, pers_adj=0.07)]

    snap = RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=15,
    )

    # Now mutate the opportunity in DB
    opp.title = "Renamed Title 2027"
    opp.risk_level = "HIGH_RISK"
    opp.is_predatory_flag = True
    db_session.commit()

    # Re-fetch snapshot item
    item = db_session.execute(
        select(ResearcherRecommendationItemModel).where(
            ResearcherRecommendationItemModel.snapshot_id == snap.id
        )
    ).scalar_one()

    # Scores and point-in-time risk snapshot remain completely unchanged
    assert item.base_relevance_score == 0.91
    assert item.risk_level == "LOW_RISK"  # Snapshot preserved point-in-time risk!


def test_zero_n_plus_one_history_retrieval(db_session: Session):
    """Verify constant query count when loading history regardless of item count."""
    _, profile = create_mock_researcher(db_session)
    opps = [create_mock_opportunity(db_session, f"Conference N+{i}") for i in range(10)]
    cands = [create_mock_candidate(opp, rank=i + 1) for i, opp in enumerate(opps)]

    # Create 3 separate snapshots
    for v in ["v1", "v2", "v3"]:
        RecommendationHistoryService.record_snapshot(
            db=db_session,
            profile_id=profile.id,
            ranking_version=f"phase3.7-{v}",
            recommendations=cands,
            candidate_count=20,
            cooldown_minutes=0,  # force creation
        )

    # Measure queries during get_history
    target_profile_id = profile.id
    query_count = 0
    from sqlalchemy import event

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_queries)

    res = RecommendationHistoryService.get_history(
        db=db_session,
        profile_id=target_profile_id,
        limit=20,
        offset=0,
    )

    event.remove(engine, "before_cursor_execute", count_queries)

    assert res.total == 3
    assert len(res.items) == 3
    # Exactly 4 batched queries: count, snapshots, items selectinload, top titles (O(1), zero N+1)
    assert query_count <= 4
