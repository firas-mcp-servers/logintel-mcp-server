"""Unit tests for time parsing utility scenarios."""

from datetime import UTC, datetime, timedelta

import pytest

from logintel.utils.time_parser import TimeRange, parse_relative_time


class TestParseRelativeTime:
    """Scenarios for parsing relative and absolute time strings."""

    def test_when_given_now_then_returns_reference_time(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now", reference=ref)
        assert result == ref

    def test_when_given_now_minus_1h_then_returns_one_hour_before(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now-1h", reference=ref)
        assert result == ref - timedelta(hours=1)

    def test_when_given_now_minus_30m_then_returns_thirty_minutes_before(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now-30m", reference=ref)
        assert result == ref - timedelta(minutes=30)

    def test_when_given_now_minus_1d_then_returns_one_day_before(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now-1d", reference=ref)
        assert result == ref - timedelta(days=1)

    def test_when_given_now_minus_90s_then_returns_ninety_seconds_before(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now-90s", reference=ref)
        assert result == ref - timedelta(seconds=90)

    def test_when_given_iso_timestamp_with_z_then_parses_correctly(self):
        result = parse_relative_time("2026-05-24T10:00:00Z")
        assert result == datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC)

    def test_when_given_iso_timestamp_with_offset_then_parses_correctly(self):
        result = parse_relative_time("2026-05-24T10:00:00+01:00")
        assert result.hour == 10
        assert result.utcoffset() == timedelta(hours=1)

    def test_when_given_iso_timestamp_without_z_then_parses_correctly(self):
        result = parse_relative_time("2026-05-24T10:00:00")
        assert result == datetime(2026, 5, 24, 10, 0, 0)

    def test_when_given_invalid_string_then_raises_value_error(self):
        with pytest.raises(ValueError, match="Unable to parse time"):
            parse_relative_time("not-a-time")

    def test_when_given_now_plus_1h_then_returns_one_hour_after(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now+1h", reference=ref)
        assert result == ref + timedelta(hours=1)

    def test_when_given_uppercase_now_then_parses_correctly(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("NOW", reference=ref)
        assert result == ref

    def test_when_given_mixed_case_iso_then_parses_correctly(self):
        result = parse_relative_time("2026-05-24t10:00:00z")
        assert result == datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC)

    def test_when_no_reference_provided_then_uses_current_time(self):
        before = datetime.now(UTC)
        result = parse_relative_time("now")
        after = datetime.now(UTC)
        assert before <= result <= after


class TestTimeRangeModel:
    """Scenarios for the internal TimeRange class."""

    def test_when_created_with_from_and_to_then_both_fields_are_set(self):
        tr = TimeRange(
            from_time=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC),
            to_time=datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC),
        )
        assert tr.from_time == datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC)
        assert tr.to_time == datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC)

    def test_when_created_with_from_only_then_to_defaults_to_now(self):
        before = datetime.now(UTC)
        tr = TimeRange(from_time=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC))
        after = datetime.now(UTC)
        assert tr.from_time == datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC)
        assert before <= tr.to_time <= after

    def test_when_timestamp_is_within_range_then_contains_returns_true(self):
        tr = TimeRange(
            from_time=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC),
            to_time=datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC),
        )
        ts = datetime(2026, 5, 24, 10, 30, 0, tzinfo=UTC)
        assert tr.contains(ts) is True

    def test_when_timestamp_is_before_range_then_contains_returns_false(self):
        tr = TimeRange(
            from_time=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC),
            to_time=datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC),
        )
        ts = datetime(2026, 5, 24, 9, 0, 0, tzinfo=UTC)
        assert tr.contains(ts) is False

    def test_when_timestamp_is_after_range_then_contains_returns_false(self):
        tr = TimeRange(
            from_time=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC),
            to_time=datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC),
        )
        ts = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        assert tr.contains(ts) is False


class TestParseDelta:
    """Scenarios for parsing delta strings internally."""

    def test_when_given_composite_delta_then_sum_is_correct(self):
        from logintel.utils.time_parser import _parse_delta

        result = _parse_delta("1h30m")
        assert result == timedelta(hours=1, minutes=30)

    def test_when_given_days_and_hours_then_sum_is_correct(self):
        from logintel.utils.time_parser import _parse_delta

        result = _parse_delta("2d12h")
        assert result == timedelta(days=2, hours=12)

    def test_when_given_empty_string_then_returns_zero(self):
        from logintel.utils.time_parser import _parse_delta

        result = _parse_delta("")
        assert result == timedelta()

    def test_when_given_invalid_unit_then_raises_value_error(self):
        from logintel.utils.time_parser import _parse_delta

        with pytest.raises(ValueError):
            _parse_delta("1x")

    def test_when_given_number_without_unit_then_raises_value_error(self):
        from logintel.utils.time_parser import _parse_delta

        with pytest.raises(ValueError):
            _parse_delta("42")

    def test_when_given_multiple_invalid_units_then_raises_value_error(self):
        from logintel.utils.time_parser import _parse_delta

        with pytest.raises(ValueError):
            _parse_delta("1h2x")
