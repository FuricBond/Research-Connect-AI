"""
Phase 6.3 — The scheduled jobs.

The five jobs from the Phase 6 job matrix (rows 17-21). Each is a thin adapter: it opens its
own database scope, calls one existing entry point, commits where that entry point leaves the
transaction to its caller, and reports what happened. No aggregation, governance, ranking,
risk, reminder, expiry or ingestion logic lives here.

    Job                       Entry point                                              Network
    opportunity_refresh       scrapers.pipelines.collect_opportunities.run_pipeline      yes
    adaptive_signal_refresh   AdaptivePreferenceSignalService.recompute_adaptive_signals no
    governance_refresh        PersonalizationGovernanceService.recompute_governance     no
    reminder_dispatch         ReminderSchedulerService.run_scheduled_reminders          no
    deadline_expiry           scrapers.expiration.manager.expire_past_opportunities     no

Which researchers the profile-scoped jobs process
    Scheduled work is proactive, so it only touches a researcher when the state it maintains
    is actually in use under their own Phase 5.9 controls (no settings row means the
    documented defaults, all on):
      - adaptive_signal_refresh: researchers with interactions or signals, and with
        personalization, adaptive signals and feedback learning all on. "Feedback learning
        off" means new behaviour must not be aggregated, so their signals are left as they are.
      - governance_refresh: researchers with signals or a governance evaluation, and with
        personalization and adaptive signals on. The gate is refreshed even when feedback
        learning is off, because it is what damps the signals that still apply.
    These are selection rules only. The controls are still enforced where personalization is
    applied, and the on-demand recompute endpoints behave exactly as before.
"""
from __future__ import annotations

from collections.abc import Callable
import functools
import logging
import uuid

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.models.adaptive_signal import AdaptivePreferenceSignalModel
from app.models.personalization_governance import PersonalizationDriftEvaluationModel
from app.models.personalization_transparency import ResearcherPersonalizationSettingsModel
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import ResearcherInteractionModel
from app.scheduler.locks import profile_lock_key
from app.scheduler.scheduler import JobContext, JobDefinition, JobResult, classify_error
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService
from app.services.personalization_governance_service import PersonalizationGovernanceService
from app.services.reminder_scheduler_service import ReminderSchedulerService

logger = logging.getLogger(__name__)

# Job names are stable identifiers: they name the logs and metrics and derive the lock keys.
OPPORTUNITY_REFRESH = "opportunity_refresh"
ADAPTIVE_SIGNAL_REFRESH = "adaptive_signal_refresh"
GOVERNANCE_REFRESH = "governance_refresh"
REMINDER_DISPATCH = "reminder_dispatch"
DEADLINE_EXPIRY = "deadline_expiry"

APPROVED_JOB_NAMES = (
    OPPORTUNITY_REFRESH,
    ADAPTIVE_SIGNAL_REFRESH,
    GOVERNANCE_REFRESH,
    REMINDER_DISPATCH,
    DEADLINE_EXPIRY,
)

# Per-run budgets. Generous against measured cost (a profile refresh is tens of milliseconds;
# a reminder pass is under a millisecond per researcher) so that they catch hangs, not load.
# The ingestion budget covers WikiCFP's 5 s crawl delay per page and the HTTP client's
# 10 s connect / 20 s read timeouts with its retries.
OPPORTUNITY_REFRESH_TIMEOUT_SECONDS = 1_800
ADAPTIVE_SIGNAL_REFRESH_TIMEOUT_SECONDS = 1_800
GOVERNANCE_REFRESH_TIMEOUT_SECONDS = 1_800
REMINDER_DISPATCH_TIMEOUT_SECONDS = 600
DEADLINE_EXPIRY_TIMEOUT_SECONDS = 300

# Profiles loaded per enumeration query; each batch runs in one session that is then closed.
PROFILE_BATCH_SIZE = 100


# ── Profile selection ─────────────────────────────────────────────────────────


def _without_opt_out(*controls: ColumnElement[bool]) -> ColumnElement[bool]:
    """True unless the researcher's settings row switches one of `controls` off."""
    settings = ResearcherPersonalizationSettingsModel
    return ~exists().where(
        settings.profile_id == ResearchProfileModel.id,
        or_(*(control.is_(False) for control in controls)),
    )


def adaptive_refresh_candidates() -> ColumnElement[bool]:
    settings = ResearcherPersonalizationSettingsModel
    has_evidence = or_(
        exists().where(ResearcherInteractionModel.profile_id == ResearchProfileModel.id),
        exists().where(AdaptivePreferenceSignalModel.profile_id == ResearchProfileModel.id),
    )
    return and_(
        has_evidence,
        _without_opt_out(
            settings.personalization_enabled,
            settings.adaptive_signals_enabled,
            settings.feedback_learning_enabled,
        ),
    )


def governance_refresh_candidates() -> ColumnElement[bool]:
    settings = ResearcherPersonalizationSettingsModel
    has_gate_state = or_(
        exists().where(AdaptivePreferenceSignalModel.profile_id == ResearchProfileModel.id),
        exists().where(PersonalizationDriftEvaluationModel.profile_id == ResearchProfileModel.id),
    )
    return and_(
        has_gate_state,
        _without_opt_out(settings.personalization_enabled, settings.adaptive_signals_enabled),
    )


def _next_profile_batch(
    db: Session,
    criterion: ColumnElement[bool],
    after: uuid.UUID | None,
    batch_size: int,
) -> list[uuid.UUID]:
    """Keyset pagination over profile ids: stable, and never loads more than one batch."""
    stmt = (
        select(ResearchProfileModel.id)
        .where(criterion)
        .order_by(ResearchProfileModel.id)
        .limit(batch_size)
    )
    if after is not None:
        stmt = stmt.where(ResearchProfileModel.id > after)
    return list(db.execute(stmt).scalars())


def _serialize_profile_work(db: Session, profile_id: uuid.UUID) -> None:
    """
    Holds a transaction-scoped lock on the profile (PostgreSQL only) until the unit of work
    commits. adaptive_signal_refresh also recomputes governance (P1-8), so without it the two
    jobs could evaluate one profile concurrently and both append the same governance
    transition event.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(profile_lock_key(profile_id))))


def _run_per_profile(
    context: JobContext,
    criterion: Callable[[], ColumnElement[bool]],
    process: Callable[[Session, uuid.UUID], object],
    batch_size: int,
) -> JobResult:
    """
    Runs `process` for every matching profile, one committed unit of work per profile. A
    profile that fails is rolled back, counted and skipped; the run carries on. Stops at the
    next profile boundary when the scheduler asks it to.
    """
    processed = failed = 0
    after: uuid.UUID | None = None
    while True:
        context.check_cancelled()
        with context.session() as db:
            batch = _next_profile_batch(db, criterion(), after, batch_size)
            for profile_id in batch:
                context.check_cancelled()
                try:
                    _serialize_profile_work(db, profile_id)
                    process(db, profile_id)
                    db.commit()
                    processed += 1
                except Exception as exc:
                    db.rollback()
                    failed += 1
                    error_type, _ = classify_error(exc)
                    logger.warning(
                        "Scheduled job %s skipped profile %s after %s",
                        context.job_name,
                        profile_id,
                        error_type,
                        extra={
                            "job_name": context.job_name,
                            "run_id": str(context.run_id),
                            "profile_id": str(profile_id),
                            "error_type": error_type,
                        },
                    )
        if len(batch) < batch_size:
            break
        after = batch[-1]
    return JobResult(
        records_processed=processed,
        items_failed=failed,
        details={"profiles_processed": processed, "profiles_failed": failed},
    )


# ── Job adapters ──────────────────────────────────────────────────────────────


def run_adaptive_signal_refresh(context: JobContext, *, batch_size: int = PROFILE_BATCH_SIZE) -> JobResult:
    """Matrix row 18. The service applies the P1-1 reset cutoff and refreshes governance (P1-8)."""
    return _run_per_profile(
        context,
        adaptive_refresh_candidates,
        lambda db, profile_id: AdaptivePreferenceSignalService.recompute_adaptive_signals(
            db=db, profile_id=profile_id
        ),
        batch_size,
    )


def run_governance_refresh(context: JobContext, *, batch_size: int = PROFILE_BATCH_SIZE) -> JobResult:
    """Matrix row 19. A failed evaluation is rolled back, leaving the previous gate in force."""
    return _run_per_profile(
        context,
        governance_refresh_candidates,
        lambda db, profile_id: PersonalizationGovernanceService.recompute_governance(
            db=db, profile_id=profile_id
        ),
        batch_size,
    )


def run_reminder_dispatch(context: JobContext) -> JobResult:
    """
    Matrix row 21. The service loads, evaluates and commits its own pass; notifications are
    deduplicated by their unique deduplication_key, so repeating a pass creates none twice.
    """
    context.check_cancelled()
    with context.session() as db:
        summary = ReminderSchedulerService.run_scheduled_reminders(db)
    return JobResult(
        records_processed=summary.created_notifications,
        items_failed=len(summary.errors),
        details={
            "discovered_reminders": summary.discovered_reminders,
            "created_notifications": summary.created_notifications,
            "delivered_notifications": summary.delivered_notifications,
            "skipped_duplicates": summary.skipped_duplicates,
            "cancelled_obsolete": summary.cancelled_obsolete,
            "errors": len(summary.errors),
        },
    )


def run_deadline_expiry(context: JobContext) -> JobResult:
    """Matrix row 20. The sweep flushes and leaves the commit to its caller."""
    from scrapers.expiration.manager import expire_past_opportunities

    context.check_cancelled()
    with context.session() as db:
        expired = expire_past_opportunities(db)
        db.commit()
    return JobResult(records_processed=expired, details={"expired": expired})


def run_opportunity_refresh(context: JobContext, *, topic: str, max_pages: int) -> JobResult:
    """
    Matrix row 17: outbound requests to WikiCFP. The pipeline opens and commits its own
    session. Its expired-record sweep is left off; deadline_expiry does that on its own
    schedule.
    """
    # Imported here so that loading the backend never imports the scraping stack.
    from scrapers.pipelines.collect_opportunities import run_pipeline

    context.check_cancelled()
    stats = run_pipeline(topic=topic, max_pages=max_pages, dry_run=False, sweep_expired=False)
    return JobResult(
        records_processed=int(stats.get("inserted", 0)) + int(stats.get("updated", 0)),
        items_failed=int(stats.get("errors", 0)),
        details={
            key: stats.get(key)
            for key in (
                "topic",
                "pages_fetched",
                "parsed",
                "valid",
                "invalid",
                "inserted",
                "updated",
                "unchanged",
                "duplicates",
                "errors",
                "run_id",
            )
        },
    )


# ── Registry ──────────────────────────────────────────────────────────────────


def build_default_jobs(
    cfg: Settings,
    *,
    profile_batch_size: int = PROFILE_BATCH_SIZE,
) -> list[JobDefinition]:
    """
    The approved jobs, in dispatch order. The network job is included only when
    SCHEDULER_OPPORTUNITY_REFRESH_ENABLED is set, and it goes last.
    """
    jobs = [
        JobDefinition(
            name=DEADLINE_EXPIRY,
            func=run_deadline_expiry,
            interval_seconds=cfg.scheduler_deadline_expiry_interval_seconds,
            timeout_seconds=DEADLINE_EXPIRY_TIMEOUT_SECONDS,
            description="Mark ACTIVE/UNVERIFIED opportunities past their deadline as EXPIRED",
        ),
        JobDefinition(
            name=REMINDER_DISPATCH,
            func=run_reminder_dispatch,
            interval_seconds=cfg.scheduler_reminder_interval_seconds,
            timeout_seconds=REMINDER_DISPATCH_TIMEOUT_SECONDS,
            description="Create and deliver due deadline reminders",
        ),
        JobDefinition(
            name=ADAPTIVE_SIGNAL_REFRESH,
            func=functools.partial(run_adaptive_signal_refresh, batch_size=profile_batch_size),
            interval_seconds=cfg.scheduler_adaptive_refresh_interval_seconds,
            timeout_seconds=ADAPTIVE_SIGNAL_REFRESH_TIMEOUT_SECONDS,
            description="Recompute adaptive preference signals (and their governance) per researcher",
        ),
        JobDefinition(
            name=GOVERNANCE_REFRESH,
            func=functools.partial(run_governance_refresh, batch_size=profile_batch_size),
            interval_seconds=cfg.scheduler_governance_refresh_interval_seconds,
            timeout_seconds=GOVERNANCE_REFRESH_TIMEOUT_SECONDS,
            description="Recompute personalization health, drift and the governance gate per researcher",
        ),
    ]
    if cfg.scheduler_opportunity_refresh_enabled:
        jobs.append(
            JobDefinition(
                name=OPPORTUNITY_REFRESH,
                func=functools.partial(
                    run_opportunity_refresh,
                    topic=cfg.scheduler_opportunity_refresh_topic,
                    max_pages=cfg.scheduler_opportunity_refresh_max_pages,
                ),
                interval_seconds=cfg.scheduler_opportunity_refresh_interval_seconds,
                timeout_seconds=OPPORTUNITY_REFRESH_TIMEOUT_SECONDS,
                description="Ingest opportunities from WikiCFP",
                requires_network=True,
            )
        )
    return jobs
