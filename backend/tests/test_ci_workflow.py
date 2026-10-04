"""
Fix 8/9 — the CI workflow stays valid and in step with the local commands.

.github/workflows/ci.yml must parse, use no secrets, run the backend against the same pgvector
image as docker-compose.yml with the CPU torch wheel pinned in backend/Dockerfile, and run exactly
the commands that pass locally. The browser end-to-end suite is not part of it.
"""
from __future__ import annotations

from pathlib import Path
import re

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(job: dict) -> list[str]:
    return [step["run"].strip() for step in job["steps"] if "run" in step]


def test_the_workflow_runs_on_push_and_pull_request_without_secrets():
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = _workflow()
    # YAML 1.1 reads a bare `on:` key as True.
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"push", "pull_request"}
    assert workflow["permissions"] == {"contents": "read"}
    assert not re.search(r"\$\{\{\s*secrets\.", text)
    assert set(workflow["jobs"]) == {"backend", "frontend"}


def test_the_backend_job_matches_the_compose_database_and_the_image_dependencies():
    job = _workflow()["jobs"]["backend"]
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    service = job["services"]["postgres"]
    assert service["image"] == compose["services"]["postgres"]["image"]
    assert "--health-cmd" in service["options"]

    assert job["env"]["APP_ENV"] == "test"
    assert job["env"]["DATABASE_URL"].endswith("@localhost:5432/researchconnect")
    assert job["defaults"]["run"]["working-directory"] == "backend"

    dockerfile = (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
    torch_pin = re.search(r"torch==[\d.]+", dockerfile).group(0)
    install, *commands = _runs(job)
    assert install.splitlines() == [
        f"python -m pip install --index-url https://download.pytorch.org/whl/cpu {torch_pin}",
        "python -m pip install -r requirements.txt",
    ]
    assert commands == ["alembic upgrade head", "pytest -q", "pytest ../scrapers/tests -q"]


def test_the_frontend_job_runs_the_local_checks_and_no_browser_suite():
    job = _workflow()["jobs"]["frontend"]
    assert job["defaults"]["run"]["working-directory"] == "frontend"
    setup_node = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/setup-node"))
    assert setup_node["with"]["cache"] == "npm"
    assert _runs(job) == ["npm ci", "npm run type-check", "npm run lint", "npm test", "npm run build"]
    assert "e2e" not in " ".join(_runs(job) + _runs(_workflow()["jobs"]["backend"]))
