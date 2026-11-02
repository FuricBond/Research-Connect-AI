"""
On the running stack: an administrator has no personal research workflow through the API, and no request
can make the server load the cross-encoder.
"""
from __future__ import annotations

import uuid

from conftest import compose, register, request


def test_an_administrator_is_refused_by_personal_research_routes(demo):
    admin = demo["admin"]
    profile = admin.profile_id
    for method, path in [
        ("get", "/api/v1/reading-list"),
        ("get", "/api/reading-list"),
        ("get", "/api/v1/submissions"),
        ("get", "/api/v1/workspace"),
        ("get", "/api/v1/calendar"),
        ("get", "/api/v1/workspace-invitations/mine"),
        ("get", "/api/v1/postings/applications/mine"),
        ("get", "/api/v1/postings/applications/mine/summary"),
        ("get", f"/api/v1/researchers/{profile}"),
        ("get", f"/api/v1/researchers/{profile}/preferences"),
        ("get", f"/api/v1/researchers/{uuid.uuid4()}/preferences"),
    ]:
        answer = getattr(admin, method)(path)
        assert answer.status_code == 403, (path, answer.status_code, answer.text[:200])
        assert "FACULTY, STUDENT" in answer.json()["detail"], path


def test_an_administrator_cannot_apply_and_a_student_can(demo):
    # Accounts of its own: other suites count what the seeded faculty member and student have.
    admin, faculty, student = demo["admin"], register("FACULTY"), register("STUDENT")
    made = faculty.post(
        "/api/v1/postings",
        json={
            "title": f"Assistant {uuid.uuid4().hex[:8]}",
            "posting_type": "RESEARCH_ASSISTANTSHIP",
            "description": "Work on evaluation methods with the group for a semester.",
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
        },
    )
    assert made.status_code == 201, made.text
    posting = made.json()["id"]
    assert faculty.post(f"/api/v1/postings/{posting}/transition", json={"target_status": "OPEN"}).status_code == 200

    assert admin.post(f"/api/v1/postings/{posting}/applications", json={"cover_note": "No"}).status_code == 403
    assert len(faculty.get(f"/api/v1/postings/{posting}/applications").json()["applications"]) == 0
    assert student.post(f"/api/v1/postings/{posting}/applications", json={"cover_note": "Yes"}).status_code == 201


def test_an_administrator_keeps_platform_administration(demo):
    admin = demo["admin"]
    assert admin.get("/api/v1/admin/users?limit=1").status_code == 200
    assert admin.get("/api/v1/admin/ingestion-runs").status_code == 200
    assert admin.get("/api/v1/notifications/unread-count").status_code == 200


def test_a_request_cannot_start_the_reranker(demo):
    query = f"retrieval evaluation {uuid.uuid4().hex[:6]}"
    forced = request("GET", "/api/v1/discovery/research/search", params={"q": query, "rerank": "true", "explain": "true"})
    plain = request("GET", "/api/v1/discovery/research/search", params={"q": query, "explain": "true"})
    assert forced.status_code == plain.status_code == 200
    assert [i["final_score"] for i in forced.json()["items"]] == [i["final_score"] for i in plain.json()["items"]]
    assert not any(i["explanation"]["reranker_explanation"]["enabled"] for i in forced.json()["items"])
    assert not any(i["explanation"]["reranker_explanation"]["applied"] for i in forced.json()["items"])
    logs = compose("logs", "--no-color", "backend").stdout
    assert "Initializing CrossEncoder" not in logs
