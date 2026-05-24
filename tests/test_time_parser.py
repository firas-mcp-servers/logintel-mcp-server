"""Tests for time parsing utilities."""

from datetime import UTC, datetime, timedelta

import pytest

from logintel.utils.time_parser import parse_relative_time


class TestParseRelativeTime:
    """Tests for parse_relative_time."""

    def test_now(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now", reference=ref)
        assert result == ref

    def test_now_minus_1h(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now-1h", reference=ref)
        assert result == ref - timedelta(hours=1)

    def test_now_minus_30m(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now-30m", reference=ref)
        assert result == ref - timedelta(minutes=30)

    def test_now_minus_1d(self):
        ref = datetime(2026, 5, 24, 12, 0, 0, tzinfo=UTC)
        result = parse_relative_time("now-1d", reference=ref)
        assert result == ref - timedelta(days=1)

    def test_iso_format(self):
        result = parse_relative_time("2026-05-24T10:00:00Z")
        assert result == datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC)

    def test_iso_format_with_offset(self):
        result = parse_relative_time("2026-05-24T10:00:00+01:00")
        assert result.hour == 10

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_relative_time("invalid")
