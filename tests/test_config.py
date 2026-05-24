"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest

from logintel.config import DefaultsConfig, Settings, SourceConfig


class TestSettings:
    """Tests for the Settings class."""

    def test_load_from_yaml(self):
        """Test loading settings from a YAML file."""
        yaml_content = """
version: "1.0"
sources:
  local-app:
    type: local
    paths:
      - "/var/log/app/*.log"
defaults:
  timeRange: "2h"
  maxResults: 50
intelligence:
  enableCaching: false
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()

            settings = Settings.from_yaml(f.name)

        assert "local-app" in settings.sources
        assert settings.sources["local-app"].type == "local"
        assert settings.defaults.time_range == "2h"
        assert settings.defaults.max_results == 50
        assert settings.intelligence.enable_caching is False

        Path(f.name).unlink()

    def test_missing_file_returns_defaults(self):
        """Test that a missing config file returns default settings."""
        settings = Settings.from_yaml("/nonexistent/path.yaml")
        assert settings.sources == {}
        assert settings.defaults.time_range == "1h"
