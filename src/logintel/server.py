"""LogIntel MCP Server implementation using FastMCP."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from logintel.config import Settings
from logintel.logging_config import configure_logging
from logintel.providers.registry import ProviderRegistry

logger = logging.getLogger("logintel.server")


def create_server(
    config_path: str = ".logintelrc.yaml",
    log_level: str = "INFO",
) -> FastMCP:
    """Create and configure the FastMCP server."""
    configure_logging(level=log_level)

    settings = Settings.from_yaml(config_path)
    registry = ProviderRegistry(settings)

    mcp = FastMCP("logintel")

    @mcp.tool(annotations={"readOnlyHint": True})
    async def list_log_sources() -> dict:
        """List all configured log sources."""
        return {"sources": registry.list_sources()}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def get_source_health(source: str) -> dict:
        """Check connectivity and health of a log source."""
        try:
            provider = registry.get(source)
            health = await provider.health()
            return health.model_dump(by_alias=True)
        except KeyError as exc:
            logger.warning("Health check for unknown source: %s", source)
            return {
                "source": source,
                "status": "unknown",
                "message": f"Unknown source: {exc}",
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Health check failed for source '%s'", source)
            return {
                "source": source,
                "status": "unhealthy",
                "message": str(exc),
            }

    @mcp.tool(annotations={"readOnlyHint": True})
    async def get_source_schema(source: str) -> dict:
        """Get field/schema info for a log source."""
        try:
            provider = registry.get(source)
            schema = await provider.get_schema()
            return schema.model_dump(by_alias=True)
        except KeyError as exc:
            logger.warning("Schema request for unknown source: %s", source)
            return {
                "source": source,
                "fields": [],
                "known_formats": [],
                "error": f"Unknown source: {exc}",
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Schema request failed for source '%s'", source)
            return {
                "source": source,
                "fields": [],
                "known_formats": [],
                "error": str(exc),
            }

    logger.info("LogIntel MCP server initialized with %d source(s)", len(registry.all_providers()))
    return mcp


async def run_server(mcp: FastMCP, transport: str = "stdio") -> None:
    """Run the MCP server with the specified transport."""
    if transport == "stdio":
        await mcp.run_stdio_async()
    elif transport == "http":
        await mcp.run_sse_async()
    else:
        raise ValueError(f"Unsupported transport: {transport}")
