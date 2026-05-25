"""Unit tests for DatadogProvider helper methods (pure functions)."""

from logintel.models.params import AggregateParams, FilterParams, SearchParams
from logintel.providers.datadog import DatadogProvider


class TestBuildSearchQuery:
    """Cover _build_search_query static method."""

    def test_when_query_has_keyword_then_returns_keyword(self):
        params = SearchParams(source="test", query="error")
        query = DatadogProvider._build_search_query(params)
        assert query == "error"

    def test_when_query_is_empty_then_returns_wildcard(self):
        params = SearchParams(source="test", query="")
        query = DatadogProvider._build_search_query(params)
        assert query == "*"


class TestBuildFilterQuery:
    """Cover _build_filter_query static method."""

    def test_when_no_filters_then_returns_wildcard(self):
        params = FilterParams(source="test")
        query = DatadogProvider._build_filter_query(params)
        assert query == "*"

    def test_when_level_is_set_then_contains_status(self):
        params = FilterParams(source="test", level="ERROR")
        query = DatadogProvider._build_filter_query(params)
        assert query == "status:error"

    def test_when_service_is_set_then_contains_service(self):
        params = FilterParams(source="test", service="payment")
        query = DatadogProvider._build_filter_query(params)
        assert query == "service:payment"

    def test_when_host_is_set_then_contains_host(self):
        params = FilterParams(source="test", host="server01")
        query = DatadogProvider._build_filter_query(params)
        assert query == "host:server01"

    def test_when_trace_id_is_set_then_contains_trace_id(self):
        params = FilterParams(source="test", trace_id="abc123")
        query = DatadogProvider._build_filter_query(params)
        assert query == "@trace_id:abc123"

    def test_when_custom_fields_are_set_then_contains_at_fields(self):
        params = FilterParams(source="test", custom_fields={"env": "prod"})
        query = DatadogProvider._build_filter_query(params)
        assert query == "@env:prod"

    def test_when_multiple_filters_then_joins_with_space(self):
        params = FilterParams(source="test", level="ERROR", service="api")
        query = DatadogProvider._build_filter_query(params)
        assert "status:error" in query
        assert "service:api" in query
        assert " " in query


class TestBuildAggregateBody:
    """Cover _build_aggregate_body static method."""

    def test_when_default_params_then_count_by_timestamp(self):
        params = AggregateParams(source="test")
        body = DatadogProvider._build_aggregate_body(params)
        assert body["compute"]["aggregation"] == "count"
        assert body["group_by"][0]["facet"] == "timestamp"

    def test_when_group_by_service_then_uses_service_facet(self):
        params = AggregateParams(source="test", group_by=["service"])
        body = DatadogProvider._build_aggregate_body(params)
        assert body["group_by"][0]["facet"] == "service"

    def test_when_group_by_level_then_uses_status_facet(self):
        params = AggregateParams(source="test", group_by=["level"])
        body = DatadogProvider._build_aggregate_body(params)
        assert body["group_by"][0]["facet"] == "status"

    def test_when_group_by_timestamp_bucket_then_uses_timestamp(self):
        params = AggregateParams(source="test", group_by=["timestamp_bucket"])
        body = DatadogProvider._build_aggregate_body(params)
        assert body["group_by"][0]["facet"] == "timestamp"

    def test_when_metric_is_avg_then_uses_avg(self):
        params = AggregateParams(source="test", metric="avg", field="duration")
        body = DatadogProvider._build_aggregate_body(params)
        assert body["compute"]["aggregation"] == "avg"
        assert body["compute"]["metric"] == "duration"

    def test_when_metric_is_sum_then_uses_sum(self):
        params = AggregateParams(source="test", metric="sum", field="bytes")
        body = DatadogProvider._build_aggregate_body(params)
        assert body["compute"]["aggregation"] == "sum"

    def test_when_metric_is_min_then_uses_min(self):
        params = AggregateParams(source="test", metric="min", field="latency")
        body = DatadogProvider._build_aggregate_body(params)
        assert body["compute"]["aggregation"] == "min"

    def test_when_metric_is_max_then_uses_max(self):
        params = AggregateParams(source="test", metric="max", field="latency")
        body = DatadogProvider._build_aggregate_body(params)
        assert body["compute"]["aggregation"] == "max"

    def test_when_metric_is_unknown_then_uses_count(self):
        params = AggregateParams(source="test", metric="unknown")
        body = DatadogProvider._build_aggregate_body(params)
        assert body["compute"]["aggregation"] == "count"

    def test_when_count_has_no_field_then_no_metric_key(self):
        params = AggregateParams(source="test", metric="count")
        body = DatadogProvider._build_aggregate_body(params)
        assert "metric" not in body["compute"]

    def test_when_limit_is_custom_then_group_by_has_limit(self):
        params = AggregateParams(source="test", limit=50)
        body = DatadogProvider._build_aggregate_body(params)
        assert body["group_by"][0]["limit"] == 50


class TestParseSearchResults:
    """Cover _parse_search_results static method."""

    def test_when_datadog_data_has_all_fields_then_extracts_them(self):
        data = [
            {
                "attributes": {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "status": "error",
                    "service": "api",
                    "host": "i-0123",
                    "message": "boom",
                    "attributes": {"custom": 123},
                    "tags": ["env:prod"],
                },
                "id": "1",
                "type": "log",
            }
        ]
        entries = DatadogProvider._parse_search_results(data)
        assert len(entries) == 1
        assert entries[0].timestamp == "2026-05-24T10:00:00Z"
        assert entries[0].level == "ERROR"
        assert entries[0].service == "api"
        assert entries[0].host == "i-0123"
        assert entries[0].message == "boom"
        assert entries[0].fields == {"custom": 123, "env": "prod"}

    def test_when_empty_data_then_returns_empty_list(self):
        entries = DatadogProvider._parse_search_results([])
        assert entries == []

    def test_when_no_custom_attributes_then_fields_empty(self):
        data = [
            {
                "attributes": {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "status": "info",
                    "message": "hello",
                },
                "id": "1",
                "type": "log",
            }
        ]
        entries = DatadogProvider._parse_search_results(data)
        assert entries[0].fields == {}


class TestParseAggregateResults:
    """Cover _parse_aggregate_results static method."""

    def test_when_count_results_then_returns_buckets(self):
        data = [
            {
                "by": {"service": "api"},
                "aggregations": [{"value": 42, "metric": "count"}],
            }
        ]
        agg = DatadogProvider._parse_aggregate_results(data)
        assert len(agg.buckets) == 1
        assert agg.buckets[0].value == 42.0
        assert agg.buckets[0].key == {"service": "api"}

    def test_when_empty_data_then_returns_empty_buckets(self):
        agg = DatadogProvider._parse_aggregate_results([])
        assert agg.buckets == []
        assert agg.total == 0

    def test_when_no_aggregations_then_zero_value(self):
        data = [{"by": {"service": "api"}, "aggregations": []}]
        agg = DatadogProvider._parse_aggregate_results(data)
        assert agg.buckets[0].value == 0.0


class TestExtractCursor:
    """Cover _extract_cursor static method."""

    def test_when_meta_has_after_then_returns_cursor(self):
        meta = {"page": {"after": "cursor123"}}
        assert DatadogProvider._extract_cursor(meta) == "cursor123"

    def test_when_meta_has_no_page_then_returns_none(self):
        assert DatadogProvider._extract_cursor({}) is None

    def test_when_page_has_no_after_then_returns_none(self):
        assert DatadogProvider._extract_cursor({"page": {}}) is None
