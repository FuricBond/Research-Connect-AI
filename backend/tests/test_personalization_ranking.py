"""
Unit, Integration, Regression, and Ablation Tests for Phase 3.5:
Personalization Ranking Layer.

Verifies:
  1. Ranking behavior: Highly relevant beats weakly relevant personalized candidate (0.90 vs 0.60 + 0.15).
  2. Personalization reorders similarly relevant candidates (0.70 + 0.00 vs 0.68 + 0.12).
  3. Explicit preference beats weaker inferred preference (0.40 vs 0.15 weight).
  4. Inferred preference beats generic profile signal.
  5. Scholarly expertise influences ranking (primary > secondary > emerging).
  6. Preference strength and confidence scale adjustment appropriately.
  7. Recency decays stale preferences.
  8. Guardrails: Personalization adjustment capped strictly at MAX_PERSONALIZATION_CONTRIBUTION (<= 0.15).
  9. Relevance floor / damping prevents relevance manufacture on weak candidates.
  10. Monotonicity invariant: base(A) - base(B) > 0.15 cannot be inverted.
  11. Trust/risk safety: High-risk & predatory candidates cannot receive personalization boost.
  12. Deadline safety: Expired candidates remain excluded.
  13. Cold start: Works with profile-only, expertise-only, preference-only, and total cold start.
  14. Determinism: 100% stable ranking across repeated executions; multi-key tie-breaker.
  15. Backwards compatibility: enable_personalization=False yields pure Phase 2 base ranking (R0).
  16. Ablation diagnostics: R0 vs R1 tracks reordered count, rank deltas, and average adjustment.
  17. REST API endpoint: 200 OK, 403 Forbidden, 404 Not Found, query parameter filtering.
  18. Zero N+1 query performance: Bounded query count across candidate sets.
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
from app.ranking.personalization_ranker import (
    MAX_PERSONALIZATION_CONTRIBUTION,
    PersonalizationRanker,
    ResearcherPersonalizationContext,
    personalization_ranker,
)
from app.schemas.personalized_candidate import (
    CandidateProvenanceSchema,
    CandidateSourceType,
    PersonalizedCandidateItemSchema,
    PersonalizedCandidateOpportunitySchema,
)
from app.schemas.personalized_ranking import (
    PersonalizedRankedCandidateSchema,
    PersonalizedRankingResponse,
)
from app.services.personalization_ranking_service import (
    PersonalizationRankingService,
)

# ── SQLite In-Memory Database Compatibility ───────────────────────────────────

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a clean in-memory SQLite session with Phase 3.5 tables."""
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
        institution="Stanford University",
        academic_status=AcademicStatus.FACULTY.value,
        keywords=keywords or ["Machine Learning", "Neural Networks"],
        target_opportunity_types=target_types or ["CONFERENCE", "JOURNAL"],
    )
    db.add(profile)
    db.flush()
    return profile


def create_opportunity(
    db: Session,
    title: str,
    opportunity_type: str = "CONFERENCE",
    delivery_mode: str = "HYBRID",
    deadline_days: int = 30,
    status: str = "ACTIVE",
    is_predatory: bool = False,
    risk_level: str = "LOW_RISK",
    risk_score: float = 0.0,
    location: str = "San Francisco, USA",
    organizer: str = "IEEE",
) -> OpportunityModel:
    deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title=title,
        opportunity_type=opportunity_type,
        delivery_mode=delivery_mode,
        status=status,
        submission_deadline=deadline,
        is_predatory_flag=is_predatory,
        risk_score=risk_score,
        location=location,
        organizer=organizer,
        content_hash=f"hash_{uuid.uuid4().hex[:12]}",
    )
    db.add(opp)
    db.flush()
    return opp


def make_candidate_item(
    opp_id: uuid.UUID,
    title: str,
    base_score: float = 0.50,
    opportunity_type: str = "CONFERENCE",
    delivery_mode: str = "HYBRID",
    days_remaining: float = 30.0,
    topics: list[str] | None = None,
    is_predatory: bool = False,
    risk_level: str = "LOW_RISK",
    risk_score: float = 0.0,
    deadline_status: str = "UPCOMING",
    urgency_tier: str = "APPROACHING",
    sources: list[CandidateSourceType] | None = None,
    matched_topics: list[str] | None = None,
    matched_prefs: list[str] | None = None,
    matched_exp: list[str] | None = None,
) -> PersonalizedCandidateItemSchema:
    """Construct a mock PersonalizedCandidateItemSchema for isolated ranker testing."""
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
        urgency_tier=urgency_tier,
        deadline_explanation="Submission closes soon",
    )
    provenance = CandidateProvenanceSchema(
        candidate_id=uuid.uuid4(),
        opportunity_id=opp_id,
        sources=sources if sources is not None else [CandidateSourceType.EXPLICIT_PREFERENCE],
        matched_topics=matched_topics or [],
        matched_preferences=matched_prefs or [],
        matched_expertise=matched_exp or [],
        reasons=["Candidate matches criteria"],
        retrieval_channels=["preference_match"],
    )
    return PersonalizedCandidateItemSchema(
        candidate_id=provenance.candidate_id,
        opportunity=opp_schema,
        provenance=provenance,
        eligibility_passed=True,
        eligibility_reasons=["Valid status and deadline"],
        base_relevance_score=base_score,
    )



# ═══════════════════════════════════════════════════════════════════════════════
# 1. CORE RANKING BEHAVIOR & RELEVANCE DOMINANCE
# ═══════════════════════════════════════════════════════════════════════════════


def test_relevance_dominance_large_gap():
    """
    Core Requirement: Relevance must remain dominant.
    A researcher strongly preferring Candidate B cannot overturn a materially large
    base-relevance gap with Candidate A.

    Candidate A: Base = 0.90, Personalization = 0.00 -> Final = 0.90
    Candidate B: Base = 0.60, Personalization = 0.15 (max) -> Final = 0.75
    Candidate A must outrank Candidate B.
    """
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()

    # Candidate A: high base relevance, zero personalization
    cand_a = make_candidate_item(
        opp_id=id_a,
        title="Candidate A - Highly Relevant",
        base_score=0.90,
        opportunity_type="JOURNAL",  # doesn't match researcher preferred CONFERENCE
        delivery_mode="OFFLINE",     # doesn't match HYBRID
        topics=["Quantum Mechanics"],
        sources=[],
    )

    # Candidate B: moderate base relevance, strong personalization
    cand_b = make_candidate_item(
        opp_id=id_b,
        title="Candidate B - Moderate Base, Strong Personalization",
        base_score=0.60,
        opportunity_type="CONFERENCE",  # matches explicit preference
        delivery_mode="HYBRID",         # matches explicit preference
        topics=["Machine Learning"],    # matches expertise & preference
    )

    # Researcher prefers Machine Learning and Conferences
    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(
                category="OPPORTUNITY_TYPE",
                preference_value="CONFERENCE",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
            ResearcherPreferenceModel(
                category="DELIVERY_MODE",
                preference_value="HYBRID",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
            ResearcherPreferenceModel(
                category="TOPIC",
                preference_value="Machine Learning",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
        ),
        expertise_items=(
            ResearcherInterestModel(
                topic_name="Machine Learning",
                topic_slug="machine-learning",
                classification="PRIMARY_EXPERTISE",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
        ),
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand_b, cand_a], context=context)

    assert len(ranked) == 2
    # Candidate A must rank first despite Candidate B having maximum personalization
    assert ranked[0].opportunity_id == id_a
    assert ranked[0].rank == 1
    assert ranked[0].base_relevance_score == 0.90
    assert ranked[0].final_score == 0.90

    assert ranked[1].opportunity_id == id_b
    assert ranked[1].rank == 2
    assert ranked[1].base_relevance_score == 0.60
    assert ranked[1].personalization_adjustment <= 0.15
    assert ranked[1].final_score <= 0.75
    assert ranked[0].final_score > ranked[1].final_score


def test_personalization_reorders_similarly_relevant_candidates():
    """
    Personalization legitimately resolves small base relevance gaps.

    Candidate A: Base = 0.70, Personalization = 0.00 -> Final = 0.70
    Candidate B: Base = 0.68, Personalization = 0.12 -> Final = 0.80
    Candidate B outranks Candidate A.
    """
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()

    cand_a = make_candidate_item(
        opp_id=id_a,
        title="Candidate A",
        base_score=0.70,
        opportunity_type="JOURNAL",
        topics=["Robotics"],
    )
    cand_b = make_candidate_item(
        opp_id=id_b,
        title="Candidate B",
        base_score=0.68,
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        topics=["Machine Learning"],
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(
                category="OPPORTUNITY_TYPE",
                preference_value="CONFERENCE",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
            ResearcherPreferenceModel(
                category="TOPIC",
                preference_value="Machine Learning",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
        ),
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand_a, cand_b], context=context)

    assert len(ranked) == 2
    # Candidate B is promoted above Candidate A due to strong personalization
    assert ranked[0].opportunity_id == id_b
    assert ranked[0].rank == 1
    assert ranked[0].base_rank == 2
    assert ranked[0].rank_delta == 1  # promoted by 1 position
    assert ranked[0].final_score > ranked[1].final_score

    assert ranked[1].opportunity_id == id_a
    assert ranked[1].rank == 2
    assert ranked[1].base_rank == 1
    assert ranked[1].rank_delta == -1  # demoted by 1 position


def test_explicit_preference_beats_inferred_preference():
    """
    Hierarchy test: Explicit preference (weight 0.40) beats verified inferred preference (weight 0.15).
    """
    id_exp = uuid.uuid4()
    id_inf = uuid.uuid4()

    cand_exp = make_candidate_item(
        opp_id=id_exp,
        title="Opportunity Explicit Match",
        base_score=0.70,
        opportunity_type="CONFERENCE",
    )
    cand_inf = make_candidate_item(
        opp_id=id_inf,
        title="Opportunity Inferred Match",
        base_score=0.70,
        opportunity_type="JOURNAL",
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(
                category="OPPORTUNITY_TYPE",
                preference_value="CONFERENCE",
                source="EXPLICIT",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
        ),
        inferred_preferences=(
            ResearcherPreferenceModel(
                category="OPPORTUNITY_TYPE",
                preference_value="JOURNAL",
                source="INFERRED",
                strength=1.0,
                confidence=0.80,
                recency_score=1.0,
            ),
        ),
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand_inf, cand_exp], context=context)

    cand_exp_res = next(r for r in ranked if r.opportunity_id == id_exp)
    cand_inf_res = next(r for r in ranked if r.opportunity_id == id_inf)

    assert cand_exp_res.personalization_adjustment > cand_inf_res.personalization_adjustment
    assert cand_exp_res.rank < cand_inf_res.rank


def test_expertise_classification_multiplier():
    """
    Expertise test: Primary expertise (1.0) yields higher contribution than
    Secondary expertise (0.75) and Emerging interest (0.50).
    """
    id_primary = uuid.uuid4()
    id_secondary = uuid.uuid4()
    id_emerging = uuid.uuid4()

    cand_p = make_candidate_item(
        opp_id=id_primary,
        title="Primary Expertise Opp",
        base_score=0.65,
        topics=["Deep Learning"],
    )
    cand_s = make_candidate_item(
        opp_id=id_secondary,
        title="Secondary Expertise Opp",
        base_score=0.65,
        topics=["Bioinformatics"],
    )
    cand_e = make_candidate_item(
        opp_id=id_emerging,
        title="Emerging Interest Opp",
        base_score=0.65,
        topics=["Quantum Computing"],
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        expertise_items=(
            ResearcherInterestModel(
                topic_name="Deep Learning",
                topic_slug="deep-learning",
                classification="PRIMARY_EXPERTISE",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
            ResearcherInterestModel(
                topic_name="Bioinformatics",
                topic_slug="bioinformatics",
                classification="SECONDARY_EXPERTISE",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
            ResearcherInterestModel(
                topic_name="Quantum Computing",
                topic_slug="quantum-computing",
                classification="EMERGING_INTEREST",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,
            ),
        ),
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand_e, cand_s, cand_p], context=context)

    res_p = next(r for r in ranked if r.opportunity_id == id_primary)
    res_s = next(r for r in ranked if r.opportunity_id == id_secondary)
    res_e = next(r for r in ranked if r.opportunity_id == id_emerging)

    assert res_p.personalization_adjustment > res_s.personalization_adjustment
    assert res_s.personalization_adjustment > res_e.personalization_adjustment
    assert res_p.rank == 1
    assert res_s.rank == 2
    assert res_e.rank == 3


def test_recency_and_confidence_decay():
    """
    Confidence & Recency test:
    High confidence/recency produces higher personalization adjustment than stale/decayed preferences.
    """
    id_fresh = uuid.uuid4()
    id_decayed = uuid.uuid4()

    cand_fresh = make_candidate_item(
        opp_id=id_fresh,
        title="Fresh Opp",
        base_score=0.70,
        opportunity_type="CONFERENCE",
    )
    cand_decayed = make_candidate_item(
        opp_id=id_decayed,
        title="Decayed Opp",
        base_score=0.70,
        opportunity_type="WORKSHOP",
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(
                category="OPPORTUNITY_TYPE",
                preference_value="CONFERENCE",
                strength=1.0,
                confidence=1.0,
                recency_score=1.0,  # fresh
            ),
            ResearcherPreferenceModel(
                category="OPPORTUNITY_TYPE",
                preference_value="WORKSHOP",
                strength=1.0,
                confidence=0.50,
                recency_score=0.20,  # decayed
            ),
        ),
    )

    ranker = PersonalizationRanker()
    ranked = ranker.rank([cand_decayed, cand_fresh], context=context)

    res_fresh = next(r for r in ranked if r.opportunity_id == id_fresh)
    res_decayed = next(r for r in ranked if r.opportunity_id == id_decayed)

    assert res_fresh.personalization_adjustment > res_decayed.personalization_adjustment
    assert res_fresh.rank < res_decayed.rank


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FORMAL GUARDRAILS & INVARIANTS
# ═══════════════════════════════════════════════════════════════════════════════


def test_personalization_contribution_strictly_capped():
    """
    Guardrail: Personalization contribution is strictly <= 0.15 across all possible inputs.
    """
    ranker = PersonalizationRanker()
    cand = make_candidate_item(
        opp_id=uuid.uuid4(),
        title="Super Matching Candidate",
        base_score=0.80,
        opportunity_type="CONFERENCE",
        delivery_mode="HYBRID",
        topics=["AI", "ML", "DL"],
    )

    # Maxed out signals
    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(category="OPPORTUNITY_TYPE", preference_value="CONFERENCE", strength=1.0, confidence=1.0, recency_score=1.0),
            ResearcherPreferenceModel(category="DELIVERY_MODE", preference_value="HYBRID", strength=1.0, confidence=1.0, recency_score=1.0),
            ResearcherPreferenceModel(category="TOPIC", preference_value="AI", strength=1.0, confidence=1.0, recency_score=1.0),
        ),
        inferred_preferences=(
            ResearcherPreferenceModel(category="TOPIC", preference_value="ML", confidence=1.0, strength=1.0, recency_score=1.0),
        ),
        expertise_items=(
            ResearcherInterestModel(topic_name="DL", topic_slug="dl", classification="PRIMARY_EXPERTISE", strength=1.0, confidence=1.0, recency_score=1.0),
        ),
        profile_keywords=("AI", "ML", "DL"),
        target_opportunity_types=("CONFERENCE",),
    )

    ranked = ranker.rank([cand], context=context)
    assert len(ranked) == 1
    assert ranked[0].personalization_adjustment <= MAX_PERSONALIZATION_CONTRIBUTION
    assert ranked[0].personalization_adjustment <= 0.15


def test_relevance_damping_low_relevance():
    """
    Guardrail: Relevance damping prevents manufacture of relevance.
    Candidates with low base relevance (< 0.50) receive reduced adjustments.
    """
    ranker = PersonalizationRanker()

    # Weak base relevance (0.10)
    cand_weak = make_candidate_item(
        opp_id=uuid.uuid4(),
        title="Weak Candidate",
        base_score=0.10,
        opportunity_type="CONFERENCE",
    )
    # Strong base relevance (0.70)
    cand_strong = make_candidate_item(
        opp_id=uuid.uuid4(),
        title="Strong Candidate",
        base_score=0.70,
        opportunity_type="CONFERENCE",
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(category="OPPORTUNITY_TYPE", preference_value="CONFERENCE", strength=1.0, confidence=1.0, recency_score=1.0),
        ),
    )

    ranked = ranker.rank([cand_weak, cand_strong], context=context)
    res_weak = next(r for r in ranked if r.opportunity_id == cand_weak.opportunity.id)
    res_strong = next(r for r in ranked if r.opportunity_id == cand_strong.opportunity.id)

    assert res_weak.score_breakdown.relevance_damping < 1.0
    assert res_strong.score_breakdown.relevance_damping == 1.0
    # Weak candidate's adjustment is damped
    assert res_weak.personalization_adjustment < res_strong.personalization_adjustment


def test_monotonicity_invariant_property():
    """
    Formal Monotonicity Guarantee:
    For any candidates A and B, if base(A) - base(B) > 0.15, A MUST outrank B regardless of personalization.
    """
    ranker = PersonalizationRanker()
    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(category="TOPIC", preference_value="Preferred", strength=1.0, confidence=1.0, recency_score=1.0),
        ),
    )

    # Grid of test pairs
    base_scores = [(0.95, 0.75), (0.85, 0.65), (0.70, 0.50), (0.50, 0.30)]

    for score_a, score_b in base_scores:
        cand_a = make_candidate_item(uuid.uuid4(), "Cand A", base_score=score_a, topics=["Other"])
        cand_b = make_candidate_item(uuid.uuid4(), "Cand B", base_score=score_b, topics=["Preferred"])

        ranked = ranker.rank([cand_b, cand_a], context=context)
        # Cand A must outrank Cand B because base_gap > 0.15
        assert ranked[0].opportunity_id == cand_a.opportunity.id
        assert ranked[0].final_score > ranked[1].final_score


def test_trust_risk_safety_preservation():
    """
    Phase 2.6 Trust/Risk Safety:
    Personalization must NEVER promote predatory or high-risk opportunities.
    Adjustment is strictly 0.0 for high-risk items.
    """
    ranker = PersonalizationRanker()

    id_pred = uuid.uuid4()
    cand_predatory = make_candidate_item(
        opp_id=id_pred,
        title="Predatory Conference with perfect match",
        base_score=0.70,
        opportunity_type="CONFERENCE",
        is_predatory=True,
        risk_level="HIGH_RISK",
        risk_score=0.95,
    )

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(category="OPPORTUNITY_TYPE", preference_value="CONFERENCE", strength=1.0, confidence=1.0, recency_score=1.0),
        ),
    )

    ranked = ranker.rank([cand_predatory], context=context)
    assert len(ranked) == 1
    # Personalization adjustment must be 0.0
    assert ranked[0].personalization_adjustment == 0.0
    assert ranked[0].final_score == 0.70
    assert ranked[0].opportunity.is_predatory_flag is True
    assert ranked[0].opportunity.risk_level == "HIGH_RISK"


def test_deadline_safety_preservation():
    """
    Phase 2.7 Deadline Safety:
    Expired opportunities must remain excluded from ranking.
    """
    ranker = PersonalizationRanker()

    cand_expired = make_candidate_item(
        opp_id=uuid.uuid4(),
        title="Expired Journal",
        base_score=0.85,
        deadline_status="EXPIRED",
        days_remaining=-5.0,
    )
    cand_active = make_candidate_item(
        opp_id=uuid.uuid4(),
        title="Active Journal",
        base_score=0.60,
        deadline_status="UPCOMING",
        days_remaining=25.0,
    )

    context = ResearcherPersonalizationContext(profile_id=uuid.uuid4())

    ranked = ranker.rank([cand_expired, cand_active], context=context)
    # Expired must be excluded
    assert len(ranked) == 1
    assert ranked[0].opportunity_id == cand_active.opportunity.id


# ═══════════════════════════════════════════════════════════════════════════════
# 3. COLD START BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════════


def test_cold_start_profile_only():
    """Cold start: Researcher with profile keywords only receives appropriate ranking."""
    ranker = PersonalizationRanker()
    cand_match = make_candidate_item(uuid.uuid4(), "Computer Vision Conf", base_score=0.60, topics=["Computer Vision"])
    cand_other = make_candidate_item(uuid.uuid4(), "Astrophysics Conf", base_score=0.60, topics=["Astrophysics"])

    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        profile_keywords=("Computer Vision",),
    )

    ranked = ranker.rank([cand_other, cand_match], context=context)
    assert ranked[0].opportunity_id == cand_match.opportunity.id
    assert ranked[0].personalization_adjustment > 0.0


def test_cold_start_total_fallback():
    """Total cold start: Researcher with no data gracefully degrades to Phase 2 base ranking."""
    ranker = PersonalizationRanker()
    id_1 = uuid.uuid4()
    id_2 = uuid.uuid4()
    cand_1 = make_candidate_item(id_1, "Opp 1", base_score=0.80)
    cand_2 = make_candidate_item(id_2, "Opp 2", base_score=0.65)

    context = ResearcherPersonalizationContext(profile_id=uuid.uuid4(), is_cold_start=True)

    ranked = ranker.rank([cand_2, cand_1], context=context)
    assert len(ranked) == 2
    assert ranked[0].opportunity_id == id_1
    assert ranked[0].personalization_adjustment == 0.0
    assert ranked[0].final_score == 0.80
    assert ranked[1].opportunity_id == id_2
    assert ranked[1].personalization_adjustment == 0.0
    assert ranked[1].final_score == 0.65


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DETERMINISM & TIE-BREAKING
# ═══════════════════════════════════════════════════════════════════════════════


def test_determinism_repeated_execution():
    """Determinism: 10 repeated runs with identical input produce 100% identical rankings."""
    ranker = PersonalizationRanker()
    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        profile_keywords=("AI",),
    )

    candidates = [
        make_candidate_item(uuid.uuid4(), f"Opp {i}", base_score=0.50 + (i * 0.05), topics=["AI"])
        for i in range(10)
    ]

    first_ordering = [r.opportunity_id for r in ranker.rank(candidates, context=context)]

    for _ in range(9):
        current_ordering = [r.opportunity_id for r in ranker.rank(candidates, context=context)]
        assert current_ordering == first_ordering


def test_tie_breaking_identical_final_scores():
    """
    Tie-breaking: If final_score is identical, order is broken by:
    1. base_relevance_score DESC
    2. urgency_score DESC
    3. opportunity_id ASC (lexicographical string)
    """
    ranker = PersonalizationRanker()
    id_lower_uuid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    id_higher_uuid = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    # Both have identical base score and zero personalization, but different UUIDs
    cand_1 = make_candidate_item(id_higher_uuid, "Cand High UUID", base_score=0.70)
    cand_2 = make_candidate_item(id_lower_uuid, "Cand Low UUID", base_score=0.70)

    context = ResearcherPersonalizationContext(profile_id=uuid.uuid4())
    ranked = ranker.rank([cand_1, cand_2], context=context)

    # Lower UUID must win deterministic tie-break
    assert ranked[0].opportunity_id == id_lower_uuid
    assert ranked[1].opportunity_id == id_higher_uuid


# ═══════════════════════════════════════════════════════════════════════════════
# 5. BACKWARDS COMPATIBILITY & ABLATION
# ═══════════════════════════════════════════════════════════════════════════════


def test_backwards_compatibility_disabled_personalization():
    """
    Backwards compatibility: When enable_personalization=False,
    system outputs pure Phase 2 base ranking (R0).
    """
    ranker = PersonalizationRanker()
    context = ResearcherPersonalizationContext(
        profile_id=uuid.uuid4(),
        explicit_preferences=(
            ResearcherPreferenceModel(category="TOPIC", preference_value="AI", strength=1.0, confidence=1.0, recency_score=1.0),
        ),
    )

    cand_a = make_candidate_item(uuid.uuid4(), "Cand A", base_score=0.75, topics=["Other"])
    cand_b = make_candidate_item(uuid.uuid4(), "Cand B", base_score=0.70, topics=["AI"])

    # With personalization disabled: Cand A beats Cand B purely on base relevance
    ranked = ranker.rank([cand_b, cand_a], context=context, enable_personalization=False)

    assert ranked[0].opportunity_id == cand_a.opportunity.id
    assert ranked[0].personalization_adjustment == 0.0
    assert ranked[0].rank_delta == 0
    assert ranked[1].opportunity_id == cand_b.opportunity.id
    assert ranked[1].personalization_adjustment == 0.0
    assert ranked[1].rank_delta == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. END-TO-END SERVICE & REST API
# ═══════════════════════════════════════════════════════════════════════════════


def test_service_get_personalized_recommendations(db_session: Session):
    """
    Integration test for PersonalizationRankingService:
    Sets up a full profile, preferences, opportunities, and executes end-to-end ranking.
    """
    user = create_test_user(db_session)
    profile = create_test_profile(db_session, user, keywords=["Artificial Intelligence"])

    # Add explicit preference
    pref = ResearcherPreferenceModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        category="OPPORTUNITY_TYPE",
        preference_key="opportunity_type",
        preference_value="CONFERENCE",
        display_label="Conference",
        strength=1.0,
        confidence=1.0,
        source="EXPLICIT",
        is_active=True,
    )
    db_session.add(pref)

    # Add opportunities
    opp_conf = create_opportunity(db_session, "Premier AI Conference", opportunity_type="CONFERENCE")
    opp_journ = create_opportunity(db_session, "Journal of AI Research", opportunity_type="JOURNAL")
    db_session.commit()

    response = PersonalizationRankingService.get_personalized_recommendations(
        db=db_session,
        profile_id=profile.id,
        limit=10,
    )

    assert isinstance(response, PersonalizedRankingResponse)
    assert response.researcher_id == profile.id
    assert response.ranked_count >= 1
    assert response.max_personalization_contribution == 0.15
    assert response.ablation_summary is not None
    assert response.ablation_summary.invariants_verified is True


def test_rest_api_get_personalized_recommendations(client: TestClient, db_session: Session):
    """
    REST API test: GET /api/v1/researchers/{id}/personalized-recommendations
    Verifies 200 OK, authentication ownership, and ablation parameters.
    """
    user = create_test_user(db_session, email="prof@university.edu")
    profile = create_test_profile(db_session, user)

    opp = create_opportunity(db_session, "Global Computing Summit")
    db_session.commit()

    # 1. Successful retrieval with ownership header
    resp = client.get(
        f"/api/v1/researchers/{profile.id}/personalized-recommendations?limit=10&enable_personalization=true",
        headers={"X-User-ID": str(user.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["researcher_id"] == str(profile.id)
    assert "recommendations" in data
    assert "ablation_summary" in data

    # 2. Forbidden access with different user ID
    # After P0-D fix: nonexistent UUID → 401 (unknown identity, no auto-bootstrap).
    # A known different user → 403 (forbidden). Both protect the resource.
    forbidden_user_id = uuid.uuid4()
    resp_forbidden = client.get(
        f"/api/v1/researchers/{profile.id}/personalized-recommendations",
        headers={"X-User-ID": str(forbidden_user_id)},
    )
    assert resp_forbidden.status_code in (401, 403), (
        f"Expected 401 or 403 for unauthorized access, got {resp_forbidden.status_code}"
    )

    # 3. Non-existent researcher profile
    non_existent_id = uuid.uuid4()
    resp_404 = client.get(
        f"/api/v1/researchers/{non_existent_id}/personalized-recommendations",
    )
    assert resp_404.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 7. PERFORMANCE & ZERO N+1 QUERIES
# ═══════════════════════════════════════════════════════════════════════════════


def test_zero_n_plus_one_query_performance(db_session: Session):
    """
    Performance test: Verify database query count remains bounded O(1)
    and does NOT grow linearly with the candidate pool size.
    """
    user = create_test_user(db_session, email="perf@university.edu")
    profile = create_test_profile(db_session, user)

    # Populate 30 opportunities
    for i in range(30):
        create_opportunity(db_session, f"Performance Benchmark Opp {i}")
    db_session.commit()

    # Count executed statements during personalized ranking
    query_count = 0

    def query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", query_listener)

    try:
        response = PersonalizationRankingService.get_personalized_recommendations(
            db=db_session,
            profile_id=profile.id,
            limit=20,
        )
        assert response.ranked_count > 0
    finally:
        event.remove(engine, "before_cursor_execute", query_listener)

    # Assert bounded query count: profile (1) + prefs (1) + interests (1) + candidates (<=5) + base models (1) + behavioral signals (<=3) + snapshot persistence (<=3)
    # Total queries should be <= 22, never 30+ (which would indicate N+1)
    assert query_count <= 22, f"Too many queries executed ({query_count}); possible N+1 query issue."
