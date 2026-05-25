"""Parameter models for LogProvider methods."""

from typing import Any

from pydantic import BaseModel, Field

from logintel.models.common import TimeRange


class SearchParams(BaseModel):
    """Parameters for searching logs."""

    source: str
    query: str
    time_range: TimeRange | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: str | None = None  # Pagination cursor


class FilterParams(BaseModel):
    """Parameters for filtering logs."""

    source: str
    time_range: TimeRange | None = None
    level: str | None = None
    service: str | None = None
    host: str | None = None
    trace_id: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=1000)
    offset: str | None = None

    model_config = {"populate_by_name": True}


class AggregateParams(BaseModel):
    """Parameters for aggregating logs."""

    source: str
    time_range: TimeRange | None = None
    group_by: list[str] = Field(default_factory=list)
    metric: str = "count"  # count, avg, sum, min, max
    field: str | None = None  # Field to aggregate on (for avg/sum/etc.)
    time_bucket: str | None = None  # e.g., "1m", "5m", "1h"
    limit: int = Field(default=100, ge=1, le=1000)


class TailParams(BaseModel):
    """Parameters for tailing logs."""

    source: str
    lines: int = Field(default=50, ge=1, le=1000)
    follow: bool = False  # True = stream indefinitely
    filter_query: str | None = None


class PatternParams(BaseModel):
    """Parameters for error pattern detection."""

    source: str
    time_range: TimeRange | None = None
    service: str | None = None
    min_occurrences: int = Field(default=5, ge=1)


class AnomalyParams(BaseModel):
    """Parameters for anomaly detection."""

    source: str
    time_range: TimeRange | None = None
    metric: str = "log_volume"  # log_volume, error_rate, latency
    sensitivity: str = "medium"  # low, medium, high
