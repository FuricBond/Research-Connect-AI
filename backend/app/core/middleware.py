"""
Phase 6 — Cross-cutting HTTP middleware: request correlation, access logging, and
defensive security headers.
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging_config import request_id_ctx

access_logger = logging.getLogger("app.access")

# Client-supplied correlation IDs are echoed back and logged, so constrain their shape.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Assigns or propagates an X-Request-ID header, exposes it to log records for the
    duration of the request, and emits one structured access-log line per request.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get("x-request-id")
        request_id = incoming if incoming and _REQUEST_ID_PATTERN.match(incoming) else str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            access_logger.info(
                "%s %s %s",
                request.method,
                request.url.path,
                status_code,
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "user_id": getattr(request.state, "user_id", None),
                },
            )
            request_id_ctx.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds conservative security headers suitable for a JSON API."""

    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
    }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for name, value in self.HEADERS.items():
            response.headers.setdefault(name, value)
        return response
