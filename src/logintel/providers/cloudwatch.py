"""AWS CloudWatch Logs provider for LogIntel."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError, ProfileNotFound

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

logger = logging.getLogger("logintel.providers.cloudwatch")


class CloudWatchProvider(LogProvider):
    """Provider for querying AWS CloudWatch Logs."""

    def __init__(self, source_id: str, config: SourceConfig) -> None:
        self._id = source_id
        self._region: str = getattr(config, "region", "us-east-1")
        self._profile: str | None = getattr(config, "profile", None)
        self._log_groups: list[str] = getattr(config, "logGroups", []) or getattr(
            config, "log_groups", []
        )
        self._cross_account_role: str | None = getattr(
            config, "crossAccountRoleArn", None
        ) or getattr(config, "cross_account_role_arn", None)
        self._client: Any | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return "cloudwatch"

    # ------------------------------------------------------------------
    # Boto3 client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Lazy-initialize the CloudWatch Logs boto3 client."""
        if self._client is not None:
            return self._client

        try:
            session = (
                boto3.Session(profile_name=self._profile) if self._profile else boto3.Session()
            )
        except ProfileNotFound as exc:
            logger.error("AWS profile '%s' not found: %s", self._profile, exc)
            raise

        if self._cross_account_role:
            sts = session.client("sts", region_name=self._region)
            creds = sts.assume_role(
                RoleArn=self._cross_account_role,
                RoleSessionName="logintel-mcp",
            )["Credentials"]
            self._client = boto3.client(
                "logs",
                region_name=self._region,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        else:
            self._client = session.client("logs", region_name=self._region)

        return self._client

    @staticmethod
    def _to_epoch_seconds(dt: datetime) -> int:
        """Convert a datetime to Unix epoch seconds (int)."""
        return int(dt.timestamp())

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_search_query(params: SearchParams) -> str:
        """Build a CloudWatch Logs Insights query for search."""
        parts = ["fields @timestamp, @message, @logStream"]
        if params.query:
            # Escape forward slashes in the query for regex-like matching
            escaped = params.query.replace("/", "\\/")
            parts.append(f"| filter @message like /{escaped}/")
        parts.append("| sort @timestamp desc")
        parts.append(f"| limit {params.limit}")
        return " ".join(parts)

    @staticmethod
    def _build_filter_query(params: FilterParams) -> str:
        """Build a CloudWatch Logs Insights query for structured filtering."""
        parts = ["fields @timestamp, @message, @logStream"]
        filters: list[str] = []

        if params.level:
            filters.append(f'@message like /"level":"{params.level}"/')
            filters.append(f'@message like /"level": "{params.level}"/')
            filters.append(f"@message like /{params.level}/")
        if params.service:
            filters.append(f"@logStream like /{params.service}/")
        if params.host:
            filters.append(f"@logStream like /{params.host}/")
        if params.trace_id:
            filters.append(f'@message like /"traceId":"{params.trace_id}"/')
            filters.append(f'@message like /"trace_id":"{params.trace_id}"/')

        for key, value in params.custom_fields.items():
            filters.append(f'@message like /"{key}":"{value}"/')
            filters.append(f'@message like /"{key}": "{value}"/')

        if filters:
            # CloudWatch Insights uses 'or' between multiple like checks on the same
            # conceptual field and 'and' across different fields. For simplicity we
            # join with 'and' and group level alternatives with 'or'.
            parts.append("| filter " + " and ".join(filters))

        parts.append("| sort @timestamp desc")
        parts.append(f"| limit {params.limit}")
        return " ".join(parts)

    @staticmethod
    def _build_aggregate_query(params: AggregateParams) -> str:
        """Build a CloudWatch Logs Insights stats query for aggregation."""
        group_parts: list[str] = []

        for field in params.group_by:
            if field == "timestamp_bucket" and params.time_bucket:
                group_parts.append(f"bin({params.time_bucket})")
            elif field == "level":
                # Extract level from JSON message — heuristic
                group_parts.append("level")
            elif field == "service" or field == "host":
                group_parts.append("@logStream")
            else:
                group_parts.append(field)

        if not group_parts:
            bucket = params.time_bucket or "5m"
            group_parts = [f"bin({bucket})"]

        metric = params.metric.lower()
        if metric in ("avg", "average"):
            func = f"avg({params.field})" if params.field else "count()"
        elif metric == "sum":
            func = f"sum({params.field})" if params.field else "count()"
        elif metric == "min":
            func = f"min({params.field})" if params.field else "count()"
        elif metric == "max":
            func = f"max({params.field})" if params.field else "count()"
        else:
            func = "count()"

        group_by_str = ", ".join(group_parts)
        return f"stats {func} by {group_by_str} | sort {func} desc | limit {params.limit}"

    # ------------------------------------------------------------------
    # Result parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_insights_results(results: list[list[dict]]) -> list[LogEntry]:
        """Parse CloudWatch Insights tabular results into LogEntry objects."""
        entries: list[LogEntry] = []
        for row in results:
            row_dict: dict[str, str] = {}
            for cell in row:
                row_dict[cell["field"]] = cell.get("value", "")

            timestamp = row_dict.get("@timestamp", datetime.now(UTC).isoformat())
            message = row_dict.get("@message", "")
            log_stream = row_dict.get("@logStream")

            # Try to extract level and service from JSON messages
            level = "UNKNOWN"
            service = log_stream
            trace_id = None
            extra: dict[str, Any] = {}

            try:
                parsed = json.loads(message)
                if isinstance(parsed, dict):
                    level = str(parsed.get("level", "UNKNOWN")).upper()
                    service = str(parsed.get("service", log_stream or "unknown"))
                    trace_id = parsed.get("traceId") or parsed.get("trace_id")
                    excluded = {
                        "timestamp",
                        "level",
                        "message",
                        "service",
                        "host",
                        "traceId",
                        "trace_id",
                        "spanId",
                        "span_id",
                    }
                    for k, v in parsed.items():
                        if k not in excluded:
                            extra[k] = v
            except json.JSONDecodeError:
                # Plain text: try to infer level from common prefixes
                msg_upper = message.upper()
                for lvl in ("ERROR", "WARN", "WARNING", "INFO", "DEBUG", "TRACE"):
                    if msg_upper.startswith(lvl) or f" {lvl} " in msg_upper:
                        level = lvl if lvl != "WARNING" else "WARN"
                        break

            entries.append(
                LogEntry(
                    timestamp=timestamp,
                    level=level,
                    message=message,
                    service=service,
                    host=log_stream,
                    trace_id=str(trace_id) if trace_id else None,
                    source="cloudwatch",
                    fields=extra,
                    raw=row_dict,
                )
            )
        return entries

    @staticmethod
    def _parse_stats_results(results: list[list[dict]], params: AggregateParams) -> AggregateResult:
        """Parse CloudWatch Insights stats results into AggregateResult."""
        buckets: list[AggregateBucket] = []
        total_records = 0

        for row in results:
            row_dict: dict[str, str] = {}
            value: float = 0.0
            count: int = 0

            for cell in row:
                field_name = cell["field"]
                field_value = cell.get("value", "")

                if field_name in ("count()", "avg()", "sum()", "min()", "max()"):
                    try:
                        value = float(field_value)
                    except ValueError:
                        value = 0.0
                    count = int(value) if value == int(value) else 1
                elif field_name.startswith("stats "):
                    # Sometimes the function name is the full expression
                    try:
                        value = float(field_value)
                    except ValueError:
                        value = 0.0
                    count = int(value) if value == int(value) else 1
                else:
                    row_dict[field_name] = field_value

            # Fallback: if no metric value was parsed, try to find any numeric field
            if value == 0.0 and count == 0:
                for _k, v in row_dict.items():
                    try:
                        value = float(v)
                        count = int(value) if value == int(value) else 1
                        break
                    except ValueError:
                        continue

            buckets.append(AggregateBucket(key=row_dict, value=value, count=count))
            total_records += count

        return AggregateResult(buckets=buckets, total=total_records)

    # ------------------------------------------------------------------
    # LogProvider interface
    # ------------------------------------------------------------------

    async def health(self) -> HealthStatus:
        """Check that configured log groups exist and are accessible."""
        if not self._log_groups:
            return HealthStatus(
                source=self._id,
                status="degraded",
                message="No log groups configured",
            )

        try:
            client = self._get_client()
            missing: list[str] = []

            for group in self._log_groups:
                try:
                    # describe_log_groups with exact name
                    resp = await asyncio.to_thread(
                        client.describe_log_groups,
                        logGroupNamePrefix=group,
                        limit=1,
                    )
                    groups = resp.get("logGroups", [])
                    if not groups or groups[0]["logGroupName"] != group:
                        missing.append(group)
                except ClientError as exc:
                    logger.warning("Failed to describe log group '%s': %s", group, exc)
                    missing.append(group)

            if missing:
                return HealthStatus(
                    source=self._id,
                    status="degraded",
                    message=f"Log groups not found: {', '.join(missing)}",
                )

            return HealthStatus(
                source=self._id,
                status="healthy",
                message=f"Found {len(self._log_groups)} log group(s)",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Health check failed for CloudWatch source '%s'", self._id)
            return HealthStatus(
                source=self._id,
                status="unhealthy",
                message=str(exc),
            )

    async def search(self, params: SearchParams) -> SearchResult:
        """Search logs using CloudWatch Logs Insights."""
        if not self._log_groups:
            return SearchResult(entries=[], total=0)

        try:
            client = self._get_client()
            query = self._build_search_query(params)

            start_time = parse_relative_time("now-1h")
            end_time = datetime.now(UTC)
            if params.time_range:
                start_time = parse_relative_time(params.time_range.from_time)
                if params.time_range.to_time:
                    end_time = parse_relative_time(params.time_range.to_time)

            resp = await asyncio.to_thread(
                client.start_query,
                logGroupNames=self._log_groups,
                startTime=self._to_epoch_seconds(start_time),
                endTime=self._to_epoch_seconds(end_time),
                queryString=query,
            )
            query_id = resp["queryId"]

            # Poll for completion
            results = await self._wait_for_query(client, query_id)
            entries = self._parse_insights_results(results)
            return SearchResult(
                entries=entries,
                total=len(entries),
            )
        except Exception:  # noqa: BLE001
            logger.exception("CloudWatch search failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def filter(self, params: FilterParams) -> SearchResult:
        """Filter logs using structured criteria via CloudWatch Logs Insights."""
        if not self._log_groups:
            return SearchResult(entries=[], total=0)

        try:
            client = self._get_client()
            query = self._build_filter_query(params)

            start_time = parse_relative_time("now-1h")
            end_time = datetime.now(UTC)
            if params.time_range:
                start_time = parse_relative_time(params.time_range.from_time)
                if params.time_range.to_time:
                    end_time = parse_relative_time(params.time_range.to_time)

            resp = await asyncio.to_thread(
                client.start_query,
                logGroupNames=self._log_groups,
                startTime=self._to_epoch_seconds(start_time),
                endTime=self._to_epoch_seconds(end_time),
                queryString=query,
            )
            query_id = resp["queryId"]

            results = await self._wait_for_query(client, query_id)
            entries = self._parse_insights_results(results)
            return SearchResult(
                entries=entries,
                total=len(entries),
            )
        except Exception:  # noqa: BLE001
            logger.exception("CloudWatch filter failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def aggregate(self, params: AggregateParams) -> AggregateResult:
        """Aggregate logs using CloudWatch Logs Insights stats queries."""
        if not self._log_groups:
            return AggregateResult(buckets=[], total=0)

        try:
            client = self._get_client()
            query = self._build_aggregate_query(params)

            start_time = parse_relative_time("now-1h")
            end_time = datetime.now(UTC)
            if params.time_range:
                start_time = parse_relative_time(params.time_range.from_time)
                if params.time_range.to_time:
                    end_time = parse_relative_time(params.time_range.to_time)

            resp = await asyncio.to_thread(
                client.start_query,
                logGroupNames=self._log_groups,
                startTime=self._to_epoch_seconds(start_time),
                endTime=self._to_epoch_seconds(end_time),
                queryString=query,
            )
            query_id = resp["queryId"]

            results = await self._wait_for_query(client, query_id)
            return self._parse_stats_results(results, params)
        except Exception:  # noqa: BLE001
            logger.exception("CloudWatch aggregate failed for source '%s'", self._id)
            return AggregateResult(buckets=[], total=0)

    async def tail(self, params: TailParams) -> SearchResult:
        """Tail recent logs using filter_log_events (faster than Insights)."""
        if not self._log_groups:
            return SearchResult(entries=[], total=0)

        try:
            client = self._get_client()
            all_entries: list[LogEntry] = []
            start_time = self._to_epoch_seconds(
                datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            )

            for group in self._log_groups:
                kwargs: dict[str, Any] = {
                    "logGroupName": group,
                    "startTime": start_time * 1000,  # filter_log_events expects ms
                    "limit": params.lines,
                }
                if params.filter_query:
                    kwargs["filterPattern"] = params.filter_query

                resp = await asyncio.to_thread(client.filter_log_events, **kwargs)
                events = resp.get("events", [])

                for event in events:
                    ts_ms = event.get("timestamp", 0)
                    ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()
                    message = event.get("message", "")
                    log_stream = event.get("logStreamName")

                    # Try JSON parsing for structured fields
                    level = "UNKNOWN"
                    service = log_stream or "unknown"
                    trace_id = None
                    extra: dict[str, Any] = {}

                    try:
                        parsed = json.loads(message)
                        if isinstance(parsed, dict):
                            level = str(parsed.get("level", "UNKNOWN")).upper()
                            service = str(parsed.get("service", log_stream or "unknown"))
                            trace_id = parsed.get("traceId") or parsed.get("trace_id")
                            for k, v in parsed.items():
                                if k not in (
                                    "timestamp",
                                    "level",
                                    "message",
                                    "service",
                                    "host",
                                    "traceId",
                                    "trace_id",
                                    "spanId",
                                    "span_id",
                                ):
                                    extra[k] = v
                    except json.JSONDecodeError:
                        msg_upper = message.upper()
                        for lvl in ("ERROR", "WARN", "WARNING", "INFO", "DEBUG", "TRACE"):
                            if msg_upper.startswith(lvl) or f" {lvl} " in msg_upper:
                                level = lvl if lvl != "WARNING" else "WARN"
                                break

                    all_entries.append(
                        LogEntry(
                            timestamp=ts_iso,
                            level=level,
                            message=message,
                            service=service,
                            host=log_stream,
                            trace_id=str(trace_id) if trace_id else None,
                            source="cloudwatch",
                            fields=extra,
                            raw=event,
                        )
                    )

            # Sort by timestamp desc and take last N
            all_entries.sort(key=lambda e: e.timestamp, reverse=True)
            entries = all_entries[: params.lines]
            return SearchResult(entries=entries, total=len(entries))
        except Exception:  # noqa: BLE001
            logger.exception("CloudWatch tail failed for source '%s'", self._id)
            return SearchResult(entries=[], total=0)

    async def get_schema(self) -> SchemaInfo:
        """Return schema info for CloudWatch Logs fields."""
        fields = [
            SchemaField(name="@timestamp", type="timestamp", required=True),
            SchemaField(name="@message", type="string", required=True),
            SchemaField(name="@logStream", type="string", required=False),
            SchemaField(name="@logGroup", type="string", required=False),
        ]

        # Try to augment with discovered fields from a sample query
        try:
            client = self._get_client()
            sample_query = "fields @timestamp, @message, @logStream | limit 1"
            start_time = self._to_epoch_seconds(datetime.now(UTC) - timedelta(minutes=5))
            end_time = self._to_epoch_seconds(datetime.now(UTC))

            resp = await asyncio.to_thread(
                client.start_query,
                logGroupNames=self._log_groups,
                startTime=start_time,
                endTime=end_time,
                queryString=sample_query,
            )
            query_id = resp["queryId"]
            results = await self._wait_for_query(client, query_id)

            if results:
                sample = self._parse_insights_results([results[0]])[0]
                return SchemaInfo(
                    source=self._id,
                    fields=fields,
                    known_formats=["json", "plaintext"],
                    sample_log=sample,
                )
        except Exception:  # noqa: BLE001,S110
            pass

        return SchemaInfo(
            source=self._id,
            fields=fields,
            known_formats=["json", "plaintext"],
        )

    async def detect_patterns(self, params: PatternParams) -> PatternResult:
        # Phase 5 intelligence — return empty for now
        return PatternResult(patterns=[], total_errors=0)

    async def find_anomalies(self, params: AnomalyParams) -> AnomalyResult:
        # Phase 5 intelligence — return empty for now
        return AnomalyResult(anomalies=[], metric=params.metric)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _wait_for_query(
        self,
        client: Any,
        query_id: str,
        max_retries: int = 60,
        poll_interval: float = 0.5,
    ) -> list[list[dict]]:
        """Poll a CloudWatch Logs Insights query until it completes."""
        for _ in range(max_retries):
            resp = await asyncio.to_thread(client.get_query_results, queryId=query_id)
            status = resp.get("status", "")
            if status in ("Complete", "Failed", "Cancelled"):
                if status == "Complete":
                    return resp.get("results", [])
                logger.warning("Query %s ended with status: %s", query_id, status)
                return []
            await asyncio.sleep(poll_interval)
        logger.warning("Query %s timed out waiting for completion", query_id)
        return []
