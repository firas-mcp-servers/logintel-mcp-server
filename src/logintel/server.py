"""LogIntel MCP Server implementation using FastMCP."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from logintel.config import Settings
from logintel.logging_config import configure_logging
from logintel.models.params import (
    AggregateParams,
    FilterParams,
    SearchParams,
    TailParams,
)
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

    @mcp.tool(annotations={"readOnlyHint": True})
    async def search_logs(
        source: str,
        query: str,
        time_range: dict | None = None,
        limit: int = 100,
        offset: str | None = None,
    ) -> dict:
        """Search logs using natural language or a structured query."""
        try:
            provider = registry.get(source)
            params = SearchParams(
                source=source,
                query=query,
                time_range=_dict_to_time_range(time_range),
                limit=limit,
                offset=offset,
            )
            result = await provider.search(params)
            return result.model_dump(by_alias=True)
        except KeyError:
            return {"error": f"Unknown source: {source}", "entries": []}
        except Exception as exc:  # noqa: BLE001
            logger.exception("search_logs failed for source '%s'", source)
            return {"error": str(exc), "entries": []}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def filter_logs(
        source: str,
        time_range: dict | None = None,
        level: str | None = None,
        service: str | None = None,
        host: str | None = None,
        trace_id: str | None = None,
        custom_fields: dict | None = None,
        limit: int = 100,
        offset: str | None = None,
    ) -> dict:
        """Filter logs by structured criteria."""
        try:
            provider = registry.get(source)
            params = FilterParams(
                source=source,
                time_range=_dict_to_time_range(time_range),
                level=level,
                service=service,
                host=host,
                trace_id=trace_id,
                custom_fields=custom_fields or {},
                limit=limit,
                offset=offset,
            )
            result = await provider.filter(params)
            return result.model_dump(by_alias=True)
        except KeyError:
            return {"error": f"Unknown source: {source}", "entries": []}
        except Exception as exc:  # noqa: BLE001
            logger.exception("filter_logs failed for source '%s'", source)
            return {"error": str(exc), "entries": []}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def tail_logs(
        source: str,
        lines: int = 50,
        filter_query: str | None = None,
    ) -> dict:
        """Stream/follow logs in real-time from a source (returns latest N entries)."""
        try:
            provider = registry.get(source)
            params = TailParams(
                source=source,
                lines=lines,
                filter_query=filter_query,
            )
            result = await provider.tail(params)
            return result.model_dump(by_alias=True)
        except KeyError:
            return {"error": f"Unknown source: {source}", "entries": []}
        except Exception as exc:  # noqa: BLE001
            logger.exception("tail_logs failed for source '%s'", source)
            return {"error": str(exc), "entries": []}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def aggregate_logs(
        source: str,
        time_range: dict | None = None,
        group_by: list[str] | None = None,
        metric: str = "count",
        field: str | None = None,
        time_bucket: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Aggregate/group logs (count by service, error rate over time, top error messages)."""
        try:
            provider = registry.get(source)
            params = AggregateParams(
                source=source,
                time_range=_dict_to_time_range(time_range),
                group_by=group_by or [],
                metric=metric,
                field=field,
                time_bucket=time_bucket,
                limit=limit,
            )
            result = await provider.aggregate(params)
            return result.model_dump(by_alias=True)
        except KeyError:
            return {"error": f"Unknown source: {source}", "buckets": [], "total": 0}
        except Exception as exc:  # noqa: BLE001
            logger.exception("aggregate_logs failed for source '%s'", source)
            return {"error": str(exc), "buckets": [], "total": 0}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def summarize_logs(source: str, query: str = "", limit: int = 100) -> dict:
        """Generate a natural language summary of a set of logs."""
        try:
            provider = registry.get(source)
            params = SearchParams(source=source, query=query, limit=limit)
            result = await provider.search(params)

            entries = result.entries
            if not entries:
                return {"summary": "No logs found matching the criteria.", "count": 0}

            levels: dict[str, int] = {}
            services: dict[str, int] = {}
            messages: dict[str, int] = {}

            for entry in entries:
                levels[entry.level] = levels.get(entry.level, 0) + 1
                svc = entry.service or "unknown"
                services[svc] = services.get(svc, 0) + 1
                messages[entry.message] = messages.get(entry.message, 0) + 1

            top_errors = sorted(
                messages.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]

            summary_parts = [f"Analyzed {len(entries)} log entries."]
            if levels:
                level_str = ", ".join(f"{k}: {v}" for k, v in sorted(levels.items()))
                summary_parts.append(f"Levels — {level_str}.")
            if services:
                svc_str = ", ".join(f"{k}: {v}" for k, v in sorted(services.items()))
                summary_parts.append(f"Services — {svc_str}.")
            if top_errors:
                summary_parts.append(
                    f"Top message: '{top_errors[0][0]}' ({top_errors[0][1]} occurrences)."
                )

            return {
                "summary": " ".join(summary_parts),
                "count": len(entries),
                "levels": levels,
                "services": services,
                "top_messages": [msg for msg, _ in top_errors],
            }
        except KeyError:
            return {"error": f"Unknown source: {source}", "count": 0}
        except Exception as exc:  # noqa: BLE001
            logger.exception("summarize_logs failed for source '%s'", source)
            return {"error": str(exc), "count": 0}

    logger.info(
        "LogIntel MCP server initialized with %d source(s)",
        len(registry.all_providers()),
    )
    return mcp


def _dict_to_time_range(time_range: dict | None):
    """Convert a raw dict to a TimeRange model."""
    from logintel.models.common import TimeRange

    if not time_range:
        return None
    return TimeRange(
        from_time=time_range.get("from", "now-1h"),
        to_time=time_range.get("to"),
    )


async def run_server(mcp: FastMCP, transport: str = "stdio") -> None:
    """Run the MCP server with the specified transport."""
    if transport == "stdio":
        await mcp.run_stdio_async()
    elif transport == "http":
        await mcp.run_sse_async()
    else:
        raise ValueError(f"Unsupported transport: {transport}")
