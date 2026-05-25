"""Grafana Loki provider for LogIntel."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

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

logger = logging.getLogger("logintel.providers.loki")


class LokiProvider(LogProvider):
    """Provider for querying Grafana Loki logs via HTTP API."""

    def __init__(self, source_id: str, config: SourceConfig) -> None:
        self._id = source_id
        self._url: str = getattr(config, "url", "http://localhost:3100")
        self._username: str | None = getattr(config, "basicAuth", {}).get("username") or getattr(
            config, "basic_auth", {}
        ).get("username")
        self._password: str | None = getattr(config, "basicAuth", {}).get("password") or getattr(
            config, "basic_auth", {}
        ).get("password")
        self._tenant_id: str | None = getattr(config, "tenantId", None) or getattr(
            config, "tenant_id", None
        )
        self._default_labels: dict[str, str] = (
            getattr(config, "defaultLabels", {}) or getattr(config, "default_labels", {}) or {}
        )
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return "loki"

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the httpx client with Loki base URL and auth."""
        if self._client is not None:
            return self._client

        headers: dict[str, str] = {}
        if self._tenant_id:
            headers["X-Scope-OrgID"] = self._tenant_id

        auth = None
        if self._username and self._password:
            auth = httpx.BasicAuth(self._username, self._password)

        self._client = httpx.AsyncClient(
            base_url=self._url, headers=headers, auth=auth, timeout=30.0
        )
        return self._client

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    @staticmethod
    def _to_ns(value: str) -> int:
        """Convert a time string to nanoseconds since epoch."""
        dt = parse_relative_time(value)
        return int(dt.timestamp() * 1_000_000_000)

    def _build_label_selector(self, extra_labels: dict[str, str] | None = None) -> str:
        """Build a LogQL label selector from default + extra labels."""
        labels = dict(self._default_labels)
        if extra_labels:
            labels.update(extra_labels)
        if not labels:
            return "{}"
        pairs = [f'{k}="{v}"' for k, v in labels.items()]
        return "{" + ",".join(pairs) + "}"

    @staticmethod
    def _build_search_logql(params: SearchParams, selector: str) -> str:
        """Build a LogQL query for search (line contains)."""
        query = params.query.strip()
        if query:
            escaped = query.replace('"', '\\"')
            return f'{selector} |= "{escaped}"'
        return selector

    @staticmethod
    def _build_filter_logql(params: FilterParams, selector: str) -> str:
        """Build a LogQL query from structured filters."""
        labels: dict[str, str] = {}

        if params.level:
            labels["level"] = params.level.lower()
        if params.service:
            labels["service"] = params.service
        if params.host:
            labels["host"] = params.host

        if labels:
            inner = ",".join(f'{k}="{v}"' for k, v in labels.items())
            base = "{" + inner + "}"
        else:
            base = selector

        filters: list[str] = []
        for key, value in params.custom_fields.items():
            filters.append(f'| {key}="{value}"')
        if params.trace_id:
            filters.append(f'| trace_id="{params.trace_id}"')

        if filters:
            return f"{base} | json " + " ".join(filters)

        return base

    def _build_aggregate_logql(self, params: AggregateParams, selector: str) -> str:
        """Build a LogQL metric query for aggregation."""
        bucket = params.time_bucket or "5m"

        metric = params.metric.lower()
        if metric in ("avg", "average"):
            func = "avg_over_time"
        elif metric == "sum":
            func = "sum_over_time"
        elif metric == "min":
            func = "min_over_time"
        elif metric == "max":
            func = "max_over_time"
        else:
            func = "count_over_time"

        if func == "count_over_time":
            expr = f"{func}({selector}[{bucket}])"
        else:
            expr = f"{func}({selector}[{bucket}])"

        if params.group_by:
            group_fields = []
            for field in params.group_by:
                if field == "timestamp_bucket":
                    continue
                group_fields.append(field)
            if group_fields:
                expr = f"sum by ({','.join(group_fields)}) ({expr})"

        return expr

    # ------------------------------------------------------------------
    # Result parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_stream_results(data: dict[str, Any]) -> list[LogEntry]:
        """Parse Loki streams response into LogEntry objects."""
        entries: list[LogEntry] = []
        results = data.get("data", {}).get("result", [])

        for stream in results:
            stream_labels = stream.get("stream", {})
            for ts_ns, line in stream.get("values", []):
                ts_sec = int(ts_ns) / 1_000_000_000
                dt = datetime.fromtimestamp(ts_sec, tz=UTC)
                timestamp = dt.isoformat().replace("+00:00", "Z")

                message = line
                level = "UNKNOWN"
                service = stream_labels.get("service")
                host = stream_labels.get("host")
                trace_id = None
                fields: dict[str, Any] = dict(stream_labels)

                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        message = str(parsed.get("message", parsed.get("msg", line)))
                        level = str(parsed.get("level", parsed.get("severity", "UNKNOWN"))).upper()
                        service = parsed.get("service", service)
                        host = parsed.get("host", host)
                        trace_id = parsed.get("trace_id") or parsed.get("traceId")
                        for k, v in parsed.items():
                            if k not in (
                                "message",
                                "msg",
                                "level",
                                "severity",
                                "service",
                                "host",
                                "trace_id",
                                "traceId",
                                "span_id",
                                "spanId",
                                "timestamp",
                            ):
                                fields[k] = v
                except Exception:
                    pass

                entries.append(
                    LogEntry(
                        timestamp=timestamp,
                        level=level,
                        message=message,
                        service=service,
                        host=host,
                        trace_id=str(trace_id) if trace_id else None,
                        source="loki",
                        fields=fields,
                        raw={"stream": stream_labels, "line": line},
                    )
                )

        return entries

    @staticmethod
    def _parse_metric_results(data: dict[str, Any]) -> AggregateResult:
        """Parse Loki metric (vector/matrix) response into AggregateResult."""
        buckets: list[AggregateBucket] = []
        total = 0

        result_data = data.get("data", {})
        results = result_data.get("result", [])
        result_type = result_data.get("resultType", "")

        if result_type == "vector":
            for item in results:
                metric = item.get("metric", {})
                value = item.get("value", [0, "0"])
                try:
                    val = float(value[1])
                except (ValueError, TypeError, IndexError):
                    val = 0.0
                count = int(val) if val == int(val) else 1
                buckets.append(AggregateBucket(key=dict(metric), value=val, count=count))
                total += count

        elif result_type == "matrix":
            for item in results:
                metric = item.get("metric", {})
                values = item.get("values", [])
                if values:
                    try:
                        val = sum(float(v[1]) for v in values)
                    except (ValueError, TypeError, IndexError):
                        val = 0.0
                    count = len(values)
                    buckets.append(AggregateBucket(key=dict(metric), value=val, count=count))
                    total += count

        return AggregateResult(buckets=buckets, total=total)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _time_range_ns(self, params_time_range: Any | None) -> tuple[int, int]:
        """Build start/end nanoseconds from optional TimeRange."""
        if params_time_range:
            start = self._to_ns(params_time_range.from_time)
            end = (
                self._to_ns(params_time_range.to_time)
                if params_time_range.to_time
                else self._to_ns("now")
            )
        else:
            start = self._to_ns("now-1h")
            end = self._to_ns("now")
        return start, end

    # ------------------------------------------------------------------
    # LogProvider interface
    # ------------------------------------------------------------------

    async def health(self) -> HealthStatus:
        """Check Loki readiness endpoint."""
        try:
            client = self._get_client()
            resp = await client.get("/ready")
            if resp.status_code == 200:
                return HealthStatus(
                    source=self._id,
                    status="healthy",
                    message="Connected to Loki",
                )
            return HealthStatus(
                source=self._id,
                status="degraded",
                message=f"Loki returned status {resp.status_code}",
            )
        except Exception:
            logger.exception("Loki health check failed for source '%s'", self._id)
            return HealthStatus(
                source=self._id,
                status="unhealthy",
                message="Loki connection failed",
            )

    async def search(self, params: SearchParams) -> SearchResult:
        """Search logs using LogQL line filter."""
        try:
            client = self._get_client()
            selector = self._build_label_selector()
            query = self._build_search_logql(params, selector)
            start, end = self._time_range_ns(params.time_range)

            resp = await client.get(
                "/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": start,
                    "end": end,
                    "limit": min(params.limit, 1000),
                    "direction": "backward",
                },
            )
            resp.raise_for_status()
            result_data = resp.json()
            entries = self._parse_stream_results(result_data)
            return SearchResult(entries=entries, total=len(entries))
        except Exception:
            logger.exception("Loki search failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def filter(self, params: FilterParams) -> SearchResult:
        """Filter logs using structured criteria via LogQL."""
        try:
            client = self._get_client()
            selector = self._build_label_selector()
            query = self._build_filter_logql(params, selector)
            start, end = self._time_range_ns(params.time_range)

            resp = await client.get(
                "/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": start,
                    "end": end,
                    "limit": min(params.limit, 1000),
                    "direction": "backward",
                },
            )
            resp.raise_for_status()
            result_data = resp.json()
            entries = self._parse_stream_results(result_data)
            return SearchResult(entries=entries, total=len(entries))
        except Exception:
            logger.exception("Loki filter failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def aggregate(self, params: AggregateParams) -> AggregateResult:
        """Aggregate logs using LogQL metric queries."""
        try:
            client = self._get_client()
            selector = self._build_label_selector()
            query = self._build_aggregate_logql(params, selector)
            start, end = self._time_range_ns(params.time_range)

            resp = await client.get(
                "/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": start,
                    "end": end,
                    "limit": min(params.limit, 1000),
                },
            )
            resp.raise_for_status()
            result_data = resp.json()
            return self._parse_metric_results(result_data)
        except Exception:
            logger.exception("Loki aggregate failed for source '%s'", self._id)
            return AggregateResult(buckets=[], total=0)

    async def tail(self, params: TailParams) -> SearchResult:
        """Tail recent logs from Loki (last 5 minutes)."""
        try:
            client = self._get_client()
            selector = self._build_label_selector()

            if params.filter_query:
                escaped = params.filter_query.replace('"', '\\"')
                query = f'{selector} |= "{escaped}"'
            else:
                query = selector

            start = self._to_ns("now-5m")
            end = self._to_ns("now")

            resp = await client.get(
                "/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": start,
                    "end": end,
                    "limit": min(params.lines, 1000),
                    "direction": "backward",
                },
            )
            resp.raise_for_status()
            result_data = resp.json()
            entries = self._parse_stream_results(result_data)
            return SearchResult(entries=entries, total=len(entries))
        except Exception:
            logger.exception("Loki tail failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def get_schema(self) -> SchemaInfo:
        """Return schema info, discovering labels from Loki."""
        fields = [
            SchemaField(name="timestamp", type="timestamp", required=True),
            SchemaField(name="message", type="string", required=True),
            SchemaField(name="level", type="string", required=False),
            SchemaField(name="service", type="string", required=False),
            SchemaField(name="host", type="string", required=False),
        ]

        try:
            client = self._get_client()
            resp = await client.get("/loki/api/v1/labels")
            if resp.status_code == 200:
                result_data = resp.json()
                labels = result_data.get("data", [])
                for label in labels:
                    if label not in ("timestamp", "message", "level", "service", "host"):
                        fields.append(SchemaField(name=label, type="string", required=False))

                sample_resp = await client.get(
                    "/loki/api/v1/query_range",
                    params={
                        "query": self._build_label_selector(),
                        "start": self._to_ns("now-5m"),
                        "end": self._to_ns("now"),
                        "limit": 1,
                        "direction": "backward",
                    },
                )
                if sample_resp.status_code == 200:
                    sample_data = sample_resp.json()
                    entries = self._parse_stream_results(sample_data)
                    if entries:
                        return SchemaInfo(
                            source=self._id,
                            fields=fields,
                            known_formats=["json", "logfmt"],
                            sample_log=entries[0],
                        )
        except Exception:
            logger.exception("Loki schema discovery failed for source '%s'", self._id)

        return SchemaInfo(
            source=self._id,
            fields=fields,
            known_formats=["json", "logfmt"],
        )

    async def detect_patterns(self, params: PatternParams) -> PatternResult:
        # Phase 5 intelligence — return empty for now
        return PatternResult(patterns=[], total_errors=0)

    async def find_anomalies(self, params: AnomalyParams) -> AnomalyResult:
        # Phase 5 intelligence — return empty for now
        return AnomalyResult(anomalies=[], metric=params.metric)
