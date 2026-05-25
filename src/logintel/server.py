"""LogIntel MCP Server implementation using FastMCP."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from logintel.cache import QueryCache
from logintel.config import Settings
from logintel.intelligence.comparator import compare_periods
from logintel.intelligence.correlator import correlate_across_sources
from logintel.intelligence.nl2query import explain, translate
from logintel.intelligence.root_cause import analyze_root_cause as _analyze_root_cause
from logintel.logging_config import configure_logging
from logintel.models.params import (
    AggregateParams,
    AnomalyParams,
    FilterParams,
    PatternParams,
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
    cache = QueryCache(
        maxsize=settings.intelligence.cache_ttl_seconds * 2,
        ttl=settings.intelligence.cache_ttl_seconds,
    )

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

    # ------------------------------------------------------------------
    # Phase 5 — Intelligence tools
    # ------------------------------------------------------------------

    @mcp.tool(annotations={"readOnlyHint": True})
    async def correlate_logs(
        sources: list[str],
        time_range: dict | None = None,
        trace_id: str | None = None,
        service: str | None = None,
        correlation_window: str = "5m",
        limit: int = 100,
    ) -> dict:
        """Correlate logs across services by trace ID, timestamp proximity, or shared fields."""
        cache_key = {
            "sources": sorted(sources),
            "time_range": time_range,
            "trace_id": trace_id,
            "service": service,
            "correlation_window": correlation_window,
            "limit": limit,
        }
        cached = cache.get("__correlate__", "correlate", cache_key)
        if cached is not None:
            return cached

        try:
            result = await correlate_across_sources(
                registry=registry,
                sources=sources,
                time_range=time_range,
                trace_id=trace_id,
                service=service,
                correlation_window=correlation_window,
                limit=limit,
            )
            cache.set("__correlate__", "correlate", cache_key, result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("correlate_logs failed")
            return {"error": str(exc), "groups": [], "total_entries": 0}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def analyze_root_cause(
        service: str,
        time_range: dict,
        symptom: str,
        sources: list[str] | None = None,
        correlation_window: str = "5m",
        limit: int = 100,
    ) -> dict:
        """Given an incident timeframe and affected service, analyze surrounding
        logs to identify likely root causes."""
        cache_key = {
            "service": service,
            "time_range": time_range,
            "symptom": symptom,
            "sources": sorted(sources) if sources else None,
            "correlation_window": correlation_window,
            "limit": limit,
        }
        cached = cache.get("__root_cause__", "analyze", cache_key)
        if cached is not None:
            return cached

        try:
            result = await _analyze_root_cause(
                registry=registry,
                service=service,
                time_range=time_range,
                symptom=symptom,
                sources=sources,
                correlation_window=correlation_window,
                limit=limit,
            )
            cache.set("__root_cause__", "analyze", cache_key, result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("analyze_root_cause failed")
            return {"error": str(exc), "likely_causes": []}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def compare_time_periods(
        source: str,
        baseline_range: dict,
        comparison_range: dict,
        query: str = "",
        limit: int = 100,
    ) -> dict:
        """Compare logs between two time windows (e.g., before/after deployment)."""
        cache_key = {
            "source": source,
            "baseline_range": baseline_range,
            "comparison_range": comparison_range,
            "query": query,
            "limit": limit,
        }
        cached = cache.get("__compare__", "compare", cache_key)
        if cached is not None:
            return cached

        try:
            provider = registry.get(source)
            result = await compare_periods(
                provider=provider,
                source=source,
                baseline_range=baseline_range,
                comparison_range=comparison_range,
                query=query,
                limit=limit,
            )
            cache.set("__compare__", "compare", cache_key, result)
            return result
        except KeyError:
            return {"error": f"Unknown source: {source}"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("compare_time_periods failed for source '%s'", source)
            return {"error": str(exc)}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def detect_error_patterns(
        source: str,
        time_range: dict | None = None,
        service: str | None = None,
        min_occurrences: int = 5,
    ) -> dict:
        """Analyze logs to detect recurring error patterns, group similar errors,
        and surface anomalies."""
        try:
            provider = registry.get(source)
            params = PatternParams(
                source=source,
                time_range=_dict_to_time_range(time_range),
                service=service,
                min_occurrences=min_occurrences,
            )
            result = await provider.detect_patterns(params)
            return result.model_dump(by_alias=True)
        except KeyError:
            return {"error": f"Unknown source: {source}", "patterns": []}
        except Exception as exc:  # noqa: BLE001
            logger.exception("detect_error_patterns failed for source '%s'", source)
            return {"error": str(exc), "patterns": []}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def find_anomalies(
        source: str,
        time_range: dict | None = None,
        metric: str = "log_volume",
        sensitivity: str = "medium",
    ) -> dict:
        """Detect statistical anomalies in log volume, error rates, latency patterns."""
        try:
            provider = registry.get(source)
            params = AnomalyParams(
                source=source,
                time_range=_dict_to_time_range(time_range),
                metric=metric,
                sensitivity=sensitivity,
            )
            result = await provider.find_anomalies(params)
            return result.model_dump(by_alias=True)
        except KeyError:
            return {"error": f"Unknown source: {source}", "anomalies": []}
        except Exception as exc:  # noqa: BLE001
            logger.exception("find_anomalies failed for source '%s'", source)
            return {"error": str(exc), "anomalies": []}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def natural_language_to_query(source: str, question: str) -> dict:
        """Translate a natural language question into the target backend's native query language."""
        try:
            provider = registry.get(source)
            result = translate(question, provider.type)
            return {"source": source, "provider": provider.type, **result}
        except KeyError:
            return {"error": f"Unknown source: {source}"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("natural_language_to_query failed for source '%s'", source)
            return {"error": str(exc)}

    @mcp.tool(annotations={"readOnlyHint": True})
    async def explain_query(source: str, query: str) -> dict:
        """Explain what a backend-specific query does in plain English."""
        try:
            provider = registry.get(source)
            explanation = explain(query, provider.type)
            return {"source": source, "provider": provider.type, "explanation": explanation}
        except KeyError:
            return {"error": f"Unknown source: {source}"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("explain_query failed for source '%s'", source)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    @mcp.prompt()
    def investigate_incident() -> str:
        """Structured investigation workflow prompt."""
        return """You are an on-call SRE investigating a production incident.

Follow this structured workflow:

1. **Detect anomalies** — Use find_anomalies to check for unusual spikes in
   error rates or log volume.
2. **Search logs** — Use search_logs or filter_logs to find ERROR and WARN
   entries in the affected time window.
3. **Correlate** — Use correlate_logs to find related logs across services by
   trace_id or timestamp proximity.
4. **Analyze root cause** — Use analyze_root_cause with the affected service
   and incident timeframe.
5. **Summarize** — Use summarize_logs to get a high-level view of what happened.
6. **Recommend** — Based on the evidence, suggest the most likely root cause
   and next steps.

Start by asking the user for: the affected service, the approximate incident
time, and the observed symptom."""

    @mcp.prompt()
    def oncall_summary() -> str:
        """Generate a shift summary prompt."""
        return """You are generating an on-call shift summary.

For each configured source, gather:
- Recent error patterns (detect_error_patterns)
- Any anomalies (find_anomalies)
- Top error messages and affected services (summarize_logs)

Then produce a concise shift summary with:
1. **Overall health** — number of sources checked, any unhealthy ones.
2. **Top issues** — the most frequent errors and anomalies.
3. **Recommended actions** — what should be investigated or fixed next.
4. **Notable events** — any spikes, new error types, or service degradations.

Keep the summary brief and actionable."""

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
