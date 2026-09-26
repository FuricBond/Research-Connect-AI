"""
Phase 6.3 — Background scheduler and scheduled jobs.

Deterministic by construction: jobs are triggered with `run_job_now` rather than by waiting
out an interval, and blocking jobs are coordinated with threading events. The few
loop-driven tests use a zero startup delay and wait for recorded runs, not for time.

  A  disabled by default               K  reset boundary (P1-1)
  B  starts when enabled, once         L  consent (Phase 5.9 controls)
  C  graceful shutdown                 M  governance failure stays fail-safe (P1-5/P1-8)
  D  exactly the approved jobs         N  query counts at 10 / 50 / 100 profiles
  E  jobs call the existing services   O  no network outside the opt-in job
  F  failure isolation                 P  run ids
  G  overlap prevention                Q  metrics and logging
  H  lock released after a failure     R  two scheduler instances (PostgreSQL advisory locks)
  I  lock released after a timeout     S  one service failing leaves the others running
  J  idempotency
Plus: session hygiene, work kept off the event loop, bounded concurrency, and per-profile
failure isolation.
"""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone
import logging
import os
import subprocess
import sys
import threading
import time
import uuid

import httpx
import pytest
import requests
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.logging_config import request_id_ctx
from app.db.types import TSVector, Vector

# Imported at collection, like the API suites: importing app.main configures logging, and
# the conftest quiets it for the session only after collection.
from app.main import app  # noqa: F401
from app.models.adaptive_signal import (
    AdaptiveEvidenceState,
    AdaptivePreferenceSignalModel,
    AdaptiveSignalDimension,
)
from app.models.base import Base
from app.models.notification import DeliveryChannel, NotificationModel, OffsetUnit
from app.models.opportunity import OpportunityModel
from app.models.personalization_governance import (
    GovernanceGateState,
    PersonalizationDriftEvaluationModel,
    PersonalizationGovernanceEventModel,
    PersonalizationHealthState,
)
from app.models.personalization_transparency import (
    PersonalizationControlEventModel,
    ResearcherPersonalizationSettingsModel,
)
from app.models.research_profile import ResearchProfileModel
from app.models.researcher_interaction import InteractionType, ResearcherInteractionModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.user import UserModel
from app.personalization.governance_engine import PersonalizationGovernanceEngine
from app.scheduler import lifecycle
from app.scheduler.jobs import (
    ADAPTIVE_SIGNAL_REFRESH,
    APPROVED_JOB_NAMES,
    DEADLINE_EXPIRY,
    GOVERNANCE_REFRESH,
    OPPORTUNITY_REFRESH,
    REMINDER_DISPATCH,
    build_default_jobs,
)
from app.scheduler.locks import LocalLockBackend, PostgresAdvisoryLockBackend, job_lock_key
from app.scheduler.metrics import JobRunStatus
from app.scheduler.scheduler import JobDefinition, JobResult, Scheduler, classify_error
from app.schemas.notification import ReminderRuleCreate
from app.services.adaptive_signal_service import AdaptivePreferenceSignalService
from app.services.notification_service import NotificationService
from app.services.personalization_governance_service import PersonalizationGovernanceService
from app.services.personalization_transparency_service import (
    PersonalizationTransparencyService,
)
from app.services.reminder_scheduler_service import ReminderRunSummary, ReminderSchedulerService

# The same SQLite stand-ins every other suite registers (these registrations are global).
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

SUCCEEDED = JobRunStatus.SUCCEEDED


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def _sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def engine():
    eng = _sqlite_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def make_scheduler(jobs, session_factory, *, lock_backend=None, **overrides) -> Scheduler:
    options = dict(
        startup_delay_seconds=0.0,
        stagger_seconds=0.0,
        cancel_grace_seconds=5.0,
        shutdown_timeout_seconds=5.0,
    )
    options.update(overrides)
    return Scheduler(
        jobs,
        session_factory=session_factory,
        lock_backend=lock_backend or LocalLockBackend(),
        **options,
    )


def job(name, func, *, interval=3600.0, timeout=30.0) -> JobDefinition:
    return JobDefinition(name=name, func=func, interval_seconds=interval, timeout_seconds=timeout)


def run_now(scheduler: Scheduler, name: str):
    return asyncio.run(scheduler.run_job_now(name))


def run_all(scheduler: Scheduler, names) -> dict:
    async def _all():
        return {name: await scheduler.run_job_now(name) for name in names}

    return asyncio.run(_all())


def join_scheduler_threads(timeout: float = 10.0) -> None:
    for thread in threading.enumerate():
        if thread.name.startswith("scheduler-"):
            thread.join(timeout)


class Gate:
    """A job body that signals when it starts and blocks until released (ignores cancellation)."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def __call__(self, context) -> JobResult:
        self.calls += 1
        self.entered.set()
        self.release.wait(timeout=30)
        return JobResult(records_processed=1)


def add_profile(db: Session, label: str = "researcher") -> ResearchProfileModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=f"{label}.{uuid.uuid4().hex[:10]}@university.edu",
        hashed_password="hashed",
        full_name=f"Dr. {label.title()}",
        role="FACULTY",
        is_active=True,
    )
    db.add(user)
    db.flush()
    profile = ResearchProfileModel(
        id=uuid.uuid4(),
        user_id=user.id,
        academic_status="FACULTY",
        institution="Test University",
        keywords=["machine learning"],
        target_opportunity_types=["CONFERENCE"],
    )
    db.add(profile)
    db.commit()
    return profile


def add_opportunity(
    db: Session,
    title: str,
    *,
    days_until_deadline: float = 45,
    opportunity_type: str = "CONFERENCE",
) -> OpportunityModel:
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title=title,
        opportunity_type=opportunity_type,
        status="ACTIVE",
        delivery_mode="ONLINE",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=days_until_deadline),
        is_predatory_flag=False,
    )
    db.add(opp)
    db.commit()
    return opp


def add_interactions(
    db: Session,
    profile: ResearchProfileModel,
    opportunity: OpportunityModel,
    count: int,
    *,
    created_at: datetime | None = None,
) -> None:
    moment = created_at or (datetime.now(timezone.utc) - timedelta(days=1))
    for _ in range(count):
        db.add(
            ResearcherInteractionModel(
                id=uuid.uuid4(),
                profile_id=profile.id,
                opportunity_id=opportunity.id,
                interaction_type=InteractionType.INTERESTED.value,
                client_event_id=f"evt-{uuid.uuid4().hex}",
                created_at=moment,
            )
        )
    db.commit()


def add_signal(db: Session, profile: ResearchProfileModel, *, evidence: int = 10) -> AdaptivePreferenceSignalModel:
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signal = AdaptivePreferenceSignalModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        dimension=AdaptiveSignalDimension.OPPORTUNITY_TYPE.value,
        signal_value="CONFERENCE",
        positive_evidence_count=evidence,
        negative_evidence_count=0,
        total_evidence_count=evidence,
        decay_adjusted_positive_weight=6.0,
        decay_adjusted_negative_weight=0.0,
        weighted_signal_strength=0.8,
        confidence=0.9,
        evidence_state=AdaptiveEvidenceState.STRONG.value,
        latest_evidence_timestamp=moment,
        deterministic_explanation="seeded adaptive signal",
        created_at=moment,
        updated_at=moment,
    )
    db.add(signal)
    db.commit()
    return signal


def set_controls(db: Session, profile: ResearchProfileModel, **flags: bool) -> None:
    db.add(ResearcherPersonalizationSettingsModel(id=uuid.uuid4(), profile_id=profile.id, **flags))
    db.commit()


def signals_of(db: Session, profile: ResearchProfileModel) -> list[AdaptivePreferenceSignalModel]:
    db.expire_all()
    return list(
        db.execute(
            select(AdaptivePreferenceSignalModel).where(
                AdaptivePreferenceSignalModel.profile_id == profile.id
            )
        ).scalars()
    )


def count_rows(db: Session, model, **where) -> int:
    db.expire_all()
    stmt = select(func.count()).select_from(model)
    for column, value in where.items():
        stmt = stmt.where(getattr(model, column) == value)
    return db.execute(stmt).scalar_one()


# ── A. Disabled by default ────────────────────────────────────────────────────


def test_a_scheduler_and_network_ingestion_are_off_by_default(monkeypatch):
    for variable in ("SCHEDULER_ENABLED", "SCHEDULER_OPPORTUNITY_REFRESH_ENABLED"):
        monkeypatch.delenv(variable, raising=False)
    assert Settings.model_fields["scheduler_enabled"].default is False
    assert Settings.model_fields["scheduler_opportunity_refresh_enabled"].default is False
    fresh = Settings(_env_file=None)
    assert fresh.scheduler_enabled is False
    assert fresh.scheduler_opportunity_refresh_enabled is False


def test_a_disabled_application_starts_no_scheduler(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(
        lifecycle, "build_scheduler", lambda cfg: pytest.fail("a scheduler was built while disabled")
    )
    with TestClient(app) as client:
        assert client.app.state.scheduler is None
        assert client.get("/api/health").status_code == 200
        assert not [t for t in threading.enumerate() if t.name.startswith("scheduler-")]


# ── B. Starts when enabled, exactly once ──────────────────────────────────────


def test_b_enabled_application_starts_the_scheduler_once_and_stops_it(monkeypatch, session_factory):
    from fastapi.testclient import TestClient

    from app.main import app

    dispatched = threading.Event()
    built: list[Scheduler] = []

    def probe(context):
        dispatched.set()
        return JobResult(records_processed=0)

    def build(cfg):
        scheduler = make_scheduler([job("probe", probe)], session_factory)
        built.append(scheduler)
        return scheduler

    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(lifecycle, "build_scheduler", build)
    with TestClient(app) as client:
        scheduler = client.app.state.scheduler
        assert scheduler is built[0]
        assert scheduler.is_running
        assert dispatched.wait(timeout=10), "the enabled scheduler never dispatched its job"

    assert len(built) == 1
    assert not built[0].is_running
    assert client.app.state.scheduler is None


def test_b_a_scheduler_cannot_be_started_twice(session_factory):
    async def scenario():
        scheduler = make_scheduler(
            [job("probe", lambda context: None)], session_factory, startup_delay_seconds=3600
        )
        await scheduler.start()
        try:
            with pytest.raises(RuntimeError):
                await scheduler.start()
        finally:
            await scheduler.stop()

    asyncio.run(scenario())


# ── C. Graceful shutdown ──────────────────────────────────────────────────────


def test_c_stop_ends_the_loops_stops_running_jobs_and_releases_their_locks(session_factory):
    locks = LocalLockBackend()
    entered, finished = threading.Event(), threading.Event()

    def long_running(context):
        entered.set()
        try:
            context.wait_for_stop(30)
            context.check_cancelled()
        finally:
            finished.set()

    async def scenario():
        scheduler = make_scheduler([job("long", long_running, timeout=60)], session_factory, lock_backend=locks)
        await scheduler.start()
        assert await asyncio.to_thread(entered.wait, 10)
        assert locks.is_held("long")
        started = time.monotonic()
        await scheduler.stop()
        elapsed = time.monotonic() - started
        leftover = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        return scheduler, elapsed, leftover

    scheduler, elapsed, leftover = asyncio.run(scenario())
    join_scheduler_threads()
    assert leftover == []
    assert elapsed < 5
    assert finished.is_set()
    assert not locks.is_held("long")
    assert not scheduler.is_running
    assert scheduler.metrics.get("long").cancellations == 1
    assert not [t for t in threading.enumerate() if t.name.startswith("scheduler-") and t.is_alive()]


# ── D. Exactly the approved jobs ──────────────────────────────────────────────


def test_d_exactly_the_approved_phase6_jobs_are_registered():
    cfg = Settings(_env_file=None)
    default_jobs = build_default_jobs(cfg)
    assert [j.name for j in default_jobs] == [
        DEADLINE_EXPIRY,
        REMINDER_DISPATCH,
        ADAPTIVE_SIGNAL_REFRESH,
        GOVERNANCE_REFRESH,
    ]

    with_network = build_default_jobs(cfg.model_copy(update={"scheduler_opportunity_refresh_enabled": True}))
    assert len(APPROVED_JOB_NAMES) == 5
    assert sorted(j.name for j in with_network) == sorted(APPROVED_JOB_NAMES)
    assert [j.name for j in with_network if j.requires_network] == [OPPORTUNITY_REFRESH]
    assert {j.name: j.interval_seconds for j in with_network} == {
        DEADLINE_EXPIRY: cfg.scheduler_deadline_expiry_interval_seconds,
        REMINDER_DISPATCH: cfg.scheduler_reminder_interval_seconds,
        ADAPTIVE_SIGNAL_REFRESH: cfg.scheduler_adaptive_refresh_interval_seconds,
        GOVERNANCE_REFRESH: cfg.scheduler_governance_refresh_interval_seconds,
        OPPORTUNITY_REFRESH: cfg.scheduler_opportunity_refresh_interval_seconds,
    }
    assert all(j.timeout_seconds > 0 for j in with_network)

    # The application builds the same registry.
    assert lifecycle.build_scheduler(cfg).job_names == tuple(j.name for j in default_jobs)


def test_d_intervals_below_a_minute_are_rejected(monkeypatch):
    monkeypatch.setenv("SCHEDULER_REMINDER_INTERVAL_SECONDS", "5")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


# ── E. Jobs call the existing services ────────────────────────────────────────


def test_e_each_job_is_a_thin_adapter_over_its_existing_service(monkeypatch, db, session_factory):
    import scrapers.expiration.manager as expiry_module
    import scrapers.pipelines.collect_opportunities as pipeline_module

    first, second = add_profile(db, "first"), add_profile(db, "second")
    opportunity = add_opportunity(db, "Adapter Conference")
    for profile in (first, second):
        add_interactions(db, profile, opportunity, 1)
        add_signal(db, profile)

    calls: list[tuple] = []
    summary = ReminderRunSummary(
        discovered_reminders=4, created_notifications=3, delivered_notifications=3, skipped_duplicates=1
    )
    monkeypatch.setattr(
        AdaptivePreferenceSignalService,
        "recompute_adaptive_signals",
        lambda db, profile_id, **kw: calls.append(("adaptive", profile_id)) or [],
    )
    monkeypatch.setattr(
        PersonalizationGovernanceService,
        "recompute_governance",
        lambda db, profile_id, **kw: calls.append(("governance", profile_id)) or (None, []),
    )
    monkeypatch.setattr(
        ReminderSchedulerService,
        "run_scheduled_reminders",
        lambda db, now=None: calls.append(("reminders", type(db))) or summary,
    )
    monkeypatch.setattr(
        expiry_module,
        "expire_past_opportunities",
        lambda session, now=None: calls.append(("expiry", type(session))) or 7,
    )

    def fake_pipeline(**kwargs):
        calls.append(("pipeline", kwargs))
        return {"topic": kwargs["topic"], "inserted": 5, "updated": 2, "errors": 0, "run_id": "r-1"}

    monkeypatch.setattr(pipeline_module, "run_pipeline", fake_pipeline)

    cfg = settings.model_copy(
        update={
            "scheduler_opportunity_refresh_enabled": True,
            "scheduler_opportunity_refresh_topic": "robotics",
            "scheduler_opportunity_refresh_max_pages": 2,
        }
    )
    scheduler = make_scheduler(build_default_jobs(cfg), session_factory)
    runs = run_all(scheduler, APPROVED_JOB_NAMES)

    assert all(r.status is SUCCEEDED for r in runs.values()), {n: r.status for n, r in runs.items()}
    assert sorted(pid for kind, pid in calls if kind == "adaptive") == sorted([first.id, second.id])
    assert sorted(pid for kind, pid in calls if kind == "governance") == sorted([first.id, second.id])
    reminder_calls = [c for c in calls if c[0] == "reminders"]
    expiry_calls = [c for c in calls if c[0] == "expiry"]
    assert len(reminder_calls) == 1 and issubclass(reminder_calls[0][1], Session)
    assert len(expiry_calls) == 1 and issubclass(expiry_calls[0][1], Session)
    assert [c[1] for c in calls if c[0] == "pipeline"] == [
        {"topic": "robotics", "max_pages": 2, "dry_run": False, "sweep_expired": False}
    ]
    # Each result is whatever its service reported, nothing recomputed on the side.
    assert runs[REMINDER_DISPATCH].records_processed == 3
    assert runs[REMINDER_DISPATCH].details["skipped_duplicates"] == 1
    assert runs[DEADLINE_EXPIRY].records_processed == 7
    assert runs[OPPORTUNITY_REFRESH].records_processed == 7
    assert runs[ADAPTIVE_SIGNAL_REFRESH].records_processed == 2
    assert runs[GOVERNANCE_REFRESH].records_processed == 2


def test_e_scheduler_code_contains_no_domain_logic():
    """The adapters must not reach for the engines, reset cutoffs or dedup rules themselves."""
    import ast
    import inspect

    from app.scheduler import jobs, locks, scheduler

    referenced: set[str] = set()
    for module in (jobs, locks, scheduler):
        for node in ast.walk(ast.parse(inspect.getsource(module))):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.alias):
                referenced.add(node.name.rsplit(".", 1)[-1])
    forbidden = {
        "AdaptiveSignalEngine",
        "PersonalizationGovernanceEngine",
        "aggregate_interactions",
        "evaluate_governance",
        "resolve_reset_cutoff",
        "personalization_reset_at",
        "deduplication_key",
        "compute_deduplication_key",
        "is_opportunity_expired",
        "OpportunityRepository",
        "WikiCFPSource",
        "risk_score",
    }
    assert referenced.isdisjoint(forbidden), sorted(referenced & forbidden)


# ── F. Failure isolation ──────────────────────────────────────────────────────


def test_f_a_failing_job_stops_neither_its_own_loop_nor_its_siblings(session_factory):
    def failing(context):
        raise RuntimeError("boom")

    def healthy(context):
        return JobResult(records_processed=1)

    async def scenario():
        scheduler = make_scheduler(
            [job("failing", failing, interval=0.01), job("healthy", healthy, interval=0.01)],
            session_factory,
        )
        await scheduler.start()
        try:
            await scheduler.wait_for_runs("failing", 3, timeout=10)
            await scheduler.wait_for_runs("healthy", 3, timeout=10)
            assert scheduler.is_running
        finally:
            await scheduler.stop()
        return scheduler

    scheduler = asyncio.run(scenario())
    failing_metrics, healthy_metrics = scheduler.metrics.get("failing"), scheduler.metrics.get("healthy")
    assert failing_metrics.failures >= 3 and failing_metrics.successes == 0
    assert failing_metrics.last_error_type == "RuntimeError"
    assert healthy_metrics.successes >= 3 and healthy_metrics.failures == 0


def test_f_a_job_raising_system_exit_is_an_ordinary_failure(session_factory):
    def exits(context):
        raise SystemExit(3)

    scheduler = make_scheduler([job("exits", exits), job("after", lambda context: None)], session_factory)
    runs = run_all(scheduler, ["exits", "after"])
    assert runs["exits"].status is JobRunStatus.FAILED
    assert runs["exits"].error_type == "JobAborted"
    assert runs["after"].status is SUCCEEDED


# ── G. Overlap prevention ─────────────────────────────────────────────────────


def test_g_concurrent_runs_of_one_job_are_prevented(session_factory):
    gate, locks = Gate(), LocalLockBackend()

    async def scenario():
        here = make_scheduler([job("slow", gate)], session_factory, lock_backend=locks)
        elsewhere = make_scheduler([job("slow", gate)], session_factory, lock_backend=locks)
        first = asyncio.create_task(here.run_job_now("slow"))
        assert await asyncio.to_thread(gate.entered.wait, 10)
        same_process = await here.run_job_now("slow")
        other_instance = await elsewhere.run_job_now("slow")
        gate.release.set()
        return await first, same_process, other_instance

    first, same_process, other_instance = asyncio.run(scenario())
    assert first.status is SUCCEEDED
    assert same_process.status is JobRunStatus.SKIPPED_RUNNING
    assert other_instance.status is JobRunStatus.SKIPPED_LOCKED
    assert gate.calls == 1


# ── H. Lock released after a failure ──────────────────────────────────────────


def test_h_the_lock_is_released_when_a_job_raises(session_factory):
    locks = LocalLockBackend()
    attempts: list[bool] = []

    def flaky(context):
        attempts.append(locks.is_held("flaky"))
        if len(attempts) == 1:
            raise RuntimeError("first run fails")
        return JobResult(records_processed=1)

    scheduler = make_scheduler([job("flaky", flaky)], session_factory, lock_backend=locks)
    failed = run_now(scheduler, "flaky")
    released_after_failure = not locks.is_held("flaky")
    succeeded = run_now(scheduler, "flaky")

    assert attempts == [True, True], "each run held the lock while it worked"
    assert failed.status is JobRunStatus.FAILED
    assert released_after_failure
    assert succeeded.status is SUCCEEDED
    assert not locks.is_held("flaky")


# ── I. Lock released after a timeout ──────────────────────────────────────────


def test_i_a_timed_out_job_stops_releases_its_lock_and_the_scheduler_continues(session_factory):
    locks = LocalLockBackend()
    stopped = threading.Event()

    def cooperative(context):
        context.wait_for_stop(30)  # long work that checks for a stop request between units
        stopped.set()
        context.check_cancelled()
        return JobResult()

    scheduler = make_scheduler(
        [job("slow", cooperative, timeout=0.2), job("other", lambda context: JobResult(records_processed=1))],
        session_factory,
        lock_backend=locks,
    )
    timed_out = run_now(scheduler, "slow")
    held_after = locks.is_held("slow")
    other = run_now(scheduler, "other")

    assert timed_out.status is JobRunStatus.TIMED_OUT
    assert timed_out.error_type == "Timeout"
    assert stopped.is_set()
    assert held_after is False
    assert other.status is SUCCEEDED
    assert scheduler.metrics.get("slow").timeouts == 1


def test_i_a_stuck_job_keeps_its_lock_until_it_returns_so_runs_never_overlap(session_factory):
    gate, locks = Gate(), LocalLockBackend()

    async def scenario():
        here = make_scheduler([job("stuck", gate, timeout=0.1)], session_factory, lock_backend=locks, cancel_grace_seconds=0.1)
        elsewhere = make_scheduler([job("stuck", gate, timeout=0.1)], session_factory, lock_backend=locks)
        timed_out = await here.run_job_now("stuck")
        still_held = locks.is_held("stuck")
        again_here = await here.run_job_now("stuck")
        from_elsewhere = await elsewhere.run_job_now("stuck")
        gate.release.set()
        await asyncio.to_thread(join_scheduler_threads)
        released = not locks.is_held("stuck")
        recovered = await here.run_job_now("stuck")
        return timed_out, still_held, again_here, from_elsewhere, released, recovered

    timed_out, still_held, again_here, from_elsewhere, released, recovered = asyncio.run(scenario())
    assert timed_out.status is JobRunStatus.TIMED_OUT
    assert still_held, "the run is still working, so it must still hold its lock"
    assert again_here.status is JobRunStatus.SKIPPED_RUNNING
    assert from_elsewhere.status is JobRunStatus.SKIPPED_LOCKED
    assert released
    assert recovered.status is SUCCEEDED
    assert gate.calls == 2


# ── J. Idempotency ────────────────────────────────────────────────────────────


def test_j_deadline_expiry_twice_expires_each_record_once(db, session_factory):
    for i in range(2):
        add_opportunity(db, f"Past Workshop {i}", days_until_deadline=-3)
    add_opportunity(db, "Future Workshop", days_until_deadline=30)
    scheduler = make_scheduler(build_default_jobs(settings), session_factory)

    first, second = run_now(scheduler, DEADLINE_EXPIRY), run_now(scheduler, DEADLINE_EXPIRY)

    assert (first.status, first.records_processed) == (SUCCEEDED, 2)
    assert (second.status, second.records_processed) == (SUCCEEDED, 0)
    assert count_rows(db, OpportunityModel) == 3
    assert count_rows(db, OpportunityModel, status="EXPIRED") == 2
    assert count_rows(db, OpportunityModel, status="ACTIVE") == 1


def test_j_reminder_dispatch_twice_creates_each_notification_once(db, session_factory):
    profile = add_profile(db, "reminded")
    opportunity = add_opportunity(db, "Reminder Conference", days_until_deadline=6)
    db.add(SavedOpportunityModel(user_id=profile.user_id, opportunity_id=opportunity.id, status="PLANNING"))
    db.commit()
    NotificationService.create_reminder_rule(
        db,
        profile.id,
        ReminderRuleCreate(
            event_type="OPPORTUNITY_SUBMISSION",
            offset_amount=7,
            offset_unit=OffsetUnit.DAYS,
            delivery_channel=DeliveryChannel.IN_APP,
        ),
    )
    scheduler = make_scheduler(build_default_jobs(settings), session_factory)

    first = run_now(scheduler, REMINDER_DISPATCH)
    after_first = count_rows(db, NotificationModel)
    second = run_now(scheduler, REMINDER_DISPATCH)

    assert first.status is SUCCEEDED and first.records_processed >= 1
    assert second.status is SUCCEEDED and second.records_processed == 0
    assert second.details["skipped_duplicates"] >= first.records_processed
    assert count_rows(db, NotificationModel) == after_first
    keys = db.execute(select(NotificationModel.deduplication_key)).scalars().all()
    assert len(keys) == len(set(keys))


def test_j_personalization_jobs_twice_leave_identical_state(db, session_factory):
    profile = add_profile(db, "stable")
    add_interactions(db, profile, add_opportunity(db, "Stable Conference"), 8)
    scheduler = make_scheduler(build_default_jobs(settings), session_factory)

    def state():
        signals = sorted(
            (s.id, s.dimension, s.signal_value, s.total_evidence_count) for s in signals_of(db, profile)
        )
        return (
            signals,
            count_rows(db, PersonalizationDriftEvaluationModel, profile_id=profile.id),
            count_rows(db, PersonalizationGovernanceEventModel, profile_id=profile.id),
        )

    run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH)
    after_first = state()
    for name in (ADAPTIVE_SIGNAL_REFRESH, GOVERNANCE_REFRESH, GOVERNANCE_REFRESH):
        assert run_now(scheduler, name).status is SUCCEEDED
    after_repeats = state()

    assert after_first[0], "expected adaptive signals"
    assert after_first[1] == 1
    assert after_repeats == after_first


# ── K. Reset boundary (P1-1) ──────────────────────────────────────────────────


def test_k_scheduled_refresh_never_resurrects_pre_reset_evidence(db, session_factory):
    profile = add_profile(db, "reset")
    opportunity = add_opportunity(db, "Pre-Reset Conference")
    add_interactions(db, profile, opportunity, 8)
    scheduler = make_scheduler(build_default_jobs(settings), session_factory)

    run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH)
    assert signals_of(db, profile), "pre-reset interactions built signals"

    PersonalizationTransparencyService.reset_personalization(db, profile.id, reason="scheduler test")
    after_reset = run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH)
    assert after_reset.status is SUCCEEDED
    assert signals_of(db, profile) == [], "the scheduled refresh re-aggregated pre-reset evidence"

    # Evidence recorded after the reset is learned, and only that evidence.
    add_interactions(db, profile, opportunity, 5, created_at=datetime.now(timezone.utc))
    run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH)
    signals = signals_of(db, profile)
    assert signals
    assert max(s.total_evidence_count for s in signals) == 5
    assert count_rows(db, ResearcherInteractionModel, profile_id=profile.id) == 13, "the audit trail is kept"


# ── L. Consent (Phase 5.9 controls) ───────────────────────────────────────────


def test_l_scheduled_jobs_only_process_researchers_whose_controls_allow_it(db, session_factory):
    opportunity = add_opportunity(db, "Consent Conference")
    default = add_profile(db, "default")  # no settings row: documented defaults, all on
    learning_off = add_profile(db, "learningoff")
    adaptive_off = add_profile(db, "adaptiveoff")
    personalization_off = add_profile(db, "personalizationoff")
    set_controls(db, learning_off, feedback_learning_enabled=False)
    set_controls(db, adaptive_off, adaptive_signals_enabled=False)
    set_controls(db, personalization_off, personalization_enabled=False)
    for profile in (default, learning_off, adaptive_off, personalization_off):
        add_interactions(db, profile, opportunity, 8)
    seeded = {p.id: add_signal(db, p) for p in (learning_off, adaptive_off, personalization_off)}
    settings_before = sorted(
        (s.profile_id, s.personalization_enabled, s.adaptive_signals_enabled, s.feedback_learning_enabled)
        for s in db.execute(select(ResearcherPersonalizationSettingsModel)).scalars()
    )
    scheduler = make_scheduler(build_default_jobs(settings), session_factory)

    adaptive = run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH)
    governance = run_now(scheduler, GOVERNANCE_REFRESH)

    assert adaptive.records_processed == 1, "only the researcher with learning on is re-aggregated"
    assert signals_of(db, default)
    for profile_id, signal in seeded.items():
        db.expire_all()
        current = db.get(AdaptivePreferenceSignalModel, signal.id)
        assert current is not None and current.total_evidence_count == 10, "opted-out signals were touched"

    # Governance still damps the frozen signals of a researcher with only learning off.
    assert governance.records_processed == 2
    assert count_rows(db, PersonalizationDriftEvaluationModel, profile_id=default.id) == 1
    assert count_rows(db, PersonalizationDriftEvaluationModel, profile_id=learning_off.id) == 1
    assert count_rows(db, PersonalizationDriftEvaluationModel, profile_id=adaptive_off.id) == 0
    assert count_rows(db, PersonalizationDriftEvaluationModel, profile_id=personalization_off.id) == 0

    # The jobs never change a researcher's own controls.
    db.expire_all()
    settings_after = sorted(
        (s.profile_id, s.personalization_enabled, s.adaptive_signals_enabled, s.feedback_learning_enabled)
        for s in db.execute(select(ResearcherPersonalizationSettingsModel)).scalars()
    )
    assert settings_after == settings_before
    assert count_rows(db, PersonalizationControlEventModel) == 0


# ── M. Governance failure stays fail-safe ─────────────────────────────────────


def _suspended_profile(db: Session) -> tuple[ResearchProfileModel, PersonalizationDriftEvaluationModel]:
    profile = add_profile(db, "suspended")
    add_interactions(db, profile, add_opportunity(db, "Governed Conference"), 8)
    add_signal(db, profile)
    evaluation = PersonalizationDriftEvaluationModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        overall_health_state=PersonalizationHealthState.DEGRADED.value,
        governance_state=GovernanceGateState.SUSPEND.value,
        evaluation_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        health_summary="seeded",
        governance_explanation="seeded",
    )
    db.add(evaluation)
    db.commit()
    return profile, evaluation


def test_m_a_failing_governance_evaluation_leaves_the_previous_gate_in_force(monkeypatch, db, session_factory):
    profile, evaluation = _suspended_profile(db)
    events_before = count_rows(db, PersonalizationGovernanceEventModel)

    def unavailable(*args, **kwargs):
        raise RuntimeError("governance engine unavailable")

    monkeypatch.setattr(PersonalizationGovernanceEngine, "evaluate_governance", unavailable)
    scheduler = make_scheduler(build_default_jobs(settings), session_factory)

    governance = run_now(scheduler, GOVERNANCE_REFRESH)
    adaptive = run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH)
    sibling = run_now(scheduler, DEADLINE_EXPIRY)

    assert governance.status is JobRunStatus.PARTIAL
    assert (governance.records_processed, governance.items_failed) == (0, 1)
    # P1-8: the failed governance step never discards a valid signal recomputation.
    assert adaptive.status is SUCCEEDED
    assert signals_of(db, profile)
    # The SUSPEND gate is still the one in force; nothing was loosened or appended.
    db.expire_all()
    current = db.get(PersonalizationDriftEvaluationModel, evaluation.id)
    assert current.governance_state == GovernanceGateState.SUSPEND.value
    assert count_rows(db, PersonalizationDriftEvaluationModel, profile_id=profile.id) == 1
    assert count_rows(db, PersonalizationGovernanceEventModel) == events_before
    assert sibling.status is SUCCEEDED


# ── N. Query counts ───────────────────────────────────────────────────────────


def measure_profile_job_queries(
    profiles: int,
    job_name: str,
    *,
    interactions_per_opportunity: int = 2,
    batch_size: int = 25,
) -> int:
    """Seeds `profiles` researchers on a fresh database and counts one run's SQL statements."""
    engine = _sqlite_engine()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        with factory() as seed:
            opportunities = [add_opportunity(seed, f"Shared Opportunity {i}") for i in range(2)]
            for i in range(profiles):
                profile = add_profile(seed, f"scale{i}")
                for opportunity in opportunities:
                    add_interactions(seed, profile, opportunity, interactions_per_opportunity)
        scheduler = make_scheduler(build_default_jobs(settings, profile_batch_size=batch_size), factory)
        if job_name == GOVERNANCE_REFRESH:
            run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH)  # creates the signals governance governs

        statements = 0

        def count(*args, **kwargs):
            nonlocal statements
            statements += 1

        event.listen(engine, "before_cursor_execute", count)
        run = run_now(scheduler, job_name)
        event.remove(engine, "before_cursor_execute", count)
        assert run.status is SUCCEEDED and run.records_processed == profiles
        return statements
    finally:
        engine.dispose()


QUERY_SCALING: dict[str, dict[int, int]] = {}


@pytest.mark.parametrize("job_name", [ADAPTIVE_SIGNAL_REFRESH, GOVERNANCE_REFRESH])
def test_n_query_count_per_profile_is_constant_from_10_to_100_profiles(job_name):
    batch_size = 25
    counts = {n: measure_profile_job_queries(n, job_name, batch_size=batch_size) for n in (10, 50, 100)}
    QUERY_SCALING[job_name] = counts

    # Enumeration issues one keyset query per batch, plus one that finds no more rows when
    # the last batch is exactly full: 10 -> 1, 50 -> 3, 100 -> 5.
    enumeration = {n: n // batch_size + 1 for n in counts}
    per_profile = {n: (counts[n] - enumeration[n]) / n for n in counts}
    assert per_profile[10] == per_profile[50] == per_profile[100], (counts, per_profile)
    assert per_profile[10].is_integer()


@pytest.mark.parametrize("job_name", [ADAPTIVE_SIGNAL_REFRESH, GOVERNANCE_REFRESH])
def test_n_query_count_does_not_grow_with_interaction_history(job_name):
    light = measure_profile_job_queries(10, job_name, interactions_per_opportunity=1)
    heavy = measure_profile_job_queries(10, job_name, interactions_per_opportunity=8)
    assert light == heavy


# ── O. No network outside the opt-in job ──────────────────────────────────────


def test_o_default_jobs_make_no_network_requests(monkeypatch, db, session_factory):
    import scrapers.pipelines.collect_opportunities as pipeline_module

    profile = add_profile(db, "offline")
    add_interactions(db, profile, add_opportunity(db, "Offline Conference"), 3)
    add_opportunity(db, "Past Offline Workshop", days_until_deadline=-2)

    def no_network(*args, **kwargs):
        raise AssertionError("a scheduled job attempted a network request")

    monkeypatch.setattr(requests.Session, "request", no_network)
    monkeypatch.setattr(httpx.Client, "send", no_network)
    monkeypatch.setattr(pipeline_module, "run_pipeline", lambda **kw: pytest.fail("ingestion ran while disabled"))

    jobs = build_default_jobs(settings)  # the test settings: network ingestion off
    assert OPPORTUNITY_REFRESH not in [j.name for j in jobs]
    assert not any(j.requires_network for j in jobs)
    runs = run_all(make_scheduler(jobs, session_factory), [j.name for j in jobs])
    assert all(r.status is SUCCEEDED for r in runs.values()), {n: r.status for n, r in runs.items()}


def test_o_loading_the_application_does_not_import_the_scraping_pipeline():
    probe = (
        "import sys; import app.main; "
        "print('scrapers.pipelines.collect_opportunities' in sys.modules, "
        "'scrapers.sources.wikicfp' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "False False"


# ── P. Run ids ────────────────────────────────────────────────────────────────


def test_p_every_run_has_its_own_run_id_and_tags_its_logs(session_factory):
    seen: list[tuple[uuid.UUID, str | None]] = []

    def record(context):
        seen.append((context.run_id, request_id_ctx.get()))
        return JobResult()

    locks = LocalLockBackend()
    scheduler = make_scheduler([job("ids", record)], session_factory, lock_backend=locks)
    runs = [run_now(scheduler, "ids") for _ in range(3)]
    holder = locks.try_acquire("ids")
    skipped = run_now(scheduler, "ids")
    holder.release()

    assert [r.run_id for r in runs] == [run_id for run_id, _ in seen]
    assert [tag for _, tag in seen] == [f"ids:{r.run_id}" for r in runs]
    assert skipped.status is JobRunStatus.SKIPPED_LOCKED
    all_ids = [r.run_id for r in runs] + [skipped.run_id]
    assert len(set(all_ids)) == 4 and all(isinstance(i, uuid.UUID) for i in all_ids)


# ── Q. Metrics and logging ────────────────────────────────────────────────────


def test_q_metrics_and_logs_record_every_outcome(session_factory, caplog):
    caplog.set_level(logging.INFO, logger="app.scheduler")
    outcomes = iter(["ok", "fail", "partial"])

    def varied(context):
        kind = next(outcomes)
        if kind == "fail":
            raise ValueError("bad input")
        return JobResult(records_processed=4, items_failed=1 if kind == "partial" else 0)

    locks = LocalLockBackend()
    scheduler = make_scheduler([job("varied", varied)], session_factory, lock_backend=locks)
    ok, failed, partial = (run_now(scheduler, "varied") for _ in range(3))
    holder = locks.try_acquire("varied")
    skipped = run_now(scheduler, "varied")
    holder.release()

    metrics = scheduler.metrics.get("varied")
    assert (ok.status, failed.status, partial.status, skipped.status) == (
        SUCCEEDED,
        JobRunStatus.FAILED,
        JobRunStatus.PARTIAL,
        JobRunStatus.SKIPPED_LOCKED,
    )
    assert metrics.runs_recorded == 4 and metrics.executions == 3
    assert (metrics.successes, metrics.failures, metrics.partial_successes, metrics.skipped_due_to_lock) == (1, 1, 1, 1)
    assert metrics.total_duration_seconds >= 0 and metrics.last_duration_seconds is not None
    assert metrics.last_success_at is not None and metrics.last_failure_at is not None
    assert failed.error_type == "ValueError" and failed.error_message == "bad input"

    summaries = [r for r in caplog.records if getattr(r, "run_id", None) and hasattr(r, "status")]
    by_run = {r.run_id: r for r in summaries}
    for run in (ok, failed, partial, skipped):
        entry = by_run[str(run.run_id)]
        assert entry.job_name == "varied" and entry.status == run.status.value
        assert entry.started_at and entry.finished_at and entry.duration_seconds is not None
    assert by_run[str(ok.run_id)].records_processed == 4
    assert by_run[str(failed.run_id)].levelno == logging.ERROR
    assert by_run[str(failed.run_id)].error_type == "ValueError"
    snapshot = scheduler.metrics.snapshot()
    assert snapshot["varied"]["executions"] == 3


def test_q_database_errors_are_logged_without_their_parameters_or_detail():
    driver_error = Exception(
        'duplicate key value violates unique constraint "uq_users_email"\n'
        "DETAIL:  Key (email)=(someone@university.edu) already exists."
    )
    exc = IntegrityError("INSERT INTO users (email) VALUES (%(email)s)", {"email": "someone@university.edu"}, driver_error)
    error_type, message = classify_error(exc)
    assert error_type == "IntegrityError(Exception)"
    assert message == 'duplicate key value violates unique constraint "uq_users_email"'
    assert "someone@" not in message


# ── S. One service failing leaves the others running ──────────────────────────


def test_s_one_failing_service_leaves_the_other_jobs_running(monkeypatch, db, session_factory):
    profile = add_profile(db, "isolated")
    add_interactions(db, profile, add_opportunity(db, "Isolated Conference"), 8)
    add_opportunity(db, "Past Isolated Workshop", days_until_deadline=-2)

    def broken(db, now=None):
        raise RuntimeError("reminder store unavailable")

    monkeypatch.setattr(ReminderSchedulerService, "run_scheduled_reminders", broken)
    fast_jobs = [dataclasses.replace(j, interval_seconds=0.01) for j in build_default_jobs(settings)]

    async def scenario():
        # One run at a time: the SQLite test database is a single shared connection.
        scheduler = make_scheduler(fast_jobs, session_factory, max_concurrent_jobs=1)
        await scheduler.start()
        try:
            for name in (DEADLINE_EXPIRY, REMINDER_DISPATCH, ADAPTIVE_SIGNAL_REFRESH, GOVERNANCE_REFRESH):
                await scheduler.wait_for_runs(name, 2, timeout=30)
        finally:
            await scheduler.stop()
        return scheduler

    scheduler = asyncio.run(scenario())
    assert scheduler.metrics.get(REMINDER_DISPATCH).failures >= 2
    for name in (DEADLINE_EXPIRY, ADAPTIVE_SIGNAL_REFRESH, GOVERNANCE_REFRESH):
        metrics = scheduler.metrics.get(name)
        assert metrics.successes >= 2 and metrics.failures == 0, (name, metrics)
    assert signals_of(db, profile)
    assert count_rows(db, OpportunityModel, status="EXPIRED") == 1


def test_s_a_failing_profile_is_rolled_back_and_the_others_are_committed(monkeypatch, db, session_factory):
    opportunity = add_opportunity(db, "Batch Conference")
    profiles = [add_profile(db, f"batch{i}") for i in range(3)]
    for profile in profiles:
        add_interactions(db, profile, opportunity, 8)
    bad = profiles[1]
    real_recompute = AdaptivePreferenceSignalService.recompute_adaptive_signals

    def recompute(db, profile_id, **kwargs):
        signals = real_recompute(db=db, profile_id=profile_id, **kwargs)
        if profile_id == bad.id:
            raise RuntimeError("failure after writing")  # the unit's writes must not survive
        return signals

    monkeypatch.setattr(AdaptivePreferenceSignalService, "recompute_adaptive_signals", recompute)
    run = run_now(make_scheduler(build_default_jobs(settings), session_factory), ADAPTIVE_SIGNAL_REFRESH)

    assert run.status is JobRunStatus.PARTIAL
    assert (run.records_processed, run.items_failed) == (2, 1)
    assert signals_of(db, bad) == []
    assert all(signals_of(db, p) for p in profiles if p.id != bad.id)


# ── Sessions, event loop and concurrency ──────────────────────────────────────


def test_sessions_are_new_per_run_closed_and_rolled_back_on_error(engine):
    opened: list[Session] = []

    class TrackingSession(Session):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.closed = False
            opened.append(self)

        def close(self):
            self.closed = True
            super().close()

    factory = sessionmaker(bind=engine, class_=TrackingSession, autoflush=False)

    def writes_then_fails(context):
        with context.session() as session:
            session.add(
                OpportunityModel(
                    id=uuid.uuid4(),
                    title="must not persist",
                    opportunity_type="CONFERENCE",
                    status="ACTIVE",
                    delivery_mode="ONLINE",
                    submission_deadline=datetime.now(timezone.utc) + timedelta(days=10),
                    is_predatory_flag=False,
                )
            )
            session.flush()  # the write reaches the database before the failure
            raise RuntimeError("failure after a write")

    scheduler = make_scheduler([job("writer", writes_then_fails)], factory)
    runs = [run_now(scheduler, "writer") for _ in range(2)]

    assert all(r.status is JobRunStatus.FAILED for r in runs)
    assert len(opened) == 2 and opened[0] is not opened[1]
    assert all(s.closed for s in opened)
    with factory() as check:
        assert check.execute(select(func.count()).select_from(OpportunityModel)).scalar_one() == 0


def test_blocking_job_work_runs_off_the_event_loop(session_factory):
    gate = Gate()

    async def scenario():
        scheduler = make_scheduler(
            [job("blocking", gate), job("quick", lambda context: JobResult(records_processed=1))],
            session_factory,
        )
        slow = asyncio.create_task(scheduler.run_job_now("blocking"))
        assert await asyncio.to_thread(gate.entered.wait, 10)
        quick = await asyncio.wait_for(scheduler.run_job_now("quick"), timeout=5)
        still_running = not slow.done()
        gate.release.set()
        return quick, still_running, await slow

    quick, still_running, slow = asyncio.run(scenario())
    assert quick.status is SUCCEEDED and still_running and slow.status is SUCCEEDED


def test_concurrent_runs_are_bounded(session_factory):
    gate = Gate()
    second_started = threading.Event()

    def second(context):
        second_started.set()
        return JobResult()

    async def scenario():
        scheduler = make_scheduler([job("first", gate), job("second", second)], session_factory, max_concurrent_jobs=1)
        first = asyncio.create_task(scheduler.run_job_now("first"))
        assert await asyncio.to_thread(gate.entered.wait, 10)
        queued = asyncio.create_task(scheduler.run_job_now("second"))
        for _ in range(5):
            await asyncio.sleep(0)  # let the queued dispatch run up to the concurrency limit
        waited = not second_started.is_set() and scheduler.active_worker_count() == 1
        gate.release.set()
        return waited, await first, await queued

    waited, first, queued = asyncio.run(scenario())
    assert waited, "a second job started while the only slot was taken"
    assert first.status is SUCCEEDED and queued.status is SUCCEEDED


# ── R. Two scheduler instances (PostgreSQL advisory locks) ────────────────────


def _postgres_available() -> bool:
    try:
        probe = create_engine(settings.database_url, pool_pre_ping=True)
        with probe.connect() as connection:
            return connection.execute(select(1)).scalar_one() == 1
    except Exception:
        return False


postgres_integration = pytest.mark.skipif(
    not _postgres_available(), reason="PostgreSQL is not reachable in current environment."
)


@pytest.fixture
def pg_engine():
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=2, max_overflow=2)
    yield engine
    engine.dispose()


def _lock_is_free(engine, name: str) -> bool:
    """Checks from a separate connection; takes and immediately returns the lock if free."""
    key = job_lock_key(name)
    with engine.connect() as connection:
        acquired = connection.execute(select(func.pg_try_advisory_lock(key))).scalar_one()
        if acquired:
            connection.execute(select(func.pg_advisory_unlock(key)))
        connection.commit()
    return acquired


def _pg_scheduler(engine, jobs, **overrides) -> Scheduler:
    return make_scheduler(
        jobs,
        sessionmaker(autocommit=False, autoflush=False, bind=engine),
        lock_backend=PostgresAdvisoryLockBackend(engine),
        **overrides,
    )


@postgres_integration
def test_r_advisory_lock_stops_a_second_scheduler_instance_running_the_same_job(pg_engine):
    name = f"r-overlap-{uuid.uuid4().hex[:8]}"
    gate = Gate()

    async def scenario():
        first_instance = _pg_scheduler(pg_engine, [job(name, gate)])
        second_instance = _pg_scheduler(pg_engine, [job(name, gate)])
        first = asyncio.create_task(first_instance.run_job_now(name))
        assert await asyncio.to_thread(gate.entered.wait, 10)
        held_while_running = not await asyncio.to_thread(_lock_is_free, pg_engine, name)
        blocked = await second_instance.run_job_now(name)
        gate.release.set()
        completed = await first
        free_after = await asyncio.to_thread(_lock_is_free, pg_engine, name)
        later = await second_instance.run_job_now(name)
        return held_while_running, blocked, completed, free_after, later

    held_while_running, blocked, completed, free_after, later = asyncio.run(scenario())
    assert held_while_running
    assert blocked.status is JobRunStatus.SKIPPED_LOCKED
    assert completed.status is SUCCEEDED
    assert free_after
    assert later.status is SUCCEEDED
    assert gate.calls == 2


@postgres_integration
def test_r_advisory_lock_is_released_after_failure_and_after_timeout(pg_engine):
    failing_name = f"r-fail-{uuid.uuid4().hex[:8]}"
    slow_name = f"r-slow-{uuid.uuid4().hex[:8]}"

    def failing(context):
        raise RuntimeError("boom")

    def cooperative(context):
        context.wait_for_stop(30)
        context.check_cancelled()

    scheduler = _pg_scheduler(pg_engine, [job(failing_name, failing), job(slow_name, cooperative, timeout=0.3)])
    assert run_now(scheduler, failing_name).status is JobRunStatus.FAILED
    assert _lock_is_free(pg_engine, failing_name)
    assert run_now(scheduler, slow_name).status is JobRunStatus.TIMED_OUT
    assert _lock_is_free(pg_engine, slow_name)


@postgres_integration
def test_r_run_session_holds_the_lock_with_a_statement_timeout_that_is_reset_afterwards():
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
    name = f"r-session-{uuid.uuid4().hex[:8]}"
    seen: dict = {}
    unsigned = job_lock_key(name) & 0xFFFFFFFFFFFFFFFF

    def probe(context):
        with context.session() as session:
            seen["timeout"] = session.execute(text("SHOW statement_timeout")).scalar_one()
            seen["pid"] = session.execute(select(func.pg_backend_pid())).scalar_one()
            seen["holders"] = session.execute(
                text(
                    "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted "
                    "AND classid::bigint = :hi AND objid::bigint = :lo AND objsubid = 1"
                ),
                {"hi": unsigned >> 32, "lo": unsigned & 0xFFFFFFFF},
            ).scalars().all()
        return JobResult()

    try:
        run = run_now(_pg_scheduler(engine, [job(name, probe, timeout=42)]), name)
        with engine.connect() as connection:  # pool_size=1: the same connection, back in the pool
            reset_timeout = connection.execute(text("SHOW statement_timeout")).scalar_one()
    finally:
        engine.dispose()

    assert run.status is SUCCEEDED
    assert seen["timeout"] == "42s"
    assert seen["holders"] == [seen["pid"]], "the run's session is not on the lock-holding connection"
    assert reset_timeout == "0"


@postgres_integration
def test_r_profile_work_is_serialized_until_the_holding_transaction_commits(pg_engine):
    """Mechanism: a second unit of work on the same profile waits for the first to commit."""
    from sqlalchemy.exc import OperationalError

    from app.scheduler.jobs import _serialize_profile_work

    profile_id = uuid.uuid4()
    factory = sessionmaker(bind=pg_engine)
    with factory() as holder, factory() as contender:
        _serialize_profile_work(holder, profile_id)
        contender.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(OperationalError) as blocked:
            _serialize_profile_work(contender, profile_id)
        assert type(blocked.value.orig).__name__ == "LockNotAvailable"
        contender.rollback()

        other_profile = uuid.uuid4()
        _serialize_profile_work(contender, other_profile)  # other profiles are not blocked
        contender.rollback()

        holder.commit()  # releases the transaction-scoped lock
        _serialize_profile_work(contender, profile_id)
        contender.rollback()


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_MIGRATION_TESTS") != "1" or not _postgres_available(),
    reason="set RUN_POSTGRES_MIGRATION_TESTS=1 to run tests that create an isolated PostgreSQL database",
)
def test_r_concurrent_adaptive_and_governance_refresh_record_one_transition_event():
    """
    adaptive_signal_refresh recomputes governance (P1-8), so both personalization jobs can
    evaluate one profile at once. A barrier inside the pure governance evaluation (which runs
    after every read) lines the two evaluations up; without the per-profile lock both read
    the old gate and both append the same transition event.
    """
    from sqlalchemy.engine import make_url

    base = make_url(settings.database_url)
    name = f"researchconnect_sched_{uuid.uuid4().hex[:10]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = None
    real_evaluate = PersonalizationGovernanceEngine.evaluate_governance
    try:
        url = base.set(database=name)
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
            env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)},
            capture_output=True,
            text=True,
        )
        assert migrated.returncode == 0, migrated.stderr[-2000:]
        engine = create_engine(url, pool_pre_ping=True)
        factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        scheduler = _pg_scheduler(engine, build_default_jobs(settings))
        with factory() as db:
            opportunities = [add_opportunity(db, f"Race Conference {i}") for i in range(2)]
            profile = add_profile(db, "race")
            for opportunity in opportunities:
                add_interactions(db, profile, opportunity, 4)
            profile_id, opportunity_ids = profile.id, [o.id for o in opportunities]
        assert run_now(scheduler, ADAPTIVE_SIGNAL_REFRESH).status is SUCCEEDED  # the gate's first state
        with factory() as db:  # fresh negative evidence: the gate is now due a transition
            for opportunity_id in opportunity_ids:
                for _ in range(6):
                    db.add(
                        ResearcherInteractionModel(
                            id=uuid.uuid4(),
                            profile_id=profile_id,
                            opportunity_id=opportunity_id,
                            interaction_type=InteractionType.NOT_INTERESTED.value,
                            client_event_id=f"neg-{uuid.uuid4().hex}",
                            created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                        )
                    )
            db.commit()
            events_before = count_rows(db, PersonalizationGovernanceEventModel)

        barrier = threading.Barrier(2, timeout=3)

        def lined_up(*args, **kwargs):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass  # with the lock, the other evaluation only starts after this one commits
            return real_evaluate(*args, **kwargs)

        PersonalizationGovernanceEngine.evaluate_governance = lined_up

        async def both():
            return await asyncio.gather(
                scheduler.run_job_now(ADAPTIVE_SIGNAL_REFRESH), scheduler.run_job_now(GOVERNANCE_REFRESH)
            )

        runs = asyncio.run(both())
        with factory() as db:
            new_events = count_rows(db, PersonalizationGovernanceEventModel) - events_before
    finally:
        PersonalizationGovernanceEngine.evaluate_governance = real_evaluate
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"), {"n": name}
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()

    assert all(r.status is SUCCEEDED for r in runs)
    assert barrier.broken, "the second evaluation ran while the first still held the profile"
    assert new_events == 1
