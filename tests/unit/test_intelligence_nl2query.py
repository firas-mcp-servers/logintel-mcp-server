"""Unit tests for NL2Query and explain functions."""


from logintel.intelligence.nl2query import explain, translate


class TestTranslateDatadog:
    """Scenarios for Datadog query translation."""

    def test_when_error_keyword_then_status_error(self):
        result = translate("Show me errors", "datadog")
        assert "status:error" in result["query"]
        assert result["provider"] == "datadog"

    def test_when_warn_keyword_then_status_warn(self):
        result = translate("Show me warnings", "datadog")
        assert "status:warn" in result["query"]

    def test_when_info_keyword_then_status_info(self):
        result = translate("Show me info logs", "datadog")
        assert "status:info" in result["query"]

    def test_when_service_mentioned_then_service_filter(self):
        result = translate("Logs from service payment", "datadog")
        assert "service:payment" in result["query"]

    def test_when_host_mentioned_then_host_filter(self):
        result = translate("Logs from host:server01", "datadog")
        assert "host:server01" in result["query"]

    def test_when_no_keywords_then_wildcard(self):
        result = translate("Show me everything", "datadog")
        assert result["query"] == "*"

    def test_when_last_hour_then_time_range_1h(self):
        result = translate("Errors in the last hour", "datadog")
        assert result["time_range"] == "1h"

    def test_when_last_30_minutes_then_time_range_30m(self):
        result = translate("Logs in the last 30 minutes", "datadog")
        assert result["time_range"] == "30m"

    def test_when_last_5_minutes_then_time_range_5m(self):
        result = translate("Logs in the last 5 minutes", "datadog")
        assert result["time_range"] == "5m"

    def test_when_past_day_then_time_range_24h(self):
        result = translate("Logs in the past day", "datadog")
        assert result["time_range"] == "24h"

    def test_when_last_week_then_time_range_7d(self):
        result = translate("Logs in the last week", "datadog")
        assert result["time_range"] == "7d"


class TestTranslateLoki:
    """Scenarios for Loki LogQL translation."""

    def test_when_error_keyword_then_level_error_label(self):
        result = translate("Show me errors", "loki")
        assert 'level="error"' in result["query"]
        assert result["provider"] == "loki"

    def test_when_service_mentioned_then_service_label(self):
        result = translate("Logs from service api", "loki")
        assert 'service="api"' in result["query"]

    def test_when_host_mentioned_then_host_label(self):
        result = translate("Logs from host:web01", "loki")
        assert 'host="web01"' in result["query"]

    def test_when_no_keywords_then_empty_selector(self):
        result = translate("Show me all", "loki")
        assert result["query"] == "{}"


class TestTranslateCloudWatch:
    """Scenarios for CloudWatch Logs Insights translation."""

    def test_when_error_keyword_then_filter_message(self):
        result = translate("Show me errors", "cloudwatch")
        assert "filter @message" in result["query"]
        assert result["provider"] == "cloudwatch"

    def test_when_no_keywords_then_basic_fields(self):
        result = translate("Show me everything", "cloudwatch")
        assert "fields @timestamp, @message" in result["query"]


class TestTranslateLocal:
    """Scenarios for local file query translation."""

    def test_when_error_keyword_then_error_pattern(self):
        result = translate("Show me errors", "local")
        assert result["query"] == "ERROR"
        assert result["provider"] == "local"

    def test_when_warn_keyword_then_warn_pattern(self):
        result = translate("Show me warnings", "local")
        assert result["query"] == "WARN"

    def test_when_no_keywords_then_original_text(self):
        result = translate("custom search", "local")
        assert result["query"] == "custom search"


class TestTranslateUnknownProvider:
    """Scenarios for unknown provider types."""

    def test_when_unknown_provider_then_pass_through(self):
        result = translate("Show me errors", "splunk")
        assert result["query"] == "Show me errors"
        assert result["provider"] == "splunk"
        assert "Direct pass-through" in result["note"]


class TestExplainDatadog:
    """Scenarios for Datadog query explanation."""

    def test_when_status_error_then_mentions_error_filter(self):
        text = explain("status:error", "datadog")
        assert "ERROR-level" in text

    def test_when_service_filter_then_mentions_service(self):
        text = explain("service:api", "datadog")
        assert "api" in text

    def test_when_wildcard_then_mentions_all_logs(self):
        text = explain("*", "datadog")
        assert "all logs" in text


class TestExplainLoki:
    """Scenarios for Loki query explanation."""

    def test_when_empty_selector_then_mentions_all_streams(self):
        text = explain("{}", "loki")
        assert "all streams" in text

    def test_when_level_error_then_mentions_error(self):
        text = explain('{level="error"}', "loki")
        assert "ERROR-level" in text

    def test_when_line_filter_then_mentions_containing(self):
        text = explain('{} |= "timeout"', "loki")
        assert "containing" in text


class TestExplainCloudWatch:
    """Scenarios for CloudWatch query explanation."""

    def test_when_filter_message_then_mentions_filtering(self):
        text = explain("fields @timestamp | filter @message like /error/i", "cloudwatch")
        assert "filters log messages" in text

    def test_when_basic_query_then_mentions_all_fields(self):
        text = explain("fields @timestamp, @message", "cloudwatch")
        assert "retrieves all log fields" in text


class TestExplainLocal:
    """Scenarios for local file query explanation."""

    def test_when_any_query_then_mentions_grep(self):
        text = explain("ERROR", "local")
        assert "grep/regex" in text


class TestExplainUnknownProvider:
    """Scenarios for unknown provider explanation."""

    def test_when_unknown_provider_then_generic_explanation(self):
        text = explain("query", "splunk")
        assert "splunk" in text
        assert "query" in text
