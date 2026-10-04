"""
Phase 5.16 — Real email over SMTP.

SmtpEmailProvider sends one message per connection: STARTTLS on port 587, implicit TLS on port
465, or plain SMTP for a local relay. It works with any standard mail server (Gmail with an app
password, Outlook, Mailtrap, a university relay) and needs nothing beyond the standard library.

Only recipients on EMAIL_RECIPIENT_ALLOWLIST are mailed: everyone else is refused before any
connection is made, whichever code path asked. An empty allowlist means nobody, so a database
full of seeded users is never mailed by accident; "*" means everyone.

Failures are classified so the caller knows whether to try again:
  - refused recipient, or a 5xx answer       permanent (retryable=False)
  - unreachable server, TLS failure, timeout,
    failed login, or a 4xx answer            temporary (retryable=True)

Neither the password, a recipient address nor the server's reply text is ever logged or put in
an error message: errors name the SMTP status code or the exception class only.
"""
from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import logging
import smtplib
import ssl
from typing import Literal

from pydantic import SecretStr

from app.core.config import Settings
from app.services.reminder_scheduler_service import DeliveryResult, EmailProvider, set_email_provider

logger = logging.getLogger(__name__)


class RecipientAllowlist:
    """Comma-separated addresses and @domains, or "*" for everyone. Case-insensitive."""

    def __init__(self, text: str) -> None:
        entries = {part.strip().lower() for part in text.split(",") if part.strip()}
        self.everyone = "*" in entries
        self.domains = frozenset(entry[1:] for entry in entries if entry.startswith("@") and len(entry) > 1)
        self.addresses = frozenset(entry for entry in entries if "@" in entry and not entry.startswith("@"))

    def allows(self, address: str) -> bool:
        address = address.strip().lower()
        if "@" not in address:
            return False
        if self.everyone:
            return True
        return address in self.addresses or address.rsplit("@", 1)[1] in self.domains

    @property
    def is_empty(self) -> bool:
        return not (self.everyone or self.domains or self.addresses)


class SmtpEmailProvider(EmailProvider):
    """Sends each email over its own SMTP connection."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: SecretStr,
        security: Literal["starttls", "ssl", "none"],
        timeout_seconds: int,
        from_address: str,
        from_name: str,
        allowlist: RecipientAllowlist,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._security = security
        self._timeout = timeout_seconds
        self._from_address = from_address
        self._from_name = from_name
        self._allowlist = allowlist

    @classmethod
    def from_settings(cls, cfg: Settings) -> SmtpEmailProvider:
        return cls(
            host=cfg.smtp_host.strip(),
            port=cfg.smtp_port,
            username=cfg.smtp_username.strip(),
            password=cfg.smtp_password,
            security=cfg.smtp_security,
            timeout_seconds=cfg.smtp_timeout_seconds,
            from_address=cfg.email_from_address.strip(),
            from_name=cfg.email_from_name.strip(),
            allowlist=RecipientAllowlist(cfg.email_recipient_allowlist),
        )

    def accepts_recipient(self, to_email: str) -> bool:
        return self._allowlist.allows(to_email)

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> DeliveryResult:
        if not self.accepts_recipient(to_email):
            return DeliveryResult(
                success=False,
                error_message="Recipient is not on EMAIL_RECIPIENT_ALLOWLIST",
            )

        message = EmailMessage()
        message["From"] = formataddr((self._from_name, self._from_address))
        message["To"] = to_email
        # A header may not contain line breaks.
        message["Subject"] = " ".join(subject.split())
        message_id = make_msgid(domain=self._from_address.rsplit("@", 1)[-1])
        message["Message-ID"] = message_id
        # Quoted-printable is 7-bit safe on every server, with or without 8BITMIME.
        message.set_content(body_text, cte="quoted-printable")
        if body_html:
            message.add_alternative(body_html, subtype="html", cte="quoted-printable")

        try:
            with self._open() as smtp:
                if self._username:
                    smtp.login(self._username, self._password.get_secret_value())
                smtp.send_message(message)
        except smtplib.SMTPRecipientsRefused:
            return DeliveryResult(success=False, error_message="The mail server refused the recipient")
        except smtplib.SMTPAuthenticationError:
            return DeliveryResult(
                success=False,
                error_message="SMTP login failed; check SMTP_USERNAME and SMTP_PASSWORD",
                retryable=True,
            )
        except smtplib.SMTPResponseException as err:
            return DeliveryResult(
                success=False,
                error_message=f"The mail server answered {err.smtp_code}",
                retryable=400 <= err.smtp_code < 500,
            )
        except (smtplib.SMTPException, OSError) as err:
            # Refused or dropped connection, timeout, TLS failure.
            return DeliveryResult(
                success=False,
                error_message=f"Could not reach the mail server ({type(err).__name__})",
                retryable=True,
            )
        return DeliveryResult(success=True, provider_reference=message_id)

    def _open(self) -> smtplib.SMTP:
        context = ssl.create_default_context()
        if self._security == "ssl":
            return smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout, context=context)
        smtp = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        try:
            if self._security == "starttls":
                smtp.starttls(context=context)
        except BaseException:
            smtp.close()
            raise
        return smtp


def email_delivery_configured(cfg: Settings) -> bool:
    """Whether notifications are emailed at all: SMTP is set up and the scheduler sends them."""
    return cfg.email_provider == "smtp" and cfg.scheduler_enabled


def configure_email_provider(cfg: Settings) -> EmailProvider | None:
    """
    Called once at startup. Installs the SMTP provider when EMAIL_PROVIDER=smtp and leaves the
    in-memory mock in place otherwise. Returns the provider it installed, if any.
    """
    if cfg.email_provider != "smtp":
        return None
    provider = SmtpEmailProvider.from_settings(cfg)
    set_email_provider(provider)
    logger.info("Email delivery: SMTP (%s security)", cfg.smtp_security)
    if not cfg.scheduler_enabled:
        logger.warning(
            "EMAIL_PROVIDER=smtp but SCHEDULER_ENABLED=false: notifications will not be emailed"
        )
    if RecipientAllowlist(cfg.email_recipient_allowlist).is_empty:
        logger.warning(
            "EMAIL_RECIPIENT_ALLOWLIST is empty: nobody will receive email. "
            "List addresses or @domains, or set it to * for everyone"
        )
    return provider
