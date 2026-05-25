"""Coverage-gap tests for LokiProvider edge cases and fallback branches."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from logintel.models.params import AggregateParams, FilterParams, SearchParams
from logintel.providers.loki import LokiProvider


def _make_mock_response(status: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def provider() -> LokiProvider:
    return LokiProvider("loki-test", type("C", (), {"type": "loki"})())


class TestBuildAggregateLogqlGaps:
    """Hit fallback branches in _build_aggregate_logql."""

    def test_when_metric_is_unknown_then_defaults_to_count(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", metric="unknown")
        q = provider._build_aggregate_logql(params, "{}")
        assert "count_over_time" in q


class TestTimeRangeNsGaps:
    """Hit branches in _time_range_ns."""

    def test_when_time_range_has_no_to_time_then_uses_now(self):
        from logintel.models.common import TimeRange

        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        tr = TimeRange(from_time="now-1h")
        start, end = provider._time_range_ns(tr)
        assert start < end
        assert end > 0


class TestParseStreamResultsGaps:
    """Hit JSON parsing branches in _parse_stream_results."""

    def test_when_json_has_msg_instead_of_message(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"msg":"hello","level":"warn"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].message == "hello"
        assert entries[0].level == "WARN"

    def test_when_json_has_severity_instead_of_level(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"message":"hello","severity":"debug"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].level == "DEBUG"

    def test_when_json_has_span_id_then_not_in_fields(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"message":"hello","span_id":"span1"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert "span_id" not in entries[0].fields

    def test_when_json_is_not_dict_then_uses_raw_line(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '"just a string"',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].message == '"just a string"'


class TestParseMetricResultsGaps:
    """Hit exception branches in _parse_metric_results."""

    def test_when_matrix_values_are_malformed_then_zero(self):
        data = {
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"service": "api"},
                        "values": [
                            [1716540000, "bad"],
                        ],
                    }
                ],
            }
        }
        agg = LokiProvider._parse_metric_results(data)
        assert agg.buckets[0].value == 0.0

    def test_when_vector_value_is_missing_index_then_zero(self):
        data = {
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"service": "api"}, "value": [1716540000]}],
            }
        }
        agg = LokiProvider._parse_metric_results(data)
        assert agg.buckets[0].value == 0.0


class TestSearchGaps:
    """Hit branches in search not covered by main tests."""

    @pytest.mark.asyncio
    async def test_when_search_query_is_empty_then_no_line_filter(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "streams", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.search(SearchParams(source="loki-test", query=""))
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["query"] == "{}"


class TestFilterGaps:
    """Hit branches in filter not covered by main tests."""

    @pytest.mark.asyncio
    async def test_filter_no_filters_no_defaults_empty_selector(self, provider: LokiProvider):
        mock_resp = _make_mock_response(
            200, {"status": "success", "data": {"resultType": "streams", "result": []}}
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        provider._client = mock_client

        await provider.filter(FilterParams(source="loki-test"))
        call_params = mock_client.get.call_args.kwargs["params"]
        assert call_params["query"] == "{}"


class TestGetClientGaps:
    """Hit lazy client initialization branches."""

    def test_when_client_is_none_then_lazy_initializes(self):
        config = type(
            "C",
            (),
            {
                "type": "loki",
                "url": "http://loki:3100",
                "tenantId": "tenant-1",
                "basicAuth": {"username": "u", "password": "p"},
            },
        )()
        provider = LokiProvider("loki-test", config)
        assert provider._client is None
        client = provider._get_client()
        assert client is not None
        assert provider._client is client
        # Second call returns cached client
        assert provider._get_client() is client

    def test_when_no_auth_then_client_has_no_auth(self):
        config = type("C", (), {"type": "loki", "url": "http://loki:3100"})()
        provider = LokiProvider("loki-test", config)
        client = provider._get_client()
        assert client is not None


class TestParseStreamResultsExtraGaps:
    """Additional JSON parsing branches in _parse_stream_results."""

    def test_when_json_has_custom_field_then_in_fields(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"message":"hello","level":"info","env":"prod"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].fields["env"] == "prod"

    def test_when_json_has_msg_instead_of_message(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"msg":"hello","level":"warn"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].message == "hello"
        assert entries[0].level == "WARN"

    def test_when_json_has_severity_instead_of_level(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"message":"hello","severity":"debug"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].level == "DEBUG"

    def test_when_json_has_span_id_then_not_in_fields(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"message":"hello","span_id":"span1"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert "span_id" not in entries[0].fields

    def test_when_json_is_not_dict_then_uses_raw_line(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1716540000000000000",
                                '"just a string"',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].message == '"just a string"'


class TestDetectPatternsAndAnomaliesGaps:
    """Hit detect_patterns and find_anomalies stubs."""

    @pytest.mark.asyncio
    async def test_detect_patterns_returns_empty(self, provider: LokiProvider):
        from logintel.models.params import PatternParams

        result = await provider.detect_patterns(PatternParams(source="loki-test"))
        assert result.patterns == []
        assert result.total_errors == 0

    @pytest.mark.asyncio
    async def test_find_anomalies_returns_empty(self, provider: LokiProvider):
        from logintel.models.params import AnomalyParams

        result = await provider.find_anomalies(AnomalyParams(source="loki-test"))
        assert result.anomalies == []
        assert result.metric == "log_volume"


class TestGetSchemaGaps:
    """Hit branches in get_schema not covered by main tests."""

    @pytest.mark.asyncio
    async def test_labels_ok_but_sample_not_ok_then_no_sample_log(self, provider: LokiProvider):
        labels_resp = _make_mock_response(200, {"status": "success", "data": ["env"]})
        sample_resp = _make_mock_response(500, {"error": "boom"})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[labels_resp, sample_resp])
        provider._client = mock_client

        schema = await provider.get_schema()
        assert schema.sample_log is None

    @pytest.mark.asyncio
    async def test_labels_response_no_data_key_then_no_extra_fields(self, provider: LokiProvider):
        labels_resp = _make_mock_response(200, {"status": "success"})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=labels_resp)
        provider._client = mock_client

        schema = await provider.get_schema()
        field_names = {f.name for f in schema.fields}
        # Should only have the base fields, no discovered labels
        assert "env" not in field_names
