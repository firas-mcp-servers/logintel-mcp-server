"""Result models for LogProvider methods."""

from typing import Any

from pydantic import BaseModel, Field

from logintel.models.common import LogEntry


class SearchResult(BaseModel):
    """Result of a log search."""

    entries: list[LogEntry]
    total: int | None = None  # Total matching entries (may be estimated)
    next_offset: str | None = None  # Pagination cursor
    query_time_ms: float | None = None


class AggregateBucket(BaseModel):
    """A single bucket in an aggregation result."""

    key: dict[str, Any]  # Group-by field values
    value: float  # Aggregated metric value
    count: int  # Number of entries in bucket


class AggregateResult(BaseModel):
    """Result of a log aggregation."""

    buckets: list[AggregateBucket]
    total: int  # Total entries aggregated
    query_time_ms: float | None = None


class ErrorPattern(BaseModel):
    """A detected error pattern."""

    pattern: str  # The pattern string (can be regex or template)
    count: int
    sample_messages: list[str] = Field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None
    services: list[str] = Field(default_factory=list)


class PatternResult(BaseModel):
    """Result of error pattern detection."""

    patterns: list[ErrorPattern]
    total_errors: int
    query_time_ms: float | None = None


class AnomalyPoint(BaseModel):
    """A single anomalous data point."""

    timestamp: str
    expected_value: float | None = None
    actual_value: float
    deviation_score: float  # How anomalous (0-1+)


class AnomalyResult(BaseModel):
    """Result of anomaly detection."""

    anomalies: list[AnomalyPoint]
    metric: str
    query_time_ms: float | None = None
