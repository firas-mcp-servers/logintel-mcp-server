"""Integration tests: MCP tool responses through equipped Loki provider."""

import json

import httpx
import pytest
import respx

from logintel.server import create_server

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _loki_config():
    return {
        "sources": {
            "loki-test": {
                "type": "loki",
                "url": "http://localhost:3100",
                "defaultLabels": {"app": "api"},
            }
        }
    }


def _yaml_from_dict(d):
    import yaml

    return yaml.dump(d)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestMcpLokiListSources:
    """list_log_sources with Loki provider equipped."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_loki_configured_then_list_includes_loki(self, mcp):
        result = await mcp.call_tool("list_log_sources", {})
        data = json.loads(result[0].text)
        ids = {s["id"] for s in data["sources"]}
        assert "loki-test" in ids
        assert any(s["type"] == "loki" for s in data["sources"])


class TestMcpLokiHealth:
    """get_source_health through Loki provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_loki_ready_then_returns_healthy(self, mcp):
        respx.get("http://localhost:3100/ready").mock(
            return_value=httpx.Response(200, json={"status": "ready"})
        )
        result = await mcp.call_tool("get_source_health", {"source": "loki-test"})
        data = json.loads(result[0].text)
        assert data["status"] == "healthy"
        assert "Loki" in data["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_loki_not_ready_then_returns_degraded(self, mcp):
        respx.get("http://localhost:3100/ready").mock(
            return_value=httpx.Response(503, json={"status": "not ready"})
        )
        result = await mcp.call_tool("get_source_health", {"source": "loki-test"})
        data = json.loads(result[0].text)
        assert data["status"] == "degraded"


class TestMcpLokiSearch:
    """search_logs through Loki provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
            "    defaultLabels:\n      app: api\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_loki_returns_streams_then_entries_parsed(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/query_range").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"service": "api", "host": "host-1"},
                                "values": [
                                    [
                                        "1716540000000000000",
                                        '{"message":"hello","level":"info","trace_id":"abc123"}',
                                    ]
                                ],
                            }
                        ],
                    },
                },
            )
        )
        result = await mcp.call_tool(
            "search_logs",
            {"source": "loki-test", "query": "hello"},
        )
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["message"] == "hello"
        assert data["entries"][0]["level"] == "INFO"
        assert data["entries"][0]["trace_id"] == "abc123"
        assert data["entries"][0]["source"] == "loki-test"

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_loki_returns_empty_then_entries_empty(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/query_range").mock(
            return_value=httpx.Response(
                200,
                json={"status": "success", "data": {"resultType": "streams", "result": []}},
            )
        )
        result = await mcp.call_tool(
            "search_logs",
            {"source": "loki-test", "query": "nothing"},
        )
        data = json.loads(result[0].text)
        assert data["entries"] == []


class TestMcpLokiFilter:
    """filter_logs through Loki provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_filter_by_level_then_parses_entries(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/query_range").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"service": "api"},
                                "values": [
                                    [
                                        "1716540000000000000",
                                        '{"message":"err","level":"error"}',
                                    ]
                                ],
                            }
                        ],
                    },
                },
            )
        )
        result = await mcp.call_tool(
            "filter_logs",
            {"source": "loki-test", "level": "error"},
        )
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["level"] == "ERROR"


class TestMcpLokiTail:
    """tail_logs through Loki provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_tail_called_then_returns_latest_entries(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/query_range").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"service": "api"},
                                "values": [
                                    [
                                        "1716540000000000000",
                                        '{"message":"latest","level":"info"}',
                                    ]
                                ],
                            }
                        ],
                    },
                },
            )
        )
        result = await mcp.call_tool("tail_logs", {"source": "loki-test", "lines": 1})
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["message"] == "latest"


class TestMcpLokiAggregate:
    """aggregate_logs through Loki provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_aggregate_by_service_then_returns_buckets(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/query_range").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "matrix",
                        "result": [
                            {
                                "metric": {"service": "api"},
                                "values": [[1716540000, "5"]],
                            }
                        ],
                    },
                },
            )
        )
        result = await mcp.call_tool(
            "aggregate_logs",
            {"source": "loki-test", "group_by": ["service"], "metric": "count"},
        )
        data = json.loads(result[0].text)
        assert len(data["buckets"]) >= 1
        assert data["total"] >= 1


class TestMcpLokiSchema:
    """get_source_schema through Loki provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_loki_labels_available_then_returns_schema(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/labels").mock(
            return_value=httpx.Response(200, json={"data": ["app", "service", "host"]})
        )
        result = await mcp.call_tool("get_source_schema", {"source": "loki-test"})
        data = json.loads(result[0].text)
        assert data["source"] == "loki-test"
        assert len(data["fields"]) > 0
        field_names = {f["name"] for f in data["fields"]}
        assert "app" in field_names

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_loki_labels_fails_then_returns_fallback_schema(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/labels").mock(
            return_value=httpx.Response(500, json={"error": "oops"})
        )
        result = await mcp.call_tool("get_source_schema", {"source": "loki-test"})
        data = json.loads(result[0].text)
        assert data["source"] == "loki-test"
        assert len(data["fields"]) > 0


class TestMcpLokiErrorPaths:
    """Error handling through Loki provider + MCP layer."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  loki-test:\n    type: loki\n    url: http://localhost:3100\n"
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_unknown_source_then_returns_error(self, mcp):
        result = await mcp.call_tool("search_logs", {"source": "missing", "query": "x"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["entries"] == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_http_error_then_returns_empty_entries(self, mcp):
        respx.get("http://localhost:3100/loki/api/v1/query_range").mock(
            side_effect=ConnectionError("refused")
        )
        result = await mcp.call_tool(
            "search_logs",
            {"source": "loki-test", "query": "x"},
        )
        data = json.loads(result[0].text)
        assert data["entries"] == []
        assert data["total"] == 0
