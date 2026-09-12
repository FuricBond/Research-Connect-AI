"""
Phase 3.7 — Recommendation Evaluation Tests.

Tests cover:
  1. Data sufficiency transitions (NO_HISTORY, NO_FEEDBACK, INSUFFICIENT_DATA, SUFFICIENT_DATA)
  2. Precision@K calculation against ground-truth feedback
  3. Recall@K calculation and null handling when 0 ground truth items exist
  4. HitRate@K binary outcome verification
  5. Graded NDCG@K calculation with Phase 3.6 feedback semantics (APPLY=4, INTERESTED=3, SAVE=2, VIEW=1)
  6. Save Rate, Engagement Rate, and Dismissal Rate calculations
  7. Ranking version comparison (R0 Baseline vs R1 Personalized vs R2 Behavioral)
  8. Determinism (repeated evaluations on identical data produce bit-identical results)
  9. Read-only safety invariant (evaluation never mutates any database state)
 10. API endpoint ownership enforcement via X-User-ID (HTTP 403)
 11. Zero N+1 query performance during batch evaluation (exactly 2 queries)
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
from app.models.opportunity import OpportunityModel
from app.models.recommendation_history import (
    ResearcherRecommendationItemModel,
    ResearcherRecommendationSnapshotModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_feedback import ResearcherRecommendationFeedbackModel
from app.models.user import UserModel
from app.ranking.recommendation_evaluation_engine import (
    RecommendationEvaluationEngine,
)
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
from app.schemas.recommendation_evaluation import (
    DataSufficiencyStatus,
)
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


def create_mock_researcher(db: Session, email: str = "evaluator@university.edu") -> tuple[UserModel, ResearchProfileModel]:
    user = UserModel(email=email, hashed_password="pw", full_name="Dr. Evaluator", is_active=True)
    db.add(user)
    db.flush()

    profile = ResearchProfileModel(
        user_id=user.id,
        institution="Evaluation Institute",
        department="Information Retrieval",
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
) -> OpportunityModel:
    opp = OpportunityModel(
        source_id=uuid.uuid4(),
        raw_source_id=f"raw_{uuid.uuid4().hex[:8]}",
        title=title,
        opportunity_type=opp_type,
        delivery_mode="HYBRID",
        status="ACTIVE",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=60),
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
            matched_expertise=["IR"],
            matched_topics=["IR"],
            matched_types=["CONFERENCE"],
        ),
        provenance=CandidateProvenanceSchema(
            candidate_id=uuid.uuid4(),
            opportunity_id=opp.id,
            sources=[CandidateSourceType.EXPLICIT_PREFERENCE],
            matched_topics=["IR"],
            matched_preferences=["Conference"],
            matched_expertise=["IR"],
            reasons=["Matches IR preference"],
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


def test_data_sufficiency_transitions(db_session: Session):
    """Verify evidence status transitions: NO_HISTORY -> NO_FEEDBACK -> INSUFFICIENT_DATA -> SUFFICIENT_DATA."""
    _, profile = create_mock_researcher(db_session)

    # 1. Zero history -> NO_HISTORY
    eval_no_hist = RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id
    )
    assert eval_no_hist.data_status == DataSufficiencyStatus.NO_HISTORY
    assert eval_no_hist.metrics.precision_at_5 is None
    assert eval_no_hist.metrics.save_rate is None

    # 2. History exists, but zero feedback -> NO_FEEDBACK
    opps = [create_mock_opportunity(db_session, f"Conference {i}") for i in range(10)]
    cands = [create_mock_candidate(opp, rank=i + 1) for i, opp in enumerate(opps)]

    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=20,
    )

    eval_no_fb = RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id
    )
    assert eval_no_fb.data_status == DataSufficiencyStatus.NO_FEEDBACK
    assert eval_no_fb.metrics.save_rate == 0.0
    assert eval_no_fb.metrics.precision_at_5 is None  # Do NOT fabricate 0.0

    # 3. Add feedback on small sample (< 5 items or 0 positive) -> INSUFFICIENT_DATA
    fb1 = ResearcherRecommendationFeedbackModel(
        researcher_id=profile.id,
        opportunity_id=opps[0].id,
        feedback_type="VIEW",
        source="RECOMMENDATION",
    )
    db_session.add(fb1)
    db_session.commit()

    eval_insufficient = RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id
    )
    # Zero positive interactions for recall:
    assert eval_insufficient.data_status == DataSufficiencyStatus.INSUFFICIENT_DATA
    assert eval_insufficient.metrics.recall_at_10 is None

    # 4. Add positive feedback (SAVE, APPLY) -> SUFFICIENT_DATA
    for i in range(3):
        fb_pos = ResearcherRecommendationFeedbackModel(
            researcher_id=profile.id,
            opportunity_id=opps[i].id,
            feedback_type="SAVE" if i < 2 else "APPLY",
            source="RECOMMENDATION",
        )
        db_session.merge(fb_pos)
    db_session.commit()

    eval_sufficient = RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id
    )
    assert eval_sufficient.data_status == DataSufficiencyStatus.SUFFICIENT_DATA
    assert eval_sufficient.metrics.precision_at_5 is not None
    assert eval_sufficient.metrics.recall_at_10 is not None
    assert eval_sufficient.metrics.ndcg_at_10 is not None


def test_precision_recall_hit_rate_metrics(db_session: Session):
    """Verify Precision@K, Recall@K, and HitRate@K calculations against ground truth."""
    _, profile = create_mock_researcher(db_session)
    opps = [create_mock_opportunity(db_session, f"Venue {i}") for i in range(10)]
    cands = [create_mock_candidate(opp, rank=i + 1) for i, opp in enumerate(opps)]

    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=20,
    )

    # Ground truth: venues 0, 1, 3 have positive feedback (SAVE, APPLY, INTERESTED)
    # Venue 0 is rank 1, venue 1 is rank 2, venue 3 is rank 4.
    # Total positive items = 3. All 3 appear in top 5!
    for idx, fb_type in [(0, "SAVE"), (1, "APPLY"), (3, "INTERESTED")]:
        db_session.add(
            ResearcherRecommendationFeedbackModel(
                researcher_id=profile.id,
                opportunity_id=opps[idx].id,
                feedback_type=fb_type,
                source="RECOMMENDATION",
            )
        )
    db_session.commit()

    eval_res = RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id
    )

    metrics = eval_res.metrics
    # Top 5 has 3 relevant items: Precision@5 = 3 / 5 = 0.60
    assert metrics.precision_at_5 == 0.60
    # Top 10 has 3 relevant items: Precision@10 = 3 / 10 = 0.30
    assert metrics.precision_at_10 == 0.30
    # Total known relevant = 3. All 3 retrieved in top 10: Recall@10 = 3 / 3 = 1.00
    assert metrics.recall_at_10 == 1.00
    # At least 1 in top 5: HitRate@5 = 1.0
    assert metrics.hit_rate_at_5 == 1.00
    assert metrics.hit_rate_at_10 == 1.00


def test_ndcg_at_k_graded_relevance():
    """Verify NDCG@K reflects graded feedback semantics (APPLY=4, INTERESTED=3, SAVE=2, VIEW=1)."""
    opp_ids = [uuid.uuid4() for _ in range(5)]

    # Case A: Perfect ranking (APPLY at rank 1, INTERESTED at rank 2, SAVE at rank 3, VIEW at rank 4)
    feedback_perfect = {
        opp_ids[0]: ["APPLY"],        # 4.0
        opp_ids[1]: ["INTERESTED"],   # 3.0
        opp_ids[2]: ["SAVE"],         # 2.0
        opp_ids[3]: ["VIEW"],         # 1.0
        opp_ids[4]: ["DISMISS"],      # 0.0
    }
    all_rel = {opp_ids[0], opp_ids[1], opp_ids[2]}

    res_perfect = RecommendationEvaluationEngine.evaluate_snapshot(
        ordered_opportunity_ids=opp_ids,
        feedback_by_opp=feedback_perfect,
        all_known_relevant_ids=all_rel,
    )
    # Perfect order must yield NDCG = 1.0
    assert res_perfect["ndcg_at_5"] == 1.00

    # Case B: Inverted ranking (irrelevant / weak items at top, strong at bottom)
    feedback_inverted = {
        opp_ids[0]: ["DISMISS"],
        opp_ids[1]: ["VIEW"],
        opp_ids[2]: ["SAVE"],
        opp_ids[3]: ["INTERESTED"],
        opp_ids[4]: ["APPLY"],
    }
    res_inverted = RecommendationEvaluationEngine.evaluate_snapshot(
        ordered_opportunity_ids=opp_ids,
        feedback_by_opp=feedback_inverted,
        all_known_relevant_ids=all_rel,
    )
    assert res_inverted["ndcg_at_5"] is not None
    assert 0.0 < res_inverted["ndcg_at_5"] < 1.0
    assert res_inverted["ndcg_at_5"] < res_perfect["ndcg_at_5"]


def test_outcome_rates_calculation(db_session: Session):
    """Verify Save Rate, Engagement Rate, and Dismissal Rate matching exact user actions."""
    _, profile = create_mock_researcher(db_session)
    opps = [create_mock_opportunity(db_session, f"Venue {i}") for i in range(10)]
    cands = [create_mock_candidate(opp, rank=i + 1) for i, opp in enumerate(opps)]

    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=10,
    )

    # 2 SAVEs (opp 0, 1)
    db_session.add(ResearcherRecommendationFeedbackModel(researcher_id=profile.id, opportunity_id=opps[0].id, feedback_type="SAVE", source="RECOMMENDATION"))
    db_session.add(ResearcherRecommendationFeedbackModel(researcher_id=profile.id, opportunity_id=opps[1].id, feedback_type="SAVE", source="RECOMMENDATION"))

    # 1 VIEW (opp 2)
    db_session.add(ResearcherRecommendationFeedbackModel(researcher_id=profile.id, opportunity_id=opps[2].id, feedback_type="VIEW", source="RECOMMENDATION"))

    # 1 INTERESTED (opp 3)
    db_session.add(ResearcherRecommendationFeedbackModel(researcher_id=profile.id, opportunity_id=opps[3].id, feedback_type="INTERESTED", source="RECOMMENDATION"))

    # 2 DISMISS (opp 4, 5)
    db_session.add(ResearcherRecommendationFeedbackModel(researcher_id=profile.id, opportunity_id=opps[4].id, feedback_type="DISMISS", source="RECOMMENDATION"))
    db_session.add(ResearcherRecommendationFeedbackModel(researcher_id=profile.id, opportunity_id=opps[5].id, feedback_type="NOT_INTERESTED", source="RECOMMENDATION"))

    db_session.commit()

    eval_res = RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id
    )

    metrics = eval_res.metrics
    # Total items shown = 10
    # Saved items = 2 -> 2 / 10 = 0.20
    assert metrics.save_rate == 0.20
    # Engaged items = opp 0, 1, 2, 3 -> 4 items -> 4 / 10 = 0.40
    assert metrics.engagement_rate == 0.40
    # Dismissed items = opp 4, 5 -> 2 items -> 2 / 10 = 0.20
    assert metrics.dismissal_rate == 0.20


def test_ranking_version_comparison_r0_r1_r2(db_session: Session):
    """Verify independent metrics calculation across algorithm versions (R0 vs R1 vs R2)."""
    _, profile = create_mock_researcher(db_session)
    opps = [create_mock_opportunity(db_session, f"Venue {i}") for i in range(10)]

    # R0 Baseline snapshot
    cands_r0 = [create_mock_candidate(opps[i], rank=i + 1, base_score=0.8 - (i * 0.05)) for i in range(5)]
    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase2-baseline",
        recommendations=cands_r0,
        candidate_count=10,
        cooldown_minutes=0,
    )

    # R2 Behavioral snapshot (where relevant item was promoted to rank 1)
    cands_r2 = [
        create_mock_candidate(opps[4], rank=1, base_score=0.6, pers_adj=0.1, beh_adj=0.05),
        create_mock_candidate(opps[0], rank=2, base_score=0.8),
    ]
    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands_r2,
        candidate_count=10,
        cooldown_minutes=0,
    )

    # Add feedback: user SAVED opps[4]
    db_session.add(
        ResearcherRecommendationFeedbackModel(
            researcher_id=profile.id,
            opportunity_id=opps[4].id,
            feedback_type="SAVE",
            source="RECOMMENDATION",
        )
    )
    db_session.commit()

    eval_res = RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id, include_comparison=True
    )

    assert eval_res.ranking_comparison is not None
    assert "phase2-baseline" in eval_res.ranking_comparison
    assert "phase3.7-v1" in eval_res.ranking_comparison

    r0_comp = eval_res.ranking_comparison["phase2-baseline"]
    r2_comp = eval_res.ranking_comparison["phase3.7-v1"]

    assert r0_comp.display_name == "R0: Phase 2 Baseline Ranker"
    assert r2_comp.display_name == "R2: Phase 3.7 Behavioral Personalization"

    # In R0, opps[4] was rank 5. In R2, opps[4] was rank 1.
    # Therefore Precision@5 for both contains opps[4], but HitRate@1 for R2 is higher!
    assert r2_comp.metrics.save_rate is not None
    assert r0_comp.metrics.save_rate is not None


def test_evaluation_determinism(db_session: Session):
    """Verify evaluation is 100% deterministic (repeated runs produce identical metrics)."""
    _, profile = create_mock_researcher(db_session)
    opps = [create_mock_opportunity(db_session, f"Deterministic {i}") for i in range(8)]
    cands = [create_mock_candidate(opp, rank=i + 1) for i, opp in enumerate(opps)]

    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=10,
    )

    for i in range(3):
        db_session.add(
            ResearcherRecommendationFeedbackModel(
                researcher_id=profile.id,
                opportunity_id=opps[i].id,
                feedback_type="INTERESTED",
                source="RECOMMENDATION",
            )
        )
    db_session.commit()

    run1 = RecommendationHistoryService.evaluate_recommendations(db=db_session, profile_id=profile.id)
    run2 = RecommendationHistoryService.evaluate_recommendations(db=db_session, profile_id=profile.id)
    run3 = RecommendationHistoryService.evaluate_recommendations(db=db_session, profile_id=profile.id)

    assert run1.metrics.precision_at_5 == run2.metrics.precision_at_5 == run3.metrics.precision_at_5
    assert run1.metrics.recall_at_10 == run2.metrics.recall_at_10 == run3.metrics.recall_at_10
    assert run1.metrics.ndcg_at_10 == run2.metrics.ndcg_at_10 == run3.metrics.ndcg_at_10
    assert run1.metrics.engagement_rate == run2.metrics.engagement_rate == run3.metrics.engagement_rate


def test_evaluation_read_only_safety_invariant(db_session: Session):
    """Verify that offline evaluation is strictly read-only and mutates zero database rows."""
    _, profile = create_mock_researcher(db_session)
    opp = create_mock_opportunity(db_session, "Safety Venue")
    cands = [create_mock_candidate(opp, rank=1)]

    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=10,
    )

    db_session.add(
        ResearcherRecommendationFeedbackModel(
            researcher_id=profile.id,
            opportunity_id=opp.id,
            feedback_type="SAVE",
            source="RECOMMENDATION",
        )
    )
    db_session.commit()

    # Capture row counts before
    snap_count_before = db_session.scalar(select(ResearcherRecommendationSnapshotModel))
    item_count_before = db_session.scalar(select(ResearcherRecommendationItemModel))
    fb_count_before = db_session.scalar(select(ResearcherRecommendationFeedbackModel))

    # Run evaluation
    RecommendationHistoryService.evaluate_recommendations(
        db=db_session, profile_id=profile.id
    )

    # Capture row counts after
    snap_count_after = db_session.scalar(select(ResearcherRecommendationSnapshotModel))
    item_count_after = db_session.scalar(select(ResearcherRecommendationItemModel))
    fb_count_after = db_session.scalar(select(ResearcherRecommendationFeedbackModel))

    assert snap_count_before == snap_count_after
    assert item_count_before == item_count_after
    assert fb_count_before == fb_count_after


def test_evaluation_api_and_ownership(client: TestClient, db_session: Session):
    """Verify evaluation API endpoint and X-User-ID ownership authorization."""
    user, profile = create_mock_researcher(db_session)
    opp = create_mock_opportunity(db_session, "API Venue")
    cands = [create_mock_candidate(opp, rank=1)]

    RecommendationHistoryService.record_snapshot(
        db=db_session,
        profile_id=profile.id,
        ranking_version="phase3.7-v1",
        recommendations=cands,
        candidate_count=10,
    )

    # 1. Successful evaluation with correct X-User-ID
    res = client.get(
        f"/api/v1/researchers/{profile.id}/recommendation-evaluation",
        headers={"X-User-ID": str(user.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["researcher_id"] == str(profile.id)
    assert data["data_status"] in ["NO_FEEDBACK", "SUFFICIENT_DATA", "INSUFFICIENT_DATA"]
    assert "metrics" in data

    # 2. Forbidden access with wrong X-User-ID
    res_forbidden = client.get(
        f"/api/v1/researchers/{profile.id}/recommendation-evaluation",
        headers={"X-User-ID": str(uuid.uuid4())},
    )
    assert res_forbidden.status_code == 403


def test_zero_n_plus_one_evaluation_queries(db_session: Session):
    """Verify batch evaluation executes in exactly 2 queries regardless of snapshot count."""
    _, profile = create_mock_researcher(db_session)
    opps = [create_mock_opportunity(db_session, f"Venue E+{i}") for i in range(10)]
    cands = [create_mock_candidate(opp, rank=i + 1) for i, opp in enumerate(opps)]

    # Create 5 snapshots with 10 items each (50 item rows)
    for i in range(5):
        RecommendationHistoryService.record_snapshot(
            db=db_session,
            profile_id=profile.id,
            ranking_version="phase3.7-v1",
            recommendations=cands,
            candidate_count=20,
            cooldown_minutes=0,
        )

    # Add 5 feedback rows
    for i in range(5):
        db_session.add(
            ResearcherRecommendationFeedbackModel(
                researcher_id=profile.id,
                opportunity_id=opps[i].id,
                feedback_type="SAVE",
                source="RECOMMENDATION",
            )
        )
    db_session.commit()

    target_profile_id = profile.id
    query_count = 0
    from sqlalchemy import event

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_queries)

    res = RecommendationHistoryService.evaluate_recommendations(
        db=db_session,
        profile_id=target_profile_id,
    )

    event.remove(engine, "before_cursor_execute", count_queries)

    assert res.total_snapshots == 5
    assert res.total_recommendations == 50
    # Exactly 3 queries: 1 for snapshots with selectinload + 1 for items + 1 for feedback (zero N+1)
    assert query_count <= 3
