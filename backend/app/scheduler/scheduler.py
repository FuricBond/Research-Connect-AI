"""
Phase 6.3 — A small asyncio scheduler for periodic maintenance jobs.

Lifecycle
    `start()` launches one asyncio task per registered job; each waits for its first due time,
    dispatches a run, and repeats every `interval_seconds` (measured start to start). `stop()`
    ends the loops, asks running jobs to stop at their next safe point, and waits at most
    `shutdown_timeout_seconds` for them. `run_job_now()` dispatches one run immediately, which
    is how tests (and operators) trigger a job without waiting for its interval.

Execution boundary
    The services the jobs call are synchronous SQLAlchemy code, so every run executes in its
    own daemon thread; the event loop only waits on a future. A daemon thread cannot hold the
    process open at shutdown, and a lock it held is released by PostgreSQL when the process
    exits and its connection closes.

Isolation
    One task per job, and every outcome of a run (success, exception, timeout) is recorded
    and logged without leaving the dispatcher, so a failing job never stops its own loop or
    any other job. At most `max_concurrent_jobs` runs execute at once.

Overlap
    A job runs at most once at a time in this process (a run whose previous run is still
    going is recorded as SKIPPED_RUNNING) and, through the job lock, at most once at a time
    across processes (SKIPPED_LOCKED). The worker thread takes the lock itself and releases it
    in a `finally` when its work actually ends, so a timed-out run that is still unwinding
    keeps its lock and later runs are skipped rather than overlapped.

Timeouts
    When a run exceeds `timeout_seconds` it is recorded as TIMED_OUT and signalled to stop.
    Jobs check the signal between units of work (for example between profiles), roll back
    the unit in progress, and release their lock. On PostgreSQL every statement a run issues
    is also bounded by a `statement_timeout` equal to the job's budget.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
import functools
import logging
import threading
from typing import Any
import uuid

from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.logging_config import request_id_ctx
from app.scheduler.locks import JobLockBackend
from app.scheduler.metrics import JobRun, JobRunStatus, SchedulerMetrics

logger = logging.getLogger(__name__)

_LOG_LEVELS = {
    JobRunStatus.SUCCEEDED: logging.INFO,
    JobRunStatus.PARTIAL: logging.WARNING,
    JobRunStatus.FAILED: logging.ERROR,
    JobRunStatus.TIMED_OUT: logging.ERROR,
    JobRunStatus.CANCELLED: logging.WARNING,
    JobRunStatus.SKIPPED_LOCKED: logging.INFO,
    JobRunStatus.SKIPPED_RUNNING: logging.WARNING,
}


class JobCancelled(Exception):
    """Raised inside a job when the scheduler has asked it to stop (timeout or shutdown)."""


class JobAborted(Exception):
    """A job raised SystemExit, KeyboardInterrupt or similar; recorded as an ordinary failure."""


@dataclass(frozen=True)
class JobResult:
    records_processed: int | None = None
    # Items (profiles, notifications, records) that failed while the run carried on.
    items_failed: int = 0
    details: Mapping[str, Any] = field(default_factory=dict)


class JobContext:
    """What a job receives: its identity, a cancellation check, and database sessions."""

    def __init__(
        self,
        *,
        job_name: str,
        run_id: uuid.UUID,
        cancel_event: threading.Event,
        session_factory: Callable[..., Session],
        connection: Connection | None,
    ) -> None:
        self.job_name = job_name
        self.run_id = run_id
        self._cancel_event = cancel_event
        self._session_factory = session_factory
        self._connection = connection

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        """Call between units of work; raises JobCancelled once the scheduler asks to stop."""
        if self._cancel_event.is_set():
            raise JobCancelled(f"{self.job_name} run {self.run_id} was asked to stop")

    def wait_for_stop(self, timeout: float) -> bool:
        """An interruptible pause: returns True as soon as the scheduler asks the run to stop."""
        return self._cancel_event.wait(timeout)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """
        A new session for this run, never a request's session. On PostgreSQL it is bound to
        the connection holding the job lock, so the run's statement timeout applies to it.
        Rolled back if the block raises, and always closed.
        """
        if self._connection is not None:
            db = self._session_factory(bind=self._connection)
        else:
            db = self._session_factory()
        try:
            yield db
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


@dataclass(frozen=True)
class JobDefinition:
    name: str
    func: Callable[[JobContext], JobResult | None]
    interval_seconds: float
    timeout_seconds: float
    description: str = ""
    requires_network: bool = False

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0 or self.timeout_seconds <= 0:
            raise ValueError(f"Job {self.name!r} needs a positive interval and timeout")


def classify_error(exc: BaseException) -> tuple[str, str]:
    """
    (error type, first line of the message): enough to triage a failure without logging row
    data. A database error's full text carries the statement, its parameters and the
    driver's DETAIL line, so only the driver's first line is kept.
    """
    original = getattr(exc, "orig", None)
    source = original if isinstance(original, BaseException) else exc
    error_type = type(exc).__name__
    if source is not exc:
        error_type = f"{error_type}({type(source).__name__})"
    lines = str(source).strip().splitlines()
    return error_type, (lines[0][:200] if lines else "")


@dataclass
class _WorkerOutcome:
    locked: bool = False
    result: JobResult | None = None


@dataclass
class _InFlight:
    future: asyncio.Future
    cancel_event: threading.Event
    run_id: uuid.UUID | None = None
    # Set when the dispatcher stopped waiting (timeout grace expired or shutdown).
    abandoned: bool = False


class Scheduler:
    def __init__(
        self,
        jobs: Sequence[JobDefinition],
        *,
        session_factory: Callable[..., Session],
        lock_backend: JobLockBackend,
        max_concurrent_jobs: int = 2,
        startup_delay_seconds: float = 60.0,
        stagger_seconds: float = 15.0,
        cancel_grace_seconds: float = 30.0,
        shutdown_timeout_seconds: float = 5.0,
    ) -> None:
        names = [job.name for job in jobs]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate job names: {names}")
        if max_concurrent_jobs < 1:
            raise ValueError("max_concurrent_jobs must be at least 1")
        self._jobs: dict[str, JobDefinition] = {job.name: job for job in jobs}
        self._session_factory = session_factory
        self._lock_backend = lock_backend
        self._max_concurrent_jobs = max_concurrent_jobs
        self._startup_delay_seconds = startup_delay_seconds
        self._stagger_seconds = stagger_seconds
        self._cancel_grace_seconds = cancel_grace_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self.metrics = SchedulerMetrics(names)

        self._started = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._slots: asyncio.Semaphore | None = None
        self._runs_changed: asyncio.Condition | None = None
        self._loop_tasks: list[asyncio.Task] = []
        self._inflight: dict[str, _InFlight] = {}

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def job_names(self) -> tuple[str, ...]:
        return tuple(self._jobs)

    @property
    def is_running(self) -> bool:
        return self._started

    def job(self, name: str) -> JobDefinition:
        try:
            return self._jobs[name]
        except KeyError:
            raise ValueError(f"Unknown scheduled job {name!r}") from None

    def active_worker_count(self) -> int:
        """Runs whose worker thread has started and not yet finished."""
        return sum(
            1
            for inflight in self._inflight.values()
            if inflight.run_id is not None and not inflight.future.done()
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Starts one loop per job. A scheduler starts once; a second call is an error."""
        if self._started:
            raise RuntimeError("Scheduler is already running")
        self._bind_loop()
        self._stop_event.clear()
        self._started = True
        for index, job in enumerate(self._jobs.values()):
            first_delay = self._startup_delay_seconds + index * self._stagger_seconds
            self._loop_tasks.append(
                asyncio.create_task(self._job_loop(job, first_delay), name=f"scheduler:{job.name}")
            )
        logger.info(
            "Scheduler started with %d job(s): %s",
            len(self._jobs),
            ", ".join(
                f"{job.name} every {job.interval_seconds:g}s" for job in self._jobs.values()
            ),
            extra={"scheduler_jobs": list(self._jobs)},
        )

    async def stop(self) -> None:
        """Stops scheduling, signals running jobs, and waits briefly for them to unwind."""
        if not self._started:
            return
        self._stop_event.set()
        for task in self._loop_tasks:
            task.cancel()
        await asyncio.gather(*self._loop_tasks, return_exceptions=True)
        self._loop_tasks.clear()

        running = [inflight for inflight in self._inflight.values() if not inflight.future.done()]
        for inflight in running:
            inflight.cancel_event.set()
        if running:
            _, still_running = await asyncio.wait(
                [inflight.future for inflight in running],
                timeout=self._shutdown_timeout_seconds,
            )
            if still_running:
                for inflight in running:
                    if inflight.future in still_running:
                        inflight.abandoned = True
                logger.warning(
                    "Scheduler stopped with %d job run(s) still unwinding; they run in daemon "
                    "threads, and PostgreSQL releases their locks when the process exits",
                    len(still_running),
                )
        self._started = False
        logger.info("Scheduler stopped")

    async def run_job_now(self, name: str, trigger: str = "manual") -> JobRun:
        """Dispatches one run immediately, with the same locking and isolation as a scheduled run."""
        job = self.job(name)
        self._bind_loop()
        return await self._dispatch(job, trigger)

    async def wait_for_runs(self, name: str, count: int, timeout: float) -> None:
        """Waits until `count` runs of the job have been recorded (for tests and tooling)."""
        self.job(name)
        self._bind_loop()

        async def _wait() -> None:
            async with self._runs_changed:
                await self._runs_changed.wait_for(
                    lambda: self.metrics.get(name).runs_recorded >= count
                )

        await asyncio.wait_for(_wait(), timeout=timeout)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _bind_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is loop:
            return
        if self._started:
            raise RuntimeError("Scheduler is running on a different event loop")
        self._loop = loop
        self._stop_event = asyncio.Event()
        self._slots = asyncio.Semaphore(self._max_concurrent_jobs)
        self._runs_changed = asyncio.Condition()
        self._inflight = {}

    async def _job_loop(self, job: JobDefinition, first_delay: float) -> None:
        loop = asyncio.get_running_loop()
        next_start = loop.time() + first_delay
        while True:
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=max(0.0, next_start - loop.time())
                )
                return
            except TimeoutError:
                pass
            started = loop.time()
            try:
                await self._dispatch(job, "schedule")
            except asyncio.CancelledError:
                raise
            except Exception:
                # _dispatch records every outcome itself; this only keeps the loop alive.
                logger.exception("Scheduler loop for %s caught an unexpected error", job.name)
            next_start = max(started + job.interval_seconds, loop.time())

    async def _dispatch(self, job: JobDefinition, trigger: str) -> JobRun:
        current = self._inflight.get(job.name)
        if current is not None and not current.future.done():
            run = JobRun(job_name=job.name, trigger=trigger).finish(
                JobRunStatus.SKIPPED_RUNNING,
                details={"reason": "the previous run in this process has not finished"},
            )
            await self._record(run)
            return run

        future: asyncio.Future = self._loop.create_future()
        inflight = _InFlight(future=future, cancel_event=threading.Event())
        self._inflight[job.name] = inflight
        future.add_done_callback(functools.partial(self._on_worker_done, job.name, inflight))

        try:
            await self._slots.acquire()
        except asyncio.CancelledError:
            future.cancel()
            raise
        future.add_done_callback(lambda _future: self._slots.release())

        run = JobRun(job_name=job.name, trigger=trigger)
        inflight.run_id = run.run_id
        thread = threading.Thread(
            target=self._worker,
            args=(job, run.run_id, inflight.cancel_event, future),
            name=f"scheduler-{job.name}",
            daemon=True,
        )
        try:
            thread.start()
        except BaseException:
            future.cancel()
            raise

        try:
            outcome: _WorkerOutcome = await asyncio.wait_for(
                asyncio.shield(future), timeout=job.timeout_seconds
            )
        except TimeoutError:
            inflight.cancel_event.set()
            run.finish(
                JobRunStatus.TIMED_OUT,
                error_type="Timeout",
                error_message=f"exceeded its {job.timeout_seconds:g}s budget",
            )
            await self._record(run)
            await self._await_unwind(job, run, inflight)
            return run
        except asyncio.CancelledError:
            # stop() waits for the worker to unwind; it marks the run abandoned only if the
            # worker outlives that wait.
            inflight.cancel_event.set()
            run.finish(JobRunStatus.CANCELLED, error_type="SchedulerShutdown")
            self._record_sync(run)
            raise
        except Exception as exc:
            error_type, message = classify_error(exc)
            run.finish(JobRunStatus.FAILED, error_type=error_type, error_message=message)
            logger.debug("Scheduled job %s run %s failed", job.name, run.run_id, exc_info=exc)
            await self._record(run)
            return run

        if outcome.locked:
            run.finish(
                JobRunStatus.SKIPPED_LOCKED,
                details={"reason": "another holder has the job's lock"},
            )
        else:
            result = outcome.result
            run.finish(
                JobRunStatus.PARTIAL if result.items_failed else JobRunStatus.SUCCEEDED,
                records_processed=result.records_processed,
                items_failed=result.items_failed,
                details=dict(result.details),
            )
        await self._record(run)
        return run

    async def _await_unwind(self, job: JobDefinition, run: JobRun, inflight: _InFlight) -> None:
        """After a timeout, gives the run a bounded chance to reach a safe point and unlock."""
        try:
            await asyncio.wait_for(asyncio.shield(inflight.future), timeout=self._cancel_grace_seconds)
        except TimeoutError:
            inflight.abandoned = True
            logger.warning(
                "Scheduled job %s run %s is still running after its timeout; it keeps its lock "
                "until it returns, so later runs are skipped rather than overlapped",
                job.name,
                run.run_id,
                extra={"job_name": job.name, "run_id": str(run.run_id)},
            )
        except Exception:
            # Expected: the run stopped with JobCancelled (or failed while unwinding).
            pass

    def _worker(
        self,
        job: JobDefinition,
        run_id: uuid.UUID,
        cancel_event: threading.Event,
        future: asyncio.Future,
    ) -> None:
        # Tags every log line the run's services emit with the run id (the correlation slot
        # that HTTP requests fill with X-Request-ID).
        token = request_id_ctx.set(f"{job.name}:{run_id}")
        try:
            outcome = self._run_locked(job, run_id, cancel_event)
        except Exception as exc:
            self._resolve(future, exception=exc)
        except BaseException as exc:
            # Re-raised on the event loop, SystemExit or KeyboardInterrupt would stop the
            # whole server; a job cannot be allowed to do that.
            self._resolve(future, exception=JobAborted(f"job raised {type(exc).__name__}"))
        else:
            self._resolve(future, result=outcome)
        finally:
            request_id_ctx.reset(token)

    def _run_locked(
        self,
        job: JobDefinition,
        run_id: uuid.UUID,
        cancel_event: threading.Event,
    ) -> _WorkerOutcome:
        handle = self._lock_backend.try_acquire(
            job.name, statement_timeout_seconds=job.timeout_seconds
        )
        if handle is None:
            return _WorkerOutcome(locked=True)
        try:
            logger.info(
                "Scheduled job %s run %s started",
                job.name,
                run_id,
                extra={"job_name": job.name, "run_id": str(run_id)},
            )
            context = JobContext(
                job_name=job.name,
                run_id=run_id,
                cancel_event=cancel_event,
                session_factory=self._session_factory,
                connection=handle.connection,
            )
            context.check_cancelled()
            result = job.func(context)
            return _WorkerOutcome(result=result if isinstance(result, JobResult) else JobResult())
        finally:
            handle.release()

    @staticmethod
    def _resolve(
        future: asyncio.Future,
        *,
        result: _WorkerOutcome | None = None,
        exception: BaseException | None = None,
    ) -> None:
        def _complete() -> None:
            if future.done():
                return
            if exception is not None:
                future.set_exception(exception)
            else:
                future.set_result(result)

        try:
            future.get_loop().call_soon_threadsafe(_complete)
        except RuntimeError:
            # The event loop has closed (process shutdown); nobody is waiting any more.
            pass

    def _on_worker_done(self, job_name: str, inflight: _InFlight, future: asyncio.Future) -> None:
        if future.cancelled():
            return
        error = future.exception()  # also marks a late exception as retrieved
        if inflight.abandoned:
            logger.warning(
                "Scheduled job %s run %s finished after the scheduler stopped waiting (%s); "
                "its lock is released",
                job_name,
                inflight.run_id,
                "stopped" if isinstance(error, JobCancelled) else type(error).__name__ if error else "completed",
                extra={"job_name": job_name, "run_id": str(inflight.run_id)},
            )

    def _record_sync(self, run: JobRun) -> None:
        self.metrics.record(run)
        fields = run.log_fields()
        token = request_id_ctx.set(f"{run.job_name}:{run.run_id}")
        try:
            message = "Scheduled job %s run %s %s in %.3fs (records=%s, failed items=%s)"
            args: tuple[Any, ...] = (
                run.job_name,
                run.run_id,
                run.status.value,
                run.duration_seconds or 0.0,
                run.records_processed,
                run.items_failed,
            )
            if run.error_type:
                message += ": %s %s"
                args += (run.error_type, run.error_message or "")
            elif run.status in (JobRunStatus.SKIPPED_LOCKED, JobRunStatus.SKIPPED_RUNNING):
                message += ": %s"
                args += (run.details.get("reason", ""),)
            logger.log(_LOG_LEVELS[run.status], message, *args, extra=fields)
        finally:
            request_id_ctx.reset(token)

    async def _record(self, run: JobRun) -> None:
        self._record_sync(run)
        async with self._runs_changed:
            self._runs_changed.notify_all()
