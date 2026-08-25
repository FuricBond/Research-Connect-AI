"""
Lightweight structural mirrors of the OpenAlex JSON response.

These dataclasses are used during parsing to give type-checked access to
the raw API response fields.  They deliberately avoid heavy validation
(that is the validator's job) and map closely to the actual JSON structure
observed from the API.

Key observations from live API inspection (2026-08-25):
  - ``id`` is always the full URL form: ``https://openalex.org/W...``
  - ``abstract_inverted_index`` may be absent, null, empty, or a dict
  - ``authorships`` is a list of objects each with an embedded ``author``
    and ``institutions`` sub-list
  - ``primary_location.source`` may be null (no publication venue)
  - Numeric fields (cited_by_count, works_count) are integers, never null

We keep these models minimal — only fields we actually normalise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OAAuthorResponse:
    """Embedded author stub inside an authorship object."""
    id: str                          # full URL, e.g. "https://openalex.org/A5048491430"
    display_name: str
    orcid: str | None = None         # full URL or plain ID or null


@dataclass
class OAInstitutionResponse:
    """Embedded institution stub inside an authorship object."""
    id: str                          # full URL
    display_name: str
    ror: str | None = None           # full URL or compact ID
    country_code: str | None = None
    type: str | None = None          # "education", "company", …


@dataclass
class OAAuthorshipResponse:
    """Single entry in the ``authorships`` list of a work."""
    author: OAAuthorResponse
    author_position: str | None = None          # "first", "middle", "last"
    is_corresponding: bool = False
    institutions: list[OAInstitutionResponse] = field(default_factory=list)


@dataclass
class OASourceResponse:
    """Embedded source/venue object (from ``primary_location.source``)."""
    id: str                          # full URL
    display_name: str
    type: str | None = None
    issn_l: str | None = None
    issn: list[str] | None = None
    is_oa: bool = False
    is_in_doaj: bool = False
    host_organization_name: str | None = None
    homepage_url: str | None = None


@dataclass
class OAPrimaryLocationResponse:
    """``primary_location`` object from a work response."""
    landing_page_url: str | None = None
    is_oa: bool = False
    source: OASourceResponse | None = None


@dataclass
class OAOpenAccessResponse:
    """``open_access`` object from a work response."""
    is_oa: bool = False
    oa_status: str | None = None     # "gold", "green", "bronze", "hybrid", "closed"
    oa_url: str | None = None


@dataclass
class OAWorkResponse:
    """Top-level work object from the OpenAlex /works endpoint."""
    id: str                          # full URL, e.g. "https://openalex.org/W2741809807"
    title: str
    display_name: str

    publication_year: int | None = None
    publication_date: str | None = None
    work_type: str | None = None     # OpenAlex calls this "type"
    language: str | None = None
    cited_by_count: int = 0

    doi: str | None = None           # full URL, e.g. "https://doi.org/10.7717/peerj.4375"

    primary_location: OAPrimaryLocationResponse | None = None
    open_access: OAOpenAccessResponse | None = None
    authorships: list[OAAuthorshipResponse] = field(default_factory=list)

    # abstract_inverted_index is preserved as raw dict/None for abstract_utils
    abstract_inverted_index: Any = None

    # Selective raw fields for raw_metadata JSONB (keywords/topics for future use)
    keywords: list[dict] = field(default_factory=list)
    topics: list[dict] = field(default_factory=list)
    concepts: list[dict] = field(default_factory=list)
