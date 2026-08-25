"""
Internal normalized data models for the Crossref ingestion and enrichment pipeline.

NormalizedCrossrefWork   — scholarly work parsed and normalized from Crossref JSON
NormalizedCrossrefAuthor — author representation with ORCID and affiliation
NormalizedCrossrefSource — journal/container/publisher venue representation

These dataclasses decouple raw API responses from database schemas and provide
clean inputs for the enrichment and persistence layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scrapers.models import LifecycleAction


@dataclass
class NormalizedCrossrefAuthor:
    """Normalized author record from Crossref."""
    full_name: str
    given_name: str | None = None
    family_name: str | None = None
    orcid: str | None = None                  # Bare ORCID, e.g. "0000-0003-1613-5981"
    sequence: str | None = None               # "first", "additional"
    affiliations: list[str] = field(default_factory=list)


@dataclass
class NormalizedCrossrefSource:
    """Normalized publication venue/source from Crossref."""
    title: str                                # Container title / journal name
    publisher: str | None = None              # Host organization / publisher
    issn_l: str | None = None                 # Primary linking ISSN if available
    issn: list[str] = field(default_factory=list)  # All known ISSNs (print, electronic)
    source_type: str = "journal"              # Default type


@dataclass
class NormalizedCrossrefWork:
    """
    Normalized scholarly work from Crossref ready for matching, enrichment,
    and persistence.
    """
    doi: str                                  # Canonical DOI, e.g. "10.7717/peerj.4375"
    title: str

    subtitle: str | None = None
    abstract: str | None = None               # JATS XML stripped clean text

    work_type: str | None = None              # article, book-chapter, proceedings, etc.
    publication_year: int | None = None
    publication_date: str | None = None       # ISO date string e.g. "2018-02-13"
    published_online: str | None = None
    published_print: str | None = None

    volume: str | None = None
    issue: str | None = None
    page: str | None = None
    article_number: str | None = None

    url: str | None = None                    # Landing page / resolver URL
    license_url: str | None = None            # Open access license URL if declared
    is_oa: bool = False

    cited_by_count: int = 0
    reference_count: int = 0

    source: NormalizedCrossrefSource | None = None
    authors: list[NormalizedCrossrefAuthor] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)

    raw_metadata: dict | None = None

    # Pipeline tracking
    lifecycle_action: LifecycleAction | None = None
    validation_errors: list[str] = field(default_factory=list)
