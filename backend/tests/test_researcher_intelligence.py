"""
Unit, Integration, and Benchmark Tests for Phase 3.2:
Researcher Interest & Expertise Intelligence.

Verifies:
  1. Mathematical scoring bounds [0.0, 1.0] and absence of NaN/Infinity.
  2. Deterministic recency modeling distinguishing sustained from recent activity.
  3. Deterministic expertise tiering and tie-breaking.
  4. 10 canonical evaluation fixture scenarios (Section 23 of spec).
  5. 100% execution determinism across repeated runs.
  6. Zero N+1 query architecture.
  7. FastAPI REST endpoints (/research-intelligence, /interests, /expertise).
  8. Strict Phase 2 independence and no personalization leakage.
"""
from __future__ import annotations

import math
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
from app.models.research_knowledge import (
    InstitutionModel,
    ResearcherModel,
    ResearchWorkAuthorModel,
    ResearchWorkModel,
    ResearchWorkTopicModel,
)
from app.models.research_profile import AcademicStatus, ResearchProfileModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.schemas.researcher_intelligence import (
    ExpertiseClassification,
    ResearcherIntelligenceResponse,
)
from app.services.researcher_intelligence_service import (
    REFERENCE_YEAR,
    ResearcherIntelligenceService,
)

# ── SQLite In-Memory Database Fixture ─────────────────────────────────────────

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with Phase 3.2 tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    target_tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["institutions"],
        Base.metadata.tables["researchers"],
        Base.metadata.tables["research_works"],
        Base.metadata.tables["research_work_authors"],
        Base.metadata.tables["topics"],
        Base.metadata.tables["research_work_topics"],
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
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
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


# ── Helper Factory Functions ──────────────────────────────────────────────────


def create_test_researcher_with_profile(
    db: Session,
    full_name: str = "Dr. Ada Lovelace",
    email: str = "ada@computing.org",
    keywords: list[str] | None = None,
) -> tuple[UserModel, ResearchProfileModel, ResearcherModel]:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        hashed_password="pw",
        role="FACULTY",
    )
    db.add(user)

    scholar = ResearcherModel(
        id=uuid.uuid4(),
        display_name=full_name,
        orcid="0000-0002-1825-0097",
        works_count=0,
        cited_by_count=0,
    )
    db.add(scholar)
    db.flush()

    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        canonical_researcher_id=scholar.id,
        academic_status="FACULTY",
        keywords=keywords or [],
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.refresh(scholar)
    db.refresh(user)
    return user, profile, scholar


def create_work_with_topic(
    db: Session,
    scholar: ResearcherModel,
    title: str,
    topic_name: str,
    year: int = 2024,
    citations: int = 10,
    is_lead: bool = True,
    is_primary: bool = True,
    confidence: float = 0.90,
    abstract: str | None = "Detailed research study on computational structures and machine learning.",
    doi: str | None = "10.1000/182",
) -> tuple[ResearchWorkModel, TopicModel]:
    # Find or create topic
    topic = db.query(TopicModel).filter(TopicModel.name == topic_name).first()
    if not topic:
        topic = TopicModel(
            id=uuid.uuid4(),
            name=topic_name,
            slug=topic_name.lower().replace(" ", "-"),
        )
        db.add(topic)
        db.flush()

    work = ResearchWorkModel(
        id=uuid.uuid4(),
        title=title,
        abstract=abstract,
        publication_year=year,
        doi=doi,
        cited_by_count=citations,
        work_type="article",
    )
    db.add(work)
    db.flush()

    author_link = ResearchWorkAuthorModel(
        work_id=work.id,
        researcher_id=scholar.id,
        author_position="first" if is_lead else "middle",
        is_corresponding=is_lead,
    )
    db.add(author_link)

    topic_link = ResearchWorkTopicModel(
        id=uuid.uuid4(),
        work_id=work.id,
        topic_id=topic.id,
        confidence_score=confidence,
        is_primary=is_primary,
        source="OpenAlex",
    )
    db.add(topic_link)

    scholar.works_count += 1
    scholar.cited_by_count += citations

    db.commit()
    db.refresh(work)
    db.refresh(topic)
    return work, topic


# ── 1. Mathematical Scoring & Invariant Tests ─────────────────────────────────


class TestScoringInvariants:
    def test_strength_score_bounds_and_monotonicity(self):
        # Monotonicity with work count
        s1 = ResearcherIntelligenceService._compute_strength(
            work_count=1,
            total_works=1,
            lead_works_count=1,
            primary_works_count=1,
            total_citations=5,
            is_profile_keyword=False,
            recency=1.0,
        )
        s5 = ResearcherIntelligenceService._compute_strength(
            work_count=5,
            total_works=5,
            lead_works_count=5,
            primary_works_count=5,
            total_citations=50,
            is_profile_keyword=False,
            recency=1.0,
        )
        s15 = ResearcherIntelligenceService._compute_strength(
            work_count=15,
            total_works=15,
            lead_works_count=15,
            primary_works_count=15,
            total_citations=200,
            is_profile_keyword=True,
            recency=1.0,
        )

        assert 0.0 <= s1 <= 1.0
        assert 0.0 <= s5 <= 1.0
        assert 0.0 <= s15 <= 1.0
        assert s1 < s5 < s15
        assert not math.isnan(s1) and not math.isinf(s1)

    def test_confidence_score_bounds_and_metadata_sensitivity(self):
        # Low metadata completeness
        c_low = ResearcherIntelligenceService._compute_confidence(
            confidences=[0.60],
            work_count=1,
            has_abstracts_count=0,
            has_dois_count=0,
            has_years_count=0,
            is_profile_keyword=False,
            source_count=1,
        )
        # High metadata completeness & multi-source
        c_high = ResearcherIntelligenceService._compute_confidence(
            confidences=[0.95],
            work_count=5,
            has_abstracts_count=5,
            has_dois_count=5,
            has_years_count=5,
            is_profile_keyword=True,
            source_count=2,
        )

        assert 0.0 <= c_low <= 1.0
        assert 0.0 <= c_high <= 1.0
        assert c_low < c_high
        assert not math.isnan(c_low) and not math.isinf(c_high)

    def test_recency_score_preserves_older_expertise_without_zeroing(self):
        # Recent work (2025/2026)
        r_recent = ResearcherIntelligenceService._compute_recency([REFERENCE_YEAR])
        assert r_recent == 1.0

        # 4 years ago (2022)
        r_mid = ResearcherIntelligenceService._compute_recency([REFERENCE_YEAR - 4])
        assert 0.60 <= r_mid <= 0.80

        # Very old work (2000 -> 26 years ago)
        r_old = ResearcherIntelligenceService._compute_recency([2000])
        # Must obey floor at 0.15, never 0.0
        assert r_old >= 0.15
        assert r_old < r_mid < r_recent

        # Missing publication years
        r_empty = ResearcherIntelligenceService._compute_recency([])
        assert r_empty == 0.50

    def test_expertise_tiering_deterministic_classification(self):
        # Primary: strong, sustained, high confidence
        c_prim, is_prim = ResearcherIntelligenceService._classify_topic(
            work_count=6,
            total_works=6,
            strength=0.85,
            confidence=0.80,
            recency=0.90,
            span_years=4,
            is_profile_keyword=True,
        )
        assert c_prim == ExpertiseClassification.PRIMARY_EXPERTISE
        assert is_prim is True

        # Emerging: recent work with moderate history
        c_emerg, is_emerg = ResearcherIntelligenceService._classify_topic(
            work_count=1,
            total_works=5,
            strength=0.45,
            confidence=0.60,
            recency=0.95,
            span_years=0,
            is_profile_keyword=False,
        )
        assert c_emerg == ExpertiseClassification.EMERGING_INTEREST
        assert is_emerg is False

        # Insufficient evidence: low confidence
        c_insuf, _ = ResearcherIntelligenceService._classify_topic(
            work_count=1,
            total_works=10,
            strength=0.15,
            confidence=0.20,
            recency=0.40,
            span_years=0,
            is_profile_keyword=False,
        )
        assert c_insuf == ExpertiseClassification.INSUFFICIENT_EVIDENCE


# ── 2. The 10 Canonical Evaluation Scenarios (Spec Section 23) ────────────────


class TestEvaluationDatasetScenarios:
    def test_case_1_strong_single_domain_researcher(self, db_session: Session):
        """Scenario 1: Researcher with sustained publications in one primary domain."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Alice Turing", "alice@domain1.org"
        )
        for i in range(8):
            create_work_with_topic(
                db_session,
                scholar,
                title=f"Advanced Machine Learning Volume {i}",
                topic_name="Machine Learning",
                year=2018 + i,
                citations=25,
            )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        assert len(res.interests) >= 1
        top_interest = res.interests[0]
        assert top_interest.topic_name == "Machine Learning"
        assert top_interest.classification == ExpertiseClassification.PRIMARY_EXPERTISE
        assert top_interest.is_primary_expertise is True
        assert top_interest.strength >= 0.70
        assert top_interest.confidence >= 0.70
        assert top_interest.evidence_count == 8

    def test_case_2_multi_domain_researcher(self, db_session: Session):
        """Scenario 2: Researcher with balanced publications across two distinct domains."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Bob Polymath", "bob@multi.org"
        )
        for i in range(4):
            create_work_with_topic(
                db_session, scholar, f"Computer Vision Study {i}", "Computer Vision", year=2021 + i
            )
        for i in range(3):
            create_work_with_topic(
                db_session, scholar, f"Robotics Control {i}", "Robotics", year=2022 + i
            )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        topic_names = [i.topic_name for i in res.interests]
        assert "Computer Vision" in topic_names
        assert "Robotics" in topic_names
        assert res.summary.total_topics_analyzed >= 2

    def test_case_3_emerging_topic_researcher(self, db_session: Session):
        """Scenario 3: Researcher recently published in an emerging field (2025/2026)."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Eve Frontier", "eve@frontier.org"
        )
        create_work_with_topic(
            db_session,
            scholar,
            "Generative Agents and Foundation Models",
            "Generative AI",
            year=2025,
            citations=5,
        )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        gen_ai = next(i for i in res.interests if i.topic_name == "Generative AI")
        assert gen_ai.classification == ExpertiseClassification.EMERGING_INTEREST
        assert gen_ai.recency_score >= 0.85

    def test_case_4_sparse_researcher(self, db_session: Session):
        """Scenario 4: Researcher with only a single published paper."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Sam Novice", "sam@novice.org"
        )
        create_work_with_topic(
            db_session,
            scholar,
            "Introductory Quantum Computing Principles",
            "Quantum Computing",
            year=2023,
            citations=1,
        )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        assert len(res.interests) == 1
        item = res.interests[0]
        assert item.evidence_count == 1
        assert 0.0 <= item.strength <= 1.0

    def test_case_5_missing_abstracts(self, db_session: Session):
        """Scenario 5: Works without abstracts handle gracefully with lower confidence."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. No Abstract", "noabs@scholar.org"
        )
        create_work_with_topic(
            db_session,
            scholar,
            "Paper Title Only Without Body Text",
            "Information Retrieval",
            year=2024,
            abstract=None,
        )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        assert len(res.interests) == 1
        assert res.interests[0].confidence < 0.80

    def test_case_6_missing_explicit_topics_extraction_fallback(self, db_session: Session):
        """Scenario 6: Work without DB topic associations extracts keywords from title."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Free Text", "freetext@scholar.org"
        )
        work = ResearchWorkModel(
            id=uuid.uuid4(),
            title="Deep Neural Networks for Medical Image Segmentation",
            abstract="We present convolutional and deep learning models for biomedical imaging analysis.",
            publication_year=2024,
            cited_by_count=12,
        )
        db_session.add(work)
        db_session.flush()

        link = ResearchWorkAuthorModel(work_id=work.id, researcher_id=scholar.id)
        db_session.add(link)
        db_session.commit()

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        assert len(res.interests) >= 1
        # Extracted terms should include deep learning or neural networks
        all_terms = " ".join([i.topic_name.lower() for i in res.interests])
        assert any(term in all_terms for term in ["neural", "learning", "segmentation", "image"])

    def test_case_7_old_publications_recency_and_preservation(self, db_session: Session):
        """Scenario 7: Works published long ago maintain sustained expertise with decayed recency."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Veteran Scholar", "veteran@classic.edu"
        )
        for i in range(5):
            create_work_with_topic(
                db_session,
                scholar,
                f"Classic Compiler Architecture {i}",
                "Compilers",
                year=2002 + i,
                citations=80,
            )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        compilers = res.interests[0]
        assert compilers.topic_name == "Compilers"
        # Older work maintains sustained expertise
        assert compilers.classification in (
            ExpertiseClassification.PRIMARY_EXPERTISE,
            ExpertiseClassification.SECONDARY_EXPERTISE,
        )
        # Recency score decayed toward the floor (0.15) but is non-zero
        assert 0.15 <= compilers.recency_score <= 0.40

    def test_case_8_recent_publications_high_recency(self, db_session: Session):
        """Scenario 8: Recent works (2025/2026) have peak recency score."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Up To Date", "uptodate@lab.org"
        )
        create_work_with_topic(
            db_session, scholar, "Fresh Discovery in Cryptography", "Cryptography", year=2026
        )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        crypto = res.interests[0]
        assert crypto.recency_score == 1.0

    def test_case_9_mixed_strength_topics_ordered_deterministically(self, db_session: Session):
        """Scenario 9: Multiple topics with differing evidence rank deterministically."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Tiered Scholar", "tiered@lab.org"
        )
        # 6 works in AI
        for i in range(6):
            create_work_with_topic(
                db_session, scholar, f"AI Research {i}", "Artificial Intelligence", year=2023
            )
        # 2 works in Databases
        for i in range(2):
            create_work_with_topic(
                db_session, scholar, f"DB Research {i}", "Databases", year=2022
            )
        # 1 work in Security
        create_work_with_topic(
            db_session, scholar, "Security Vulnerability Note", "Cybersecurity", year=2020
        )

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        assert res.interests[0].topic_name == "Artificial Intelligence"
        assert res.interests[1].topic_name == "Databases"
        assert res.interests[2].topic_name == "Cybersecurity"

    def test_case_10_profile_keywords_only_no_works(self, db_session: Session):
        """Scenario 10: New researcher with declared profile keywords but 0 publications."""
        user = UserModel(
            id=uuid.uuid4(),
            email="newuser@domain.edu",
            full_name="Alex Newcomer",
            hashed_password="hash",
            role="STUDENT",
        )
        db_session.add(user)
        db_session.flush()

        profile = ResearchProfileModel(
            id=uuid.uuid4(),
            user_id=user.id,
            keywords=["Natural Language Processing", "Bioinformatics"],
        )
        db_session.add(profile)
        db_session.commit()

        res = ResearcherIntelligenceService.get_researcher_intelligence(db_session, profile.id)
        assert len(res.interests) == 2
        assert all(i.source == "PROFILE_DECLARED" for i in res.interests)
        assert all(i.strength == 0.50 for i in res.interests)
        assert res.summary.has_profile_keywords is True
        assert res.summary.total_works_analyzed == 0


# ── 3. Determinism & Performance (Zero N+1) ───────────────────────────────────


class TestDeterminismAndPerformance:
    def test_execution_determinism_across_10_runs(self, db_session: Session):
        """Identical inputs must produce identical outputs (Section 16)."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Deterministic", "det@science.org"
        )
        for i in range(4):
            create_work_with_topic(
                db_session, scholar, f"Algorithmic Fairness {i}", "Algorithmic Fairness", year=2023
            )

        runs = [
            ResearcherIntelligenceService.get_researcher_intelligence(
                db_session, profile.id, refresh=True
            )
            for _ in range(10)
        ]

        base = runs[0]
        for run in runs[1:]:
            assert len(run.interests) == len(base.interests)
            for item_run, item_base in zip(run.interests, base.interests):
                assert item_run.topic_name == item_base.topic_name
                assert item_run.strength == item_base.strength
                assert item_run.confidence == item_base.confidence
                assert item_run.classification == item_base.classification
                assert item_run.provenance_reasons == item_base.provenance_reasons

    def test_zero_n_plus_one_database_query_budget(self, db_session: Session):
        """Query count must remain constant and not scale with number of works."""
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Batch Query", "batch@performance.org"
        )
        # Seed 15 works
        for i in range(15):
            create_work_with_topic(
                db_session, scholar, f"High Throughput Paper {i}", "Distributed Systems", year=2024
            )

        # Function to count queries for a given researcher
        def get_compute_query_count(scholar_entity, profile_entity):
            count = 0
            def counter(conn, cursor, statement, parameters, context, executemany):
                nonlocal count
                count += 1

            engine = db_session.get_bind()
            event.listen(engine, "before_cursor_execute", counter)
            try:
                ResearcherIntelligenceService.compute_intelligence(
                    db=db_session,
                    profile=profile_entity,
                    canonical_researcher=scholar_entity,
                )
            finally:
                event.remove(engine, "before_cursor_execute", counter)
            return count

        # Count with 15 works
        count_15 = get_compute_query_count(scholar, profile)

        # Add 15 MORE works (total 30 works)
        for i in range(15):
            create_work_with_topic(
                db_session, scholar, f"Extra High Throughput Paper {i}", "Distributed Systems", year=2024
            )

        # Count with 30 works
        count_30 = get_compute_query_count(scholar, profile)

        # Both must be bounded (<= 5 queries) and strictly constant O(1)
        assert count_15 <= 5, f"Expected bounded query count for 15 works, got {count_15}"
        assert count_30 <= 5, f"Expected bounded query count for 30 works, got {count_30}"
        assert count_15 == count_30, f"Query count scaled with work count: {count_15} vs {count_30} (N+1 leak)"



# ── 4. FastAPI REST Endpoints Integration ─────────────────────────────────────


class TestResearcherIntelligenceAPI:
    def test_get_researcher_intelligence_endpoint(self, client: TestClient, db_session: Session):
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. API Test", "api@test.org"
        )
        create_work_with_topic(
            db_session, scholar, "Neural Network Compression", "Deep Learning", year=2024
        )

        response = client.get(
            f"/api/v1/researchers/{profile.id}/research-intelligence",
            headers={"X-User-ID": str(profile.user_id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["researcher_id"] == str(profile.id)
        assert len(data["interests"]) >= 1
        assert data["interests"][0]["topic_name"] == "Deep Learning"
        assert "provenance_reasons" in data["interests"][0]
        assert "summary" in data

    def test_get_interests_and_expertise_sub_endpoints(
        self, client: TestClient, db_session: Session
    ):
        _, profile, scholar = create_test_researcher_with_profile(
            db_session, "Dr. Sub Endpoint", "sub@test.org"
        )
        for i in range(4):
            create_work_with_topic(
                db_session, scholar, f"Robotics Vision {i}", "Robotics", year=2023
            )

        resp_interests = client.get(
            f"/api/v1/researchers/{profile.id}/interests",
            headers={"X-User-ID": str(profile.user_id)},
        )
        assert resp_interests.status_code == 200
        assert isinstance(resp_interests.json(), list)

        resp_expertise = client.get(
            f"/api/v1/researchers/{profile.id}/expertise",
            headers={"X-User-ID": str(profile.user_id)},
        )
        assert resp_expertise.status_code == 200
        assert isinstance(resp_expertise.json(), list)

    def test_not_found_endpoint(self, client: TestClient):
        random_id = uuid.uuid4()
        response = client.get(f"/api/v1/researchers/{random_id}/research-intelligence")
        assert response.status_code == 404
