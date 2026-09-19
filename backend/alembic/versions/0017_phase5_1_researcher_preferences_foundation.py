"""Phase 5.1 — Researcher Preferences Foundation

Enhances researcher_preferences table:
  - Adds preference_type (VARCHAR 50, not null, default 'PREFERRED')
  - Adds index idx_researcher_preferences_type on preference_type
  - Adds check constraint chk_researcher_preferences_type: preference_type IN ('PREFERRED', 'EXCLUDED')

Revision ID: 0017_phase5_1_researcher_preferences_foundation
Revises:     0016_phase4_6_collaboration
Create Date: 2026-09-19 21:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0017_phase5_1_researcher_preferences_foundation"
down_revision: Union[str, None] = "0016_phase4_6_collaboration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add preference_type column with server_default='PREFERRED'
    op.add_column(
        "researcher_preferences",
        sa.Column(
            "preference_type",
            sa.String(50),
            nullable=False,
            server_default="PREFERRED",
            comment="Preference type: PREFERRED or EXCLUDED (Phase 5.1)",
        ),
    )

    # 2. Create index for fast filtering on preference_type
    op.create_index(
        "idx_researcher_preferences_type",
        "researcher_preferences",
        ["preference_type"],
    )

    # 3. Add check constraint to ensure only valid preference types are stored
    op.create_check_constraint(
        "chk_researcher_preferences_type",
        "researcher_preferences",
        "preference_type IN ('PREFERRED', 'EXCLUDED')",
    )


def downgrade() -> None:
    # 1. Drop check constraint
    op.drop_constraint(
        "chk_researcher_preferences_type",
        "researcher_preferences",
        type_="check",
    )

    # 2. Drop index
    op.drop_index(
        "idx_researcher_preferences_type",
        table_name="researcher_preferences",
    )

    # 3. Drop column
    op.drop_column("researcher_preferences", "preference_type")
