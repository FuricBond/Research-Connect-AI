"""
In-Memory Response Cache for Deterministic Discovery Endpoints (Phase 2.4K).

Provides thread-safe, TTL-based in-memory caching for read-only GET discovery requests.
Emits standard `X-Cache: HIT` / `X-Cache: MISS` headers and supports configurable TTL and size bounds.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import logging
import threading
import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Stored cache item with serialized content and expiration metadata."""
    content: bytes
    media_type: str
    status_code: int
    headers: dict[str, str]
    expires_at: float
    created_at: float


class DiscoveryCache:
    """
    Thread-safe in-memory TTL cache with LRU eviction policy.
    """

    def __init__(
        self,
        default_ttl: int = 60,
        max_entries: int = 1000,
    ) -> None:
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

    def generate_key(self, path: str, query_params: list[tuple[str, str]]) -> str:
        """
        Generate a deterministic SHA-256 cache key from request path and sorted query parameters.
        """
        sorted_params = sorted(query_params, key=lambda x: (x[0], x[1]))
        param_str = "&".join(f"{k}={v}" for k, v in sorted_params)
        raw_key = f"GET:{path}?{param_str}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> CacheEntry | None:
        """Retrieve cached entry if present and not expired."""
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if now > entry.expires_at:
                del self._cache[key]
                return None

            # Move to end for LRU
            self._cache.move_to_end(key)
            return entry

    def set(
        self,
        key: str,
        content: bytes,
        media_type: str = "application/json",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Store response content in cache with expiration."""
        now = time.time()
        effective_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = now + effective_ttl

        safe_headers = dict(headers or {})
        # Omit hop-by-hop or dynamic caching headers
        safe_headers.pop("content-length", None)
        safe_headers.pop("x-cache", None)

        entry = CacheEntry(
            content=content,
            media_type=media_type,
            status_code=status_code,
            headers=safe_headers,
            expires_at=expires_at,
            created_at=now,
        )

        with self._lock:
            # Evict oldest entry if at capacity
            if len(self._cache) >= self.max_entries and key not in self._cache:
                self._cache.popitem(last=False)

            self._cache[key] = entry
            self._cache.move_to_end(key)

    def clear(self) -> None:
        """Purge all cached responses."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Current number of active cached entries."""
        with self._lock:
            return len(self._cache)


# Default singleton instance
discovery_cache = DiscoveryCache(
    default_ttl=getattr(settings, "discovery_cache_ttl_seconds", 60),
    max_entries=getattr(settings, "discovery_cache_max_entries", 1000),
)


class DiscoveryResponseCacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware providing deterministic caching for read-only GET discovery queries.
    """

    def __init__(
        self,
        app,
        cache: DiscoveryCache | None = None,
        path_prefix: str = "/api/v1/discovery",
    ) -> None:
        super().__init__(app)
        self.cache = cache or discovery_cache
        self.path_prefix = path_prefix

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Check if caching is enabled
        if not getattr(settings, "discovery_cache_enabled", True):
            return await call_next(request)

        # Check for bypass header
        if (
            request.headers.get("x-bypass-cache") == "true"
            or request.headers.get("cache-control") in {"no-cache", "no-store"}
        ):
            return await call_next(request)

        # Only cache GET requests on discovery endpoints
        is_discovery = (
            request.url.path.startswith(self.path_prefix)
            or request.url.path.startswith("/api/discovery")
        )
        if request.method != "GET" or not is_discovery:
            return await call_next(request)

        # Build deterministic cache key
        query_items = list(request.query_params.multi_items())
        cache_key = self.cache.generate_key(request.url.path, query_items)

        # Check for cache hit
        cached_entry = self.cache.get(cache_key)
        if cached_entry is not None:
            remaining_ttl = max(1, int(cached_entry.expires_at - time.time()))
            resp = StarletteResponse(
                content=cached_entry.content,
                status_code=cached_entry.status_code,
                media_type=cached_entry.media_type,
                headers=dict(cached_entry.headers),
            )
            resp.headers["X-Cache"] = "HIT"
            resp.headers["Cache-Control"] = f"public, max-age={remaining_ttl}"
            return resp

        # Downstream execution (cache miss)
        response = await call_next(request)

        # Only cache successful 200 OK responses
        if response.status_code == 200:
            # Capture response body
            body_chunks = []
            async for chunk in response.body_iterator:
                body_chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            body_bytes = b"".join(body_chunks)

            # Store in cache
            ttl = getattr(settings, "discovery_cache_ttl_seconds", 60)
            self.cache.set(
                key=cache_key,
                content=body_bytes,
                media_type=response.media_type or "application/json",
                status_code=response.status_code,
                headers=dict(response.headers),
                ttl=ttl,
            )

            # Return reconstructed response
            resp = StarletteResponse(
                content=body_bytes,
                status_code=response.status_code,
                media_type=response.media_type or "application/json",
                headers=dict(response.headers),
            )
            resp.headers["X-Cache"] = "MISS"
            resp.headers["Cache-Control"] = f"public, max-age={ttl}"
            return resp

        response.headers["X-Cache"] = "BYPASS"
        return response
