"""Unit tests for DatadogProvider with mocked httpx."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from logintel.config import SourceConfig
from logintel.models.params import (
    AggregateParams,
    FilterParams,
    SearchParams,
    TailParams,
)
from logintel.providers.datadog import DatadogProvider

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_mock_response(status_code: int = 200, json_data: dict | None = None):
    """Create a mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def provider():
    config = SourceConfig(
        type="datadog",
        site="datadoghq.com",
        apiKey="test-api-key",
        appKey="test-app-key",
    )
    return DatadogProvider("dd-test", config)


# ------------------------------------------------------------------
# Properties & client lifecycle
# ------------------------------------------------------------------


class TestProperties:
    def test_when_id_property_accessed_then_returns_source_id(self):
        config = SourceConfig(type="datadog", site="datadoghq.com")
        provider = DatadogProvider("my-dd", config)
        assert provider.id == "my-dd"
        assert provider.type == "datadog"

    def test_when_get_client_called_twice_then_returns_same_instance(self, provider):
        c1 = provider._get_client()
        c2 = provider._get_client()
        assert c1 is c2


class TestGetClientConfig:
    def test_when_no_keys_then_client_has_empty_headers(self):
        config = SourceConfig(type="datadog", site="datadoghq.eu")
        provider = DatadogProvider("dd", config)
        client = provider._get_client()
        assert client.base_url == "https://api.datadoghq.eu"
        assert client.headers["DD-API-KEY"] == ""

    def test_when_keys_set_then_client_has_auth_headers(self):
        config = SourceConfig(type="datadog", site="datadoghq.com", apiKey="ak", appKey="apk")
        provider = DatadogProvider("dd", config)
        client = provider._get_client()
        assert client.headers["DD-API-KEY"] == "ak"
        assert client.headers["DD-APPLICATION-KEY"] == "apk"


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


class TestHealth:
    @pytest.mark.asyncio
    async def test_when_no_api_key_then_returns_unhealthy(self):
        config = SourceConfig(type="datadog", site="datadoghq.com")
        provider = DatadogProvider("dd", config)
        health = await provider.health()
        assert health.status == "unhealthy"
        assert "API key" in health.message

    @pytest.mark.asyncio
    async def test_when_post_returns_200_then_returns_healthy(self, provider):
        mock_resp = _make_mock_response(200, {"data": [], "meta": {}})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "healthy"
        assert "datadoghq.com" in health.message

    @pytest.mark.asyncio
    async def test_when_post_returns_401_then_returns_unhealthy(self, provider):
        mock_resp = _make_mock_response(401)
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "unhealthy"
        assert "authentication" in health.message.lower()

    @pytest.mark.asyncio
    async def test_when_post_returns_403_then_returns_unhealthy(self, provider):
        mock_resp = _make_mock_response(403)
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "unhealthy"

    @pytest.mark.asyncio
    async def test_when_post_returns_500_then_returns_degraded(self, provider):
        mock_resp = _make_mock_response(500)
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "degraded"
        assert "500" in health.message

    @pytest.mark.asyncio
    async def test_when_post_raises_then_returns_unhealthy(self, provider):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "unhealthy"
        assert "network error" in health.message


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


class TestSearch:
    @pytest.mark.asyncio
    async def test_when_search_succeeds_then_returns_entries(self, provider):
        mock_resp = _make_mock_response(
            200,
            {
                "data": [
                    {
                        "attributes": {
                            "timestamp": "2026-05-24T10:00:00Z",
                            "status": "error",
                            "service": "api",
                            "host": "i-0123",
                            "message": "Something broke",
                            "attributes": {"trace_id": "abc123"},
                            "tags": ["env:prod"],
                        },
                        "id": "1",
                        "type": "log",
                    }
                ],
                "meta": {"page": {"after": "cursor1"}},
            },
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.search(SearchParams(source="dd-test", query="error"))
        assert len(result.entries) == 1
        assert result.entries[0].level == "ERROR"
        assert result.entries[0].service == "api"
        assert result.entries[0].message == "Something broke"
        assert result.entries[0].trace_id == "abc123"
        assert result.entries[0].fields == {"env": "prod"}
        assert result.next_offset == "cursor1"

        # Verify request body
        body = mock_client.post.call_args.kwargs["json"]
        assert body["filter"]["query"] == "error"
        assert body["sort"] == "-timestamp"
        assert body["page"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_when_search_has_time_range_then_uses_range(self, provider):
        mock_resp = _make_mock_response(200, {"data": [], "meta": {}})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.search(
            SearchParams(
                source="dd-test",
                query="x",
                time_range={"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
            )
        )
        body = mock_client.post.call_args.kwargs["json"]
        assert body["filter"]["from"] == "2026-05-24T09:00:00Z"
        assert body["filter"]["to"] == "2026-05-24T11:00:00Z"

    @pytest.mark.asyncio
    async def test_when_search_raises_then_returns_empty(self, provider):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("boom"))
        provider._client = mock_client

        result = await provider.search(SearchParams(source="dd-test", query="error"))
        assert result.entries == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_when_search_has_indexes_then_passes_indexes(self, provider):
        config = SourceConfig(
            type="datadog",
            site="datadoghq.com",
            apiKey="ak",
            appKey="apk",
            defaultIndexes=["main", "prod"],
        )
        provider = DatadogProvider("dd", config)
        mock_resp = _make_mock_response(200, {"data": [], "meta": {}})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.search(SearchParams(source="dd", query="*"))
        body = mock_client.post.call_args.kwargs["json"]
        assert body["filter"]["indexes"] == ["main", "prod"]


# ------------------------------------------------------------------
# Filter
# ------------------------------------------------------------------


class TestFilter:
    @pytest.mark.asyncio
    async def test_when_filter_succeeds_then_returns_entries(self, provider):
        mock_resp = _make_mock_response(
            200,
            {
                "data": [
                    {
                        "attributes": {
                            "timestamp": "2026-05-24T10:00:00Z",
                            "status": "warn",
                            "message": "Warning",
                        },
                        "id": "2",
                        "type": "log",
                    }
                ],
                "meta": {},
            },
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.filter(FilterParams(source="dd-test", level="WARN"))
        assert len(result.entries) == 1
        assert result.entries[0].level == "WARN"

        body = mock_client.post.call_args.kwargs["json"]
        assert body["filter"]["query"] == "status:warn"

    @pytest.mark.asyncio
    async def test_when_filter_has_multiple_criteria_then_joins_with_space(self, provider):
        mock_resp = _make_mock_response(200, {"data": [], "meta": {}})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.filter(
            FilterParams(source="dd-test", level="ERROR", service="api", host="h1")
        )
        body = mock_client.post.call_args.kwargs["json"]
        assert "status:error" in body["filter"]["query"]
        assert "service:api" in body["filter"]["query"]
        assert "host:h1" in body["filter"]["query"]

    @pytest.mark.asyncio
    async def test_when_filter_raises_then_returns_empty(self, provider):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("boom"))
        provider._client = mock_client

        result = await provider.filter(FilterParams(source="dd-test"))
        assert result.entries == []


# ------------------------------------------------------------------
# Aggregate
# ------------------------------------------------------------------


class TestAggregate:
    @pytest.mark.asyncio
    async def test_when_aggregate_succeeds_then_returns_buckets(self, provider):
        mock_resp = _make_mock_response(
            200,
            {
                "data": [
                    {
                        "by": {"service": "api"},
                        "aggregations": [{"value": 42, "metric": "count"}],
                    }
                ]
            },
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.aggregate(AggregateParams(source="dd-test"))
        assert len(result.buckets) == 1
        assert result.buckets[0].value == 42.0
        assert result.buckets[0].key == {"service": "api"}

        body = mock_client.post.call_args.kwargs["json"]
        assert body["compute"]["aggregation"] == "count"
        assert body["group_by"][0]["facet"] == "timestamp"

    @pytest.mark.asyncio
    async def test_when_aggregate_has_metric_avg_then_uses_avg(self, provider):
        mock_resp = _make_mock_response(200, {"data": []})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.aggregate(AggregateParams(source="dd-test", metric="avg", field="duration"))
        body = mock_client.post.call_args.kwargs["json"]
        assert body["compute"]["aggregation"] == "avg"
        assert body["compute"]["metric"] == "duration"

    @pytest.mark.asyncio
    async def test_when_aggregate_raises_then_returns_empty(self, provider):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("boom"))
        provider._client = mock_client

        result = await provider.aggregate(AggregateParams(source="dd-test"))
        assert result.buckets == []
        assert result.total == 0


# ------------------------------------------------------------------
# Tail
# ------------------------------------------------------------------


class TestTail:
    @pytest.mark.asyncio
    async def test_when_tail_succeeds_then_returns_entries(self, provider):
        mock_resp = _make_mock_response(
            200,
            {
                "data": [
                    {
                        "attributes": {
                            "timestamp": "2026-05-24T10:00:00Z",
                            "status": "info",
                            "message": "hello",
                        },
                        "id": "3",
                        "type": "log",
                    }
                ]
            },
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.tail(TailParams(source="dd-test"))
        assert len(result.entries) == 1
        assert result.entries[0].level == "INFO"

        body = mock_client.post.call_args.kwargs["json"]
        assert body["filter"]["from"] == "now-5m"
        assert body["page"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_when_tail_has_filter_query_then_uses_query(self, provider):
        mock_resp = _make_mock_response(200, {"data": [], "meta": {}})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.tail(TailParams(source="dd-test", filter_query="error"))
        body = mock_client.post.call_args.kwargs["json"]
        assert body["filter"]["query"] == "error"

    @pytest.mark.asyncio
    async def test_when_tail_raises_then_returns_empty(self, provider):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("boom"))
        provider._client = mock_client

        result = await provider.tail(TailParams(source="dd-test"))
        assert result.entries == []


# ------------------------------------------------------------------
# Get Schema
# ------------------------------------------------------------------


class TestGetSchema:
    @pytest.mark.asyncio
    async def test_when_get_schema_succeeds_then_returns_fields_and_sample(self, provider):
        mock_resp = _make_mock_response(
            200,
            {
                "data": [
                    {
                        "attributes": {
                            "timestamp": "2026-05-24T10:00:00Z",
                            "status": "info",
                            "message": "x",
                            "service": "api",
                        },
                        "id": "1",
                        "type": "log",
                    }
                ]
            },
        )
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        schema = await provider.get_schema()
        assert schema.source == "dd-test"
        assert any(f.name == "timestamp" for f in schema.fields)
        assert schema.sample_log is not None

    @pytest.mark.asyncio
    async def test_when_get_schema_returns_empty_then_returns_basic_fields(self, provider):
        mock_resp = _make_mock_response(200, {"data": []})
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        schema = await provider.get_schema()
        assert schema.source == "dd-test"
        assert schema.sample_log is None

    @pytest.mark.asyncio
    async def test_when_get_schema_raises_then_returns_basic_fields(self, provider):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("boom"))
        provider._client = mock_client

        schema = await provider.get_schema()
        assert schema.source == "dd-test"
        assert schema.sample_log is None


# ------------------------------------------------------------------
# Stubs
# ------------------------------------------------------------------


class TestDetectPatterns:
    @pytest.mark.asyncio
    async def test_returns_empty_patterns(self, provider):
        from logintel.models.params import PatternParams

        result = await provider.detect_patterns(PatternParams(source="dd-test"))
        assert result.patterns == []
        assert result.total_errors == 0


class TestFindAnomalies:
    @pytest.mark.asyncio
    async def test_returns_empty_anomalies(self, provider):
        from logintel.models.params import AnomalyParams

        result = await provider.find_anomalies(AnomalyParams(source="dd-test"))
        assert result.anomalies == []
        assert result.metric == "log_volume"
