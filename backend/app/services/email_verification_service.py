"""
Decision C — proving that an account's owner receives mail at its address.

Registering with an address proves nothing about it, so a workspace invitation waits for this.
The account asks for a confirmation email; a one-time token goes to the address, and only a hash of
it is stored. Confirming needs both the token and the signed-in account that asked: if someone
registers another person's address and that person clicks the link, the page asks them to sign in
to an account they cannot open, and nothing is confirmed.

What was proved is stored as the address itself, not as a flag, so an account whose email later
differs from it counts as unconfirmed. A second account can never hold the same confirmed address.

Without a mail server (EMAIL_PROVIDER=mock, the default) nothing can be proved, and addresses stay
unconfirmed: this fails closed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import html
import logging
import secrets
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_verification import EmailVerificationTokenModel
from app.models.user import UserModel
from app.services.reminder_scheduler_service import get_email_provider

logger = logging.getLogger(__name__)

TOKEN_LIFETIME = timedelta(hours=24)


class EmailDeliveryUnavailableError(Exception):
    """This server cannot mail this address at all: no mail server, or it is not on the allowlist."""


class EmailDeliveryFailedError(Exception):
    """The mail server did not take the message; worth trying again later."""


class InvalidEmailConfirmationError(Exception):
    """Unknown, expired, already used, or issued to another account: all answered the same way."""


def normalize_email(address: str) -> str:
    """The one comparison used for accounts and invitations: surrounding space and case do not count."""
    return address.strip().lower()


def has_verified_email(user: UserModel) -> bool:
    return bool(user.email_verified_address) and user.email_verified_address == normalize_email(user.email)


def hash_token(token: str) -> str:
    """Only this digest is stored. A token is 256 random bits, so a fast hash is enough."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _base_url() -> str:
    return settings.app_public_url.rstrip("/")


class EmailVerificationService:

    @classmethod
    def request_confirmation(cls, db: Session, user: UserModel) -> bool:
        """
        Sends a new confirmation link, which replaces any earlier one. False when the address is
        already confirmed and nothing was sent.
        """
        if has_verified_email(user):
            return False
        provider = get_email_provider()
        if not provider.delivers_mail or not provider.accepts_recipient(user.email):
            raise EmailDeliveryUnavailableError("This server cannot send email to this address.")

        token = secrets.token_urlsafe(32)
        db.execute(delete(EmailVerificationTokenModel).where(EmailVerificationTokenModel.user_id == user.id))
        row = EmailVerificationTokenModel(
            id=uuid.uuid4(),
            user_id=user.id,
            email=normalize_email(user.email),
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + TOKEN_LIFETIME,
        )
        db.add(row)
        db.commit()

        link = f"{_base_url()}/verify-email#token={token}"
        name = (user.full_name or "").strip() or "there"
        result = provider.send_email(
            to_email=user.email,
            subject="Confirm your email address",
            body_text=(
                f"Hi {name},\n\n"
                "Someone asked to confirm this address for a ResearchConnect account. To confirm it, "
                f"open this link and sign in to that account (it works once, for 24 hours):\n\n{link}\n\n"
                "If this was not you, ignore this email: nothing happens unless that account is yours.\n"
            ),
            body_html=(
                '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#1f2937">'
                f"<p>Hi {html.escape(name)},</p>"
                "<p>Someone asked to confirm this address for a ResearchConnect account. To confirm it, "
                "open this link and sign in to that account (it works once, for 24 hours):</p>"
                f'<p><a href="{html.escape(link)}">Confirm your email address</a></p>'
                "<p>If this was not you, ignore this email: nothing happens unless that account is yours.</p>"
                "</div>"
            ),
        )
        if not result.success:
            db.delete(row)
            db.commit()
            logger.warning("Could not send an email confirmation: %s", result.error_message)
            if result.retryable:
                raise EmailDeliveryFailedError("The confirmation email could not be sent.")
            raise EmailDeliveryUnavailableError("This server cannot send email to this address.")
        return True

    @classmethod
    def confirm(cls, db: Session, user: UserModel, token: str) -> UserModel:
        """
        Marks the address confirmed. The token is claimed by one conditional update, so it works
        once however many requests race, and a token issued to another account is not even used up.
        """
        if has_verified_email(user):
            return user
        now = datetime.now(timezone.utc)
        digest = hash_token(token)
        claimed = db.execute(
            update(EmailVerificationTokenModel)
            .where(
                EmailVerificationTokenModel.token_hash == digest,
                EmailVerificationTokenModel.user_id == user.id,
                EmailVerificationTokenModel.consumed_at.is_(None),
                EmailVerificationTokenModel.expires_at > now,
            )
            .values(consumed_at=now)
            .execution_options(synchronize_session=False)
        ).rowcount
        if claimed != 1:
            db.rollback()
            raise InvalidEmailConfirmationError("This confirmation link is no longer valid.")

        address = db.execute(
            select(EmailVerificationTokenModel.email).where(EmailVerificationTokenModel.token_hash == digest)
        ).scalar_one()
        if address != normalize_email(user.email):
            db.commit()
            raise InvalidEmailConfirmationError("This confirmation link is no longer valid.")

        user.email_verified_address = address
        user.email_verified_at = now
        try:
            db.flush()
        except IntegrityError:
            # Another account already holds this confirmed address.
            db.rollback()
            raise InvalidEmailConfirmationError("This confirmation link is no longer valid.") from None

        # Invitations waiting for this address can now be shown to its owner.
        from app.services.workspace_collaboration_service import WorkspaceCollaborationService

        WorkspaceCollaborationService.notify_invitations_after_confirmation(db, user)
        db.commit()
        db.refresh(user)
        logger.info("Email address confirmed", extra={"confirmed_user_id": str(user.id)})
        return user

    @staticmethod
    def send_invitation_email(to_email: str, inviter_name: str | None) -> None:
        """
        Tells whoever reads this mailbox that an invitation waits, when no confirmed account holds
        the address. Only its owner sees this, so an account that merely registered the address
        learns nothing. It names neither the workspace nor a token. Best effort: an invitation
        exists whether or not this arrives, and the inviter is told the same either way.
        """
        provider = get_email_provider()
        if not provider.accepts_recipient(to_email):
            return
        inviter = (inviter_name or "").strip() or "A researcher"
        link = f"{_base_url()}/notifications#invitations"
        try:
            result = provider.send_email(
                to_email=to_email,
                subject="You have been invited to a research workspace",
                body_text=(
                    f"{inviter} invited you to work on a research workspace on ResearchConnect.\n\n"
                    "To see it, sign in or create an account with this email address, confirm the address, "
                    f"and answer the invitation on your notifications page:\n\n{link}\n"
                ),
                body_html=(
                    '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#1f2937">'
                    f"<p>{html.escape(inviter)} invited you to work on a research workspace on ResearchConnect.</p>"
                    "<p>To see it, sign in or create an account with this email address, confirm the address, "
                    "and answer the invitation on your notifications page.</p>"
                    f'<p><a href="{html.escape(link)}">Open ResearchConnect</a></p>'
                    "</div>"
                ),
            )
        except Exception:
            logger.warning("Could not send an invitation email", exc_info=True)
            return
        if not result.success:
            logger.warning("Could not send an invitation email: %s", result.error_message)
