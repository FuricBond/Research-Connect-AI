"""
Phase 6.3 — Locks that keep a scheduled job from running twice at once.

Several backend processes (uvicorn workers, replicas) can each run a scheduler. Before a run
does any work it takes a lock named after its job and skips the run if another holder has
it; it never waits.

On PostgreSQL the lock is a session-level advisory lock held on a connection dedicated to
the run. Every process sharing the database sees it, the run's own session is bound to the
same connection, and if the process dies the server drops the lock with the connection.
Everywhere else (the SQLite test databases) there is only one process, and an in-process
lock gives the same semantics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import logging
import threading
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)

_JOB_LOCK_NAMESPACE = "researchconnect-ai:scheduler:job:"
_PROFILE_LOCK_NAMESPACE = "researchconnect-ai:scheduler:profile:"


def _signed_64bit_key(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def job_lock_key(job_name: str) -> int:
    """Stable advisory-lock key for a job: the same in every process and on every restart."""
    return _signed_64bit_key(_JOB_LOCK_NAMESPACE + job_name)


def profile_lock_key(profile_id: uuid.UUID) -> int:
    """Stable advisory-lock key serializing scheduled personalization work on one profile."""
    return _signed_64bit_key(_PROFILE_LOCK_NAMESPACE + str(profile_id))


class JobLockHandle(ABC):
    """A held job lock. `connection` is the connection holding it, when there is one."""

    connection: Connection | None = None

    @abstractmethod
    def release(self) -> None:
        """Releases the lock. Never raises."""


class JobLockBackend(ABC):
    @abstractmethod
    def try_acquire(
        self,
        job_name: str,
        statement_timeout_seconds: float | None = None,
    ) -> JobLockHandle | None:
        """Takes the job's lock without waiting; returns None when another holder has it."""


class _PostgresAdvisoryLockHandle(JobLockHandle):
    def __init__(self, connection: Connection, job_name: str, key: int) -> None:
        self.connection = connection
        self._job_name = job_name
        self._key = key

    def release(self) -> None:
        connection = self.connection
        try:
            # Abandon anything the run left open, clear its statement timeout, then unlock.
            connection.rollback()
            connection.execute(text("RESET statement_timeout"))
            released = connection.execute(select(func.pg_advisory_unlock(self._key))).scalar_one()
            connection.commit()
            if not released:
                logger.warning("Scheduler lock for job %s was not held at release", self._job_name)
        except Exception as exc:
            # Closing the underlying DBAPI connection makes the server drop the lock.
            logger.warning(
                "Scheduler lock for job %s could not be released cleanly (%s); "
                "discarding its connection so the server drops the lock",
                self._job_name,
                type(exc).__name__,
            )
            connection.invalidate()
        finally:
            connection.close()


class PostgresAdvisoryLockBackend(JobLockBackend):
    """Cross-process job locks: session-level PostgreSQL advisory locks."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def try_acquire(
        self,
        job_name: str,
        statement_timeout_seconds: float | None = None,
    ) -> JobLockHandle | None:
        key = job_lock_key(job_name)
        connection = self._engine.connect()
        try:
            acquired = connection.execute(select(func.pg_try_advisory_lock(key))).scalar_one()
            if not acquired:
                connection.rollback()
                connection.close()
                return None
            if statement_timeout_seconds:
                # Session-level, so it bounds every statement the run issues on this
                # connection; RESET on release before the connection returns to the pool.
                connection.execute(
                    text("SELECT set_config('statement_timeout', :value, false)"),
                    {"value": str(max(1, int(statement_timeout_seconds * 1000)))},
                )
            # End the implicit transaction: the lock and the setting are session-scoped, and
            # a session bound to this connection must begin (and own) its own transactions.
            connection.commit()
        except Exception:
            connection.invalidate()
            connection.close()
            raise
        return _PostgresAdvisoryLockHandle(connection, job_name, key)


class _LocalLockHandle(JobLockHandle):
    def __init__(self, backend: LocalLockBackend, job_name: str) -> None:
        self._backend = backend
        self._job_name = job_name

    def release(self) -> None:
        self._backend._release(self._job_name)


class LocalLockBackend(JobLockBackend):
    """In-process job locks, for databases that only one process uses (SQLite tests)."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._held: set[str] = set()

    def try_acquire(
        self,
        job_name: str,
        statement_timeout_seconds: float | None = None,
    ) -> JobLockHandle | None:
        with self._guard:
            if job_name in self._held:
                return None
            self._held.add(job_name)
        return _LocalLockHandle(self, job_name)

    def is_held(self, job_name: str) -> bool:
        with self._guard:
            return job_name in self._held

    def _release(self, job_name: str) -> None:
        with self._guard:
            self._held.discard(job_name)


def lock_backend_for(engine: Engine) -> JobLockBackend:
    """Advisory locks on PostgreSQL; in-process locks for single-process test databases."""
    if engine.dialect.name == "postgresql":
        return PostgresAdvisoryLockBackend(engine)
    return LocalLockBackend()
