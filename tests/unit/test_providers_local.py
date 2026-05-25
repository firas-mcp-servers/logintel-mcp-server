"""Unit tests for LocalFileProvider scenarios."""

import json
from pathlib import Path

import pytest

from logintel.config import SourceConfig
from logintel.models import (
    AggregateParams,
    AnomalyParams,
    FilterParams,
    PatternParams,
    SearchParams,
    TailParams,
)
from logintel.providers.local import LocalFileProvider


class TestLocalFileProviderLifecycle:
    """Scenarios for LocalFileProvider initialization and basic properties."""

    def test_when_created_with_json_config_then_parse_json_is_enabled(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        assert provider.id == "test"
        assert provider.type == "local"
        assert provider._parse_json is True

    def test_when_created_with_regex_config_then_regex_is_compiled(self):
        config = SourceConfig(
            type="local",
            paths=["/tmp/*.log"],
            regexPattern=r"^(?P<msg>.*)$",
        )
        provider = LocalFileProvider("test", config)
        assert provider._regex is not None


class TestLocalFileProviderHealth:
    """Scenarios for health check behavior."""

    @pytest.mark.asyncio
    async def test_when_files_exist_and_are_readable_then_returns_healthy(self, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("test log line\n")
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.log")])
        provider = LocalFileProvider("test", config)
        health = await provider.health()
        assert health.status == "healthy"
        assert "1" in health.message

    @pytest.mark.asyncio
    async def test_when_no_files_match_patterns_then_returns_degraded(self):
        config = SourceConfig(type="local", paths=["/nonexistent/*.log"])
        provider = LocalFileProvider("test", config)
        health = await provider.health()
        assert health.status == "degraded"
        assert "No files found" in health.message


class TestLocalFileProviderParseLine:
    """Scenarios for parsing individual log lines."""

    def test_when_given_valid_json_line_then_parses_all_fields(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        line = json.dumps(
            {
                "timestamp": "2026-05-24T10:00:00Z",
                "level": "ERROR",
                "message": "DB failed",
                "service": "payment",
            }
        )
        entry = provider._parse_line(line, "test")
        assert entry is not None
        assert entry.timestamp == "2026-05-24T10:00:00Z"
        assert entry.level == "ERROR"
        assert entry.message == "DB failed"
        assert entry.service == "payment"

    def test_when_given_json_without_message_field_then_uses_fallback_keys(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        line = json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO", "msg": "hello"})
        entry = provider._parse_line(line, "test")
        assert entry is not None
        assert entry.message == "hello"

    def test_when_given_json_with_no_known_message_key_then_uses_whole_dict(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        line = json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO"})
        entry = provider._parse_line(line, "test")
        assert entry is not None
        assert "timestamp" in entry.message

    def test_when_given_plain_text_line_then_returns_unknown_level(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line("plain log message", "test")
        assert entry is not None
        assert entry.level == "UNKNOWN"
        assert entry.message == "plain log message"

    def test_when_given_empty_line_then_returns_none(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line("   ", "test")
        assert entry is None

    def test_when_given_regex_matching_line_then_extracts_named_groups(self):
        config = SourceConfig(
            type="local",
            paths=["/tmp/*.log"],
            regexPattern=(
                r"^(?P<timestamp>\S+ \S+) \[(?P<level>\w+)\] "
                r"(?P<service>\w+): (?P<message>.*)$"
            ),
        )
        provider = LocalFileProvider("test", config)
        line = "2026-05-24 10:00:00 [ERROR] payment: DB failed"
        entry = provider._parse_line(line, "test")
        assert entry is not None
        assert entry.level == "ERROR"
        assert entry.service == "payment"
        assert entry.message == "DB failed"

    def test_when_given_non_json_with_json_parsing_enabled_then_falls_back_to_plain(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line("not json at all", "test")
        assert entry is not None
        assert entry.level == "UNKNOWN"
        assert entry.message == "not json at all"

    def test_when_given_json_list_instead_of_dict_then_returns_plain_text(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line("[1, 2, 3]", "test")
        assert entry is not None
        assert entry.level == "UNKNOWN"


class TestLocalFileProviderSearch:
    """Scenarios for searching logs."""

    @pytest.fixture
    def provider(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "DB connection failed",
                    "service": "payment",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:05:00Z",
                    "level": "INFO",
                    "message": "Request processed",
                    "service": "api",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:10:00Z",
                    "level": "ERROR",
                    "message": "Timeout occurred",
                    "service": "payment",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
            timestampField="timestamp",
            levelField="level",
            serviceField="service",
        )
        return LocalFileProvider("test", config)

    @pytest.mark.asyncio
    async def test_when_searching_by_service_name_then_returns_matching_entries(self, provider):
        result = await provider.search(SearchParams(source="test", query="payment"))
        assert len(result.entries) == 2
        assert all(e.service == "payment" for e in result.entries)

    @pytest.mark.asyncio
    async def test_when_searching_by_level_then_returns_matching_entries(self, provider):
        result = await provider.search(SearchParams(source="test", query="error"))
        assert len(result.entries) == 2
        assert all(e.level == "ERROR" for e in result.entries)

    @pytest.mark.asyncio
    async def test_when_searching_by_message_content_then_returns_matching_entries(self, provider):
        result = await provider.search(SearchParams(source="test", query="Timeout"))
        assert len(result.entries) == 1
        assert result.entries[0].message == "Timeout occurred"

    @pytest.mark.asyncio
    async def test_when_searching_with_time_range_then_filters_by_timestamp(self, provider):
        result = await provider.search(
            SearchParams(
                source="test",
                query="",
                time_range={"from": "2026-05-24T10:04:00Z", "to": "2026-05-24T10:06:00Z"},
            )
        )
        assert len(result.entries) == 1
        assert result.entries[0].message == "Request processed"

    @pytest.mark.asyncio
    async def test_when_searching_with_no_matches_then_returns_empty_result(self, provider):
        result = await provider.search(SearchParams(source="test", query="nonexistent"))
        assert len(result.entries) == 0

    @pytest.mark.asyncio
    async def test_when_searching_with_limit_then_respects_limit(self, provider):
        result = await provider.search(SearchParams(source="test", query="", limit=2))
        assert len(result.entries) == 2

    @pytest.mark.asyncio
    async def test_when_searching_with_offset_then_skips_first_entries(self, provider):
        result = await provider.search(SearchParams(source="test", query="", limit=1, offset="1"))
        assert len(result.entries) == 1
        assert result.entries[0].message == "Request processed"


class TestLocalFileProviderFilter:
    """Scenarios for filtering logs by structured criteria."""

    @pytest.fixture
    def provider(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "DB failed",
                    "service": "payment",
                    "host": "host1",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:05:00Z",
                    "level": "INFO",
                    "message": "OK",
                    "service": "api",
                    "host": "host2",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
            timestampField="timestamp",
            levelField="level",
            serviceField="service",
            hostField="host",
        )
        return LocalFileProvider("test", config)

    @pytest.mark.asyncio
    async def test_when_filtering_by_level_error_then_returns_only_errors(self, provider):
        result = await provider.filter(FilterParams(source="test", level="ERROR"))
        assert len(result.entries) == 1
        assert result.entries[0].level == "ERROR"

    @pytest.mark.asyncio
    async def test_when_filtering_by_service_then_returns_only_that_service(self, provider):
        result = await provider.filter(FilterParams(source="test", service="api"))
        assert len(result.entries) == 1
        assert result.entries[0].service == "api"

    @pytest.mark.asyncio
    async def test_when_filtering_by_host_then_returns_only_that_host(self, provider):
        result = await provider.filter(FilterParams(source="test", host="host1"))
        assert len(result.entries) == 1
        assert result.entries[0].host == "host1"

    @pytest.mark.asyncio
    async def test_when_filtering_by_trace_id_then_returns_only_matching_entries(self, provider):
        log_file = Path(provider._paths[0]).parent / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "x",
                    "trace_id": "abc123",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:01:00Z",
                    "level": "ERROR",
                    "message": "y",
                    "trace_id": "def456",
                }
            )
            + "\n"
        )
        result = await provider.filter(FilterParams(source="test", trace_id="abc123"))
        assert len(result.entries) == 1
        assert result.entries[0].trace_id == "abc123"

    @pytest.mark.asyncio
    async def test_when_filtering_by_custom_fields_then_returns_matching_entries(self, provider):
        log_file = Path(provider._paths[0]).parent / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "x",
                    "env": "prod",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:01:00Z",
                    "level": "ERROR",
                    "message": "y",
                    "env": "dev",
                }
            )
            + "\n"
        )
        result = await provider.filter(FilterParams(source="test", custom_fields={"env": "prod"}))
        assert len(result.entries) == 1
        assert result.entries[0].fields["env"] == "prod"

    @pytest.mark.asyncio
    async def test_when_filtering_with_time_range_then_returns_entries_in_range(self, provider):
        result = await provider.filter(
            FilterParams(
                source="test",
                time_range={"from": "2026-05-24T10:04:00Z", "to": "2026-05-24T10:06:00Z"},
            )
        )
        assert len(result.entries) == 1
        assert result.entries[0].message == "OK"


class TestLocalFileProviderTail:
    """Scenarios for tailing logs."""

    @pytest.fixture
    def provider(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        lines = []
        for i in range(10):
            lines.append(
                json.dumps(
                    {
                        "timestamp": f"2026-05-24T10:0{i:02d}:00Z",
                        "level": "INFO",
                        "message": f"line {i}",
                    }
                )
            )
        log_file.write_text("\n".join(lines) + "\n")
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
            timestampField="timestamp",
        )
        return LocalFileProvider("test", config)

    @pytest.mark.asyncio
    async def test_when_tailing_with_default_lines_then_returns_last_50_or_all(self, provider):
        result = await provider.tail(TailParams(source="test"))
        assert len(result.entries) == 10
        assert result.entries[-1].message == "line 9"

    @pytest.mark.asyncio
    async def test_when_tailing_with_limit_then_returns_last_n_entries(self, provider):
        result = await provider.tail(TailParams(source="test", lines=3))
        assert len(result.entries) == 3
        assert result.entries[0].message == "line 7"
        assert result.entries[-1].message == "line 9"

    @pytest.mark.asyncio
    async def test_when_tailing_with_filter_then_returns_matching_last_entries(self, provider):
        result = await provider.tail(TailParams(source="test", lines=5, filter_query="line 1"))
        # Only "line 1" matches (lines are 0-9, "line 10" would match but doesn't exist)
        assert len(result.entries) == 1
        assert result.entries[0].message == "line 1"


class TestLocalFileProviderAggregate:
    """Scenarios for log aggregation."""

    @pytest.fixture
    def provider(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "x",
                    "service": "payment",
                    "duration_ms": 100,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:05:00Z",
                    "level": "INFO",
                    "message": "y",
                    "service": "api",
                    "duration_ms": 200,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:10:00Z",
                    "level": "ERROR",
                    "message": "z",
                    "service": "payment",
                    "duration_ms": 300,
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
            timestampField="timestamp",
            levelField="level",
            serviceField="service",
        )
        return LocalFileProvider("test", config)

    @pytest.mark.asyncio
    async def test_when_aggregating_count_by_level_then_returns_correct_counts(self, provider):
        result = await provider.aggregate(AggregateParams(source="test", group_by=["level"]))
        assert len(result.buckets) == 2
        counts = {b.key["level"]: b.count for b in result.buckets}
        assert counts["ERROR"] == 2
        assert counts["INFO"] == 1

    @pytest.mark.asyncio
    async def test_when_aggregating_count_by_service_then_returns_correct_counts(self, provider):
        result = await provider.aggregate(AggregateParams(source="test", group_by=["service"]))
        assert len(result.buckets) == 2
        counts = {b.key["service"]: b.count for b in result.buckets}
        assert counts["payment"] == 2
        assert counts["api"] == 1

    @pytest.mark.asyncio
    async def test_when_aggregating_with_time_bucket_then_groups_by_time(self, provider):
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["timestamp_bucket"], time_bucket="1h")
        )
        assert len(result.buckets) == 1
        assert result.buckets[0].count == 3

    @pytest.mark.asyncio
    async def test_when_aggregating_avg_metric_then_returns_average(self, provider):
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["service"], metric="avg", field="duration_ms")
        )
        payment_bucket = next(b for b in result.buckets if b.key["service"] == "payment")
        assert payment_bucket.value == 200.0

    @pytest.mark.asyncio
    async def test_when_aggregating_sum_metric_then_returns_sum(self, provider):
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["service"], metric="sum", field="duration_ms")
        )
        payment_bucket = next(b for b in result.buckets if b.key["service"] == "payment")
        assert payment_bucket.value == 400.0

    @pytest.mark.asyncio
    async def test_when_aggregating_min_metric_then_returns_minimum(self, provider):
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["service"], metric="min", field="duration_ms")
        )
        payment_bucket = next(b for b in result.buckets if b.key["service"] == "payment")
        assert payment_bucket.value == 100.0

    @pytest.mark.asyncio
    async def test_when_aggregating_max_metric_then_returns_maximum(self, provider):
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["service"], metric="max", field="duration_ms")
        )
        payment_bucket = next(b for b in result.buckets if b.key["service"] == "payment")
        assert payment_bucket.value == 300.0

    @pytest.mark.asyncio
    async def test_when_aggregating_with_limit_then_respects_limit(self, provider):
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["level"], limit=1)
        )
        assert len(result.buckets) == 1


class TestLocalFileProviderSchema:
    """Scenarios for schema discovery."""

    @pytest.mark.asyncio
    async def test_when_json_configured_then_schema_includes_json_format(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        schema = await provider.get_schema()
        assert "json" in schema.known_formats
        assert any(f.name == "timestamp" for f in schema.fields)

    @pytest.mark.asyncio
    async def test_when_regex_configured_then_schema_includes_regex_format(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], regexPattern=r"^(?P<msg>.*)$")
        provider = LocalFileProvider("test", config)
        schema = await provider.get_schema()
        assert "regex" in schema.known_formats


class TestLocalFileProviderSecurity:
    """Scenarios for path sandboxing security."""

    def test_when_file_is_within_allowed_path_then_access_is_permitted(self, tmp_path):
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.log")])
        provider = LocalFileProvider("test", config)
        assert provider._is_path_allowed(tmp_path / "app.log") is True

    def test_when_file_is_outside_allowed_path_then_access_is_denied(self, tmp_path):
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.log")])
        provider = LocalFileProvider("test", config)
        assert provider._is_path_allowed(Path("/etc/passwd")) is False

    def test_when_path_contains_dotdot_then_access_is_denied(self, tmp_path):
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.log")])
        provider = LocalFileProvider("test", config)
        malicious = tmp_path / ".." / "etc" / "passwd"
        assert provider._is_path_allowed(malicious) is False


class TestLocalFileProviderPlaceholderMethods:
    """Scenarios for placeholder methods not yet implemented."""

    @pytest.mark.asyncio
    async def test_when_detect_patterns_is_called_then_returns_empty_result(self, tmp_path):
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.log")])
        provider = LocalFileProvider("test", config)
        result = await provider.detect_patterns(PatternParams(source="test"))
        assert result.patterns == []
        assert result.total_errors == 0

    @pytest.mark.asyncio
    async def test_when_find_anomalies_is_called_then_returns_empty_result(self, tmp_path):
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.log")])
        provider = LocalFileProvider("test", config)
        result = await provider.find_anomalies(AnomalyParams(source="test"))
        assert result.anomalies == []
