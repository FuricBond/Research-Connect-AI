"""
Phase 5.13 — Find a Supervisor.

A STUDENT gets FACULTY members ranked by research fit, each with a deterministic explanation.
The person suggested is the same person peer discovery suggests, so consent and disclosure are
tested as strictly as there:

  Consent       Only discoverable, available, active FACULTY accounts appear. Students never
                appear, even discoverable ones.
  Disclosure    Institution and contact email follow the faculty member's own choices.
  Determinism   Identical inputs produce an identical score, ordering and explanation.
  Honesty       Without embeddings the match is scored on topics and says so; an empty result
                says which problem caused it.
  Read-only     A search writes nothing and its query count does not grow with candidates.

No test loads the embedding model: every test runs with a fake embedding service.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid

import numpy as np
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.research_knowledge import (
    ResearcherModel,
    ResearchWorkAuthorModel,
    ResearchWorkModel,
    ResearchWorkTopicModel,
)
from app.models.research_posting import ResearchPostingModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_discovery import (
    CollaborationInterest,
    CollaborationStatus,
    ResearcherDiscoverySettingsModel,
)
from app.models.researcher_interest import ResearcherInterestModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.personalization.peer_matching_engine import PeerMatchTier, TopicProfile
from app.personalization.supervisor_matching_config import (
    DEFAULT_SUPERVISOR_MATCHING_CONFIG,
    SupervisorMatchingConfig,
)
from app.personalization.supervisor_matching_engine import (
    FacultyPaper,
    OpenPosting,
    SupervisionAvailability,
    SupervisorCandidate,
    SupervisorMatchingEngine,
    SupervisorSignalType,
)
from app.schemas.researcher_discovery import DiscoverySettingsUpdate
from app.services import supervisor_discovery_service as supervisor_module
from app.services.peer_discovery_service import PeerDiscoveryService
from app.services.supervisor_discovery_service import SupervisorDiscoveryService

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

DIM = 384
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def _vec(*components: float) -> list[float]:
    """A unit vector of the stored embedding size, from its leading components."""
    values = list(components) + [0.0] * (DIM - len(components))
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


class FakeEmbeddingService:
    """Stands in for the sentence-transformer model; records what it was asked to encode."""

    def __init__(self, vector: list[float] | None = None, error: Exception | None = None):
        self.vector = vector if vector is not None else _vec(1.0)
        self.error = error
        self.texts: list[str] = []

    def encode_one(self, text: str) -> list[float]:
        self.texts.append(text)
        if self.error is not None:
            raise self.error
        return list(self.vector)


@pytest.fixture(autouse=True)
def shared_embedding_service(monkeypatch) -> FakeEmbeddingService:
    """The process-wide service is replaced, so no test (API ones included) loads the model."""
    fake = FakeEmbeddingService()
    monkeypatch.setattr(supervisor_module, "get_embedding_service", lambda: fake)
    return fake


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Fixture helpers ─────────────────────────────────────────────────────────


def _make_researcher(
    db: Session,
    name: str,
    *,
    role: str = "FACULTY",
    institution: str = "Test University",
    keywords: list[str] | None = None,
    is_active: bool = True,
) -> tuple[UserModel, ResearchProfileModel]:
    slug = name.lower().replace(" ", ".").replace("dr.", "").strip(".")
    user = UserModel(
        id=uuid.uuid4(),
        email=f"{slug}.{uuid.uuid4().hex[:6]}@university.edu",
        hashed_password="hashed",
        full_name=name,
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY" if role == "FACULTY" else "POSTGRADUATE",
        institution=institution,
        department="Computer Science",
        keywords=keywords or [],
    )
    db.add(profile)
    db.commit()
    return user, profile


def _topic(db: Session, slug: str) -> TopicModel:
    topic = db.execute(select(TopicModel).where(TopicModel.slug == slug)).scalar_one_or_none()
    if topic is None:
        topic = TopicModel(id=uuid.uuid4(), name=slug.replace("-", " ").title(), slug=slug)
        db.add(topic)
        db.flush()
    return topic


def _add_topics(
    db: Session,
    profile: ResearchProfileModel,
    topics: dict[str, float],
    classification: str = "PRIMARY_EXPERTISE",
) -> None:
    """Records expertise topics for a profile, creating the canonical topics as needed."""
    for slug, strength in topics.items():
        topic = _topic(db, slug)
        db.add(
            ResearcherInterestModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                topic_id=topic.id,
                topic_name=topic.name,
                topic_slug=slug,
                strength=strength,
                confidence=0.9,
                evidence_count=5,
                classification=classification,
                is_primary_expertise=classification == "PRIMARY_EXPERTISE",
                source="TEST",
            )
        )
    db.commit()


def _opt_in(
    db: Session,
    profile: ResearchProfileModel,
    *,
    status: CollaborationStatus = CollaborationStatus.OPEN_TO_ENQUIRIES,
    interests: list[CollaborationInterest] | None = None,
    show_institution: bool = True,
    show_contact_email: bool = False,
) -> ResearcherDiscoverySettingsModel:
    PeerDiscoveryService.update_settings(
        db,
        profile.id,
        DiscoverySettingsUpdate(
            is_discoverable=True,
            collaboration_status=status,
            collaboration_interests=interests or [CollaborationInterest.CO_AUTHORSHIP],
            show_institution=show_institution,
            show_contact_email=show_contact_email,
        ),
    )
    settings = PeerDiscoveryService.load_settings(db, profile.id)
    assert settings is not None
    return settings


def _add_work(
    db: Session,
    profile: ResearchProfileModel,
    title: str,
    *,
    year: int,
    embedding: list[float] | None = None,
    topics: tuple[str, ...] = (),
    doi: str | None = None,
) -> ResearchWorkModel:
    """A publication authored by the profile's canonical researcher, created on first use."""
    if profile.canonical_researcher_id is None:
        researcher = ResearcherModel(id=uuid.uuid4(), display_name=title.split()[0])
        db.add(researcher)
        db.flush()
        profile.canonical_researcher_id = researcher.id
    work = ResearchWorkModel(
        id=uuid.uuid4(),
        openalex_id=f"W{uuid.uuid4().int % 10**10}",
        title=title,
        publication_year=year,
        doi=doi,
        landing_page_url=f"https://example.org/{title.lower().replace(' ', '-')}",
        embedding=embedding,
    )
    db.add(work)
    db.flush()
    db.add(ResearchWorkAuthorModel(work_id=work.id, researcher_id=profile.canonical_researcher_id))
    for slug in topics:
        db.add(ResearchWorkTopicModel(id=uuid.uuid4(), work_id=work.id, topic_id=_topic(db, slug).id))
    db.commit()
    return work


def _add_posting(
    db: Session,
    user: UserModel,
    profile: ResearchProfileModel,
    title: str,
    *,
    posting_type: str = "THESIS_TOPIC",
    status: str = "OPEN",
) -> ResearchPostingModel:
    posting = ResearchPostingModel(
        id=uuid.uuid4(),
        author_profile_id=profile.id,
        author_user_id=user.id,
        title=title,
        posting_type=posting_type,
        status=status,
        description="A supervised project.",
    )
    db.add(posting)
    db.commit()
    return posting


def _add_topic_preference(
    db: Session,
    profile: ResearchProfileModel,
    slug: str,
    *,
    preference_type: str = "PREFERRED",
    label: str | None = None,
) -> None:
    db.add(
        ResearcherPreferenceModel(
            id=uuid.uuid4(),
            profile_id=profile.id,
            category="TOPIC",
            preference_type=preference_type,
            preference_key="topic",
            preference_value=slug,
            display_label=label or slug.replace("-", " ").title(),
            strength=1.0,
            confidence=0.95,
            source="EXPLICIT",
            is_active=True,
        )
    )
    db.commit()


def _student(db: Session, name: str = "Sam Student", **kwargs) -> tuple[UserModel, ResearchProfileModel]:
    user, profile = _make_researcher(db, name, role="STUDENT", **kwargs)
    _add_topics(db, profile, {"retrieval": 0.9, "ranking": 0.8})
    return user, profile


def _faculty(
    db: Session, name: str, *, topics: dict[str, float] | None = None, **kwargs
) -> tuple[UserModel, ResearchProfileModel]:
    user, profile = _make_researcher(db, name, **kwargs)
    _add_topics(db, profile, topics or {"retrieval": 0.9, "hci": 0.8})
    return user, profile


def _find(db: Session, profile_id: uuid.UUID, **kwargs):
    kwargs.setdefault("embedding_service", FakeEmbeddingService())
    return SupervisorDiscoveryService.find_supervisors(db, profile_id, reference_time=NOW, **kwargs)


def _profile(profile_id: uuid.UUID | None = None, **kwargs) -> TopicProfile:
    return TopicProfile(profile_id=profile_id or uuid.uuid4(), **kwargs)


def _signal(assessment, signal_type: SupervisorSignalType):
    return next(s for s in assessment.signals if s.signal_type == signal_type)


STUDENT_TOPICS = {"retrieval": 0.9, "ranking": 0.8}


# ===========================================================================
# Configuration invariants
# ===========================================================================


def test_signal_weights_sum_to_one():
    config = DEFAULT_SUPERVISOR_MATCHING_CONFIG
    total = (
        config.topic_fit_weight
        + config.semantic_fit_weight
        + config.recent_paper_evidence_weight
        + config.taxonomy_proximity_weight
        + config.supervision_availability_weight
    )
    assert abs(total - 1.0) < 1e-9
    assert config.algorithm_version == "5.13.1"


def test_misconfigured_weights_are_rejected_at_construction():
    with pytest.raises(ValueError, match="must sum to 1.0"):
        SupervisorMatchingConfig(topic_fit_weight=0.9)


# ===========================================================================
# Engine: scoring law
# ===========================================================================


def test_engine_is_deterministic():
    student = _profile(expertise=dict(STUDENT_TOPICS), ancestors={"retrieval": frozenset({"cs"})})
    faculty = _profile(
        expertise={"retrieval": 0.9, "hci": 0.8},
        ancestors={"retrieval": frozenset({"cs"}), "hci": frozenset({"cs"})},
    )
    papers = (
        FacultyPaper(uuid.uuid4(), "Dense retrieval", 2025, np.array(_vec(1.0, 0.2)), frozenset({"retrieval"})),
        FacultyPaper(uuid.uuid4(), "User studies", 2023, np.array(_vec(0.1, 1.0)), frozenset({"hci"})),
    )
    kwargs = dict(
        student_vector=np.array(_vec(1.0)),
        faculty_vector=np.array(_vec(1.0, 0.5)),
        recent_papers=papers,
        availability=SupervisionAvailability("OPEN_TO_ENQUIRIES", ("MENTORSHIP",)),
    )

    first = SupervisorMatchingEngine.score_pair(student, faculty, **kwargs)
    second = SupervisorMatchingEngine.score_pair(student, faculty, **kwargs)

    assert first == second
    assert first.explanation_reasons == second.explanation_reasons


def test_score_is_bounded():
    """A perfect match cannot exceed 1.0, and a heavily penalised one cannot fall below 0.0."""
    topics = {f"topic-{i}": 1.0 for i in range(6)}
    vector = np.array(_vec(1.0))
    perfect = SupervisorMatchingEngine.score_pair(
        _profile(expertise=dict(topics)),
        _profile(expertise=dict(topics)),
        student_vector=vector,
        faculty_vector=vector,
        recent_papers=(FacultyPaper(uuid.uuid4(), "Same", 2026, vector, frozenset(topics)),),
        availability=SupervisionAvailability(
            open_postings=(OpenPosting(uuid.uuid4(), "Thesis", "THESIS_TOPIC"),)
        ),
    )
    assert 0.0 <= perfect.match_score <= 1.0

    excluded = {f"avoid-{i}": 0.9 for i in range(30)}
    penalised = SupervisorMatchingEngine.score_pair(
        _profile(expertise=dict(STUDENT_TOPICS)),
        _profile(expertise={"retrieval": 0.9, **excluded}),
        excluded_topics=frozenset(excluded),
    )
    assert penalised.match_score == 0.0


def test_semantic_fit_is_zero_with_a_reason_when_there_are_no_vectors():
    student = _profile(expertise=dict(STUDENT_TOPICS))
    faculty = _profile(expertise={"retrieval": 0.9, "hci": 0.8})

    result = SupervisorMatchingEngine.score_pair(student, faculty)

    semantic = _signal(result, SupervisorSignalType.SEMANTIC_FIT)
    assert semantic.raw_score == 0.0
    assert semantic.weighted_contribution == 0.0
    assert "scored on research topics only" in semantic.explanation
    assert result.explanation_reasons[-1] == semantic.explanation, "a topic-only match says so"
    assert result.match_score > 0.0, "topic fit alone still produces a match"


def test_missing_faculty_vector_is_explained_separately():
    result = SupervisorMatchingEngine.score_pair(
        _profile(expertise=dict(STUDENT_TOPICS)),
        _profile(expertise={"retrieval": 0.9, "hci": 0.8}),
        student_vector=_vec(1.0),
    )
    semantic = _signal(result, SupervisorSignalType.SEMANTIC_FIT)
    assert semantic.explanation.startswith("None of their publications has an embedding yet")


def test_mean_vectors_are_renormalised_before_the_cosine():
    """A mean of unit vectors is shorter than unit length; its direction is what counts."""
    student = _profile(expertise=dict(STUDENT_TOPICS))
    faculty = _profile(expertise={"retrieval": 0.9, "hci": 0.8})

    result = SupervisorMatchingEngine.score_pair(
        student,
        faculty,
        student_vector=np.array([2.0] + [0.0] * (DIM - 1)),
        faculty_vector=np.array([0.25] + [0.0] * (DIM - 1)),
    )

    semantic = _signal(result, SupervisorSignalType.SEMANTIC_FIT)
    assert semantic.raw_score == 1.0
    assert semantic.evidence == ("similarity 1.00",)


def test_matching_papers_are_ordered_by_similarity_then_year_then_id():
    student = _profile(expertise=dict(STUDENT_TOPICS))
    faculty = _profile(expertise={"retrieval": 0.9, "hci": 0.8})
    close = _vec(0.8, 0.6)  # cosine 0.8 with the student
    best = FacultyPaper(uuid.UUID(int=9), "Best", 2022, _vec(1.0))
    older = FacultyPaper(uuid.UUID(int=1), "Older", 2024, close)
    newer_b = FacultyPaper(uuid.UUID(int=3), "Newer B", 2025, close)
    newer_a = FacultyPaper(uuid.UUID(int=2), "Newer A", 2025, close)
    unrelated = FacultyPaper(uuid.UUID(int=4), "Unrelated", 2026, _vec(0.2, 1.0))

    config = SupervisorMatchingConfig(max_matching_papers=5)
    result = SupervisorMatchingEngine.score_pair(
        student,
        faculty,
        student_vector=_vec(1.0),
        faculty_vector=_vec(1.0),
        recent_papers=(older, unrelated, newer_b, best, newer_a),
        config=config,
    )

    assert [p.title for p in result.matching_papers] == ["Best", "Newer A", "Newer B", "Older"]
    assert result.matching_papers[1].similarity == pytest.approx(0.8)
    evidence = _signal(result, SupervisorSignalType.RECENT_PAPER_EVIDENCE)
    assert evidence.raw_score == pytest.approx((1.0 + 0.8 * 3) / 4)

    capped = SupervisorMatchingEngine.score_pair(
        student,
        faculty,
        student_vector=_vec(1.0),
        faculty_vector=_vec(1.0),
        recent_papers=(older, unrelated, newer_b, best, newer_a),
    )
    assert [p.title for p in capped.matching_papers] == ["Best", "Newer A", "Newer B"]


def test_recent_papers_fall_back_to_topic_overlap_without_vectors():
    student = _profile(expertise=dict(STUDENT_TOPICS))
    faculty = _profile(expertise={"retrieval": 0.9, "hci": 0.8})
    papers = (
        FacultyPaper(uuid.uuid4(), "On topic", 2025, None, frozenset({"retrieval", "ranking"})),
        FacultyPaper(uuid.uuid4(), "Half on topic", 2024, None, frozenset({"retrieval", "hci"})),
        FacultyPaper(uuid.uuid4(), "Off topic", 2025, None, frozenset({"hci", "vision", "audio"})),
    )

    result = SupervisorMatchingEngine.score_pair(student, faculty, recent_papers=papers)

    assert [p.title for p in result.matching_papers] == ["On topic", "Half on topic"]
    assert result.matching_papers[0].shared_topics == ("ranking", "retrieval")
    evidence = _signal(result, SupervisorSignalType.RECENT_PAPER_EVIDENCE)
    assert evidence.raw_score == pytest.approx(0.75)
    assert "share your topics" in evidence.explanation


def test_ties_are_broken_by_profile_id():
    student = _profile(expertise=dict(STUDENT_TOPICS))
    candidates = [
        SupervisorCandidate(_profile(uuid.UUID(int=2), expertise={"retrieval": 0.9, "hci": 0.8})),
        SupervisorCandidate(_profile(uuid.UUID(int=1), expertise={"retrieval": 0.9, "hci": 0.8})),
        SupervisorCandidate(_profile(student.profile_id, expertise=dict(STUDENT_TOPICS))),
    ]

    ranked = SupervisorMatchingEngine.rank_candidates(student, candidates)
    reversed_ranked = SupervisorMatchingEngine.rank_candidates(student, list(reversed(candidates)))

    assert [a.faculty_profile_id for a in ranked] == [uuid.UUID(int=1), uuid.UUID(int=2)]
    assert ranked == reversed_ranked
    assert student.profile_id not in {a.faculty_profile_id for a in ranked}


def test_excluded_topics_cost_a_fixed_penalty_each():
    student = _profile(expertise=dict(STUDENT_TOPICS))
    faculty = _profile(expertise={"retrieval": 0.9, "ranking": 0.8, "robotics": 0.7, "vision": 0.6})

    plain = SupervisorMatchingEngine.score_pair(student, faculty)
    one = SupervisorMatchingEngine.score_pair(student, faculty, excluded_topics={"robotics"})
    two = SupervisorMatchingEngine.score_pair(student, faculty, excluded_topics={"robotics", "vision"})

    assert plain.match_score - one.match_score == pytest.approx(0.05)
    assert plain.match_score - two.match_score == pytest.approx(0.10)
    penalty = _signal(two, SupervisorSignalType.EXCLUDED_TOPIC_PENALTY)
    assert penalty.weighted_contribution == pytest.approx(-0.10)
    assert penalty.evidence == ("robotics", "vision")
    assert "which you excluded" in penalty.explanation
    assert not any(
        s.signal_type == SupervisorSignalType.EXCLUDED_TOPIC_PENALTY for s in plain.signals
    )


def test_supervision_availability():
    student = _profile(expertise=dict(STUDENT_TOPICS))
    faculty = _profile(expertise={"retrieval": 0.9, "hci": 0.8})

    def availability_score(availability: SupervisionAvailability) -> float:
        result = SupervisorMatchingEngine.score_pair(student, faculty, availability=availability)
        return _signal(result, SupervisorSignalType.SUPERVISION_AVAILABILITY).raw_score

    thesis = OpenPosting(uuid.uuid4(), "Thesis on ranking", "THESIS_TOPIC")
    postdoc = OpenPosting(uuid.uuid4(), "Postdoc", "POSTDOC")
    assert availability_score(SupervisionAvailability("SELECTIVELY_AVAILABLE", (), (thesis,))) == 1.0
    assert availability_score(SupervisionAvailability("SELECTIVELY_AVAILABLE", (), (postdoc,))) == 0.4
    assert availability_score(SupervisionAvailability("OPEN_TO_ENQUIRIES")) == 0.75
    assert availability_score(SupervisionAvailability("OPEN_TO_ENQUIRIES", ("MENTORSHIP",))) == 0.95
    assert availability_score(
        SupervisionAvailability("SEEKING_COLLABORATORS", ("STUDENT_CO_SUPERVISION",))
    ) == 1.0


def test_thin_faculty_profile_needs_an_embedding_to_be_compared():
    student = _profile(expertise=dict(STUDENT_TOPICS))
    thin = _profile(expertise={"retrieval": 0.9})

    without = SupervisorMatchingEngine.score_pair(student, thin)
    assert without.tier == PeerMatchTier.INSUFFICIENT_EVIDENCE
    assert without.match_score == 0.0

    with_vectors = SupervisorMatchingEngine.score_pair(
        student, thin, student_vector=_vec(1.0), faculty_vector=_vec(1.0)
    )
    assert with_vectors.tier != PeerMatchTier.INSUFFICIENT_EVIDENCE
    assert with_vectors.match_score > 0.0


# ===========================================================================
# Service: consent
# ===========================================================================


def test_only_faculty_appear(db_session: Session):
    """A discoverable student is a peer, never a suggested supervisor."""
    _, student = _student(db_session)
    _, other_student = _make_researcher(db_session, "Olive Student", role="STUDENT")
    _add_topics(db_session, other_student, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, other_student)
    _, faculty = _faculty(db_session, "Dr. Faculty", institution="Other University")
    _opt_in(db_session, faculty)

    result = _find(db_session, student.id)

    assert [m.supervisor.profile_id for m in result.matches] == [faculty.id]
    assert result.total_candidates_evaluated == 1


def test_faculty_without_consent_or_availability_are_excluded(db_session: Session):
    _, student = _student(db_session)
    _, no_row = _faculty(db_session, "Dr. NoRow")
    _, hidden = _faculty(db_session, "Dr. Hidden")
    _opt_in(db_session, hidden)
    PeerDiscoveryService.update_settings(
        db_session, hidden.id, DiscoverySettingsUpdate(is_discoverable=False)
    )
    _, busy = _faculty(db_session, "Dr. Busy")
    _opt_in(db_session, busy, status=CollaborationStatus.NOT_AVAILABLE)
    _, inactive = _faculty(db_session, "Dr. Inactive", is_active=False)
    _opt_in(db_session, inactive)
    _, eligible = _faculty(db_session, "Dr. Eligible")
    _opt_in(db_session, eligible)

    result = _find(db_session, student.id)

    assert [m.supervisor.profile_id for m in result.matches] == [eligible.id]
    assert result.total_candidates_evaluated == 1


# ===========================================================================
# Service: disclosure
# ===========================================================================


def test_disclosure_choices_are_honoured(db_session: Session):
    _, student = _student(db_session)
    _, reticent = _faculty(db_session, "Dr. Reticent", institution="Secret Institute")
    _opt_in(db_session, reticent, show_institution=False)
    open_user, open_faculty = _faculty(db_session, "Dr. Open", institution="Open University")
    _opt_in(db_session, open_faculty, show_contact_email=True)

    matches = {m.supervisor.full_name: m.supervisor for m in _find(db_session, student.id).matches}

    assert matches["Dr. Reticent"].institution is None
    assert matches["Dr. Reticent"].department is None
    assert matches["Dr. Reticent"].contact_email is None, "email is withheld by default"
    assert matches["Dr. Open"].institution == "Open University"
    assert matches["Dr. Open"].contact_email == open_user.email


# ===========================================================================
# Service: behaviour
# ===========================================================================


def test_thin_student_profile_gets_actionable_guidance(db_session: Session):
    _, student = _make_researcher(db_session, "New Student", role="STUDENT")
    _, faculty = _faculty(db_session, "Dr. Faculty")
    _opt_in(db_session, faculty)

    result = _find(db_session, student.id)

    assert result.data_sufficiency == "INSUFFICIENT_PROFILE"
    assert result.matches == []
    assert "Add keywords" in (result.guidance or "")


def test_no_discoverable_faculty_points_to_the_peer_opt_in(db_session: Session):
    _, student = _student(db_session)
    _faculty(db_session, "Dr. Private")

    result = _find(db_session, student.id)

    assert result.data_sufficiency == "NO_CANDIDATES"
    assert result.matches == []
    assert "Find Peers" in (result.guidance or "")


def test_preferred_topics_make_a_student_matchable_and_shape_the_interest_text(db_session: Session):
    """A student with no publications states what they want to work on through preferences."""
    _, student = _make_researcher(db_session, "Pref Student", role="STUDENT", keywords=["Evaluation"])
    _add_topic_preference(db_session, student, "retrieval", label="Information Retrieval")
    _add_topic_preference(db_session, student, "ranking", label="Learning to Rank")
    _, faculty = _faculty(db_session, "Dr. Faculty")
    _opt_in(db_session, faculty)
    service = FakeEmbeddingService()

    result = _find(db_session, student.id, embedding_service=service)

    assert result.data_sufficiency == "SUFFICIENT"
    assert [m.supervisor.profile_id for m in result.matches] == [faculty.id]
    assert "retrieval" in result.matches[0].shared_topics
    assert service.texts == ["evaluation. Information Retrieval, Learning to Rank"]
    assert result.semantic_available is True


def test_excluded_topic_preference_lowers_a_match(db_session: Session):
    _, student = _student(db_session)
    _, faculty = _faculty(db_session, "Dr. Robotics", topics={"retrieval": 0.9, "robotics": 0.8})
    _opt_in(db_session, faculty)
    before = _find(db_session, student.id).matches[0]

    _add_topic_preference(db_session, student, "robotics", preference_type="EXCLUDED")
    after = _find(db_session, student.id).matches[0]

    assert before.match_score - after.match_score == pytest.approx(0.05)
    assert any(s.signal_type == SupervisorSignalType.EXCLUDED_TOPIC_PENALTY for s in after.signals)


def test_an_open_posting_raises_availability_and_a_draft_does_not(db_session: Session):
    _, student = _student(db_session)
    open_user, with_open = _faculty(db_session, "Dr. Open Posting")
    _opt_in(db_session, with_open, status=CollaborationStatus.SELECTIVELY_AVAILABLE)
    open_posting = _add_posting(db_session, open_user, with_open, "Thesis: neural ranking")
    draft_user, with_draft = _faculty(db_session, "Dr. Draft Posting")
    _opt_in(db_session, with_draft, status=CollaborationStatus.SELECTIVELY_AVAILABLE)
    _add_posting(db_session, draft_user, with_draft, "Unpublished thesis", status="DRAFT")

    matches = {m.supervisor.profile_id: m for m in _find(db_session, student.id).matches}

    def availability(match):
        return next(
            s for s in match.signals if s.signal_type == SupervisorSignalType.SUPERVISION_AVAILABILITY
        )

    assert availability(matches[with_open.id]).raw_score == 1.0
    assert [p.posting_id for p in matches[with_open.id].open_postings] == [open_posting.id]
    assert availability(matches[with_draft.id]).raw_score == pytest.approx(0.4)
    assert matches[with_draft.id].open_postings == []
    assert matches[with_open.id].match_score > matches[with_draft.id].match_score

    only_open = _find(db_session, student.id, open_postings_only=True)
    assert [m.supervisor.profile_id for m in only_open.matches] == [with_open.id]


def test_open_postings_filter_explains_an_empty_result(db_session: Session):
    _, student = _student(db_session)
    _, faculty = _faculty(db_session, "Dr. Faculty")
    _opt_in(db_session, faculty)

    result = _find(db_session, student.id, open_postings_only=True)

    assert result.matches == []
    assert result.data_sufficiency == "SUFFICIENT"
    assert "open postings filter" in (result.guidance or "")


def test_recent_matching_papers_are_listed(db_session: Session):
    _, student = _student(db_session)
    _, faculty = _faculty(db_session, "Dr. Author")
    _opt_in(db_session, faculty)
    recent = _add_work(
        db_session, faculty, "Neural ranking models", year=2024, embedding=_vec(1.0),
        topics=("ranking",), doi="10.1000/ranking",
    )
    _add_work(db_session, faculty, "Early ranking work", year=2015, embedding=_vec(1.0))
    _add_work(db_session, faculty, "Robot grasping", year=2025, embedding=_vec(0.0, 1.0))

    match = _find(db_session, student.id, embedding_service=FakeEmbeddingService(_vec(1.0))).matches[0]

    assert [p.work_id for p in match.matching_papers] == [recent.id], "old and unrelated papers are not evidence"
    paper = match.matching_papers[0]
    assert paper.publication_year == 2024
    assert paper.doi == "10.1000/ranking"
    assert paper.similarity == pytest.approx(1.0)
    assert paper.shared_topics == ["ranking"]


def test_the_students_own_works_are_preferred_over_encoding_text(db_session: Session):
    _, student = _student(db_session)
    _add_work(db_session, student, "My first paper", year=2025, embedding=_vec(1.0))
    _, faculty = _faculty(db_session, "Dr. Faculty")
    _opt_in(db_session, faculty)
    _add_work(db_session, faculty, "Their paper", year=2025, embedding=_vec(1.0))
    service = FakeEmbeddingService()

    result = _find(db_session, student.id, embedding_service=service)

    assert service.texts == [], "no encoding is needed when the student has embedded works"
    assert result.semantic_available is True
    semantic = next(
        s for s in result.matches[0].signals if s.signal_type == SupervisorSignalType.SEMANTIC_FIT
    )
    assert semantic.raw_score == pytest.approx(1.0)


def test_works_without_embeddings_score_on_topics_and_say_so(db_session: Session):
    _, student = _student(db_session)
    _, faculty = _faculty(db_session, "Dr. Topics")
    _opt_in(db_session, faculty)
    _add_work(db_session, faculty, "Ranking for retrieval", year=2025, topics=("retrieval", "ranking"))
    failing = FakeEmbeddingService(error=RuntimeError("model unavailable"))

    result = _find(db_session, student.id, embedding_service=failing)

    assert result.semantic_available is False
    match = result.matches[0]
    semantic = next(s for s in match.signals if s.signal_type == SupervisorSignalType.SEMANTIC_FIT)
    assert semantic.raw_score == 0.0
    assert "scored on research topics only" in match.explanation_reasons[-1]
    assert [p.title for p in match.matching_papers] == ["Ranking for retrieval"]


def test_faculty_topics_come_from_their_works_without_interest_rows(db_session: Session):
    _, student = _student(db_session)
    _, faculty = _make_researcher(db_session, "Dr. Unprofiled")
    _opt_in(db_session, faculty)
    _add_work(db_session, faculty, "Paper one", year=2025, topics=("retrieval", "ranking"))
    _add_work(db_session, faculty, "Paper two", year=2024, topics=("retrieval",))

    result = _find(db_session, student.id)

    assert [m.supervisor.profile_id for m in result.matches] == [faculty.id]
    assert set(result.matches[0].shared_topics) == {"retrieval", "ranking"}


def test_exclude_same_institution_filter(db_session: Session):
    _, student = _student(db_session, institution="Alpha University")
    _, internal = _faculty(db_session, "Dr. Internal", institution="Alpha University")
    _, external = _faculty(db_session, "Dr. External", institution="Beta Institute")
    for faculty in (internal, external):
        _opt_in(db_session, faculty)

    everyone = _find(db_session, student.id)
    external_only = _find(db_session, student.id, exclude_same_institution=True)

    assert {m.supervisor.profile_id for m in everyone.matches} == {internal.id, external.id}
    assert [m.supervisor.profile_id for m in external_only.matches] == [external.id]


def test_unknown_profile_raises(db_session: Session):
    with pytest.raises(ValueError, match="not found"):
        _find(db_session, uuid.uuid4())


def test_a_search_writes_nothing(db_session: Session):
    _, student = _student(db_session)
    _, faculty = _faculty(db_session, "Dr. Faculty")
    _opt_in(db_session, faculty)
    _add_work(db_session, faculty, "Paper", year=2025, embedding=_vec(1.0), topics=("retrieval",))
    student_id = student.id
    statements: list[str] = []

    def _listener(conn, cursor, statement, *args):
        statements.append(statement.lstrip().split()[0].upper())

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _listener)
    try:
        result = _find(db_session, student_id)
    finally:
        event.remove(engine, "before_cursor_execute", _listener)

    assert result.returned_count == 1
    assert set(statements) == {"SELECT"}
    assert not db_session.new and not db_session.dirty and not db_session.deleted


def test_supervisor_search_query_count_is_bounded(db_session: Session):
    """Query count must not grow with the number of candidates."""
    _, student = _student(db_session, keywords=["evaluation"])
    # Read before counting: the committed instance is expired and would reload itself.
    student_id = student.id

    def add_faculty(index: int) -> None:
        user, faculty = _faculty(db_session, f"Dr. Faculty{index}", institution=f"Institute {index}")
        _opt_in(db_session, faculty)
        _add_work(db_session, faculty, f"Paper {index}", year=2025, embedding=_vec(1.0), topics=("retrieval",))
        _add_posting(db_session, user, faculty, f"Thesis {index}")

    def count_queries() -> tuple[int, int]:
        engine = db_session.get_bind()
        count = 0

        def _listener(*args, **kwargs):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", _listener)
        try:
            result = _find(db_session, student_id, limit=50)
        finally:
            event.remove(engine, "before_cursor_execute", _listener)
        return count, result.returned_count

    for index in range(3):
        add_faculty(index)
    few, few_returned = count_queries()
    for index in range(3, 12):
        add_faculty(index)
    many, many_returned = count_queries()

    assert (few_returned, many_returned) == (3, 12)
    assert few == many, f"query count grew with candidates: {few} -> {many}"
    assert many <= 8, f"expected a bounded query count, executed {many}"


# ===========================================================================
# REST API
# ===========================================================================


def test_api_returns_ranked_supervisors_for_the_owning_student(client: TestClient, db_session: Session):
    student_user, student = _student(db_session)
    faculty_user, faculty = _faculty(db_session, "Dr. Supervisor", institution="Beta Institute")
    _opt_in(db_session, faculty)
    _add_work(db_session, faculty, "Learning to rank", year=2025, embedding=_vec(1.0), topics=("ranking",))
    posting = _add_posting(db_session, faculty_user, faculty, "Thesis: ranking evaluation")

    res = client.get(
        f"/api/v1/researchers/{student.id}/supervisor-matches",
        params={"limit": 5},
        headers={"X-User-ID": str(student_user.id)},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["data_sufficiency"] == "SUFFICIENT"
    assert body["algorithm_version"] == "5.13.1"
    assert body["semantic_available"] is True
    assert body["returned_count"] == 1
    match = body["matches"][0]
    assert match["supervisor"]["full_name"] == "Dr. Supervisor"
    assert match["supervisor"]["contact_email"] is None
    assert match["tier"] in ("STRONG", "MODERATE", "EXPLORATORY")
    assert {s["signal_type"] for s in match["signals"]} >= {
        "TOPIC_FIT", "SEMANTIC_FIT", "RECENT_PAPER_EVIDENCE", "TAXONOMY_PROXIMITY",
        "SUPERVISION_AVAILABILITY",
    }
    assert match["matching_papers"][0]["title"] == "Learning to rank"
    assert match["open_postings"][0]["posting_id"] == str(posting.id)
    assert match["explanation_reasons"]


def test_api_is_for_students_only(client: TestClient, db_session: Session):
    faculty_user, faculty = _faculty(db_session, "Dr. Requester")

    res = client.get(
        f"/api/v1/researchers/{faculty.id}/supervisor-matches",
        headers={"X-User-ID": str(faculty_user.id)},
    )

    assert res.status_code == 403
    assert "student" in res.json()["detail"]


def test_api_requires_ownership_and_authentication(client: TestClient, db_session: Session):
    _, student = _student(db_session)
    intruder_user, _ = _make_researcher(db_session, "Ivy Intruder", role="STUDENT")

    forbidden = client.get(
        f"/api/v1/researchers/{student.id}/supervisor-matches",
        headers={"X-User-ID": str(intruder_user.id)},
    )
    anonymous = client.get(f"/api/v1/researchers/{student.id}/supervisor-matches")

    assert forbidden.status_code == 403
    assert anonymous.status_code == 401


def test_api_unknown_profile_is_404(client: TestClient, db_session: Session):
    student_user, _ = _student(db_session)

    res = client.get(
        f"/api/v1/researchers/{uuid.uuid4()}/supervisor-matches",
        headers={"X-User-ID": str(student_user.id)},
    )

    assert res.status_code == 404
