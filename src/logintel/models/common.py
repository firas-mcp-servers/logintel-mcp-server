"""Common Pydantic models used across LogIntel."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class LogLevel(str, Enum):
    """Standard log levels."""

    ERROR = "ERROR"
    WARN = "WARN"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"


class TimeRange(BaseModel):
    """Time range for queries."""

    from_time: str
    to_time: str | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _map_aliases(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if "from" in data:
                data["from_time"] = data.pop("from")
            if "to" in data:
                data["to_time"] = data.pop("to")
        return data


class LogEntry(BaseModel):
    """Standardized log entry format."""

    timestamp: str  # ISO 8601
    level: str  # ERROR, WARN, INFO, DEBUG, TRACE
    message: str  # Raw or rendered message
    service: str | None = None  # Service name
    host: str | None = None  # Host/container
    trace_id: str | None = None
    span_id: str | None = None
    source: str  # Source ID
    fields: dict[str, Any] = Field(default_factory=dict)  # Extracted structured fields
    raw: Any | None = None  # Provider-specific raw data

    model_config = {"populate_by_name": True}


class HealthStatus(BaseModel):
    """Health check result for a log source."""

    source: str
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    message: str | None = None
    latency_ms: float | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SchemaField(BaseModel):
    """Description of a field in a log source schema."""

    name: str
    type: str  # string, number, boolean, timestamp, etc.
    description: str | None = None
    example: Any | None = None
    required: bool = False


class SchemaInfo(BaseModel):
    """Schema information for a log source."""

    source: str
    fields: list[SchemaField]
    known_formats: list[str] = Field(default_factory=list)
    sample_log: LogEntry | None = None
