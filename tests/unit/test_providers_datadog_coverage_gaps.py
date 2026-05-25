"""Coverage-gap tests for DatadogProvider edge cases and fallback branches."""

from logintel.providers.datadog import DatadogProvider


class TestParseAggregateResultsGaps:
    """Hit exception/fallback branches in _parse_aggregate_results."""

    def test_when_value_is_not_numeric_then_defaults_to_zero(self):
        data = [
            {
                "by": {"service": "api"},
                "aggregations": [{"value": "not-a-number", "metric": "count"}],
            }
        ]
        agg = DatadogProvider._parse_aggregate_results(data)
        assert agg.buckets[0].value == 0.0
        assert agg.buckets[0].count == 0

    def test_when_value_is_none_then_defaults_to_zero(self):
        data = [
            {
                "by": {"service": "api"},
                "aggregations": [{"value": None, "metric": "count"}],
            }
        ]
        agg = DatadogProvider._parse_aggregate_results(data)
        assert agg.buckets[0].value == 0.0
        assert agg.buckets[0].count == 0
