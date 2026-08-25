"""
Crossref validator — validates normalized Crossref models before matching/persistence.

Philosophy:
  - Validates integrity of normalized Crossref objects.
  - Invalid records are rejected and logged, never crashing the ingestion run.
  - Returns (is_valid: bool, errors: list[str]).
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from scrapers.crossref.doi_utils import is_valid_doi
from scrapers.crossref.models import (
    NormalizedCrossrefAuthor,
    NormalizedCrossrefSource,
    NormalizedCrossrefWork,
)

logger = logging.getLogger(__name__)

_ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-[\dX]{4}$", re.IGNORECASE)
_YEAR_MIN = 1000
_YEAR_MAX = 2100


def _is_valid_url(url: str | None) -> bool:
    """Return True if URL has http/https scheme and non-empty netloc."""
    if not url:
        return True
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def validate_crossref_author(author: NormalizedCrossrefAuthor) -> tuple[bool, list[str]]:
    """Validate a single NormalizedCrossrefAuthor."""
    errors: list[str] = []
    if not author.full_name or not author.full_name.strip():
        errors.append("author full_name is required and must not be empty")

    if author.orcid and not _ORCID_PATTERN.match(author.orcid):
        errors.append(f"orcid {author.orcid!r} does not match standard pattern")

    return len(errors) == 0, errors


def validate_crossref_source(source: NormalizedCrossrefSource) -> tuple[bool, list[str]]:
    """Validate a NormalizedCrossrefSource."""
    errors: list[str] = []
    if not source.title or not source.title.strip():
        errors.append("source title is required and must not be empty")

    return len(errors) == 0, errors


def validate_crossref_work(work: NormalizedCrossrefWork) -> tuple[bool, list[str]]:
    """
    Validate a NormalizedCrossrefWork.

    Returns:
        (is_valid: bool, errors: list[str])
    """
    errors: list[str] = []

    # 1. DOI required and valid
    if not is_valid_doi(work.doi):
        errors.append(f"doi {work.doi!r} is not a valid canonical DOI")

    # 2. Title required
    if not work.title or not work.title.strip():
        errors.append("title is required and must not be empty")

    # 3. Publication year in sane range
    if work.publication_year is not None:
        if not (_YEAR_MIN <= work.publication_year <= _YEAR_MAX):
            errors.append(
                f"publication_year {work.publication_year} outside valid range [{_YEAR_MIN}, {_YEAR_MAX}]"
            )

    # 4. Citation and reference counts non-negative
    if work.cited_by_count < 0:
        errors.append(f"cited_by_count must be >= 0, got {work.cited_by_count}")
    if work.reference_count < 0:
        errors.append(f"reference_count must be >= 0, got {work.reference_count}")

    # 5. URLs
    if work.url and not _is_valid_url(work.url):
        errors.append(f"url {work.url!r} is not a valid HTTP/HTTPS URL")
    if work.license_url and not _is_valid_url(work.license_url):
        errors.append(f"license_url {work.license_url!r} is not a valid HTTP/HTTPS URL")

    # 6. Authors validation
    for i, author in enumerate(work.authors):
        is_author_valid, author_errs = validate_crossref_author(author)
        if not is_author_valid:
            errors.extend([f"author[{i}]: {err}" for err in author_errs])

    # 7. Source validation
    if work.source:
        is_src_valid, src_errs = validate_crossref_source(work.source)
        if not is_src_valid:
            errors.extend([f"source: {err}" for err in src_errs])

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning("Crossref validation failed [%s]: %s", work.doi, "; ".join(errors))

    return is_valid, errors
