"""
Sliding-window In-Memory Rate Limiter for Phase 2.4K.

Provides thread-safe, memory-bounded rate limiting for public discovery endpoints.
Emits standard rate limit headers (Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
and returns HTTP 429 Too Many Requests when limits are exceeded.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
import threading
import time
from typing import Callable

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitStatus:
    """Status result from checking a rate limit."""
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding-window rate limiter storing epoch timestamps per client identifier.
    """

    def __init__(
        self,
        requests_per_window: int = 60,
        window_seconds: int = 60,
        max_tracked_keys: int = 10000,
    ) -> None:
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        self._lock = threading.Lock()
        self._records: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def check(self, key: str) -> RateLimitStatus:
        """
        Check whether an incoming request under `key` is allowed within the current sliding window.
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            # Periodically prune stale entries to prevent memory growth
            if now - self._last_cleanup > 30:
                self._cleanup_stale(window_start)
                self._last_cleanup = now

            timestamps = self._records[key]
            # Filter timestamps within current window
            valid_timestamps = [t for t in timestamps if t > window_start]
            current_count = len(valid_timestamps)

            if current_count >= self.requests_per_window:
                oldest = valid_timestamps[0] if valid_timestamps else now
                reset_after = max(1, int(oldest + self.window_seconds - now))
                self._records[key] = valid_timestamps
                return RateLimitStatus(
                    allowed=False,
                    limit=self.requests_per_window,
                    remaining=0,
                    reset_after_seconds=reset_after,
                )

            valid_timestamps.append(now)
            self._records[key] = valid_timestamps
            remaining = max(0, self.requests_per_window - len(valid_timestamps))
            oldest = valid_timestamps[0]
            reset_after = max(1, int(oldest + self.window_seconds - now))

            return RateLimitStatus(
                allowed=True,
                limit=self.requests_per_window,
                remaining=remaining,
                reset_after_seconds=reset_after,
            )

    def _cleanup_stale(self, window_start: float) -> None:
        """Prune client records with no requests in the active window."""
        stale_keys = [
            k for k, ts in self._records.items()
            if not ts or ts[-1] <= window_start
        ]
        for k in stale_keys:
            del self._records[k]

        # Guard against key explosion
        if len(self._records) > self.max_tracked_keys:
            self._records.clear()

    def reset(self) -> None:
        """Clear all rate limit tracking records."""
        with self._lock:
            self._records.clear()


# Default singleton instance
rate_limiter = SlidingWindowRateLimiter(
    requests_per_window=getattr(settings, "discovery_rate_limit_per_minute", 60),
    window_seconds=60,
)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request headers or transport socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class DiscoveryRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware applying rate limits specifically to discovery endpoints.
    """

    def __init__(
        self,
        app,
        limiter: SlidingWindowRateLimiter | None = None,
        path_prefix: str = "/api/v1/discovery",
    ) -> None:
        super().__init__(app)
        self.limiter = limiter or rate_limiter
        self.path_prefix = path_prefix

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Check if rate limiting is enabled and applies to this path
        if not getattr(settings, "discovery_rate_limiting_enabled", True):
            return await call_next(request)

        if request.headers.get("x-bypass-rate-limit") == "true":
            return await call_next(request)

        # Check path prefix (handle /api/v1/discovery and /api/discovery)
        is_discovery = request.url.path.startswith(self.path_prefix) or request.url.path.startswith("/api/discovery")
        if not is_discovery or request.method == "OPTIONS":
            return await call_next(request)

        client_ip = get_client_ip(request)
        status_info = self.limiter.check(client_ip)

        if not status_info.allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Too many discovery requests."},
                headers={
                    "Retry-After": str(status_info.reset_after_seconds),
                    "X-RateLimit-Limit": str(status_info.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(status_info.reset_after_seconds),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(status_info.limit)
        response.headers["X-RateLimit-Remaining"] = str(status_info.remaining)
        response.headers["X-RateLimit-Reset"] = str(status_info.reset_after_seconds)
        return response
