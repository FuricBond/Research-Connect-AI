"""
Unit tests for ranking signals and feature calculation in app.ranking.signals.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import pytest

from app.ranking.signals import (
    RankingSignals,
    calculate_freshness,
    calculate_urgency,
    normalize_lexical_score,
    validate_signal,
)


class TestValidateSignal:
    """Tests for signal validation, clamping, and rejection of invalid numeric values."""

    def test_valid_floats_and_integers(self):
        assert validate_signal(0.0) == 0.0
        assert validate_signal(0.5) == 0.5
        assert validate_signal(1.0) == 1.0
        assert validate_signal(1) == 1.0
        assert validate_signal(0) == 0.0

    def test_clamping_bounds(self):
        assert validate_signal(-0.5) == 0.0
        assert validate_signal(-100.0) == 0.0
        assert validate_signal(1.5) == 1.0
        assert validate_signal(999.0) == 1.0

    def test_none_returns_default(self):
        assert validate_signal(None, default=0.0) == 0.0
        assert validate_signal(None, default=0.75) == 0.75

    def test_boolean_rejected(self):
        with pytest.raises(ValueError, match="must be numeric"):
            validate_signal(True)
        with pytest.raises(ValueError, match="must be numeric"):
            validate_signal(False)

    def test_non_numeric_types_rejected(self):
        with pytest.raises(ValueError, match="must be numeric"):
            validate_signal("0.5")
        with pytest.raises(ValueError, match="must be numeric"):
            validate_signal([0.5])
        with pytest.raises(ValueError, match="must be numeric"):
            validate_signal({"score": 0.5})

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="cannot be NaN"):
            validate_signal(float("nan"))

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="cannot be infinite"):
            validate_signal(float("inf"))
        with pytest.raises(ValueError, match="cannot be infinite"):
            validate_signal(float("-inf"))


class TestNormalizeLexicalScore:
    """Tests for full-text lexical search score normalization."""

    def test_zero_or_negative_scores(self):
        assert normalize_lexical_score(0.0) == 0.0
        assert normalize_lexical_score(-1.0) == 0.0
        assert normalize_lexical_score(None) == 0.0

    def test_positive_scores(self):
        # 1.0 / (1.0 + 1.0) = 0.5
        assert normalize_lexical_score(1.0) == 0.5
        # 3.0 / (3.0 + 1.0) = 0.75
        assert normalize_lexical_score(3.0) == 0.75
        # Monotonicity
        assert normalize_lexical_score(5.0) > normalize_lexical_score(2.0)
        assert normalize_lexical_score(100.0) < 1.0


class TestCalculateFreshness:
    """Tests for publication recency decay score calculation."""

    def test_current_year_maximum_freshness(self):
        ref_year = 2026
        assert calculate_freshness(publication_year=2026, reference_year=ref_year) == 1.0
        # Future year paper is also capped at 1.0
        assert calculate_freshness(publication_year=2027, reference_year=ref_year) == 1.0

    def test_exponential_half_life_decay(self):
        ref_year = 2026
        half_life = 5.0
        # 5 years old -> exactly 0.5
        score_5y = calculate_freshness(
            publication_year=2021, reference_year=ref_year, half_life_years=half_life
        )
        assert math.isclose(score_5y, 0.5, abs_tol=1e-5)

        # 10 years old -> exactly 0.25
        score_10y = calculate_freshness(
            publication_year=2016, reference_year=ref_year, half_life_years=half_life
        )
        assert math.isclose(score_10y, 0.25, abs_tol=1e-5)

    def test_date_object_and_string_parsing(self):
        ref_year = 2026
        # Date object
        score_date = calculate_freshness(
            publication_date=date(2026, 3, 15), reference_year=ref_year
        )
        assert score_date == 1.0

        # Datetime object
        score_dt = calculate_freshness(
            publication_date=datetime(2021, 6, 1, tzinfo=timezone.utc),
            reference_year=ref_year,
            half_life_years=5.0,
        )
        assert math.isclose(score_dt, 0.5, abs_tol=1e-5)

        # ISO String
        score_str = calculate_freshness(
            publication_date="2026-01-01", reference_year=ref_year
        )
        assert score_str == 1.0

    def test_missing_or_invalid_dates(self):
        assert calculate_freshness(publication_year=None, publication_date=None) == 0.0
        assert calculate_freshness(publication_year=-10) == 0.0
        assert calculate_freshness(publication_date="invalid-date") == 0.0

    def test_invalid_half_life_raises_error(self):
        with pytest.raises(ValueError, match="must be positive"):
            calculate_freshness(publication_year=2024, half_life_years=0.0)
        with pytest.raises(ValueError, match="must be positive"):
            calculate_freshness(publication_year=2024, half_life_years=-2.0)


class TestCalculateUrgency:
    """Tests for academic opportunity submission deadline urgency calculation."""

    def test_approaching_deadlines_within_window(self):
        now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        window = 90.0

        # Deadline today -> urgency 1.0
        score_now = calculate_urgency(submission_deadline=now, reference_time=now, window_days=window)
        assert score_now == 1.0

        # 45 days out in 90-day window -> urgency 0.5
        deadline_45d = now + timedelta(days=45)
        score_45d = calculate_urgency(submission_deadline=deadline_45d, reference_time=now, window_days=window)
        assert math.isclose(score_45d, 0.5, abs_tol=1e-4)

        # 9 days out in 90-day window -> urgency 0.9
        deadline_9d = now + timedelta(days=9)
        score_9d = calculate_urgency(submission_deadline=deadline_9d, reference_time=now, window_days=window)
        assert math.isclose(score_9d, 0.9, abs_tol=1e-4)

    def test_past_and_distant_deadlines(self):
        now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        window = 90.0

        # Expired deadline (past) -> urgency 0.0
        past_deadline = now - timedelta(days=5)
        assert calculate_urgency(submission_deadline=past_deadline, reference_time=now, window_days=window) == 0.0

        # Distant deadline (> window) -> urgency 0.0
        distant_deadline = now + timedelta(days=120)
        assert calculate_urgency(submission_deadline=distant_deadline, reference_time=now, window_days=window) == 0.0

    def test_iso_string_and_naive_datetimes(self):
        now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        # ISO string
        score_iso = calculate_urgency(
            submission_deadline="2026-09-10T12:00:00Z", reference_time=now, window_days=90.0
        )
        assert score_iso == 0.9

        # Naive datetime
        naive_now = datetime(2026, 9, 1, 12, 0)
        naive_deadline = datetime(2026, 9, 10, 12, 0)
        score_naive = calculate_urgency(
            submission_deadline=naive_deadline, reference_time=naive_now, window_days=90.0
        )
        assert score_naive == 0.9

    def test_missing_or_malformed_deadline(self):
        assert calculate_urgency(submission_deadline=None) == 0.0
        assert calculate_urgency(submission_deadline="not-a-date") == 0.0

    def test_invalid_window_days_raises_error(self):
        with pytest.raises(ValueError, match="must be positive"):
            calculate_urgency(submission_deadline=datetime.now(timezone.utc), window_days=0.0)


class TestRankingSignalsContainer:
    """Tests for the immutable RankingSignals dataclass."""

    def test_default_values(self):
        signals = RankingSignals()
        assert signals.semantic_similarity == 0.0
        assert signals.lexical_similarity == 0.0
        assert signals.topic_similarity == 0.0
        assert signals.type_compatibility == 0.0
        assert signals.freshness == 0.0
        assert signals.urgency == 0.0
        assert signals.retrieval_sources == []

    def test_custom_values_and_immutability(self):
        signals = RankingSignals(
            semantic_similarity=0.85,
            lexical_similarity=0.40,
            topic_similarity=0.90,
            type_compatibility=1.0,
            freshness=0.75,
            urgency=0.50,
            retrieval_sources=["semantic", "lexical"],
        )
        assert signals.semantic_similarity == 0.85
        assert signals.retrieval_sources == ["semantic", "lexical"]

        with pytest.raises(AttributeError):
            signals.semantic_similarity = 0.99  # frozen dataclass
