"""Audit SEC-05 — invitation tokens are stored only as a hash

Replaces workspace_invitations.token with token_hash, the SHA-256 of the token. Every existing row
is hashed in place, so an invitation already sent keeps working: its token still matches, and no
pending invitation is lost. After this migration the database holds nothing that can be used as a
token.

Downgrading cannot bring the tokens back. The old column is restored holding the digest, so
tokens handed out earlier stop matching; those invitations can still be answered by their invitee
from the notifications page, which needs no token.

Revision ID: 0033_invitation_token_hash
Revises:     0032_phase6_7_token_revocation
Create Date: 2026-11-01 12:00:00.000000
"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0033_invitation_token_hash"
down_revision: Union[str, None] = "0032_phase6_7_token_revocation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workspace_invitations", sa.Column("token_hash", sa.String(64), nullable=True))

    connection = op.get_bind()
    invitations = sa.table(
        "workspace_invitations",
        sa.column("id"),
        sa.column("token", sa.String),
        sa.column("token_hash", sa.String),
    )
    for row in connection.execute(sa.select(invitations.c.id, invitations.c.token)).all():
        digest = hashlib.sha256(row.token.encode("utf-8")).hexdigest()
        connection.execute(
            invitations.update().where(invitations.c.id == row.id).values(token_hash=digest)
        )

    op.alter_column("workspace_invitations", "token_hash", nullable=False)
    op.create_unique_constraint("uq_workspace_invitations_token_hash", "workspace_invitations", ["token_hash"])
    op.drop_index("idx_workspace_invitations_token", table_name="workspace_invitations")
    op.drop_constraint("uq_workspace_invitations_token", "workspace_invitations", type_="unique")
    op.drop_column("workspace_invitations", "token")


def downgrade() -> None:
    op.add_column("workspace_invitations", sa.Column("token", sa.String(255), nullable=True))
    op.execute("UPDATE workspace_invitations SET token = token_hash")
    op.alter_column("workspace_invitations", "token", nullable=False)
    op.create_unique_constraint("uq_workspace_invitations_token", "workspace_invitations", ["token"])
    op.create_index("idx_workspace_invitations_token", "workspace_invitations", ["token"])
    op.drop_constraint("uq_workspace_invitations_token_hash", "workspace_invitations", type_="unique")
    op.drop_column("workspace_invitations", "token_hash")
