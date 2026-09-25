"""Phase 5.12 — Peer and co-author discovery consent

Creates researcher_discovery_settings: a researcher's opt-in consent to appear in peer discovery,
their collaboration status and interests, and their field-level disclosure choices.

Discoverability defaults to false and existing researchers get no row at all, so nobody becomes
findable as a side effect of this migration. Absence of a decision is not consent.

Revision ID: 0028_phase5_12_peer_discovery
Revises:     0027_phase5_11_openings_and_applications
Create Date: 2026-09-25 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0028_phase5_12_peer_discovery"
down_revision: Union[str, None] = "0027_phase5_11_openings_and_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "researcher_discovery_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("is_discoverable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "collaboration_status",
            sa.String(50),
            nullable=False,
            server_default="OPEN_TO_ENQUIRIES",
        ),
        sa.Column("collaboration_interests", JSONB, nullable=True),
        sa.Column("show_institution", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("show_contact_email", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("collaboration_note", sa.Text(), nullable=True),
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "collaboration_status IN ('SEEKING_COLLABORATORS', 'OPEN_TO_ENQUIRIES', "
            "'SELECTIVELY_AVAILABLE', 'NOT_AVAILABLE')",
            name="chk_discovery_settings_collaboration_status",
        ),
    )

    # Peer searches filter on discoverability first, so it leads the composite index.
    op.create_index(
        "idx_discovery_settings_discoverable",
        "researcher_discovery_settings",
        ["is_discoverable", "collaboration_status"],
    )
    op.create_index(
        "idx_discovery_settings_profile",
        "researcher_discovery_settings",
        ["profile_id"],
        unique=True,
    )
    op.create_index(
        "ix_researcher_discovery_settings_profile_id",
        "researcher_discovery_settings",
        ["profile_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("researcher_discovery_settings")
