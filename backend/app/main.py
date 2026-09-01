from __future__ import annotations

import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.health import router as health_router
from app.api.opportunities import router as opportunities_router
from app.api.v1.discovery import router as discovery_router
from app.core.cache import DiscoveryResponseCacheMiddleware
from app.core.config import settings
from app.core.rate_limiter import DiscoveryRateLimitMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates an X-Request-ID header on all incoming requests."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app = FastAPI(title=settings.app_name)

# Mount middleware in order: CORS -> Correlation -> Cache -> Rate Limiting
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(DiscoveryResponseCacheMiddleware)
app.add_middleware(DiscoveryRateLimitMiddleware)

app.include_router(health_router, prefix="/api")
app.include_router(opportunities_router, prefix="/api")
app.include_router(discovery_router, prefix="/api/v1")
app.include_router(discovery_router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} backend is running"}

