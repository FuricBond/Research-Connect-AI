"""
Written UTC and GMT offsets ("UTC+5:30", "GMT-04:00") are read or refused, never dropped.

They used to be recognised as plain UTC: the deadline came out wrong by the whole offset and was
still reported with confidence 1.0. A malformed or impossible offset has no safe reading, so it is
INVALID with no instant at all.
"""
from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from app.ranking.deadline import DeadlineEvidenceExtractor
from app.ranking.deadline.models import NormalizationStatus, TimezoneIndicator
from app.ranking.deadline.normalizers import DeadlineNormalizer, parse_numeric_offset


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _normalize(raw: str):
    return DeadlineNormalizer.normalize_raw_string(raw)


@pytest.mark.parametrize(
    ("raw", "expected", "offset"),
    [
        # Whole hours, both signs
        ("2026-08-22 12:00 UTC+1", _utc(2026, 8, 22, 11), "+01:00"),
        ("2026-08-22 12:00 GMT+1", _utc(2026, 8, 22, 11), "+01:00"),
        ("2026-08-22 12:00 UTC-5", _utc(2026, 8, 22, 17), "-05:00"),
        ("2026-08-22 12:00 GMT-5", _utc(2026, 8, 22, 17), "-05:00"),
        # Half hours, both signs: the sign applies to the minutes too
        ("2026-08-22 12:00 UTC+5:30", _utc(2026, 8, 22, 6, 30), "+05:30"),
        ("2026-08-22 12:00 UTC-3:30", _utc(2026, 8, 22, 15, 30), "-03:30"),
        # Zero-padded and explicit minutes
        ("2026-08-22 12:00 UTC+05:30", _utc(2026, 8, 22, 6, 30), "+05:30"),
        ("2026-08-22 12:00 GMT-04:00", _utc(2026, 8, 22, 16), "-04:00"),
        ("2026-08-22 12:00 UTC+0545", _utc(2026, 8, 22, 6, 15), "+05:45"),
        # Whitespace and case
        ("2026-08-22 12:00 UTC +5:30", _utc(2026, 8, 22, 6, 30), "+05:30"),
        ("2026-08-22 12:00 UTC + 5:30", _utc(2026, 8, 22, 6, 30), "+05:30"),
        ("2026-08-22 12:00 utc+5:30", _utc(2026, 8, 22, 6, 30), "+05:30"),
        ("2026-08-22 12:00 Gmt - 4", _utc(2026, 8, 22, 16), "-04:00"),
        # Other date formats, and the ends of the real range
        ("August 22, 2026 11:59 PM UTC+8", _utc(2026, 8, 22, 15, 59), "+08:00"),
        ("22 Aug 2026 23:59 GMT+14", _utc(2026, 8, 22, 9, 59), "+14:00"),
    ],
)
def test_a_written_offset_converts_correctly(raw: str, expected: datetime, offset: str) -> None:
    result = _normalize(raw)
    assert result.normalized_utc == expected
    assert result.timezone_offset == offset
    assert result.normalization_status == NormalizationStatus.EXPLICIT_TIMEZONE
    assert result.normalization_confidence == 1.0


def test_equivalent_representations_are_the_same_instant() -> None:
    instants = {
        _normalize(raw).normalized_utc
        for raw in (
            "2026-08-22 12:00 UTC+5:30",
            "2026-08-22 12:00 UTC+05:30",
            "2026-08-22 12:00 GMT+5:30",
            "2026-08-22 12:00 utc + 0530",
            "2026-08-22T12:00:00+05:30",
            "2026-08-22 12:00 +05:30",
            "2026-08-22 06:30 UTC",
            "2026-08-22 12:00 IST",
            "2026-08-22 12:00 Asia/Kolkata",
        )
    }
    assert instants == {_utc(2026, 8, 22, 6, 30)}


def test_a_date_with_a_written_offset_ends_at_that_offsets_midnight() -> None:
    result = _normalize("2026-08-22 UTC+5:30")
    assert result.normalized_utc == _utc(2026, 8, 22, 18, 29, 59)
    assert result.is_end_of_day_inferred is True
    assert result.timezone_offset == "+05:30"
    assert result.normalization_confidence == 0.95


def test_the_offset_is_not_taken_for_the_time_of_day() -> None:
    result = _normalize("2026-08-22 UTC + 5:30")
    assert result.local_time == time(23, 59, 59)
    assert result.is_end_of_day_inferred is True
    assert result.normalized_utc == _utc(2026, 8, 22, 18, 29, 59)


@pytest.mark.parametrize(
    "raw",
    [
        # Out of the real range, UTC-12:00 to UTC+14:00
        "2026-08-22 12:00 UTC+15",
        "2026-08-22 12:00 UTC+14:30",
        "2026-08-22 12:00 UTC-13",
        "2026-08-22 12:00 UTC-12:30",
        "2026-08-22 12:00 GMT+25",
        # Minutes that do not exist
        "2026-08-22 12:00 UTC+5:99",
        "2026-08-22 12:00 UTC+5:60",
        # Cannot be read as an offset
        "2026-08-22 12:00 UTC+5.5",
        "2026-08-22 12:00 UTC+5:3",
        "2026-08-22 12:00 UTC+123",
        "2026-08-22 12:00 UTC+12345",
        "2026-08-22 12:00 UTC+",
        "2026-08-22 12:00 GMT-",
        "2026-08-22 12:00 UTC+abc",
    ],
)
def test_an_impossible_or_malformed_offset_has_no_instant(raw: str) -> None:
    result = _normalize(raw)
    assert result.normalization_status == NormalizationStatus.INVALID
    assert result.normalized_utc is None
    assert result.normalization_confidence == 0.0


@pytest.mark.parametrize("raw", ["2026-08-22 12:00 +15:00", "2026-08-22 12:00 -13:00"])
def test_a_bare_offset_out_of_range_is_refused_too(raw: str) -> None:
    result = _normalize(raw)
    assert result.normalization_status == NormalizationStatus.INVALID
    assert result.normalized_utc is None


def test_plain_utc_and_gmt_are_still_utc() -> None:
    for raw in ("2026-08-22 12:00 UTC", "2026-08-22 12:00 GMT", "2026-08-22T12:00:00Z"):
        result = _normalize(raw)
        assert result.normalized_utc == _utc(2026, 8, 22, 12), raw
        assert result.normalization_status == NormalizationStatus.EXPLICIT_TIMEZONE, raw


def test_a_date_range_after_utc_is_not_an_offset() -> None:
    result = _normalize("2026-08-22 UTC - 2026-08-25")
    assert result.normalization_status != NormalizationStatus.INVALID
    assert result.timezone_offset == "+00:00"
    assert _normalize("Aug 22, 2026 UTC - Aug 25").timezone_offset == "+00:00"


def test_no_offset_at_all_stays_inferred_not_invented() -> None:
    result = _normalize("2026-08-22 12:00")
    assert result.normalization_status == NormalizationStatus.INFERRED_TIMEZONE
    assert result.normalization_confidence == 0.85
    assert result.is_end_of_day_inferred is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-08-22T12:00:00+05:30", _utc(2026, 8, 22, 6, 30)),
        ("2026-08-22T12:00:00-07:00", _utc(2026, 8, 22, 19)),
        ("2026-08-22 12:00 +05:30", _utc(2026, 8, 22, 6, 30)),
    ],
)
def test_iso_offsets_still_work(raw: str, expected: datetime) -> None:
    assert _normalize(raw).normalized_utc == expected


@pytest.mark.parametrize("raw", ["2026-08-22 23:59 AoE", "2026-08-22 23:59 UTC-12", "2026-08-22 23:59 UTC-12:00", "2026-08-22 23:59 GMT-12"])
def test_anywhere_on_earth_still_works(raw: str) -> None:
    result = _normalize(raw)
    assert result.normalized_utc == _utc(2026, 8, 23, 11, 59)
    assert result.timezone_name == "AoE"


def test_date_only_is_still_end_of_day_aoe() -> None:
    result = _normalize("2026-08-22")
    assert result.normalized_utc == _utc(2026, 8, 23, 11, 59, 59)
    assert result.is_end_of_day_inferred is True
    assert result.normalization_status == NormalizationStatus.INFERRED_TIMEZONE


@pytest.mark.parametrize(
    ("raw", "expected", "offset"),
    [
        ("2026-07-01 12:00 America/New_York", _utc(2026, 7, 1, 16), "-04:00"),
        ("2026-01-15 12:00 America/New_York", _utc(2026, 1, 15, 17), "-05:00"),
        ("2026-07-01 12:00 Europe/Berlin", _utc(2026, 7, 1, 10), "+02:00"),
        ("2026-01-15 12:00 Europe/Berlin", _utc(2026, 1, 15, 11), "+01:00"),
        # A negative half-hour zone: the label used to round the hours down, to -04:30
        ("2026-01-15 12:00 America/St_Johns", _utc(2026, 1, 15, 15, 30), "-03:30"),
    ],
)
def test_named_zones_keep_their_daylight_saving_offsets(raw: str, expected: datetime, offset: str) -> None:
    result = _normalize(raw)
    assert result.normalized_utc == expected
    assert result.timezone_offset == offset


@pytest.mark.parametrize(
    "raw",
    ["04/05/2026 12:00 UTC+5:30", "2026-02-30 12:00 UTC+5:30", "soon"],
)
def test_ambiguous_impossible_and_missing_dates_stay_unresolved(raw: str) -> None:
    assert _normalize(raw).normalized_utc is None


def test_the_extractor_records_a_written_offset_as_an_offset_not_as_utc() -> None:
    evidence = DeadlineEvidenceExtractor.extract_milestone_from_string("2026-08-22 12:00 UTC+5:30")
    assert evidence.timezone_indicator == TimezoneIndicator.EXPLICIT_OFFSET
    assert evidence.parsed_time_str == "12:00"
    assert DeadlineEvidenceExtractor.extract_milestone_from_string("2026-08-22 12:00 UTC").timezone_indicator == TimezoneIndicator.EXPLICIT_UTC


@pytest.mark.parametrize(
    ("raw", "valid"),
    [("+14:00", True), ("-12:00", True), ("+14:01", False), ("-12:01", False), ("+5:60", False), ("+00:00", True)],
)
def test_the_offset_range_is_utc_minus_12_to_plus_14(raw: str, valid: bool) -> None:
    assert (parse_numeric_offset(raw)[0] is not None) is valid
