"""Unit tests for the time-period comparison engine."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from logintel.intelligence.comparator import (
    _compute_stats,
    _find_new_items,
    _generate_summary,
    _pct_change,
    compare_periods,
)
from logintel.models.common import LogEntry
from logintel.models.results import SearchResult


def _make_entry(level: str = "INFO", message: str = "msg", service: str = "api") -> LogEntry:
    return LogEntry(
        timestamp="2026-05-24T10:00:00Z",
        level=level,
        message=message,
        service=service,
        source="test",
        fields={},
    )


class TestComparePeriods:
    """Scenarios for time-period comparison."""

    @pytest.mark.asyncio
    async def test_when_baseline_has_more_logs_then_shows_decrease(self):
        provider = MagicMock()
        provider.search = AsyncMock(
            side_effect=[
                SearchResult(entries=[_make_entry()] * 10, total=10),
                SearchResult(entries=[_make_entry()] * 4, total=4),
            ]
        )

        result = await compare_periods(
            provider=provider,
            source="src1",
            baseline_range={"from": "now-2h", "to": "now-1h"},
            comparison_range={"from": "now-1h", "to": "now"},
        )
        assert result["diff"]["total_count"]["baseline"] == 10
        assert result["diff"]["total_count"]["comparison"] == 4
        assert result["diff"]["total_count"]["change"] == -60.0
        assert "decreased" in result["summary"]

    @pytest.mark.asyncio
    async def test_when_comparison_has_new_messages_then_lists_them(self):
        provider = MagicMock()
        provider.search = AsyncMock(
            side_effect=[
                SearchResult(entries=[_make_entry(message="old")], total=1),
                SearchResult(
                    entries=[_make_entry(message="old"), _make_entry(message="new")],
                    total=2,
                ),
            ]
        )

        result = await compare_periods(
            provider=provider,
            source="src1",
            baseline_range={"from": "now-2h", "to": "now-1h"},
            comparison_range={"from": "now-1h", "to": "now"},
        )
        assert "new" in result["diff"]["new_messages"]

    @pytest.mark.asyncio
    async def test_when_provider_fails_then_returns_empty_stats(self):
        provider = MagicMock()
        provider.search = AsyncMock(side_effect=ConnectionError("boom"))

        result = await compare_periods(
            provider=provider,
            source="src1",
            baseline_range={"from": "now-2h", "to": "now-1h"},
            comparison_range={"from": "now-1h", "to": "now"},
        )
        assert result["diff"]["total_count"]["baseline"] == 0


class TestComputeStats:
    """Scenarios for stats computation."""

    def test_when_mixed_levels_then_counts_errors(self):
        entries = [
            _make_entry(level="ERROR"),
            _make_entry(level="ERROR"),
            _make_entry(level="INFO"),
        ]
        stats = _compute_stats(SearchResult(entries=entries, total=3))
        assert stats["total"] == 3
        assert stats["errors"] == 2
        assert stats["error_rate"] == 2 / 3

    def test_when_empty_then_zero_stats(self):
        stats = _compute_stats(SearchResult(entries=[], total=0))
        assert stats["total"] == 0
        assert stats["errors"] == 0
        assert stats["error_rate"] == 0.0

    def test_when_top_messages_then_sorted_by_count(self):
        entries = [
            _make_entry(message="a"),
            _make_entry(message="a"),
            _make_entry(message="b"),
        ]
        stats = _compute_stats(SearchResult(entries=entries, total=3))
        assert stats["top_messages"][0]["message"] == "a"
        assert stats["top_messages"][0]["count"] == 2


class TestPctChange:
    """Scenarios for percentage change calculation."""

    def test_when_baseline_zero_and_comparison_positive_then_inf(self):
        assert _pct_change(0, 5) == float("inf")

    def test_when_baseline_zero_and_comparison_zero_then_zero(self):
        assert _pct_change(0, 0) == 0.0

    def test_when_doubled_then_100_percent(self):
        assert _pct_change(10, 20) == 100.0

    def test_when_halved_then_minus_50_percent(self):
        assert _pct_change(20, 10) == -50.0


class TestFindNewItems:
    """Scenarios for finding new items."""

    def test_when_items_in_compare_not_in_base_then_returns_them(self):
        assert _find_new_items({"a", "b"}, {"b", "c"}) == ["c"]

    def test_when_no_new_items_then_empty(self):
        assert _find_new_items({"a", "b"}, {"a", "b"}) == []


class TestGenerateSummary:
    """Scenarios for summary generation."""

    def test_when_volume_increased_then_says_increased(self):
        diff = {
            "total_count": {"baseline": 10, "comparison": 30, "change": 200.0},
            "error_count": {"baseline": 0, "comparison": 0, "change": 0.0},
            "new_messages": [],
        }
        summary = _generate_summary(diff)
        assert "increased" in summary

    def test_when_volume_decreased_then_says_decreased(self):
        diff = {
            "total_count": {"baseline": 30, "comparison": 10, "change": -66.67},
            "error_count": {"baseline": 0, "comparison": 0, "change": 0.0},
            "new_messages": [],
        }
        summary = _generate_summary(diff)
        assert "decreased" in summary

    def test_when_errors_spiked_then_says_errors_increased(self):
        diff = {
            "total_count": {"baseline": 10, "comparison": 10, "change": 0.0},
            "error_count": {"baseline": 1, "comparison": 10, "change": 900.0},
            "new_messages": [],
        }
        summary = _generate_summary(diff)
        assert "Errors increased" in summary

    def test_when_new_messages_then_lists_them(self):
        diff = {
            "total_count": {"baseline": 10, "comparison": 10, "change": 0.0},
            "error_count": {"baseline": 0, "comparison": 0, "change": 0.0},
            "new_messages": ["new error"],
        }
        summary = _generate_summary(diff)
        assert "new error" in summary
