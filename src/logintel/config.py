"""Configuration management for LogIntel."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class SourceConfig(BaseModel):
    """Configuration for a single log source."""

    type: str
    # Additional fields are provider-specific and validated at runtime
    model_config = {"extra": "allow"}


class DefaultsConfig(BaseModel):
    """Default settings for queries."""

    time_range: str = Field(default="1h", alias="timeRange")
    max_results: int = Field(default=100, alias="maxResults")
    timezone: str = "UTC"


class IntelligenceConfig(BaseModel):
    """Intelligence layer settings."""

    enable_caching: bool = Field(default=True, alias="enableCaching")
    cache_ttl_seconds: int = Field(default=60, alias="cacheTtlSeconds")
    anomaly_sensitivity: str = Field(default="medium", alias="anomalySensitivity")
    max_correlation_depth: int = Field(default=3, alias="maxCorrelationDepth")


class Settings(BaseSettings):
    """Application settings."""

    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    intelligence: IntelligenceConfig = Field(default_factory=IntelligenceConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "Settings":
        """Load settings from a YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            return cls()

        with file_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Strip top-level "version" key if present
        data.pop("version", None)
        return cls(**data)
