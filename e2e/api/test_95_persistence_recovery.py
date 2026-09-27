"""
Steps 17–18 — data persists across restarts, and the stack recovers as documented.

A researcher and a faculty member create data across the workflows; then the backend, the
frontend and PostgreSQL are restarted in turn, and finally the whole stack goes down and
up again with its volume kept. After each step everything is read back unchanged through
the API, and the issued bearer tokens still work (the signing key is configuration, not
process state).
"""
from __future__ import annotations

import time

import httpx
import pytest

from conftest import WEB_URL, Account, compose, opportunity_by_title, register, wait_ready

pytestmark = pytest.mark.stack


@pytest.fixture(scope="module")
def world(demo_seeded) -> dict:
    researcher = register(label="durable", full_name="Dora Durable")
    faculty = register("FACULTY", label="durable-fac")
    assert researcher.patch(f"/api/v1/researchers/{researcher.profile_id}", json={"bio": "Studies durable storage."}).status_code == 200
    item = researcher.post("/api/v1/workspace", json={
        "opportunity_id": opportunity_by_title("Conference on Natural Language Understanding")["id"],
        "priority": "HIGH", "notes": "Persist me"}).json()
    submission = researcher.post("/api/v1/submissions", json={
        "workspace_item_id": item["id"], "title": "Durable retrieval", "submission_type": "SHORT_PAPER"}).json()
    posting = faculty.post("/api/v1/postings", json={
        "title": "Durable lab rotation", "posting_type": "LAB_ROTATION",
        "description": "A rotation that must survive every restart of the platform."}).json()
    prefs = researcher.patch("/api/v1/notifications/preferences", json={"email_enabled": False})
    assert prefs.status_code == 200
    return {"researcher": researcher, "faculty": faculty, "item": item["id"],
            "submission": submission["id"], "posting": posting["id"]}


def _snapshot(world: dict) -> dict:
    r: Account = world["researcher"]
    f: Account = world["faculty"]
    item = r.get(f"/api/v1/workspace/{world['item']}").json()
    return {
        "bio": r.get(f"/api/v1/researchers/{r.profile_id}").json()["bio"],
        "item": (item["priority"], item["notes"], item["status"]),
        "submission": r.get(f"/api/v1/submissions/{world['submission']}").json()["title"],
        "posting": f.get(f"/api/v1/postings/{world['posting']}").json()["title"],
        "email_enabled": r.get("/api/v1/notifications/preferences").json()["email_enabled"],
    }


EXPECTED = {
    "bio": "Studies durable storage.",
    "item": ("HIGH", "Persist me", "SAVED"),
    "submission": "Durable retrieval",
    "posting": "Durable lab rotation",
    "email_enabled": False,
}


def _web_ok() -> bool:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{WEB_URL}/login", timeout=5).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2)
    return False


def test_data_is_written(world):
    assert _snapshot(world) == EXPECTED


def test_backend_restart_keeps_data_and_sessions(world):
    compose("restart", "backend")
    wait_ready()
    assert _snapshot(world) == EXPECTED


def test_frontend_restart_serves_again(world):
    compose("restart", "frontend")
    assert _web_ok()
    assert _snapshot(world) == EXPECTED


def test_database_restart_is_recovered_without_restarting_the_backend(world):
    compose("restart", "postgres")
    ready = wait_ready(timeout=120)  # the pool re-validates connections (pool_pre_ping)
    assert ready["schema"] == "current"
    assert _snapshot(world) == EXPECTED


def test_full_down_and_up_keeps_the_volume_and_applies_no_migrations(world):
    compose("down")
    started = time.monotonic()
    compose("up", "-d", "--wait", timeout=600)
    wait_ready()
    elapsed = time.monotonic() - started
    migrate_log = compose("logs", "--no-color", "--no-log-prefix", "migrate", check=False).stdout
    assert "Running upgrade" not in migrate_log, "an existing database is already at head"
    assert _web_ok()
    assert _snapshot(world) == EXPECTED
    restarts = compose("ps", "-a", "--format", "{{.Service}} {{.Status}}", check=False).stdout
    assert "Restarting" not in restarts, restarts
    from conftest import observe

    observe("full_restart_seconds", round(elapsed, 1))
