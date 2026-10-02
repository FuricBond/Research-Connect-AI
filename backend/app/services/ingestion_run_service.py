"""
Research refresh (step 4/6) — ingestion runs and data freshness, for the admin console.

Each research refresh pass writes one ingestion_runs row labelled
``research_refresh:{run_tag}:{lane}:{subfield}``; the rows sharing a run_tag are one refresh.
This module reads them back for ``GET /api/v1/admin/ingestion-runs``.

Stored error messages can hold request text (redacted, but still a URL and an exception), so
responses carry a fixed error category instead, and only the numeric run metrics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.ingestion_run import IngestionRunModel
from app.schemas.opportunity import IngestionRunRead, ResearchRefreshStatus

RESEARCH_REFRESH_PREFIX = "research_refresh:"
RESEARCH_REFRESH_JOB = "research_refresh"

# The error categories a response may show; anything else becomes "error".
ERROR_CATEGORIES = ("budget exhausted", "stop requested", "interrupted", "error")


def error_category(message: str | None) -> str | None:
    """A fixed, text-free label for a stored error message (None when there was no error)."""
    if not message:
        return None
    lowered = message.lower()
    if "budget" in lowered:
        return "budget exhausted"
    if lowered == "stop requested":
        return "stop requested"
    if lowered == "interrupted":
        return "interrupted"
    return "error"


def run_tag_of(topic: str | None) -> str | None:
    """The run_tag of a research refresh row's label, or None for any other row."""
    if not topic or not topic.startswith(RESEARCH_REFRESH_PREFIX):
        return None
    parts = topic.split(":")
    return parts[1] if len(parts) >= 2 and parts[1] else None


def to_read(run: IngestionRunModel) -> IngestionRunRead:
    """The API view of a run: the error as a category, and only numeric metrics."""
    item = IngestionRunRead.model_validate(run)
    metrics = None
    if isinstance(run.metrics_detail, dict):
        metrics = {
            key: value
            for key, value in run.metrics_detail.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    return item.model_copy(update={"error_message": error_category(run.error_message), "metrics_detail": metrics})


def _research_rows():
    return select(IngestionRunModel).where(IngestionRunModel.topic.startswith(RESEARCH_REFRESH_PREFIX))


def list_runs(db: Session, *, limit: int, research_only: bool = True) -> list[IngestionRunRead]:
    """The newest ingestion runs first; with research_only, research refresh rows only."""
    stmt = _research_rows() if research_only else select(IngestionRunModel)
    stmt = stmt.order_by(IngestionRunModel.started_at.desc(), IngestionRunModel.id.desc()).limit(limit)
    return [to_read(run) for run in db.execute(stmt).scalars()]


def runs_for_tag(db: Session, run_tag: str) -> list[IngestionRunModel]:
    """Every row of one research refresh."""
    return list(
        db.execute(
            select(IngestionRunModel).where(
                IngestionRunModel.topic.startswith(f"{RESEARCH_REFRESH_PREFIX}{run_tag}:", autoescape=True)
            )
        ).scalars()
    )


def newest_run_tags(db: Session, count: int) -> list[str]:
    """Up to ``count`` distinct research refresh run tags, newest first."""
    tags: list[str] = []
    stmt = _research_rows().order_by(IngestionRunModel.started_at.desc(), IngestionRunModel.id.desc())
    for run in db.execute(stmt.limit(count * 64)).scalars():
        tag = run_tag_of(run.topic)
        if tag is not None and tag not in tags:
            tags.append(tag)
            if len(tags) == count:
                break
    return tags


def run_status(rows: list[IngestionRunModel]) -> str | None:
    """RUNNING if any pass is running, FAILED if every pass failed, otherwise COMPLETED."""
    if not rows:
        return None
    statuses = {row.status for row in rows}
    if "RUNNING" in statuses:
        return "RUNNING"
    if statuses == {"FAILED"}:
        return "FAILED"
    return "COMPLETED"


def _as_utc(moment: datetime | None) -> datetime | None:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def research_refresh_status(
    db: Session,
    cfg: Settings,
    *,
    scheduler: Any | None = None,
    now: datetime | None = None,
) -> ResearchRefreshStatus:
    """
    Data freshness for the admin console. The next run is estimated from the last start
    plus the interval: the scheduler's in-memory metrics when this process schedules the
    job, otherwise the newest run in the database. None when the job is not scheduled.
    """
    now = now or datetime.now(timezone.utc)

    scheduled = scheduler is not None and RESEARCH_REFRESH_JOB in getattr(scheduler, "job_names", ())
    enabled = scheduled or (cfg.scheduler_enabled and cfg.scheduler_research_refresh_enabled)
    interval = int(
        scheduler.job(RESEARCH_REFRESH_JOB).interval_seconds
        if scheduled
        else cfg.scheduler_research_refresh_interval_seconds
    )

    tags = newest_run_tags(db, 1)
    rows = runs_for_tag(db, tags[0]) if tags else []
    last_started = _as_utc(min((row.started_at for row in rows), default=None))
    last_status = run_status(rows)

    added = db.execute(
        select(func.coalesce(func.sum(IngestionRunModel.records_inserted), 0)).where(
            IngestionRunModel.topic.startswith(RESEARCH_REFRESH_PREFIX),
            IngestionRunModel.started_at >= now - timedelta(hours=24),
        )
    ).scalar_one()

    reference = last_started
    if scheduled:
        in_memory = scheduler.metrics.get(RESEARCH_REFRESH_JOB).last_started_at
        if in_memory is not None:
            reference = _as_utc(in_memory)
    next_run = reference + timedelta(seconds=interval) if enabled and reference is not None else None

    return ResearchRefreshStatus(
        enabled=enabled,
        interval_seconds=interval,
        last_run_started_at=last_started,
        last_run_status=last_status,
        works_added_last_24h=int(added),
        next_run_estimate=next_run,
    )
