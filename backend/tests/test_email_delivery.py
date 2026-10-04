"""
Phase 5.16 — Email delivery of notifications.

  SMTP sender   One message per connection, text and HTML parts, STARTTLS or implicit TLS.
                Recipients outside EMAIL_RECIPIENT_ALLOWLIST are refused before connecting.
                Failures are classified as temporary or permanent, and no error message ever
                carries the password or the server's reply text.
  Settings      EMAIL_PROVIDER=smtp needs a host and a sender; production refuses an SMTP
                login over an unencrypted connection; the mock stays unless smtp is chosen.
  Dispatch      Each recent in-app notification is decided once: emailed with a link to its
                page, or skipped (type, already read, email off, inactive, not allowed, too
                old). The in-app status is never changed. Temporary failures are retried and
                pause the pass; five attempts or a permanent refusal fail it. Oldest first, at
                most 25 a pass, and a repeated pass sends nothing twice.

No test opens a network connection: smtplib is replaced by an in-memory fake.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
import smtplib
import ssl
import uuid

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import security
from app.core.config import Settings
from app.db.types import TSVector, Vector
from app.models.base import Base
from app.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    EmailStatus,
    NotificationDeliveryAttemptModel,
    NotificationModel,
    NotificationPreferenceModel,
    NotificationType,
)
from app.models.research_profile import ResearchProfileModel
from app.models.user import UserModel
from app.scheduler.jobs import run_email_dispatch
from app.services import smtp_email_provider
from app.services.email_dispatch_service import (
    BATCH_SIZE,
    EMAIL_WINDOW,
    MAX_EMAIL_ATTEMPTS,
    EmailDispatchService,
    link_path,
)
from app.services.reminder_scheduler_service import (
    DeliveryResult,
    EmailProvider,
    MockEmailProvider,
    get_email_provider,
    set_email_provider,
)
from app.services.smtp_email_provider import (
    RecipientAllowlist,
    SmtpEmailProvider,
    configure_email_provider,
)

compiles(JSONB, "sqlite")(lambda type_, compiler, **kw: "JSON")
compiles(Vector, "sqlite")(lambda type_, compiler, **kw: "TEXT")
compiles(TSVector, "sqlite")(lambda type_, compiler, **kw: "TEXT")

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
APP_URL = "https://app.example.test/"
# Built at run time, like a real secret; never a literal password in the suite.
PASSWORD = "pw-" + uuid.uuid4().hex

OK = DeliveryResult(success=True, provider_reference="<accepted@example.test>")
TEMPORARY = DeliveryResult(
    success=False,
    error_message="Could not reach the mail server (TimeoutError)",
    retryable=True,
)
PERMANENT = DeliveryResult(success=False, error_message="The mail server refused the recipient")


def _naive(value: datetime | None) -> datetime | None:
    """SQLite hands timestamps back without a zone; compare them as UTC wall times."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


# ── Fakes ───────────────────────────────────────────────────────────────────


class FakeProvider(EmailProvider):
    """Records every email; answers from `results` in order, then OK (or `always`)."""

    def __init__(
        self,
        results: list[DeliveryResult] | None = None,
        *,
        always: DeliveryResult | None = None,
        refuse: tuple[str, ...] = (),
    ) -> None:
        self.sent: list[dict] = []
        self._results = list(results or [])
        self._always = always
        self._refuse = {address.lower() for address in refuse}

    def accepts_recipient(self, to_email: str) -> bool:
        return to_email.lower() not in self._refuse

    def send_email(self, to_email, subject, body_text, body_html=None) -> DeliveryResult:
        self.sent.append({"to": to_email, "subject": subject, "text": body_text, "html": body_html})
        if self._results:
            return self._results.pop(0)
        return self._always or OK


class FakeSMTP:
    """Stands in for smtplib.SMTP; `fail` maps a step (connect, starttls, login, send) to an error."""

    instances: list[FakeSMTP] = []
    fail: dict[str, BaseException] = {}

    def __init__(self, host, port, timeout=None, context=None, **kwargs) -> None:
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list = []
        self.sent: list = []
        type(self).instances.append(self)
        if "connect" in self.fail:
            raise self.fail["connect"]

    def starttls(self, context=None):
        self.calls.append("starttls")
        if "starttls" in self.fail:
            raise self.fail["starttls"]

    def login(self, user, password):
        self.calls.append(("login", user, password))
        if "login" in self.fail:
            raise self.fail["login"]

    def send_message(self, message):
        self.sent.append(message)
        if "send" in self.fail:
            raise self.fail["send"]

    def close(self):
        self.calls.append("close")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.calls.append("quit")
        return False


class FakeSMTPSSL(FakeSMTP):
    instances: list[FakeSMTP] = []


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail = [], {}
    FakeSMTPSSL.instances, FakeSMTPSSL.fail = [], {}
    monkeypatch.setattr(smtp_email_provider.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtp_email_provider.smtplib, "SMTP_SSL", FakeSMTPSSL)
    return FakeSMTP


def _smtp(**overrides) -> SmtpEmailProvider:
    values = dict(
        host="smtp.example.test",
        port=587,
        username="alerts@example.test",
        password=SecretStr(PASSWORD),
        security="starttls",
        timeout_seconds=10,
        from_address="alerts@example.test",
        from_name="ResearchConnect AI",
        allowlist=RecipientAllowlist("*"),
    )
    values.update(overrides)
    return SmtpEmailProvider(**values)


# ── Database fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _account(
    db: Session,
    email: str,
    *,
    full_name: str = "Priya Raman",
    is_active: bool = True,
    email_enabled: bool | None = None,
) -> tuple[UserModel, ResearchProfileModel]:
    user = UserModel(
        id=uuid.uuid4(),
        email=email,
        hashed_password="hashed",
        full_name=full_name,
        role="STUDENT",
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    profile = ResearchProfileModel(id=uuid.uuid4(), user_id=user.id, academic_status="POSTGRADUATE")
    db.add(profile)
    if email_enabled is not None:
        db.add(NotificationPreferenceModel(profile_id=profile.id, email_enabled=email_enabled))
    db.commit()
    return user, profile


def _notification(
    db: Session,
    profile: ResearchProfileModel,
    *,
    created_at: datetime = NOW - timedelta(minutes=1),
    notification_type: NotificationType = NotificationType.POSTING_MATCH,
    title: str = "New posting matches your interests",
    body: str = "“Doctoral position in retrieval” — 82% fit",
    source_type: str = "RESEARCH_POSTING",
    source_id: uuid.UUID | None = None,
    channel: DeliveryChannel = DeliveryChannel.IN_APP,
    status: DeliveryStatus = DeliveryStatus.DELIVERED,
    read_at: datetime | None = None,
    email_status: str | None = None,
) -> NotificationModel:
    notification = NotificationModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        notification_type=notification_type.value,
        title=title,
        body=body,
        source_type=source_type,
        source_id=source_id if source_id is not None else uuid.uuid4(),
        scheduled_for=created_at,
        delivered_at=created_at,
        read_at=read_at,
        delivery_status=status.value,
        delivery_channel=channel.value,
        deduplication_key=uuid.uuid4().hex,
        metadata_json={},
        email_status=email_status,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(notification)
    db.commit()
    return notification


def _dispatch(db: Session, provider: EmailProvider, **kwargs):
    kwargs.setdefault("now", NOW)
    return EmailDispatchService.dispatch_pending(db, app_url=APP_URL, provider=provider, **kwargs)


def _attempts(db: Session, notification: NotificationModel) -> list[NotificationDeliveryAttemptModel]:
    return list(
        db.execute(
            select(NotificationDeliveryAttemptModel)
            .where(NotificationDeliveryAttemptModel.notification_id == notification.id)
            .order_by(NotificationDeliveryAttemptModel.attempt_number)
        ).scalars()
    )


# ── SMTP sender ─────────────────────────────────────────────────────────────


def test_smtp_sends_a_text_and_html_message_over_starttls(fake_smtp):
    result = _smtp().send_email(
        to_email="priya@lab.example.test",
        subject="New posting\nmatches your interests",
        body_text="Plain body",
        body_html="<p>HTML body</p>",
    )

    assert result.success is True
    [connection] = FakeSMTP.instances
    assert (connection.host, connection.port, connection.timeout) == ("smtp.example.test", 587, 10)
    assert connection.calls == ["starttls", ("login", "alerts@example.test", PASSWORD), "quit"]
    [message] = connection.sent
    assert message["From"] == "ResearchConnect AI <alerts@example.test>"
    assert message["To"] == "priya@lab.example.test"
    # A line break in a title never reaches the header.
    assert message["Subject"] == "New posting matches your interests"
    assert message["Message-ID"] == result.provider_reference
    assert message.get_body(("plain",)).get_content().strip() == "Plain body"
    assert message.get_body(("html",)).get_content().strip() == "<p>HTML body</p>"


def test_smtp_messages_are_seven_bit_safe(fake_smtp):
    """Curly quotes and dashes survive any server, with or without 8BITMIME."""
    _smtp().send_email(
        to_email="priya@lab.example.test",
        subject="“Doctoral position” — 82% fit",
        body_text="“Doctoral position” — 82% fit",
        body_html="<p>“Doctoral position” — 82% fit</p>",
    )

    [message] = FakeSMTP.instances[0].sent
    message.as_bytes().decode("ascii")
    for part in ("plain", "html"):
        body = message.get_body((part,))
        assert body["Content-Transfer-Encoding"] == "quoted-printable"
        assert "“Doctoral position” — 82% fit" in body.get_content()
    assert message["Subject"] == "“Doctoral position” — 82% fit"


def test_smtp_ssl_uses_implicit_tls_and_skips_login_without_a_username(fake_smtp):
    result = _smtp(security="ssl", port=465, username="").send_email(
        to_email="priya@lab.example.test", subject="Hello", body_text="Body"
    )

    assert result.success is True
    assert FakeSMTP.instances == []
    [connection] = FakeSMTPSSL.instances
    assert connection.port == 465
    assert isinstance(connection.context, ssl.SSLContext)
    assert connection.calls == ["quit"]


def test_smtp_refuses_recipients_outside_the_allowlist_without_connecting(fake_smtp):
    provider = _smtp(allowlist=RecipientAllowlist(" Me@Example.test , @lab.example.test "))

    result = provider.send_email(to_email="someone@elsewhere.test", subject="Hi", body_text="Body")

    assert result.success is False and result.retryable is False
    assert "EMAIL_RECIPIENT_ALLOWLIST" in result.error_message
    assert FakeSMTP.instances == []
    assert provider.accepts_recipient("me@example.TEST") is True
    assert provider.accepts_recipient("anyone@lab.example.test") is True
    assert provider.accepts_recipient("anyone@sub.lab.example.test") is False
    assert provider.accepts_recipient("not-an-address") is False


def test_the_allowlist_is_nobody_when_empty_and_everyone_with_a_star():
    empty = RecipientAllowlist("  ,  ")
    assert empty.is_empty and not empty.allows("priya@lab.example.test")
    everyone = RecipientAllowlist("*")
    assert not everyone.is_empty and everyone.allows("priya@lab.example.test")
    assert not everyone.allows("no-at-sign")


@pytest.mark.parametrize(
    ("step", "error", "retryable"),
    [
        ("send", smtplib.SMTPRecipientsRefused({"x@lab.example.test": (550, b"no such user")}), False),
        ("send", smtplib.SMTPDataError(554, b"message rejected as spam"), False),
        ("send", smtplib.SMTPDataError(451, b"try again later"), True),
        ("login", smtplib.SMTPAuthenticationError(535, f"bad credentials {PASSWORD}".encode()), True),
        ("send", smtplib.SMTPServerDisconnected("connection unexpectedly closed"), True),
        ("connect", ConnectionRefusedError(111, "connection refused"), True),
        ("connect", TimeoutError("timed out"), True),
        ("starttls", ssl.SSLError("certificate verify failed"), True),
    ],
)
def test_smtp_failures_are_classified_and_never_echo_secrets_or_replies(fake_smtp, step, error, retryable):
    FakeSMTP.fail = {step: error}

    result = _smtp().send_email(to_email="x@lab.example.test", subject="Hi", body_text="Body")

    assert result.success is False
    assert result.retryable is retryable
    assert PASSWORD not in result.error_message
    for reply in ("no such user", "spam", "try again", "bad credentials", "unexpectedly", "verify"):
        assert reply not in result.error_message


def test_a_failed_starttls_closes_the_connection(fake_smtp):
    FakeSMTP.fail = {"starttls": ssl.SSLError("handshake failed")}

    _smtp().send_email(to_email="x@lab.example.test", subject="Hi", body_text="Body")

    assert FakeSMTP.instances[0].calls == ["starttls", "close"]


# ── Settings and startup ────────────────────────────────────────────────────


def test_smtp_settings_need_a_host_and_a_sender():
    assert Settings(_env_file=None).email_provider == "mock"
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, email_provider="smtp")
    assert "SMTP_HOST" in str(excinfo.value) and "EMAIL_FROM_ADDRESS" in str(excinfo.value)

    cfg = Settings(
        _env_file=None,
        email_provider="smtp",
        smtp_host="smtp.example.test",
        email_from_address="alerts@example.test",
        smtp_password=PASSWORD,
    )
    assert cfg.smtp_password.get_secret_value() == PASSWORD
    assert PASSWORD not in repr(cfg) and PASSWORD not in str(cfg.model_dump())


def _production(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        app_env="production",
        auth_secret_key=uuid.uuid4().hex + uuid.uuid4().hex,
        database_url=f"postgresql+psycopg://rc_app:{uuid.uuid4().hex}@db.internal:5432/researchconnect",
        email_provider="smtp",
        smtp_host="smtp.example.test",
        email_from_address="alerts@example.test",
    )
    values.update(overrides)
    return Settings(**values)


def test_production_refuses_an_smtp_login_over_an_unencrypted_connection(monkeypatch):
    monkeypatch.setattr(security, "settings", _production(smtp_security="none", smtp_username="alerts"))
    with pytest.raises(RuntimeError, match="SMTP_SECURITY must be starttls or ssl"):
        security.validate_security_settings()

    # A local relay without a login, or any encrypted connection, is fine.
    monkeypatch.setattr(security, "settings", _production(smtp_security="none"))
    security.validate_security_settings()
    monkeypatch.setattr(security, "settings", _production(smtp_username="alerts"))
    security.validate_security_settings()


def test_startup_keeps_the_mock_unless_smtp_is_chosen():
    before = get_email_provider()
    assert configure_email_provider(Settings(_env_file=None)) is None
    assert get_email_provider() is before


def test_startup_installs_smtp_and_warns_about_what_would_stop_email(caplog):
    cfg = Settings(
        _env_file=None,
        email_provider="smtp",
        smtp_host="smtp.example.test",
        email_from_address="alerts@example.test",
        smtp_username="alerts@example.test",
        smtp_password=PASSWORD,
    )
    with caplog.at_level(logging.INFO, logger="app.services.smtp_email_provider"):
        provider = configure_email_provider(cfg)

    assert isinstance(provider, SmtpEmailProvider)
    assert get_email_provider() is provider
    assert "SCHEDULER_ENABLED=false" in caplog.text
    assert "EMAIL_RECIPIENT_ALLOWLIST is empty" in caplog.text
    assert PASSWORD not in caplog.text and "smtp.example.test" not in caplog.text


# ── Dispatch ────────────────────────────────────────────────────────────────


def test_a_new_notification_is_emailed_once_with_a_link_to_its_page(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    posting_id = uuid.uuid4()
    notification = _notification(db_session, profile, source_id=posting_id)
    provider = FakeProvider()

    summary = _dispatch(db_session, provider)

    assert (summary.sent, summary.skipped, summary.failed, summary.paused) == (1, 0, 0, False)
    [email] = provider.sent
    assert email["to"] == "priya@lab.example.test"
    assert email["subject"] == "New posting matches your interests"
    assert "Hi Priya Raman," in email["text"]
    assert f"https://app.example.test/postings/{posting_id}" in email["text"]
    assert "https://app.example.test/settings/notifications" in email["text"]
    assert f'href="https://app.example.test/postings/{posting_id}"' in email["html"]

    db_session.refresh(notification)
    assert notification.email_status == EmailStatus.SENT.value
    assert notification.email_attempts == 1
    assert _naive(notification.email_sent_at) == _naive(NOW)
    # The in-app delivery is untouched.
    assert notification.delivery_status == DeliveryStatus.DELIVERED.value
    assert _naive(notification.delivered_at) == _naive(NOW - timedelta(minutes=1))
    [attempt] = _attempts(db_session, notification)
    assert (attempt.channel, attempt.status, attempt.attempt_number) == ("EMAIL", "DELIVERED", 1)
    assert attempt.provider_reference == OK.provider_reference

    assert _dispatch(db_session, provider).sent == 0
    assert len(provider.sent) == 1


def test_a_recipient_without_a_preference_row_gets_email(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    assert db_session.execute(select(NotificationPreferenceModel)).first() is None
    _notification(db_session, profile)

    assert _dispatch(db_session, FakeProvider()).sent == 1


def test_notifications_that_should_not_be_emailed_are_skipped_once(db_session):
    _, email_off = _account(db_session, "off@lab.example.test", email_enabled=False)
    _, reader = _account(db_session, "reader@lab.example.test")
    _, chatty = _account(db_session, "chatty@lab.example.test")
    _, inactive = _account(db_session, "inactive@lab.example.test", is_active=False)
    _, outsider = _account(db_session, "outsider@elsewhere.test")
    skipped = [
        _notification(db_session, email_off),
        _notification(db_session, reader, read_at=NOW - timedelta(seconds=30)),
        _notification(db_session, chatty, notification_type=NotificationType.COLLABORATION_ACTIVITY),
        _notification(db_session, chatty, notification_type=NotificationType.DOCUMENT_UPDATED),
        _notification(db_session, inactive),
        _notification(db_session, outsider),
    ]
    provider = FakeProvider(refuse=("outsider@elsewhere.test",))

    summary = _dispatch(db_session, provider)

    assert (summary.sent, summary.skipped) == (0, len(skipped))
    assert provider.sent == []
    for notification in skipped:
        db_session.refresh(notification)
        assert notification.email_status == EmailStatus.SKIPPED.value
        assert notification.email_attempts == 0
        assert _attempts(db_session, notification) == []
    assert _dispatch(db_session, provider).skipped == 0


def test_old_notifications_expire_and_other_rows_are_left_alone(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    old = _notification(db_session, profile, created_at=NOW - EMAIL_WINDOW - timedelta(minutes=1))
    email_channel = _notification(db_session, profile, channel=DeliveryChannel.EMAIL)
    cancelled = _notification(db_session, profile, status=DeliveryStatus.CANCELLED)
    backfilled = _notification(db_session, profile, email_status=EmailStatus.SKIPPED.value)
    provider = FakeProvider()

    summary = _dispatch(db_session, provider)

    assert (summary.expired, summary.sent, summary.skipped) == (1, 0, 0)
    assert provider.sent == []
    for notification, expected in (
        (old, EmailStatus.SKIPPED.value),
        (email_channel, None),
        (cancelled, None),
        (backfilled, EmailStatus.SKIPPED.value),
    ):
        db_session.refresh(notification)
        assert notification.email_status == expected


def test_a_temporary_failure_is_retried_and_pauses_the_rest_of_the_pass(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    first = _notification(db_session, profile, created_at=NOW - timedelta(minutes=3))
    second = _notification(db_session, profile, created_at=NOW - timedelta(minutes=2))

    down = FakeProvider(always=TEMPORARY)
    summary = _dispatch(db_session, down)

    assert (summary.retrying, summary.sent, summary.paused) == (1, 0, True)
    assert len(down.sent) == 1
    db_session.refresh(first)
    db_session.refresh(second)
    assert (first.email_status, first.email_attempts) == (EmailStatus.RETRY.value, 1)
    assert (second.email_status, second.email_attempts) == (None, 0)
    assert first.delivery_status == DeliveryStatus.DELIVERED.value

    summary = _dispatch(db_session, FakeProvider(), now=NOW + timedelta(minutes=1))

    assert summary.sent == 2
    db_session.refresh(first)
    assert (first.email_status, first.email_attempts) == (EmailStatus.SENT.value, 2)
    assert [(a.status, a.attempt_number) for a in _attempts(db_session, first)] == [
        ("FAILED", 1),
        ("DELIVERED", 2),
    ]
    assert _attempts(db_session, first)[0].error_message == TEMPORARY.error_message


def test_temporary_failures_give_up_after_the_last_attempt(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    notification = _notification(db_session, profile)
    down = FakeProvider(always=TEMPORARY)

    for attempt in range(1, MAX_EMAIL_ATTEMPTS + 1):
        _dispatch(db_session, down, now=NOW + timedelta(minutes=attempt))
        db_session.refresh(notification)
        expected = EmailStatus.FAILED.value if attempt == MAX_EMAIL_ATTEMPTS else EmailStatus.RETRY.value
        assert (notification.email_status, notification.email_attempts) == (expected, attempt)

    assert _dispatch(db_session, down, now=NOW + timedelta(minutes=10)).failed == 0
    assert len(down.sent) == MAX_EMAIL_ATTEMPTS


def test_a_permanent_failure_fails_at_once_without_pausing(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    refused = _notification(db_session, profile, created_at=NOW - timedelta(minutes=3))
    accepted = _notification(db_session, profile, created_at=NOW - timedelta(minutes=2))

    summary = _dispatch(db_session, FakeProvider([PERMANENT]))

    assert (summary.failed, summary.sent, summary.paused) == (1, 1, False)
    db_session.refresh(refused)
    db_session.refresh(accepted)
    assert (refused.email_status, refused.email_attempts) == (EmailStatus.FAILED.value, 1)
    assert accepted.email_status == EmailStatus.SENT.value


def test_sends_the_oldest_first_and_at_most_one_batch_a_pass(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    titles = [f"Notification {index:02d}" for index in range(BATCH_SIZE + 5)]
    for index, title in enumerate(titles):
        _notification(db_session, profile, title=title, created_at=NOW - timedelta(minutes=60 - index))
    provider = FakeProvider()

    assert _dispatch(db_session, provider).sent == BATCH_SIZE
    assert [email["subject"] for email in provider.sent] == titles[:BATCH_SIZE]
    assert _dispatch(db_session, provider).sent == 5
    assert [email["subject"] for email in provider.sent] == titles


def test_stops_between_emails_when_asked(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    for minutes in (3, 2, 1):
        _notification(db_session, profile, created_at=NOW - timedelta(minutes=minutes))
    provider = FakeProvider()

    summary = _dispatch(db_session, provider, should_stop=lambda: len(provider.sent) >= 1)

    assert summary.sent == 1


def test_stored_text_is_escaped_in_the_html_part(db_session):
    _, profile = _account(db_session, "priya@lab.example.test", full_name="<b>Priya</b>")
    _notification(db_session, profile, title="<i>New</i> match", body="<script>alert(1)</script>")
    provider = FakeProvider()

    _dispatch(db_session, provider)

    [email] = provider.sent
    assert "<script>" not in email["html"] and "&lt;script&gt;alert(1)&lt;/script&gt;" in email["html"]
    assert "&lt;b&gt;Priya&lt;/b&gt;" in email["html"] and "&lt;i&gt;New&lt;/i&gt;" in email["html"]
    assert "<script>alert(1)</script>" in email["text"]


def test_each_email_links_to_the_page_of_its_source():
    def make(**fields) -> NotificationModel:
        values = dict(source_type="SYSTEM", source_id=None, calendar_event_id=None, opportunity_id=None)
        values.update(fields)
        return NotificationModel(**values)

    posting_id = uuid.uuid4()
    assert link_path(make(source_type="RESEARCH_POSTING", source_id=posting_id)) == f"/postings/{posting_id}"
    assert link_path(make(source_type="CALENDAR_EVENT", calendar_event_id=uuid.uuid4())) == "/calendar"
    assert link_path(make(source_type="OPPORTUNITY", opportunity_id=uuid.uuid4())) == "/workspace"
    assert link_path(make(source_type="WORKSPACE", source_id=uuid.uuid4())) == "/workspace"
    assert link_path(make()) == "/notifications"


def test_the_scheduler_job_sends_through_the_installed_provider(db_session):
    _, profile = _account(db_session, "priya@lab.example.test")
    _notification(db_session, profile, created_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    provider = FakeProvider()
    set_email_provider(provider)

    class _Context:
        cancelled = False

        def check_cancelled(self) -> None:
            pass

        @contextmanager
        def session(self):
            yield db_session

    result = run_email_dispatch(_Context(), app_url=APP_URL)

    assert result.records_processed == 1
    assert result.details["sent"] == 1 and result.details["paused"] is False
    assert len(provider.sent) == 1


def test_the_mock_provider_still_accepts_every_recipient():
    assert MockEmailProvider().accepts_recipient("anyone@anywhere.test") is True
