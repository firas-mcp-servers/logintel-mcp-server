"""Unit tests for the correlation engine."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from logintel.intelligence.correlator import (
    _group_by_time_proximity,
    _make_time_group,
    _parse_window,
    correlate_across_sources,
)
from logintel.models.common import LogEntry


def _make_entry(
    timestamp: str,
    level: str = "INFO",
    message: str = "msg",
    service: str | None = None,
    trace_id: str | None = None,
) -> LogEntry:
    return LogEntry(
        timestamp=timestamp,
        level=level,
        message=message,
        service=service,
        source="test",
        fields={},
        trace_id=trace_id,
    )


class TestCorrelateAcrossSources:
    """Scenarios for cross-source correlation."""

    @pytest.mark.asyncio
    async def test_when_trace_id_given_then_correlates_by_trace_id(self):
        entry = _make_entry("2026-05-24T10:00:00Z", trace_id="abc123")
        provider = MagicMock()
        provider.filter = AsyncMock(
            return_value=MagicMock(entries=[entry], total=1)
        )
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)

        result = await correlate_across_sources(
            registry=registry,
            sources=["src1", "src2"],
            time_range={"from": "now-1h", "to": "now"},
            trace_id="abc123",
        )
        assert result["total_entries"] == 2
        assert len(result["groups"]) == 1
        assert result["groups"][0]["correlation_type"] == "trace_id"
        assert result["groups"][0]["correlation_key"] == "abc123"

    @pytest.mark.asyncio
    async def test_when_no_trace_id_then_groups_by_time_proximity(self):
        e1 = _make_entry("2026-05-24T10:00:00Z", service="api")
        e2 = _make_entry("2026-05-24T10:01:00Z", service="api")
        provider = MagicMock()
        provider.search = AsyncMock(
            return_value=MagicMock(entries=[e1, e2], total=2)
        )
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)

        result = await correlate_across_sources(
            registry=registry,
            sources=["src1"],
            time_range={"from": "now-1h", "to": "now"},
        )
        assert result["total_entries"] == 2
        assert len(result["groups"]) >= 1

    @pytest.mark.asyncio
    async def test_when_provider_fails_then_skips_that_source(self):
        provider = MagicMock()
        provider.search = AsyncMock(side_effect=ConnectionError("boom"))
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)

        result = await correlate_across_sources(
            registry=registry,
            sources=["src1"],
            time_range={"from": "now-1h", "to": "now"},
        )
        assert result["total_entries"] == 0
        assert result["groups"] == []

    @pytest.mark.asyncio
    async def test_when_service_filter_given_then_filters_entries(self):
        e1 = _make_entry("2026-05-24T10:00:00Z", service="api")
        e2 = _make_entry("2026-05-24T10:01:00Z", service="other")
        provider = MagicMock()
        provider.search = AsyncMock(
            return_value=MagicMock(entries=[e1, e2], total=2)
        )
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)

        result = await correlate_across_sources(
            registry=registry,
            sources=["src1"],
            time_range={"from": "now-1h", "to": "now"},
            service="api",
        )
        total_in_groups = sum(
            len(g["entries"]) for g in result["groups"]
        )
        assert total_in_groups == 1


class TestGroupByTimeProximity:
    """Scenarios for time-proximity grouping."""

    def test_when_entries_within_window_then_single_group(self):
        entries = [
            _make_entry("2026-05-24T10:00:00Z"),
            _make_entry("2026-05-24T10:01:00Z"),
            _make_entry("2026-05-24T10:02:00Z"),
        ]
        groups = _group_by_time_proximity(entries, timedelta(minutes=5), None)
        assert len(groups) == 1
        assert len(groups[0].entries) == 3

    def test_when_entries_spaced_apart_then_multiple_groups(self):
        entries = [
            _make_entry("2026-05-24T10:00:00Z"),
            _make_entry("2026-05-24T10:10:00Z"),
            _make_entry("2026-05-24T10:20:00Z"),
        ]
        groups = _group_by_time_proximity(entries, timedelta(minutes=5), None)
        assert len(groups) == 3

    def test_when_empty_then_returns_empty(self):
        groups = _group_by_time_proximity([], timedelta(minutes=5), None)
        assert groups == []

    def test_when_service_filter_then_only_matching_entries(self):
        entries = [
            _make_entry("2026-05-24T10:00:00Z", service="api"),
            _make_entry("2026-05-24T10:01:00Z", service="other"),
        ]
        groups = _group_by_time_proximity(entries, timedelta(minutes=5), "api")
        assert len(groups) == 1
        assert len(groups[0].entries) == 1

    def test_when_service_filter_no_match_then_empty(self):
        entries = [
            _make_entry("2026-05-24T10:00:00Z", service="other"),
        ]
        groups = _group_by_time_proximity(entries, timedelta(minutes=5), "api")
        assert groups == []


class TestMakeTimeGroup:
    """Scenarios for time group creation."""

    def test_when_entries_have_errors_then_higher_score(self):
        entries = [
            _make_entry("2026-05-24T10:00:00Z", level="ERROR"),
            _make_entry("2026-05-24T10:01:00Z", level="ERROR"),
        ]
        group = _make_time_group(entries)
        assert group.correlation_type == "timestamp_proximity"
        assert group.score > 0.5

    def test_when_entries_are_info_then_lower_score(self):
        entries = [
            _make_entry("2026-05-24T10:00:00Z", level="INFO"),
        ]
        group = _make_time_group(entries)
        assert group.score < 0.5


class TestParseWindow:
    """Scenarios for correlation window parsing."""

    def test_when_minutes_then_returns_timedelta(self):
        assert _parse_window("5m") == timedelta(minutes=5)

    def test_when_hours_then_returns_timedelta(self):
        assert _parse_window("1h") == timedelta(hours=1)

    def test_when_seconds_then_returns_timedelta(self):
        assert _parse_window("30s") == timedelta(seconds=30)

    def test_when_no_unit_then_defaults_to_minutes(self):
        assert _parse_window("10") == timedelta(minutes=10)
