"""Coverage-gap tests for Phase 5 intelligence layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from logintel.cache import QueryCache
from logintel.intelligence.comparator import _generate_summary
from logintel.intelligence.correlator import _dict_to_tr, correlate_across_sources
from logintel.intelligence.nl2query import explain, translate
from logintel.models.common import LogEntry
from logintel.server import create_server


def _make_entry(ts: str, level: str = "INFO", msg: str = "m") -> LogEntry:
    return LogEntry(timestamp=ts, level=level, message=msg, source="s")


# ------------------------------------------------------------------
# Cache hit branches in server tools
# ------------------------------------------------------------------

# TestServerCacheHits is covered by TestServerCacheBranches below


# ------------------------------------------------------------------
# Comparator branches
# ------------------------------------------------------------------


class TestGenerateSummaryGaps:
    """Hit uncovered branches in _generate_summary."""

    def test_when_total_change_is_inf_then_zero_to_present(self):
        diff = {
            "total_count": {"baseline": 0, "comparison": 5, "change": float("inf")},
            "error_count": {"baseline": 0, "comparison": 0, "change": 0.0},
            "new_messages": [],
        }
        assert "went from zero to present" in _generate_summary(diff)

    def test_when_errors_decreased_then_says_decreased(self):
        diff = {
            "total_count": {"baseline": 10, "comparison": 10, "change": 0.0},
            "error_count": {"baseline": 10, "comparison": 2, "change": -80.0},
            "new_messages": [],
        }
        assert "Errors decreased" in _generate_summary(diff)


# ------------------------------------------------------------------
# Correlator branches
# ------------------------------------------------------------------


class TestCorrelatorGaps:
    """Hit uncovered branches in correlator."""

    @pytest.mark.asyncio
    async def test_when_trace_filter_raises_then_skips_source(self):
        provider = MagicMock()
        provider.filter = AsyncMock(side_effect=ConnectionError("boom"))
        registry = MagicMock()
        registry.get = MagicMock(return_value=provider)

        result = await correlate_across_sources(
            registry=registry,
            sources=["src1"],
            time_range=None,
            trace_id="abc",
        )
        assert result["total_entries"] == 0

    def test_when_dict_to_tr_gets_none_then_returns_none(self):
        assert _dict_to_tr(None) is None


# ------------------------------------------------------------------
# NL2Query branches
# ------------------------------------------------------------------


class TestNl2QueryGaps:
    """Hit uncovered branches in NL2Query."""

    def test_loki_warn_keyword(self):
        result = translate("Show me warnings", "loki")
        assert 'level="warn"' in result["query"]

    def test_loki_info_keyword(self):
        result = translate("Show me info logs", "loki")
        assert 'level="info"' in result["query"]

    def test_loki_keyword_line_filter_when_no_labels(self):
        result = translate("Show me timeouts", "loki")
        assert '|= "timeouts"' in result["query"]

    def test_cloudwatch_warn_keyword(self):
        result = translate("Show me warnings", "cloudwatch")
        assert "like /warn/i" in result["query"]

    def test_local_info_keyword(self):
        result = translate("Show me info logs", "local")
        assert result["query"] == "INFO"

    def test_explain_datadog_warn_status(self):
        text = explain("status:warn", "datadog")
        assert "WARN-level" in text

    def test_explain_datadog_host(self):
        text = explain("host:server01", "datadog")
        assert "server01" in text

    def test_explain_datadog_custom_field(self):
        text = explain("@env:prod", "datadog")
        assert "custom field filters" in text

    def test_explain_loki_warn_level(self):
        text = explain('{level="warn"}', "loki")
        assert "WARN-level" in text

    def test_explain_loki_service(self):
        text = explain('{service="api"}', "loki")
        assert "api" in text


# ------------------------------------------------------------------
# Root cause branches
# ------------------------------------------------------------------


class TestRootCauseGaps:
    """Hit uncovered branches in root_cause."""

    def test_dict_to_tr_none(self):
        from logintel.intelligence.root_cause import _dict_to_tr as _tr

        assert _tr(None) is None


# ------------------------------------------------------------------
# Server exception branches
# ------------------------------------------------------------------


class TestServerExceptionBranches:
    """Hit exception handlers in new server tools."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text('{"timestamp":"2026-05-24T10:00:00Z","level":"INFO","message":"ok"}\n')
        config = tmp_path / "config.yaml"
        config.write_text(
            f"sources:\n"
            f"  local-app:\n"
            f"    type: local\n"
            f"    paths:\n"
            f'      - "{tmp_path / "*.jsonl"}"\n'
            f"    parseJson: true\n"
            f"    timestampField: timestamp\n"
            f"    levelField: level\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_detect_error_patterns_exception_returns_error(self, mcp):
        with patch(
            "logintel.server.ProviderRegistry.get",
            side_effect=RuntimeError("boom"),
        ):
            result = await mcp.call_tool("detect_error_patterns", {"source": "local-app"})
        data = __import__("json").loads(result[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_find_anomalies_exception_returns_error(self, mcp):
        with patch(
            "logintel.server.ProviderRegistry.get",
            side_effect=RuntimeError("boom"),
        ):
            result = await mcp.call_tool("find_anomalies", {"source": "local-app"})
        data = __import__("json").loads(result[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_nl2query_exception_returns_error(self, mcp):
        with patch(
            "logintel.server.ProviderRegistry.get",
            side_effect=RuntimeError("boom"),
        ):
            result = await mcp.call_tool(
                "natural_language_to_query",
                {"source": "local-app", "question": "errors"},
            )
        data = __import__("json").loads(result[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_explain_query_exception_returns_error(self, mcp):
        with patch(
            "logintel.server.ProviderRegistry.get",
            side_effect=RuntimeError("boom"),
        ):
            result = await mcp.call_tool(
                "explain_query",
                {"source": "local-app", "query": "ERROR"},
            )
        data = __import__("json").loads(result[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_compare_time_periods_exception_returns_error(self, mcp):
        with patch(
            "logintel.server.compare_periods",
            side_effect=RuntimeError("boom"),
        ):
            result = await mcp.call_tool(
                "compare_time_periods",
                {
                    "source": "local-app",
                    "baseline_range": {
                        "from": "2026-05-24T08:00:00Z",
                        "to": "2026-05-24T09:00:00Z",
                    },
                    "comparison_range": {
                        "from": "2026-05-24T09:00:00Z",
                        "to": "2026-05-24T10:00:00Z",
                    },
                },
            )
        data = __import__("json").loads(result[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_correlate_logs_exception_returns_error(self, mcp):
        with patch(
            "logintel.server.correlate_across_sources",
            side_effect=RuntimeError("boom"),
        ):
            result = await mcp.call_tool(
                "correlate_logs",
                {"sources": ["local-app"]},
            )
        data = __import__("json").loads(result[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_analyze_root_cause_exception_returns_error(self, mcp):
        with patch(
            "logintel.server._analyze_root_cause",
            side_effect=RuntimeError("boom"),
        ):
            result = await mcp.call_tool(
                "analyze_root_cause",
                {
                    "service": "api",
                    "time_range": {"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
                    "symptom": "500 errors",
                },
            )
        data = __import__("json").loads(result[0].text)
        assert "error" in data


# ------------------------------------------------------------------
# Server cache hit branches (direct coverage via monkeypatch)
# ------------------------------------------------------------------


class TestServerCacheBranches:
    """Hit cache hit branches by pre-seeding the cache."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("sources: {}\n")
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_correlate_logs_cache_hit(self, mcp):
        # Access the closure variable 'cache' via the function's closure
        # This is a bit hacky but necessary for coverage
        cached = {"groups": [], "total_entries": 0, "cached": True}
        with patch.object(QueryCache, "get", return_value=cached):
            result = await mcp.call_tool(
                "correlate_logs",
                {"sources": ["x"]},
            )
        data = __import__("json").loads(result[0].text)
        assert data["cached"] is True

    @pytest.mark.asyncio
    async def test_analyze_root_cause_cache_hit(self, mcp):
        cached = {"likely_causes": [], "cached": True}
        with patch.object(QueryCache, "get", return_value=cached):
            result = await mcp.call_tool(
                "analyze_root_cause",
                {
                    "service": "api",
                    "time_range": {"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
                    "symptom": "500 errors",
                },
            )
        data = __import__("json").loads(result[0].text)
        assert data["cached"] is True

    @pytest.mark.asyncio
    async def test_compare_time_periods_cache_hit(self, mcp):
        cached = {"diff": {}, "summary": "cached", "cached": True}
        with patch.object(QueryCache, "get", return_value=cached):
            result = await mcp.call_tool(
                "compare_time_periods",
                {
                    "source": "x",
                    "baseline_range": {
                        "from": "2026-05-24T08:00:00Z",
                        "to": "2026-05-24T09:00:00Z",
                    },
                    "comparison_range": {
                        "from": "2026-05-24T09:00:00Z",
                        "to": "2026-05-24T10:00:00Z",
                    },
                },
            )
        data = __import__("json").loads(result[0].text)
        assert data["cached"] is True
