"""
Global Pytest Configuration and Test Fixtures for ResearchConnect AI Backend.
"""
import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path for cross-module imports (ml, scrapers)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from app.core.cache import discovery_cache
from app.core.config import settings
from app.core.rate_limiter import login_rate_limiter, rate_limiter


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
