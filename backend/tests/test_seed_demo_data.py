"""
Phase 6 — Demo data seeder tests (audit finding P1-10).

The repository ships no dataset, so a fresh database has nothing for ranking, risk or
deadline intelligence to operate on. These tests run the seeder against in-memory SQLite to
verify it is idempotent, produces credentials that actually authenticate, and yields a corpus
that exercises the intelligence pipelines (expired deadlines and predatory venues included).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import verify_password
from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_preference import ResearcherPreferenceModel
from app.models.user import UserModel
from app.models.research_posting import PostingStatus, PostingType, ResearchPostingModel
from app.models.researcher_discovery import ResearcherDiscoverySettingsModel
from app.models.researcher_interest import ResearcherInterestModel
from app.models.topic import TopicModel
from app.ranking.risk.scoring import assess_opportunity_risk
from app.services.peer_discovery_service import PeerDiscoveryService
from scripts import seed_demo_data

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

TEST_PASSWORD = "SeedTestPass123!"


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


def _seed(db: Session, *, dry_run: bool = False) -> dict:
    """Runs the seeder's units against a supplied session, in the same order as main()."""
    from datetime import datetime, timezone

    reference_time = datetime.now(timezone.utc)
    profiles = seed_demo_data._seed_accounts(db, TEST_PASSWORD, dry_run)
    created, updated = seed_demo_data._seed_opportunities(db, reference_time, dry_run)
    pref_created = 0
    faculty = profiles.get("demo.faculty@researchconnect.test")
    if faculty is not None:
        pref_created = seed_demo_data._seed_preferences(db, faculty, dry_run)
    seed_demo_data._seed_topics(db, dry_run)
    expertise_created = seed_demo_data._seed_expertise(db, profiles, dry_run)
    discovery_created = seed_demo_data._seed_discovery_settings(
        db, profiles, reference_time, dry_run
    )
    posting_created, posting_updated = seed_demo_data._seed_postings(
        db, faculty, reference_time, dry_run
    )
    return {
        "profiles": profiles,
        "opportunities_created": created,
        "opportunities_updated": updated,
        "preferences_created": pref_created,
        "expertise_created": expertise_created,
        "discovery_created": discovery_created,
        "postings_created": posting_created,
        "postings_updated": posting_updated,
    }


def test_seed_creates_accounts_profiles_preferences_and_opportunities(db_session: Session):
    result = _seed(db_session)

    assert len(result["profiles"]) == len(seed_demo_data.DEMO_ACCOUNTS)
    assert result["opportunities_created"] == len(seed_demo_data.DEMO_OPPORTUNITIES)
    assert result["preferences_created"] == len(seed_demo_data.DEMO_PREFERENCES)

    user_count = db_session.scalar(select(func.count(UserModel.id)))
    profile_count = db_session.scalar(select(func.count(ResearchProfileModel.id)))
    assert user_count == len(seed_demo_data.DEMO_ACCOUNTS)
    assert profile_count == len(seed_demo_data.DEMO_ACCOUNTS)

    roles = set(db_session.execute(select(UserModel.role)).scalars().all())
    assert roles == {"FACULTY", "STUDENT", "ADMIN"}, "demo must cover every platform role"


def test_seeded_password_authenticates(db_session: Session):
    """A demo account is useless if its stored hash does not verify."""
    _seed(db_session)
    user = db_session.execute(
        select(UserModel).where(UserModel.email == "demo.faculty@researchconnect.test")
    ).scalar_one()

    assert verify_password(TEST_PASSWORD, user.hashed_password)
    assert not verify_password("wrong-password", user.hashed_password)


def test_seed_is_idempotent(db_session: Session):
    """Re-running must update in place rather than duplicating rows."""
    _seed(db_session)
    second = _seed(db_session)

    assert second["opportunities_created"] == 0
    assert second["opportunities_updated"] == len(seed_demo_data.DEMO_OPPORTUNITIES)
    assert second["preferences_created"] == 0
    assert second["postings_created"] == 0
    assert second["postings_updated"] == len(seed_demo_data.DEMO_POSTINGS)
    assert second["expertise_created"] == 0
    assert second["discovery_created"] == 0

    assert db_session.scalar(select(func.count(UserModel.id))) == len(seed_demo_data.DEMO_ACCOUNTS)
    assert db_session.scalar(select(func.count(OpportunityModel.id))) == len(
        seed_demo_data.DEMO_OPPORTUNITIES
    )
    assert db_session.scalar(select(func.count(ResearcherPreferenceModel.id))) == len(
        seed_demo_data.DEMO_PREFERENCES
    )


def test_dry_run_writes_nothing(db_session: Session):
    _seed(db_session, dry_run=True)

    assert db_session.scalar(select(func.count(UserModel.id))) == 0
    assert db_session.scalar(select(func.count(OpportunityModel.id))) == 0


def test_corpus_exercises_deadline_and_risk_intelligence(db_session: Session):
    """
    A demo corpus of uniformly healthy future deadlines would never show the deadline or
    risk engines doing anything, so the seed deliberately includes both edge cases.
    """
    _seed(db_session)
    opportunities = db_session.execute(select(OpportunityModel)).scalars().all()

    expired = [o for o in opportunities if o.status == "EXPIRED"]
    assert expired, "corpus must include expired opportunities for the deadline engine"

    flagged = [o for o in opportunities if o.is_predatory_flag]
    assert len(flagged) == 2, "corpus must include the two synthetic predatory venues"

    # The Phase 2.6 engine must independently reach a high-risk verdict from the text alone,
    # not merely trust the seeded flag.
    for opportunity in flagged:
        assessment = assess_opportunity_risk(opportunity)
        assert assessment.risk_score >= 0.70, (
            f"risk engine scored seeded predatory venue {opportunity.title!r} at "
            f"{assessment.risk_score}"
        )

    reputable = [o for o in opportunities if not o.is_predatory_flag]
    for opportunity in reputable:
        assessment = assess_opportunity_risk(opportunity)
        assert assessment.risk_score < 0.70, (
            f"risk engine false-positived on reputable venue {opportunity.title!r}"
        )

    types = {o.opportunity_type for o in opportunities}
    assert {"CONFERENCE", "JOURNAL", "WORKSHOP"}.issubset(types)


def test_reset_removes_seeded_rows(db_session: Session):
    _seed(db_session)
    removed = seed_demo_data._delete_demo_rows(db_session)

    assert removed["users"] == len(seed_demo_data.DEMO_ACCOUNTS)
    assert removed["opportunities"] == len(seed_demo_data.DEMO_OPPORTUNITIES)
    assert db_session.scalar(select(func.count(UserModel.id))) == 0
    assert db_session.scalar(select(func.count(OpportunityModel.id))) == 0
    # Profiles and preferences cascade from the deleted accounts.
    assert db_session.scalar(select(func.count(ResearchProfileModel.id))) == 0
    assert db_session.scalar(select(func.count(ResearcherPreferenceModel.id))) == 0


def test_schema_preflight_reports_missing_tables():
    """Seeding an unmigrated database must say so instead of raising a driver traceback."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    empty_session = sessionmaker(bind=engine)()
    try:
        missing = seed_demo_data.verify_schema(empty_session)
        assert set(missing) == set(seed_demo_data.REQUIRED_TABLES)
    finally:
        empty_session.close()


def test_schema_preflight_passes_on_migrated_schema(db_session: Session):
    assert seed_demo_data.verify_schema(db_session) == []


def test_reset_leaves_unrelated_rows_untouched(db_session: Session):
    """The reset is keyed on demo identifiers and must not touch real data."""
    real_user = UserModel(
        id=uuid.uuid4(),
        email="real.researcher@university.edu",
        hashed_password="hashed",
        full_name="Real Researcher",
        role="FACULTY",
        is_active=True,
    )
    real_opp = OpportunityModel(
        id=uuid.uuid4(),
        title="A Genuine Conference Not Seeded By The Demo Script",
        opportunity_type="CONFERENCE",
        status="ACTIVE",
        delivery_mode="ONLINE",
    )
    db_session.add_all([real_user, real_opp])
    db_session.commit()

    _seed(db_session)
    seed_demo_data._delete_demo_rows(db_session)

    assert db_session.get(UserModel, real_user.id) is not None
    assert db_session.get(OpportunityModel, real_opp.id) is not None


def test_seeded_postings_cover_published_funded_and_draft(db_session: Session):
    """
    The demo needs one of each shape: a published supervisor-led posting, a funded opening that
    accepts applications, and a draft, so both the discovery and authoring views have content.
    """
    _seed(db_session)
    postings = db_session.execute(select(ResearchPostingModel)).scalars().all()
    assert len(postings) == len(seed_demo_data.DEMO_POSTINGS)

    statuses = {p.status for p in postings}
    assert PostingStatus.OPEN.value in statuses
    assert PostingStatus.DRAFT.value in statuses

    published = [p for p in postings if p.status == PostingStatus.OPEN.value]
    assert all(p.published_at is not None for p in published), (
        "a published posting must carry its first-publication timestamp"
    )
    drafts = [p for p in postings if p.status == PostingStatus.DRAFT.value]
    assert all(p.published_at is None for p in drafts)

    funded = [
        p for p in postings if PostingType(p.posting_type) in PostingType.structured_openings()
    ]
    assert funded, "the corpus must include a structured funded opening"
    accepting = [p for p in funded if p.accepts_applications]
    assert accepting, "at least one opening must accept on-platform applications"
    assert accepting[0].compensation_type != "UNSPECIFIED"
    assert accepting[0].compensation_amount is not None


def test_seeded_postings_are_owned_by_the_faculty_account(db_session: Session):
    result = _seed(db_session)
    faculty = result["profiles"]["demo.faculty@researchconnect.test"]
    postings = db_session.execute(select(ResearchPostingModel)).scalars().all()
    assert {p.author_profile_id for p in postings} == {faculty.id}
    assert {p.author_user_id for p in postings} == {faculty.user_id}


def test_seeded_expertise_produces_an_explainable_peer_match(db_session: Session):
    """
    Peer discovery is only demonstrable if the seeded researchers actually match, with both
    shared and complementary signal rather than being near-identical or unrelated.
    """
    result = _seed(db_session)
    faculty = result["profiles"]["demo.faculty@researchconnect.test"]
    student = result["profiles"]["demo.student@researchconnect.test"]

    matches = PeerDiscoveryService.find_peers(db_session, faculty.id)
    assert matches.data_sufficiency == "SUFFICIENT"
    assert matches.returned_count >= 1
    match = next(m for m in matches.matches if m.peer.profile_id == student.id)
    assert match.shared_topics, "the demo pair must share at least one topic"
    assert match.complementary_topics, "and each must bring something the other lacks"
    assert match.explanation_reasons


def test_seeded_discovery_settings_record_consent(db_session: Session):
    _seed(db_session)
    settings = db_session.execute(select(ResearcherDiscoverySettingsModel)).scalars().all()
    assert len(settings) == len(seed_demo_data.DEMO_DISCOVERY)
    assert all(row.is_discoverable for row in settings)
    assert all(row.consent_updated_at is not None for row in settings), (
        "opting in must record when consent was given"
    )
    # Email stays private even in the demo data, matching the product default.
    assert all(row.show_contact_email is False for row in settings)


def test_seeded_topic_tree_has_resolvable_parents(db_session: Session):
    """A child topic with an unresolved parent would silently lose taxonomy proximity."""
    _seed(db_session)
    topics = {t.slug: t for t in db_session.execute(select(TopicModel)).scalars().all()}
    for slug, parent_slug in seed_demo_data.DEMO_TOPIC_TREE.items():
        assert slug in topics, f"{slug} was not created"
        if parent_slug is None:
            assert topics[slug].parent_id is None
        else:
            assert topics[slug].parent_id == topics[parent_slug].id


def test_reset_removes_phase5_seed_content(db_session: Session):
    _seed(db_session)
    removed = seed_demo_data._delete_demo_rows(db_session)

    assert removed["postings"] == len(seed_demo_data.DEMO_POSTINGS)
    assert removed["discovery_settings"] == len(seed_demo_data.DEMO_DISCOVERY)
    assert removed["interests"] > 0
    assert db_session.scalar(select(func.count(ResearchPostingModel.id))) == 0
    assert db_session.scalar(select(func.count(ResearcherDiscoverySettingsModel.id))) == 0
    assert db_session.scalar(select(func.count(ResearcherInterestModel.id))) == 0
