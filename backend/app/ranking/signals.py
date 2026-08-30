"""
Ranking Signals and Feature Extraction for Phase 2.4E.

Provides normalization, mathematical feature computation, and validation for:
  - Semantic Similarity (cosine similarity in [0, 1])
  - Lexical Similarity (normalized full-text search score in [0, 1])
  - Topic Overlap & DAG Proximity ([0, 1])
  - Publication / Opportunity Type Compatibility ([0, 1])
  - Publication Recency Freshness (exponential decay score in [0, 1])
  - Submission Deadline Urgency (linear/windowed proximity score in [0, 1])
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import math
import re
from typing import Any

from app.core.config import settings

# ── Signal Validation ─────────────────────────────────────────────────────────


def validate_signal(
    val: Any,
    signal_name: str = "signal",
    default: float = 0.0,
) -> float:
    """
    Validate that a signal value is a finite number, reject NaN/Inf, and clamp to [0.0, 1.0].

    Parameters
    ----------
    val:
        The raw signal value.
    signal_name:
        Descriptive name for error messages.
    default:
        Value to return if val is None.

    Returns
    -------
    float
        Normalized float in range [0.0, 1.0].

    Raises
    ------
    ValueError:
        If val is non-numeric (and not None) or is NaN/Infinite.
    """
    if val is None:
        return float(default)

    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(
            f"Signal '{signal_name}' must be numeric, got {type(val).__name__}."
        )

    f_val = float(val)

    if math.isnan(f_val):
        raise ValueError(f"Signal '{signal_name}' cannot be NaN.")

    if math.isinf(f_val):
        raise ValueError(f"Signal '{signal_name}' cannot be infinite.")

    # Clamp to [0.0, 1.0]
    return round(min(1.0, max(0.0, f_val)), 6)


# ── Lexical Score Normalization ───────────────────────────────────────────────


def normalize_lexical_score(raw_score: float | None) -> float:
    """
    Normalize raw PostgreSQL ts_rank_cd cover density score into [0.0, 1.0).

    Uses monotonic saturating transform: raw_score / (raw_score + 1.0).
    """
    if raw_score is None:
        return 0.0
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise ValueError(f"raw_score must be numeric, got {type(raw_score).__name__}.")
    f_val = float(raw_score)
    if math.isnan(f_val):
        raise ValueError("raw_score cannot be NaN.")
    if math.isinf(f_val):
        raise ValueError("raw_score cannot be infinite.")
    if f_val <= 0.0:
        return 0.0
    return round(f_val / (f_val + 1.0), 6)


# ── Freshness Decay ───────────────────────────────────────────────────────────


def calculate_freshness(
    publication_year: int | None = None,
    publication_date: str | date | datetime | None = None,
    reference_year: int | None = None,
    half_life_years: float | None = None,
) -> float:
    """
    Calculate recency freshness score based on publication age with exponential half-life decay.

    Formula:
        freshness = exp( - (ln(2) / half_life_years) * max(0, reference_year - pub_year) )

    Parameters
    ----------
    publication_year:
        Exact integer publication year (e.g. 2024).
    publication_date:
        Optional date string (ISO format), date, or datetime object.
    reference_year:
        Reference anchor year (defaults to current UTC year).
    half_life_years:
        Number of years at which freshness drops to 0.5 (defaults to config: 5.0).

    Returns
    -------
    float
        Freshness score in range [0.0, 1.0].
    """
    half_life = (
        half_life_years
        if half_life_years is not None
        else getattr(settings, "hybrid_ranking_freshness_half_life_years", 5.0)
    )
    if half_life <= 0.0:
        raise ValueError(f"half_life_years must be positive, got {half_life}.")

    extracted_year: int | None = None

    if publication_year is not None and isinstance(publication_year, (int, float)):
        extracted_year = int(publication_year)
    elif publication_date is not None:
        if isinstance(publication_date, (datetime, date)):
            extracted_year = publication_date.year
        elif isinstance(publication_date, str):
            match = re.match(r"^(\d{4})", publication_date.strip())
            if match:
                extracted_year = int(match.group(1))

    if extracted_year is None or extracted_year <= 0:
        return 0.0

    if reference_year is None:
        reference_year = datetime.now(timezone.utc).year

    # Papers from current or future years have maximum freshness
    age_years = max(0, reference_year - extracted_year)
    decay_constant = math.log(2.0) / half_life
    score = math.exp(-decay_constant * age_years)

    return round(min(1.0, max(0.0, score)), 6)


# ── Deadline Urgency ──────────────────────────────────────────────────────────


def calculate_urgency(
    submission_deadline: datetime | str | None = None,
    reference_time: datetime | None = None,
    window_days: float | None = None,
) -> float:
    """
    Calculate deadline urgency score for academic opportunities.

    Urgency increases linearly from 0.0 (at or beyond window_days) to 1.0 (due now/today).
    Expired deadlines (days_remaining < 0) return 0.0.

    Parameters
    ----------
    submission_deadline:
        Submission deadline datetime or ISO format string.
    reference_time:
        Current reference timestamp (defaults to now in UTC).
    window_days:
        Maximum window in days where urgency applies (defaults to config: 90.0).

    Returns
    -------
    float
        Urgency score in range [0.0, 1.0].
    """
    max_window = (
        window_days
        if window_days is not None
        else getattr(settings, "hybrid_ranking_urgency_window_days", 90.0)
    )
    if max_window <= 0.0:
        raise ValueError(f"window_days must be positive, got {max_window}.")

    if submission_deadline is None:
        return 0.0

    dt_deadline: datetime
    if isinstance(submission_deadline, str):
        try:
            dt_deadline = datetime.fromisoformat(submission_deadline)
        except ValueError:
            return 0.0
    elif isinstance(submission_deadline, datetime):
        dt_deadline = submission_deadline
    else:
        return 0.0

    # Ensure timezone awareness in UTC
    if dt_deadline.tzinfo is None:
        dt_deadline = dt_deadline.replace(tzinfo=timezone.utc)

    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    diff_seconds = (dt_deadline - reference_time).total_seconds()
    days_remaining = diff_seconds / 86400.0

    # Expired or beyond urgency window
    if days_remaining < 0.0 or days_remaining >= max_window:
        return 0.0

    # Linear scaling: 0 days -> 1.0, max_window days -> 0.0
    urgency = 1.0 - (days_remaining / max_window)
    return round(min(1.0, max(0.0, urgency)), 6)


# ── Signals Container ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RankingSignals:
    """
    Normalized multi-signal feature container for candidate ranking.

    All score attributes are guaranteed to be in range [0.0, 1.0].
    """

    semantic_similarity: float = 0.0
    lexical_similarity: float = 0.0
    topic_similarity: float = 0.0
    type_compatibility: float = 0.0
    freshness: float = 0.0
    urgency: float = 0.0
    retrieval_sources: list[str] = field(default_factory=list)
