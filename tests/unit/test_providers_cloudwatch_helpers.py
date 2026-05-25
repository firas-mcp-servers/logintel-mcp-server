"""Unit tests for CloudWatchProvider helper methods (pure functions)."""

from datetime import UTC, datetime

from logintel.models.params import AggregateParams, FilterParams, SearchParams
from logintel.providers.cloudwatch import CloudWatchProvider


class TestToEpochSeconds:
    """Cover _to_epoch_seconds static method."""

    def test_when_datetime_is_provided_then_returns_epoch_seconds(self):
        dt = datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC)
        result = CloudWatchProvider._to_epoch_seconds(dt)
        assert result == int(dt.timestamp())


class TestBuildSearchQuery:
    """Cover _build_search_query static method."""

    def test_when_query_is_empty_then_returns_fields_and_sort(self):
        params = SearchParams(source="test", query="")
        query = CloudWatchProvider._build_search_query(params)
        assert query.startswith("fields @timestamp, @message, @logStream")
        assert "| sort @timestamp desc" in query
        assert "| limit 100" in query
        assert "filter" not in query

    def test_when_query_has_keyword_then_contains_filter_like(self):
        params = SearchParams(source="test", query="error")
        query = CloudWatchProvider._build_search_query(params)
        assert "| filter @message like /error/" in query

    def test_when_query_has_forward_slash_then_escapes_it(self):
        params = SearchParams(source="test", query="path/to/file")
        query = CloudWatchProvider._build_search_query(params)
        assert "| filter @message like /path\\/to\\/file/" in query

    def test_when_limit_is_custom_then_uses_custom_limit(self):
        params = SearchParams(source="test", query="x", limit=50)
        query = CloudWatchProvider._build_search_query(params)
        assert "| limit 50" in query


class TestBuildFilterQuery:
    """Cover _build_filter_query static method."""

    def test_when_no_filters_then_has_no_filter_clause(self):
        params = FilterParams(source="test")
        query = CloudWatchProvider._build_filter_query(params)
        assert "| filter" not in query

    def test_when_level_is_set_then_contains_level_filter(self):
        params = FilterParams(source="test", level="ERROR")
        query = CloudWatchProvider._build_filter_query(params)
        assert "ERROR" in query
        assert "| filter" in query

    def test_when_service_is_set_then_contains_logstream_filter(self):
        params = FilterParams(source="test", service="payment")
        query = CloudWatchProvider._build_filter_query(params)
        assert "@logStream like /payment/" in query

    def test_when_host_is_set_then_contains_logstream_filter(self):
        params = FilterParams(source="test", host="server01")
        query = CloudWatchProvider._build_filter_query(params)
        assert "@logStream like /server01/" in query

    def test_when_trace_id_is_set_then_contains_trace_filter(self):
        params = FilterParams(source="test", trace_id="abc123")
        query = CloudWatchProvider._build_filter_query(params)
        assert "abc123" in query

    def test_when_custom_fields_are_set_then_contains_field_filters(self):
        params = FilterParams(source="test", custom_fields={"env": "prod"})
        query = CloudWatchProvider._build_filter_query(params)
        assert '"env":"prod"' in query or '"env": "prod"' in query

    def test_when_multiple_filters_then_joins_with_and(self):
        params = FilterParams(source="test", level="ERROR", service="api")
        query = CloudWatchProvider._build_filter_query(params)
        assert " and " in query


class TestBuildAggregateQuery:
    """Cover _build_aggregate_query static method."""

    def test_when_default_params_then_count_by_bin(self):
        params = AggregateParams(source="test")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert query.startswith("stats count() by bin(5m)")

    def test_when_time_bucket_set_then_uses_custom_bin(self):
        params = AggregateParams(source="test", time_bucket="1h")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "bin(1h)" in query

    def test_when_group_by_service_then_uses_logstream(self):
        params = AggregateParams(source="test", group_by=["service"])
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "@logStream" in query

    def test_when_group_by_host_then_uses_logstream(self):
        params = AggregateParams(source="test", group_by=["host"])
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "@logStream" in query

    def test_when_metric_is_avg_then_uses_avg_function(self):
        params = AggregateParams(source="test", metric="avg", field="duration")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "avg(duration)" in query

    def test_when_metric_is_sum_then_uses_sum_function(self):
        params = AggregateParams(source="test", metric="sum", field="bytes")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "sum(bytes)" in query

    def test_when_metric_is_min_then_uses_min_function(self):
        params = AggregateParams(source="test", metric="min", field="latency")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "min(latency)" in query

    def test_when_metric_is_max_then_uses_max_function(self):
        params = AggregateParams(source="test", metric="max", field="latency")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "max(latency)" in query

    def test_when_metric_is_unknown_then_uses_count(self):
        params = AggregateParams(source="test", metric="unknown")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "count()" in query

    def test_when_limit_is_custom_then_uses_custom_limit(self):
        params = AggregateParams(source="test", limit=50)
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "| limit 50" in query


class TestParseInsightsResults:
    """Cover _parse_insights_results static method."""

    def test_when_json_message_then_extracts_fields(self):
        results = [
            [
                {"field": "@timestamp", "value": "2026-05-24T10:00:00.000Z"},
                {
                    "field": "@message",
                    "value": '{"level":"ERROR","message":"boom","service":"api"}',
                },
                {"field": "@logStream", "value": "stream1"},
            ]
        ]
        entries = CloudWatchProvider._parse_insights_results(results)
        assert len(entries) == 1
        assert entries[0].level == "ERROR"
        assert entries[0].message == '{"level":"ERROR","message":"boom","service":"api"}'
        assert entries[0].service == "api"
        assert entries[0].host == "stream1"

    def test_when_plain_text_message_then_infers_level(self):
        results = [
            [
                {"field": "@timestamp", "value": "2026-05-24T10:00:00.000Z"},
                {"field": "@message", "value": "ERROR: something broke"},
                {"field": "@logStream", "value": "stream1"},
            ]
        ]
        entries = CloudWatchProvider._parse_insights_results(results)
        assert entries[0].level == "ERROR"

    def test_when_json_has_extra_fields_then_populates_fields(self):
        results = [
            [
                {"field": "@timestamp", "value": "2026-05-24T10:00:00.000Z"},
                {
                    "field": "@message",
                    "value": '{"level":"INFO","message":"hello","env":"prod","custom":123}',
                },
                {"field": "@logStream", "value": "stream1"},
            ]
        ]
        entries = CloudWatchProvider._parse_insights_results(results)
        assert entries[0].fields == {"env": "prod", "custom": 123}

    def test_when_empty_results_then_returns_empty_list(self):
        entries = CloudWatchProvider._parse_insights_results([])
        assert entries == []


class TestParseStatsResults:
    """Cover _parse_stats_results static method."""

    def test_when_count_results_then_returns_buckets(self):
        results = [
            [
                {"field": "bin(5m)", "value": "2026-05-24 10:00:00.000"},
                {"field": "@logStream", "value": "stream1"},
                {"field": "count()", "value": "42"},
            ]
        ]
        params = AggregateParams(source="test")
        agg = CloudWatchProvider._parse_stats_results(results, params)
        assert len(agg.buckets) == 1
        assert agg.buckets[0].value == 42.0
        assert agg.buckets[0].count == 42

    def test_when_empty_results_then_returns_empty_buckets(self):
        agg = CloudWatchProvider._parse_stats_results([], AggregateParams(source="test"))
        assert agg.buckets == []
        assert agg.total == 0
