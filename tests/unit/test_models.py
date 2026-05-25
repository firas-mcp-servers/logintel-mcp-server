"""Unit tests for Pydantic model validation scenarios."""

import pytest
from pydantic import ValidationError

from logintel.models import (
    AggregateParams,
    FilterParams,
    HealthStatus,
    LogEntry,
    SchemaField,
    SchemaInfo,
    SearchParams,
    TailParams,
    TimeRange,
)


class TestLogEntry:
    """Scenarios for LogEntry model creation and validation."""

    def test_when_created_with_required_fields_then_entry_is_valid(self):
        entry = LogEntry(
            timestamp="2026-05-24T12:00:00Z",
            level="ERROR",
            message="Connection timeout",
            source="local-app",
        )
        assert entry.level == "ERROR"
        assert entry.service is None
        assert entry.fields == {}

    def test_when_created_with_trace_and_span_ids_then_aliases_are_resolved(self):
        entry = LogEntry(
            timestamp="2026-05-24T12:00:00Z",
            level="INFO",
            message="OK",
            source="test",
            traceId="abc123",
            spanId="def456",
        )
        assert entry.trace_id == "abc123"
        assert entry.span_id == "def456"

    def test_when_created_with_extra_fields_then_fields_are_stored(self):
        entry = LogEntry(
            timestamp="2026-05-24T12:00:00Z",
            level="INFO",
            message="OK",
            source="test",
            fields={"user_id": "42", "request_path": "/api/v1/orders"},
        )
        assert entry.fields["user_id"] == "42"
        assert entry.fields["request_path"] == "/api/v1/orders"

    def test_when_level_is_lowercase_then_level_is_preserved_as_is(self):
        entry = LogEntry(
            timestamp="2026-05-24T12:00:00Z",
            level="info",
            message="test",
            source="test",
        )
        assert entry.level == "info"


class TestSearchParams:
    """Scenarios for SearchParams validation and defaults."""

    def test_when_limit_is_zero_then_validation_raises_error(self):
        with pytest.raises(ValidationError):
            SearchParams(source="test", query="error", limit=0)

    def test_when_limit_exceeds_maximum_then_validation_raises_error(self):
        with pytest.raises(ValidationError):
            SearchParams(source="test", query="error", limit=1001)

    def test_when_limit_is_within_bounds_then_params_are_valid(self):
        params = SearchParams(source="test", query="error", limit=500)
        assert params.limit == 500

    def test_when_created_with_defaults_then_limit_is_100(self):
        params = SearchParams(source="test", query="error")
        assert params.limit == 100
        assert params.offset is None

    def test_when_created_with_offset_then_offset_is_preserved(self):
        params = SearchParams(source="test", query="error", offset="50")
        assert params.offset == "50"


class TestFilterParams:
    """Scenarios for FilterParams validation and behavior."""

    def test_when_created_with_trace_id_alias_then_trace_id_is_resolved(self):
        params = FilterParams(source="test", traceId="trace-123")
        assert params.trace_id == "trace-123"

    def test_when_created_with_custom_fields_then_fields_are_preserved(self):
        params = FilterParams(source="test", custom_fields={"env": "prod", "region": "us-east-1"})
        assert params.custom_fields == {"env": "prod", "region": "us-east-1"}


class TestTailParams:
    """Scenarios for TailParams validation."""

    def test_when_lines_is_zero_then_validation_raises_error(self):
        with pytest.raises(ValidationError):
            TailParams(source="test", lines=0)

    def test_when_lines_exceeds_maximum_then_validation_raises_error(self):
        with pytest.raises(ValidationError):
            TailParams(source="test", lines=1001)

    def test_when_created_with_defaults_then_lines_is_50(self):
        params = TailParams(source="test")
        assert params.lines == 50
        assert params.follow is False


class TestAggregateParams:
    """Scenarios for AggregateParams validation."""

    def test_when_created_with_defaults_then_metric_is_count(self):
        params = AggregateParams(source="test")
        assert params.metric == "count"
        assert params.group_by == []

    def test_when_created_with_time_bucket_then_time_bucket_is_preserved(self):
        params = AggregateParams(source="test", time_bucket="5m")
        assert params.time_bucket == "5m"


class TestHealthStatus:
    """Scenarios for HealthStatus model behavior."""

    def test_when_created_with_healthy_status_then_status_is_healthy(self):
        hs = HealthStatus(source="test", status="healthy")
        assert hs.status == "healthy"
        assert hs.checked_at is not None

    def test_when_created_with_unhealthy_status_then_status_is_unhealthy(self):
        hs = HealthStatus(source="test", status="unhealthy")
        assert hs.status == "unhealthy"

    def test_when_created_with_invalid_status_then_validation_raises_error(self):
        with pytest.raises(ValidationError):
            HealthStatus(source="test", status="broken")

    def test_when_latency_is_provided_then_latency_is_stored(self):
        hs = HealthStatus(source="test", status="healthy", latency_ms=42.5)
        assert hs.latency_ms == 42.5


class TestSchemaInfo:
    """Scenarios for SchemaInfo model behavior."""

    def test_when_created_empty_then_fields_list_is_empty(self):
        schema = SchemaInfo(source="test", fields=[])
        assert schema.fields == []
        assert schema.known_formats == []

    def test_when_created_with_fields_then_fields_are_accessible(self):
        schema = SchemaInfo(
            source="test",
            fields=[
                SchemaField(name="timestamp", type="timestamp", required=True),
                SchemaField(name="level", type="string", required=False),
            ],
        )
        assert len(schema.fields) == 2
        assert schema.fields[0].name == "timestamp"
        assert schema.fields[0].required is True
        assert schema.fields[1].required is False

    def test_when_field_has_example_then_example_is_stored(self):
        field = SchemaField(name="level", type="string", example="ERROR", required=True)
        assert field.example == "ERROR"


class TestTimeRange:
    """Scenarios for TimeRange model behavior."""

    def test_when_created_with_from_and_to_then_both_fields_are_set(self):
        tr = TimeRange(from_time="now-1h", to_time="now")
        assert tr.from_time == "now-1h"
        assert tr.to_time == "now"

    def test_when_created_with_from_only_then_to_is_none(self):
        tr = TimeRange(from_time="now-1h")
        assert tr.from_time == "now-1h"
        assert tr.to_time is None
