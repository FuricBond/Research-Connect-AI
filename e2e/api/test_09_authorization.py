"""
Step 14 — representative authorization boundaries across roles, over real bearer tokens.

Not the Phase 6.7 audit: a matrix of the boundaries the workflows depend on, with a positive
control for each role so a refusal cannot come from a broken request. Reviewer-note privacy
and peer consent are covered in test_06 and test_07.
"""
from __future__ import annotations

import pytest

from conftest import Account, opportunity_by_title, register, request


@pytest.fixture(scope="module")
def actors(demo) -> dict[str, Account]:
    a, b = register(label="authz-a"), register(label="authz-b")
    item = a.post("/api/v1/workspace", json={"opportunity_id": opportunity_by_title("Conference on Applied Machine Learning")["id"]})
    assert item.status_code == 201
    a.user["workspace_item"] = item.json()["id"]
    return {"a": a, "b": b, "faculty": demo["faculty"], "admin": demo["admin"]}


def _status(account: Account, method: str, path: str, body=None) -> int:
    return request(method, path, account.token, json=body).status_code


def test_positive_controls(actors):
    a, faculty, admin = actors["a"], actors["faculty"], actors["admin"]
    assert _status(a, "GET", f"/api/v1/researchers/{a.profile_id}/preferences") == 200
    assert _status(a, "GET", f"/api/v1/workspace/{a.user['workspace_item']}") == 200
    assert _status(faculty, "GET", "/api/v1/postings/mine") == 200
    assert _status(admin, "GET", "/api/v1/admin/users") == 200


@pytest.mark.parametrize("method, path, body", [
    ("GET", "/api/v1/researchers/{a_profile}", None),
    ("PATCH", "/api/v1/researchers/{a_profile}", {"bio": "changed by someone else"}),
    ("GET", "/api/v1/researchers/{a_profile}/preferences", None),
    ("GET", "/api/v1/researchers/{a_profile}/preferences/structured", None),
    ("GET", "/api/v1/researchers/{a_profile}/recommendations/unified", None),
    ("GET", "/api/v1/researchers/{a_profile}/interactions/summary", None),
    ("GET", "/api/v1/researchers/{a_profile}/personalization/settings", None),
    ("GET", "/api/v1/researchers/{a_profile}/notifications", None),
    ("GET", "/api/v1/researchers/{a_profile}/calendar", None),
    ("GET", "/api/v1/workspace/{a_item}", None),
    ("POST", "/api/v1/workspace/{a_item}/archive", None),
])
def test_researcher_b_cannot_reach_researcher_as_private_data(actors, method, path, body):
    a, b = actors["a"], actors["b"]
    url = path.format(a_profile=a.profile_id, a_item=a.user["workspace_item"])
    assert _status(b, method, url, body) in (403, 404), f"{method} {url}"


@pytest.mark.parametrize("role", ["a", "b"])
def test_researchers_cannot_use_faculty_or_admin_operations(actors, role):
    researcher = actors[role]
    posting = {"title": "Not a faculty member", "posting_type": "PROJECT",
               "description": "A posting a student account must not be able to publish."}
    assert _status(researcher, "POST", "/api/v1/postings", posting) == 403
    assert _status(researcher, "GET", "/api/v1/admin/users") == 403
    assert _status(researcher, "PATCH", f"/api/v1/admin/users/{researcher.id}", {"role": "ADMIN"}) == 403
    assert _status(researcher, "POST", "/api/v1/notifications/trigger-reminders") == 403
    assert researcher.get("/api/v1/auth/me").json()["role"] == "STUDENT", "no self-promotion"


def test_faculty_cannot_use_admin_operations(actors):
    faculty = actors["faculty"]
    assert _status(faculty, "GET", "/api/v1/admin/users") == 403
    assert _status(faculty, "PATCH", f"/api/v1/admin/users/{faculty.id}", {"role": "ADMIN"}) == 403
    assert _status(faculty, "PATCH", f"/api/v1/admin/users/{actors['a'].id}", {"is_active": False}) == 403
    assert actors["a"].get("/api/v1/auth/me").status_code == 200


def test_faculty_cannot_reach_a_researchers_private_workspace(actors):
    faculty, a = actors["faculty"], actors["a"]
    assert _status(faculty, "GET", f"/api/v1/workspace/{a.user['workspace_item']}") in (403, 404)
    assert _status(faculty, "GET", f"/api/v1/researchers/{a.profile_id}/preferences") == 403
