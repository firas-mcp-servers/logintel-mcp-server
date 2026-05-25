"""Integration tests for Phase 5 intelligence tools."""

import json

import pytest

from logintel.server import create_server


class TestServerToolCorrelateLogs:
    """Scenarios for the correlate_logs tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "DB failed",
                    "service": "payment",
                    "trace_id": "abc123",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:01Z",
                    "level": "ERROR",
                    "message": "Payment timeout",
                    "service": "payment",
                    "trace_id": "abc123",
                }
            )
            + "\n"
        )
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
            f"    serviceField: service\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_trace_id_given_then_correlates_entries(self, mcp):
        result = await mcp.call_tool(
            "correlate_logs",
            {
                "sources": ["local-app"],
                "trace_id": "abc123",
                "time_range": {"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
            },
        )
        data = json.loads(result[0].text)
        assert data["total_entries"] == 2
        assert len(data["groups"]) == 1
        assert data["groups"][0]["correlation_type"] == "trace_id"

    @pytest.mark.asyncio
    async def test_when_service_given_then_correlates_by_time(self, mcp):
        result = await mcp.call_tool(
            "correlate_logs",
            {
                "sources": ["local-app"],
                "service": "payment",
                "time_range": {"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
            },
        )
        data = json.loads(result[0].text)
        assert data["total_entries"] == 2

    @pytest.mark.asyncio
    async def test_when_unknown_source_then_returns_empty(self, mcp):
        result = await mcp.call_tool(
            "correlate_logs",
            {
                "sources": ["missing"],
                "time_range": {"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
            },
        )
        data = json.loads(result[0].text)
        assert data["groups"] == []
        assert data["total_entries"] == 0


class TestServerToolAnalyzeRootCause:
    """Scenarios for the analyze_root_cause tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "DB connection timeout",
                    "service": "payment",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:01:00Z",
                    "level": "WARN",
                    "message": "Slow query",
                    "service": "payment",
                }
            )
            + "\n"
        )
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
            f"    serviceField: service\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_errors_exist_then_returns_causes(self, mcp):
        result = await mcp.call_tool(
            "analyze_root_cause",
            {
                "service": "payment",
                "time_range": {"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
                "symptom": "500 errors",
            },
        )
        data = json.loads(result[0].text)
        assert data["service"] == "payment"
        assert data["symptom"] == "500 errors"
        assert data["error_count"] >= 1
        assert len(data["likely_causes"]) > 0
        assert len(data["timeline"]) > 0


class TestServerToolCompareTimePeriods:
    """Scenarios for the compare_time_periods tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T08:00:00Z",
                    "level": "INFO",
                    "message": "baseline msg",
                    "service": "api",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "new error",
                    "service": "api",
                }
            )
            + "\n"
        )
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
            f"    serviceField: service\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_periods_differ_then_returns_diff(self, mcp):
        result = await mcp.call_tool(
            "compare_time_periods",
            {
                "source": "local-app",
                "baseline_range": {
                    "from": "2026-05-24T07:00:00Z",
                    "to": "2026-05-24T09:00:00Z",
                },
                "comparison_range": {
                    "from": "2026-05-24T09:00:00Z",
                    "to": "2026-05-24T11:00:00Z",
                },
            },
        )
        data = json.loads(result[0].text)
        assert "diff" in data
        assert "summary" in data
        assert data["source"] == "local-app"

    @pytest.mark.asyncio
    async def test_when_unknown_source_then_returns_error(self, mcp):
        result = await mcp.call_tool(
            "compare_time_periods",
            {
                "source": "missing",
                "baseline_range": {"from": "now-2h", "to": "now-1h"},
                "comparison_range": {"from": "now-1h", "to": "now"},
            },
        )
        data = json.loads(result[0].text)
        assert "error" in data


class TestServerToolDetectErrorPatterns:
    """Scenarios for the detect_error_patterns tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "boom",
                    "service": "api",
                }
            )
            + "\n"
        )
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
            f"    serviceField: service\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_source_exists_then_returns_patterns(self, mcp):
        result = await mcp.call_tool(
            "detect_error_patterns",
            {"source": "local-app"},
        )
        data = json.loads(result[0].text)
        assert "patterns" in data

    @pytest.mark.asyncio
    async def test_when_source_unknown_then_returns_error(self, mcp):
        result = await mcp.call_tool(
            "detect_error_patterns",
            {"source": "missing"},
        )
        data = json.loads(result[0].text)
        assert "error" in data


class TestServerToolFindAnomalies:
    """Scenarios for the find_anomalies tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "ok",
                    "service": "api",
                }
            )
            + "\n"
        )
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
            f"    serviceField: service\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_source_exists_then_returns_anomalies(self, mcp):
        result = await mcp.call_tool(
            "find_anomalies",
            {"source": "local-app"},
        )
        data = json.loads(result[0].text)
        assert "anomalies" in data

    @pytest.mark.asyncio
    async def test_when_source_unknown_then_returns_error(self, mcp):
        result = await mcp.call_tool(
            "find_anomalies",
            {"source": "missing"},
        )
        data = json.loads(result[0].text)
        assert "error" in data


class TestServerToolNaturalLanguageToQuery:
    """Scenarios for the natural_language_to_query tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-app:\n    type: datadog\n    apiKey: test\n    appKey: test\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_question_given_then_returns_query(self, mcp):
        result = await mcp.call_tool(
            "natural_language_to_query",
            {"source": "dd-app", "question": "Show me errors"},
        )
        data = json.loads(result[0].text)
        assert "query" in data
        assert data["provider"] == "datadog"

    @pytest.mark.asyncio
    async def test_when_source_unknown_then_returns_error(self, mcp):
        result = await mcp.call_tool(
            "natural_language_to_query",
            {"source": "missing", "question": "Show me errors"},
        )
        data = json.loads(result[0].text)
        assert "error" in data


class TestServerToolExplainQuery:
    """Scenarios for the explain_query tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-app:\n    type: datadog\n    apiKey: test\n    appKey: test\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_query_given_then_returns_explanation(self, mcp):
        result = await mcp.call_tool(
            "explain_query",
            {"source": "dd-app", "query": "status:error"},
        )
        data = json.loads(result[0].text)
        assert "explanation" in data
        assert "ERROR-level" in data["explanation"]

    @pytest.mark.asyncio
    async def test_when_source_unknown_then_returns_error(self, mcp):
        result = await mcp.call_tool(
            "explain_query",
            {"source": "missing", "query": "status:error"},
        )
        data = json.loads(result[0].text)
        assert "error" in data


class TestServerPrompts:
    """Scenarios for MCP prompts."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("sources: {}\n")
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_investigate_incident_prompt_then_returns_workflow(self, mcp):
        result = await mcp.get_prompt("investigate_incident", {})
        assert "SRE" in result.messages[0].content.text
        assert "anomalies" in result.messages[0].content.text

    @pytest.mark.asyncio
    async def test_when_oncall_summary_prompt_then_returns_shift_summary(self, mcp):
        result = await mcp.get_prompt("oncall_summary", {})
        assert "on-call" in result.messages[0].content.text
        assert "error patterns" in result.messages[0].content.text
