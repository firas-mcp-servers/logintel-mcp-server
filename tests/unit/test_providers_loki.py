"""Unit tests for LokiProvider with mocked httpx."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from logintel.config import SourceConfig
from logintel.models.params import (
    AggregateParams,
    FilterParams,
    SearchParams,
    TailParams,
)
from logintel.providers.loki import LokiProvider


def _make_mock_response(status: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def provider() -> LokiProvider:
    config = SourceConfig(
        type="loki",
        url="http://localhost:3100",
        basicAuth={"username": "admin", "password": "secret"},
        tenantId="tenant-1",
        defaultLabels={"app": "api"},
    )
    return LokiProvider("loki-test", config)


class TestInit:
    def test_when_config_has_basic_auth_then_credentials_set(self):
        config = SourceConfig(
            type="loki", url="http://loki:3100", basicAuth={"username": "u", "password": "p"}
        )
        p = LokiProvider("loki-1", config)
        assert p._username == "u"
        assert p._password == "p"

    def test_when_config_has_snake_case_then_credentials_set(self):
        config = SourceConfig(
            type="loki", url="http://loki:3100", basic_auth={"username": "u", "password": "p"}
        )
        p = LokiProvider("loki-1", config)
        assert p._username == "u"
        assert p._password == "p"

    def test_when_config_has_default_labels_then_labels_set(self):
        config = SourceConfig(type="loki", defaultLabels={"env": "prod"})
        p = LokiProvider("loki-1", config)
        assert p._default_labels == {"env": "prod"}

    def test_when_config_has_no_optional_fields_then_uses_defaults(self):
        config = SourceConfig(type="loki")
        p = LokiProvider("loki-1", config)
        assert p._url == "http://localhost:3100"
        assert p._username is None
        assert p._password is None
        assert p._tenant_id is None
        assert p._default_labels == {}


class TestProperties:
    def test_id_returns_source_id(self, provider: LokiProvider):
        assert provider.id == "loki-test"

    def test_type_returns_loki(self, provider: LokiProvider):
        assert provider.type == "loki"


class TestHealth:
    @pytest.mark.asyncio
    async def test_when_ready_returns_200_then_healthy(self, provider: LokiProvider):
        mock_resp = _make_mock_response(200, {"status": "ready"})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "healthy"
        assert health.message == "Connected to Loki"

    @pytest.mark.asyncio
    async def test_when_ready_returns_503_then_degraded(self, provider: LokiProvider):
        mock_resp = _make_mock_response(503, {"status": "not ready"})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "degraded"
        assert "503" in health.message

    @pytest.mark.asyncio
    async def test_when_http_error_then_unhealthy(self, provider: LokiProvider):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        provider._client = mock_client

        health = await provider.health()
        assert health.status == "unhealthy"
        assert "Loki connection failed" in health.message


class TestSearch:
    @pytest.mark.asyncio
    async def test_when_search_succeeds_then_returns_entries(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200,
            {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {
                                "service": "api",
                                "host": "host-1",
                            },
                            "values": [
                                [
                                    "1716540000000000000",
                                    '{"message":"hello","level":"info","trace_id":"abc123"}',
                                ]
                            ],
                        }
                    ],
                },
            },
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.search(SearchParams(source="loki-test", query="hello"))
        assert len(result.entries) == 1
        assert result.entries[0].message == "hello"
        assert result.entries[0].level == "INFO"
        assert result.entries[0].service == "api"
        assert result.entries[0].host == "host-1"
        assert result.entries[0].trace_id == "abc123"
        assert result.entries[0].source == "loki"

        # Verify request params
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["direction"] == "backward"
        assert call_params["limit"] == 100
        assert call_params["query"] == '{app="api"} |= "hello"'

    @pytest.mark.asyncio
    async def test_when_search_has_plain_text_line_then_parses_raw(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200,
            {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {},
                            "values": [["1716540000000000000", "plain text log"]],
                        }
                    ],
                },
            },
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.search(SearchParams(source="loki-test", query="plain"))
        assert result.entries[0].message == "plain text log"
        assert result.entries[0].level == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_when_search_fails_then_returns_empty(self, provider: LokiProvider):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        provider._client = mock_client

        result = await provider.search(SearchParams(source="loki-test", query="error"))
        assert result.entries == []
        assert result.total == 0


class TestFilter:
    @pytest.mark.asyncio
    async def test_filter_with_level_and_service_builds_logql(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "streams", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.filter(
            FilterParams(source="loki-test", level="ERROR", service="payment")
        )
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["query"] == '{level="error",service="payment"}'

    @pytest.mark.asyncio
    async def test_filter_with_custom_fields_builds_json_pipeline(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "streams", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.filter(
            FilterParams(source="loki-test", custom_fields={"env": "prod"})
        )
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["query"] == '{app="api"} | json | env="prod"'

    @pytest.mark.asyncio
    async def test_filter_with_trace_id_builds_json_pipeline(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "streams", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.filter(FilterParams(source="loki-test", trace_id="abc123"))
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["query"] == '{app="api"} | json | trace_id="abc123"'

    @pytest.mark.asyncio
    async def test_when_filter_fails_then_returns_empty(self, provider: LokiProvider):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        provider._client = mock_client

        result = await provider.filter(FilterParams(source="loki-test"))
        assert result.entries == []


class TestAggregate:
    @pytest.mark.asyncio
    async def test_when_aggregate_count_then_builds_count_over_time(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200,
            {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"service": "api"},
                            "value": [1716540000, "42"],
                        }
                    ],
                },
            },
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.aggregate(AggregateParams(source="loki-test"))
        assert len(result.buckets) == 1
        assert result.buckets[0].value == 42.0
        assert result.buckets[0].key == {"service": "api"}

        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["query"] == 'count_over_time({app="api"}[5m])'

    @pytest.mark.asyncio
    async def test_when_aggregate_with_group_by_then_adds_sum_by(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "vector", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.aggregate(
            AggregateParams(source="loki-test", group_by=["service"])
        )
        call_params = mock_client.get.call_args.kwargs["params"]
        assert "sum by (service)" in call_params["query"]

    @pytest.mark.asyncio
    async def test_when_aggregate_matrix_result_then_sums_values(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200,
            {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"service": "api"},
                            "values": [
                                [1716540000, "10"],
                                [1716540001, "20"],
                            ],
                        }
                    ],
                },
            },
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.aggregate(AggregateParams(source="loki-test"))
        assert len(result.buckets) == 1
        assert result.buckets[0].value == 30.0
        assert result.buckets[0].count == 2

    @pytest.mark.asyncio
    async def test_when_aggregate_fails_then_returns_empty(self, provider: LokiProvider):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        provider._client = mock_client

        result = await provider.aggregate(AggregateParams(source="loki-test"))
        assert result.buckets == []
        assert result.total == 0


class TestTail:
    @pytest.mark.asyncio
    async def test_when_tail_succeeds_then_returns_recent_entries(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200,
            {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {"service": "api"},
                            "values": [
                                ["1716540000000000000", "tail line 1"],
                                ["1716540001000000000", "tail line 2"],
                            ],
                        }
                    ],
                },
            },
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        result = await provider.tail(TailParams(source="loki-test", lines=10))
        assert len(result.entries) == 2
        assert result.entries[0].message == "tail line 1"
        assert result.entries[1].message == "tail line 2"

    @pytest.mark.asyncio
    async def test_when_tail_has_filter_query_then_adds_line_filter(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "streams", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.tail(TailParams(source="loki-test", filter_query="error"))
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["query"] == '{app="api"} |= "error"'

    @pytest.mark.asyncio
    async def test_when_tail_fails_then_returns_empty(self, provider: LokiProvider):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        provider._client = mock_client

        result = await provider.tail(TailParams(source="loki-test"))
        assert result.entries == []


class TestGetSchema:
    @pytest.mark.asyncio
    async def test_labels_endpoint_succeeds_adds_discovered_labels(self, provider: LokiProvider):
        labels_resp = _make_mock_response(
            200, {"status": "success", "data": ["env", "version"]}
        )
        sample_resp = _make_mock_response(
            200,
            {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {"env": "prod"},
                            "values": [["1716540000000000000", '{"message":"sample"}']],
                        }
                    ],
                },
            },
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[labels_resp, sample_resp])
        provider._client = mock_client

        schema = await provider.get_schema()
        field_names = {f.name for f in schema.fields}
        assert "env" in field_names
        assert "version" in field_names
        assert schema.sample_log is not None
        assert schema.sample_log.message == "sample"

    @pytest.mark.asyncio
    async def test_labels_endpoint_fails_returns_basic_schema(self, provider: LokiProvider):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        provider._client = mock_client

        schema = await provider.get_schema()
        field_names = {f.name for f in schema.fields}
        assert "timestamp" in field_names
        assert "message" in field_names
        assert schema.sample_log is None

    @pytest.mark.asyncio
    async def test_sample_query_no_data_returns_schema_without_sample(
        self, provider: LokiProvider
    ):
        labels_resp = _make_mock_response(
            200, {"status": "success", "data": ["env"]}
        )
        sample_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "streams", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[labels_resp, sample_resp])
        provider._client = mock_client

        schema = await provider.get_schema()
        assert schema.sample_log is None
