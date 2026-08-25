"""
DOI Canonicalization and validation utilities for Crossref integration.

Normalizes DOI strings from diverse formats into standard canonical representation:
  - https://doi.org/10.1234/ABC -> 10.1234/ABC
  - http://dx.doi.org/10.1234/ABC -> 10.1234/ABC
  - doi:10.1234/ABC -> 10.1234/ABC
  - 10.1234/ABC -> 10.1234/ABC

DOI format definition:
  - Prefix: Starts with '10.' followed by 4 to 9 digits (registrant code), then '/'
  - Suffix: Arbitrary character sequence assigned by publisher
"""
from __future__ import annotations

import re
import urllib.parse

# Regex to match DOI prefix and suffix (case-insensitive prefix match)
_DOI_PATTERN = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:)?(10\.\d{4,9}/[^\s]+)$",
    re.IGNORECASE,
)

_PREFIX_PATTERN = re.compile(r"^10\.\d{4,9}/", re.IGNORECASE)


def canonicalize_doi(raw_doi: str | None) -> str | None:
    """
    Convert a raw DOI string into canonical format (e.g., '10.1234/example').

    Steps:
    1. Strip leading and trailing whitespace.
    2. URL-decode (%2F -> /) safely.
    3. Strip common URL and URI prefixes (https://doi.org/, http://dx.doi.org/, doi:).
    4. Strip trailing punctuation marks (.,;), spaces, or trailing slashes often accidentally copied.
    5. Validate that prefix starts with '10.\\d{4,9}/'.
    6. Return standard canonical string or None if invalid.

    Args:
        raw_doi: The input DOI or URL string.

    Returns:
        Canonicalized DOI string, or None if the input is empty or invalid.
    """
    if not raw_doi:
        return None

    cleaned = raw_doi.strip()
    if not cleaned:
        return None

    # URL decode safely
    try:
        cleaned = urllib.parse.unquote(cleaned)
    except Exception:
        pass

    # Strip prefixes
    prefixes_to_strip = [
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "dx.doi.org/",
        "doi.org/",
        "doi:",
        "DOI:",
    ]
    for prefix in prefixes_to_strip:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
            break

    # Strip trailing punctuation often accidentally included in citations or URLs
    cleaned = cleaned.rstrip(".,;)>]}")

    # Check against DOI structure: must start with 10.XXXX/
    if not _PREFIX_PATTERN.match(cleaned):
        return None

    # Normalize the 10.XXXX/ prefix to lowercase, keep suffix casing intact
    prefix_match = _PREFIX_PATTERN.match(cleaned)
    if prefix_match:
        prefix_part = prefix_match.group(0).lower()
        suffix_part = cleaned[len(prefix_part):]
        if not suffix_part:
            return None
        return f"{prefix_part}{suffix_part}"

    return None


def is_valid_doi(doi: str | None) -> bool:
    """Return True if the DOI is non-empty and conforms to standard canonical format."""
    canonical = canonicalize_doi(doi)
    return canonical is not None and len(canonical) > 7
