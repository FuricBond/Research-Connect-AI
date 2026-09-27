"""
Phase 6.3 — Scheduler wiring for the FastAPI application.

The application lifespan starts the scheduler only when SCHEDULER_ENABLED is true, once per
application process, and stops it when the process shuts down. With the default (false)
nothing is created: no task, no thread, no database connection.

Phase 6.5 added one step before that: in production the lifespan first verifies the
database schema is current and refuses to start otherwise.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.core.config import Settings, settings
from app.scheduler.jobs import build_default_jobs
from app.scheduler.locks import lock_backend_for
from app.scheduler.scheduler import Scheduler

logger = logging.getLogger(__name__)


def build_scheduler(cfg: Settings) -> Scheduler:
    """The production scheduler: the approved jobs on the application's own engine."""
    from app.db.session import SessionLocal, engine

    return Scheduler(
        build_default_jobs(cfg),
        session_factory=SessionLocal,
        lock_backend=lock_backend_for(engine),
    )


def verify_database_schema(cfg: Settings) -> None:
    """
    Phase 6.5: in production, refuse to start unless the database is reachable and its
    schema is exactly this code's Alembic head. Outside production this is skipped, so the
    test suite and the host development loop open no connection at startup; readiness is
    still reported by `GET /api/health/ready`.
    """
    if cfg.app_env != "production":
        return
    from app.db.schema_status import ensure_schema_current
    from app.db.session import engine

    ensure_schema_current(engine)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    verify_database_schema(settings)
    scheduler: Scheduler | None = None
    if settings.scheduler_enabled:
        scheduler = build_scheduler(settings)
        await scheduler.start()
    else:
        logger.debug("Background scheduler disabled (SCHEDULER_ENABLED=false)")
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()
        app.state.scheduler = None
