"""Unit tests targeting specific coverage gaps in CloudWatchProvider."""

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from logintel.config import SourceConfig
from logintel.models.params import (
    AggregateParams,
    FilterParams,
    TailParams,
)
from logintel.providers.cloudwatch import CloudWatchProvider


class TestCoverageGapProperties:
    """Cover line 59: property access."""

    def test_when_id_property_accessed_then_returns_source_id(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1")
        provider = CloudWatchProvider("my-cw", config)
        assert provider.id == "my-cw"
        assert provider.type == "cloudwatch"


class TestCoverageGapGetClientEarlyReturn:
    """Cover line 72: _get_client early return when cached."""

    def test_when_called_twice_then_returns_same_client(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1")
        provider = CloudWatchProvider("cw", config)
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            c1 = provider._get_client()
            c2 = provider._get_client()
            assert c1 is c2
            assert mock_session.client.call_count == 1


class TestCoverageGapProfileNotFound:
    """Cover lines 80-82: ProfileNotFound handling."""

    def test_when_profile_not_found_then_raises(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1", profile="nonexistent")
        provider = CloudWatchProvider("cw", config)

        from botocore.exceptions import ProfileNotFound

        with (
            patch(
                "logintel.providers.cloudwatch.boto3.Session",
                side_effect=ProfileNotFound(profile="nonexistent"),
            ),
            pytest.raises(ProfileNotFound),
        ):
            provider._get_client()


class TestCoverageGapAggregateGroupByBranches:
    """Cover lines 162, 165, 171: aggregate query group_by branches."""

    def test_when_group_by_timestamp_bucket_then_uses_bin(self):
        params = AggregateParams(source="test", group_by=["timestamp_bucket"], time_bucket="1h")
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "bin(1h)" in query

    def test_when_group_by_level_then_uses_level(self):
        params = AggregateParams(source="test", group_by=["level"])
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "level" in query

    def test_when_group_by_unknown_field_then_uses_field_name(self):
        params = AggregateParams(source="test", group_by=["custom_field"])
        query = CloudWatchProvider._build_aggregate_query(params)
        assert "custom_field" in query


class TestCoverageGapParseStatsValueError:
    """Cover lines 267-268: ValueError when converting stats value."""

    def test_when_count_value_is_not_numeric_then_uses_zero(self):
        results = [
            [
                {"field": "bin(5m)", "value": "2026-05-24 10:00:00.000"},
                {"field": "count()", "value": "not-a-number"},
            ]
        ]
        agg = CloudWatchProvider._parse_stats_results(results, AggregateParams(source="test"))
        assert agg.buckets[0].value == 0.0


class TestCoverageGapParseStatsStartsWithStats:
    """Cover lines 272-276: field name starts with 'stats '."""

    def test_when_field_starts_with_stats_then_parses_value(self):
        results = [
            [
                {"field": "bin(5m)", "value": "2026-05-24 10:00:00.000"},
                {"field": "stats count() by bin(5m)", "value": "42"},
            ]
        ]
        agg = CloudWatchProvider._parse_stats_results(results, AggregateParams(source="test"))
        assert agg.buckets[0].value == 42.0

    def test_when_stats_field_value_is_not_numeric_then_uses_zero(self):
        results = [
            [
                {"field": "stats count() by bin(5m)", "value": "abc"},
            ]
        ]
        agg = CloudWatchProvider._parse_stats_results(results, AggregateParams(source="test"))
        assert agg.buckets[0].value == 0.0


class TestCoverageGapParseStatsFallbackNumeric:
    """Cover lines 282-288: fallback numeric search in row_dict."""

    def test_when_no_metric_value_then_finds_numeric_in_row_dict(self):
        results = [
            [
                {"field": "bin(5m)", "value": "2026-05-24 10:00:00.000"},
                {"field": "@logStream", "value": "stream1"},
                {"field": "my_metric", "value": "99.5"},
            ]
        ]
        agg = CloudWatchProvider._parse_stats_results(results, AggregateParams(source="test"))
        assert agg.buckets[0].value == 99.5

    def test_when_no_numeric_found_then_zero(self):
        results = [
            [
                {"field": "bin(5m)", "value": "2026-05-24 10:00:00.000"},
                {"field": "@logStream", "value": "stream1"},
            ]
        ]
        agg = CloudWatchProvider._parse_stats_results(results, AggregateParams(source="test"))
        assert agg.buckets[0].value == 0.0


class TestCoverageGapHealthClientError:
    """Cover lines 324-325: ClientError in health check."""

    @pytest.mark.asyncio
    async def test_when_describe_raises_client_error_then_returns_degraded(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1", logGroups=["/aws/lambda/app"])
        provider = CloudWatchProvider("cw", config)
        mock_client = MagicMock()
        mock_client.describe_log_groups.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "DescribeLogGroups",
        )
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            health = await provider.health()
            assert health.status == "degraded"
            assert "/aws/lambda/app" in health.message


class TestCoverageGapFilterTimeRange:
    """Cover lines 395-397: filter with time_range."""

    @pytest.mark.asyncio
    async def test_when_filter_has_time_range_then_uses_range(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1", logGroups=["/aws/lambda/app"])
        provider = CloudWatchProvider("cw", config)
        mock_client = MagicMock()
        mock_client.start_query.return_value = {"queryId": "qid"}
        mock_client.get_query_results.return_value = {"status": "Complete", "results": []}
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            await provider.filter(
                FilterParams(
                    source="cw",
                    level="ERROR",
                    time_range={"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
                )
            )
            call_kwargs = mock_client.start_query.call_args.kwargs
            assert call_kwargs["startTime"] == 1779613200
            assert call_kwargs["endTime"] == 1779620400


class TestCoverageGapAggregateTimeRange:
    """Cover lines 430-432: aggregate with time_range."""

    @pytest.mark.asyncio
    async def test_when_aggregate_has_time_range_then_uses_range(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1", logGroups=["/aws/lambda/app"])
        provider = CloudWatchProvider("cw", config)
        mock_client = MagicMock()
        mock_client.start_query.return_value = {"queryId": "qid"}
        mock_client.get_query_results.return_value = {"status": "Complete", "results": []}
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            await provider.aggregate(
                AggregateParams(
                    source="cw",
                    time_range={"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
                )
            )
            call_kwargs = mock_client.start_query.call_args.kwargs
            assert call_kwargs["startTime"] == 1779613200
            assert call_kwargs["endTime"] == 1779620400


class TestCoverageGapTailExtraFields:
    """Cover line 497: tail JSON parsing with extra fields."""

    @pytest.mark.asyncio
    async def test_when_tail_json_has_extra_fields_then_populates_fields(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1", logGroups=["/aws/lambda/app"])
        provider = CloudWatchProvider("cw", config)
        mock_client = MagicMock()
        mock_client.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": 1716544800000,
                    "message": json.dumps(
                        {
                            "level": "INFO",
                            "message": "hello",
                            "service": "api",
                            "env": "prod",
                            "custom": 123,
                        }
                    ),
                    "logStreamName": "stream1",
                }
            ]
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.tail(TailParams(source="cw"))
            assert result.entries[0].fields == {"env": "prod", "custom": 123}


class TestCoverageGapTailPlainTextBranches:
    """Cover tail plain-text parsing branches."""

    @pytest.mark.asyncio
    async def test_when_tail_plain_text_has_level_in_middle_then_infers_level(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1", logGroups=["/aws/lambda/app"])
        provider = CloudWatchProvider("cw", config)
        mock_client = MagicMock()
        mock_client.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": 1716544800000,
                    "message": "2024-01-01 ERROR something broke",
                    "logStreamName": "stream1",
                }
            ]
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.tail(TailParams(source="cw"))
            assert result.entries[0].level == "ERROR"

    @pytest.mark.asyncio
    async def test_when_tail_plain_text_has_no_level_then_unknown(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1", logGroups=["/aws/lambda/app"])
        provider = CloudWatchProvider("cw", config)
        mock_client = MagicMock()
        mock_client.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": 1716544800000,
                    "message": "just a normal message",
                    "logStreamName": None,
                }
            ]
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.tail(TailParams(source="cw"))
            assert result.entries[0].level == "UNKNOWN"
            assert result.entries[0].service == "unknown"
