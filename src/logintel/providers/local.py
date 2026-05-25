"""Local file system log provider."""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from logintel.config import SourceConfig
from logintel.models.common import HealthStatus, LogEntry, SchemaField, SchemaInfo
from logintel.models.params import (
    AggregateParams,
    AnomalyParams,
    FilterParams,
    PatternParams,
    SearchParams,
    TailParams,
)
from logintel.models.results import (
    AggregateBucket,
    AggregateResult,
    AnomalyResult,
    PatternResult,
    SearchResult,
)
from logintel.providers.base import LogProvider
from logintel.utils.time_parser import parse_relative_time

logger = logging.getLogger("logintel.providers.local")


class LocalFileProvider(LogProvider):
    """Provider for reading logs from local files."""

    def __init__(self, source_id: str, config: SourceConfig) -> None:
        self._id = source_id
        self._config = config
        self._paths: list[str] = getattr(config, "paths", [])
        self._parse_json: bool = getattr(config, "parseJson", False)
        self._timestamp_field: str = getattr(config, "timestampField", "timestamp")
        self._level_field: str = getattr(config, "levelField", "level")
        self._service_field: str = getattr(config, "serviceField", "service")
        self._host_field: str | None = getattr(config, "hostField", None)
        self._message_field: str | None = getattr(config, "messageField", None)
        self._regex_pattern: str | None = getattr(config, "regexPattern", None)
        self._regex: re.Pattern | None = None
        if self._regex_pattern:
            self._regex = re.compile(self._regex_pattern)

        # Resolve allowed paths for sandboxing
        self._allowed_paths = self._resolve_allowed_paths()

    def _resolve_allowed_paths(self) -> list[Path]:
        """Resolve all configured paths to absolute paths for sandboxing."""
        resolved = []
        for pattern in self._paths:
            for path_str in glob.glob(pattern, recursive=True):
                path = Path(path_str).resolve()
                resolved.append(path)
            # Also resolve the parent directory of the glob pattern
            # so new files that match are accessible
            glob_path = Path(pattern).expanduser()
            if glob_path.is_absolute():
                parent = glob_path.parent.resolve()
                if parent.exists():
                    resolved.append(parent)
        return list(dict.fromkeys(resolved))  # deduplicate while preserving order

    def _is_path_allowed(self, path: Path) -> bool:
        """Check if a path is within the allowed sandbox."""
        resolved = path.resolve()
        for allowed in self._allowed_paths:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False

    def _discover_files(self) -> list[Path]:
        """Discover all log files matching configured paths."""
        files = []
        for pattern in self._paths:
            for path_str in glob.glob(pattern, recursive=True):
                path = Path(path_str)
                if path.is_file() and self._is_path_allowed(path):
                    files.append(path)
        return sorted(set(files))

    def _parse_line(self, line: str, source: str) -> LogEntry | None:
        """Parse a single log line into a LogEntry."""
        line = line.strip()
        if not line:
            return None

        # Try JSON parsing first if enabled
        if self._parse_json:
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return self._build_entry_from_dict(data, source, raw=data)
            except json.JSONDecodeError:
                pass

        # Try regex pattern if configured
        if self._regex:
            match = self._regex.match(line)
            if match:
                return self._build_entry_from_dict(match.groupdict(), source, raw=line)

        # Fallback: plain text line
        return LogEntry(
            timestamp=datetime.now(UTC).isoformat(),
            level="UNKNOWN",
            message=line,
            source=source,
        )

    def _build_entry_from_dict(self, data: dict[str, Any], source: str, raw: Any) -> LogEntry:
        """Build a LogEntry from a dictionary (JSON or regex groups)."""
        timestamp = str(data.get(self._timestamp_field, datetime.now(UTC).isoformat()))
        level = str(data.get(self._level_field, "UNKNOWN")).upper()
        service = data.get(self._service_field)
        host = data.get(self._host_field) if self._host_field else None

        # Determine message
        if self._message_field and self._message_field in data:
            message = str(data[self._message_field])
        else:
            # Try common message fields
            for key in ("message", "msg", "log", "text", "body"):
                if key in data:
                    message = str(data[key])
                    break
            else:
                message = str(data)

        # Extract trace_id and span_id if present
        trace_id = data.get("trace_id") or data.get("traceId")
        span_id = data.get("span_id") or data.get("spanId")

        # Remaining fields go into 'fields'
        known_fields = {
            self._timestamp_field,
            self._level_field,
            self._service_field,
            self._host_field,
            self._message_field,
            "trace_id",
            "traceId",
            "span_id",
            "spanId",
        }
        extra_fields = {k: v for k, v in data.items() if k not in known_fields and v is not None}

        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=message,
            service=str(service) if service else None,
            host=str(host) if host else None,
            trace_id=str(trace_id) if trace_id else None,
            span_id=str(span_id) if span_id else None,
            source=source,
            fields=extra_fields,
            raw=raw,
        )

    def _parse_timestamp(self, value: str) -> datetime | None:
        """Try to parse a timestamp string."""
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    def _line_matches_time_range(
        self, entry: LogEntry, from_time: datetime | None, to_time: datetime | None
    ) -> bool:
        """Check if a log entry falls within a time range."""
        if from_time is None and to_time is None:
            return True
        ts = self._parse_timestamp(entry.timestamp)
        if ts is None:
            return True  # If we can't parse, include it
        if from_time and ts < from_time:
            return False
        return not (to_time and ts > to_time)

    def _line_matches_search(self, entry: LogEntry, query: str) -> bool:
        """Check if a log entry matches a search query (case-insensitive substring)."""
        q = query.lower()
        if q in entry.message.lower():
            return True
        if entry.service and q in entry.service.lower():
            return True
        if entry.host and q in entry.host.lower():
            return True
        if entry.level.lower() == q:
            return True
        # Search in extra fields
        return any(isinstance(v, str) and q in v.lower() for v in entry.fields.values())

    def _line_matches_filter(self, entry: LogEntry, params: FilterParams) -> bool:
        """Check if a log entry matches structured filter criteria."""
        if params.level and entry.level.upper() != params.level.upper():
            return False
        if params.service and (not entry.service or entry.service != params.service):
            return False
        if params.host and (not entry.host or entry.host != params.host):
            return False
        if params.trace_id and entry.trace_id != params.trace_id:
            return False
        for key, value in params.custom_fields.items():
            if key not in entry.fields or str(entry.fields[key]) != str(value):
                return False
        return True

    def _read_entries(
        self,
        files: list[Path],
        source: str,
        limit: int = 1000,
        offset: int | None = None,
    ) -> list[LogEntry]:
        """Read and parse log entries from files."""
        entries = []
        skip = offset or 0
        for file_path in files:
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        entry = self._parse_line(line, source)
                        if entry:
                            if skip > 0:
                                skip -= 1
                                continue
                            entries.append(entry)
                            if len(entries) >= limit:
                                return entries
            except OSError as exc:
                logger.warning("Failed to read %s: %s", file_path, exc)
        return entries

    def _read_entries_reverse(
        self,
        files: list[Path],
        source: str,
        limit: int = 1000,
    ) -> list[LogEntry]:
        """Read entries in reverse order (newest first) for tail operations."""
        all_entries = []
        for file_path in files:
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        entry = self._parse_line(line, source)
                        if entry:
                            all_entries.append(entry)
            except OSError as exc:
                logger.warning("Failed to read %s: %s", file_path, exc)
        return all_entries[-limit:]

    # ------------------------------------------------------------------
    # LogProvider interface
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return "local"

    async def health(self) -> HealthStatus:
        files = self._discover_files()
        if not files:
            return HealthStatus(
                source=self._id,
                status="degraded",
                message=f"No files found for patterns: {self._paths}",
            )
        unreadable = [str(f) for f in files if not os.access(f, os.R_OK)]
        if unreadable:
            return HealthStatus(
                source=self._id,
                status="degraded",
                message=f"Found {len(files)} files, {len(unreadable)} unreadable",
            )
        return HealthStatus(
            source=self._id,
            status="healthy",
            message=f"Found {len(files)} readable file(s)",
        )

    async def search(self, params: SearchParams) -> SearchResult:
        files = self._discover_files()
        from_time = to_time = None
        if params.time_range:
            from_time = parse_relative_time(params.time_range.from_time)
            if params.time_range.to_time:
                to_time = parse_relative_time(params.time_range.to_time)

        entries = []
        offset = int(params.offset) if params.offset else 0
        limit = params.limit

        for file_path in files:
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        entry = self._parse_line(line, self._id)
                        if not entry:
                            continue
                        if not self._line_matches_time_range(entry, from_time, to_time):
                            continue
                        if not self._line_matches_search(entry, params.query):
                            continue
                        if offset > 0:
                            offset -= 1
                            continue
                        entries.append(entry)
                        if len(entries) >= limit:
                            next_offset = str(offset + limit) if offset else str(limit)
                            return SearchResult(
                                entries=entries,
                                total=None,
                                next_offset=next_offset,
                            )
            except OSError as exc:
                logger.warning("Failed to read %s: %s", file_path, exc)

        return SearchResult(entries=entries, total=len(entries))

    async def filter(self, params: FilterParams) -> SearchResult:
        files = self._discover_files()
        from_time = to_time = None
        if params.time_range:
            from_time = parse_relative_time(params.time_range.from_time)
            if params.time_range.to_time:
                to_time = parse_relative_time(params.time_range.to_time)

        entries = []
        offset = int(params.offset) if params.offset else 0
        limit = params.limit

        for file_path in files:
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        entry = self._parse_line(line, self._id)
                        if not entry:
                            continue
                        if not self._line_matches_time_range(entry, from_time, to_time):
                            continue
                        if not self._line_matches_filter(entry, params):
                            continue
                        if offset > 0:
                            offset -= 1
                            continue
                        entries.append(entry)
                        if len(entries) >= limit:
                            next_offset = str(offset + limit) if offset else str(limit)
                            return SearchResult(
                                entries=entries,
                                total=None,
                                next_offset=next_offset,
                            )
            except OSError as exc:
                logger.warning("Failed to read %s: %s", file_path, exc)

        return SearchResult(entries=entries, total=len(entries))

    async def aggregate(self, params: AggregateParams) -> AggregateResult:
        files = self._discover_files()
        from_time = to_time = None
        if params.time_range:
            from_time = parse_relative_time(params.time_range.from_time)
            if params.time_range.to_time:
                to_time = parse_relative_time(params.time_range.to_time)

        # Collect all matching entries
        entries = []
        for file_path in files:
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        entry = self._parse_line(line, self._id)
                        if entry and self._line_matches_time_range(entry, from_time, to_time):
                            entries.append(entry)
            except OSError as exc:
                logger.warning("Failed to read %s: %s", file_path, exc)

        # Bucket entries
        buckets: dict[str, dict[str, Any]] = {}
        for entry in entries:
            key_parts = {}
            for field in params.group_by:
                if field == "level":
                    key_parts[field] = entry.level
                elif field == "service":
                    key_parts[field] = entry.service or "unknown"
                elif field == "host":
                    key_parts[field] = entry.host or "unknown"
                elif field == "timestamp_bucket":
                    # Time bucketing handled separately
                    continue
                elif field in entry.fields:
                    key_parts[field] = str(entry.fields[field])
                else:
                    key_parts[field] = "unknown"

            # Handle time bucketing
            if params.time_bucket:
                ts = self._parse_timestamp(entry.timestamp)
                if ts:
                    bucket_ts = self._bucket_timestamp(ts, params.time_bucket)
                    key_parts["timestamp_bucket"] = bucket_ts

            key_str = json.dumps(key_parts, sort_keys=True)
            if key_str not in buckets:
                buckets[key_str] = {"key": key_parts, "values": [], "count": 0}
            buckets[key_str]["count"] += 1

            # Collect values for numeric metrics
            if params.metric != "count" and params.field:
                val = self._extract_numeric(entry, params.field)
                if val is not None:
                    buckets[key_str]["values"].append(val)

        # Build result buckets
        result_buckets = []
        for bucket in buckets.values():
            if params.metric == "count":
                value = float(bucket["count"])
            elif params.metric in ("avg", "average"):
                vals = bucket["values"]
                value = sum(vals) / len(vals) if vals else 0.0
            elif params.metric == "sum":
                value = sum(bucket["values"])
            elif params.metric == "min":
                value = min(bucket["values"]) if bucket["values"] else 0.0
            elif params.metric == "max":
                value = max(bucket["values"]) if bucket["values"] else 0.0
            else:
                value = float(bucket["count"])

            result_buckets.append(
                AggregateBucket(key=bucket["key"], value=value, count=bucket["count"])
            )

        # Sort by count descending, limit
        result_buckets.sort(key=lambda b: b.count, reverse=True)
        result_buckets = result_buckets[: params.limit]

        return AggregateResult(buckets=result_buckets, total=len(entries))

    def _bucket_timestamp(self, ts: datetime, bucket: str) -> str:
        """Round a timestamp to a bucket boundary."""
        # Parse bucket like "1m", "5m", "1h"
        match = re.match(r"^(\d+)([mhd])$", bucket)
        if not match:
            return ts.isoformat()
        num = int(match.group(1))
        unit = match.group(2)
        if unit == "m":
            minute = (ts.minute // num) * num
            return ts.replace(minute=minute, second=0, microsecond=0).isoformat()
        if unit == "h":
            hour = (ts.hour // num) * num
            return ts.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()
        if unit == "d":
            return ts.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        return ts.isoformat()  # pragma: no cover

    def _extract_numeric(self, entry: LogEntry, field: str) -> float | None:
        """Extract a numeric value from a log entry by field name."""
        if field == "level":
            return None
        if field in entry.fields:
            try:
                return float(entry.fields[field])  # type: ignore[arg-type]
            except (ValueError, TypeError):
                return None
        return None

    async def tail(self, params: TailParams) -> SearchResult:
        files = self._discover_files()
        # Read all entries, filter, return last N
        all_entries = []
        for file_path in files:
            try:
                with file_path.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        entry = self._parse_line(line, self._id)
                        if not entry:
                            continue
                        if params.filter_query and not self._line_matches_search(
                            entry, params.filter_query
                        ):
                            continue
                        all_entries.append(entry)
            except OSError as exc:
                logger.warning("Failed to read %s: %s", file_path, exc)

        entries = all_entries[-params.lines :]
        return SearchResult(entries=entries, total=len(entries))

    async def get_schema(self) -> SchemaInfo:
        fields = [
            SchemaField(name="timestamp", type="timestamp", required=True),
            SchemaField(name="level", type="string", required=True),
            SchemaField(name="message", type="string", required=True),
        ]
        if self._service_field:
            fields.append(SchemaField(name="service", type="string", required=False))
        if self._host_field:
            fields.append(SchemaField(name="host", type="string", required=False))

        known_formats = ["json"] if self._parse_json else []
        if self._regex_pattern:
            known_formats.append("regex")

        return SchemaInfo(
            source=self._id,
            fields=fields,
            known_formats=known_formats,
        )

    async def detect_patterns(self, params: PatternParams) -> PatternResult:
        # Phase 5 intelligence — return empty for now
        return PatternResult(patterns=[], total_errors=0)

    async def find_anomalies(self, params: AnomalyParams) -> AnomalyResult:
        # Phase 5 intelligence — return empty for now
        return AnomalyResult(anomalies=[], metric=params.metric)
