"""End-to-end tests for server transport scenarios."""

from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from logintel.server import run_server


class TestRunServerTransport:
    """Scenarios for running the MCP server with different transports."""

    @pytest.mark.asyncio
    async def test_when_stdio_transport_is_used_then_runs_stdio_async(self):
        mcp = FastMCP("test")
        mcp.run_stdio_async = AsyncMock()
        await run_server(mcp, transport="stdio")
        mcp.run_stdio_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_when_http_transport_is_used_then_runs_sse_async(self):
        mcp = FastMCP("test")
        mcp.run_sse_async = AsyncMock()
        await run_server(mcp, transport="http")
        mcp.run_sse_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_when_unsupported_transport_is_used_then_raises_value_error(self):
        mcp = FastMCP("test")
        with pytest.raises(ValueError, match="Unsupported transport: websocket"):
            await run_server(mcp, transport="websocket")
