"""
Research refresh (step 4/6) — admins are alerted after repeated failed refreshes.

Two research refresh runs in a row with every pass FAILED create one SYSTEM in-app
notification per active administrator, keyed on the run that completed the streak.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.types import TSVector, Vector
from app.models import Base
from app.models.ingestion_run import IngestionRunModel
from app.models.notification import NotificationModel
from app.models.research_profile import ResearchProfileModel
from app.models.source import SourceModel
from app.models.user import UserModel
from app.services.ingestion_alert_service import ALERT_TITLE, notify_admins_after_repeated_failures

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

URL_ERROR = (
    "stopped on an error: HTTPSConnectionPool(host='api.openalex.org', port=443): "
    "Max retries exceeded with url: /works?filter=x&api_key=***"
)


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


class Refreshes:
    """Writes research refresh runs, one minute apart, oldest first."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.source = SourceModel(id=uuid.uuid4(), name="OpenAlex", source_type="API")
        db.add(self.source)
        db.commit()
        self.clock = datetime.now(timezone.utc) - timedelta(hours=1)

    def add(self, *statuses: str, error: str | None = URL_ERROR) -> str:
        tag = uuid.uuid4().hex
        for lane, status in zip(("newest", "rising"), statuses):
            self.clock += timedelta(minutes=1)
            self.db.add(
                IngestionRunModel(
                    id=uuid.uuid4(),
                    source_id=self.source.id,
                    topic=f"research_refresh:{tag}:{lane}:1702",
                    status=status,
                    started_at=self.clock,
                    error_message=error if status == "FAILED" else None,
                )
            )
        self.db.commit()
        return tag


def _user(db: Session, role: str, *, active: bool = True, with_profile: bool = True) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=f"{role.lower()}.{uuid.uuid4().hex[:8]}@institution.edu",
        hashed_password="hashed",
        full_name=f"{role.title()} User",
        role=role,
        is_active=active,
    )
    db.add(user)
    db.flush()
    if with_profile:
        db.add(ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, academic_status="FACULTY"))
    db.commit()
    return user


def _alerts(db: Session) -> list[NotificationModel]:
    db.expire_all()
    return list(db.execute(select(NotificationModel).where(NotificationModel.title == ALERT_TITLE)).scalars())


def _owner(db: Session, notification: NotificationModel) -> uuid.UUID:
    return db.execute(
        select(ResearchProfileModel.user_id).where(ResearchProfileModel.id == notification.profile_id)
    ).scalar_one()


@pytest.fixture
def refreshes(db) -> Refreshes:
    return Refreshes(db)


def test_one_failed_run_creates_no_notification(db, refreshes):
    _user(db, "ADMIN")
    tag = refreshes.add("FAILED", "FAILED")
    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 0
    assert _alerts(db) == []


def test_two_failed_runs_alert_every_active_admin_once(db, refreshes):
    admins = [_user(db, "ADMIN"), _user(db, "ADMIN", with_profile=False)]
    refreshes.add("FAILED", "FAILED")
    tag = refreshes.add("FAILED", "FAILED")

    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 2

    alerts = _alerts(db)
    assert sorted(_owner(db, a) for a in alerts) == sorted(a.id for a in admins)
    for alert in alerts:
        assert alert.notification_type == "SYSTEM"
        assert alert.source_type == "SYSTEM"
        assert alert.delivery_channel == "IN_APP"
        assert alert.delivery_status == "DELIVERED"
        assert alert.delivered_at is not None
        assert "2 research refresh runs failed" in alert.body
        assert "Last error: error" in alert.body
    # The admin without a profile got a minimal one, as the notifications API would create.
    assert db.execute(
        select(func.count()).select_from(ResearchProfileModel).where(ResearchProfileModel.user_id == admins[1].id)
    ).scalar_one() == 1


def test_a_second_call_for_the_same_run_creates_nothing(db, refreshes):
    _user(db, "ADMIN")
    refreshes.add("FAILED", "FAILED")
    tag = refreshes.add("FAILED", "FAILED")

    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 1
    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 0
    assert len(_alerts(db)) == 1


def test_a_longer_streak_alerts_again_for_its_newest_run(db, refreshes):
    _user(db, "ADMIN")
    refreshes.add("FAILED", "FAILED")
    second = refreshes.add("FAILED", "FAILED")
    assert notify_admins_after_repeated_failures(db, run_tag=second) == 1
    third = refreshes.add("FAILED")
    assert notify_admins_after_repeated_failures(db, run_tag=third) == 1
    bodies = sorted(a.body for a in _alerts(db))
    assert len(bodies) == 2
    assert any("The last 2 research refresh runs failed" in b for b in bodies)
    assert any("The last 3 research refresh runs failed" in b for b in bodies)


def test_a_failure_after_a_completed_run_creates_nothing(db, refreshes):
    _user(db, "ADMIN")
    refreshes.add("COMPLETED", "COMPLETED")
    tag = refreshes.add("FAILED", "FAILED")
    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 0
    assert _alerts(db) == []


def test_a_partly_completed_run_breaks_the_streak(db, refreshes):
    _user(db, "ADMIN")
    refreshes.add("FAILED", "FAILED")
    refreshes.add("FAILED", "COMPLETED")
    tag = refreshes.add("FAILED", "FAILED")
    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 0


def test_a_stopped_run_is_not_a_failure(db, refreshes):
    _user(db, "ADMIN")
    refreshes.add("FAILED", error="stop requested")
    tag = refreshes.add("FAILED", "FAILED")
    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 0


def test_only_the_newest_run_can_complete_a_streak(db, refreshes):
    _user(db, "ADMIN")
    refreshes.add("FAILED", "FAILED")
    older = refreshes.add("FAILED", "FAILED")
    refreshes.add("FAILED", "FAILED")
    assert notify_admins_after_repeated_failures(db, run_tag=older) == 0


def test_inactive_admins_and_non_admins_get_nothing(db, refreshes):
    active = _user(db, "ADMIN")
    _user(db, "ADMIN", active=False)
    _user(db, "FACULTY")
    _user(db, "STUDENT")
    refreshes.add("FAILED", "FAILED")
    tag = refreshes.add("FAILED", "FAILED")

    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 1
    assert [_owner(db, a) for a in _alerts(db)] == [active.id]


def test_the_alert_names_the_error_type_only(db, refreshes):
    _user(db, "ADMIN")
    refreshes.add("FAILED", "FAILED")
    tag = refreshes.add("FAILED", error="OpenAlex daily usage budget exhausted. It resets in about 2.5 h.")

    assert notify_admins_after_repeated_failures(db, run_tag=tag) == 1
    (alert,) = _alerts(db)
    assert "Last error: budget exhausted" in alert.body
    text = f"{alert.title} {alert.body} {alert.metadata_json}"
    for leaked in ("http", "api_key", "HTTPSConnectionPool", "Max retries", "/works", "resets in"):
        assert leaked not in text


def test_no_runs_at_all_creates_nothing(db):
    _user(db, "ADMIN")
    assert notify_admins_after_repeated_failures(db, run_tag="missing") == 0
