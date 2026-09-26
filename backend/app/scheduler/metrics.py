"""
Phase 6.3 — Scheduler run records and per-job metrics.

Every dispatch produces one JobRun with a unique run id. Metrics are kept in process memory
and emitted through the application log (one structured line per run); there is no metrics
server, matching the rest of the backend.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import threading
from typing import Any
import uuid


class JobRunStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    # Completed, but some items (profiles, notifications, records) failed and were skipped.
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    # Stopped by scheduler shutdown while running.
    CANCELLED = "CANCELLED"
    # Another holder (usually another process) had the job's lock; nothing ran.
    SKIPPED_LOCKED = "SKIPPED_LOCKED"
    # This process's previous run of the job had not finished; nothing ran.
    SKIPPED_RUNNING = "SKIPPED_RUNNING"


SKIPPED_STATUSES = frozenset({JobRunStatus.SKIPPED_LOCKED, JobRunStatus.SKIPPED_RUNNING})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobRun:
    job_name: str
    trigger: str
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime | None = None
    status: JobRunStatus | None = None
    records_processed: int | None = None
    items_failed: int = 0
    error_type: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def finish(
        self,
        status: JobRunStatus,
        *,
        records_processed: int | None = None,
        items_failed: int = 0,
        error_type: str | None = None,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> JobRun:
        self.finished_at = _utcnow()
        self.status = status
        self.records_processed = records_processed
        self.items_failed = items_failed
        self.error_type = error_type
        self.error_message = error_message
        if details:
            self.details = dict(details)
        return self

    def log_fields(self) -> dict[str, Any]:
        return {
            "job_name": self.job_name,
            "run_id": str(self.run_id),
            "trigger": self.trigger,
            "status": self.status.value if self.status else None,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": round(self.duration_seconds, 3) if self.duration_seconds is not None else None,
            "records_processed": self.records_processed,
            "items_failed": self.items_failed,
            "error_type": self.error_type,
            "details": self.details,
        }


@dataclass
class JobMetrics:
    job_name: str
    runs_recorded: int = 0
    # Runs that took the lock and did work, whatever their outcome.
    executions: int = 0
    successes: int = 0
    partial_successes: int = 0
    failures: int = 0
    timeouts: int = 0
    cancellations: int = 0
    skipped_due_to_lock: int = 0
    skipped_still_running: int = 0
    total_duration_seconds: float = 0.0
    last_run_id: str | None = None
    last_status: str | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_duration_seconds: float | None = None
    last_records_processed: int | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_type: str | None = None


class SchedulerMetrics:
    """Per-job counters. Written on the event loop, readable from any thread."""

    def __init__(self, job_names: list[str]) -> None:
        self._lock = threading.Lock()
        self._jobs = {name: JobMetrics(job_name=name) for name in job_names}

    def record(self, run: JobRun) -> None:
        with self._lock:
            metrics = self._jobs[run.job_name]
            metrics.runs_recorded += 1
            metrics.last_run_id = str(run.run_id)
            metrics.last_status = run.status.value if run.status else None
            metrics.last_started_at = run.started_at
            metrics.last_finished_at = run.finished_at

            if run.status is JobRunStatus.SKIPPED_LOCKED:
                metrics.skipped_due_to_lock += 1
                return
            if run.status is JobRunStatus.SKIPPED_RUNNING:
                metrics.skipped_still_running += 1
                return

            metrics.executions += 1
            duration = run.duration_seconds or 0.0
            metrics.total_duration_seconds += duration
            metrics.last_duration_seconds = duration
            metrics.last_records_processed = run.records_processed
            if run.status is JobRunStatus.SUCCEEDED:
                metrics.successes += 1
                metrics.last_success_at = run.finished_at
            elif run.status is JobRunStatus.PARTIAL:
                metrics.partial_successes += 1
                metrics.last_success_at = run.finished_at
                metrics.last_failure_at = run.finished_at
                metrics.last_error_type = run.error_type or "ItemFailures"
            else:
                if run.status is JobRunStatus.TIMED_OUT:
                    metrics.timeouts += 1
                elif run.status is JobRunStatus.CANCELLED:
                    metrics.cancellations += 1
                else:
                    metrics.failures += 1
                metrics.last_failure_at = run.finished_at
                metrics.last_error_type = run.error_type

    def get(self, job_name: str) -> JobMetrics:
        with self._lock:
            return JobMetrics(**asdict(self._jobs[job_name]))

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: asdict(metrics) for name, metrics in self._jobs.items()}
