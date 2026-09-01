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


# ── Opportunity Quality Scoring (Phase 2.4J) ──────────────────────────────────

INDEXING_TIER_SCORES: dict[str, float] = {
    # Tier 1: Highly prestigious / Gold standard indexers
    "SCOPUS": 1.00,
    "SCI": 1.00,
    "SCIE": 1.00,
    "SSCI": 1.00,
    "AHCI": 1.00,
    "WEB OF SCIENCE": 1.00,
    "WOS": 1.00,
    "IEEE": 1.00,
    "IEEE XPLORE": 1.00,
    "ACM": 1.00,
    "ACM DIGITAL LIBRARY": 1.00,
    "MEDLINE": 1.00,
    "PUBMED": 1.00,
    # Tier 2: Recognized secondary & major domain-specific indexers
    "DBLP": 0.75,
    "EI COMPENDEX": 0.75,
    "COMPENDEX": 0.75,
    "DOAJ": 0.75,
    "SPRINGER": 0.75,
    "ELSEVIER": 0.75,
    "INSPEC": 0.75,
    "EMBASE": 0.75,
    "ERIC": 0.75,
    "CORE A*": 0.90,
    "CORE A": 0.80,
    # Tier 3: Standard / General citation aggregators & directories
    "GOOGLE SCHOLAR": 0.50,
    "CROSSREF": 0.50,
    "SEMANTIC SCHOLAR": 0.50,
    "WIKICFP": 0.50,
    "CORE B": 0.65,
    "CORE C": 0.50,
    "INDEX COPERNICUS": 0.50,
}

DEFAULT_NEUTRAL_INDEXING_SCORE = 0.50
UNKNOWN_INDEXING_SCORE = 0.40


def calculate_indexing_quality(indexing: list[str] | None) -> float:
    """
    Calculate deterministic quality score from opportunity indexing list.

    Hierarchy:
      - Tier 1 (Scopus, Web of Science, IEEE, ACM, PubMed) -> 1.00
      - Tier 2 (DBLP, EI Compendex, DOAJ, Springer, etc.) -> 0.75
      - Tier 3 (Google Scholar, Crossref, WikiCFP) -> 0.50
      - Unrecognized non-empty indexing -> 0.40
      - Missing or empty indexing -> 0.50 (neutral default; no false negative)

    Parameters
    ----------
    indexing:
        List of indexing provider names.

    Returns
    -------
    float
        Normalized score in [0.0, 1.0].
    """
    if indexing is None or len(indexing) == 0:
        return DEFAULT_NEUTRAL_INDEXING_SCORE

    if not isinstance(indexing, (list, set, tuple)):
        return DEFAULT_NEUTRAL_INDEXING_SCORE

    best_score = 0.0
    has_valid_entry = False

    for item in indexing:
        if item is None or not isinstance(item, str) or not item.strip():
            continue
        has_valid_entry = True
        key = item.strip().upper()
        score = INDEXING_TIER_SCORES.get(key, UNKNOWN_INDEXING_SCORE)
        if score > best_score:
            best_score = score

    if not has_valid_entry:
        return DEFAULT_NEUTRAL_INDEXING_SCORE

    return round(min(1.0, max(0.0, best_score)), 6)


def calculate_predatory_penalty(
    is_predatory_flag: bool | None = None,
    risk_score: float | None = None,
    penalty_factor: float | None = None,
) -> float:
    """
    Calculate multiplicative quality penalty for predatory risk.

    Returns a multiplier in range [0.0, 1.0]:
      - 1.00: Clean, zero verified predatory risk.
      - penalty_factor (default 0.20): Flagged as predatory or risk_score >= 0.70.
      - 1.0 - (risk_score * 0.50): Intermediate cautionary risk.
      - Missing/None: 1.00 (neutral default; no penalty without evidence).

    Parameters
    ----------
    is_predatory_flag:
        Boolean flag indicating suspected or confirmed predatory venue.
    risk_score:
        Numerical risk score in [0.00, 1.00].
    penalty_factor:
        Penalty multiplier for flagged predatory venues (default from config: 0.20).
    """
    factor = (
        penalty_factor
        if penalty_factor is not None
        else getattr(settings, "hybrid_ranking_predatory_penalty_factor", 0.20)
    )
    factor = max(0.0, min(1.0, float(factor)))

    if is_predatory_flag is True:
        return factor

    if risk_score is not None:
        try:
            f_risk = float(risk_score)
            if not math.isnan(f_risk) and not math.isinf(f_risk):
                if f_risk >= 0.70:
                    return factor
                elif f_risk > 0.0:
                    return round(max(factor, 1.0 - (f_risk * 0.50)), 6)
        except (ValueError, TypeError):
            pass

    return 1.00


def calculate_status_reliability(status: str | None) -> float:
    """
    Calculate venue status reliability score.

    Parameters
    ----------
    status:
        Opportunity lifecycle status (e.g. 'VERIFIED', 'ACTIVE', 'UNVERIFIED', 'ARCHIVED', 'CANCELLED').
    """
    if not status or not isinstance(status, str):
        return 0.70

    upper_status = status.strip().upper()
    if upper_status in ("VERIFIED", "ACTIVE"):
        return 1.00
    elif upper_status == "UNVERIFIED":
        return 0.70
    elif upper_status == "ARCHIVED":
        return 0.30
    elif upper_status == "CANCELLED":
        return 0.00
    else:
        return 0.70


def calculate_opportunity_quality(
    opportunity: Any | None = None,
    *,
    is_predatory_flag: bool | None = None,
    risk_score: float | None = None,
    indexing: list[str] | None = None,
    status: str | None = None,
    indexing_weight: float | None = None,
    status_weight: float | None = None,
    predatory_penalty_factor: float | None = None,
) -> float:
    """
    Calculate composite opportunity quality score in range [0.0, 1.0].

    Integrates:
      1. Indexing quality (e.g. Scopus, IEEE, ACM, DBLP).
      2. Status & reliability (VERIFIED, ACTIVE vs UNVERIFIED vs CANCELLED).
      3. Multiplicative predatory risk penalty.

    Parameters
    ----------
    opportunity:
        Optional OpportunityModel ORM instance or candidate dict.
    is_predatory_flag ... status:
        Explicit metadata overrides.

    Returns
    -------
    float
        Normalized quality score in [0.0, 1.0].
    """
    # Extract from opportunity instance if provided
    eff_predatory = is_predatory_flag
    eff_risk = risk_score
    eff_indexing = indexing
    eff_status = status

    if opportunity is not None:
        if eff_predatory is None:
            eff_predatory = getattr(opportunity, "is_predatory_flag", None)
            if isinstance(opportunity, dict) and eff_predatory is None:
                eff_predatory = opportunity.get("is_predatory_flag", opportunity.get("is_predatory"))

        if eff_risk is None:
            eff_risk = getattr(opportunity, "risk_score", None)
            if isinstance(opportunity, dict) and eff_risk is None:
                eff_risk = opportunity.get("risk_score")

        if eff_indexing is None:
            eff_indexing = getattr(opportunity, "indexing", None)
            if isinstance(opportunity, dict) and eff_indexing is None:
                eff_indexing = opportunity.get("indexing")

        if eff_status is None:
            eff_status = getattr(opportunity, "status", None)
            if isinstance(opportunity, dict) and eff_status is None:
                eff_status = opportunity.get("status")

    w_indexing = (
        indexing_weight
        if indexing_weight is not None
        else getattr(settings, "opportunity_quality_indexing_weight", 0.70)
    )
    w_status = (
        status_weight
        if status_weight is not None
        else getattr(settings, "opportunity_quality_status_weight", 0.30)
    )

    score_indexing = calculate_indexing_quality(eff_indexing)
    score_status = calculate_status_reliability(eff_status)

    total_weight = w_indexing + w_status
    if total_weight <= 0.0:
        base_quality = score_indexing
    else:
        base_quality = (w_indexing * score_indexing + w_status * score_status) / total_weight

    penalty = calculate_predatory_penalty(
        is_predatory_flag=eff_predatory,
        risk_score=eff_risk,
        penalty_factor=predatory_penalty_factor,
    )

    quality = base_quality * penalty
    return round(min(1.0, max(0.0, quality)), 6)


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
    opportunity_quality: float = 0.0
    retrieval_sources: list[str] = field(default_factory=list)

