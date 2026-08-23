"""
Duplicate detection for scraped opportunities.

Strategy (three-tier, not naive title equality):

1. PRIMARY — source + raw_source_id composite (mirrors DB unique constraint).
   Exact match. This is the strongest signal: same record from same source.

2. SECONDARY — normalized website_url fingerprint.
   If two records from different sources point to the same external URL,
   they are likely the same event.  Uses SHA-256 of lowercased, stripped URL.

3. TERTIARY — normalized title + submission_deadline date.
   Same title (case-insensitive, whitespace-normalized) on the same deadline
   day is likely a duplicate posted under a different source category.
   This is a weaker signal — used for informational logging only (not blocking).

The DuplicateDetector is session-scoped (one instance per pipeline run).
It maintains in-memory sets for fast O(1) checks.
DB-level constraint violations (tier 1) are also caught by the persistence
layer as a last-resort safety net.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from scrapers.models import NormalizedOpportunity

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def _fingerprint_url(url: str | None) -> str | None:
    """Return a SHA-256 hex fingerprint of a lowercased, stripped URL."""
    if not url:
        return None
    normalized = url.strip().lower()
    # Strip trailing slash for consistent matching
    normalized = normalized.rstrip("/")
    return hashlib.sha256(normalized.encode()).hexdigest()


def _fingerprint_title_deadline(title: str, deadline_date: str | None) -> str | None:
    """
    Fingerprint of (normalized_title, deadline_date_string).

    Returns None if the deadline is absent (too many false positives without it).
    """
    if not deadline_date:
        return None
    norm_title = _WHITESPACE_RE.sub(" ", title).strip().lower()
    key = f"{norm_title}::{deadline_date}"
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass
class DuplicateResult:
    is_duplicate: bool
    tier: int | None = None          # 1, 2, or 3 (which tier caught it)
    reason: str | None = None


class DuplicateDetector:
    """
    Session-scoped duplicate detector.

    Maintains in-memory fingerprint sets built during a pipeline run.
    Must be reset between independent pipeline runs if the same instance
    is reused.

    Usage:
        detector = DuplicateDetector()
        for opp in normalized_opps:
            result = detector.check(opp)
            if not result.is_duplicate:
                detector.register(opp)
                persist(opp)
    """

    def __init__(self) -> None:
        # Tier 1: source_name + raw_source_id tuples
        self._source_ids: set[tuple[str, str]] = set()
        # Tier 2: URL fingerprints (SHA-256)
        self._url_fingerprints: set[str] = set()
        # Tier 3: title+deadline fingerprints (informational only)
        self._title_deadline_fingerprints: set[str] = set()

    def check(self, opp: NormalizedOpportunity) -> DuplicateResult:
        """
        Check whether an opportunity has already been seen this run.

        Returns a DuplicateResult — check .is_duplicate before persisting.
        """
        # --- Tier 1: source + raw_source_id ---
        source_key = (opp.source_name, opp.raw_source_id)
        if source_key in self._source_ids:
            logger.debug(
                "Tier-1 duplicate detected: source=%r id=%r",
                opp.source_name,
                opp.raw_source_id,
            )
            return DuplicateResult(
                is_duplicate=True,
                tier=1,
                reason=f"source={opp.source_name!r} raw_source_id={opp.raw_source_id!r}",
            )

        # --- Tier 2: normalized URL ---
        url_fp = _fingerprint_url(opp.website_url)
        if url_fp and url_fp in self._url_fingerprints:
            logger.debug(
                "Tier-2 duplicate detected by URL: %r for %r",
                opp.website_url,
                opp.title,
            )
            return DuplicateResult(
                is_duplicate=True,
                tier=2,
                reason=f"website_url={opp.website_url!r}",
            )

        # --- Tier 3: title + deadline (informational) ---
        deadline_str = (
            opp.submission_deadline.date().isoformat()
            if opp.submission_deadline
            else None
        )
        title_fp = _fingerprint_title_deadline(opp.title, deadline_str)
        if title_fp and title_fp in self._title_deadline_fingerprints:
            logger.info(
                "Tier-3 (soft) duplicate: same title+deadline as existing record. "
                "title=%r deadline=%s — will still process.",
                opp.title,
                deadline_str,
            )
            # Tier 3 is informational — NOT blocking
            return DuplicateResult(is_duplicate=False, tier=3, reason="title+deadline match (soft)")

        return DuplicateResult(is_duplicate=False)

    def register(self, opp: NormalizedOpportunity) -> None:
        """
        Register an opportunity in the detector's seen-sets.

        Call this AFTER confirming the record will be persisted.
        """
        self._source_ids.add((opp.source_name, opp.raw_source_id))

        url_fp = _fingerprint_url(opp.website_url)
        if url_fp:
            self._url_fingerprints.add(url_fp)

        deadline_str = (
            opp.submission_deadline.date().isoformat()
            if opp.submission_deadline
            else None
        )
        title_fp = _fingerprint_title_deadline(opp.title, deadline_str)
        if title_fp:
            self._title_deadline_fingerprints.add(title_fp)

    def reset(self) -> None:
        """Clear all seen-sets (use between independent pipeline runs)."""
        self._source_ids.clear()
        self._url_fingerprints.clear()
        self._title_deadline_fingerprints.clear()

    @property
    def seen_count(self) -> int:
        """Number of unique source+id pairs registered so far."""
        return len(self._source_ids)
