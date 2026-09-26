"""
Phase 6.4 audit P2-1 — the demo seeder must never adopt an account it did not create.

Anyone can register a demo email (such as demo.admin@researchconnect.test) through the API.
The seeder used to find that account by email and update it in place: a demo role (ADMIN
included), a new password and `is_verified`, while keeping its ID, so the tokens its owner
already held became ADMIN tokens. These tests run the real seeder entry point in production
mode against in-memory SQLite, and the attack through the real API.
"""
from __future__ import annotations

import logging
import secrets
import sys
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.db.types import TSVector, Vector
from app.main import app
from app.models.base import Base
from app.models.opportunity import OpportunityModel
from app.models.user import UserModel
from scripts import seed_demo_data

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

ADMIN = "demo.admin@researchconnect.test"
FACULTY = "demo.faculty@researchconnect.test"
STUDENT = "demo.student@researchconnect.test"
OPERATOR_PASSWORD = "Operator-" + secrets.token_urlsafe(12)


@pytest.fixture
def factory(monkeypatch):
    """A fresh database shared by the seeder and the API, with production settings."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(seed_demo_data, "SessionLocal", session_factory)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_dev_identity_enabled", False)
    yield session_factory
    engine.dispose()


def run_seeder(monkeypatch, *flags: str, password: str = OPERATOR_PASSWORD) -> int:
    monkeypatch.setattr(sys, "argv", ["seed_demo_data", *flags, "--password", password])
    return seed_demo_data.main()


def add_account(factory, email: str, role: str, password: str) -> uuid.UUID:
    """An account created the way registration creates one: a plain random ID."""
    with factory() as db:
        user = UserModel(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            full_name="Mallory",
            role=role,
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        db.commit()
        return user.id


def demo_accounts(factory) -> dict[str, tuple]:
    with factory() as db:
        users = db.execute(
            select(UserModel).where(UserModel.email.in_(seed_demo_data.DEMO_EMAILS))
        ).scalars().all()
        return {u.email: (u.id, u.role, u.hashed_password, u.is_verified) for u in users}


def count(factory, model) -> int:
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model))


# ── The attack ────────────────────────────────────────────────────────────────


def test_attack_a_registered_demo_admin_email_gains_nothing_from_seeding(factory, monkeypatch):
    """
    The audited scenario end to end: the attacker registers demo.admin as a STUDENT with
    their own password and keeps the token; the operator then seeds production without
    --reset. The attacker must stay a STUDENT, keep their password, and stay out of admin.
    """

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        attacker_password = "Attacker-" + secrets.token_urlsafe(12)
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": ADMIN, "password": attacker_password, "full_name": "Mallory"},
        )
        assert registered.status_code == 201
        assert registered.json()["user"]["role"] == "STUDENT"
        token = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        second = client.post(
            "/api/v1/auth/register",
            json={"email": "mallory.two@example.org", "password": attacker_password, "full_name": "Mallory Two"},
        )
        hash_before = demo_accounts(factory)[ADMIN][2]

        assert run_seeder(monkeypatch) == 1, "the seeder refuses instead of adopting the account"

        me = client.get("/api/v1/auth/me", headers=token)
        assert me.status_code == 200 and me.json()["role"] == "STUDENT"
        assert client.get("/api/v1/admin/users", headers=token).status_code == 403
        promote = client.patch(
            f"/api/v1/admin/users/{second.json()['user']['id']}", headers=token, json={"role": "ADMIN"}
        )
        assert promote.status_code == 403

        assert demo_accounts(factory)[ADMIN][2] == hash_before
        login = {"email": ADMIN, "password": attacker_password}
        assert client.post("/api/v1/auth/login", json=login).status_code == 200
        login["password"] = OPERATOR_PASSWORD
        assert client.post("/api/v1/auth/login", json=login).status_code == 401

        assert set(demo_accounts(factory)) == {ADMIN}, "the refused run created no demo accounts"
        assert count(factory, OpportunityModel) == 0, "and wrote no demo data"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    ("email", "role"),
    [
        (ADMIN, "STUDENT"),  # STUDENT -> demo ADMIN
        (ADMIN, "FACULTY"),  # self-registered FACULTY -> demo ADMIN
        (FACULTY, "STUDENT"),  # STUDENT -> demo FACULTY
        (STUDENT, "STUDENT"),  # same role: the account and its password still stay its owner's
    ],
)
def test_an_existing_account_with_a_demo_email_keeps_its_role_and_password(factory, monkeypatch, email, role):
    own_password = "Own-" + secrets.token_urlsafe(12)
    add_account(factory, email, role, own_password)
    before = demo_accounts(factory)[email]

    assert run_seeder(monkeypatch) == 1

    after = demo_accounts(factory)
    assert set(after) == {email}
    assert after[email] == before, "ID, role, password hash and verification are all unchanged"
    assert after[email][1] == role
    assert verify_password(own_password, after[email][2])
    assert not verify_password(OPERATOR_PASSWORD, after[email][2])
    assert count(factory, OpportunityModel) == 0


def test_an_account_registered_after_the_check_is_refused_and_the_run_rolled_back(factory, monkeypatch):
    """
    The up-front check and the update are separate statements, so an account can be
    registered in between. The update itself refuses it and nothing from the run commits,
    including the faculty and student rows added before the admin email was reached.
    """
    add_account(factory, ADMIN, "STUDENT", "Own-password-1")
    before = demo_accounts(factory)
    monkeypatch.setattr(seed_demo_data, "find_foreign_demo_accounts", lambda db: [])

    assert run_seeder(monkeypatch) == 1

    assert demo_accounts(factory) == before
    assert count(factory, OpportunityModel) == 0


# ── Legitimate seeding still works ────────────────────────────────────────────


def test_a_fresh_database_gets_the_demo_accounts_with_seeder_issued_ids(factory, monkeypatch):
    assert run_seeder(monkeypatch) == 0

    assert {email: row[1] for email, row in demo_accounts(factory).items()} == {
        FACULTY: "FACULTY",
        STUDENT: "STUDENT",
        ADMIN: "ADMIN",
    }
    with factory() as db:
        for user in db.execute(select(UserModel)).scalars():
            assert seed_demo_data.is_seeded_demo_account(user)
            assert user.id.version == 4
            assert verify_password(OPERATOR_PASSWORD, user.hashed_password)


def test_re_running_updates_the_seeded_accounts_in_place(factory, monkeypatch):
    assert run_seeder(monkeypatch) == 0
    first = demo_accounts(factory)
    opportunities = count(factory, OpportunityModel)

    assert run_seeder(monkeypatch) == 0

    second = demo_accounts(factory)
    assert {e: row[:2] for e, row in second.items()} == {e: row[:2] for e, row in first.items()}
    assert count(factory, UserModel) == len(seed_demo_data.DEMO_ACCOUNTS)
    assert count(factory, OpportunityModel) == opportunities


def test_a_seeded_account_is_restored_and_takes_the_new_password_on_a_re_run(factory, monkeypatch):
    """The existing contract for the seeder's own accounts: a re-run yields known credentials."""
    assert run_seeder(monkeypatch) == 0
    with factory() as db:
        faculty = db.execute(select(UserModel).where(UserModel.email == FACULTY)).scalar_one()
        faculty.role = "STUDENT"
        faculty.is_active = False
        db.commit()
        faculty_id = faculty.id
    rotated = "Rotated-" + secrets.token_urlsafe(12)

    assert run_seeder(monkeypatch, password=rotated) == 0

    with factory() as db:
        faculty = db.execute(select(UserModel).where(UserModel.email == FACULTY)).scalar_one()
        assert faculty.id == faculty_id
        assert faculty.role == "FACULTY" and faculty.is_active
        assert verify_password(rotated, faculty.hashed_password)


def test_dry_run_writes_nothing_and_reports_the_same_refusal(factory, monkeypatch):
    assert run_seeder(monkeypatch, "--dry-run") == 0
    assert count(factory, UserModel) == 0 and count(factory, OpportunityModel) == 0

    add_account(factory, ADMIN, "STUDENT", "Own-password-1")
    before = demo_accounts(factory)
    assert run_seeder(monkeypatch, "--dry-run") == 1
    assert demo_accounts(factory) == before

    # A real --reset would delete the account first, so its dry run goes ahead, still writing nothing.
    assert run_seeder(monkeypatch, "--dry-run", "--reset") == 0
    assert demo_accounts(factory) == before
    assert count(factory, OpportunityModel) == 0


# ── --reset keeps its documented semantics ───────────────────────────────────


def test_reset_deletes_an_account_using_a_demo_email_and_recreates_the_demo_set(factory, monkeypatch, caplog):
    attacker_id = add_account(factory, ADMIN, "STUDENT", "Own-password-1")
    caplog.set_level(logging.WARNING, logger="seed.demo")

    assert run_seeder(monkeypatch, "--reset") == 0

    assert f"--reset deletes {ADMIN}, which this seeder did not create" in caplog.text
    with factory() as db:
        assert db.get(UserModel, attacker_id) is None, "the attacker's identity, and its tokens, are gone"
        admin = db.execute(select(UserModel).where(UserModel.email == ADMIN)).scalar_one()
        assert admin.id != attacker_id
        assert seed_demo_data.is_seeded_demo_account(admin) and admin.role == "ADMIN"
    assert count(factory, UserModel) == len(seed_demo_data.DEMO_ACCOUNTS)


def test_reset_still_recreates_the_seeded_accounts_under_new_ids(factory, monkeypatch):
    """Tokens issued before a reset keep failing afterwards, because the identities change."""
    assert run_seeder(monkeypatch) == 0
    first = demo_accounts(factory)

    assert run_seeder(monkeypatch, "--reset") == 0

    second = demo_accounts(factory)
    assert set(second) == set(first)
    assert all(second[email][0] != first[email][0] for email in first)


# ── The account ID scheme ─────────────────────────────────────────────────────


def test_only_seeder_issued_ids_are_recognised():
    seeded = seed_demo_data.new_demo_account_id(ADMIN)
    assert seeded.version == 4
    assert seed_demo_data.is_seeded_demo_account(UserModel(id=seeded, email=ADMIN))
    assert not seed_demo_data.is_seeded_demo_account(UserModel(id=seeded, email=FACULTY)), (
        "the check is bound to the email"
    )
    assert seed_demo_data.new_demo_account_id(ADMIN) != seeded, "random, so --reset issues new identities"
    assert not any(
        seed_demo_data.is_seeded_demo_account(UserModel(id=uuid.uuid4(), email=ADMIN)) for _ in range(10_000)
    ), "registration-assigned IDs are never mistaken for seeded ones"
