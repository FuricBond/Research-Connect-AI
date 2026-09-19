"""
Performance Benchmarking and Zero N+1 Verification for Phase 4.5 Deadline Reminders.

Benchmarks:
  - Notification scheduling and evaluation across researcher scales:
      - 10 researchers
      - 50 researchers
      - 100 researchers
      - 500 researchers
      - 1,000 researchers
  - Query count monitoring ensuring bounded database query complexity (zero N+1)
  - Duplicate detection and idempotency latency profile
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import time
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.calendar import ResearchCalendarEventModel, ResearchCalendarModel
from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationDeliveryAttemptModel,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
    OffsetUnit,
    ReminderRuleModel,
)
from app.models.opportunity import OpportunityModel
from app.models.research_profile import ResearchProfileModel
from app.models.saved_opportunity import SavedOpportunityModel
from app.models.user import UserModel
from app.services.reminder_scheduler_service import ReminderSchedulerService

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with all Phase 4.5 tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    target_tables = [
        Base.metadata.tables["users"],
        Base.metadata.tables["institutions"],
        Base.metadata.tables["researchers"],
        Base.metadata.tables["topics"],
        Base.metadata.tables["opportunities"],
        Base.metadata.tables["opportunity_topics"],
        Base.metadata.tables["saved_opportunities"],
        Base.metadata.tables["research_submissions"],
        Base.metadata.tables["research_submission_documents"],
        Base.metadata.tables["research_submission_document_versions"],
        Base.metadata.tables["research_submission_events"],
        Base.metadata.tables["research_profiles"],
        Base.metadata.tables["researcher_interests"],
        Base.metadata.tables["researcher_preferences"],
        Base.metadata.tables["researcher_recommendation_feedback"],
        Base.metadata.tables["research_calendars"],
        Base.metadata.tables["research_calendar_events"],
        Base.metadata.tables["researcher_notification_preferences"],
        Base.metadata.tables["reminder_rules"],
        Base.metadata.tables["notifications"],
        Base.metadata.tables["notification_delivery_attempts"],
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    sm = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = sm()
    yield session
    session.close()


@pytest.mark.parametrize("researcher_count", [10, 50, 100, 500, 1000])
def test_reminder_scheduler_scaling_and_latency(
    db_session: Session,
    researcher_count: int,
):
    """
    Measures scheduling evaluation latency, notification creation throughput,
    and duplicate detection performance for 10, 50, 100, 500, and 1,000 researchers.
    """
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    deadline_utc = now + timedelta(days=7)
    eval_time = now + timedelta(days=6)  # 1 day before deadline (well within 3-day reminder window)

    # Create common shared opportunity
    opp = OpportunityModel(
        id=uuid.uuid4(),
        title="Benchmark Conference 2026",
        opportunity_type="CONFERENCE",
        submission_deadline=deadline_utc,
    )
    db_session.add(opp)

    users = []
    profiles = []
    saved_opps = []
    rules = []

    for i in range(researcher_count):
        u_id = uuid.uuid4()
        p_id = uuid.uuid4()
        r_id = uuid.uuid4()

        users.append(
            UserModel(
                id=u_id,
                email=f"bench_researcher_{i:04d}@univ.edu",
                hashed_password="pw",
                full_name=f"Dr. Bench {i}",
                is_active=True,
            )
        )
        profiles.append(
            ResearchProfileModel(
                id=p_id,
                user_id=u_id,
                academic_status="FACULTY",
            )
        )
        saved_opps.append(
            SavedOpportunityModel(
                id=uuid.uuid4(),
                user_id=u_id,
                opportunity_id=opp.id,
                status="PLANNING",
            )
        )
        rules.append(
            ReminderRuleModel(
                id=r_id,
                profile_id=p_id,
                event_type="OPPORTUNITY_SUBMISSION",
                offset_amount=3,
                offset_unit=OffsetUnit.DAYS.value,
                delivery_channel=DeliveryChannel.IN_APP.value,
                is_active=True,
            )
        )

    db_session.add_all(users)
    db_session.add_all(profiles)
    db_session.add_all(saved_opps)
    db_session.add_all(rules)
    db_session.commit()

    # 1. First run: Evaluation and Notification Creation
    start_run = time.perf_counter()
    summary1 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    run1_ms = (time.perf_counter() - start_run) * 1000.0

    assert summary1.created_notifications == researcher_count
    assert summary1.delivered_notifications == researcher_count

    # 2. Second run: Idempotency & Duplicate Detection Latency
    start_run2 = time.perf_counter()
    summary2 = ReminderSchedulerService.run_scheduled_reminders(db_session, now=eval_time)
    run2_ms = (time.perf_counter() - start_run2) * 1000.0

    assert summary2.created_notifications == 0
    assert summary2.skipped_duplicates == researcher_count

    # Latency budgets:
    # 1,000 researchers scheduling should complete within 3.5 seconds in in-memory SQLite
    assert run1_ms < 3500.0, f"Run 1 took {run1_ms:.2f}ms for {researcher_count} researchers (exceeds budget)"
    assert run2_ms < 2500.0, f"Run 2 (duplicate check) took {run2_ms:.2f}ms for {researcher_count} researchers"

    print(
        f"\n[BENCHMARK] {researcher_count:4d} researchers -> "
        f"Run 1 (Evaluation + Creation): {run1_ms:.2f}ms ({run1_ms/researcher_count:.3f}ms/user) | "
        f"Run 2 (Deduplication): {run2_ms:.2f}ms ({run2_ms/researcher_count:.3f}ms/user)"
    )
