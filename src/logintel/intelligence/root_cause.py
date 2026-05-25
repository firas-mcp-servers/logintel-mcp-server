"""Root cause analysis engine."""

from __future__ import annotations

import logging
from typing import Any

from logintel.models.params import FilterParams, SearchParams
from logintel.providers.registry import ProviderRegistry

logger = logging.getLogger("logintel.intelligence.root_cause")


async def analyze_root_cause(
    registry: ProviderRegistry,
    service: str,
    time_range: dict[str, str],
    symptom: str,
    sources: list[str] | None = None,
    correlation_window: str = "5m",
    limit: int = 100,
) -> dict[str, Any]:
    """Analyze surrounding logs to suggest likely root causes."""
    target_sources = sources or list(registry.all_providers().keys())
    from_time = time_range.get("from", "now-1h")
    to_time = time_range.get("to", "now")

    # Step 1: Find error logs in the affected service
    error_entries: list[dict[str, Any]] = []
    for source_id in target_sources:
        try:
            provider = registry.get(source_id)
            params = FilterParams(
                source=source_id,
                time_range=_dict_to_tr(time_range),
                service=service,
                level="ERROR",
                limit=limit,
            )
            result = await provider.filter(params)
            for entry in result.entries:
                error_entries.append(
                    {
                        "entry": entry,
                        "source": source_id,
                    }
                )
        except Exception:
            logger.exception("Root-cause error search failed for source '%s'", source_id)

    # Step 2: Collect all logs in the time window for context
    context_entries: list[dict[str, Any]] = []
    for source_id in target_sources:
        try:
            provider = registry.get(source_id)
            params = SearchParams(
                source=source_id,
                query="",
                time_range=_dict_to_tr(time_range),
                limit=limit,
            )
            result = await provider.search(params)
            for entry in result.entries:
                context_entries.append(
                    {
                        "entry": entry,
                        "source": source_id,
                    }
                )
        except Exception:
            logger.exception("Root-cause context search failed for source '%s'", source_id)

    # Step 3: Build timeline and identify likely causes
    timeline = _build_timeline(context_entries)
    causes = _identify_causes(error_entries, context_entries, service, symptom)

    return {
        "service": service,
        "symptom": symptom,
        "time_range": {"from": from_time, "to": to_time},
        "sources_analyzed": target_sources,
        "error_count": len(error_entries),
        "timeline": timeline,
        "likely_causes": causes,
    }


def _build_timeline(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort entries into a chronological timeline."""
    sorted_entries = sorted(entries, key=lambda e: e["entry"].timestamp)
    return [
        {
            "timestamp": e["entry"].timestamp,
            "source": e["source"],
            "level": e["entry"].level,
            "service": e["entry"].service,
            "message": e["entry"].message,
        }
        for e in sorted_entries
    ]


def _identify_causes(
    errors: list[dict[str, Any]],
    context: list[dict[str, Any]],
    target_service: str,
    symptom: str,
) -> list[dict[str, Any]]:
    """Rank likely root causes based on heuristics."""
    causes: list[dict[str, Any]] = []

    # Heuristic 1: Upstream service errors before target service errors
    upstream_errors: dict[str, int] = {}
    for err in errors:
        svc = err["entry"].service or "unknown"
        if svc != target_service:
            upstream_errors[svc] = upstream_errors.get(svc, 0) + 1
    for svc, count in sorted(upstream_errors.items(), key=lambda x: -x[1]):
        causes.append(
            {
                "cause": f"Errors in upstream service '{svc}'",
                "confidence": min(0.5 + count * 0.05, 0.95),
                "evidence": f"{count} error(s) from {svc} during incident window",
            }
        )

    # Heuristic 2: Specific error messages recurring
    message_counts: dict[str, int] = {}
    for err in errors:
        msg = err["entry"].message
        message_counts[msg] = message_counts.get(msg, 0) + 1
    for msg, count in sorted(message_counts.items(), key=lambda x: -x[1])[:3]:
        causes.append(
            {
                "cause": f"Recurring error: {msg[:80]}",
                "confidence": min(0.4 + count * 0.05, 0.9),
                "evidence": f"{count} occurrence(s)",
            }
        )

    # Heuristic 3: Check for DB/connection/timeout keywords
    keywords = ["timeout", "connection", "database", "db", "refused", "unavailable"]
    keyword_hits: dict[str, int] = {}
    for err in errors:
        msg_lower = err["entry"].message.lower()
        for kw in keywords:
            if kw in msg_lower:
                keyword_hits[kw] = keyword_hits.get(kw, 0) + 1
    for kw, count in sorted(keyword_hits.items(), key=lambda x: -x[1]):
        causes.append(
            {
                "cause": f"Infrastructure issue: '{kw}' detected",
                "confidence": min(0.45 + count * 0.05, 0.85),
                "evidence": f"{count} error(s) mention '{kw}'",
            }
        )

    # Heuristic 4: Warn-level spikes before errors (causality)
    warn_count = sum(
        1 for c in context if c["entry"].level in ("WARN", "WARNING")
    )
    if warn_count > len(errors):
        causes.append(
            {
                "cause": "Warning spike preceding errors",
                "confidence": 0.6,
                "evidence": f"{warn_count} warnings vs {len(errors)} errors",
            }
        )

    # Sort by confidence descending, deduplicate
    seen: set[str] = set()
    unique_causes: list[dict[str, Any]] = []
    for cause in sorted(causes, key=lambda c: -c["confidence"]):
        key = cause["cause"]
        if key not in seen:
            seen.add(key)
            unique_causes.append(cause)

    return unique_causes[:5]


def _dict_to_tr(time_range: dict[str, str] | None):
    """Convert a raw dict to a TimeRange model."""
    from logintel.models.common import TimeRange

    if not time_range:
        return None
    return TimeRange(
        from_time=time_range.get("from", "now-1h"),
        to_time=time_range.get("to"),
    )
