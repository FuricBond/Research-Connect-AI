"""
Research knowledge layer — SQLAlchemy ORM models for Phase 2.2A (OpenAlex).

These models represent structured research-knowledge entities ingested from
OpenAlex.  They are intentionally separate from the ``opportunities`` table,
which stores *actionable* research calls (conferences, journals, workshops …).

Tables
------
researchers              — individual authors / researchers
research_sources         — publication venues (journals, repositories, …)
institutions             — universities, research labs, companies
research_works           — individual scholarly works (articles, datasets, …)
research_work_authors    — many-to-many: works ↔ researchers
research_work_institutions — many-to-many: works ↔ institutions (via authorships)

Provenance
----------
Every record is traceable to OpenAlex via ``openalex_id`` (unique per table).
The ``source_id`` on ``research_works`` points to the ``sources`` table entry
for "OpenAlex" (type=API), mirroring the existing provenance architecture.

Topics
------
OpenAlex topic/keyword data is stored inside ``raw_metadata`` JSONB rather
than in the existing ``topics`` table.  The existing taxonomy is not modified
in this phase.  A future migration can introduce a proper bridge table once
the reconciliation strategy is decided.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.source import SourceModel


# ── Researcher / Author ───────────────────────────────────────────────────────


class ResearcherModel(Base, TimestampMixin):
    """Individual researcher / author, normalised from OpenAlex author objects."""

    __tablename__ = "researchers"
    __table_args__ = (
        UniqueConstraint("openalex_id", name="uq_researchers_openalex_id"),
        Index("idx_researchers_openalex_id", "openalex_id"),
        Index("idx_researchers_orcid", "orcid"),
        Index("idx_researchers_last_seen", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # OpenAlex identity
    openalex_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Compact OpenAlex author ID, e.g. 'A5048491430'",
    )

    # Core fields
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    orcid: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="ORCID identifier, e.g. '0000-0003-1613-5981'",
    )

    # Citation metrics
    works_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Raw API payload for future enrichment
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Freshness tracking
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    work_authorships: Mapped[list["ResearchWorkAuthorModel"]] = relationship(
        back_populates="researcher",
        cascade="all, delete-orphan",
    )


# ── Research Source (publication venue) ──────────────────────────────────────


class ResearchSourceModel(Base, TimestampMixin):
    """
    Publication venue from OpenAlex (journal, repository, conference series …).

    This is NOT automatically converted into an ``OpportunityModel``.
    It acts as reference metadata about where research works are published.
    A future phase may use it to enrich JOURNAL opportunities in the
    ``opportunities`` table.
    """

    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint("openalex_id", name="uq_research_sources_openalex_id"),
        CheckConstraint(
            "source_type IN ('journal','repository','conference','ebook platform',"
            "'book series','metadata','other')",
            name="chk_research_sources_type",
        ),
        Index("idx_research_sources_openalex_id", "openalex_id"),
        Index("idx_research_sources_issn_l", "issn_l"),
        Index("idx_research_sources_last_seen", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # OpenAlex identity
    openalex_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Compact OpenAlex source ID, e.g. 'S1983995261'",
    )

    # Core fields
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="OpenAlex source type: journal, repository, conference, …",
    )

    # Publisher / journal identifiers
    issn_l: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Linking ISSN (canonical across print/online editions)",
    )
    issn: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="All known ISSNs as a JSON list",
    )

    # Open-access flags
    is_oa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_in_doaj: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Host organisation
    host_organization: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Publisher / host organisation display name",
    )

    # Metrics
    works_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # URLs
    homepage_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Raw API payload
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Freshness tracking
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    primary_works: Mapped[list["ResearchWorkModel"]] = relationship(
        back_populates="primary_source",
        foreign_keys="ResearchWorkModel.primary_source_id",
    )


# ── Institution ───────────────────────────────────────────────────────────────


class InstitutionModel(Base, TimestampMixin):
    """Research institution (university, lab, company, …), normalised from OpenAlex."""

    __tablename__ = "institutions"
    __table_args__ = (
        UniqueConstraint("openalex_id", name="uq_institutions_openalex_id"),
        Index("idx_institutions_openalex_id", "openalex_id"),
        Index("idx_institutions_ror", "ror"),
        Index("idx_institutions_country_code", "country_code"),
        Index("idx_institutions_last_seen", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # OpenAlex identity
    openalex_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Compact OpenAlex institution ID, e.g. 'I18014758'",
    )

    # Core fields
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    ror: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="ROR (Research Organization Registry) ID",
    )
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    institution_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="education, company, government, nonprofit, …",
    )
    homepage_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metrics
    works_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Raw API payload
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Freshness tracking
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    work_institution_links: Mapped[list["ResearchWorkInstitutionModel"]] = relationship(
        back_populates="institution",
        cascade="all, delete-orphan",
    )


# ── Research Work ─────────────────────────────────────────────────────────────


class ResearchWorkModel(Base, TimestampMixin):
    """
    Individual scholarly work (article, preprint, dataset, book chapter, …)
    normalised from OpenAlex.

    OpenAlex topics/keywords are stored inside ``raw_metadata`` JSONB so they
    can be accessed without a separate query and without altering the existing
    ``topics`` taxonomy.
    """

    __tablename__ = "research_works"
    __table_args__ = (
        UniqueConstraint("openalex_id", name="uq_research_works_openalex_id"),
        CheckConstraint(
            "publication_year >= 1000 AND publication_year <= 2100",
            name="chk_research_works_year",
        ),
        Index("idx_research_works_openalex_id", "openalex_id"),
        Index("idx_research_works_doi", "doi"),
        Index("idx_research_works_year", "publication_year"),
        Index("idx_research_works_type", "work_type"),
        Index("idx_research_works_source", "primary_source_id"),
        Index("idx_research_works_last_seen", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # OpenAlex identity
    openalex_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Compact OpenAlex work ID, e.g. 'W2741809807'",
    )

    # Bibliographic identifiers
    doi: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="DOI without resolver prefix, e.g. '10.7717/peerj.4375'",
    )

    # Core content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reconstructed from OpenAlex inverted index, or None",
    )

    # Dates
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication_date: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="ISO date string, e.g. '2018-02-13'",
    )

    # Classification
    work_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="article, preprint, book-chapter, dataset, …",
    )
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Citations
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Open Access
    is_oa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    oa_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="gold, green, bronze, hybrid, closed",
    )

    # Primary location
    landing_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # FK to primary publication venue
    primary_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    # FK to source (provenance) — points to the "OpenAlex" entry in sources table
    ingestion_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
        comment="Points to the OpenAlex entry in the sources table",
    )

    # Raw API payload — bounded subset of useful fields
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Freshness tracking
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    primary_source: Mapped[Optional["ResearchSourceModel"]] = relationship(
        back_populates="primary_works",
        foreign_keys=[primary_source_id],
    )
    ingestion_source: Mapped[Optional["SourceModel"]] = relationship(
        foreign_keys=[ingestion_source_id],
    )
    author_links: Mapped[list["ResearchWorkAuthorModel"]] = relationship(
        back_populates="work",
        cascade="all, delete-orphan",
    )
    institution_links: Mapped[list["ResearchWorkInstitutionModel"]] = relationship(
        back_populates="work",
        cascade="all, delete-orphan",
    )


# ── Junction: Work ↔ Researcher ───────────────────────────────────────────────


class ResearchWorkAuthorModel(Base):
    """Many-to-many junction: research work ↔ researcher with authorship metadata."""

    __tablename__ = "research_work_authors"
    __table_args__ = (
        Index("idx_rwa_work_id", "work_id"),
        Index("idx_rwa_researcher_id", "researcher_id"),
    )

    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_works.id", ondelete="CASCADE"),
        primary_key=True,
    )
    researcher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("researchers.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Author position from OpenAlex: "first", "middle", "last"
    author_position: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_corresponding: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    work: Mapped["ResearchWorkModel"] = relationship(back_populates="author_links")
    researcher: Mapped["ResearcherModel"] = relationship(
        back_populates="work_authorships"
    )


# ── Junction: Work ↔ Institution ──────────────────────────────────────────────


class ResearchWorkInstitutionModel(Base):
    """Many-to-many junction: research work ↔ institution (via authorships)."""

    __tablename__ = "research_work_institutions"
    __table_args__ = (
        Index("idx_rwi_work_id", "work_id"),
        Index("idx_rwi_institution_id", "institution_id"),
    )

    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_works.id", ondelete="CASCADE"),
        primary_key=True,
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("institutions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    work: Mapped["ResearchWorkModel"] = relationship(back_populates="institution_links")
    institution: Mapped["InstitutionModel"] = relationship(
        back_populates="work_institution_links"
    )
