"""Provider registry and factory for creating LogProvider instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from logintel.config import Settings, SourceConfig
from logintel.models.common import HealthStatus
from logintel.providers.base import LogProvider

if TYPE_CHECKING:
    pass

logger = logging.getLogger("logintel.providers")


class StubProvider(LogProvider):
    """Placeholder provider for sources that are not yet implemented."""

    def __init__(self, source_id: str, source_type: str, config: SourceConfig) -> None:
        self._id = source_id
        self._type = source_type
        self._config = config

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> str:
        return self._type

    async def health(self) -> HealthStatus:
        return HealthStatus(
            source=self._id,
            status="unknown",
            message=f"Provider '{self._type}' is not yet implemented",
        )

    async def search(self, params):  # noqa: ANN001, ANN202
        raise NotImplementedError(f"Provider '{self._type}' is not yet implemented")

    async def filter(self, params):  # noqa: ANN001, ANN202
        raise NotImplementedError(f"Provider '{self._type}' is not yet implemented")

    async def aggregate(self, params):  # noqa: ANN001, ANN202
        raise NotImplementedError(f"Provider '{self._type}' is not yet implemented")

    async def tail(self, params):  # noqa: ANN001, ANN202
        raise NotImplementedError(f"Provider '{self._type}' is not yet implemented")

    async def get_schema(self):
        from logintel.models.common import SchemaInfo

        return SchemaInfo(source=self._id, fields=[])

    async def detect_patterns(self, params):  # noqa: ANN001, ANN202
        raise NotImplementedError(f"Provider '{self._type}' is not yet implemented")

    async def find_anomalies(self, params):  # noqa: ANN001, ANN202
        raise NotImplementedError(f"Provider '{self._type}' is not yet implemented")


class ProviderRegistry:
    """Registry that holds all configured LogProvider instances."""

    def __init__(self, settings: Settings) -> None:
        self._providers: dict[str, LogProvider] = {}
        self._settings = settings
        self._build_registry()

    def _build_registry(self) -> None:
        """Instantiate providers from settings."""
        for source_id, source_config in self._settings.sources.items():
            provider = self._create_provider(source_id, source_config)
            self._providers[source_id] = provider
            logger.info("Registered provider '%s' (type=%s)", source_id, provider.type)

    def _create_provider(self, source_id: str, config: SourceConfig) -> LogProvider:
        """Factory method to create the right provider for a source config."""
        if config.type == "local":
            from logintel.providers.local import LocalFileProvider

            return LocalFileProvider(source_id, config)
        elif config.type == "cloudwatch":
            from logintel.providers.cloudwatch import CloudWatchProvider

            return CloudWatchProvider(source_id, config)
        # elif config.type == "datadog":
        #     from logintel.providers.datadog import DatadogProvider
        #     return DatadogProvider(source_id, config)
        # elif config.type == "loki":
        #     from logintel.providers.loki import LokiProvider
        #     return LokiProvider(source_id, config)
        return StubProvider(source_id, config.type, config)

    def get(self, source_id: str) -> LogProvider:
        """Get a provider by source ID."""
        if source_id not in self._providers:
            raise KeyError(f"Unknown source: {source_id}")
        return self._providers[source_id]

    def list_sources(self) -> list[dict]:
        """List all registered sources."""
        return [{"id": pid, "type": provider.type} for pid, provider in self._providers.items()]

    def all_providers(self) -> dict[str, LogProvider]:
        """Return all providers."""
        return dict(self._providers)
