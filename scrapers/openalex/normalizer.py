"""
OpenAlex normalizer — converts raw API response dicts into internal models.

Normalisation responsibilities:
  - Extract and compact OpenAlex IDs (strip ``https://openalex.org/`` prefix)
  - Reconstruct abstract text from inverted index
  - Normalise DOIs (strip resolver URL prefix)
  - Normalise ORCIDs (strip URL prefix, keep plain ID)
  - Normalise ROR IDs (strip URL prefix)
  - Coerce numeric fields (cited_by_count, works_count) to non-negative int
  - Build bounded raw_metadata JSONB payload
  - Handle missing / null fields gracefully

Each ``normalize_*`` function accepts the raw dict from the OpenAlex API and
returns the corresponding Normalized* model or raises ValueError for records
that are fundamentally unparseable (missing required field).  The pipeline
catches these and counts them as INVALID.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.openalex.abstract_utils import reconstruct_abstract
from scrapers.openalex.models import (
    AuthorshipEntry,
    NormalizedInstitution,
    NormalizedResearchSource,
    NormalizedResearcher,
    NormalizedWork,
)

logger = logging.getLogger(__name__)

# ── ID normalisation helpers ──────────────────────────────────────────────────

_OPENALEX_ID_RE = re.compile(
    r"https?://openalex\.org/([WAICS]\d+)", re.IGNORECASE
)
_DOI_URL_PREFIX = "https://doi.org/"
_ORCID_URL_PREFIX = "https://orcid.org/"
_ROR_URL_PREFIX = "https://ror.org/"


def extract_openalex_id(full_url: str | None) -> str | None:
    """
    Extract the compact OpenAlex ID from a full URL.

    ``"https://openalex.org/W2741809807"`` → ``"W2741809807"``

    Returns ``None`` if the URL is missing or does not match the expected
    pattern.
    """
    if not full_url:
        return None
    m = _OPENALEX_ID_RE.match(full_url.strip())
    if m:
        return m.group(1)
    # Some responses use the compact ID directly — pass through if it looks right
    stripped = full_url.strip()
    if re.match(r"^[WAICS]\d+$", stripped, re.IGNORECASE):
        return stripped
    return None


def _normalise_doi(doi_url: str | None) -> str | None:
    """Strip the resolver prefix, return bare DOI or None."""
    if not doi_url:
        return None
    doi = doi_url.strip()
    if doi.startswith(_DOI_URL_PREFIX):
        doi = doi[len(_DOI_URL_PREFIX):]
    return doi if doi else None


def _normalise_orcid(orcid_raw: str | None) -> str | None:
    """Strip ORCID URL prefix; return plain ORCID or None."""
    if not orcid_raw:
        return None
    orcid = orcid_raw.strip()
    if orcid.startswith(_ORCID_URL_PREFIX):
        orcid = orcid[len(_ORCID_URL_PREFIX):]
    return orcid if orcid else None


def _normalise_ror(ror_raw: str | None) -> str | None:
    """Strip ROR URL prefix; return compact ROR ID or None."""
    if not ror_raw:
        return None
    ror = ror_raw.strip()
    if ror.startswith(_ROR_URL_PREFIX):
        ror = ror[len(_ROR_URL_PREFIX):]
    return ror if ror else None


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce value to non-negative int, falling back to ``default``."""
    try:
        n = int(value)
        return max(0, n)
    except (TypeError, ValueError):
        return default


# ── Institution normaliser ────────────────────────────────────────────────────


def normalize_institution(raw: dict) -> NormalizedInstitution:
    """
    Normalise a raw OpenAlex institution dict.

    Raises:
        ValueError: If ``id`` or ``display_name`` is missing.
    """
    openalex_id = extract_openalex_id(raw.get("id"))
    if not openalex_id:
        raise ValueError(f"Institution missing valid id: {raw.get('id')!r}")

    display_name = (raw.get("display_name") or "").strip()
    if not display_name:
        raise ValueError(f"Institution {openalex_id} missing display_name")

    ror_raw = (raw.get("ror") or "").strip() or None
    ror = _normalise_ror(ror_raw)

    raw_metadata: dict = {
        "openalex_id": raw.get("id"),
        "lineage": raw.get("lineage", []),
        "type": raw.get("type"),
        "country_code": raw.get("country_code"),
    }

    return NormalizedInstitution(
        openalex_id=openalex_id,
        display_name=display_name,
        ror=ror,
        country_code=raw.get("country_code"),
        institution_type=raw.get("type"),
        homepage_url=raw.get("homepage_url"),
        works_count=_safe_int(raw.get("works_count")),
        cited_by_count=_safe_int(raw.get("cited_by_count")),
        raw_metadata=raw_metadata,
    )


# ── Researcher normaliser ─────────────────────────────────────────────────────


def normalize_researcher(raw: dict) -> NormalizedResearcher:
    """
    Normalise a raw OpenAlex author dict (either a full author object or the
    embedded stub found in authorship entries).

    Raises:
        ValueError: If ``id`` or ``display_name`` is missing.
    """
    openalex_id = extract_openalex_id(raw.get("id"))
    if not openalex_id:
        raise ValueError(f"Researcher missing valid id: {raw.get('id')!r}")

    display_name = (raw.get("display_name") or "").strip()
    if not display_name:
        raise ValueError(f"Researcher {openalex_id} missing display_name")

    orcid = _normalise_orcid(raw.get("orcid"))

    raw_metadata: dict = {
        "openalex_id": raw.get("id"),
        "orcid": raw.get("orcid"),
    }

    return NormalizedResearcher(
        openalex_id=openalex_id,
        display_name=display_name,
        orcid=orcid,
        works_count=_safe_int(raw.get("works_count")),
        cited_by_count=_safe_int(raw.get("cited_by_count")),
        raw_metadata=raw_metadata,
    )


# ── ResearchSource normaliser ─────────────────────────────────────────────────


def normalize_research_source(raw: dict) -> NormalizedResearchSource:
    """
    Normalise a raw OpenAlex source/venue dict.

    Raises:
        ValueError: If ``id`` or ``display_name`` is missing.
    """
    openalex_id = extract_openalex_id(raw.get("id"))
    if not openalex_id:
        raise ValueError(f"ResearchSource missing valid id: {raw.get('id')!r}")

    display_name = (raw.get("display_name") or "").strip()
    if not display_name:
        raise ValueError(f"ResearchSource {openalex_id} missing display_name")

    issn_raw = raw.get("issn")
    issn: list[str] | None = issn_raw if isinstance(issn_raw, list) else None

    raw_metadata: dict = {
        "openalex_id": raw.get("id"),
        "type": raw.get("type"),
        "host_organization": raw.get("host_organization"),
        "host_organization_name": raw.get("host_organization_name"),
        "is_core": raw.get("is_core"),
    }

    return NormalizedResearchSource(
        openalex_id=openalex_id,
        display_name=display_name,
        source_type=raw.get("type"),
        issn_l=raw.get("issn_l"),
        issn=issn,
        is_oa=bool(raw.get("is_oa", False)),
        is_in_doaj=bool(raw.get("is_in_doaj", False)),
        host_organization=raw.get("host_organization_name") or raw.get("host_organization"),
        works_count=_safe_int(raw.get("works_count")),
        cited_by_count=_safe_int(raw.get("cited_by_count")),
        homepage_url=raw.get("homepage_url"),
        raw_metadata=raw_metadata,
    )


# ── Work normaliser ───────────────────────────────────────────────────────────


def _extract_primary_source(raw_work: dict) -> NormalizedResearchSource | None:
    """Extract and normalise the primary location's source from a work dict."""
    primary_location = raw_work.get("primary_location") or {}
    source_raw = primary_location.get("source")
    if not source_raw or not isinstance(source_raw, dict):
        return None
    try:
        return normalize_research_source(source_raw)
    except (ValueError, Exception) as exc:
        logger.debug("Could not normalise primary source: %s", exc)
        return None


def _extract_authorships(raw_work: dict) -> list[AuthorshipEntry]:
    """
    Extract and normalise the authorships list from a work dict.

    Skips individual invalid author/institution entries (logs a debug message)
    rather than failing the entire work.
    """
    entries: list[AuthorshipEntry] = []
    for authorship in raw_work.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author_raw = authorship.get("author")
        if not author_raw or not isinstance(author_raw, dict):
            continue

        try:
            researcher = normalize_researcher(author_raw)
        except ValueError as exc:
            logger.debug("Skipping invalid author in work: %s", exc)
            continue

        institutions: list[NormalizedInstitution] = []
        for inst_raw in authorship.get("institutions") or []:
            if not isinstance(inst_raw, dict):
                continue
            try:
                institutions.append(normalize_institution(inst_raw))
            except ValueError as exc:
                logger.debug("Skipping invalid institution in authorship: %s", exc)

        entries.append(
            AuthorshipEntry(
                researcher=researcher,
                author_position=authorship.get("author_position"),
                is_corresponding=bool(authorship.get("is_corresponding", False)),
                institutions=institutions,
            )
        )
    return entries


def _build_work_raw_metadata(raw: dict) -> dict:
    """
    Build a bounded raw_metadata payload for a work.

    Includes topics/keywords/concepts for future AI use, plus key identifiers.
    Excludes huge fields like ``referenced_works``, ``related_works``,
    ``locations`` (which can be very large lists).
    """
    return {
        "openalex_id": raw.get("id"),
        "doi": raw.get("doi"),
        "ids": raw.get("ids"),
        "primary_topic": raw.get("primary_topic"),
        "topics": raw.get("topics", []),
        "keywords": raw.get("keywords", []),
        "concepts": raw.get("concepts", [])[:10],  # keep top 10 by score
        "open_access": raw.get("open_access"),
        "biblio": raw.get("biblio"),
        "indexed_in": raw.get("indexed_in", []),
        "counts_by_year": raw.get("counts_by_year", [])[:5],  # last 5 years
        "cited_by_count": raw.get("cited_by_count"),
        "updated_date": raw.get("updated_date"),
    }


def normalize_work(raw: dict) -> NormalizedWork:
    """
    Normalise a raw OpenAlex work dict into a ``NormalizedWork``.

    Raises:
        ValueError: If ``id`` or ``title`` is missing.
    """
    openalex_id = extract_openalex_id(raw.get("id"))
    if not openalex_id:
        raise ValueError(f"Work missing valid id: {raw.get('id')!r}")

    # OpenAlex uses both "title" and "display_name" — prefer "title"
    title_raw = raw.get("title") or raw.get("display_name") or ""
    title = title_raw.strip()
    if not title:
        raise ValueError(f"Work {openalex_id} missing title")

    # Abstract
    abstract = reconstruct_abstract(raw.get("abstract_inverted_index"))

    # DOI
    doi = _normalise_doi(raw.get("doi"))

    # Open access
    oa_info = raw.get("open_access") or {}
    is_oa = bool(oa_info.get("is_oa", False))
    oa_status = oa_info.get("oa_status")

    # Landing page URL (from primary_location)
    primary_location = raw.get("primary_location") or {}
    landing_page_url = primary_location.get("landing_page_url") or oa_info.get("oa_url")

    return NormalizedWork(
        openalex_id=openalex_id,
        title=title,
        doi=doi,
        abstract=abstract,
        publication_year=raw.get("publication_year"),
        publication_date=raw.get("publication_date"),
        work_type=raw.get("type"),
        language=raw.get("language"),
        cited_by_count=_safe_int(raw.get("cited_by_count")),
        is_oa=is_oa,
        oa_status=oa_status,
        landing_page_url=landing_page_url,
        primary_source=_extract_primary_source(raw),
        authorships=_extract_authorships(raw),
        raw_metadata=_build_work_raw_metadata(raw),
    )
