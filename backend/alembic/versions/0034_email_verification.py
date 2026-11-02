"""Decision C — an account can prove it receives mail at its address

Adds users.email_verified_address and users.email_verified_at, and email_verification_tokens, which
holds only hashes. Nothing existing is rewritten: every account starts unconfirmed, because nothing
has ever proved an address, and pending invitations stay pending, waiting for a confirmed address.
Memberships already granted are not touched.

Downgrading drops the new column and table, and with them every confirmation.

Revision ID: 0034_email_verification
Revises:     0033_invitation_token_hash
Create Date: 2026-11-02 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0034_email_verification"
down_revision: Union[str, None] = "0033_invitation_token_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_address", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_email_verified_address", "users", ["email_verified_address"], unique=True)

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_token_hash"),
    )
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_index("ix_users_email_verified_address", table_name="users")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified_address")
