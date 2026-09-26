"""
Global Pytest Configuration and Test Fixtures for ResearchConnect AI Backend.
"""
import os
from pathlib import Path
import sys
import uuid

# Ensure repository root is on sys.path for cross-module imports (ml, scrapers)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from app.core.cache import discovery_cache
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.rate_limiter import login_rate_limiter, rate_limiter
from app.models.user import UserModel


@pytest.fixture(scope="session", autouse=True)
def quiet_application_logging():
    """
    Importing `app.main` configures the root logger so the running service emits access
    logs on stdout. Under pytest that turns every request and every hot-loop log call in
    the suite into captured output, which inflates the performance-budget tests. Raising
    the level once per session keeps timings representative; individual tests that assert
    on log output can still attach their own handler via `caplog`.
    """
    configure_logging("WARNING", "text")


@pytest.fixture(autouse=True)
def reset_discovery_middleware_state():
    """
    Ensure each test starts with a fresh rate limiter window and clean response cache.
    """
    rate_limiter.reset()
    login_rate_limiter.reset()
    discovery_cache.clear()
    yield
    rate_limiter.reset()
    login_rate_limiter.reset()
    discovery_cache.clear()


@pytest.fixture
def intruder_identity(db_session):
    """
    A second, fully-registered account used to probe cross-researcher authorization.

    Phase 6 answers 401 for credentials that do not resolve to a real user, so an
    ownership probe has to authenticate as a genuine *other* account before it can reach
    the 403 ownership check. Passing a random UUID would only prove that unknown
    credentials are rejected, which the security regression suite already covers.
    """
    user = UserModel(
        id=uuid.uuid4(),
        email=f"intruder.{uuid.uuid4().hex[:10]}@other-university.edu",
        hashed_password="not-a-usable-password-hash",
        full_name="Dr. Unrelated Researcher",
        role="STUDENT",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture(autouse=True)
def developer_identity_mode(monkeypatch):
    """
    The pre-Phase 6 suite authenticates with a raw X-User-ID header, which the API only
    honours in developer identity mode. Security tests that exercise production behaviour
    turn it back off with `monkeypatch.setattr(settings, "auth_dev_identity_enabled", False)`.
    Minimum-cost bcrypt keeps password hashing fast in tests.
    """
    monkeypatch.setattr(settings, "auth_dev_identity_enabled", True)
    monkeypatch.setattr(settings, "auth_bcrypt_rounds", 4)
    monkeypatch.setattr(settings, "auth_secret_key", "test-signing-key-0123456789abcdef-0123456789")


@pytest.fixture(autouse=True)
def scheduler_disabled(monkeypatch):
    """
    Phase 6.3: the background scheduler must never start during tests, even when a local
    `.env` enables it, because its jobs would write to the configured database. Scheduler
    tests opt in explicitly.
    """
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    monkeypatch.setattr(settings, "scheduler_opportunity_refresh_enabled", False)
