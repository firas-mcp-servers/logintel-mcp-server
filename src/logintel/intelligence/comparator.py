"""Time-period comparison engine."""

from __future__ import annotations

import logging
from typing import Any

from logintel.models.params import SearchParams
from logintel.models.results import SearchResult
from logintel.providers.base import LogProvider

logger = logging.getLogger("logintel.intelligence.comparator")


async def compare_periods(
    provider: LogProvider,
    source: str,
    baseline_range: dict[str, str],
    comparison_range: dict[str, str],
    query: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    """Compare logs between two time windows (baseline vs comparison)."""
    # Fetch baseline
    baseline = await _fetch_period(provider, source, baseline_range, query, limit)
    # Fetch comparison
    comparison = await _fetch_period(provider, source, comparison_range, query, limit)

    baseline_stats = _compute_stats(baseline)
    comparison_stats = _compute_stats(comparison)

    diff = {
        "total_count": {
            "baseline": baseline_stats["total"],
            "comparison": comparison_stats["total"],
            "change": _pct_change(baseline_stats["total"], comparison_stats["total"]),
        },
        "error_count": {
            "baseline": baseline_stats["errors"],
            "comparison": comparison_stats["errors"],
            "change": _pct_change(baseline_stats["errors"], comparison_stats["errors"]),
        },
        "error_rate": {
            "baseline": round(baseline_stats["error_rate"], 4),
            "comparison": round(comparison_stats["error_rate"], 4),
            "change": round(comparison_stats["error_rate"] - baseline_stats["error_rate"], 4),
        },
        "top_messages_baseline": baseline_stats["top_messages"],
        "top_messages_comparison": comparison_stats["top_messages"],
        "services_baseline": baseline_stats["services"],
        "services_comparison": comparison_stats["services"],
        "new_messages": _find_new_items(
            baseline_stats["message_set"], comparison_stats["message_set"]
        ),
        "disappeared_messages": _find_new_items(
            comparison_stats["message_set"], baseline_stats["message_set"]
        ),
    }

    return {
        "source": source,
        "baseline_range": baseline_range,
        "comparison_range": comparison_range,
        "diff": diff,
        "summary": _generate_summary(diff),
    }


async def _fetch_period(
    provider: LogProvider,
    source: str,
    time_range: dict[str, str],
    query: str,
    limit: int,
) -> SearchResult:
    """Fetch logs for a single time period."""
    try:
        from logintel.models.common import TimeRange

        tr = TimeRange(
            from_time=time_range.get("from", "now-1h"),
            to_time=time_range.get("to"),
        )
        params = SearchParams(source=source, query=query, time_range=tr, limit=limit)
        return await provider.search(params)
    except Exception:
        logger.exception("Failed to fetch period for source '%s'", source)
        return SearchResult(entries=[], total=0)


def _compute_stats(result: SearchResult) -> dict[str, Any]:
    """Compute statistics from a SearchResult."""
    entries = result.entries
    total = len(entries)
    errors = sum(1 for e in entries if e.level in ("ERROR", "WARN", "WARNING"))
    error_rate = errors / max(total, 1)

    message_counts: dict[str, int] = {}
    service_counts: dict[str, int] = {}
    for e in entries:
        message_counts[e.message] = message_counts.get(e.message, 0) + 1
        svc = e.service or "unknown"
        service_counts[svc] = service_counts.get(svc, 0) + 1

    top_messages = sorted(message_counts.items(), key=lambda x: -x[1])[:5]
    top_services = sorted(service_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "total": total,
        "errors": errors,
        "error_rate": error_rate,
        "top_messages": [{"message": m, "count": c} for m, c in top_messages],
        "services": [{"service": s, "count": c} for s, c in top_services],
        "message_set": set(message_counts.keys()),
    }


def _pct_change(baseline: int, comparison: int) -> float:
    """Calculate percentage change."""
    if baseline == 0:
        return float("inf") if comparison > 0 else 0.0
    return round((comparison - baseline) / baseline * 100, 2)


def _find_new_items(base_set: set[str], compare_set: set[str]) -> list[str]:
    """Find items in compare_set that are not in base_set."""
    return sorted(compare_set - base_set)


def _generate_summary(diff: dict[str, Any]) -> str:
    """Generate a natural-language summary of the comparison."""
    parts: list[str] = []
    total_change = diff["total_count"]["change"]
    error_change = diff["error_count"]["change"]

    if total_change == float("inf"):
        parts.append("Log volume went from zero to present.")
    elif total_change > 50:
        parts.append(f"Log volume increased by {total_change}%.")
    elif total_change < -50:
        parts.append(f"Log volume decreased by {abs(total_change)}%.")
    else:
        parts.append("Log volume is relatively stable.")

    if error_change == float("inf"):
        parts.append("Errors went from zero to present.")
    elif error_change > 50:
        parts.append(f"Errors increased by {error_change}%.")
    elif error_change < -50:
        parts.append(f"Errors decreased by {abs(error_change)}%.")
    else:
        parts.append("Error rate is relatively stable.")

    new_msgs = diff["new_messages"]
    if new_msgs:
        parts.append(f"New messages appeared: {', '.join(new_msgs[:3])}.")

    return " ".join(parts)
