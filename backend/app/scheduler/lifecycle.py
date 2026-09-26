"""
Phase 6.3 — Scheduler wiring for the FastAPI application.

The application lifespan starts the scheduler only when SCHEDULER_ENABLED is true, once per
application process, and stops it when the process shuts down. With the default (false)
nothing is created: no task, no thread, no database connection.
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
