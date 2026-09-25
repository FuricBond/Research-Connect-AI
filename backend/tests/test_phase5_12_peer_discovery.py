"""
Phase 5.12 — Peer & Co-Author Discovery.

Peer discovery is the one matching surface where the thing being matched is a person, so most of
these tests are about consent and disclosure rather than ranking quality:

  Consent       A researcher appears only if they opted in. No settings row means no consent,
                not a default. Someone who has not opted in may still search, because
                discoverability governs being found, not looking.
  Disclosure    Institution and contact email are shown only if that researcher chose to show
                them, enforced in one place so a field cannot leak via another response model.
  Determinism   Identical inputs produce an identical score, ordering and explanation.
  Balance       Shared and complementary expertise are scored separately, so the matcher returns
                neither the researcher's own reflection nor unrelated strangers.
  Honesty       An empty result says which problem caused it: a thin profile, or nobody opted in.
"""
from __future__ import annotations

from datetime import datetime, timezone
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
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_discovery import (
    CollaborationInterest,
    CollaborationStatus,
    ResearcherDiscoverySettingsModel,
)
from app.models.researcher_interest import ResearcherInterestModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from app.personalization.peer_matching_config import (
    DEFAULT_PEER_MATCHING_CONFIG,
    PeerMatchingConfig,
)
from app.personalization.peer_matching_engine import (
    PeerMatchingEngine,
    PeerMatchTier,
    PeerSignalType,
    TopicProfile,
)
from app.schemas.researcher_discovery import DiscoverySettingsUpdate
from app.services.peer_discovery_service import PeerDiscoveryService

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


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
    institution: str = "Test University",
    keywords: list[str] | None = None,
) -> tuple[UserModel, ResearchProfileModel]:
    slug = name.lower().replace(" ", ".").replace("dr.", "").strip(".")
    user = UserModel(
        id=uuid.uuid4(),
        email=f"{slug}.{uuid.uuid4().hex[:6]}@university.edu",
        hashed_password="hashed",
        full_name=name,
        role="FACULTY",
        is_active=True,
    )
    db.add(user)
    db.flush()
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY",
        institution=institution,
        department="Computer Science",
        keywords=keywords or [],
    )
    db.add(profile)
    db.commit()
    return user, profile


def _add_topics(db: Session, profile: ResearchProfileModel, topics: dict[str, float], classification: str = "PRIMARY_EXPERTISE") -> None:
    """Records expertise topics for a profile, creating the canonical topics as needed."""
    for slug, strength in topics.items():
        topic = db.execute(select(TopicModel).where(TopicModel.slug == slug)).scalar_one_or_none()
        if topic is None:
            topic = TopicModel(
                id=uuid.uuid4(), name=slug.replace("-", " ").title(), slug=slug
            )
            db.add(topic)
            db.flush()
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
    status: CollaborationStatus = CollaborationStatus.SEEKING_COLLABORATORS,
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


def _profile(profile_id: uuid.UUID, **kwargs) -> TopicProfile:
    return TopicProfile(profile_id=profile_id, **kwargs)


# ===========================================================================
# Configuration invariants
# ===========================================================================


def test_signal_weights_sum_to_one():
    """A drifting weight sum would silently rescale every score."""
    config = DEFAULT_PEER_MATCHING_CONFIG
    total = (
        config.shared_expertise_weight
        + config.complementary_expertise_weight
        + config.taxonomy_proximity_weight
        + config.methodology_overlap_weight
        + config.collaboration_readiness_weight
    )
    assert abs(total - 1.0) < 1e-9


def test_misconfigured_weights_are_rejected_at_construction():
    with pytest.raises(ValueError, match="must sum to 1.0"):
        PeerMatchingConfig(shared_expertise_weight=0.9)


# ===========================================================================
# Engine: scoring law
# ===========================================================================


def test_engine_is_deterministic():
    a = _profile(
        uuid.uuid4(),
        expertise={"information-retrieval": 0.9, "machine-learning": 0.7},
        ancestors={"information-retrieval": frozenset({"cs"}), "machine-learning": frozenset({"ai"})},
        keywords=frozenset({"evaluation"}),
        institution="MIT",
    )
    b = _profile(
        uuid.uuid4(),
        expertise={"information-retrieval": 0.8, "hci": 0.75},
        ancestors={"information-retrieval": frozenset({"cs"}), "hci": frozenset({"cs"})},
        keywords=frozenset({"evaluation", "user studies"}),
        institution="Stanford",
    )

    first = PeerMatchingEngine.score_pair(a, b, candidate_readiness="SEEKING_COLLABORATORS")
    second = PeerMatchingEngine.score_pair(a, b, candidate_readiness="SEEKING_COLLABORATORS")

    assert first.match_score == second.match_score
    assert first.explanation_reasons == second.explanation_reasons
    assert [s.weighted_contribution for s in first.signals] == [
        s.weighted_contribution for s in second.signals
    ]


def test_score_is_bounded():
    """Even a perfect match on every signal cannot exceed 1.0."""
    shared = {f"topic-{i}": 1.0 for i in range(6)}
    ancestors = {slug: frozenset({"root"}) for slug in shared}
    a = _profile(uuid.uuid4(), expertise=dict(shared), ancestors=dict(ancestors),
                 keywords=frozenset({"x", "y"}), institution="A")
    b = _profile(uuid.uuid4(), expertise=dict(shared), ancestors=dict(ancestors),
                 keywords=frozenset({"x", "y"}), institution="B")

    result = PeerMatchingEngine.score_pair(a, b, candidate_readiness="SEEKING_COLLABORATORS")
    assert 0.0 <= result.match_score <= 1.0


def test_thin_profile_reports_insufficient_evidence():
    """One accidental overlap must not become a confident match."""
    rich = _profile(uuid.uuid4(), expertise={"a": 0.9, "b": 0.8, "c": 0.7})
    thin = _profile(uuid.uuid4(), expertise={"a": 0.9})

    result = PeerMatchingEngine.score_pair(rich, thin)
    assert result.tier == PeerMatchTier.INSUFFICIENT_EVIDENCE
    assert result.match_score == 0.0
    assert result.confidence == 0.0
    assert "Not enough recorded research topics" in result.explanation_reasons[0]


def test_shared_and_complementary_are_scored_separately():
    """
    The two signals answer different questions, and collapsing them would hide whether a peer
    understands your work or extends it.
    """
    source = _profile(uuid.uuid4(), expertise={"retrieval": 0.9, "ranking": 0.8})
    # A near-clone: high shared, no complementary.
    clone = _profile(uuid.uuid4(), expertise={"retrieval": 0.9, "ranking": 0.8})
    # A complement: shares one field, brings two new ones.
    complement = _profile(
        uuid.uuid4(), expertise={"retrieval": 0.9, "hci": 0.8, "visualization": 0.75}
    )

    clone_result = PeerMatchingEngine.score_pair(source, clone)
    complement_result = PeerMatchingEngine.score_pair(source, complement)

    clone_comp = next(
        s for s in clone_result.signals if s.signal_type == PeerSignalType.COMPLEMENTARY_EXPERTISE
    )
    complement_comp = next(
        s
        for s in complement_result.signals
        if s.signal_type == PeerSignalType.COMPLEMENTARY_EXPERTISE
    )

    assert clone_comp.raw_score == 0.0, "an identical profile adds no complementary expertise"
    assert complement_comp.raw_score > 0.0
    assert set(complement_result.complementary_topics) == {"hci", "visualization"}


def test_weak_topics_do_not_count_as_shared_strength():
    config = DEFAULT_PEER_MATCHING_CONFIG
    below = config.min_shared_topic_strength - 0.05
    a = _profile(uuid.uuid4(), expertise={"x": 0.9}, emerging={"weak": below})
    b = _profile(uuid.uuid4(), expertise={"y": 0.9}, emerging={"weak": below})

    result = PeerMatchingEngine.score_pair(a, b)
    assert "weak" not in result.shared_topics


def test_taxonomy_proximity_links_sibling_fields():
    """Sibling topics under one parent are related even with no exact overlap."""
    a = _profile(
        uuid.uuid4(),
        expertise={"neural-retrieval": 0.9, "indexing": 0.7},
        ancestors={
            "neural-retrieval": frozenset({"information-retrieval", "cs"}),
            "indexing": frozenset({"information-retrieval", "cs"}),
        },
    )
    b = _profile(
        uuid.uuid4(),
        expertise={"query-understanding": 0.9, "evaluation-metrics": 0.8},
        ancestors={
            "query-understanding": frozenset({"information-retrieval", "cs"}),
            "evaluation-metrics": frozenset({"information-retrieval", "cs"}),
        },
    )

    result = PeerMatchingEngine.score_pair(a, b)
    taxonomy = next(
        s for s in result.signals if s.signal_type == PeerSignalType.TAXONOMY_PROXIMITY
    )
    assert taxonomy.raw_score > 0.0
    assert "information-retrieval" in taxonomy.evidence
    assert result.shared_topics == (), "no topic is literally shared here"


def test_unrelated_fields_score_no_taxonomy_proximity():
    a = _profile(uuid.uuid4(), expertise={"retrieval": 0.9, "ranking": 0.8},
                 ancestors={"retrieval": frozenset({"cs"}), "ranking": frozenset({"cs"})})
    b = _profile(uuid.uuid4(), expertise={"marine-biology": 0.9, "ecology": 0.8},
                 ancestors={"marine-biology": frozenset({"biology"}), "ecology": frozenset({"biology"})})

    result = PeerMatchingEngine.score_pair(a, b)
    taxonomy = next(s for s in result.signals if s.signal_type == PeerSignalType.TAXONOMY_PROXIMITY)
    assert taxonomy.raw_score == 0.0


def test_unavailable_candidate_scores_no_readiness():
    a = _profile(uuid.uuid4(), expertise={"x": 0.9, "y": 0.8})
    b = _profile(uuid.uuid4(), expertise={"x": 0.9, "z": 0.8})

    available = PeerMatchingEngine.score_pair(a, b, candidate_readiness="SEEKING_COLLABORATORS")
    unavailable = PeerMatchingEngine.score_pair(a, b, candidate_readiness="NOT_AVAILABLE")

    assert available.match_score > unavailable.match_score
    readiness = next(
        s for s in unavailable.signals if s.signal_type == PeerSignalType.COLLABORATION_READINESS
    )
    assert readiness.raw_score == 0.0


def test_cross_institution_is_preferred_over_same_institution():
    """A researcher already knows their own department; this is a mild nudge, not a filter."""
    source = _profile(uuid.uuid4(), expertise={"x": 0.9, "y": 0.8}, institution="Alpha University")
    same = _profile(uuid.uuid4(), expertise={"x": 0.9, "z": 0.8}, institution="Alpha University")
    other = _profile(uuid.uuid4(), expertise={"x": 0.9, "z": 0.8}, institution="Beta Institute")

    same_result = PeerMatchingEngine.score_pair(source, same, candidate_readiness="OPEN_TO_ENQUIRIES")
    other_result = PeerMatchingEngine.score_pair(source, other, candidate_readiness="OPEN_TO_ENQUIRIES")

    assert other_result.match_score > same_result.match_score
    # Still a real match, not excluded.
    assert same_result.match_score > 0.0


def test_explanations_are_ordered_by_contribution():
    """The reason that moved the score most should be read first."""
    a = _profile(
        uuid.uuid4(),
        expertise={"retrieval": 0.95, "ranking": 0.9, "evaluation": 0.85},
        keywords=frozenset({"benchmarks"}),
    )
    b = _profile(
        uuid.uuid4(),
        expertise={"retrieval": 0.95, "ranking": 0.9, "evaluation": 0.85},
        keywords=frozenset({"benchmarks"}),
    )

    result = PeerMatchingEngine.score_pair(a, b, candidate_readiness="OPEN_TO_ENQUIRIES")
    contributions = [
        abs(s.weighted_contribution) for s in result.signals if s.evidence and s.weighted_contribution
    ]
    assert contributions == sorted(contributions, reverse=True) or len(result.explanation_reasons) <= 1
    assert "You both work on" in result.explanation_reasons[0]


def test_ranking_excludes_self_and_sorts_stably():
    source = _profile(uuid.uuid4(), expertise={"x": 0.9, "y": 0.8})
    candidates = [
        (_profile(source.profile_id, expertise={"x": 0.9, "y": 0.8}), "SEEKING_COLLABORATORS"),
        (_profile(uuid.uuid4(), expertise={"x": 0.9, "y": 0.8}), "SEEKING_COLLABORATORS"),
        (_profile(uuid.uuid4(), expertise={"x": 0.5, "q": 0.4}), "OPEN_TO_ENQUIRIES"),
    ]

    ranked = PeerMatchingEngine.rank_candidates(source, candidates)
    assert source.profile_id not in {a.candidate_profile_id for a in ranked}
    scores = [a.match_score for a in ranked]
    assert scores == sorted(scores, reverse=True)


def test_ranking_respects_the_max_limit():
    source = _profile(uuid.uuid4(), expertise={"x": 0.9, "y": 0.8})
    candidates = [
        (_profile(uuid.uuid4(), expertise={"x": 0.9, "y": 0.8}), "SEEKING_COLLABORATORS")
        for _ in range(80)
    ]
    ranked = PeerMatchingEngine.rank_candidates(source, candidates, limit=1000)
    assert len(ranked) <= DEFAULT_PEER_MATCHING_CONFIG.max_limit


# ===========================================================================
# Consent
# ===========================================================================


def test_researcher_without_settings_is_not_discoverable(db_session: Session):
    """Absence of a decision is not consent."""
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _, hidden = _make_researcher(db_session, "Dr. Hidden")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, hidden, {"retrieval": 0.9, "hci": 0.8})

    result = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert result.matches == []
    assert result.data_sufficiency == "NO_CANDIDATES"
    assert "opt-in" in (result.guidance or "")


def test_reading_own_settings_does_not_create_consent(db_session: Session):
    """A GET that wrote a row would make the consent timestamp meaningless."""
    _, profile = _make_researcher(db_session, "Dr. Reader")

    settings = PeerDiscoveryService.get_settings(db_session, profile.id)
    assert settings.is_discoverable is False
    assert PeerDiscoveryService.load_settings(db_session, profile.id) is None


def test_opting_in_records_a_consent_timestamp(db_session: Session):
    _, profile = _make_researcher(db_session, "Dr. Consent")
    before = PeerDiscoveryService.get_settings(db_session, profile.id)
    assert before.consent_updated_at is None

    updated = PeerDiscoveryService.update_settings(
        db_session, profile.id, DiscoverySettingsUpdate(is_discoverable=True)
    )
    assert updated.is_discoverable is True
    assert updated.consent_updated_at is not None


def test_editing_a_note_does_not_restamp_consent(db_session: Session):
    """The consent timestamp records agreeing to be found, not the last text edit."""
    _, profile = _make_researcher(db_session, "Dr. Note")
    opted_in = PeerDiscoveryService.update_settings(
        db_session, profile.id, DiscoverySettingsUpdate(is_discoverable=True)
    )
    original = opted_in.consent_updated_at

    edited = PeerDiscoveryService.update_settings(
        db_session, profile.id, DiscoverySettingsUpdate(collaboration_note="Looking for co-authors")
    )
    assert edited.consent_updated_at == original
    assert edited.collaboration_note == "Looking for co-authors"


def test_opting_out_removes_a_researcher_from_results(db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _, peer = _make_researcher(db_session, "Dr. Peer", institution="Other University")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer)

    assert PeerDiscoveryService.find_peers(db_session, seeker.id).returned_count == 1

    PeerDiscoveryService.update_settings(
        db_session, peer.id, DiscoverySettingsUpdate(is_discoverable=False)
    )
    after = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert after.returned_count == 0


def test_a_researcher_who_has_not_opted_in_may_still_search(db_session: Session):
    """
    Discoverability governs being found. Requiring someone to publish themselves before they can
    look would be coercive, so searching is unconditional.
    """
    _, seeker = _make_researcher(db_session, "Dr. Private")
    _, peer = _make_researcher(db_session, "Dr. Public", institution="Other University")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer)

    result = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert result.is_discoverable is False, "the seeker has not opted in"
    assert result.returned_count == 1, "yet they can still discover peers"


def test_not_available_peers_are_excluded(db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _, peer = _make_researcher(db_session, "Dr. Busy", institution="Other University")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer, status=CollaborationStatus.NOT_AVAILABLE)

    result = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert result.returned_count == 0


# ===========================================================================
# Disclosure
# ===========================================================================


def test_institution_is_hidden_when_not_disclosed(db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _, peer = _make_researcher(db_session, "Dr. Reticent", institution="Secret Institute")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer, show_institution=False)

    result = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert result.returned_count == 1
    match = result.matches[0]
    assert match.peer.institution is None
    assert match.peer.department is None
    assert match.peer.full_name == "Dr. Reticent", "a name is still shown; that is the point of discovery"


def test_contact_email_is_withheld_by_default(db_session: Session):
    """An email address is the most consequential disclosure here, so it is opt-in."""
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _, peer = _make_researcher(db_session, "Dr. Peer", institution="Other University")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer)

    match = PeerDiscoveryService.find_peers(db_session, seeker.id).matches[0]
    assert match.peer.contact_email is None


def test_contact_email_is_shown_when_disclosed(db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    peer_user, peer = _make_researcher(db_session, "Dr. Open", institution="Other University")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer, show_contact_email=True)

    match = PeerDiscoveryService.find_peers(db_session, seeker.id).matches[0]
    assert match.peer.contact_email == peer_user.email


# ===========================================================================
# Service behaviour
# ===========================================================================


def test_thin_requester_profile_gets_actionable_guidance(db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. New")
    _, peer = _make_researcher(db_session, "Dr. Peer", institution="Other University")
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer)

    result = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert result.data_sufficiency == "INSUFFICIENT_PROFILE"
    assert result.matches == []
    assert "Add keywords" in (result.guidance or "")


def test_profile_keywords_alone_make_a_researcher_matchable(db_session: Session):
    """
    Someone who declared their focus but has not linked publications should still be matchable,
    otherwise discovery only works for established researchers.
    """
    _, seeker = _make_researcher(
        db_session, "Dr. Declared", keywords=["information retrieval", "evaluation"]
    )
    _, peer = _make_researcher(
        db_session,
        "Dr. Peer",
        institution="Other University",
        keywords=["information retrieval", "user studies"],
    )
    _add_topics(db_session, peer, {"hci": 0.85})
    _opt_in(db_session, peer)

    result = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert result.data_sufficiency == "SUFFICIENT"
    assert result.returned_count == 1


def test_collaboration_interest_filter(db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _, grant_peer = _make_researcher(db_session, "Dr. Grant", institution="A University")
    _, author_peer = _make_researcher(db_session, "Dr. Author", institution="B University")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    for peer in (grant_peer, author_peer):
        _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, grant_peer, interests=[CollaborationInterest.JOINT_GRANT])
    _opt_in(db_session, author_peer, interests=[CollaborationInterest.CO_AUTHORSHIP])

    grants = PeerDiscoveryService.find_peers(
        db_session, seeker.id, collaboration_interest=CollaborationInterest.JOINT_GRANT
    )
    assert [m.peer.profile_id for m in grants.matches] == [grant_peer.id]


def test_exclude_same_institution_filter(db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. Seeker", institution="Alpha University")
    _, internal = _make_researcher(db_session, "Dr. Internal", institution="Alpha University")
    _, external = _make_researcher(db_session, "Dr. External", institution="Beta Institute")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    for peer in (internal, external):
        _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
        _opt_in(db_session, peer)

    everyone = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert {m.peer.profile_id for m in everyone.matches} == {internal.id, external.id}

    external_only = PeerDiscoveryService.find_peers(
        db_session, seeker.id, exclude_same_institution=True
    )
    assert {m.peer.profile_id for m in external_only.matches} == {external.id}


def test_unknown_profile_raises(db_session: Session):
    with pytest.raises(ValueError, match="not found"):
        PeerDiscoveryService.find_peers(db_session, uuid.uuid4())


def test_taxonomy_ancestors_are_derived_from_stored_topics(db_session: Session):
    """
    Hierarchical proximity must come from the topics actually recorded, so peer matching cannot
    drift from the stored taxonomy.
    """
    parent = TopicModel(id=uuid.uuid4(), name="Information Retrieval", slug="information-retrieval")
    db_session.add(parent)
    db_session.flush()
    child_a = TopicModel(
        id=uuid.uuid4(), name="Neural Retrieval", slug="neural-retrieval", parent_id=parent.id
    )
    child_b = TopicModel(
        id=uuid.uuid4(), name="Query Understanding", slug="query-understanding", parent_id=parent.id
    )
    db_session.add_all([child_a, child_b])
    db_session.commit()

    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _, peer = _make_researcher(db_session, "Dr. Sibling", institution="Other University")
    _add_topics(db_session, seeker, {"neural-retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"query-understanding": 0.9, "hci": 0.8})
    _opt_in(db_session, peer)

    result = PeerDiscoveryService.find_peers(db_session, seeker.id)
    assert result.returned_count == 1
    taxonomy = next(
        s for s in result.matches[0].signals if s.signal_type == PeerSignalType.TAXONOMY_PROXIMITY
    )
    assert taxonomy.raw_score > 0.0
    assert "information-retrieval" in taxonomy.evidence


def test_peer_search_query_count_is_bounded(db_session: Session):
    """Query count must not grow with the number of candidates."""
    from sqlalchemy import event

    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    for index in range(12):
        _, peer = _make_researcher(db_session, f"Dr. Peer{index}", institution=f"Institute {index}")
        _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
        _opt_in(db_session, peer)

    engine = db_session.get_bind()
    count = 0

    def _listener(*args, **kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        result = PeerDiscoveryService.find_peers(db_session, seeker.id, limit=50)
    finally:
        event.remove(engine, "before_cursor_execute", _listener)

    assert result.returned_count == 12
    assert count <= 8, f"expected a bounded query count, executed {count}"


# ===========================================================================
# REST API
# ===========================================================================


def test_api_discovery_settings_round_trip(client: TestClient, db_session: Session):
    user, profile = _make_researcher(db_session, "Dr. Settings")
    headers = {"X-User-ID": str(user.id)}

    initial = client.get(f"/api/v1/researchers/{profile.id}/discovery-settings", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["is_discoverable"] is False

    updated = client.patch(
        f"/api/v1/researchers/{profile.id}/discovery-settings",
        headers=headers,
        json={
            "is_discoverable": True,
            "collaboration_status": "SEEKING_COLLABORATORS",
            "collaboration_interests": ["CO_AUTHORSHIP", "JOINT_GRANT"],
            "show_contact_email": True,
            "collaboration_note": "Looking for co-authors in retrieval evaluation.",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["is_discoverable"] is True
    assert body["collaboration_interests"] == ["CO_AUTHORSHIP", "JOINT_GRANT"]
    assert body["consent_updated_at"] is not None


def test_api_peer_discovery(client: TestClient, db_session: Session):
    seeker_user, seeker = _make_researcher(db_session, "Dr. Seeker", institution="Alpha University")
    _, peer = _make_researcher(db_session, "Dr. Peer", institution="Beta Institute")
    _add_topics(db_session, seeker, {"retrieval": 0.9, "ranking": 0.8})
    _add_topics(db_session, peer, {"retrieval": 0.9, "hci": 0.8})
    _opt_in(db_session, peer)

    res = client.get(
        f"/api/v1/researchers/{seeker.id}/peers", headers={"X-User-ID": str(seeker_user.id)}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["returned_count"] == 1
    assert body["data_sufficiency"] == "SUFFICIENT"
    match = body["matches"][0]
    assert match["peer"]["full_name"] == "Dr. Peer"
    assert match["match_score"] > 0
    assert match["explanation_reasons"]
    assert match["tier"] in ("STRONG", "MODERATE", "EXPLORATORY")


def test_api_peer_discovery_requires_ownership(client: TestClient, db_session: Session):
    _, seeker = _make_researcher(db_session, "Dr. Seeker")
    intruder_user, _ = _make_researcher(db_session, "Dr. Intruder")

    forbidden = client.get(
        f"/api/v1/researchers/{seeker.id}/peers", headers={"X-User-ID": str(intruder_user.id)}
    )
    assert forbidden.status_code == 403

    anonymous = client.get(f"/api/v1/researchers/{seeker.id}/peers")
    assert anonymous.status_code == 401


def test_api_discovery_settings_require_ownership(client: TestClient, db_session: Session):
    _, profile = _make_researcher(db_session, "Dr. Owner")
    intruder_user, _ = _make_researcher(db_session, "Dr. Intruder")

    assert (
        client.get(
            f"/api/v1/researchers/{profile.id}/discovery-settings",
            headers={"X-User-ID": str(intruder_user.id)},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/researchers/{profile.id}/discovery-settings",
            headers={"X-User-ID": str(intruder_user.id)},
            json={"is_discoverable": True},
        ).status_code
        == 403
    )
