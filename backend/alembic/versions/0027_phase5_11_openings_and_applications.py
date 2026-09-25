"""Phase 5.11 — Research internships, RA openings and the application workflow

Extends research_postings into funded appointments and adds the application record:

  1. Widens chk_research_postings_type to admit INTERNSHIP, RESEARCH_ASSISTANTSHIP and POSTDOC.
     A CHECK constraint cannot be altered in place, so it is dropped and recreated.
  2. Adds the structured opening terms (compensation, commitment, duration, eligibility) and
     the accepts_applications switch. Existing rows default to UNSPECIFIED compensation and
     accepts_applications = false, which preserves current behaviour for Phase 5.10 postings.
  3. Creates research_posting_applications, with one application per researcher per posting and
     an append-only status history readable by both the applicant and the posting's author.

Revision ID: 0027_phase5_11_openings_and_applications
Revises:     0026_phase5_10_research_postings
Create Date: 2026-09-25 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "0027_phase5_11_openings_and_applications"
down_revision: Union[str, None] = "0026_phase5_10_research_postings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PHASE_5_10_TYPES = "'PROJECT', 'THESIS_TOPIC', 'COLLABORATION', 'LAB_ROTATION'"
_PHASE_5_11_TYPES = "'INTERNSHIP', 'RESEARCH_ASSISTANTSHIP', 'POSTDOC'"


def upgrade() -> None:
    # 1. Widen the posting-type vocabulary.
    op.drop_constraint("chk_research_postings_type", "research_postings", type_="check")
    op.create_check_constraint(
        "chk_research_postings_type",
        "research_postings",
        f"posting_type IN ({_PHASE_5_10_TYPES}, {_PHASE_5_11_TYPES})",
    )

    # 2. Structured opening terms.
    op.add_column(
        "research_postings",
        sa.Column("compensation_type", sa.String(50), nullable=False, server_default="UNSPECIFIED"),
    )
    op.add_column(
        "research_postings", sa.Column("compensation_amount", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "research_postings", sa.Column("compensation_currency", sa.String(3), nullable=True)
    )
    op.add_column(
        "research_postings", sa.Column("compensation_period", sa.String(20), nullable=True)
    )
    op.add_column("research_postings", sa.Column("commitment_type", sa.String(50), nullable=True))
    op.add_column("research_postings", sa.Column("hours_per_week", sa.Integer(), nullable=True))
    op.add_column("research_postings", sa.Column("duration_months", sa.Integer(), nullable=True))
    op.add_column(
        "research_postings", sa.Column("eligibility_requirements", sa.Text(), nullable=True)
    )
    op.add_column(
        "research_postings",
        sa.Column("accepts_applications", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_check_constraint(
        "chk_research_postings_compensation_type",
        "research_postings",
        "compensation_type IN ('STIPEND', 'SALARY', 'HOURLY', 'SCHOLARSHIP', 'GRANT_FUNDED', "
        "'UNPAID', 'UNSPECIFIED')",
    )
    op.create_check_constraint(
        "chk_research_postings_commitment_type",
        "research_postings",
        "commitment_type IS NULL OR commitment_type IN ('FULL_TIME', 'PART_TIME', 'FLEXIBLE')",
    )
    op.create_check_constraint(
        "chk_research_postings_duration_positive",
        "research_postings",
        "duration_months IS NULL OR duration_months >= 1",
    )
    op.create_check_constraint(
        "chk_research_postings_compensation_non_negative",
        "research_postings",
        "compensation_amount IS NULL OR compensation_amount >= 0",
    )

    # 3. Applications.
    op.create_table(
        "research_posting_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "posting_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_postings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "applicant_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "applicant_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="SUBMITTED"),
        sa.Column("cover_note", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("portfolio_url", sa.Text(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("status_history", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "posting_id", "applicant_profile_id", name="uq_posting_application_applicant"
        ),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'UNDER_REVIEW', 'SHORTLISTED', 'OFFERED', 'ACCEPTED', "
            "'DECLINED', 'REJECTED', 'WITHDRAWN')",
            name="chk_posting_applications_status",
        ),
    )

    for name, columns in (
        ("idx_posting_applications_applicant", ["applicant_profile_id"]),
        ("idx_posting_applications_posting_status", ["posting_id", "status"]),
        ("idx_posting_applications_submitted", ["submitted_at"]),
        ("ix_research_posting_applications_applicant_profile_id", ["applicant_profile_id"]),
        ("ix_research_posting_applications_applicant_user_id", ["applicant_user_id"]),
        ("ix_research_posting_applications_posting_id", ["posting_id"]),
        ("ix_research_posting_applications_status", ["status"]),
    ):
        op.create_index(name, "research_posting_applications", columns)


def downgrade() -> None:
    op.drop_table("research_posting_applications")

    for name in (
        "chk_research_postings_compensation_non_negative",
        "chk_research_postings_duration_positive",
        "chk_research_postings_commitment_type",
        "chk_research_postings_compensation_type",
    ):
        op.drop_constraint(name, "research_postings", type_="check")

    for column in (
        "accepts_applications",
        "eligibility_requirements",
        "duration_months",
        "hours_per_week",
        "commitment_type",
        "compensation_period",
        "compensation_currency",
        "compensation_amount",
        "compensation_type",
    ):
        op.drop_column("research_postings", column)

    # Any posting carrying a Phase 5.11 category must be retyped before the narrower
    # constraint can be restored, otherwise the downgrade would fail on existing data.
    op.execute(
        f"UPDATE research_postings SET posting_type = 'PROJECT' "
        f"WHERE posting_type IN ({_PHASE_5_11_TYPES})"
    )
    op.drop_constraint("chk_research_postings_type", "research_postings", type_="check")
    op.create_check_constraint(
        "chk_research_postings_type",
        "research_postings",
        f"posting_type IN ({_PHASE_5_10_TYPES})",
    )
