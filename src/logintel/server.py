"""LogIntel MCP Server implementation using FastMCP."""

from mcp.server.fastmcp import FastMCP

from logintel.config import Settings


def create_server(config_path: str = ".logintelrc.yaml") -> FastMCP:
    """Create and configure the FastMCP server."""
    settings = Settings.from_yaml(config_path)

    mcp = FastMCP("logintel")

    @mcp.tool(annotations={"readOnlyHint": True})
    async def list_log_sources() -> dict:
        """List all configured log sources."""
        return {
            "sources": [
                {"id": source_id, "type": source.type}
                for source_id, source in settings.sources.items()
            ]
        }

    @mcp.tool(annotations={"readOnlyHint": True})
    async def get_source_health(source: str) -> dict:
        """Check connectivity and health of a log source."""
        return {"source": source, "status": "unknown", "message": "Not yet implemented"}

    return mcp


async def run_server(mcp: FastMCP, transport: str = "stdio") -> None:
    """Run the MCP server with the specified transport."""
    if transport == "stdio":
        await mcp.run_stdio_async()
    elif transport == "http":
        # FastMCP SSE transport
        await mcp.run_sse_async()
    else:
        raise ValueError(f"Unsupported transport: {transport}")
