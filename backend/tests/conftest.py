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
from app.core.rate_limiter import rate_limiter


@pytest.fixture(autouse=True)
def reset_discovery_middleware_state():
    """
    Ensure each test starts with a fresh rate limiter window and clean response cache.
    """
    rate_limiter.reset()
    discovery_cache.clear()
    yield
    rate_limiter.reset()
    discovery_cache.clear()
