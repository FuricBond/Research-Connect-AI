"""Phase 6.7 — Access token revocation

Adds users.token_version. Every access token carries the version it was issued under (the
"ver" claim) and is refused once the account's version moves on: signing out, changing the
password, or an administrator deactivating the account increments it, so tokens issued before
stop working at once instead of living out their lifetime.

Existing rows start at 0, and a token without a "ver" claim counts as version 0, so sessions
issued before this migration keep working until the account's first sign-out.

Revision ID: 0032_phase6_7_token_revocation
Revises:     0031_phase5_16_email_delivery
Create Date: 2026-10-05 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0032_phase6_7_token_revocation"
down_revision: Union[str, None] = "0031_phase5_16_email_delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
