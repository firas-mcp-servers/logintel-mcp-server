"""Integration tests for MCP server tool dispatch scenarios."""

import json

import pytest

from logintel.server import create_server


class TestServerToolListLogSources:
    """Scenarios for the list_log_sources tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n"
            "  local-app:\n"
            "    type: local\n"
            "    paths:\n"
            '      - "/var/log/app/*.log"\n'
            "  cloudwatch-prod:\n"
            "    type: cloudwatch\n"
            "    region: us-east-1\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_server_has_sources_then_list_returns_all_sources(self, mcp):
        result = await mcp.call_tool("list_log_sources", {})
        assert len(result) == 1
        data = result[0].text
        sources = json.loads(data)["sources"]
        assert len(sources) == 2
        ids = {s["id"] for s in sources}
        assert ids == {"local-app", "cloudwatch-prod"}


class TestServerToolGetSourceHealth:
    """Scenarios for the get_source_health tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("test line\n")
        config = tmp_path / "config.yaml"
        config.write_text(
            f'sources:\n  local-app:\n    type: local\n    paths:\n      - "{tmp_path / "*.log"}"\n'
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_source_is_healthy_then_returns_healthy_status(self, mcp):
        result = await mcp.call_tool("get_source_health", {"source": "local-app"})
        data = json.loads(result[0].text)
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_when_source_does_not_exist_then_returns_unknown_status(self, mcp):
        result = await mcp.call_tool("get_source_health", {"source": "missing"})
        data = json.loads(result[0].text)
        assert data["status"] == "unknown"
        assert "Unknown source" in data["message"]


class TestServerToolGetSourceSchema:
    """Scenarios for the get_source_schema tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("test line\n")
        config = tmp_path / "config.yaml"
        config.write_text(
            f"sources:\n"
            f"  local-app:\n"
            f"    type: local\n"
            f"    paths:\n"
            f'      - "{tmp_path / "*.log"}"\n'
            f"    parseJson: true\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_source_exists_then_returns_schema_with_fields(self, mcp):
        result = await mcp.call_tool("get_source_schema", {"source": "local-app"})
        data = json.loads(result[0].text)
        assert "fields" in data
        assert len(data["fields"]) > 0
        assert "json" in data["known_formats"]

    @pytest.mark.asyncio
    async def test_when_source_does_not_exist_then_returns_error(self, mcp):
        result = await mcp.call_tool("get_source_schema", {"source": "missing"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Unknown source" in data["error"]


class TestServerToolSearchLogs:
    """Scenarios for the search_logs tool."""

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
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:05:00Z",
                    "level": "INFO",
                    "message": "OK",
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
    async def test_when_searching_by_query_then_returns_matching_entries(self, mcp):
        result = await mcp.call_tool("search_logs", {"source": "local-app", "query": "payment"})
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["service"] == "payment"

    @pytest.mark.asyncio
    async def test_when_searching_with_time_range_then_filters_by_time(self, mcp):
        result = await mcp.call_tool(
            "search_logs",
            {
                "source": "local-app",
                "query": "",
                "time_range": {
                    "from": "2026-05-24T10:04:00Z",
                    "to": "2026-05-24T10:06:00Z",
                },
            },
        )
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["message"] == "OK"

    @pytest.mark.asyncio
    async def test_when_source_does_not_exist_then_returns_error(self, mcp):
        result = await mcp.call_tool("search_logs", {"source": "missing", "query": "test"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["entries"] == []


class TestServerToolFilterLogs:
    """Scenarios for the filter_logs tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "x",
                    "service": "payment",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:05:00Z",
                    "level": "INFO",
                    "message": "y",
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
    async def test_when_filtering_by_level_then_returns_only_matching_level(self, mcp):
        result = await mcp.call_tool("filter_logs", {"source": "local-app", "level": "ERROR"})
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_when_filtering_by_service_then_returns_only_matching_service(self, mcp):
        result = await mcp.call_tool("filter_logs", {"source": "local-app", "service": "api"})
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["service"] == "api"

    @pytest.mark.asyncio
    async def test_when_source_does_not_exist_then_returns_error(self, mcp):
        result = await mcp.call_tool("filter_logs", {"source": "missing", "level": "ERROR"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["entries"] == []


class TestServerToolTailLogs:
    """Scenarios for the tail_logs tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        lines = []
        for i in range(5):
            lines.append(
                json.dumps(
                    {
                        "timestamp": f"2026-05-24T10:0{i:02d}:00Z",
                        "level": "INFO",
                        "message": f"line {i}",
                    }
                )
            )
        log_file.write_text("\n".join(lines) + "\n")
        config = tmp_path / "config.yaml"
        config.write_text(
            f"sources:\n"
            f"  local-app:\n"
            f"    type: local\n"
            f"    paths:\n"
            f'      - "{tmp_path / "*.jsonl"}"\n'
            f"    parseJson: true\n"
            f"    timestampField: timestamp\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_tailing_with_lines_then_returns_last_n_entries(self, mcp):
        result = await mcp.call_tool("tail_logs", {"source": "local-app", "lines": 2})
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 2
        assert data["entries"][0]["message"] == "line 3"
        assert data["entries"][1]["message"] == "line 4"

    @pytest.mark.asyncio
    async def test_when_source_does_not_exist_then_returns_error(self, mcp):
        result = await mcp.call_tool("tail_logs", {"source": "missing", "lines": 10})
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["entries"] == []


class TestServerToolAggregateLogs:
    """Scenarios for the aggregate_logs tool."""

    @pytest.fixture
    def mcp(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "x",
                    "service": "payment",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:05:00Z",
                    "level": "INFO",
                    "message": "y",
                    "service": "api",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:10:00Z",
                    "level": "ERROR",
                    "message": "z",
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
    async def test_when_aggregating_by_level_then_returns_counts(self, mcp):
        result = await mcp.call_tool(
            "aggregate_logs",
            {"source": "local-app", "group_by": ["level"]},
        )
        data = json.loads(result[0].text)
        assert len(data["buckets"]) == 2
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_when_source_does_not_exist_then_returns_error(self, mcp):
        result = await mcp.call_tool(
            "aggregate_logs",
            {"source": "missing", "group_by": ["level"]},
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["buckets"] == []


class TestServerToolSummarizeLogs:
    """Scenarios for the summarize_logs tool."""

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
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:05:00Z",
                    "level": "INFO",
                    "message": "OK",
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
    async def test_when_logs_exist_then_returns_summary_with_counts(self, mcp):
        result = await mcp.call_tool(
            "summarize_logs", {"source": "local-app", "query": "", "limit": 10}
        )
        data = json.loads(result[0].text)
        assert "summary" in data
        assert data["count"] == 2
        assert "ERROR" in data["levels"]
        assert "INFO" in data["levels"]
        assert "payment" in data["services"]
        assert "api" in data["services"]

    @pytest.mark.asyncio
    async def test_when_no_logs_match_then_returns_empty_summary(self, mcp):
        result = await mcp.call_tool(
            "summarize_logs",
            {"source": "local-app", "query": "nonexistent", "limit": 10},
        )
        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert "No logs found" in data["summary"]

    @pytest.mark.asyncio
    async def test_when_source_does_not_exist_then_returns_error(self, mcp):
        result = await mcp.call_tool(
            "summarize_logs", {"source": "missing", "query": "", "limit": 10}
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["count"] == 0
