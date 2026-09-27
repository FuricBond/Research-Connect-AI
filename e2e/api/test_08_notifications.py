"""
Step 12 — notifications: preferences, reminder rules, generation, read state.

A researcher tracks an opportunity whose deadline is five days away. The reminder pass
(triggered here by an administrator, as the scheduler does on its own in test_90) creates
the due reminders once: repeating the pass adds nothing. The researcher reads one, then
all. A researcher who turned deadline reminders off gets none. Only an administrator may
trigger the pass, and nobody reads another researcher's notifications.
"""
from __future__ import annotations

import pytest

from conftest import Account, observe, opportunity_by_title, register, rows

SOON = "Workshop on Research Data Management"  # seeded five days before its deadline


@pytest.fixture(scope="module")
def tracker(demo_seeded) -> Account:
    account = register(label="tracker")
    saved = account.post("/api/v1/workspace", json={"opportunity_id": opportunity_by_title(SOON)["id"]})
    assert saved.status_code == 201, saved.text
    return account


@pytest.fixture(scope="module")
def muted(demo_seeded) -> Account:
    account = register(label="muted")
    off = account.patch("/api/v1/notifications/preferences", json={"deadline_reminders_enabled": False})
    assert off.status_code == 200 and off.json()["deadline_reminders_enabled"] is False
    saved = account.post("/api/v1/workspace", json={"opportunity_id": opportunity_by_title(SOON)["id"]})
    assert saved.status_code == 201
    return account


def _mine(account: Account, **params) -> dict:
    response = account.get("/api/v1/notifications", params={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()


def _reminders_for(account: Account, opportunity_id: str) -> list[dict]:
    return [n for n in _mine(account)["notifications"] if n["opportunity_id"] == opportunity_id]


def test_preferences_and_reminder_rules_persist(tracker):
    prefs = tracker.patch("/api/v1/notifications/preferences", json={"email_enabled": False, "in_app_enabled": True})
    assert prefs.status_code == 200, prefs.text
    reread = tracker.get("/api/v1/notifications/preferences").json()
    assert reread["email_enabled"] is False and reread["in_app_enabled"] is True
    rule = tracker.post("/api/v1/notifications/rules", json={"offset_amount": 2, "offset_unit": "DAYS", "delivery_channel": "IN_APP"})
    assert rule.status_code == 201, rule.text
    rules = tracker.get("/api/v1/notifications/rules").json()
    listed = rules if isinstance(rules, list) else rules.get("rules", rules.get("items", []))
    assert rule.json()["id"] in {r["id"] for r in listed}
    paused = tracker.patch(f"/api/v1/notifications/rules/{rule.json()['id']}", json={"is_active": False})
    assert paused.status_code == 200 and paused.json()["is_active"] is False
    assert tracker.delete(f"/api/v1/notifications/rules/{rule.json()['id']}").status_code in (200, 204)


def test_only_an_administrator_can_run_the_reminder_pass(tracker, demo):
    assert tracker.post("/api/v1/notifications/trigger-reminders").status_code == 403
    assert demo["faculty"].post("/api/v1/notifications/trigger-reminders").status_code == 403


def test_the_reminder_pass_notifies_once_and_honours_preferences(tracker, muted, demo, db):
    opportunity = opportunity_by_title(SOON)["id"]
    first = demo["admin"].post("/api/v1/notifications/trigger-reminders")
    assert first.status_code == 200, first.text
    reminders = _reminders_for(tracker, opportunity)
    assert reminders, "a tracked deadline five days out is inside the 7- and 14-day default rules"
    assert all(n["notification_type"] == "DEADLINE_UPCOMING" or "DEADLINE" in n["notification_type"] for n in reminders)
    assert all(n["read_at"] is None and n["delivery_status"] in ("DELIVERED", "PENDING", "SENT") for n in reminders)

    second = demo["admin"].post("/api/v1/notifications/trigger-reminders")
    assert second.status_code == 200
    assert len(_reminders_for(tracker, opportunity)) == len(reminders), "a repeated pass creates no duplicates"
    keys = [r["deduplication_key"] for r in rows(db, "SELECT deduplication_key FROM notifications WHERE profile_id = :p", p=tracker.profile_id)]
    assert len(keys) == len(set(keys))
    assert _reminders_for(muted, opportunity) == [], "deadline reminders switched off: none created"
    observe("reminder_pass", {"first": first.json(), "second": second.json(), "tracker_reminders": len(reminders)})


def test_read_and_mark_all_read_change_the_unread_count(tracker):
    before = tracker.get("/api/v1/notifications/unread-count").json()
    unread = before["unread_count"] if isinstance(before, dict) else before
    assert unread >= 1
    target = _mine(tracker, unread_only=True)["notifications"][0]
    read = tracker.post(f"/api/v1/notifications/{target['id']}/read")
    assert read.status_code == 200 and read.json()["read_at"] is not None
    after = tracker.get("/api/v1/notifications/unread-count").json()
    assert (after["unread_count"] if isinstance(after, dict) else after) == unread - 1
    assert tracker.post("/api/v1/notifications/read-all").status_code == 200
    assert _mine(tracker)["unread_count"] == 0
    # The API has no separate dismissal: notifications are read, individually or all at once.
    observe("notification_dismissal", "not implemented: read and mark-all-read only")


def test_nobody_reads_or_changes_another_researchers_notifications(tracker):
    stranger = register(label="stranger")
    theirs = _mine(tracker)["notifications"][0]
    assert stranger.post(f"/api/v1/notifications/{theirs['id']}/read").status_code in (403, 404)
    assert stranger.get(f"/api/v1/researchers/{tracker.profile_id}/notifications").status_code == 403
    assert _mine(stranger)["notifications"] == []
