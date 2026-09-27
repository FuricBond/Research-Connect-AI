"""
Step 13 — the Phase 6.3 scheduler running inside the deployed backend.

Work is prepared for each production job, then the backend is recreated with
compose.e2e-scheduler.yml (SCHEDULER_ENABLED=true, 60 s intervals). After every job has run
twice, the test checks what each one did to the database, that the second runs changed
nothing, that no job ever overlapped itself, and that the API stayed responsive meanwhile.
The backend is then recreated with the scheduler off again, as production ships it.

Jobs covered: deadline_expiry, reminder_dispatch, adaptive_signal_refresh,
governance_refresh. opportunity_refresh (WikiCFP) is opt-in and depends on an external
website, so it is not run here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import time
import uuid

import pytest
from sqlalchemy.orm import Session

from conftest import (
    SCHEDULER_FILE,
    compose,
    observe,
    opportunity_by_title,
    register,
    request,
    rows,
    scalar,
    wait_ready,
)

pytestmark = pytest.mark.stack

JOBS = ("deadline_expiry", "reminder_dispatch", "adaptive_signal_refresh", "governance_refresh")
RUN_LINE = re.compile(r"Scheduled job (\w+) run ([0-9a-f-]{36}) (\w+) in ([\d.]+)s \(records=(\d+), failed items=(\d+)\)")
START_LINE = re.compile(r"Scheduled job (\w+) run ([0-9a-f-]{36}) started")
REMINDED = "Workshop on Neural Retrieval Methods"  # twelve days out: inside the 14-day rule


def _backend_logs(since: str) -> str:
    return compose("logs", "--no-color", "--no-log-prefix", "--since", since, "backend", check=False).stdout


@pytest.fixture(scope="module")
def prepared(db, demo_seeded) -> dict:
    from app.models.opportunity import OpportunityModel

    past_id = uuid.uuid4()
    past = OpportunityModel(
        id=past_id, title=f"E2E past-deadline call {uuid.uuid4().hex[:6]}", opportunity_type="CONFERENCE",
        delivery_mode="ONLINE", status="ACTIVE", publisher="E2E",
        submission_deadline=datetime.now(timezone.utc) - timedelta(days=1),
    )
    with Session(db) as session:
        session.add(past)
        session.commit()
    researcher = register(label="scheduled")
    ids = {o: opportunity_by_title(o)["id"] for o in (REMINDED, "International Conference on Information Retrieval Systems")}
    assert researcher.post("/api/v1/workspace", json={"opportunity_id": ids[REMINDED]}).status_code == 201
    for title in ids:
        r = researcher.post(f"/api/v1/researchers/{researcher.profile_id}/opportunities/{ids[title]}/interactions",
                            json={"interaction_type": "INTERESTED", "source": "RECOMMENDATION"})
        assert r.status_code == 201
    # Nothing has processed this work yet.
    assert scalar(db, "SELECT status FROM opportunities WHERE id = :id", id=past_id) == "ACTIVE"
    assert researcher.get("/api/v1/notifications").json()["notifications"] == []
    assert researcher.get(f"/api/v1/researchers/{researcher.profile_id}/adaptive-signals").json()["total_count"] == 0
    return {"past_id": str(past_id), "researcher": researcher, "reminded_id": ids[REMINDED]}


def test_scheduled_jobs_do_their_work_once_without_overlap(prepared, db):
    since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    compose("up", "-d", "--wait", "backend", files=(SCHEDULER_FILE,))
    try:
        wait_ready()
        # First runs at +60/75/90/105 s, second runs 60 s later: wait for two of each.
        deadline, runs, latencies = time.monotonic() + 330, [], []
        while time.monotonic() < deadline:
            logs = _backend_logs(since)
            runs = RUN_LINE.findall(logs)
            done = {job: sum(1 for r in runs if r[0] == job) for job in JOBS}
            t = time.monotonic()
            assert request("GET", "/api/opportunities", params={"page_size": 20}).status_code == 200
            latencies.append(time.monotonic() - t)
            if all(count >= 2 for count in done.values()):
                break
            time.sleep(5)
        logs = _backend_logs(since)
        runs = RUN_LINE.findall(logs)
        starts = START_LINE.findall(logs)
    finally:
        compose("up", "-d", "--wait", "backend")  # back to the production default: scheduler off
        wait_ready()

    assert "Scheduler started with 4 job(s)" in logs, logs[-2000:]
    by_job = {job: [r for r in runs if r[0] == job] for job in JOBS}
    assert all(len(v) >= 2 for v in by_job.values()), {j: len(v) for j, v in by_job.items()}
    statuses = {r[2] for r in runs}
    assert statuses <= {"SUCCEEDED"}, [r for r in runs if r[2] != "SUCCEEDED"]
    # No overlap: every run finished before the next run of the same job started.
    order = [(m.start(), "start", m.group(1), m.group(2)) for m in START_LINE.finditer(logs)]
    order += [(m.start(), "end", m.group(1), m.group(2)) for m in RUN_LINE.finditer(logs)]
    open_runs: dict[str, str] = {}
    for _, kind, job, run_id in sorted(order):
        if kind == "start":
            assert job not in open_runs, f"{job} started while run {open_runs[job]} was still running"
            open_runs[job] = run_id
        else:
            open_runs.pop(job, None)

    # deadline_expiry: the past-deadline call is EXPIRED, once.
    assert scalar(db, "SELECT status FROM opportunities WHERE id = :id", id=prepared["past_id"]) == "EXPIRED"
    expiry = by_job["deadline_expiry"]
    assert int(expiry[0][4]) >= 1 and all(int(r[4]) == 0 for r in expiry[1:]), expiry

    # reminder_dispatch: the tracked deadline produced reminders, and the second run none.
    researcher = prepared["researcher"]
    reminders = [n for n in researcher.get("/api/v1/notifications").json()["notifications"]
                 if n["opportunity_id"] == prepared["reminded_id"]]
    assert reminders, "the scheduled reminder pass notified the researcher"
    dispatch = by_job["reminder_dispatch"]
    assert int(dispatch[0][4]) >= 1 and all(int(r[4]) == 0 for r in dispatch[1:]), dispatch

    # adaptive_signal_refresh: the researcher's interactions became signals without a request.
    signals = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/adaptive-signals").json()
    assert signals["total_count"] > 0
    assert int(by_job["adaptive_signal_refresh"][0][4]) >= 1
    # governance_refresh ran over the same researchers and left a current evaluation.
    governance = researcher.get(f"/api/v1/researchers/{researcher.profile_id}/personalization/governance").json()
    assert governance["total_count"] >= 1

    observe("scheduler", {
        "runs": {job: [{"status": r[2], "seconds": float(r[3]), "records": int(r[4])} for r in v] for job, v in by_job.items()},
        "api_latency_during_jobs_seconds": {"max": round(max(latencies), 3), "samples": len(latencies)},
    })
    assert max(latencies) < 5, "the API stays responsive while jobs run"


def test_the_scheduler_is_off_again_after_the_stage(db):
    logs = compose("logs", "--no-color", "--no-log-prefix", "--since", "30s", "backend", check=False).stdout
    assert "Scheduler started" not in logs
    assert wait_ready()["schema"] == "current"
