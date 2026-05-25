"""Unit tests for LokiProvider helper methods (pure functions)."""

from logintel.models.params import AggregateParams, FilterParams, SearchParams
from logintel.providers.loki import LokiProvider


class TestToNs:
    """Cover _to_ns static method."""

    def test_when_now_then_returns_positive_ns(self):
        ns = LokiProvider._to_ns("now")
        assert ns > 0

    def test_when_relative_time_then_returns_earlier_ns(self):
        now_ns = LokiProvider._to_ns("now")
        past_ns = LokiProvider._to_ns("now-1h")
        assert past_ns < now_ns

    def test_when_iso_string_then_parses(self):
        ns = LokiProvider._to_ns("2024-05-24T10:00:00Z")
        assert ns == 1716544800000000000


class TestBuildLabelSelector:
    """Cover _build_label_selector method."""

    def test_when_no_labels_then_returns_empty_braces(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        assert provider._build_label_selector() == "{}"

    def test_when_default_labels_then_returns_selector(self):
        provider = LokiProvider(
            "test", type("C", (), {"type": "loki", "defaultLabels": {"app": "api"}})()
        )
        assert provider._build_label_selector() == '{app="api"}'

    def test_when_extra_labels_then_merges(self):
        provider = LokiProvider(
            "test", type("C", (), {"type": "loki", "defaultLabels": {"app": "api"}})()
        )
        assert provider._build_label_selector({"env": "prod"}) == '{app="api",env="prod"}'


class TestBuildSearchLogql:
    """Cover _build_search_logql static method."""

    def test_when_query_has_text_then_adds_contains_filter(self):
        params = SearchParams(source="test", query="error")
        assert LokiProvider._build_search_logql(params, "{}") == '{} |= "error"'

    def test_when_query_is_empty_then_returns_selector_only(self):
        params = SearchParams(source="test", query="")
        assert LokiProvider._build_search_logql(params, "{}") == "{}"

    def test_when_query_has_quotes_then_escapes_them(self):
        params = SearchParams(source="test", query='say "hello"')
        assert '\\"' in LokiProvider._build_search_logql(params, "{}")


class TestBuildFilterLogql:
    """Cover _build_filter_logql static method."""

    def test_when_no_filters_then_returns_selector(self):
        params = FilterParams(source="test")
        assert LokiProvider._build_filter_logql(params, '{app="api"}') == '{app="api"}'

    def test_when_level_then_adds_level_label(self):
        params = FilterParams(source="test", level="ERROR")
        assert LokiProvider._build_filter_logql(params, "{}") == '{level="error"}'

    def test_when_service_then_adds_service_label(self):
        params = FilterParams(source="test", service="payment")
        assert LokiProvider._build_filter_logql(params, "{}") == '{service="payment"}'

    def test_when_host_then_adds_host_label(self):
        params = FilterParams(source="test", host="server01")
        assert LokiProvider._build_filter_logql(params, "{}") == '{host="server01"}'

    def test_when_multiple_filters_then_joins_labels(self):
        params = FilterParams(source="test", level="ERROR", service="api")
        q = LokiProvider._build_filter_logql(params, "{}")
        assert 'level="error"' in q
        assert 'service="api"' in q

    def test_when_custom_fields_then_adds_json_pipeline(self):
        params = FilterParams(source="test", custom_fields={"env": "prod"})
        q = LokiProvider._build_filter_logql(params, '{app="api"}')
        assert "| json" in q
        assert '| env="prod"' in q

    def test_when_trace_id_then_adds_json_pipeline(self):
        params = FilterParams(source="test", trace_id="abc123")
        q = LokiProvider._build_filter_logql(params, '{app="api"}')
        assert "| json" in q
        assert '| trace_id="abc123"' in q


class TestBuildAggregateLogql:
    """Cover _build_aggregate_logql method."""

    def test_when_count_then_count_over_time(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test")
        q = provider._build_aggregate_logql(params, '{app="api"}')
        assert q == 'count_over_time({app="api"}[5m])'

    def test_when_avg_then_avg_over_time(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", metric="avg")
        q = provider._build_aggregate_logql(params, "{}")
        assert "avg_over_time" in q

    def test_when_sum_then_sum_over_time(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", metric="sum")
        q = provider._build_aggregate_logql(params, "{}")
        assert "sum_over_time" in q

    def test_when_min_then_min_over_time(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", metric="min")
        q = provider._build_aggregate_logql(params, "{}")
        assert "min_over_time" in q

    def test_when_max_then_max_over_time(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", metric="max")
        q = provider._build_aggregate_logql(params, "{}")
        assert "max_over_time" in q

    def test_when_custom_time_bucket_then_uses_it(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", time_bucket="1m")
        q = provider._build_aggregate_logql(params, "{}")
        assert "[1m]" in q

    def test_when_group_by_service_then_adds_sum_by(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", group_by=["service"])
        q = provider._build_aggregate_logql(params, "{}")
        assert "sum by (service)" in q

    def test_when_group_by_timestamp_bucket_then_skips_it(self):
        provider = LokiProvider("test", type("C", (), {"type": "loki"})())
        params = AggregateParams(source="test", group_by=["timestamp_bucket"])
        q = provider._build_aggregate_logql(params, "{}")
        assert "sum by" not in q


class TestParseStreamResults:
    """Cover _parse_stream_results static method."""

    def test_when_json_log_then_extracts_fields(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {"service": "api"},
                        "values": [
                            [
                                "1716540000000000000",
                                '{"message":"hello","level":"info","trace_id":"abc"}',
                            ]
                        ],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert len(entries) == 1
        assert entries[0].message == "hello"
        assert entries[0].level == "INFO"
        assert entries[0].trace_id == "abc"
        assert entries[0].service == "api"
        assert entries[0].source == "loki"

    def test_when_plain_text_then_raw_message(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [["1716540000000000000", "plain text"]],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].message == "plain text"
        assert entries[0].level == "UNKNOWN"

    def test_when_empty_data_then_returns_empty(self):
        entries = LokiProvider._parse_stream_results({"data": {"result": []}})
        assert entries == []

    def test_when_stream_labels_preserved_in_fields(self):
        data = {
            "data": {
                "result": [
                    {
                        "stream": {"env": "prod", "version": "1.0"},
                        "values": [["1716540000000000000", "log"]],
                    }
                ]
            }
        }
        entries = LokiProvider._parse_stream_results(data)
        assert entries[0].fields["env"] == "prod"
        assert entries[0].fields["version"] == "1.0"


class TestParseMetricResults:
    """Cover _parse_metric_results static method."""

    def test_when_vector_result_then_parses(self):
        data = {
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"service": "api"}, "value": [1716540000, "42"]}],
            }
        }
        agg = LokiProvider._parse_metric_results(data)
        assert len(agg.buckets) == 1
        assert agg.buckets[0].value == 42.0
        assert agg.buckets[0].key == {"service": "api"}

    def test_when_matrix_result_then_sums(self):
        data = {
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
            }
        }
        agg = LokiProvider._parse_metric_results(data)
        assert agg.buckets[0].value == 30.0
        assert agg.buckets[0].count == 2

    def test_when_empty_result_then_returns_empty(self):
        agg = LokiProvider._parse_metric_results({"data": {"resultType": "vector", "result": []}})
        assert agg.buckets == []
        assert agg.total == 0

    def test_when_unknown_result_type_then_returns_empty(self):
        agg = LokiProvider._parse_metric_results({"data": {"resultType": "streams", "result": []}})
        assert agg.buckets == []

    def test_when_vector_value_malformed_then_zero(self):
        data = {
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"service": "api"}, "value": [1716540000, "bad"]}],
            }
        }
        agg = LokiProvider._parse_metric_results(data)
        assert agg.buckets[0].value == 0.0
