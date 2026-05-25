"""Integration tests: MCP tool responses through equipped CloudWatch provider."""

import json
from unittest.mock import MagicMock, patch

import pytest

from logintel.server import create_server

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_mock_logs_client(**kwargs):
    """Create a mock CloudWatch Logs client with sensible defaults."""
    client = MagicMock()
    client.start_query.return_value = {"queryId": "test-query-id"}
    client.get_query_results.return_value = {
        "status": "Complete",
        "results": kwargs.get("results", []),
    }
    client.filter_log_events.return_value = {
        "events": kwargs.get("events", []),
    }
    log_groups = kwargs.get("log_groups", [])
    if log_groups is not None:
        client.describe_log_groups.return_value = {"logGroups": log_groups}
    return client


def _make_mock_session(mock_logs_client):
    """Create a mock boto3 Session that returns the given logs client."""
    session = MagicMock()
    session.client.return_value = mock_logs_client
    return session


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestMcpCloudWatchListSources:
    """list_log_sources with CloudWatch provider equipped."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_cloudwatch_configured_then_list_includes_cloudwatch(self, mcp):
        result = await mcp.call_tool("list_log_sources", {})
        data = json.loads(result[0].text)
        ids = {s["id"] for s in data["sources"]}
        assert "cw-test" in ids
        assert any(s["type"] == "cloudwatch" for s in data["sources"])


class TestMcpCloudWatchHealth:
    """get_source_health through CloudWatch provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_cloudwatch_reachable_then_healthy(self, mock_session_cls, mcp):
        mock_client = _make_mock_logs_client(log_groups=[{"logGroupName": "/aws/lambda/app"}])
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool("get_source_health", {"source": "cw-test"})
        data = json.loads(result[0].text)
        assert data["status"] == "healthy"
        assert "log group" in data["message"]

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_cloudwatch_fails_then_unhealthy(self, mock_session_cls, mcp):
        mock_client = MagicMock()
        mock_client.describe_log_groups.side_effect = Exception("timeout")
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool("get_source_health", {"source": "cw-test"})
        data = json.loads(result[0].text)
        assert data["status"] == "unhealthy"


class TestMcpCloudWatchSearch:
    """search_logs through CloudWatch provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_cloudwatch_returns_results_then_entries_parsed(self, mock_session_cls, mcp):
        mock_client = _make_mock_logs_client(
            log_groups=[{"logGroupName": "/aws/lambda/app"}],
            results=[
                [
                    {"field": "@timestamp", "value": "2026-05-24 10:00:00.000"},
                    {"field": "@message", "value": "Payment failed"},
                    {"field": "@logStream", "value": "stream-1"},
                ]
            ],
        )
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool(
            "search_logs",
            {"source": "cw-test", "query": "Payment"},
        )
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["message"] == "Payment failed"
        assert data["entries"][0]["source"] == "cw-test"

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_cloudwatch_returns_empty_then_entries_empty(self, mock_session_cls, mcp):
        mock_client = _make_mock_logs_client(
            log_groups=[{"logGroupName": "/aws/lambda/app"}], results=[]
        )
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool(
            "search_logs",
            {"source": "cw-test", "query": "nothing"},
        )
        data = json.loads(result[0].text)
        assert data["entries"] == []


class TestMcpCloudWatchFilter:
    """filter_logs through CloudWatch provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_filter_by_level_then_parses_entries(self, mock_session_cls, mcp):
        mock_client = _make_mock_logs_client(
            log_groups=[{"logGroupName": "/aws/lambda/app"}],
            results=[
                [
                    {"field": "@timestamp", "value": "2026-05-24 10:00:00.000"},
                    {"field": "@message", "value": "ERROR: db timeout"},
                    {"field": "@logStream", "value": "stream-1"},
                ]
            ],
        )
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool(
            "filter_logs",
            {"source": "cw-test", "level": "ERROR"},
        )
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["level"] == "ERROR"


class TestMcpCloudWatchTail:
    """tail_logs through CloudWatch provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_tail_called_then_returns_latest_entries(self, mock_session_cls, mcp):
        mock_client = _make_mock_logs_client(
            log_groups=[{"logGroupName": "/aws/lambda/app"}],
            events=[
                {
                    "timestamp": 9999999999000,
                    "message": "latest event",
                    "logStreamName": "stream-1",
                }
            ],
        )
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool("tail_logs", {"source": "cw-test", "lines": 1})
        data = json.loads(result[0].text)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["message"] == "latest event"


class TestMcpCloudWatchAggregate:
    """aggregate_logs through CloudWatch provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_aggregate_by_level_then_returns_buckets(self, mock_session_cls, mcp):
        mock_client = _make_mock_logs_client(
            log_groups=[{"logGroupName": "/aws/lambda/app"}],
            results=[
                [
                    {"field": "level", "value": "ERROR"},
                    {"field": "count", "value": "5"},
                ]
            ],
        )
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool(
            "aggregate_logs",
            {"source": "cw-test", "group_by": ["level"], "metric": "count"},
        )
        data = json.loads(result[0].text)
        assert len(data["buckets"]) == 1
        assert data["total"] == 5


class TestMcpCloudWatchSchema:
    """get_source_schema through CloudWatch provider."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_cloudwatch_configured_then_returns_schema(self, mcp):
        result = await mcp.call_tool("get_source_schema", {"source": "cw-test"})
        data = json.loads(result[0].text)
        assert data["source"] == "cw-test"
        assert len(data["fields"]) > 0
        field_names = {f["name"] for f in data["fields"]}
        assert "@message" in field_names


class TestMcpCloudWatchErrorPaths:
    """Error handling through CloudWatch provider + MCP layer."""

    @pytest.fixture
    def mcp(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "sources:\n  cw-test:\n    type: cloudwatch\n    region: us-east-1\n    logGroups:\n      - /aws/lambda/app\n"  # noqa: E501
        )
        return create_server(config_path=str(config), log_level="ERROR")

    @pytest.mark.asyncio
    async def test_when_unknown_source_then_returns_error(self, mcp):
        result = await mcp.call_tool("search_logs", {"source": "missing", "query": "x"})
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["entries"] == []

    @pytest.mark.asyncio
    @patch("logintel.providers.cloudwatch.boto3.Session")
    async def test_when_boto_error_then_returns_empty_entries(self, mock_session_cls, mcp):
        mock_client = _make_mock_logs_client(log_groups=[{"logGroupName": "/aws/lambda/app"}])
        mock_client.start_query.side_effect = Exception("AWS down")
        mock_session = _make_mock_session(mock_client)
        mock_session_cls.return_value = mock_session

        result = await mcp.call_tool(
            "search_logs",
            {"source": "cw-test", "query": "x"},
        )
        data = json.loads(result[0].text)
        assert data["entries"] == []
        assert data["total"] == 0
