"""Integration tests: MCP tool responses through equipped Datadog provider."""

import json

import httpx
import pytest
import respx

from logintel.server import create_server


class TestMcpDatadogListSources:
    """list_log_sources with Datadog provider equipped."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_datadog_configured_then_list_includes_datadog(self, mcp):
        result = await mcp.call_tool("list_log_sources", {})
        data = json.loads(result[0].text)
        ids = {s["id"] for s in data["sources"]}
        assert "dd-test" in ids
        assert any(s["type"] == "datadog" for s in data["sources"])


class TestMcpDatadogHealth:
    """get_source_health through Datadog provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_datadog_returns_200_then_healthy(self, mcp):
        respx.post("https://api.datadoghq.com/api/v2/logs/events/search").mock(
            return_value=httpx.Response(200, json={"data": [], "meta": {}})
        )
        result = await mcp.call_tool("get_source_health", {"source": "dd-test"})
        data = json.loads(result[0].text)
        assert data["status"] == "healthy"
        assert "datadoghq.com" in data["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_datadog_returns_401_then_unhealthy(self, mcp):
        respx.post("https://api.datadoghq.com/api/v2/logs/events/search").mock(
            return_value=httpx.Response(401, json={})
        )
        result = await mcp.call_tool("get_source_health", {"source": "dd-test"})
        data = json.loads(result[0].text)
        assert data["status"] == "unhealthy"
        assert "authentication" in data["message"].lower()


class TestMcpDatadogSearch:
    """search_logs through Datadog provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_datadog_returns_logs_then_entries_parsed(self, mcp):
        respx.post("https://api.datadoghq.com/api/v2/logs/events/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "log-1",
                            "attributes": {
                                "timestamp": "2026-05-24T10:00:00Z",
                                "message": "Payment failed",
                                "status": "error",
                                "service": "payment",
                                "host": "host-1",
                                "tags": ["env:prod"],
                            },
                        }
                    ],
                    "meta": {"page": {"after": "cursor-1"}},
                },
            )
        )
        result = await mcp.call_tool(
            "search_logs",
            {"source": "dd-test", "query": "Payment"},
        )
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["message"] == "Payment failed"
        assert data["entries"][0]["level"] == "ERROR"
        assert data["entries"][0]["service"] == "payment"
        assert data["entries"][0]["source"] == "dd-test"
        assert data["next_offset"] == "cursor-1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_datadog_returns_empty_then_entries_empty(self, mcp):
        respx.post("https://api.datadoghq.com/api/v2/logs/events/search").mock(
            return_value=httpx.Response(200, json={"data": [], "meta": {}})
        )
        result = await mcp.call_tool(
            "search_logs",
            {"source": "dd-test", "query": "nothing"},
        )
        data = json.loads(result[0].text)
        assert data["entries"] == []


class TestMcpDatadogFilter:
    """filter_logs through Datadog provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_filter_by_service_then_parses_entries(self, mcp):
        respx.post("https://api.datadoghq.com/api/v2/logs/events/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "log-1",
                            "attributes": {
                                "timestamp": "2026-05-24T10:00:00Z",
                                "message": "err",
                                "status": "error",
                                "service": "api",
                            },
                        }
                    ],
                    "meta": {},
                },
            )
        )
        result = await mcp.call_tool(
            "filter_logs",
            {"source": "dd-test", "service": "api"},
        )
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["service"] == "api"


class TestMcpDatadogTail:
    """tail_logs through Datadog provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_tail_called_then_returns_latest_entries(self, mcp):
        respx.post("https://api.datadoghq.com/api/v2/logs/events/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "log-1",
                            "attributes": {
                                "timestamp": "2026-05-24T10:00:00Z",
                                "message": "latest",
                                "status": "info",
                                "service": "api",
                            },
                        }
                    ],
                    "meta": {},
                },
            )
        )
        result = await mcp.call_tool("tail_logs", {"source": "dd-test", "lines": 1})
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["message"] == "latest"


class TestMcpDatadogAggregate:
    """aggregate_logs through Datadog provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @respx.mock
    async def test_when_aggregate_by_service_then_returns_buckets(self, mcp):
        respx.post("https://api.datadoghq.com/api/v2/logs/analytics/aggregate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "buckets": [
                            {
                                "by": {"service": "api"},
                                "aggregations": [{"value": 42}],
                            }
                        ]
                    },
                    "meta": {},
                },
            )
        )
        result = await mcp.call_tool(
            "aggregate_logs",
            {"source": "dd-test", "group_by": ["service"], "metric": "count"},
        )
        data = json.loads(result[0].text)
        assert len(data["buckets"]) == 1
        assert data["total"] == 42


class TestMcpDatadogSchema:
    """get_source_schema through Datadog provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_datadog_configured_then_returns_schema(self, mcp):
        result = await mcp.call_tool("get_source_schema", {"source": "dd-test"})
        data = json.loads(result[0].text)
        assert data["source"] == "dd-test"
        assert len(data["fields"]) > 0
        field_names = {f["name"] for f in data["fields"]}
        assert "message" in field_names


class TestMcpDatadogErrorPaths:
    """Error handling through Datadog provider + MCP layer."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  dd-test:\n    type: datadog\n    site: datadoghq.com\n    apiKey: test-api\n    appKey: test-app\n"  # noqa: E501
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
        respx.post("https://api.datadoghq.com/api/v2/logs/events/search").mock(
            side_effect=ConnectionError("refused")
        )
        result = await mcp.call_tool(
            "search_logs",
            {"source": "dd-test", "query": "x"},
        )
        data = json.loads(result[0].text)
        assert data["entries"] == []
        assert data["total"] == 0
