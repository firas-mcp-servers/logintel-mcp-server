"""Unit tests for the root cause analysis engine."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from logintel.intelligence.root_cause import (
    _build_timeline,
    _identify_causes,
    analyze_root_cause,
)
from logintel.models.common import LogEntry


def _make_entry(
    timestamp: str,
    level: str = "INFO",
    message: str = "msg",
    service: str | None = None,
) -> LogEntry:
    return LogEntry(
        timestamp=timestamp,
        level=level,
        message=message,
        service=service,
        source="test",
        fields={},
    )


class TestAnalyzeRootCause:
    """Scenarios for root cause analysis."""

    @pytest.mark.asyncio
    async def test_when_errors_found_then_returns_likely_causes(self):
        err = _make_entry(
            "2026-05-24T10:00:00Z", level="ERROR", message="DB timeout", service="api"
        )
        provider = MagicMock()
        provider.filter = AsyncMock(
            return_value=MagicMock(entries=[err], total=1)
        )
        provider.search = AsyncMock(
            return_value=MagicMock(entries=[err], total=1)
        )
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)
        registry.all_providers = MagicMock(return_value={"src1": provider})

        result = await analyze_root_cause(
            registry=registry,
            service="api",
            time_range={"from": "now-1h", "to": "now"},
            symptom="500 errors",
        )
        assert result["service"] == "api"
        assert result["symptom"] == "500 errors"
        assert result["error_count"] == 1
        assert len(result["likely_causes"]) > 0
        assert len(result["timeline"]) == 1

    @pytest.mark.asyncio
    async def test_when_provider_fails_then_skips_it(self):
        provider = MagicMock()
        provider.filter = AsyncMock(side_effect=ConnectionError("boom"))
        provider.search = AsyncMock(side_effect=ConnectionError("boom"))
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)
        registry.all_providers = MagicMock(return_value={"src1": provider})

        result = await analyze_root_cause(
            registry=registry,
            service="api",
            time_range={"from": "now-1h", "to": "now"},
            symptom="500 errors",
        )
        assert result["error_count"] == 0
        assert result["likely_causes"] == []

    @pytest.mark.asyncio
    async def test_when_sources_specified_then_uses_only_those(self):
        provider = MagicMock()
        provider.filter = AsyncMock(return_value=MagicMock(entries=[], total=0))
        provider.search = AsyncMock(return_value=MagicMock(entries=[], total=0))
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)

        result = await analyze_root_cause(
            registry=registry,
            service="api",
            time_range={"from": "now-1h", "to": "now"},
            symptom="500 errors",
            sources=["src1"],
        )
        assert result["sources_analyzed"] == ["src1"]


class TestBuildTimeline:
    """Scenarios for timeline building."""

    def test_when_entries_out_of_order_then_sorted_chronologically(self):
        entries = [
            {"entry": _make_entry("2026-05-24T10:05:00Z"), "source": "src1"},
            {"entry": _make_entry("2026-05-24T10:00:00Z"), "source": "src1"},
        ]
        timeline = _build_timeline(entries)
        assert timeline[0]["timestamp"] == "2026-05-24T10:00:00Z"
        assert timeline[1]["timestamp"] == "2026-05-24T10:05:00Z"


class TestIdentifyCauses:
    """Scenarios for cause identification heuristics."""

    def test_when_upstream_errors_then_suggests_upstream_cause(self):
        errors = [
            {
                "entry": _make_entry(
                    "2026-05-24T10:00:00Z", level="ERROR", message="boom", service="db"
                )
            },
        ]
        context = []
        causes = _identify_causes(errors, context, "api", "500 errors")
        assert any("upstream" in c["cause"] for c in causes)

    def test_when_recurring_message_then_suggests_recurring_error(self):
        errors = [
            {"entry": _make_entry("2026-05-24T10:00:00Z", level="ERROR", message="same error")},
            {"entry": _make_entry("2026-05-24T10:01:00Z", level="ERROR", message="same error")},
        ]
        context = []
        causes = _identify_causes(errors, context, "api", "500 errors")
        assert any("Recurring" in c["cause"] for c in causes)

    def test_when_timeout_keyword_then_suggests_infrastructure(self):
        errors = [
            {
                "entry": _make_entry(
                    "2026-05-24T10:00:00Z", level="ERROR", message="connection timeout"
                )
            },
        ]
        context = []
        causes = _identify_causes(errors, context, "api", "500 errors")
        assert any("Infrastructure" in c["cause"] for c in causes)

    def test_when_more_warns_than_errors_then_suggests_warning_spike(self):
        errors = [
            {"entry": _make_entry("2026-05-24T10:00:00Z", level="ERROR", message="boom")},
        ]
        context = [
            {"entry": _make_entry("2026-05-24T10:00:00Z", level="WARN", message="warn1")},
            {"entry": _make_entry("2026-05-24T10:01:00Z", level="WARN", message="warn2")},
        ]
        causes = _identify_causes(errors, context, "api", "500 errors")
        assert any("Warning spike" in c["cause"] for c in causes)

    def test_when_no_errors_then_returns_empty(self):
        causes = _identify_causes([], [], "api", "500 errors")
        assert causes == []

    def test_when_duplicate_causes_then_deduplicated(self):
        errors = [
            {"entry": _make_entry("2026-05-24T10:00:00Z", level="ERROR", message="timeout")},
            {"entry": _make_entry("2026-05-24T10:01:00Z", level="ERROR", message="timeout")},
        ]
        context = []
        causes = _identify_causes(errors, context, "api", "500 errors")
        cause_texts = [c["cause"] for c in causes]
        assert len(cause_texts) == len(set(cause_texts))
