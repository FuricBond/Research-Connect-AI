"""
Internal data models for the OpenAlex ingestion pipeline.

NormalizedWork         — scholarly work ready for deduplication and persistence
NormalizedResearcher   — author / researcher record
NormalizedResearchSource — publication venue record
NormalizedInstitution  — institution record

Each model mirrors the corresponding database table columns.  They are
dataclasses (not Pydantic) to match the existing scraper codebase style.

``lifecycle_action`` is set by the persistence layer, not the normalizer.
``validation_errors`` is populated by the validator; invalid records are
logged and skipped rather than crashing the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scrapers.models import LifecycleAction


@dataclass
class NormalizedResearcher:
    """
    Normalised author/researcher record ready for persistence.

    Maps to the ``researchers`` table.
    ``openalex_id`` is the compact form (e.g. ``'A5048491430'``), NOT the
    full URL.
    """

    openalex_id: str
    display_name: str

    # Optional identifiers
    orcid: str | None = None           # e.g. "0000-0003-1613-5981"

    # Metrics (non-negative integers)
    works_count: int = 0
    cited_by_count: int = 0

    # Bounded raw payload for future enrichment
    raw_metadata: dict | None = None

    # Pipeline metadata
    lifecycle_action: LifecycleAction | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class NormalizedResearchSource:
    """
    Normalised publication venue record.

    Maps to the ``research_sources`` table.
    This is NOT an opportunity — it is reference metadata about where
    research works are published.
    """

    openalex_id: str                   # compact, e.g. "S1983995261"
    display_name: str

    source_type: str | None = None     # "journal", "repository", …
    issn_l: str | None = None          # linking ISSN
    issn: list[str] | None = None      # all known ISSNs
    is_oa: bool = False
    is_in_doaj: bool = False
    host_organization: str | None = None
    works_count: int = 0
    cited_by_count: int = 0
    homepage_url: str | None = None

    raw_metadata: dict | None = None

    lifecycle_action: LifecycleAction | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class NormalizedInstitution:
    """
    Normalised institution record.

    Maps to the ``institutions`` table.
    """

    openalex_id: str                   # compact, e.g. "I18014758"
    display_name: str

    ror: str | None = None             # e.g. "0213rcc28"
    country_code: str | None = None    # e.g. "CA"
    institution_type: str | None = None  # "education", "company", …
    homepage_url: str | None = None
    works_count: int = 0
    cited_by_count: int = 0

    raw_metadata: dict | None = None

    lifecycle_action: LifecycleAction | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class AuthorshipEntry:
    """Lightweight authorship row linking a work to a researcher."""

    researcher: NormalizedResearcher
    author_position: str | None = None  # "first", "middle", "last"
    is_corresponding: bool = False
    institutions: list[NormalizedInstitution] = field(default_factory=list)


@dataclass
class NormalizedWork:
    """
    Normalised research work record.

    Maps to the ``research_works`` table.
    ``authorships`` carries embedded researcher/institution data; the
    persistence layer upserts each entity separately and then records
    junction-table links.
    """

    openalex_id: str                   # compact, e.g. "W2741809807"
    title: str

    doi: str | None = None             # without resolver, e.g. "10.7717/peerj.4375"
    abstract: str | None = None        # reconstructed from inverted index

    publication_year: int | None = None
    publication_date: str | None = None  # ISO date, e.g. "2018-02-13"

    work_type: str | None = None       # "article", "preprint", …
    language: str | None = None        # "en"

    cited_by_count: int = 0
    is_oa: bool = False
    oa_status: str | None = None       # "gold", "green", "bronze", "hybrid", "closed"
    landing_page_url: str | None = None

    # Embedded entities (normalised separately)
    primary_source: NormalizedResearchSource | None = None
    authorships: list[AuthorshipEntry] = field(default_factory=list)

    # Bounded raw payload for future enrichment
    raw_metadata: dict | None = None

    lifecycle_action: LifecycleAction | None = None
    validation_errors: list[str] = field(default_factory=list)
