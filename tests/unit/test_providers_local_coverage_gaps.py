"""Unit tests targeting specific coverage gaps in LocalFileProvider."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from logintel.config import SourceConfig
from logintel.models import (
    AggregateParams,
    FilterParams,
    SearchParams,
    TailParams,
)
from logintel.providers.local import LocalFileProvider


class TestCoverageGapMessageField:
    """Cover line 133: _build_entry_from_dict with custom messageField."""

    def test_when_message_field_is_configured_then_uses_custom_field(self):
        config = SourceConfig(
            type="local",
            paths=["/tmp/*.log"],
            parseJson=True,
            messageField="custom_msg",
        )
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "custom_msg": "hello world",
                }
            ),
            "test",
        )
        assert entry.message == "hello world"


class TestCoverageGapSearchHost:
    """Cover line 214: _line_matches_search with host match."""

    def test_when_query_matches_host_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "host": "server01",
                }
            ),
            "test",
        )
        assert provider._line_matches_search(entry, "server01") is True


class TestCoverageGapReadEntriesLimit:
    """Cover line 256: _read_entries returns early when limit reached."""

    def test_when_limit_is_reached_then_returns_early(self, tmp_path):
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
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.jsonl")], parseJson=True)
        provider = LocalFileProvider("test", config)
        entries = provider._read_entries([log_file], "test", limit=3)
        assert len(entries) == 3


class TestCoverageGapSearchSkipsNoneEntry:
    """Cover line 331: search skips None entries."""

    @pytest.mark.asyncio
    async def test_when_log_file_has_blank_lines_then_skips_them(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            "\n\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "only valid line",
                }
            )
            + "\n\n"
        )
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.jsonl")], parseJson=True)
        provider = LocalFileProvider("test", config)
        result = await provider.search(SearchParams(source="test", query=""))
        assert len(result.entries) == 1
        assert result.entries[0].message == "only valid line"


class TestCoverageGapBucketTimestamp:
    """Cover _bucket_timestamp branches for minute and day."""

    def test_when_bucket_is_1m_then_rounds_to_minute_boundary(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        ts = datetime(2026, 5, 24, 10, 7, 30)
        result = provider._bucket_timestamp(ts, "1m")
        assert "10:07:00" in result

    def test_when_bucket_is_1d_then_rounds_to_day_boundary(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        ts = datetime(2026, 5, 24, 10, 30, 0)
        result = provider._bucket_timestamp(ts, "1d")
        assert "00:00:00" in result


class TestCoverageGapAggregateTimeRange:
    """Cover aggregate time_range parsing (lines 395-397)."""

    @pytest.mark.asyncio
    async def test_when_aggregate_has_time_range_then_filters_by_time(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T12:00:00Z",
                    "level": "INFO",
                    "message": "y",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
            timestampField="timestamp",
        )
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(
            AggregateParams(
                source="test",
                group_by=["level"],
                time_range={"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
            )
        )
        assert result.total == 1


class TestCoverageGapAggregateOSError:
    """Cover aggregate OSError handling (lines 408-409)."""

    @pytest.mark.asyncio
    async def test_when_aggregate_fails_to_open_file_then_returns_empty(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                }
            )
            + "\n"
        )
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.jsonl")], parseJson=True)
        provider = LocalFileProvider("test", config)
        with patch.object(Path, "open", side_effect=OSError("denied")):
            result = await provider.aggregate(AggregateParams(source="test"))
            assert result.buckets == []
            assert result.total == 0


class TestCoverageGapAggregateHostAndUnknownField:
    """Cover aggregate host and unknown field branches (lines 421, 425-428)."""

    @pytest.mark.asyncio
    async def test_when_aggregating_by_host_then_uses_host_or_unknown(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
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
            hostField="host",
        )
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(AggregateParams(source="test", group_by=["host"]))
        assert len(result.buckets) == 1
        assert result.buckets[0].key["host"] == "unknown"

    @pytest.mark.asyncio
    async def test_when_aggregating_by_unknown_field_then_uses_unknown(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
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
        )
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["nonexistent_field"])
        )
        assert len(result.buckets) == 1
        assert result.buckets[0].key["nonexistent_field"] == "unknown"


class TestCoverageGapFilterMatches:
    """Cover _line_matches_filter returning True (lines 276-277)."""

    def test_when_all_filters_match_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True, hostField="host")
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "ERROR",
                    "message": "x",
                    "service": "payment",
                    "host": "host1",
                    "traceId": "abc123",
                    "env": "prod",
                }
            ),
            "test",
        )
        params = FilterParams(
            source="test",
            level="ERROR",
            service="payment",
            host="host1",
            trace_id="abc123",
            custom_fields={"env": "prod"},
        )
        assert provider._line_matches_filter(entry, params) is True


class TestCoverageGapSearchHostMatch:
    """Cover line 214: _line_matches_search with host match."""

    def test_when_query_matches_host_then_returns_true(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True, hostField="host")
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "host": "server01",
                }
            ),
            "test",
        )
        assert provider._line_matches_search(entry, "server01") is True


class TestCoverageGapFilterOffsetAndLimit:
    """Cover lines 370, 376-377, 380-381: filter with offset and limit."""

    @pytest.mark.asyncio
    async def test_when_filter_has_offset_and_limit_then_returns_correct_slice(self, tmp_path):
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
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.jsonl")], parseJson=True)
        provider = LocalFileProvider("test", config)
        result = await provider.filter(
            FilterParams(source="test", level="INFO", offset="3", limit=3)
        )
        assert len(result.entries) == 3
        assert result.entries[0].message == "line 3"


class TestCoverageGapAggregateFieldInExtraFields:
    """Cover line 426: aggregate with field from entry.fields."""

    @pytest.mark.asyncio
    async def test_when_aggregating_by_extra_field_then_uses_field_value(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "env": "prod",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "env": "staging",
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
        )
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(AggregateParams(source="test", group_by=["env"]))
        assert len(result.buckets) == 2


class TestCoverageGapAggregateUnknownMetric:
    """Cover line 463: aggregate with unknown metric falls back to count."""

    @pytest.mark.asyncio
    async def test_when_metric_is_unknown_then_falls_back_to_count(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                }
            )
            + "\n"
        )
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.jsonl")], parseJson=True)
        provider = LocalFileProvider("test", config)
        result = await provider.aggregate(
            AggregateParams(source="test", group_by=["level"], metric="unknown_metric")
        )
        assert len(result.buckets) == 1
        assert result.buckets[0].value == 1.0


class TestCoverageGapFilterSkipsNoneEntry:
    """Cover line 370: filter skips None entries."""

    @pytest.mark.asyncio
    async def test_when_log_file_has_blank_lines_then_skips_them(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            "\n\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "only valid line",
                }
            )
            + "\n\n"
        )
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.jsonl")], parseJson=True)
        provider = LocalFileProvider("test", config)
        result = await provider.filter(FilterParams(source="test"))
        assert len(result.entries) == 1
        assert result.entries[0].message == "only valid line"


class TestCoverageGapBucketTimestampInvalid:
    """Cover line 491: _bucket_timestamp with invalid bucket falls back to isoformat."""

    def test_when_bucket_is_invalid_then_returns_isoformat(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"])
        provider = LocalFileProvider("test", config)
        ts = datetime(2026, 5, 24, 10, 0, 0)
        result = provider._bucket_timestamp(ts, "invalid")
        assert result == ts.isoformat()


class TestCoverageGapTailSkipsNoneEntry:
    """Cover line 514: tail skips None entries."""

    @pytest.mark.asyncio
    async def test_when_log_file_has_blank_lines_then_skips_them(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            "\n\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "only valid line",
                }
            )
            + "\n\n"
        )
        config = SourceConfig(type="local", paths=[str(tmp_path / "*.jsonl")], parseJson=True)
        provider = LocalFileProvider("test", config)
        result = await provider.tail(TailParams(source="test"))
        assert len(result.entries) == 1
        assert result.entries[0].message == "only valid line"


class TestCoverageGapTimeParserInvalidDelta:
    """Cover time_parser line 63: invalid delta format."""

    def test_when_delta_has_unit_without_number_then_raises_value_error(self):
        from logintel.utils.time_parser import _parse_delta

        with pytest.raises(ValueError, match="Invalid delta format"):
            _parse_delta("hm")

    def test_when_delta_has_trailing_number_then_raises_value_error(self):
        from logintel.utils.time_parser import _parse_delta

        with pytest.raises(ValueError, match="Invalid delta format"):
            _parse_delta("1h30")


class TestCoverageGapGetSchemaWithHost:
    """Cover line 535: get_schema includes host field when configured."""

    @pytest.mark.asyncio
    async def test_when_host_field_is_configured_then_schema_includes_host(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True, hostField="host")
        provider = LocalFileProvider("test", config)
        schema = await provider.get_schema()
        field_names = [f.name for f in schema.fields]
        assert "host" in field_names


class TestCoverageGapExtractNumericError:
    """Cover lines 500-501: _extract_numeric with non-numeric field value."""

    def test_when_field_value_is_not_numeric_then_returns_none(self):
        config = SourceConfig(type="local", paths=["/tmp/*.log"], parseJson=True)
        provider = LocalFileProvider("test", config)
        entry = provider._parse_line(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "x",
                    "count": "not-a-number",
                }
            ),
            "test",
        )
        assert provider._extract_numeric(entry, "count") is None
