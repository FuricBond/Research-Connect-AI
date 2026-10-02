"""
Research refresh — the research load lock.

Manual OpenAlex loads (``collect_openalex``) and the scheduled ``research_refresh`` job
write the same research_works rows, so they share one lock: the job's PostgreSQL advisory
lock. The scheduler takes it before it runs the job; a manual load takes it here, for its
whole run. Whoever holds it, the other waits for the next turn instead of racing.

Everything is imported inside the function, so importing this module needs no database
and a dry run never touches one.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.scheduler.locks import JobLockHandle


def acquire_research_lock() -> JobLockHandle | None:
    """
    Take the research load lock without waiting.

    Returns the held lock, to be released by the caller, or None when another research
    load or the scheduled research_refresh job holds it.
    """
    from app.db.session import engine
    from app.scheduler.jobs import RESEARCH_REFRESH
    from app.scheduler.locks import lock_backend_for

    return lock_backend_for(engine).try_acquire(RESEARCH_REFRESH)
