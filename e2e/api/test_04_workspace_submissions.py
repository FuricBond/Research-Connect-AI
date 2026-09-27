"""
Step 8 — the workspace and submission workflow, with ownership.

Save an opportunity -> notes, tags, priority -> stage transitions (including refused ones)
-> a collaboration task and note -> a submission with documents -> the readiness gate ->
transitions -> the audit trail. Researcher B is refused at every point, and B's own views
never contain A's items.
"""
from __future__ import annotations

import pytest

from conftest import Account, opportunity_by_title, register, rows

VENUE = "International Conference on Information Retrieval Systems"


@pytest.fixture(scope="module")
def owner(demo_seeded) -> Account:
    return register(label="ws-owner", full_name="Wanda Workspace")


@pytest.fixture(scope="module")
def other() -> Account:
    return register(label="ws-other")


@pytest.fixture(scope="module")
def item(owner) -> dict:
    opportunity = opportunity_by_title(VENUE)
    response = owner.post("/api/v1/workspace", json={
        "opportunity_id": opportunity["id"], "priority": "HIGH", "tags": ["phd-year-2"], "notes": "Target venue",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_saving_an_opportunity_creates_a_workspace_item_once(owner, item, db):
    assert item["status"] == "SAVED" and item["opportunity"]["title"] == VENUE
    again = owner.post("/api/v1/workspace", json={"opportunity_id": item["opportunity_id"]})
    assert again.status_code in (200, 201) and again.json()["id"] == item["id"], "saving twice is idempotent"
    listed = owner.get("/api/v1/workspace").json()["items"]
    assert [i["id"] for i in listed] == [item["id"]]
    stored = rows(db, "SELECT status, priority, tags, notes FROM saved_opportunities WHERE id = :id", id=item["id"])
    assert stored == [{"status": "SAVED", "priority": "HIGH", "tags": ["phd-year-2"], "notes": "Target venue"}]


def test_notes_tags_and_priority_update_and_persist(owner, item):
    update = owner.patch(f"/api/v1/workspace/{item['id']}", json={"notes": "Abstract due first", "tags": ["phd-year-2", "ir"], "priority": "URGENT"})
    assert update.status_code == 200, update.text
    reread = owner.get(f"/api/v1/workspace/{item['id']}").json()
    assert (reread["notes"], reread["tags"], reread["priority"]) == ("Abstract due first", ["phd-year-2", "ir"], "URGENT")


def test_stage_transitions_follow_the_state_machine(owner, item):
    path = f"/api/v1/workspace/{item['id']}/transition"
    assert "ACCEPTED" not in item["allowed_transitions"]
    skipped = owner.post(path, json={"target_status": "ACCEPTED"})
    assert skipped.status_code == 400, "an item cannot jump from SAVED to ACCEPTED"
    for target in ("CONSIDERING", "PLANNING"):  # as the workspace page does: no transition notes
        moved = owner.post(path, json={"target_status": target})
        assert moved.status_code == 200, moved.text
        assert moved.json()["status"] == target
    # Pressing "Save" on the same opportunity again (a recommendation card sends only its ID)
    # must not move it back to SAVED or reset its priority (fixed in Phase 6.6).
    again = owner.post("/api/v1/workspace", json={"opportunity_id": item["opportunity_id"]})
    assert again.status_code == 200
    assert (again.json()["status"], again.json()["priority"]) == ("PLANNING", "URGENT")
    summary = owner.get("/api/v1/workspace/summary").json()
    assert summary["counts_by_status"].get("PLANNING") == 1


def test_collaboration_task_and_note_are_recorded_in_the_activity_feed(owner, item):
    workspace = item["id"]
    task = owner.post(f"/api/v1/workspace/{workspace}/tasks", json={"title": "Draft related work", "priority": "HIGH"})
    assert task.status_code in (200, 201), task.text
    assert task.json()["status"] == "TODO" and task.json()["creator_name"] == "Wanda Workspace"
    note = owner.post(f"/api/v1/workspace/{workspace}/comments", json={"comment": "Literature review finished."})
    assert note.status_code in (200, 201), note.text
    tasks = owner.get(f"/api/v1/workspace/{workspace}/tasks").json()
    listed = tasks if isinstance(tasks, list) else tasks.get("items", tasks.get("tasks", []))
    assert any(t["title"] == "Draft related work" for t in listed)
    activity = owner.get(f"/api/v1/workspace/{workspace}/activity").json()
    events = activity if isinstance(activity, list) else activity.get("items", activity.get("activities", []))
    kinds = {e["activity_type"] for e in events}
    assert {"TASK_CREATED"} <= kinds and any("COMMENT" in k for k in kinds), kinds


def test_submission_readiness_gates_the_ready_transition(owner, item):
    created = owner.post("/api/v1/submissions", json={
        "workspace_item_id": item["id"], "title": "Neural ranking for scholarly search", "submission_type": "FULL_PAPER",
    })
    assert created.status_code == 201, created.text
    submission = created.json()
    assert submission["status"] == "DRAFT" and submission["opportunity_title"] == VENUE
    sid = submission["id"]
    document = owner.post(f"/api/v1/submissions/{sid}/documents", json={
        "document_type": "FULL_PAPER", "title": "Full paper v1", "is_required": True, "status": "DRAFT",
    })
    assert document.status_code == 201, document.text
    readiness = owner.get(f"/api/v1/submissions/{sid}/readiness").json()
    assert readiness["can_mark_submission_ready"] is False and readiness["blocking_issues"]
    blocked = owner.post(f"/api/v1/submissions/{sid}/transition", json={"target_status": "READY"})
    assert blocked.status_code == 400, "READY is refused while a required document is not ready"

    ready_doc = owner.patch(f"/api/v1/submissions/{sid}/documents/{document.json()['id']}", json={"status": "READY"})
    assert ready_doc.status_code == 200, ready_doc.text
    assert owner.get(f"/api/v1/submissions/{sid}/readiness").json()["can_mark_submission_ready"] is True
    for target in ("READY", "SUBMITTED"):
        moved = owner.post(f"/api/v1/submissions/{sid}/transition", json={"target_status": target})
        assert moved.status_code == 200, moved.text
        assert moved.json()["status"] == target
    history = owner.get(f"/api/v1/submissions/{sid}/history").json()

    def status_of(state):
        return state.get("status") if isinstance(state, dict) else state

    transitions = [(status_of(e["old_state"]), status_of(e["new_state"])) for e in history["items"]]
    assert ("DRAFT", "READY") in transitions and ("READY", "SUBMITTED") in transitions, history["items"]
    # Submitting promotes the parent workspace item to APPLIED (Phase 4.2 controlled promotion).
    assert owner.get(f"/api/v1/workspace/{item['id']}").json()["status"] == "APPLIED"
    listed = owner.get("/api/v1/submissions").json()["items"]
    assert [s["id"] for s in listed] == [sid]


def test_another_researcher_can_neither_see_nor_change_the_workspace(owner, other, item):
    workspace = item["id"]
    submissions = owner.get("/api/v1/submissions").json()["items"]
    sid = submissions[0]["id"]
    probes = [
        ("GET", f"/api/v1/workspace/{workspace}", None),
        ("PATCH", f"/api/v1/workspace/{workspace}", {"notes": "hijacked"}),
        ("POST", f"/api/v1/workspace/{workspace}/transition", {"target_status": "ARCHIVED"}),
        ("GET", f"/api/v1/workspace/{workspace}/tasks", None),
        ("POST", f"/api/v1/workspace/{workspace}/comments", {"comment": "hijacked"}),
        ("GET", f"/api/v1/submissions/{sid}", None),
        ("POST", f"/api/v1/submissions/{sid}/transition", {"target_status": "WITHDRAWN"}),
        ("DELETE", f"/api/v1/workspace/{workspace}", None),
    ]
    from conftest import request

    for method, path, body in probes:
        response = request(method, path, other.token, json=body)
        assert response.status_code in (403, 404), f"{method} {path} -> {response.status_code}"
        assert "Target venue" not in response.text and "Neural ranking" not in response.text
    assert other.get("/api/v1/workspace").json()["items"] == []
    assert other.get("/api/v1/submissions").json()["items"] == []
    intact = owner.get(f"/api/v1/workspace/{workspace}").json()
    assert intact["notes"] == "Abstract due first" and intact["status"] == "APPLIED"
