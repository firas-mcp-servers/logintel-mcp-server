"""Cross-source log correlation engine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from logintel.models.common import LogEntry
from logintel.models.params import FilterParams, SearchParams
from logintel.providers.registry import ProviderRegistry

logger = logging.getLogger("logintel.intelligence.correlator")


class CorrelatedGroup:
    """A group of correlated log entries."""

    def __init__(self, correlation_key: str, correlation_type: str) -> None:
        self.correlation_key = correlation_key
        self.correlation_type = correlation_type
        self.entries: list[LogEntry] = []
        self.score = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_key": self.correlation_key,
            "correlation_type": self.correlation_type,
            "score": round(self.score, 2),
            "entries": [e.model_dump(by_alias=True) for e in self.entries],
        }


async def correlate_across_sources(
    registry: ProviderRegistry,
    sources: list[str],
    time_range: dict[str, str] | None,
    trace_id: str | None = None,
    service: str | None = None,
    correlation_window: str = "5m",
    limit: int = 100,
) -> dict[str, Any]:
    """Correlate logs across multiple sources by trace ID or timestamp proximity."""
    groups: list[CorrelatedGroup] = []
    total_entries = 0

    # 1. Trace ID correlation (most accurate)
    if trace_id:
        trace_group = CorrelatedGroup(trace_id, "trace_id")
        for source_id in sources:
            try:
                provider = registry.get(source_id)
                params = FilterParams(
                    source=source_id,
                    time_range=_dict_to_tr(time_range),
                    trace_id=trace_id,
                    limit=limit,
                )
                result = await provider.filter(params)
                trace_group.entries.extend(result.entries)
                total_entries += len(result.entries)
            except Exception:
                logger.exception("Correlation search failed for source '%s'", source_id)

        if trace_group.entries:
            trace_group.score = 1.0
            groups.append(trace_group)

    # 2. Service + timestamp proximity correlation
    if service or not trace_id:
        all_entries: list[LogEntry] = []
        for source_id in sources:
            try:
                provider = registry.get(source_id)
                params = SearchParams(
                    source=source_id,
                    query="",
                    time_range=_dict_to_tr(time_range),
                    limit=limit,
                )
                result = await provider.search(params)
                all_entries.extend(result.entries)
                total_entries += len(result.entries)
            except Exception:
                logger.exception("Correlation search failed for source '%s'", source_id)

        if all_entries:
            window_td = _parse_window(correlation_window)
            time_groups = _group_by_time_proximity(all_entries, window_td, service)
            groups.extend(time_groups)

    # Sort by score descending
    groups.sort(key=lambda g: g.score, reverse=True)

    return {
        "groups": [g.to_dict() for g in groups],
        "total_entries": total_entries,
        "sources_queried": sources,
    }


def _group_by_time_proximity(
    entries: list[LogEntry], window: timedelta, service_filter: str | None
) -> list[CorrelatedGroup]:
    """Group entries by timestamp proximity."""
    if not entries:
        return []

    # Filter by service if specified
    if service_filter:
        entries = [e for e in entries if e.service == service_filter]

    if not entries:
        return []

    # Sort by timestamp
    sorted_entries = sorted(entries, key=lambda e: e.timestamp)

    groups: list[CorrelatedGroup] = []
    current_group: list[LogEntry] = [sorted_entries[0]]

    for i in range(1, len(sorted_entries)):
        prev_ts = datetime.fromisoformat(sorted_entries[i - 1].timestamp.replace("Z", "+00:00"))
        curr_ts = datetime.fromisoformat(sorted_entries[i].timestamp.replace("Z", "+00:00"))
        if curr_ts - prev_ts <= window:
            current_group.append(sorted_entries[i])
        else:
            groups.append(_make_time_group(current_group))
            current_group = [sorted_entries[i]]

    if current_group:
        groups.append(_make_time_group(current_group))

    return groups


def _make_time_group(entries: list[LogEntry]) -> CorrelatedGroup:
    """Create a CorrelatedGroup from a list of time-proximate entries."""
    min_ts = min(e.timestamp for e in entries)
    max_ts = max(e.timestamp for e in entries)
    key = f"{min_ts} to {max_ts}"
    group = CorrelatedGroup(key, "timestamp_proximity")
    group.entries = entries
    # Score based on error density
    error_count = sum(1 for e in entries if e.level in ("ERROR", "WARN", "WARNING"))
    group.score = min(error_count / max(len(entries), 1) + 0.1, 1.0)
    return group


def _parse_window(window: str) -> timedelta:
    """Parse a correlation window like '5m', '10m', '1h'."""
    value = int("".join(c for c in window if c.isdigit()) or "5")
    unit = "".join(c for c in window if not c.isdigit())
    if unit == "h":
        return timedelta(hours=value)
    if unit == "s":
        return timedelta(seconds=value)
    return timedelta(minutes=value)


def _dict_to_tr(time_range: dict[str, str] | None):
    """Convert a raw dict to a TimeRange model."""
    from logintel.models.common import TimeRange

    if not time_range:
        return None
    return TimeRange(
        from_time=time_range.get("from", "now-1h"),
        to_time=time_range.get("to"),
    )
