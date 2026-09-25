"""Phase 6 — Durable personalization reset cutoff

Adds ``researcher_personalization_settings.personalization_reset_at``.

Phase 5.9's safe reset deleted derived signals and bumped the state version, but the
underlying interaction and feedback records are append-only and were still re-aggregated
by the next recompute, which restored the pre-reset state. Recording the reset instant lets
every derived-signal recomputation exclude pre-reset evidence while keeping the audit trail
intact, so a reset is a durable cold start.

Existing rows keep NULL, which means "never reset" and preserves current behaviour.

Revision ID: 0025_phase6_personalization_reset_cutoff
Revises:     0024_phase6_feedback_history
Create Date: 2026-09-25 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0025_phase6_personalization_reset_cutoff"
down_revision: Union[str, None] = "0024_phase6_feedback_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "researcher_personalization_settings"
_COLUMN = "personalization_reset_at"


def _column_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return False
    return any(col["name"] == _COLUMN for col in inspector.get_columns(_TABLE))


def upgrade() -> None:
    if _column_exists():
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    if _column_exists():
        op.drop_column(_TABLE, _COLUMN)
