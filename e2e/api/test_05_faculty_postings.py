"""
Step 9 — faculty postings: create a draft, publish, update, and walk the lifecycle.

A draft is visible only to its author. Publishing makes it discoverable. DRAFT and OPEN are
reversible while the author decides (OPEN <-> CLOSED too), but FILLED and CANCELLED are
outcomes that lead only to ARCHIVED: a concluded search cannot be reopened under the same
posting. Students cannot author, and one author cannot manage another's posting.
"""
from __future__ import annotations

import pytest

from conftest import Account, register, request

DESCRIPTION = "Build and evaluate neural retrieval models for scholarly search over a large open corpus."


@pytest.fixture(scope="module")
def faculty() -> Account:
    return register("FACULTY", label="faculty", full_name="Prof. Fiona Faculty")


@pytest.fixture(scope="module")
def other_faculty() -> Account:
    return register("FACULTY", label="faculty2")


@pytest.fixture(scope="module")
def student() -> Account:
    return register(label="posting-student")


def _create(faculty: Account, title: str) -> dict:
    response = faculty.post("/api/v1/postings", json={
        "title": title, "posting_type": "PROJECT", "description": DESCRIPTION,
        "summary": "Neural retrieval for scholarly search", "work_mode": "HYBRID",
        "required_skills": ["Python", "Information Retrieval"], "positions_available": 1,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _transition(account: Account, posting_id: str, target: str):
    return account.post(f"/api/v1/postings/{posting_id}/transition", json={"target_status": target})


@pytest.fixture(scope="module")
def posting(faculty) -> dict:
    return _create(faculty, "Neural retrieval for scholarly search")


def test_a_new_posting_is_a_draft_visible_only_to_its_author(faculty, student, posting):
    assert posting["status"] == "DRAFT" and posting["is_owner"] is True
    assert posting["author"]["full_name"] == "Prof. Fiona Faculty"
    assert faculty.get(f"/api/v1/postings/{posting['id']}").status_code == 200
    assert student.get(f"/api/v1/postings/{posting['id']}").status_code == 404
    assert request("GET", f"/api/v1/postings/{posting['id']}").status_code == 404
    public = student.get("/api/v1/postings", params={"limit": 100}).json()["postings"]
    assert posting["id"] not in {p["id"] for p in public}
    mine = faculty.get("/api/v1/postings/mine").json()["postings"]
    assert [p["id"] for p in mine] == [posting["id"]]


def test_publishing_makes_it_discoverable_and_updates_reach_readers(faculty, student, posting):
    published = _transition(faculty, posting["id"], "OPEN")
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "OPEN" and published.json()["published_at"]
    seen = student.get(f"/api/v1/postings/{posting['id']}")
    assert seen.status_code == 200 and seen.json()["is_owner"] is False
    assert posting["id"] in {p["id"] for p in student.get("/api/v1/postings", params={"limit": 100}).json()["postings"]}

    updated = faculty.patch(f"/api/v1/postings/{posting['id']}", json={"title": "Neural retrieval for scholarly search (2027)"})
    assert updated.status_code == 200, updated.text
    assert student.get(f"/api/v1/postings/{posting['id']}").json()["title"] == "Neural retrieval for scholarly search (2027)"


def test_the_lifecycle_allows_reconsidering_but_not_reopening_a_concluded_search(faculty, posting):
    pid = posting["id"]
    assert _transition(faculty, pid, "CLOSED").json()["status"] == "CLOSED"
    assert _transition(faculty, pid, "OPEN").json()["status"] == "OPEN", "CLOSED can reopen"
    filled = _transition(faculty, pid, "FILLED")
    assert filled.status_code == 200 and filled.json()["allowed_transitions"] == ["ARCHIVED"]
    for target in ("OPEN", "CLOSED", "DRAFT"):
        assert _transition(faculty, pid, target).status_code == 400, f"FILLED -> {target} must be refused"
    archived = _transition(faculty, pid, "ARCHIVED")
    assert archived.status_code == 200 and archived.json()["allowed_transitions"] == []
    assert _transition(faculty, pid, "OPEN").status_code == 400

    cancelled = _create(faculty, "Cancelled rotation")
    assert _transition(faculty, cancelled["id"], "OPEN").status_code == 200
    assert _transition(faculty, cancelled["id"], "CANCELLED").status_code == 200
    assert _transition(faculty, cancelled["id"], "OPEN").status_code == 400, "a cancelled posting cannot reopen"


def test_students_cannot_author_and_authors_cannot_manage_each_others_postings(faculty, other_faculty, student):
    created = student.post("/api/v1/postings", json={
        "title": "Student-authored posting", "posting_type": "PROJECT", "description": DESCRIPTION,
    })
    assert created.status_code == 403, created.text
    target = _create(faculty, "Owned by the first author")
    assert other_faculty.patch(f"/api/v1/postings/{target['id']}", json={"title": "Taken over"}).status_code in (403, 404)
    assert _transition(other_faculty, target["id"], "OPEN").status_code in (403, 404)
    assert other_faculty.delete(f"/api/v1/postings/{target['id']}").status_code in (403, 404)
    assert faculty.get(f"/api/v1/postings/{target['id']}").json()["title"] == "Owned by the first author"
    # Only drafts can be deleted, and only by their author.
    assert faculty.delete(f"/api/v1/postings/{target['id']}").status_code == 204
    assert faculty.get(f"/api/v1/postings/{target['id']}").status_code == 404
