"""Phase 2.2A — OpenAlex Research Knowledge Layer

Creates the following tables:
  - researchers
  - research_sources
  - institutions
  - research_works
  - research_work_authors
  - research_work_institutions

These tables form a separate research-knowledge layer that is intentionally
distinct from the ``opportunities`` table.  OpenAlex research entities (works,
authors, journals, institutions) are NOT actionable research opportunities and
must not be forced into the ``opportunities`` schema.

Revision ID: 0003_phase2_2a_openalex_research_knowledge
Revises:     0002_phase2_1_ingestion_hardening
Create Date: 2026-08-25 16:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_phase2_2a_openalex_research_knowledge"
down_revision: Union[str, None] = "0002_phase2_1_ingestion_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. researchers ────────────────────────────────────────────────────────
    op.create_table(
        "researchers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("openalex_id", sa.String(length=50), nullable=False, unique=True,
                  comment="Compact OpenAlex author ID, e.g. 'A5048491430'"),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("orcid", sa.String(length=50), nullable=True,
                  comment="ORCID identifier, e.g. '0000-0003-1613-5981'"),
        sa.Column("works_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cited_by_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("openalex_id", name="uq_researchers_openalex_id"),
    )
    op.create_index("idx_researchers_openalex_id", "researchers", ["openalex_id"], unique=True)
    op.create_index("idx_researchers_orcid", "researchers", ["orcid"], unique=False)
    op.create_index("idx_researchers_last_seen", "researchers", ["last_seen_at"], unique=False)

    # ── 2. research_sources ───────────────────────────────────────────────────
    op.create_table(
        "research_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("openalex_id", sa.String(length=50), nullable=False, unique=True,
                  comment="Compact OpenAlex source ID, e.g. 'S1983995261'"),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True,
                  comment="journal, repository, conference, ebook platform, book series, metadata, other"),
        sa.Column("issn_l", sa.String(length=20), nullable=True,
                  comment="Linking ISSN"),
        sa.Column("issn", postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment="All known ISSNs as a JSON array"),
        sa.Column("is_oa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_in_doaj", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("host_organization", sa.Text(), nullable=True),
        sa.Column("works_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cited_by_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("openalex_id", name="uq_research_sources_openalex_id"),
        sa.CheckConstraint(
            "source_type IN ('journal','repository','conference','ebook platform',"
            "'book series','metadata','other')",
            name="chk_research_sources_type",
        ),
    )
    op.create_index("idx_research_sources_openalex_id", "research_sources", ["openalex_id"], unique=True)
    op.create_index("idx_research_sources_issn_l", "research_sources", ["issn_l"], unique=False)
    op.create_index("idx_research_sources_last_seen", "research_sources", ["last_seen_at"], unique=False)

    # ── 3. institutions ───────────────────────────────────────────────────────
    op.create_table(
        "institutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("openalex_id", sa.String(length=50), nullable=False, unique=True,
                  comment="Compact OpenAlex institution ID, e.g. 'I18014758'"),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("ror", sa.String(length=50), nullable=True,
                  comment="ROR (Research Organization Registry) ID"),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("institution_type", sa.String(length=50), nullable=True,
                  comment="education, company, government, nonprofit, …"),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("works_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cited_by_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("openalex_id", name="uq_institutions_openalex_id"),
    )
    op.create_index("idx_institutions_openalex_id", "institutions", ["openalex_id"], unique=True)
    op.create_index("idx_institutions_ror", "institutions", ["ror"], unique=False)
    op.create_index("idx_institutions_country_code", "institutions", ["country_code"], unique=False)
    op.create_index("idx_institutions_last_seen", "institutions", ["last_seen_at"], unique=False)

    # ── 4. research_works ─────────────────────────────────────────────────────
    op.create_table(
        "research_works",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("openalex_id", sa.String(length=50), nullable=False, unique=True,
                  comment="Compact OpenAlex work ID, e.g. 'W2741809807'"),
        sa.Column("doi", sa.String(length=255), nullable=True,
                  comment="DOI without resolver prefix"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True,
                  comment="Reconstructed from OpenAlex inverted index"),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("publication_date", sa.String(length=20), nullable=True,
                  comment="ISO date string, e.g. '2018-02-13'"),
        sa.Column("work_type", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("cited_by_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_oa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oa_status", sa.String(length=20), nullable=True),
        sa.Column("landing_page_url", sa.Text(), nullable=True),
        sa.Column(
            "primary_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ingestion_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
            comment="Points to the OpenAlex entry in the sources table",
        ),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("openalex_id", name="uq_research_works_openalex_id"),
        sa.CheckConstraint(
            "publication_year >= 1000 AND publication_year <= 2100",
            name="chk_research_works_year",
        ),
    )
    op.create_index("idx_research_works_openalex_id", "research_works", ["openalex_id"], unique=True)
    op.create_index("idx_research_works_doi", "research_works", ["doi"], unique=False)
    op.create_index("idx_research_works_year", "research_works", ["publication_year"], unique=False)
    op.create_index("idx_research_works_type", "research_works", ["work_type"], unique=False)
    op.create_index("idx_research_works_source", "research_works", ["primary_source_id"], unique=False)
    op.create_index("idx_research_works_last_seen", "research_works", ["last_seen_at"], unique=False)

    # ── 5. research_work_authors ─────────────────────────────────────────────
    op.create_table(
        "research_work_authors",
        sa.Column(
            "work_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_works.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "researcher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("researchers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("author_position", sa.String(length=20), nullable=True,
                  comment="first, middle, last"),
        sa.Column("is_corresponding", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_rwa_work_id", "research_work_authors", ["work_id"], unique=False)
    op.create_index("idx_rwa_researcher_id", "research_work_authors", ["researcher_id"], unique=False)

    # ── 6. research_work_institutions ────────────────────────────────────────
    op.create_table(
        "research_work_institutions",
        sa.Column(
            "work_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_works.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "institution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("institutions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_rwi_work_id", "research_work_institutions", ["work_id"], unique=False)
    op.create_index("idx_rwi_institution_id", "research_work_institutions", ["institution_id"], unique=False)


def downgrade() -> None:
    op.drop_table("research_work_institutions")
    op.drop_table("research_work_authors")
    op.drop_table("research_works")
    op.drop_table("institutions")
    op.drop_table("research_sources")
    op.drop_table("researchers")
