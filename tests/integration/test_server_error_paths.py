"""Integration tests for server error handling scenarios."""

import json
from unittest.mock import patch

import pytest

from logintel.server import create_server


class BrokenProvider:
    """A provider that raises exceptions on every method call."""

    @property
    def id(self):
        return "broken"

    @property
    def type(self):
        return "broken"

    async def health(self):
        raise RuntimeError("health is broken")

    async def search(self, params):  # noqa: ANN001, ANN202
        raise RuntimeError("search is broken")

    async def filter(self, params):  # noqa: ANN001, ANN202
        raise RuntimeError("filter is broken")

    async def aggregate(self, params):  # noqa: ANN001, ANN202
        raise RuntimeError("aggregate is broken")

    async def tail(self, params):  # noqa: ANN001, ANN202
        raise RuntimeError("tail is broken")

    async def get_schema(self):
        raise RuntimeError("schema is broken")

    async def detect_patterns(self, params):  # noqa: ANN001, ANN202
        raise RuntimeError("patterns is broken")

    async def find_anomalies(self, params):  # noqa: ANN001, ANN202
        raise RuntimeError("anomalies is broken")


@pytest.fixture
def mcp_with_broken_provider(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        'sources:\n  broken-source:\n    type: local\n    paths:\n      - "/tmp/*.log"\n'
    )

    with patch(
        "logintel.providers.registry.ProviderRegistry._create_provider",
        return_value=BrokenProvider(),
    ):
        mcp = create_server(config_path=str(config), log_level="ERROR")

    return mcp


class TestServerToolErrorHandling:
    """Scenarios where provider methods raise exceptions."""

    @pytest.mark.asyncio
    async def test_when_health_raises_then_returns_unhealthy_status(self, mcp_with_broken_provider):
        result = await mcp_with_broken_provider.call_tool(
            "get_source_health", {"source": "broken-source"}
        )
        data = json.loads(result[0].text)
        assert data["status"] == "unhealthy"
        assert "health is broken" in data["message"]

    @pytest.mark.asyncio
    async def test_when_schema_raises_then_returns_error(self, mcp_with_broken_provider):
        result = await mcp_with_broken_provider.call_tool(
            "get_source_schema", {"source": "broken-source"}
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "schema is broken" in data["error"]

    @pytest.mark.asyncio
    async def test_when_search_raises_then_returns_error(self, mcp_with_broken_provider):
        result = await mcp_with_broken_provider.call_tool(
            "search_logs", {"source": "broken-source", "query": "test"}
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "search is broken" in data["error"]

    @pytest.mark.asyncio
    async def test_when_filter_raises_then_returns_error(self, mcp_with_broken_provider):
        result = await mcp_with_broken_provider.call_tool(
            "filter_logs", {"source": "broken-source", "level": "ERROR"}
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "filter is broken" in data["error"]

    @pytest.mark.asyncio
    async def test_when_tail_raises_then_returns_error(self, mcp_with_broken_provider):
        result = await mcp_with_broken_provider.call_tool(
            "tail_logs", {"source": "broken-source", "lines": 10}
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "tail is broken" in data["error"]

    @pytest.mark.asyncio
    async def test_when_aggregate_raises_then_returns_error(self, mcp_with_broken_provider):
        result = await mcp_with_broken_provider.call_tool(
            "aggregate_logs",
            {"source": "broken-source", "group_by": ["level"]},
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "aggregate is broken" in data["error"]

    @pytest.mark.asyncio
    async def test_when_summarize_raises_then_returns_error(self, mcp_with_broken_provider):
        result = await mcp_with_broken_provider.call_tool(
            "summarize_logs",
            {"source": "broken-source", "query": "", "limit": 10},
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "search is broken" in data["error"]
