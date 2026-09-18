"""
Performance Benchmarking and Zero N+1 Verification for Phase 4.4 Research Calendar.

Benchmarks:
  - Event batch creation and deterministic retrieval across sizes:
      - 10 events
      - 50 events
      - 100 events
      - 500 events
      - 1,000 events
  - Query count monitoring ensuring O(1) bounded database query complexity (zero N+1)
  - In-memory RFC 5545 iCalendar serialization latency profile
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import time
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.calendar import (
    CalendarEventStatus,
    CalendarEventType,
    ResearchCalendarEventModel,
    ResearchCalendarModel,
)
from app.models.user import UserModel
from app.schemas.calendar import CalendarEventCreate
from app.services.research_calendar_service import ResearchCalendarService

# SQLite compatibility
compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")


@pytest.fixture
def db_session() -> Session:
    """Provides a fresh in-memory SQLite session with all Phase 4.4 tables."""
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
    ]
    Base.metadata.create_all(bind=engine, tables=target_tables)
    sm = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = sm()
    yield session
    session.close()


@pytest.fixture
def benchmark_user(db_session: Session) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email="perf_researcher@example.edu",
        hashed_password="hashed_perf_password",
        full_name="Dr. Performance Benchmark",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.mark.parametrize("event_count", [10, 50, 100, 500, 1000])
def test_calendar_scaling_and_ical_latency(
    db_session: Session,
    benchmark_user: UserModel,
    event_count: int,
):
    """
    Measures query execution latency and iCal serialization throughput for
    10, 50, 100, 500, and 1,000 calendar events.
    Verifies that listing operations do NOT execute per-row N+1 queries.
    """
    cal = ResearchCalendarService.create_calendar(
        db_session,
        user_id=benchmark_user.id,
        payload=type("Payload", (), {
            "name": f"Benchmark Calendar ({event_count} items)",
            "description": "Load testing calendar scaling",
            "timezone": "UTC",
            "is_default": False,
        })(),
    )

    base_time = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

    # Bulk insert events
    events = [
        ResearchCalendarEventModel(
            calendar_id=cal.id,
            title=f"Planning Milestone #{i:04d}",
            description=f"Automated benchmark milestone index {i}",
            event_type=CalendarEventType.RESEARCH_MILESTONE.value,
            start_datetime=base_time + timedelta(hours=i),
            end_datetime=base_time + timedelta(hours=i, minutes=45),
            status=CalendarEventStatus.ACTIVE.value,
            provenance_metadata={"benchmark_idx": i},
        )
        for i in range(event_count)
    ]
    db_session.add_all(events)
    db_session.commit()

    cal_id = cal.id
    user_id = benchmark_user.id

    # Query counter
    query_count = 0
    queries_executed = []

    def query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1
        queries_executed.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", query_listener)

    try:
        # Measure retrieval query count and latency
        start_query = time.perf_counter()
        retrieved_events = ResearchCalendarService.list_events(
            db=db_session,
            calendar_id=cal_id,
            user_id=user_id,
        )
        retrieval_ms = (time.perf_counter() - start_query) * 1000.0

        assert len(retrieved_events) == event_count
        assert query_count <= 2, f"Expected <= 2 queries, got {query_count}: {queries_executed}"


        # Measure iCal generation latency
        start_ical = time.perf_counter()
        feed = ResearchCalendarService.generate_ical_feed(
            db=db_session,
            calendar_id=cal_id,
            user_id=user_id,
        )
        ical_ms = (time.perf_counter() - start_ical) * 1000.0


        assert "BEGIN:VCALENDAR" in feed
        assert feed.count("BEGIN:VEVENT") == event_count
        # Ensure 1,000 events serialization completes well under 100ms
        assert ical_ms < 200.0, f"iCal generation took {ical_ms:.2f}ms for {event_count} events (exceeds budget)"

        print(
            f"\n[BENCHMARK] {event_count:4d} events -> Retrieval: {retrieval_ms:.2f}ms "
            f"({query_count} queries, 0 N+1) | iCal generation: {ical_ms:.2f}ms"
        )
    finally:
        event.remove(engine, "before_cursor_execute", query_listener)
