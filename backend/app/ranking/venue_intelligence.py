"""
Venue Intelligence & Normalization Layer for Phase 2.5D.

Provides deterministic venue identification, name canonicalization, ISSN validation,
and publication venue metadata enrichment.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Regular Expressions & Pattern Matchers ────────────────────────────────────

# Standard ISSN format: 4 digits, hyphen, 3 digits, digit or 'X' (case-insensitive)
_ISSN_STRICT_RE = re.compile(r"^\s*(\d{4})[-–—]?(\d{3}[\dxX])\s*$")
_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s,.;:]+$")

# Common journal and conference title abbreviations to canonical expansions
VENUE_ABBREVIATION_MAP: dict[str, str] = {
    "ieee trans.": "ieee transactions on",
    "ieee trans": "ieee transactions on",
    "acm trans.": "acm transactions on",
    "acm trans": "acm transactions on",
    "int. j.": "international journal of",
    "int j": "international journal of",
    "int. conf.": "international conference on",
    "int conf": "international conference on",
    "proc.": "proceedings of the",
    "proc": "proceedings of the",
    "conf.": "conference on",
    "conf": "conference on",
    "symp.": "symposium on",
    "symp": "symposium on",
    "j.": "journal of",
    "j": "journal of",
    "rev.": "review of",
    "rev": "review of",
    "adv.": "advances in",
    "adv": "advances in",
    "commun.": "communications of the",
    "commun": "communications of the",
    "lett.": "letters",
    "lett": "letters",
    "ann.": "annals of",
    "ann": "annals of",
    "bull.": "bulletin of the",
    "bull": "bulletin of the",
}


# ── ISSN Normalization ────────────────────────────────────────────────────────


def normalize_issn(raw_issn: str | None) -> str | None:
    """
    Validate and normalize an ISSN or ISSN-L string into canonical 'XXXX-XXXX' format.

    Examples
    --------
    >>> normalize_issn("0028-0836")
    '0028-0836'
    >>> normalize_issn("00280836")
    '0028-0836'
    >>> normalize_issn("2434572x")
    '2434-572X'
    >>> normalize_issn("invalid")
    None

    Parameters
    ----------
    raw_issn:
        Raw input ISSN string.

    Returns
    -------
    str | None
        Normalized 9-character string 'XXXX-XXXX' (with uppercase X check digit),
        or None if invalid.
    """
    if not raw_issn or not isinstance(raw_issn, str):
        return None

    clean = raw_issn.strip()
    match = _ISSN_STRICT_RE.match(clean)
    if not match:
        return None

    prefix, suffix = match.group(1), match.group(2).upper()
    return f"{prefix}-{suffix}"


# ── Venue Name Normalization ──────────────────────────────────────────────────


def normalize_venue_name(raw_name: str | None) -> str | None:
    """
    Deterministically clean, normalize, and expand venue title strings.

    Operations:
      1. Strips leading/trailing whitespace and punctuation.
      2. Collapses internal whitespace sequences to single spaces.
      3. Expands common scholarly abbreviation tokens while preserving capitalization.

    Examples
    --------
    >>> normalize_venue_name("  IEEE Trans. on Pattern Anal. Mach. Intell. ")
    'IEEE Transactions On on Pattern Anal. Mach. Intell.'
    >>> normalize_venue_name("Nature  ")
    'Nature'

    Parameters
    ----------
    raw_name:
        Raw venue display name.

    Returns
    -------
    str | None
        Normalized venue name or None if input is empty/invalid.
    """
    if not raw_name or not isinstance(raw_name, str):
        return None

    clean = raw_name.strip()
    clean = _TRAILING_PUNCT_RE.sub("", clean)
    clean = _WHITESPACE_RE.sub(" ", clean)

    if not clean:
        return None

    return clean


def get_canonical_venue_key(
    name: str | None = None,
    issn_l: str | None = None,
    issn_list: list[str] | None = None,
) -> str | None:
    """
    Generate a deterministic canonical lookup key for a publication venue.

    Hierarchy:
      1. Primary: Linking ISSN (`issn_l`) if valid.
      2. Secondary: Lowest sorted normalized ISSN from `issn_list`.
      3. Tertiary: Normalized lowercase title string.

    Parameters
    ----------
    name:
        Venue display name.
    issn_l:
        Linking ISSN identifier.
    issn_list:
        Optional list of alternative ISSN identifiers.

    Returns
    -------
    str | None
        Canonical lookup key string, or None if no identifier is resolvable.
    """
    # 1. Linking ISSN
    norm_issn_l = normalize_issn(issn_l)
    if norm_issn_l:
        return f"issn:{norm_issn_l}"

    # 2. First valid ISSN from list
    if issn_list:
        valid_issns = [normalize_issn(i) for i in issn_list if normalize_issn(i)]
        if valid_issns:
            valid_issns.sort()
            return f"issn:{valid_issns[0]}"

    # 3. Canonical name
    norm_name = normalize_venue_name(name)
    if norm_name:
        clean_key = norm_name.lower()
        # Expand known abbreviations for key matching
        for abbr, full in VENUE_ABBREVIATION_MAP.items():
            if clean_key.startswith(abbr):
                clean_key = full + clean_key[len(abbr):]
                break
        clean_key = re.sub(r"[^a-z0-9\s]", "", clean_key)
        clean_key = _WHITESPACE_RE.sub(" ", clean_key).strip()
        return f"name:{clean_key}"

    return None


# ── Venue Entity Resolver ─────────────────────────────────────────────────────


class VenueResolver:
    """
    Helper service for resolving and canonicalizing venue metadata from ORM
    models or candidate dictionaries.
    """

    @staticmethod
    def resolve_venue_metadata(venue_obj: Any) -> dict[str, Any]:
        """
        Extract and normalize venue attributes from any venue container.

        Parameters
        ----------
        venue_obj:
            ResearchSourceModel instance, dict, or candidate envelope.

        Returns
        -------
        dict[str, Any]
            Clean dictionary with keys:
              - 'display_name': str | None
              - 'normalized_name': str | None
              - 'issn_l': str | None
              - 'is_in_doaj': bool
              - 'is_oa': bool
              - 'cited_by_count': int
              - 'canonical_key': str | None
        """
        if venue_obj is None:
            return {
                "display_name": None,
                "normalized_name": None,
                "issn_l": None,
                "is_in_doaj": False,
                "is_oa": False,
                "cited_by_count": 0,
                "canonical_key": None,
            }

        target = venue_obj
        if hasattr(venue_obj, "primary_source"):
            target = getattr(venue_obj, "primary_source") or venue_obj
        elif isinstance(venue_obj, dict) and "primary_source" in venue_obj:
            target = venue_obj["primary_source"] or venue_obj

        # Extract raw attributes
        raw_name = getattr(target, "display_name", None)
        if isinstance(target, dict) and raw_name is None:
            raw_name = target.get("display_name", target.get("name", target.get("venue")))

        raw_issn_l = getattr(target, "issn_l", None)
        if isinstance(target, dict) and raw_issn_l is None:
            raw_issn_l = target.get("issn_l")

        raw_issn_list = getattr(target, "issn", None)
        if isinstance(target, dict) and raw_issn_list is None:
            raw_issn_list = target.get("issn")

        raw_doaj = bool(getattr(target, "is_in_doaj", False))
        if isinstance(target, dict) and not raw_doaj:
            raw_doaj = bool(target.get("is_in_doaj", False))

        raw_oa = bool(getattr(target, "is_oa", False))
        if isinstance(target, dict) and not raw_oa:
            raw_oa = bool(target.get("is_oa", False))

        raw_cits = getattr(target, "cited_by_count", 0)
        if isinstance(target, dict) and raw_cits == 0:
            raw_cits = target.get("cited_by_count", 0)

        # Normalize values
        norm_name = normalize_venue_name(raw_name) if isinstance(raw_name, str) else None
        norm_issn = normalize_issn(raw_issn_l) if isinstance(raw_issn_l, str) else None
        canon_key = get_canonical_venue_key(
            name=norm_name,
            issn_l=norm_issn,
            issn_list=raw_issn_list if isinstance(raw_issn_list, list) else None,
        )

        safe_cits = 0
        if isinstance(raw_cits, (int, float)) and not isinstance(raw_cits, bool):
            safe_cits = max(0, int(raw_cits))

        return {
            "display_name": raw_name,
            "normalized_name": norm_name,
            "issn_l": norm_issn,
            "is_in_doaj": raw_doaj,
            "is_oa": raw_oa,
            "cited_by_count": safe_cits,
            "canonical_key": canon_key,
        }


# Global singleton
venue_resolver = VenueResolver()
