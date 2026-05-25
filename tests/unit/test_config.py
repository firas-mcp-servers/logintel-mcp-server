"""Unit tests for configuration management scenarios."""

import tempfile
from pathlib import Path

from logintel.config import DefaultsConfig, IntelligenceConfig, Settings, SourceConfig


class TestSettingsFromYaml:
    """Scenarios for loading settings from YAML configuration files."""

    def test_when_yaml_file_has_sources_then_settings_contains_all_sources(self):
        """Given a YAML file with multiple sources, all sources are loaded."""
        yaml_content = """
version: "1.0"
sources:
  local-app:
    type: local
    paths:
      - "/var/log/app/*.log"
  cloudwatch-prod:
    type: cloudwatch
    region: us-east-1
    profile: production
defaults:
  timeRange: "2h"
  maxResults: 50
intelligence:
  enableCaching: false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = Settings.from_yaml(f.name)
            Path(f.name).unlink()

        assert "local-app" in settings.sources
        assert settings.sources["local-app"].type == "local"
        assert "cloudwatch-prod" in settings.sources
        assert settings.sources["cloudwatch-prod"].type == "cloudwatch"

    def test_when_yaml_file_has_defaults_then_defaults_override_built_in_values(self):
        """Given a YAML file with custom defaults, built-in defaults are overridden."""
        yaml_content = """
defaults:
  timeRange: "24h"
  maxResults: 500
  timezone: "Europe/Paris"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = Settings.from_yaml(f.name)
            Path(f.name).unlink()

        assert settings.defaults.time_range == "24h"
        assert settings.defaults.max_results == 500
        assert settings.defaults.timezone == "Europe/Paris"

    def test_when_yaml_file_does_not_exist_then_returns_default_settings(self):
        """Given a missing config file, default settings are returned without error."""
        settings = Settings.from_yaml("/nonexistent/path/config.yaml")
        assert settings.sources == {}
        assert settings.defaults.time_range == "1h"
        assert settings.defaults.max_results == 100
        assert settings.defaults.timezone == "UTC"

    def test_when_yaml_file_is_empty_then_returns_default_settings(self):
        """Given an empty YAML file, default settings are returned."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            settings = Settings.from_yaml(f.name)
            Path(f.name).unlink()

        assert settings.sources == {}

    def test_when_yaml_has_intelligence_config_then_intelligence_settings_loaded(self):
        """Given a YAML file with intelligence settings, they are parsed correctly."""
        yaml_content = """
intelligence:
  enableCaching: true
  cacheTtlSeconds: 120
  anomalySensitivity: high
  maxCorrelationDepth: 5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = Settings.from_yaml(f.name)
            Path(f.name).unlink()

        assert settings.intelligence.enable_caching is True
        assert settings.intelligence.cache_ttl_seconds == 120
        assert settings.intelligence.anomaly_sensitivity == "high"
        assert settings.intelligence.max_correlation_depth == 5

    def test_when_yaml_has_extra_provider_fields_then_fields_are_preserved(self):
        """Given a source config with extra fields, they are accessible via model."""
        yaml_content = """
sources:
  datadog-prod:
    type: datadog
    apiKey: "${DATADOG_API_KEY}"
    site: datadoghq.eu
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            settings = Settings.from_yaml(f.name)
            Path(f.name).unlink()

        datadog = settings.sources["datadog-prod"]
        assert datadog.type == "datadog"
        assert datadog.apiKey == "${DATADOG_API_KEY}"
        assert datadog.site == "datadoghq.eu"


class TestSourceConfig:
    """Scenarios for SourceConfig model behavior."""

    def test_when_created_with_type_only_then_extra_fields_are_empty(self):
        config = SourceConfig(type="local")
        assert config.type == "local"

    def test_when_created_with_extra_fields_then_fields_are_accessible(self):
        config = SourceConfig(type="local", paths=["/var/log/*.log"], parseJson=True)
        assert config.paths == ["/var/log/*.log"]
        assert config.parseJson is True


class TestDefaultsConfig:
    """Scenarios for DefaultsConfig model behavior."""

    def test_when_created_with_defaults_then_values_match_expectations(self):
        config = DefaultsConfig()
        assert config.time_range == "1h"
        assert config.max_results == 100
        assert config.timezone == "UTC"

    def test_when_created_with_custom_values_then_custom_values_preserved(self):
        config = DefaultsConfig(time_range="30m", max_results=50, timezone="PST")
        assert config.time_range == "30m"
        assert config.max_results == 50
        assert config.timezone == "PST"


class TestIntelligenceConfig:
    """Scenarios for IntelligenceConfig model behavior."""

    def test_when_created_with_defaults_then_values_match_expectations(self):
        config = IntelligenceConfig()
        assert config.enable_caching is True
        assert config.cache_ttl_seconds == 60
        assert config.anomaly_sensitivity == "medium"
        assert config.max_correlation_depth == 3
