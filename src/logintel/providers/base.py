"""Base LogProvider interface — all backends must implement this."""

from abc import ABC, abstractmethod

from logintel.models.common import HealthStatus, SchemaInfo
from logintel.models.params import (
    AggregateParams,
    AnomalyParams,
    FilterParams,
    PatternParams,
    SearchParams,
    TailParams,
)
from logintel.models.results import (
    AggregateResult,
    AnomalyResult,
    PatternResult,
    SearchResult,
)


class LogProvider(ABC):
    """Abstract base class for all log backends."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique provider instance identifier."""

    @property
    @abstractmethod
    def type(self) -> str:
        """Provider type (e.g., 'local', 'cloudwatch', 'datadog', 'loki')."""

    @abstractmethod
    async def health(self) -> HealthStatus:
        """Check connectivity and health of this provider."""

    @abstractmethod
    async def search(self, params: SearchParams) -> SearchResult:
        """Search logs using a query string."""

    @abstractmethod
    async def filter(self, params: FilterParams) -> SearchResult:
        """Filter logs by structured criteria."""

    @abstractmethod
    async def aggregate(self, params: AggregateParams) -> AggregateResult:
        """Aggregate/group logs."""

    @abstractmethod
    async def tail(self, params: TailParams) -> SearchResult:
        """Tail/follow logs in real-time."""

    @abstractmethod
    async def get_schema(self) -> SchemaInfo:
        """Get field/schema info for this provider's logs."""

    @abstractmethod
    async def detect_patterns(self, params: PatternParams) -> PatternResult:
        """Detect recurring error patterns."""

    @abstractmethod
    async def find_anomalies(self, params: AnomalyParams) -> AnomalyResult:
        """Find statistical anomalies."""

    async def native_query(self, query: str) -> SearchResult:
        """Optional: execute a provider-native query directly."""
        raise NotImplementedError(f"{self.type} does not support native_query")

    async def explain_query(self, query: str) -> str:
        """Optional: explain what a provider-native query does."""
        raise NotImplementedError(f"{self.type} does not support explain_query")
