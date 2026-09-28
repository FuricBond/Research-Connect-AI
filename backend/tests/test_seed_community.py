"""
Community seeder: sixty fictional researchers who use the platform through its own services.

Runs the seeder against in-memory SQLite with foreign keys enforced, on top of the demo
seed, to verify it creates people that authenticate, drives postings and applications through
the real services (histories and notifications included), is idempotent, never adopts an
account it did not create, and removes exactly what it added.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, verify_password
from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.notification import NotificationModel
from app.models.opportunity import OpportunityModel
from app.models.research_posting import PostingStatus, ResearchPostingModel
from app.models.research_posting_application import ResearchPostingApplicationModel
from app.models.researcher_discovery import ResearcherDiscoverySettingsModel
from app.models.topic import TopicModel
from app.models.user import UserModel
from scripts import seed_community, seed_demo_data

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

PASSWORD = "CommunityTest123!"
NOW = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # cascades behave as in PostgreSQL

    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    # The demo set first: its faculty's open assistantship receives community applications.
    profiles = seed_demo_data._seed_accounts(session, "DemoSeedTest123!", False)
    seed_demo_data._seed_opportunities(session, NOW, False)
    seed_demo_data._seed_postings(session, profiles["demo.faculty@researchconnect.test"], NOW, False)
    existing = set(session.execute(select(TopicModel.slug)).scalars())
    wanted = {slug for area in seed_community.AREAS.values() for slug in area.topics} - existing
    for slug in sorted(wanted):
        session.add(TopicModel(id=uuid.uuid4(), name=slug.replace("-", " ").title(), slug=slug))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def community_users(db: Session) -> list[UserModel]:
    users = db.execute(
        select(UserModel).where(UserModel.email.in_(seed_community.community_emails()))
    ).scalars().all()
    return [u for u in users if seed_community.is_community_account(u)]


def applications(db: Session) -> list[ResearchPostingApplicationModel]:
    return db.execute(select(ResearchPostingApplicationModel)).scalars().all()


def test_creates_sixty_people_who_can_sign_in(db):
    result = seed_community.seed_community(db, PASSWORD, now=NOW)

    assert (result["people"], result["faculty"], result["students"]) == (60, 15, 45)
    users = community_users(db)
    assert len(users) == 60
    assert all(verify_password(PASSWORD, u.hashed_password) for u in users[:3])
    faculty = next(u for u in users if u.email == "rohan.mehta@kaveritech.edu")
    assert (faculty.full_name, faculty.role) == ("Dr. Rohan Mehta", "FACULTY")


def test_people_look_real_and_carry_no_placeholder_links(db):
    seed_community.seed_community(db, PASSWORD, now=NOW)

    for user in community_users(db):
        assert "example" not in user.email and not user.email.endswith(".test")
    for posting in db.execute(select(ResearchPostingModel)).scalars():
        assert posting.external_url is None
    # The demo seeder's made-up venues no longer carry placeholder links either.
    for opportunity in db.execute(select(OpportunityModel)).scalars():
        assert opportunity.website_url is None and opportunity.submission_url is None


def test_postings_and_applications_go_through_the_services(db):
    result = seed_community.seed_community(db, PASSWORD, now=NOW)

    assert result["postings_created"] == len(seed_community.POSTINGS)
    by_title = {p.title: p for p in db.execute(select(ResearchPostingModel)).scalars()}
    for spec in seed_community.POSTINGS:
        posting = by_title[spec.title]
        assert posting.status == spec.final_status.value
        assert (posting.published_at is None) == (spec.final_status == PostingStatus.DRAFT)

    apps = applications(db)
    assert len(apps) == result["applications_created"] > 20
    statuses = {a.status for a in apps}
    assert {"SUBMITTED", "UNDER_REVIEW", "SHORTLISTED", "REJECTED", "ACCEPTED"} <= statuses
    # Each move was recorded by the service, and people were notified.
    assert all(a.status_history for a in apps if a.status != "SUBMITTED")
    assert db.execute(select(func.count()).select_from(NotificationModel)).scalar_one() > len(apps)
    filled = by_title["Research assistantship: annotation study for clinical text"]
    assert any(a.status == "ACCEPTED" for a in apps if a.posting_id == filled.id)


def test_demo_assistantship_gets_applications_left_for_the_demo_to_review(db):
    seed_community.seed_community(db, PASSWORD, now=NOW)

    posting = db.execute(
        select(ResearchPostingModel).where(ResearchPostingModel.title == seed_community.DEMO_ASSISTANTSHIP_TITLE)
    ).scalar_one()
    demo_apps = [a for a in applications(db) if a.posting_id == posting.id]
    assert len(demo_apps) == 4
    assert {a.status for a in demo_apps} <= {"SUBMITTED", "UNDER_REVIEW"}


def test_most_people_opt_in_to_peer_discovery_without_showing_email(db):
    seed_community.seed_community(db, PASSWORD, now=NOW)

    settings = db.execute(select(ResearcherDiscoverySettingsModel)).scalars().all()
    community = [s for s in settings if s.collaboration_note and "collaborat" in s.collaboration_note.lower()]
    assert len(community) >= 40
    assert not any(s.show_contact_email for s in community)


def test_rerunning_adds_nothing(db):
    seed_community.seed_community(db, PASSWORD, now=NOW)
    before = (len(community_users(db)), len(applications(db)))

    again = seed_community.seed_community(db, PASSWORD, now=NOW)

    assert (again["postings_created"], again["applications_created"]) == (0, 0)
    assert (len(community_users(db)), len(applications(db))) == before


def test_an_account_someone_else_registered_is_never_adopted(db):
    taken = "aditi.kulkarni@kaveritech.edu"
    stranger = UserModel(
        id=uuid.uuid4(), email=taken, hashed_password=hash_password("TheirOwnPass1!"),
        full_name="Someone Else", role="STUDENT", is_active=True,
    )
    db.add(stranger)
    db.commit()

    result = seed_community.seed_community(db, PASSWORD, now=NOW)
    removed = seed_community.remove_community(db)

    assert result["skipped_foreign_emails"] == 1
    db.refresh(stranger)
    assert stranger.full_name == "Someone Else"
    assert verify_password("TheirOwnPass1!", stranger.hashed_password)
    assert removed["kept_foreign"] == 1


def test_remove_deletes_only_what_the_seeder_added(db):
    seed_community.seed_community(db, PASSWORD, now=NOW)

    result = seed_community.remove_community(db)

    assert result["accounts_removed"] == 60
    assert community_users(db) == []
    assert applications(db) == []  # every applicant was a community student
    remaining = {p.title for p in db.execute(select(ResearchPostingModel)).scalars()}
    assert remaining == set(seed_demo_data.DEMO_POSTING_TITLES)
    demo = db.execute(select(UserModel).where(UserModel.email.in_(seed_demo_data.DEMO_EMAILS))).scalars().all()
    assert len(demo) == 3


@pytest.mark.parametrize(
    ("password", "env", "message"),
    [
        (None, "development", "required"),
        ("short", "development", "at least"),
        ("DemoPass123!", "production", "public demo password"),
    ],
)
def test_password_policy(password, env, message):
    with pytest.raises(ValueError, match=message):
        seed_community.resolve_password(password, env)
