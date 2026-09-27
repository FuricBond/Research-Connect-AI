"""
Shared fixtures for the Phase 6.6 API end-to-end suite.

Everything here talks to a running stack started by e2e/run_e2e.py: HTTP to the backend's
published port with real bearer tokens, SQL to its PostgreSQL for state checks, and
`docker compose` for stack operations (seeding, restarts). Nothing is mocked and no
development identity is used: the stack runs with APP_ENV=production.

Configuration comes from the environment run_e2e.py sets:
    E2E_API_URL, E2E_WEB_URL, E2E_DATABASE_URL, E2E_DEMO_PASSWORD, E2E_COMPOSE,
    E2E_COMPOSE_SCHEDULER_FILE, E2E_RESULTS_DIR
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

REQUIRED = ("E2E_API_URL", "E2E_DATABASE_URL", "E2E_DEMO_PASSWORD", "E2E_COMPOSE")
_missing = [name for name in REQUIRED if not os.environ.get(name)]
if _missing:
    raise pytest.UsageError(
        f"The E2E suite runs against a live stack; start it with `python e2e/run_e2e.py` "
        f"(missing {', '.join(_missing)})."
    )

API_URL = os.environ["E2E_API_URL"].rstrip("/")
WEB_URL = os.environ.get("E2E_WEB_URL", "").rstrip("/")
DATABASE_URL = os.environ["E2E_DATABASE_URL"]
DEMO_PASSWORD = os.environ["E2E_DEMO_PASSWORD"]
COMPOSE = json.loads(os.environ["E2E_COMPOSE"])
SCHEDULER_FILE = os.environ.get("E2E_COMPOSE_SCHEDULER_FILE", "")
RESULTS_DIR = Path(os.environ.get("E2E_RESULTS_DIR", "."))
REPO = Path(__file__).resolve().parents[2]

DEMO_EMAILS = {
    "faculty": "demo.faculty@researchconnect.test",
    "student": "demo.student@researchconnect.test",
    "admin": "demo.admin@researchconnect.test",
}

# The backend's ORM models seed the literature corpus (never app settings or services).
sys.path.insert(0, str(REPO / "backend"))


# ── Secrets the suite handles, recorded so the log scan can prove none leaked ──

_SECRETS_FILE = RESULTS_DIR / "suite_secrets.txt"
_secrets_lock = threading.Lock()


def remember_secret(value: str) -> str:
    if value:
        with _secrets_lock, _SECRETS_FILE.open("a", encoding="utf-8") as sink:
            sink.write(value + "\n")
    return value


def observe(key: str, value) -> None:
    """Records a measured fact for the report without asserting it (observations.json)."""
    path = RESULTS_DIR / "observations.json"
    with _secrets_lock:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data[key] = value
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ── HTTP ──────────────────────────────────────────────────────────────────────

# Registration and login share a limit of 10 attempts per minute per client address
# (AUTH_LOGIN_RATE_LIMIT_PER_MINUTE). The suite paces itself instead of raising the limit.
_AUTH_WINDOW, _AUTH_BUDGET = 60.0, 9
_auth_calls: deque[float] = deque()
_http = httpx.Client(base_url=API_URL, timeout=httpx.Timeout(180.0, connect=10.0))


def _pace_auth() -> None:
    while True:
        now = time.monotonic()
        while _auth_calls and now - _auth_calls[0] > _AUTH_WINDOW:
            _auth_calls.popleft()
        if len(_auth_calls) < _AUTH_BUDGET:
            _auth_calls.append(now)
            return
        time.sleep(_AUTH_WINDOW - (now - _auth_calls[0]) + 0.5)


def request(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    headers = dict(kwargs.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    is_auth = path.startswith("/api/v1/auth/login") or path.startswith("/api/v1/auth/register")
    for _ in range(3):
        if is_auth:
            _pace_auth()
        response = _http.request(method, path, headers=headers, **kwargs)
        if response.status_code != 429:
            return response
        time.sleep(float(response.headers.get("Retry-After", "30")) + 1)
    return response


@dataclass
class Account:
    email: str
    password: str = field(repr=False)  # kept out of pytest's failure output
    token: str = field(repr=False)
    user: dict = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        return self.user["id"]

    @property
    def profile_id(self) -> str:
        return self.user["profile_id"]

    @property
    def role(self) -> str:
        return self.user["role"]

    def get(self, path: str, **kw) -> httpx.Response:
        return request("GET", path, self.token, **kw)

    def post(self, path: str, **kw) -> httpx.Response:
        return request("POST", path, self.token, **kw)

    def patch(self, path: str, **kw) -> httpx.Response:
        return request("PATCH", path, self.token, **kw)

    def put(self, path: str, **kw) -> httpx.Response:
        return request("PUT", path, self.token, **kw)

    def delete(self, path: str, **kw) -> httpx.Response:
        return request("DELETE", path, self.token, **kw)


def new_password() -> str:
    return remember_secret("E2e-" + secrets.token_urlsafe(15))


def unique_email(label: str) -> str:
    return f"e2e.{label}.{uuid.uuid4().hex[:10]}@example.test"


def register(role: str = "STUDENT", label: str | None = None, **extra) -> Account:
    email = unique_email(label or role.lower())
    password = new_password()
    body = {"email": email, "password": password, "full_name": extra.pop("full_name", f"E2E {role.title()}"),
            "role": role, **extra}
    response = request("POST", "/api/v1/auth/register", json=body)
    assert response.status_code == 201, response.text
    data = response.json()
    return Account(email, password, remember_secret(data["access_token"]), data["user"])


def login(email: str, password: str) -> httpx.Response:
    response = request("POST", "/api/v1/auth/login", json={"email": email, "password": password})
    if response.status_code == 200:
        remember_secret(response.json()["access_token"])
    return response


def login_account(email: str, password: str) -> Account:
    response = login(email, password)
    assert response.status_code == 200, response.text
    data = response.json()
    return Account(email, password, data["access_token"], data["user"])


# ── Database and stack ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def db() -> Iterator[Engine]:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


def scalar(engine: Engine, sql: str, **params):
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar()


def rows(engine: Engine, sql: str, **params) -> list[dict]:
    with engine.connect() as connection:
        return [dict(r._mapping) for r in connection.execute(text(sql), params)]


def compose(*args: str, check: bool = True, timeout: float = 900, files: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    base = list(COMPOSE)
    for extra in files:
        base += ["-f", extra]
    completed = subprocess.run(
        [*base, *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise AssertionError(f"docker compose {' '.join(args)} failed: {completed.stderr[-2000:]}")
    return completed


def run_seeder(*extra: str) -> subprocess.CompletedProcess:
    """The documented seeder contract: production requires --password."""
    return compose("exec", "-T", "backend", "python", "-m", "scripts.seed_demo_data",
                   "--password", DEMO_PASSWORD, *extra, check=False, timeout=600)


def wait_ready(timeout: float = 180) -> dict:
    deadline = time.monotonic() + timeout
    last: object = None
    while time.monotonic() < deadline:
        try:
            response = _http.get("/api/health/ready", timeout=5)
            last = response.status_code
            if response.status_code == 200:
                return response.json()
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise AssertionError(f"backend not ready within {timeout}s (last: {last})")


# ── Shared accounts ───────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def demo_seeded() -> None:
    """The demo dataset exists (test_00 seeds it; a module run alone seeds it here)."""
    if login(DEMO_EMAILS["student"], DEMO_PASSWORD).status_code == 200:
        return
    result = run_seeder()
    if result.returncode != 0:  # a demo email taken by another account: recreate the set
        result = run_seeder("--reset")
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.fixture(scope="session")
def demo(demo_seeded) -> dict[str, Account]:
    return {role: login_account(email, DEMO_PASSWORD) for role, email in DEMO_EMAILS.items()}


@pytest.fixture(scope="session")
def corpus(db, demo_seeded) -> dict[str, str]:
    """Six research works with fixed embeddings, plus embeddings on the seeded venues."""
    from corpus import ensure_corpus

    return ensure_corpus(db)


def all_opportunities() -> list[dict]:
    response = request("GET", "/api/opportunities", params={"page_size": 100})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def opportunity_by_title(title: str) -> dict:
    match = [o for o in all_opportunities() if o["title"] == title]
    assert match, f"opportunity {title!r} not found"
    return match[0]
