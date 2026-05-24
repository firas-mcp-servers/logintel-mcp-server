"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from logintel.models import (
    HealthStatus,
    LogEntry,
    SchemaField,
    SchemaInfo,
    SearchParams,
)


class TestLogEntry:
    """Tests for the LogEntry model."""

    def test_valid_entry(self):
        entry = LogEntry(
            timestamp="2026-05-24T12:00:00Z",
            level="ERROR",
            message="Connection timeout",
            source="local-app",
        )
        assert entry.level == "ERROR"
        assert entry.service is None
        assert entry.fields == {}

    def test_alias_fields(self):
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


class TestSearchParams:
    """Tests for SearchParams validation."""

    def test_limit_bounds(self):
        with pytest.raises(ValidationError):
            SearchParams(source="test", query="error", limit=0)

        with pytest.raises(ValidationError):
            SearchParams(source="test", query="error", limit=1001)

        params = SearchParams(source="test", query="error", limit=500)
        assert params.limit == 500


class TestHealthStatus:
    """Tests for HealthStatus."""

    def test_valid_status(self):
        hs = HealthStatus(source="test", status="healthy")
        assert hs.status == "healthy"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            HealthStatus(source="test", status="broken")


class TestSchemaInfo:
    """Tests for SchemaInfo."""

    def test_empty_schema(self):
        schema = SchemaInfo(source="test", fields=[])
        assert schema.fields == []

    def test_with_fields(self):
        schema = SchemaInfo(
            source="test",
            fields=[
                SchemaField(name="timestamp", type="timestamp", required=True),
                SchemaField(name="level", type="string", required=False),
            ],
        )
        assert len(schema.fields) == 2
        assert schema.fields[0].name == "timestamp"
