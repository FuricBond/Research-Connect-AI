"""
Unit and Integration Tests for Phase 2.4K Production Hardening.

Tests:
  1. Sliding-window rate limiter logic and headers
  2. Rate limit exceeded (HTTP 429) and Retry-After headers
  3. Response caching (X-Cache: HIT vs MISS)
  4. Cache key differentiation across query params/filters
  5. Cache TTL expiration and purge
  6. Correlation ID (X-Request-ID) propagation
"""
from __future__ import annotations

import time
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
import pytest

from app.core.cache import DiscoveryCache, discovery_cache
from app.core.config import settings
from app.core.rate_limiter import SlidingWindowRateLimiter, rate_limiter
from app.main import app
from app.models.research_knowledge import ResearchWorkModel
from app.schemas.discovery import (
    ResearchSearchResponse,
    ResearchSearchResultItem,
    ResearchWorkRead,
)


@pytest.fixture(autouse=True)
def clean_hardening_state():
    """Ensure clean cache and rate limiter state before every test."""
    rate_limiter.reset()
    discovery_cache.clear()
    yield
    rate_limiter.reset()
    discovery_cache.clear()


@pytest.fixture
def client():
    return TestClient(app)


# ── 1. Sliding Window Rate Limiter Unit Tests ─────────────────────────────────


class TestSlidingWindowRateLimiter:
    """Unit tests for SlidingWindowRateLimiter."""

    def test_requests_allowed_under_limit(self):
        limiter = SlidingWindowRateLimiter(requests_per_window=5, window_seconds=60)
        client_key = "192.168.1.100"

        for i in range(5):
            status = limiter.check(client_key)
            assert status.allowed is True
            assert status.limit == 5
            assert status.remaining == 4 - i

    def test_request_blocked_when_limit_exceeded(self):
        limiter = SlidingWindowRateLimiter(requests_per_window=3, window_seconds=60)
        client_key = "192.168.1.101"

        assert limiter.check(client_key).allowed is True
        assert limiter.check(client_key).allowed is True
        assert limiter.check(client_key).allowed is True

        # 4th request exceeds limit
        status = limiter.check(client_key)
        assert status.allowed is False
        assert status.remaining == 0
        assert status.reset_after_seconds > 0

    def test_different_clients_isolated(self):
        limiter = SlidingWindowRateLimiter(requests_per_window=2, window_seconds=60)
        client_a = "10.0.0.1"
        client_b = "10.0.0.2"

        limiter.check(client_a)
        limiter.check(client_a)
        assert limiter.check(client_a).allowed is False

        # Client B still has quota
        assert limiter.check(client_b).allowed is True
        assert limiter.check(client_b).allowed is True
        assert limiter.check(client_b).allowed is False

    def test_window_expiration_restores_quota(self):
        limiter = SlidingWindowRateLimiter(requests_per_window=2, window_seconds=1)
        client_key = "10.0.0.3"

        assert limiter.check(client_key).allowed is True
        assert limiter.check(client_key).allowed is True
        assert limiter.check(client_key).allowed is False

        # Wait for 1-second window to expire
        time.sleep(1.1)
        assert limiter.check(client_key).allowed is True


# ── 2. Response Cache Unit Tests ──────────────────────────────────────────────


class TestDiscoveryResponseCache:
    """Unit tests for DiscoveryCache."""

    def test_cache_miss_then_hit(self):
        cache = DiscoveryCache(default_ttl=60, max_entries=10)
        key = cache.generate_key("/api/v1/discovery/research/search", [("q", "machine learning"), ("limit", "10")])

        assert cache.get(key) is None

        cache.set(key, b'{"items": []}', media_type="application/json", status_code=200)

        entry = cache.get(key)
        assert entry is not None
        assert entry.content == b'{"items": []}'
        assert entry.status_code == 200

    def test_cache_key_differentiation_by_params(self):
        cache = DiscoveryCache(default_ttl=60)
        key_a = cache.generate_key("/search", [("q", "neural network"), ("limit", "10")])
        key_b = cache.generate_key("/search", [("q", "graph network"), ("limit", "10")])
        key_c = cache.generate_key("/search", [("limit", "10"), ("q", "neural network")])

        assert key_a != key_b
        # Order of params does not change key
        assert key_a == key_c

    def test_cache_ttl_expiration(self):
        cache = DiscoveryCache(default_ttl=1)
        key = "test-key"
        cache.set(key, b"data", ttl=1)

        assert cache.get(key) is not None
        time.sleep(1.1)
        assert cache.get(key) is None

    def test_cache_clear(self):
        cache = DiscoveryCache(default_ttl=60)
        cache.set("key1", b"data1")
        cache.set("key2", b"data2")
        assert cache.size() == 2

        cache.clear()
        assert cache.size() == 0


# ── 3. Integration Tests with FastAPI TestClient ──────────────────────────────


class TestProductionHardeningIntegration:
    """Integration tests verifying middleware in the live FastAPI application."""

    def test_correlation_id_propagated(self, client):
        custom_id = "test-req-12345"
        resp = client.get("/", headers={"x-request-id": custom_id})
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID") == custom_id

    def test_correlation_id_generated_when_absent(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) > 10

    def test_discovery_response_caching_hit_and_miss(self, client):
        with patch(
            "app.services.hybrid_search_service.HybridSearchService.search_research_works",
            return_value=[],
        ):
            # First request -> Cache MISS
            resp1 = client.get("/api/v1/discovery/research/search?q=attention+mechanisms")
            assert resp1.status_code == 200
            assert resp1.headers.get("X-Cache") == "MISS"
            assert "max-age" in resp1.headers.get("Cache-Control", "")

            # Second identical request -> Cache HIT
            resp2 = client.get("/api/v1/discovery/research/search?q=attention+mechanisms")
            assert resp2.status_code == 200
            assert resp2.headers.get("X-Cache") == "HIT"

            # Query with different parameters -> Cache MISS
            resp3 = client.get("/api/v1/discovery/research/search?q=transformers")
            assert resp3.status_code == 200
            assert resp3.headers.get("X-Cache") == "MISS"

    def test_discovery_rate_limiting_enforcement(self, client):
        # Configure a strict limiter for this test
        test_limiter = SlidingWindowRateLimiter(requests_per_window=3, window_seconds=60)
        
        with patch.object(app.middleware_stack, "limiter", test_limiter, create=True):
            # We can test rate limiter middleware directly with custom limiter
            rate_limiter.requests_per_window = 3

            with patch(
                "app.services.hybrid_search_service.HybridSearchService.search_research_works",
                return_value=[],
            ):
                # 3 requests allowed
                r1 = client.get("/api/v1/discovery/research/search?q=q1")
                assert r1.status_code == 200
                assert r1.headers.get("X-RateLimit-Remaining") == "2"

                r2 = client.get("/api/v1/discovery/research/search?q=q2")
                assert r2.status_code == 200

                r3 = client.get("/api/v1/discovery/research/search?q=q3")
                assert r3.status_code == 200

                # 4th request rate limited
                r4 = client.get("/api/v1/discovery/research/search?q=q4")
                assert r4.status_code == 429
                assert "Rate limit exceeded" in r4.json()["detail"]
                assert "Retry-After" in r4.headers
                assert r4.headers.get("X-RateLimit-Remaining") == "0"
