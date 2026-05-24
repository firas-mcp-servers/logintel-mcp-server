"""Tests for provider registry and base classes."""

import pytest

from logintel.config import Settings, SourceConfig
from logintel.models.common import HealthStatus, SchemaInfo
from logintel.providers.registry import ProviderRegistry, StubProvider


class TestStubProvider:
    """Tests for the StubProvider placeholder."""

    @pytest.fixture
    def provider(self):
        config = SourceConfig(type="mock")
        return StubProvider("mock-source", "mock", config)

    @pytest.mark.asyncio
    async def test_id_and_type(self, provider):
        assert provider.id == "mock-source"
        assert provider.type == "mock"

    @pytest.mark.asyncio
    async def test_health_returns_unknown(self, provider):
        health = await provider.health()
        assert isinstance(health, HealthStatus)
        assert health.status == "unknown"
        assert "not yet implemented" in health.message

    @pytest.mark.asyncio
    async def test_get_schema_returns_empty(self, provider):
        schema = await provider.get_schema()
        assert isinstance(schema, SchemaInfo)
        assert schema.source == "mock-source"
        assert schema.fields == []

    @pytest.mark.asyncio
    async def test_search_raises(self, provider):
        from logintel.models import SearchParams

        with pytest.raises(NotImplementedError):
            await provider.search(SearchParams(source="mock-source", query="test"))


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    @pytest.fixture
    def settings(self):
        return Settings(
            sources={
                "local-app": SourceConfig(type="local"),
                "cloudwatch-prod": SourceConfig(type="cloudwatch"),
            }
        )

    @pytest.fixture
    def registry(self, settings):
        return ProviderRegistry(settings)

    def test_builds_providers(self, registry):
        sources = registry.list_sources()
        assert len(sources) == 2
        ids = {s["id"] for s in sources}
        assert ids == {"local-app", "cloudwatch-prod"}

    def test_get_existing(self, registry):
        provider = registry.get("local-app")
        assert provider.id == "local-app"
        assert provider.type == "local"

    def test_get_missing_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get("missing")

    def test_all_providers(self, registry):
        providers = registry.all_providers()
        assert len(providers) == 2
