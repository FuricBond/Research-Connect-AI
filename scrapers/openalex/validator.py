"""
OpenAlex validator — validates normalised research knowledge records.

Validation philosophy (matching the existing scraper codebase):
  - Invalid records are logged and skipped, never crash the pipeline.
  - Returns ``(is_valid: bool, errors: list[str])``.
  - One malformed record does not kill the entire ingestion run.

Validation rules per entity type:

NormalizedWork
  1. openalex_id — required, must match W\\d+ pattern
  2. title — required, non-empty
  3. publication_year — if present, must be 1000–2100
  4. cited_by_count — must be >= 0
  5. landing_page_url — if present, must be valid HTTP/HTTPS URL
  6. doi — if present, must not be empty

NormalizedResearcher
  1. openalex_id — required, must match A\\d+ pattern
  2. display_name — required, non-empty
  3. works_count / cited_by_count — must be >= 0

NormalizedResearchSource
  1. openalex_id — required, must match S\\d+ pattern
  2. display_name — required, non-empty
  3. works_count / cited_by_count — must be >= 0
  4. homepage_url — if present, must be valid HTTP/HTTPS URL

NormalizedInstitution
  1. openalex_id — required, must match I\\d+ pattern
  2. display_name — required, non-empty
  3. works_count / cited_by_count — must be >= 0
  4. homepage_url — if present, must be valid HTTP/HTTPS URL
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from scrapers.openalex.models import (
    NormalizedInstitution,
    NormalizedResearchSource,
    NormalizedResearcher,
    NormalizedWork,
)

logger = logging.getLogger(__name__)

# ── ID patterns ───────────────────────────────────────────────────────────────

_WORK_ID_RE = re.compile(r"^W\d+$", re.IGNORECASE)
_AUTHOR_ID_RE = re.compile(r"^A\d+$", re.IGNORECASE)
_SOURCE_ID_RE = re.compile(r"^S\d+$", re.IGNORECASE)
_INSTITUTION_ID_RE = re.compile(r"^I\d+$", re.IGNORECASE)

_YEAR_MIN = 1000
_YEAR_MAX = 2100


# ── Shared helpers ────────────────────────────────────────────────────────────


def _is_valid_url(url: str | None) -> bool:
    """Return True if ``url`` has a valid HTTP/HTTPS scheme and non-empty netloc."""
    if not url:
        return True  # optional field absent is OK
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:  # noqa: BLE001
        return False


def _check_non_negative(errors: list[str], value: int, name: str) -> None:
    if value < 0:
        errors.append(f"{name} must be >= 0, got {value}")


# ── Work validator ────────────────────────────────────────────────────────────


def validate_work(work: NormalizedWork) -> tuple[bool, list[str]]:
    """Validate a NormalizedWork.  Returns (is_valid, errors)."""
    errors: list[str] = []

    if not work.openalex_id or not _WORK_ID_RE.match(work.openalex_id):
        errors.append(
            f"openalex_id {work.openalex_id!r} does not match expected W\\d+ pattern"
        )

    if not work.title or not work.title.strip():
        errors.append("title is required and must not be empty")

    if work.publication_year is not None:
        if not (_YEAR_MIN <= work.publication_year <= _YEAR_MAX):
            errors.append(
                f"publication_year {work.publication_year} is outside "
                f"valid range [{_YEAR_MIN}, {_YEAR_MAX}]"
            )

    _check_non_negative(errors, work.cited_by_count, "cited_by_count")

    if work.landing_page_url and not _is_valid_url(work.landing_page_url):
        errors.append(
            f"landing_page_url {work.landing_page_url!r} is not a valid HTTP/HTTPS URL"
        )

    if work.doi is not None and not work.doi.strip():
        errors.append("doi must not be empty when present")

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(
            "Work validation failed [%s]: %s",
            work.openalex_id,
            "; ".join(errors),
        )
    return is_valid, errors


# ── Researcher validator ──────────────────────────────────────────────────────


def validate_researcher(researcher: NormalizedResearcher) -> tuple[bool, list[str]]:
    """Validate a NormalizedResearcher.  Returns (is_valid, errors)."""
    errors: list[str] = []

    if not researcher.openalex_id or not _AUTHOR_ID_RE.match(researcher.openalex_id):
        errors.append(
            f"openalex_id {researcher.openalex_id!r} does not match expected A\\d+ pattern"
        )

    if not researcher.display_name or not researcher.display_name.strip():
        errors.append("display_name is required and must not be empty")

    _check_non_negative(errors, researcher.works_count, "works_count")
    _check_non_negative(errors, researcher.cited_by_count, "cited_by_count")

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(
            "Researcher validation failed [%s]: %s",
            researcher.openalex_id,
            "; ".join(errors),
        )
    return is_valid, errors


# ── ResearchSource validator ──────────────────────────────────────────────────


def validate_research_source(source: NormalizedResearchSource) -> tuple[bool, list[str]]:
    """Validate a NormalizedResearchSource.  Returns (is_valid, errors)."""
    errors: list[str] = []

    if not source.openalex_id or not _SOURCE_ID_RE.match(source.openalex_id):
        errors.append(
            f"openalex_id {source.openalex_id!r} does not match expected S\\d+ pattern"
        )

    if not source.display_name or not source.display_name.strip():
        errors.append("display_name is required and must not be empty")

    _check_non_negative(errors, source.works_count, "works_count")
    _check_non_negative(errors, source.cited_by_count, "cited_by_count")

    if source.homepage_url and not _is_valid_url(source.homepage_url):
        errors.append(
            f"homepage_url {source.homepage_url!r} is not a valid HTTP/HTTPS URL"
        )

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(
            "ResearchSource validation failed [%s]: %s",
            source.openalex_id,
            "; ".join(errors),
        )
    return is_valid, errors


# ── Institution validator ─────────────────────────────────────────────────────


def validate_institution(institution: NormalizedInstitution) -> tuple[bool, list[str]]:
    """Validate a NormalizedInstitution.  Returns (is_valid, errors)."""
    errors: list[str] = []

    if not institution.openalex_id or not _INSTITUTION_ID_RE.match(institution.openalex_id):
        errors.append(
            f"openalex_id {institution.openalex_id!r} does not match expected I\\d+ pattern"
        )

    if not institution.display_name or not institution.display_name.strip():
        errors.append("display_name is required and must not be empty")

    _check_non_negative(errors, institution.works_count, "works_count")
    _check_non_negative(errors, institution.cited_by_count, "cited_by_count")

    if institution.homepage_url and not _is_valid_url(institution.homepage_url):
        errors.append(
            f"homepage_url {institution.homepage_url!r} is not a valid HTTP/HTTPS URL"
        )

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(
            "Institution validation failed [%s]: %s",
            institution.openalex_id,
            "; ".join(errors),
        )
    return is_valid, errors
