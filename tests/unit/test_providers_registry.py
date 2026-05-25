"""Unit tests for ProviderRegistry scenarios."""

import pytest

from logintel.config import Settings, SourceConfig
from logintel.providers.cloudwatch import CloudWatchProvider
from logintel.providers.local import LocalFileProvider
from logintel.providers.registry import ProviderRegistry, StubProvider


class TestProviderRegistryBuild:
    """Scenarios for building the provider registry from settings."""

    def test_when_settings_have_local_source_then_registry_creates_local_provider(self):
        settings = Settings(
            sources={
                "local-app": SourceConfig(type="local", paths=["/var/log/*.log"]),
            }
        )
        registry = ProviderRegistry(settings)
        provider = registry.get("local-app")
        assert isinstance(provider, LocalFileProvider)
        assert provider.type == "local"

    def test_when_settings_have_cloudwatch_source_then_registry_creates_cloudwatch_provider(self):
        settings = Settings(
            sources={
                "cloudwatch-prod": SourceConfig(type="cloudwatch", region="us-east-1"),
            }
        )
        registry = ProviderRegistry(settings)
        provider = registry.get("cloudwatch-prod")
        assert isinstance(provider, CloudWatchProvider)
        assert provider.type == "cloudwatch"

    def test_when_settings_have_multiple_sources_then_all_are_registered(self):
        settings = Settings(
            sources={
                "local-app": SourceConfig(type="local", paths=["/var/log/*.log"]),
                "cloudwatch-prod": SourceConfig(type="cloudwatch"),
                "datadog-prod": SourceConfig(type="datadog"),
            }
        )
        registry = ProviderRegistry(settings)
        sources = registry.list_sources()
        assert len(sources) == 3
        ids = {s["id"] for s in sources}
        assert ids == {"local-app", "cloudwatch-prod", "datadog-prod"}

    def test_when_settings_are_empty_then_registry_is_empty(self):
        settings = Settings()
        registry = ProviderRegistry(settings)
        assert registry.list_sources() == []


class TestProviderRegistryGet:
    """Scenarios for retrieving providers from the registry."""

    def test_when_getting_existing_source_then_returns_correct_provider(self):
        settings = Settings(
            sources={"local-app": SourceConfig(type="local", paths=["/var/log/*.log"])}
        )
        registry = ProviderRegistry(settings)
        provider = registry.get("local-app")
        assert provider.id == "local-app"

    def test_when_getting_missing_source_then_raises_key_error(self):
        settings = Settings()
        registry = ProviderRegistry(settings)
        with pytest.raises(KeyError, match="Unknown source: missing"):
            registry.get("missing")


class TestProviderRegistryAllProviders:
    """Scenarios for retrieving all providers."""

    def test_when_registry_has_providers_then_all_providers_returns_dict(self):
        settings = Settings(
            sources={"local-app": SourceConfig(type="local", paths=["/var/log/*.log"])}
        )
        registry = ProviderRegistry(settings)
        providers = registry.all_providers()
        assert "local-app" in providers


class TestProviderRegistryLoki:
    """Scenarios for Loki provider registration."""

    def test_when_type_is_loki_then_returns_loki_provider(self):
        settings = Settings(
            sources={"loki-app": SourceConfig(type="loki", url="http://loki:3100")}
        )
        registry = ProviderRegistry(settings)
        provider = registry.get("loki-app")
        assert provider.type == "loki"


class TestProviderRegistryUnknownType:
    """Scenarios for unknown source types falling back to StubProvider."""

    def test_when_type_is_unknown_then_returns_stub_provider(self):
        settings = Settings(sources={"unknown-app": SourceConfig(type="splunk")})
        registry = ProviderRegistry(settings)
        provider = registry.get("unknown-app")
        assert provider.type == "splunk"


class TestStubProvider:
    """Scenarios for the StubProvider placeholder."""

    @pytest.fixture
    def provider(self):
        config = SourceConfig(type="mock")
        return StubProvider("mock-source", "mock", config)

    def test_when_accessing_id_then_returns_source_id(self, provider):
        assert provider.id == "mock-source"

    def test_when_accessing_type_then_returns_provider_type(self, provider):
        assert provider.type == "mock"

    @pytest.mark.asyncio
    async def test_when_health_is_called_then_returns_unknown_status(self, provider):
        health = await provider.health()
        assert health.status == "unknown"
        assert "not yet implemented" in health.message

    @pytest.mark.asyncio
    async def test_when_get_schema_is_called_then_returns_empty_schema(self, provider):
        schema = await provider.get_schema()
        assert schema.source == "mock-source"
        assert schema.fields == []

    @pytest.mark.asyncio
    async def test_when_search_is_called_then_raises_not_implemented(self, provider):
        from logintel.models import SearchParams

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await provider.search(SearchParams(source="mock-source", query="test"))

    @pytest.mark.asyncio
    async def test_when_filter_is_called_then_raises_not_implemented(self, provider):
        from logintel.models import FilterParams

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await provider.filter(FilterParams(source="mock-source"))

    @pytest.mark.asyncio
    async def test_when_aggregate_is_called_then_raises_not_implemented(self, provider):
        from logintel.models import AggregateParams

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await provider.aggregate(AggregateParams(source="mock-source"))

    @pytest.mark.asyncio
    async def test_when_tail_is_called_then_raises_not_implemented(self, provider):
        from logintel.models import TailParams

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await provider.tail(TailParams(source="mock-source"))

    @pytest.mark.asyncio
    async def test_when_detect_patterns_is_called_then_raises_not_implemented(self, provider):
        from logintel.models import PatternParams

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await provider.detect_patterns(PatternParams(source="mock-source"))

    @pytest.mark.asyncio
    async def test_when_find_anomalies_is_called_then_raises_not_implemented(self, provider):
        from logintel.models import AnomalyParams

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await provider.find_anomalies(AnomalyParams(source="mock-source"))
