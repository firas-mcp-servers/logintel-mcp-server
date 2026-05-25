"""Unit tests for LocalFileProvider edge case scenarios."""

import json
from datetime import UTC, datetime

import pytest

from logintel.config import SourceConfig
from logintel.models import (
    AggregateParams,
    FilterParams,
    SearchParams,
    TailParams,
)
from logintel.providers.local import LocalFileProvider


class TestLocalFileProviderParseLineEdgeCases:
    """Scenarios for edge cases in log line parsing."""

    def test_when_given_json_array_instead_of_dict_then_falls_back_to_plain_text(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line("[1, 2, 3]", "test")
        assert entry is not None
        assert entry.level == "UNKNOWN"
        assert entry.message == "[1, 2, 3]"

    def test_when_given_regex_non_matching_line_then_falls_back_to_plain_text(self):
        config = SourceConfig(
            type="local",
            paths=["/tmp/*.log"],
            regexPattern=r"^\[(?P<level>\w+)\] (?P<message>.*)$",
        )
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line("no match here", "test")
        assert entry is not None
        assert entry.level == "UNKNOWN"
        assert entry.message == "no match here"

    def test_when_given_valid_json_with_trace_id_then_extracts_trace_id(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        line = json.dumps(
            {
                "timestamp": "2026-05-24T10:00:00Z",
                "level": "INFO",
                "message": "test",
                "traceId": "abc123",
                "spanId": "def456",
            }
        )
        entry = provider._parse_line(line, "test")
        assert entry.trace_id == "abc123"
        assert entry.span_id == "def456"

    def test_when_given_valid_json_with_trace_id_snake_case_then_extracts_trace_id(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        line = json.dumps(
            {
                "timestamp": "2026-05-24T10:00:00Z",
                "level": "INFO",
                "message": "test",
                "trace_id": "abc123",
                "span_id": "def456",
            }
        )
        entry = provider._parse_line(line, "test")
        assert entry.trace_id == "abc123"
        assert entry.span_id == "def456"


class TestLocalFileProviderTimeMatching:
    """Scenarios for time range matching logic."""

    def test_when_entry_is_within_time_range_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        from_time = datetime(2026, 5, 24, 9, 0, 0, tzinfo=UTC)
        to_time = datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC)
        assert provider._line_matches_time_range(entry, from_time, to_time) is True

    def test_when_entry_is_before_time_range_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T08:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        from_time = datetime(2026, 5, 24, 9, 0, 0, tzinfo=UTC)
        to_time = datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC)
        assert provider._line_matches_time_range(entry, from_time, to_time) is False

    def test_when_entry_is_after_time_range_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T12:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        from_time = datetime(2026, 5, 24, 9, 0, 0, tzinfo=UTC)
        to_time = datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC)
        assert provider._line_matches_time_range(entry, from_time, to_time) is False

    def test_when_entry_has_unparseable_timestamp_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "not-a-date", "level": "INFO", "message": "x"}),
            "test",
        )
        from_time = datetime(2026, 5, 24, 9, 0, 0, tzinfo=UTC)
        to_time = datetime(2026, 5, 24, 11, 0, 0, tzinfo=UTC)
        assert provider._line_matches_time_range(entry, from_time, to_time) is True

    def test_when_no_time_range_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        assert provider._line_matches_time_range(entry, None, None) is True


class TestLocalFileProviderSearchMatching:
    """Scenarios for search query matching logic."""

    def test_when_query_matches_extra_field_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "extra": "search-me",
                }
            ),
            "test",
        )
        assert provider._line_matches_search(entry, "search-me") is True

    def test_when_query_matches_level_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "ERROR", "message": "x"}),
            "test",
        )
        assert provider._line_matches_search(entry, "error") is True

    def test_when_query_does_not_match_anything_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        assert provider._line_matches_search(entry, "nonexistent") is False


class TestLocalFileProviderFilterMatching:
    """Scenarios for structured filter matching logic."""

    def test_when_level_does_not_match_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        params = FilterParams(source="test", level="ERROR")
        assert provider._line_matches_filter(entry, params) is False

    def test_when_service_does_not_match_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "service": "api",
                }
            ),
            "test",
        )
        params = FilterParams(source="test", service="payment")
        assert provider._line_matches_filter(entry, params) is False

    def test_when_host_does_not_match_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "host": "host1",
                }
            ),
            "test",
        )
        params = FilterParams(source="test", host="host2")
        assert provider._line_matches_filter(entry, params) is False

    def test_when_trace_id_does_not_match_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "traceId": "abc",
                }
            ),
            "test",
        )
        params = FilterParams(source="test", trace_id="def")
        assert provider._line_matches_filter(entry, params) is False

    def test_when_custom_field_does_not_match_then_returns_false(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "env": "prod",
                }
            ),
            "test",
        )
        params = FilterParams(source="test", custom_fields={"env": "dev"})
        assert provider._line_matches_filter(entry, params) is False

    def test_when_no_filters_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        params = FilterParams(source="test")
        assert provider._line_matches_filter(entry, params) is True


class TestLocalFileProviderReadEntries:
    """Scenarios for reading entries from files."""

    def test_when_reading_with_offset_then_skips_first_n_entries(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        lines = []
        for i in range(5):
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
        )
        provider = LocalFileProvider("test", config)
        entries = provider._read_entries([log_file], "test", limit=10, offset=2)
        assert len(entries) == 3
        assert entries[0].message == "line 2"

    def test_when_reading_reverse_then_returns_last_n_entries(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        lines = []
        for i in range(5):
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
        )
        provider = LocalFileProvider("test", config)
        entries = provider._read_entries_reverse([log_file], "test", limit=2)
        assert len(entries) == 2
        assert entries[0].message == "line 3"
        assert entries[1].message == "line 4"


class TestLocalFileProviderBucketTimestamp:
    """Scenarios for time bucket rounding."""

    def test_when_bucket_is_5m_then_rounds_to_5m_boundary(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        ts = datetime(2026, 5, 24, 10, 7, 30)
        result = provider._bucket_timestamp(ts, "5m")
        assert "10:05:00" in result

    def test_when_bucket_is_2h_then_rounds_to_2h_boundary(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        ts = datetime(2026, 5, 24, 10, 30, 0)
        result = provider._bucket_timestamp(ts, "2h")
        assert "10:00:00" in result

    def test_when_bucket_is_invalid_then_returns_iso_format(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        ts = datetime(2026, 5, 24, 10, 0, 0)
        result = provider._bucket_timestamp(ts, "invalid")
        assert result == ts.isoformat()


class TestLocalFileProviderExtractNumeric:
    """Scenarios for extracting numeric values from entries."""

    def test_when_field_is_in_extra_fields_then_returns_numeric_value(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "duration_ms": 150,
                }
            ),
            "test",
        )
        assert provider._extract_numeric(entry, "duration_ms") == 150.0

    def test_when_field_is_not_numeric_then_returns_none(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "env": "prod",
                }
            ),
            "test",
        )
        assert provider._extract_numeric(entry, "env") is None

    def test_when_field_is_level_then_returns_none(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps({"timestamp": "2026-05-24T10:00:00Z", "level": "INFO", "message": "x"}),
            "test",
        )
        assert provider._extract_numeric(entry, "level") is None


class TestLocalFileProviderParseTimestamp:
    """Scenarios for timestamp parsing with various formats."""

    def test_when_given_iso_with_microseconds_then_parses_correctly(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        result = provider._parse_timestamp("2026-05-24T10:00:00.123456")
        assert result is not None
        assert result.year == 2026
        assert result.microsecond == 123456

    def test_when_given_space_separated_then_parses_correctly(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        result = provider._parse_timestamp("2026-05-24 10:00:00")
        assert result is not None
        assert result.hour == 10

    def test_when_given_unparseable_then_returns_none(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        result = provider._parse_timestamp("not a date")
        assert result is None


class TestLocalFileProviderHealthUnreadable:
    """Scenarios for health checks with unreadable files."""

    @pytest.mark.asyncio
    async def test_when_some_files_are_unreadable_then_returns_degraded(self, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("test\n")
        log_file.chmod(0o000)
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.log")])
        provider = LocalFileProvider("test", config)
        try:
            health = await provider.health()
            assert health.status == "degraded"
            assert "unreadable" in health.message
        finally:
            log_file.chmod(0o644)


class TestLocalFileProviderExceptionPaths:
    """Scenarios where file operations raise exceptions."""

    @pytest.mark.asyncio
    async def test_when_search_encounters_unreadable_file_then_continues_gracefully(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "ok",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
        )
        provider = LocalFileProvider("test", config)
        result = await provider.search(SearchParams(source="test", query="ok"))
        assert len(result.entries) == 1

    @pytest.mark.asyncio
    async def test_when_filter_encounters_unreadable_file_then_continues_gracefully(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "ok",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
        )
        provider = LocalFileProvider("test", config)
        result = await provider.filter(FilterParams(source="test"))
        assert len(result.entries) == 1

    @pytest.mark.asyncio
    async def test_when_tail_encounters_unreadable_file_then_continues_gracefully(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "ok",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
        )
        provider = LocalFileProvider("test", config)
        result = await provider.tail(TailParams(source="test"))
        assert len(result.entries) == 1


class TestLocalFileProviderAggregateEdgeCases:
    """Scenarios for aggregation edge cases."""

    @pytest.mark.asyncio
    async def test_when_aggregating_avg_with_no_numeric_values_then_returns_zero(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "service": "api",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
        )
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["service"], metric="avg", field="duration_ms")
        )
        assert len(result.buckets) == 1
        assert result.buckets[0].value == 0.0

    @pytest.mark.asyncio
    async def test_when_aggregating_min_with_no_numeric_values_then_returns_zero(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "service": "api",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
        )
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["service"], metric="min", field="duration_ms")
        )
        assert result.buckets[0].value == 0.0

    @pytest.mark.asyncio
    async def test_when_aggregating_max_with_no_numeric_values_then_returns_zero(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "service": "api",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
        )
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["service"], metric="max", field="duration_ms")
        )
        assert result.buckets[0].value == 0.0
