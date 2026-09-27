"""
Step 19 — the demo environment can be recreated on a clean database, and the P2-1 fix holds.

Runs first, on the fresh database run_e2e.py starts. The P2-1 scenario is the one the Phase
6.4 audit found: someone registers a demo email through the public API before the seeder
runs, hoping the seeder will adopt the account and promote it (to ADMIN, for the admin
email) with the seed password. The seeder must refuse without writing anything, the account
must keep its own role and password, and only an explicit `--reset` may replace it.
"""
from __future__ import annotations

import pytest

from conftest import (
    DEMO_EMAILS,
    DEMO_PASSWORD,
    all_opportunities,
    login,
    login_account,
    new_password,
    request,
    rows,
    run_seeder,
    scalar,
)


def test_p2_1_seeder_refuses_to_adopt_a_demo_email_registered_through_the_api(db):
    if login(DEMO_EMAILS["admin"], DEMO_PASSWORD).status_code == 200:
        pytest.skip("needs an unseeded database; the full run starts from one")

    squatter_password = new_password()
    registered = request("POST", "/api/v1/auth/register", json={
        "email": DEMO_EMAILS["admin"], "password": squatter_password, "full_name": "Not The Admin",
    })
    assert registered.status_code == 201, registered.text
    assert registered.json()["user"]["role"] == "STUDENT"
    users_before = scalar(db, "SELECT count(*) FROM users")

    result = run_seeder()

    assert result.returncode == 1, result.stdout[-1500:] + result.stderr[-1500:]
    assert DEMO_EMAILS["admin"] in result.stderr + result.stdout
    assert DEMO_PASSWORD not in result.stderr + result.stdout, "the seed password must never be logged"
    # Nothing was written, and the account kept its own role and password.
    assert scalar(db, "SELECT count(*) FROM users") == users_before
    assert scalar(db, "SELECT count(*) FROM opportunities") == 0
    own = login(DEMO_EMAILS["admin"], squatter_password)
    assert own.status_code == 200 and own.json()["user"]["role"] == "STUDENT"
    assert login(DEMO_EMAILS["admin"], DEMO_PASSWORD).status_code == 401


def test_reset_replaces_the_foreign_account_and_seeds_the_documented_dataset(db):
    result = run_seeder("--reset")
    assert result.returncode == 0, result.stderr[-2000:]
    assert DEMO_PASSWORD not in result.stderr + result.stdout

    accounts = {role: login_account(email, DEMO_PASSWORD) for role, email in DEMO_EMAILS.items()}
    assert {role: a.role for role, a in accounts.items()} == {
        "faculty": "FACULTY", "student": "STUDENT", "admin": "ADMIN",
    }
    # Twelve opportunities; the two past their deadline are already EXPIRED, and the public
    # listing shows only ACTIVE/UNVERIFIED ones unless a status is requested.
    assert scalar(db, "SELECT count(*) FROM opportunities") == 12
    listed = all_opportunities()
    assert len(listed) == 10 and {o["status"] for o in listed} == {"ACTIVE"}
    expired = request("GET", "/api/opportunities", params={"status": "EXPIRED", "page_size": 100}).json()["items"]
    assert len(expired) == 2
    # Three postings: two published, one draft visible only to its author.
    public = accounts["student"].get("/api/v1/postings").json()["postings"]
    mine = accounts["faculty"].get("/api/v1/postings/mine").json()["postings"]
    assert len(public) == 2 and {p["status"] for p in public} == {"OPEN"}
    assert sorted(p["status"] for p in mine) == ["DRAFT", "OPEN", "OPEN"]
    assert any(p["is_accepting_applications"] for p in public)
    # Peer discoverability for faculty and student (Phase 5.12).
    for role in ("faculty", "student"):
        a = accounts[role]
        assert a.get(f"/api/v1/researchers/{a.profile_id}/discovery-settings").json()["is_discoverable"] is True
    # The squatter's password no longer opens the admin account.
    admin_rows = rows(db, "SELECT role FROM users WHERE email = :e", e=DEMO_EMAILS["admin"])
    assert admin_rows == [{"role": "ADMIN"}]


def test_seeding_again_is_idempotent(db):
    counts = lambda: {t: scalar(db, f"SELECT count(*) FROM {t}") for t in ("users", "opportunities", "research_postings")}
    before = counts()
    result = run_seeder()
    assert result.returncode == 0, result.stderr[-2000:]
    assert counts() == before


def test_representative_demo_workflow(demo):
    student, faculty, admin = demo["student"], demo["faculty"], demo["admin"]
    # The student finds the assistantship that accepts applications on the platform.
    postings = student.get("/api/v1/postings").json()["postings"]
    ra = next(p for p in postings if p["posting_type"] == "RESEARCH_ASSISTANTSHIP")
    assert ra["is_accepting_applications"] and ra["author"]["full_name"]
    # The faculty member's personalized view has candidates from the seeded corpus.
    ranked = faculty.get(f"/api/v1/researchers/{faculty.profile_id}/personalized-recommendations", params={"limit": 20})
    assert ranked.status_code == 200, ranked.text
    assert ranked.json()["recommendations"]
    # The administrator sees every demo account.
    users = admin.get("/api/v1/admin/users", params={"limit": 100})
    assert users.status_code == 200, users.text
    body = users.json()
    listed = {u["email"] for u in (body["users"] if isinstance(body, dict) and "users" in body else body.get("items", body))}
    assert set(DEMO_EMAILS.values()) <= listed
