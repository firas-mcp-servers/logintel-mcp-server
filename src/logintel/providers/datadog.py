"""Datadog Logs provider for LogIntel."""

from __future__ import annotations

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

logger = logging.getLogger("logintel.providers.datadog")


class DatadogProvider(LogProvider):
    """Provider for querying Datadog Logs."""

    def __init__(self, source_id: str, config: SourceConfig) -> None:
        self._id = source_id
        self._api_key: str = getattr(config, "apiKey", "")
        self._app_key: str = getattr(config, "appKey", "")
        self._site: str = getattr(config, "site", "datadoghq.com")
        self._indexes: list[str] = getattr(config, "defaultIndexes", []) or getattr(
            config, "default_indexes", []
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
        return "datadog"

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the httpx client with Datadog base URL and auth."""
        if self._client is not None:
            return self._client

        base_url = f"https://api.{self._site}"
        headers = {
            "DD-API-KEY": self._api_key,
            "DD-APPLICATION-KEY": self._app_key,
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0)
        return self._client

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_search_query(params: SearchParams) -> str:
        """Build a Datadog Lucene query string for search."""
        return params.query if params.query else "*"

    @staticmethod
    def _build_filter_query(params: FilterParams) -> str:
        """Build a Datadog Lucene query string from structured filters."""
        parts: list[str] = []

        if params.level:
            parts.append(f"status:{params.level.lower()}")
        if params.service:
            parts.append(f"service:{params.service}")
        if params.host:
            parts.append(f"host:{params.host}")
        if params.trace_id:
            parts.append(f"@trace_id:{params.trace_id}")

        for key, value in params.custom_fields.items():
            parts.append(f"@{key}:{value}")

        return " ".join(parts) if parts else "*"

    @staticmethod
    def _build_aggregate_body(params: AggregateParams) -> dict[str, Any]:
        """Build a Datadog Logs Aggregate API request body."""
        metric = params.metric.lower()
        if metric in ("avg", "average"):
            aggregation = "avg"
        elif metric == "sum":
            aggregation = "sum"
        elif metric == "min":
            aggregation = "min"
        elif metric == "max":
            aggregation = "max"
        else:
            aggregation = "count"

        compute: dict[str, Any] = {"aggregation": aggregation}
        if params.field and aggregation != "count":
            compute["metric"] = params.field

        group_by: list[dict[str, Any]] = []
        for field in params.group_by:
            facet = field
            if field == "timestamp_bucket":
                facet = "timestamp"
            elif field == "level":
                facet = "status"
            group_by.append({"facet": facet, "limit": params.limit})

        if not group_by:
            group_by = [{"facet": "timestamp", "limit": params.limit}]

        return {"compute": compute, "group_by": group_by}

    # ------------------------------------------------------------------
    # Result parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_search_results(
        data: list[dict[str, Any]], source_id: str = "datadog"
    ) -> list[LogEntry]:
        """Parse Datadog search response data into LogEntry objects."""
        entries: list[LogEntry] = []
        for item in data:
            attrs = item.get("attributes", {})
            timestamp = attrs.get("timestamp", datetime.now(UTC).isoformat())
            message = attrs.get("message", "")
            level = str(attrs.get("status", "UNKNOWN")).upper()
            service = attrs.get("service")
            host = attrs.get("host")
            tags = attrs.get("tags", [])

            # Extract trace_id from attributes or tags
            trace_id = None
            custom_attrs = attrs.get("attributes", {})
            if isinstance(custom_attrs, dict):
                trace_id = custom_attrs.get("trace_id") or custom_attrs.get("traceId")

            # Build extra fields from custom attributes + tags
            extra: dict[str, Any] = {}
            if isinstance(custom_attrs, dict):
                for k, v in custom_attrs.items():
                    if k not in ("trace_id", "traceId", "span_id", "spanId"):
                        extra[k] = v
            for tag in tags:
                if ":" in tag:
                    k, v = tag.split(":", 1)
                    extra[k] = v

            entries.append(
                LogEntry(
                    timestamp=timestamp,
                    level=level,
                    message=message,
                    service=service,
                    host=host,
                    trace_id=str(trace_id) if trace_id else None,
                    source=source_id,
                    fields=extra,
                    raw=item,
                )
            )
        return entries

    @staticmethod
    def _parse_aggregate_results(data: list[dict[str, Any]]) -> AggregateResult:
        """Parse Datadog aggregate response data into AggregateResult."""
        buckets: list[AggregateBucket] = []
        total = 0

        for item in data:
            by = item.get("by", {})
            aggs = item.get("aggregations", [])

            value = 0.0
            count = 0
            for agg in aggs:
                if "value" in agg:
                    try:
                        value = float(agg["value"])
                        count = int(value) if value == int(value) else 1
                    except (ValueError, TypeError):
                        pass

            buckets.append(AggregateBucket(key=dict(by), value=value, count=count))
            total += count

        return AggregateResult(buckets=buckets, total=total)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_time_filter(
        self, params_time_range: Any | None, default_from: str = "now-1h"
    ) -> dict[str, Any]:
        """Build the filter dict with time range and indexes."""
        filter_dict: dict[str, Any] = {}

        if params_time_range:
            filter_dict["from"] = params_time_range.from_time
            if params_time_range.to_time:
                filter_dict["to"] = params_time_range.to_time
        else:
            filter_dict["from"] = default_from
            filter_dict["to"] = "now"

        if self._indexes:
            filter_dict["indexes"] = self._indexes

        return filter_dict

    @staticmethod
    def _extract_cursor(meta: dict[str, Any]) -> str | None:
        """Extract the next page cursor from response meta."""
        page = meta.get("page", {})
        return page.get("after")

    # ------------------------------------------------------------------
    # LogProvider interface
    # ------------------------------------------------------------------

    async def health(self) -> HealthStatus:
        """Validate Datadog credentials with a minimal search request."""
        if not self._api_key or not self._app_key:
            return HealthStatus(
                source=self._id,
                status="unhealthy",
                message="Datadog API key and/or Application key not configured",
            )

        try:
            client = self._get_client()
            body = {
                "filter": {"from": "now-1m", "to": "now", "query": "*"},
                "page": {"limit": 1},
            }
            resp = await client.post("/api/v2/logs/events/search", json=body)

            if resp.status_code == 200:
                return HealthStatus(
                    source=self._id,
                    status="healthy",
                    message=f"Connected to Datadog ({self._site})",
                )
            if resp.status_code in (401, 403):
                return HealthStatus(
                    source=self._id,
                    status="unhealthy",
                    message=f"Datadog authentication failed ({resp.status_code})",
                )
            return HealthStatus(
                source=self._id,
                status="degraded",
                message=f"Datadog returned status {resp.status_code}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Datadog health check failed for source '%s'", self._id)
            return HealthStatus(
                source=self._id,
                status="unhealthy",
                message=str(exc),
            )

    async def search(self, params: SearchParams) -> SearchResult:
        """Search logs using Datadog Logs Search API."""
        try:
            client = self._get_client()
            filter_dict = self._build_time_filter(params.time_range)
            filter_dict["query"] = self._build_search_query(params)

            body: dict[str, Any] = {
                "filter": filter_dict,
                "sort": "-timestamp",
                "page": {"limit": min(params.limit, 1000)},
            }

            resp = await client.post("/api/v2/logs/events/search", json=body)
            resp.raise_for_status()
            result_data = resp.json()

            entries = self._parse_search_results(result_data.get("data", []), self._id)
            meta = result_data.get("meta", {})
            cursor = self._extract_cursor(meta)

            return SearchResult(
                entries=entries,
                total=len(entries),
                next_offset=cursor,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Datadog search failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def filter(self, params: FilterParams) -> SearchResult:
        """Filter logs using structured criteria via Datadog Search API."""
        try:
            client = self._get_client()
            filter_dict = self._build_time_filter(params.time_range)
            filter_dict["query"] = self._build_filter_query(params)

            body: dict[str, Any] = {
                "filter": filter_dict,
                "sort": "-timestamp",
                "page": {"limit": min(params.limit, 1000)},
            }

            resp = await client.post("/api/v2/logs/events/search", json=body)
            resp.raise_for_status()
            result_data = resp.json()

            entries = self._parse_search_results(result_data.get("data", []), self._id)
            meta = result_data.get("meta", {})
            cursor = self._extract_cursor(meta)

            return SearchResult(
                entries=entries,
                total=len(entries),
                next_offset=cursor,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Datadog filter failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def aggregate(self, params: AggregateParams) -> AggregateResult:
        """Aggregate logs using Datadog Logs Aggregate API."""
        try:
            client = self._get_client()
            agg_body = self._build_aggregate_body(params)
            filter_dict = self._build_time_filter(params.time_range)
            filter_dict["query"] = "*"
            agg_body["filter"] = filter_dict

            resp = await client.post("/api/v2/logs/analytics/aggregate", json=agg_body)
            resp.raise_for_status()
            result_data = resp.json()

            buckets = result_data.get("data", {})
            if isinstance(buckets, dict):
                buckets = buckets.get("buckets", [])
            return self._parse_aggregate_results(buckets)
        except Exception:  # noqa: BLE001
            logger.exception("Datadog aggregate failed for source '%s'", self._id)
            return AggregateResult(buckets=[], total=0)

    async def tail(self, params: TailParams) -> SearchResult:
        """Tail recent logs from Datadog (last 5 minutes)."""
        try:
            client = self._get_client()
            filter_dict = self._build_time_filter(None, default_from="now-5m")
            if params.filter_query:
                filter_dict["query"] = params.filter_query
            else:
                filter_dict["query"] = "*"

            body: dict[str, Any] = {
                "filter": filter_dict,
                "sort": "-timestamp",
                "page": {"limit": min(params.lines, 1000)},
            }

            resp = await client.post("/api/v2/logs/events/search", json=body)
            resp.raise_for_status()
            result_data = resp.json()

            entries = self._parse_search_results(result_data.get("data", []), self._id)
            return SearchResult(entries=entries, total=len(entries))
        except Exception:  # noqa: BLE001
            logger.exception("Datadog tail failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def get_schema(self) -> SchemaInfo:
        """Return schema info for Datadog Logs fields."""
        fields = [
            SchemaField(name="timestamp", type="timestamp", required=True),
            SchemaField(name="status", type="string", required=True),
            SchemaField(name="message", type="string", required=True),
            SchemaField(name="service", type="string", required=False),
            SchemaField(name="host", type="string", required=False),
            SchemaField(name="tags", type="array", required=False),
        ]

        # Try to augment with a sample log
        try:
            client = self._get_client()
            body = {
                "filter": {"from": "now-5m", "to": "now", "query": "*"},
                "page": {"limit": 1},
            }
            resp = await client.post("/api/v2/logs/events/search", json=body)
            if resp.status_code == 200:
                result_data = resp.json()
                data = result_data.get("data", [])
                if data:
                    entries = self._parse_search_results([data[0]], self._id)
                    return SchemaInfo(
                        source=self._id,
                        fields=fields,
                        known_formats=["json"],
                        sample_log=entries[0],
                    )
        except Exception:  # noqa: BLE001,S110
            pass

        return SchemaInfo(
            source=self._id,
            fields=fields,
            known_formats=["json"],
        )

    async def detect_patterns(self, params: PatternParams) -> PatternResult:
        # Phase 5 intelligence — return empty for now
        return PatternResult(patterns=[], total_errors=0)

    async def find_anomalies(self, params: AnomalyParams) -> AnomalyResult:
        # Phase 5 intelligence — return empty for now
        return AnomalyResult(anomalies=[], metric=params.metric)
