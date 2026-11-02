"""
The independent audit's API findings, against the running stack with PostgreSQL behind it:
what a unit test on SQLite cannot show (concurrency, the migration's column, real status codes).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import secrets
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, text

from conftest import API_URL, DATABASE_URL, Account, confirm_email, opportunity_by_title, register, request, scalar


POSTING = {
    "posting_type": "RESEARCH_ASSISTANTSHIP",
    "description": "Work on causal inference methods with the group for a semester.",
    "required_skills": ["python"],
    "opening_terms": {
        "compensation_type": "STIPEND",
        "compensation_amount": 1000,
        "compensation_currency": "USD",
        "compensation_period": "MONTH",
        "commitment_type": "PART_TIME",
        "hours_per_week": 10,
        "duration_months": 6,
        "accepts_applications": True,
    },
}


def _workspace(owner: Account) -> str:
    made = owner.post("/api/v1/workspace", json={"opportunity_id": opportunity_by_title("Conference on Applied Machine Learning")["id"]})
    assert made.status_code == 201, made.text
    return made.json()["id"]


# ── FUNC-01, SEC-05 ──────────────────────────────────────────────────────────


def test_an_invitation_is_answered_by_its_invitee_and_only_a_hash_is_stored(db):
    owner, invitee, other = register(label="inv-owner"), register(label="inv-invitee"), register(label="inv-other")
    confirm_email(owner)
    confirm_email(invitee)
    confirm_email(other)
    workspace = _workspace(owner)
    made = owner.post(f"/api/v1/workspaces/{workspace}/invitations", json={"invitee_email": invitee.email, "role": "EDITOR"})
    assert made.status_code == 201, made.text
    invitation = made.json()["invitation"]
    # The API hands out no token now: this stands for one handed out before that.
    token = secrets.token_urlsafe(32)
    with create_engine(DATABASE_URL).begin() as connection:
        connection.execute(text("UPDATE workspace_invitations SET token_hash = :hash WHERE id = :id"), {"hash": hashlib.sha256(token.encode()).hexdigest(), "id": invitation["id"]})

    stored = scalar(db, "SELECT token_hash FROM workspace_invitations WHERE id = :id", id=invitation["id"])
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert scalar(db, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'workspace_invitations' AND column_name = 'token'") == 0

    listed = invitee.get("/api/v1/workspace-invitations/mine").json()["invitations"]
    assert [i["id"] for i in listed] == [invitation["id"]]
    assert other.get("/api/v1/workspace-invitations/mine").json()["invitations"] == []
    assert other.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept").status_code == 404
    assert owner.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept").status_code == 404

    assert invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept").json()["role"] == "EDITOR"
    assert invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept").status_code == 400
    assert invitee.post(f"/api/v1/workspaces/invitations/{token}/accept").status_code == 400
    roles = {m["user_id"]: m["role"] for m in owner.get(f"/api/v1/workspaces/{workspace}/members").json()["items"]}
    assert roles[invitee.id] == "EDITOR"


def test_two_accepts_at_once_join_once(db):
    owner, invitee = register(label="inv-race-owner"), register(label="inv-race")
    confirm_email(invitee)
    workspace = _workspace(owner)
    invitation = owner.post(f"/api/v1/workspaces/{workspace}/invitations", json={"invitee_email": invitee.email, "role": "VIEWER"}).json()["invitation"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(pool.map(lambda _: invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept").status_code, range(4)))
    assert codes.count(200) == 1, codes
    assert all(code in (200, 400) for code in codes), codes
    assert scalar(db, "SELECT count(*) FROM workspace_members WHERE workspace_id = :w AND user_id = :u", w=workspace, u=invitee.id) == 1


def test_an_expired_invitation_is_refused_on_the_real_database(db):
    from sqlalchemy import text

    owner, invitee = register(label="inv-exp-owner"), register(label="inv-exp")
    confirm_email(invitee)
    workspace = _workspace(owner)
    invitation = owner.post(f"/api/v1/workspaces/{workspace}/invitations", json={"invitee_email": invitee.email, "role": "VIEWER"}).json()["invitation"]
    with db.begin() as connection:
        connection.execute(text("UPDATE workspace_invitations SET expires_at = now() - interval '1 day' WHERE id = :id"), {"id": invitation["id"]})
    assert invitee.get("/api/v1/workspace-invitations/mine").json()["invitations"] == []
    refused = invitee.post(f"/api/v1/workspace-invitations/{invitation['id']}/accept")
    assert refused.status_code == 400
    assert "expired" in refused.json()["detail"]


# ── API-01 ───────────────────────────────────────────────────────────────────


def test_first_reads_of_notification_preferences_never_race_into_a_500():
    accounts = [register(label=f"pref-race-{i}") for i in range(5)]
    failures: list[tuple[int, str]] = []

    def ask(args: tuple[Account, str]) -> None:
        account, path = args
        response = httpx.get(f"{API_URL}{path}", headers={"Authorization": f"Bearer {account.token}"}, timeout=60)
        if response.status_code != 200:
            failures.append((response.status_code, path))

    jobs = [(account, path) for account in accounts for path in ["/api/v1/notifications/preferences", "/api/v1/notifications/delivery-status"] * 3]
    assert len(jobs) == 30
    with ThreadPoolExecutor(max_workers=30) as pool:
        list(pool.map(ask, jobs))
    assert failures == []
    for account in accounts:
        assert account.get("/api/v1/notifications/preferences").json()["in_app_enabled"] is True


# ── SEC-03 ───────────────────────────────────────────────────────────────────


def test_an_unverified_faculty_account_cannot_recruit_by_direct_request(demo):
    faculty = register("FACULTY", label="unverified", verified=False)
    assert faculty.user["is_verified"] is False
    refused = faculty.post("/api/v1/postings", json={**POSTING, "title": "A posting nobody verified"})
    assert refused.status_code == 403
    assert "verif" in refused.json()["detail"]

    admin = demo["admin"]
    assert admin.patch(f"/api/v1/admin/users/{faculty.id}", json={"is_verified": True}).status_code == 200
    created = faculty.post("/api/v1/postings", json={**POSTING, "title": "A posting someone verified"})
    assert created.status_code == 201, created.text
    posting = created.json()["id"]
    assert faculty.post(f"/api/v1/postings/{posting}/transition", json={"target_status": "OPEN"}).status_code == 200
    student = register(label="applicant")
    assert request("GET", f"/api/v1/postings/{posting}").status_code == 200

    assert admin.patch(f"/api/v1/admin/users/{faculty.id}", json={"is_verified": False}).status_code == 200
    assert request("GET", f"/api/v1/postings/{posting}").status_code == 404
    assert student.post(f"/api/v1/postings/{posting}/applications", json={"cover_note": "x"}).status_code == 400
    assert faculty.post(f"/api/v1/postings/{posting}/transition", json={"target_status": "CLOSED"}).status_code == 200
    assert faculty.post(f"/api/v1/postings/{posting}/transition", json={"target_status": "OPEN"}).status_code == 403


# ── SEC-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "data:text/html,x", "vbscript:x", "ftp://example.org", "//evil.example", "not a url"])
def test_unsafe_addresses_are_refused_on_create_and_update(value):
    faculty = register("FACULTY", label="urls")
    assert faculty.post("/api/v1/postings", json={**POSTING, "title": "A posting with a link", "external_url": value}).status_code == 422
    posting = faculty.post("/api/v1/postings", json={**POSTING, "title": "A posting with a link", "external_url": "https://lab.example.org"}).json()
    assert posting["external_url"] == "https://lab.example.org"
    assert faculty.patch(f"/api/v1/postings/{posting['id']}", json={"external_url": value}).status_code == 422
    assert faculty.get(f"/api/v1/postings/{posting['id']}").json()["external_url"] == "https://lab.example.org"


# ── SEC-04, API-02 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("suffix", ["", "/works", "/preferences", "/preferences/structured", "/personalized-recommendations", "/feedback", "/notifications", "/calendar", "/supervisor-matches", "/recommendations/unified"])
def test_a_researcher_id_cannot_be_confirmed(suffix):
    owner, other = register(label="sec04-owner"), register(label="sec04-other")
    made_up = uuid.uuid4()
    real = request("GET", f"/api/v1/researchers/{owner.profile_id}{suffix}")
    fake = request("GET", f"/api/v1/researchers/{made_up}{suffix}")
    assert real.status_code == fake.status_code, suffix
    assert real.text == fake.text, suffix
    real = other.get(f"/api/v1/researchers/{owner.profile_id}{suffix}")
    fake = other.get(f"/api/v1/researchers/{made_up}{suffix}")
    assert real.status_code == fake.status_code, suffix
    assert real.text == fake.text, suffix


@pytest.mark.parametrize("query", ["search=%00", "search=a%00b"])
def test_a_nul_in_the_user_search_is_not_a_500(demo, query):
    answer = demo["admin"].get(f"/api/v1/admin/users?{query}")
    assert answer.status_code == 200
    assert answer.json() == {"users": [], "total": 0}


def test_the_user_list_filters_on_active_and_verified(demo):
    admin = demo["admin"]
    student = register(label="filter-gone")
    assert admin.patch(f"/api/v1/admin/users/{student.id}", json={"is_active": False}).status_code == 200
    found = admin.get("/api/v1/admin/users", params={"is_active": "false", "search": student.email}).json()
    assert [u["email"] for u in found["users"]] == [student.email]
    assert admin.get("/api/v1/admin/users", params={"is_active": "true", "search": student.email}).json()["total"] == 0


# ── FUNC-02 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["TODO", "IN_PROGRESS", "REVIEW", "COMPLETED", "CANCELLED"])
def test_every_task_status_the_interface_offers_is_accepted(status):
    owner = register(label="task-status")
    workspace = _workspace(owner)
    assert owner.get(f"/api/v1/workspaces/{workspace}/tasks", params={"status": status}).status_code == 200


def test_the_old_task_status_value_is_refused():
    owner = register(label="task-status-old")
    workspace = _workspace(owner)
    assert owner.get(f"/api/v1/workspaces/{workspace}/tasks", params={"status": "IN_REVIEW"}).status_code == 422
