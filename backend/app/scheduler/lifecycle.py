"""
Phase 6.3 — Scheduler wiring for the FastAPI application.

The application lifespan starts the scheduler only when SCHEDULER_ENABLED is true, once per
application process, and stops it when the process shuts down. With the default (false)
nothing is created: no task, no thread, no database connection.

Phase 6.5 added one step before that: in production the lifespan first verifies the
database schema is current and refuses to start otherwise.

Research refresh (F-3) added an opt-in embedding warm-up: with EMBEDDING_WARMUP_ON_STARTUP
true, a background thread loads the embedding model while the API is already serving, so the
first literature search does not pay for it. It never delays or fails startup.

Phase 5.16 installs the SMTP email provider before the scheduler starts, when EMAIL_PROVIDER is
smtp. Otherwise the in-memory mock stays in place.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
import threading
import time

from fastapi import FastAPI

from app.core.config import Settings, settings
from app.scheduler.jobs import build_default_jobs
from app.scheduler.locks import lock_backend_for
from app.scheduler.scheduler import Scheduler
from app.services.smtp_email_provider import configure_email_provider

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


def load_embedding_model() -> None:
    """
    Load the embedding model through the very object literature search uses, and encode one
    short string so the first real query also finds the inference path warm. Imported here,
    not at module level, so this module adds no search or ML import to application startup.
    """
    from app.services.hybrid_search_service import hybrid_search_service

    hybrid_search_service.embedding_service.encode_one("embedding warm-up")


def warm_up_embedding_model() -> None:
    """Run the model load, logging the outcome; a failure is reported, never raised."""
    started = time.perf_counter()
    try:
        load_embedding_model()
    except Exception:
        logger.warning(
            "Embedding model warm-up failed; the first literature search will load the model",
            exc_info=True,
        )
        return
    logger.info("Embedding model warm-up finished in %.1f s", time.perf_counter() - started)


def start_embedding_warmup(cfg: Settings) -> threading.Thread | None:
    """
    Start the warm-up on a daemon thread when EMBEDDING_WARMUP_ON_STARTUP is true. The
    thread is not joined: startup returns at once, and shutdown never waits for a load.
    """
    if not cfg.embedding_warmup_on_startup:
        return None
    thread = threading.Thread(target=warm_up_embedding_model, name="embedding-warmup", daemon=True)
    thread.start()
    return thread


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    verify_database_schema(settings)
    start_embedding_warmup(settings)
    configure_email_provider(settings)
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
