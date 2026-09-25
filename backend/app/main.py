from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.opportunities import router as opportunities_router
from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.calendar import router as calendar_router
from app.api.v1.discovery import router as discovery_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.researchers import router as researchers_router
from app.api.v1.submissions import router as submissions_router
from app.api.v1.workspace import router as workspace_router
from app.api.v1.workspace_collaboration import router as workspace_collaboration_router
from app.core.cache import DiscoveryResponseCacheMiddleware
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.rate_limiter import DiscoveryRateLimitMiddleware
from app.core.security import validate_security_settings

configure_logging(settings.log_level, settings.log_format)
validate_security_settings()

app = FastAPI(title=settings.app_name)

# Starlette runs the last-added middleware first, so the effective order is:
# RequestContext -> SecurityHeaders -> CORS -> Cache -> Rate Limiting -> route.
app.add_middleware(DiscoveryRateLimitMiddleware)
app.add_middleware(DiscoveryResponseCacheMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

app.include_router(health_router, prefix="/api")
app.include_router(opportunities_router, prefix="/api")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(discovery_router, prefix="/api/v1")
app.include_router(discovery_router, prefix="/api")
app.include_router(researchers_router, prefix="/api/v1")
app.include_router(researchers_router, prefix="/api")
app.include_router(workspace_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api")
app.include_router(submissions_router, prefix="/api/v1")
app.include_router(submissions_router, prefix="/api")
app.include_router(calendar_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api")
app.include_router(workspace_collaboration_router, prefix="/api/v1")
app.include_router(workspace_collaboration_router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} backend is running"}
