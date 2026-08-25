"""
Crossref normalizer — transforms raw Crossref API JSON items into normalized models.

Responsibilities:
  - Canonicalize DOI via doi_utils
  - Clean JATS/XML markup from abstracts
  - Parse date-parts arrays into ISO date strings and publication years
  - Normalize author names, ORCIDs, and affiliations
  - Map Crossref work types to standard taxonomy
  - Extract container (journal/venue) metadata and ISSNs
  - Construct structured raw_metadata JSONB payload
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

from scrapers.crossref.doi_utils import canonicalize_doi
from scrapers.crossref.models import (
    NormalizedCrossrefAuthor,
    NormalizedCrossrefSource,
    NormalizedCrossrefWork,
)

logger = logging.getLogger(__name__)

# Regex for stripping XML/JATS tags from abstracts
_XML_TAG_PATTERN = re.compile(r"<[^>]+>")
_ORCID_PREFIX_PATTERN = re.compile(r"^https?://orcid\.org/", re.IGNORECASE)

# Mapping from Crossref work types to standard taxonomy
_WORK_TYPE_MAP = {
    "journal-article": "article",
    "proceedings-article": "proceedings",
    "book-chapter": "book-chapter",
    "posted-content": "preprint",
    "monograph": "book",
    "edited-book": "book",
    "reference-book": "book",
    "dataset": "dataset",
    "peer-review": "peer-review",
    "report": "report",
    "dissertation": "dissertation",
    "standard": "standard",
}


def clean_jats_abstract(raw_abstract: str | None) -> str | None:
    """
    Remove JATS/HTML tags and unescape entities from Crossref abstract text.

    Example:
        '<jats:p>Despite growing interest in Open Access...</jats:p>'
        -> 'Despite growing interest in Open Access...'
    """
    if not raw_abstract:
        return None

    if not isinstance(raw_abstract, str):
        return None

    # Strip XML tags
    stripped = _XML_TAG_PATTERN.sub(" ", raw_abstract)
    # Unescape HTML entities (&amp;, &lt;, &gt;, &quot;, &#x27;)
    unescaped = html.unescape(stripped)
    # Normalize whitespace
    collapsed = " ".join(unescaped.split())
    # Fix spacing before punctuation caused by tag stripping (e.g. "word ." -> "word.")
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", collapsed)
    return cleaned if cleaned else None


def normalize_orcid(raw_orcid: str | None) -> str | None:
    """Strip URL prefix from ORCID, returning canonical bare ID e.g. '0000-0003-1613-5981'."""
    if not raw_orcid:
        return None
    cleaned = raw_orcid.strip()
    cleaned = _ORCID_PREFIX_PATTERN.sub("", cleaned)
    # Basic check: 16 chars with hyphens (e.g. 0000-0003-1613-5981 or ending in X)
    if re.match(r"^\d{4}-\d{4}-\d{4}-[\dX]{4}$", cleaned, re.IGNORECASE):
        return cleaned.upper()
    return cleaned if cleaned else None


def parse_crossref_date_parts(date_dict: dict[str, Any] | None) -> tuple[str | None, int | None]:
    """
    Parse a Crossref date object containing date-parts into (iso_date_str, year).

    Crossref formats:
      - {"date-parts": [[2018, 2, 13]]} -> ("2018-02-13", 2018)
      - {"date-parts": [[2018, 2]]}     -> ("2018-02", 2018)
      - {"date-parts": [[2018]]}        -> ("2018", 2018)
    """
    if not isinstance(date_dict, dict):
        return None, None

    date_parts = date_dict.get("date-parts")
    if not date_parts or not isinstance(date_parts, list) or not date_parts[0]:
        return None, None

    parts = date_parts[0]
    if not isinstance(parts, list) or not parts:
        return None, None

    try:
        year = int(parts[0])
        if len(parts) >= 3:
            month = int(parts[1])
            day = int(parts[2])
            return f"{year:04d}-{month:02d}-{day:02d}", year
        elif len(parts) == 2:
            month = int(parts[1])
            return f"{year:04d}-{month:02d}", year
        else:
            return f"{year:04d}", year
    except (ValueError, TypeError, IndexError):
        return None, None


def normalize_crossref_author(raw_author: dict[str, Any]) -> NormalizedCrossrefAuthor | None:
    """Normalize a single Crossref author object."""
    if not isinstance(raw_author, dict):
        return None

    given = raw_author.get("given", "").strip() if raw_author.get("given") else None
    family = raw_author.get("family", "").strip() if raw_author.get("family") else None
    name = raw_author.get("name", "").strip() if raw_author.get("name") else None

    # Construct full name
    if family and given:
        full_name = f"{given} {family}"
    elif family:
        full_name = family
    elif given:
        full_name = given
    elif name:
        full_name = name
    else:
        return None

    orcid = normalize_orcid(raw_author.get("ORCID"))
    sequence = raw_author.get("sequence")

    # Affiliations
    affiliations: list[str] = []
    for aff in raw_author.get("affiliation", []):
        if isinstance(aff, dict) and aff.get("name"):
            aff_name = aff["name"].strip()
            if aff_name:
                affiliations.append(aff_name)
        elif isinstance(aff, str) and aff.strip():
            affiliations.append(aff.strip())

    return NormalizedCrossrefAuthor(
        full_name=full_name,
        given_name=given,
        family_name=family,
        orcid=orcid,
        sequence=sequence,
        affiliations=affiliations,
    )


def normalize_crossref_source(raw: dict[str, Any]) -> NormalizedCrossrefSource | None:
    """Normalize container-title, publisher, and ISSN from Crossref item."""
    container_titles = raw.get("container-title", [])
    title: str | None = None
    if isinstance(container_titles, list) and container_titles:
        title = container_titles[0].strip() if container_titles[0] else None
    elif isinstance(container_titles, str):
        title = container_titles.strip()

    publisher = raw.get("publisher", "").strip() if raw.get("publisher") else None

    # Extract all ISSNs
    issns: list[str] = []
    raw_issn = raw.get("ISSN", [])
    if isinstance(raw_issn, list):
        for val in raw_issn:
            if isinstance(val, str) and val.strip():
                issns.append(val.strip())
    elif isinstance(raw_issn, str) and raw_issn.strip():
        issns.append(raw_issn.strip())

    # Check issn-type list if available
    for entry in raw.get("issn-type", []):
        if isinstance(entry, dict) and entry.get("value"):
            val = entry["value"].strip()
            if val and val not in issns:
                issns.append(val)

    issn_l = issns[0] if issns else None

    if not title and not publisher and not issns:
        return None

    return NormalizedCrossrefSource(
        title=title or publisher or "Unknown Venue",
        publisher=publisher,
        issn_l=issn_l,
        issn=issns,
        source_type="journal" if title else "other",
    )


def normalize_crossref_work(raw: dict[str, Any]) -> NormalizedCrossrefWork:
    """
    Transform raw Crossref work JSON message into NormalizedCrossrefWork.

    Raises:
        ValueError: If mandatory fields (DOI or Title) are missing or invalid.
    """
    if not isinstance(raw, dict):
        raise ValueError("Invalid Crossref work payload: expected dict")

    raw_doi = raw.get("DOI")
    canonical_doi = canonicalize_doi(raw_doi)
    if not canonical_doi:
        raise ValueError(f"Missing or invalid DOI in Crossref item: {raw_doi!r}")

    # Title extraction
    title_list = raw.get("title", [])
    title: str | None = None
    if isinstance(title_list, list) and title_list:
        title = title_list[0].strip() if title_list[0] else None
    elif isinstance(title_list, str):
        title = title_list.strip()

    if not title:
        raise ValueError(f"Missing title for Crossref work with DOI {canonical_doi}")

    # Subtitle
    subtitle_list = raw.get("subtitle", [])
    subtitle: str | None = None
    if isinstance(subtitle_list, list) and subtitle_list:
        subtitle = subtitle_list[0].strip() if subtitle_list[0] else None

    # Abstract
    abstract = clean_jats_abstract(raw.get("abstract"))

    # Work type mapping
    raw_type = raw.get("type")
    work_type = _WORK_TYPE_MAP.get(raw_type, raw_type) if raw_type else None

    # Dates
    pub_online, year_online = parse_crossref_date_parts(raw.get("published-online"))
    pub_print, year_print = parse_crossref_date_parts(raw.get("published-print"))
    pub_issued, year_issued = parse_crossref_date_parts(raw.get("issued") or raw.get("created"))

    publication_date = pub_online or pub_print or pub_issued
    publication_year = year_online or year_print or year_issued

    # Authors
    authors: list[NormalizedCrossrefAuthor] = []
    for author_item in raw.get("author", []):
        author = normalize_crossref_author(author_item)
        if author:
            authors.append(author)

    # Source
    source = normalize_crossref_source(raw)

    # Open Access License check
    license_url: str | None = None
    is_oa = False
    for lic in raw.get("license", []):
        if isinstance(lic, dict) and lic.get("URL"):
            license_url = lic["URL"].strip()
            if any(term in license_url.lower() for term in ["creativecommons.org", "open-access", "cc-by"]):
                is_oa = True
            break

    # Bibliographic fields
    volume = str(raw.get("volume")).strip() if raw.get("volume") is not None else None
    issue = str(raw.get("issue")).strip() if raw.get("issue") is not None else None
    page = str(raw.get("page")).strip() if raw.get("page") is not None else None
    article_number = str(raw.get("article-number")).strip() if raw.get("article-number") is not None else None

    # Citations
    cited_by_count = int(raw.get("is-referenced-by-count") or 0)
    reference_count = int(raw.get("reference-count") or 0)

    # Subjects
    subjects = [s.strip() for s in raw.get("subject", []) if isinstance(s, str) and s.strip()]

    # Construct bounded raw_metadata
    raw_metadata = {
        "crossref": {
            "doi": canonical_doi,
            "publisher": raw.get("publisher"),
            "container_title": raw.get("container-title"),
            "type": raw.get("type"),
            "volume": volume,
            "issue": issue,
            "page": page,
            "license": raw.get("license"),
            "is_referenced_by_count": cited_by_count,
            "reference_count": reference_count,
            "published_online": pub_online,
            "published_print": pub_print,
            "indexed": raw.get("indexed"),
            "deposited": raw.get("deposited"),
        }
    }

    return NormalizedCrossrefWork(
        doi=canonical_doi,
        title=title,
        subtitle=subtitle,
        abstract=abstract,
        work_type=work_type,
        publication_year=publication_year,
        publication_date=publication_date,
        published_online=pub_online,
        published_print=pub_print,
        volume=volume,
        issue=issue,
        page=page,
        article_number=article_number,
        url=raw.get("URL"),
        license_url=license_url,
        is_oa=is_oa,
        cited_by_count=cited_by_count,
        reference_count=reference_count,
        source=source,
        authors=authors,
        subjects=subjects,
        raw_metadata=raw_metadata,
    )
