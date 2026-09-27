"""
Step 10 — the application workflow between two real identities.

Faculty publishes an assistantship that accepts applications -> a researcher finds it and
applies -> a duplicate is refused -> the author sees the application and is notified ->
the author reviews it with a private note and moves it through the process -> the
applicant sees each new status, is notified, and never sees the reviewer note -> the
applicant withdraws and may re-apply. Neither party can act for the other, and a third
researcher sees nothing.
"""
from __future__ import annotations

import pytest

from conftest import Account, register, rows

REVIEWER_NOTE = "Strong Python; ask about evaluation experience. PRIVATE-E2E-NOTE"


@pytest.fixture(scope="module")
def author() -> Account:
    return register("FACULTY", label="author", full_name="Dr. Arun Author")


@pytest.fixture(scope="module")
def applicant() -> Account:
    return register(label="applicant", full_name="Ada Applicant")


@pytest.fixture(scope="module")
def bystander() -> Account:
    return register(label="bystander")


@pytest.fixture(scope="module")
def opening(author) -> dict:
    created = author.post("/api/v1/postings", json={
        "title": "Research assistantship in retrieval evaluation", "posting_type": "RESEARCH_ASSISTANTSHIP",
        "description": "Help build reproducible retrieval benchmarks and run evaluation campaigns.",
        "work_mode": "REMOTE", "positions_available": 1,
        "opening_terms": {"accepts_applications": True, "compensation_type": "STIPEND", "compensation_amount": 1500,
                          "compensation_currency": "USD", "compensation_period": "MONTH",
                          "commitment_type": "PART_TIME", "hours_per_week": 15, "duration_months": 6},
    })
    assert created.status_code == 201, created.text
    opened = author.post(f"/api/v1/postings/{created.json()['id']}/transition", json={"target_status": "OPEN"})
    assert opened.status_code == 200, opened.text
    assert opened.json()["is_accepting_applications"] is True
    return opened.json()


@pytest.fixture(scope="module")
def application(applicant, opening) -> dict:
    listed = applicant.get("/api/v1/postings", params={"limit": 100}).json()["postings"]
    assert opening["id"] in {p["id"] for p in listed}, "the researcher discovers the opening"
    applied = applicant.post(f"/api/v1/postings/{opening['id']}/applications", json={
        "cover_note": "I build IR evaluation pipelines.", "contact_email": applicant.email,
        "portfolio_url": "https://example.test/ada",
    })
    assert applied.status_code == 201, applied.text
    return applied.json()


def _notifications(account: Account) -> list[dict]:
    response = account.get("/api/v1/notifications", params={"limit": 100})
    assert response.status_code == 200, response.text
    return response.json()["notifications"]


def test_the_researcher_applies_once(applicant, opening, application):
    assert application["status"] == "SUBMITTED" and application["is_applicant"] is True
    assert application["posting_id"] == opening["id"]
    again = applicant.post(f"/api/v1/postings/{opening['id']}/applications", json={"cover_note": "again"})
    assert again.status_code == 409, "one application per researcher per opening"
    mine = applicant.get("/api/v1/postings/applications/mine").json()
    listed = mine["applications"] if isinstance(mine, dict) else mine
    assert [a["id"] for a in listed] == [application["id"]]
    detail = applicant.get(f"/api/v1/postings/{opening['id']}").json()
    assert detail["viewer_application_id"] == application["id"]


def test_the_author_sees_the_application_and_is_notified(author, opening, application):
    received = author.get(f"/api/v1/postings/{opening['id']}/applications").json()["applications"]
    assert [a["id"] for a in received] == [application["id"]]
    assert received[0]["applicant"]["full_name"] == "Ada Applicant" and received[0]["is_posting_author"] is True
    assert any(n["source_id"] == application["id"] or opening["title"] in n["title"] + (n["body"] or "")
               for n in _notifications(author)), "the author is told about the new application"


def test_review_moves_the_application_and_keeps_the_note_private(author, applicant, application, db):
    path = f"/api/v1/postings/applications/{application['id']}/transition"
    # The applicant cannot take the author's decisions.
    assert applicant.post(path, json={"target_status": "SHORTLISTED"}).status_code in (400, 403)
    reviewed = author.post(path, json={"target_status": "UNDER_REVIEW", "reviewer_note": REVIEWER_NOTE})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["reviewer_note"] == REVIEWER_NOTE, "the author reads their own note"
    shortlisted = author.post(path, json={"target_status": "SHORTLISTED", "decision_reason": "Strong fit"})
    assert shortlisted.status_code == 200 and shortlisted.json()["status"] == "SHORTLISTED"
    assert rows(db, "SELECT reviewer_note FROM research_posting_applications WHERE id = :id",
                id=application["id"]) == [{"reviewer_note": REVIEWER_NOTE}]

    seen = applicant.get(f"/api/v1/postings/applications/{application['id']}")
    assert seen.status_code == 200 and seen.json()["status"] == "SHORTLISTED"
    for response in (seen, applicant.get("/api/v1/postings/applications/mine"),
                     applicant.get(f"/api/v1/postings/{application['posting_id']}")):
        assert "PRIVATE-E2E-NOTE" not in response.text, "the reviewer note never reaches the applicant"
    assert seen.json()["reviewer_note"] is None
    history = [h.get("to_status") or h.get("status") for h in seen.json()["status_history"]]
    assert {"UNDER_REVIEW", "SHORTLISTED"} <= set(history), seen.json()["status_history"]
    notes = [n for n in _notifications(applicant) if n["source_id"] == application["id"] or "SHORTLISTED" in (n["title"] + (n["body"] or "")).upper()]
    assert notes, "the applicant is notified of the new status"
    assert all("PRIVATE-E2E-NOTE" not in (n["title"] + (n["body"] or "")) for n in _notifications(applicant))


def test_a_third_researcher_sees_nothing_and_cannot_act(bystander, opening, application):
    assert bystander.get(f"/api/v1/postings/applications/{application['id']}").status_code in (403, 404)
    assert bystander.get(f"/api/v1/postings/{opening['id']}/applications").status_code in (403, 404)
    move = bystander.post(f"/api/v1/postings/applications/{application['id']}/transition", json={"target_status": "WITHDRAWN"})
    assert move.status_code in (403, 404)


def test_withdrawal_ends_the_process_and_re_application_reuses_it(applicant, author, opening, application):
    path = f"/api/v1/postings/applications/{application['id']}/transition"
    withdrawn = applicant.post(path, json={"target_status": "WITHDRAWN"})
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "WITHDRAWN"
    assert author.post(path, json={"target_status": "OFFERED"}).status_code == 400, "a withdrawn application is final"
    again = applicant.post(f"/api/v1/postings/{opening['id']}/applications", json={"cover_note": "Re-applying"})
    assert again.status_code == 201, again.text
    assert again.json()["id"] == application["id"] and again.json()["status"] == "SUBMITTED"
