"""Unit tests for CloudWatchProvider with mocked boto3."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from logintel.config import SourceConfig
from logintel.models.params import (
    AggregateParams,
    FilterParams,
    SearchParams,
    TailParams,
)
from logintel.providers.cloudwatch import CloudWatchProvider

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_mock_logs_client(**kwargs):
    """Create a mock CloudWatch Logs client with sensible defaults."""
    client = MagicMock()
    client.start_query.return_value = {"queryId": "test-query-id"}
    client.get_query_results.return_value = {
        "status": "Complete",
        "results": kwargs.get("results", []),
    }
    client.filter_log_events.return_value = {
        "events": kwargs.get("events", []),
    }
    client.describe_log_groups.return_value = {
        "logGroups": kwargs.get("log_groups", []),
    }
    return client


def _make_mock_session(mock_logs_client):
    """Create a mock boto3 Session that returns the given logs client."""
    session = MagicMock()
    session.client.return_value = mock_logs_client
    return session


def _make_mock_session_with_role(mock_logs_client):
    """Create a mock boto3 Session that supports STS assume_role."""
    sts_client = MagicMock()
    sts_client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "AKID",
            "SecretAccessKey": "SECRET",
            "SessionToken": "TOKEN",
        }
    }

    def side_effect(service, **kwargs):
        if service == "sts":
            return sts_client
        return mock_logs_client

    session = MagicMock()
    session.client.side_effect = side_effect
    return session


@pytest.fixture
def provider():
    config = SourceConfig(
        type="cloudwatch",
        region="us-east-1",
        logGroups=["/aws/lambda/app"],
    )
    return CloudWatchProvider("cw-test", config)


# ------------------------------------------------------------------
# Client lifecycle
# ------------------------------------------------------------------


class TestGetClient:
    def test_when_no_profile_or_role_then_creates_client_from_default_session(self, provider):
        mock_client = _make_mock_logs_client()
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            client = provider._get_client()
            assert client is mock_client
            mock_session.client.assert_called_once_with("logs", region_name="us-east-1")

    def test_when_profile_is_set_then_uses_session_with_profile(self):
        config = SourceConfig(
            type="cloudwatch",
            region="us-east-1",
            profile="prod",
            logGroups=["/aws/lambda/app"],
        )
        provider = CloudWatchProvider("cw-test", config)
        mock_client = _make_mock_logs_client()
        mock_session = _make_mock_session(mock_client)

        with patch(
            "logintel.providers.cloudwatch.boto3.Session", return_value=mock_session
        ) as mock_session_cls:
            client = provider._get_client()
            assert client is mock_client
            mock_session_cls.assert_called_once_with(profile_name="prod")

    def test_when_cross_account_role_set_then_assumes_role_and_creates_client(self):
        config = SourceConfig(
            type="cloudwatch",
            region="us-east-1",
            logGroups=["/aws/lambda/app"],
            crossAccountRoleArn="arn:aws:iam::123456789012:role/Role",
        )
        provider = CloudWatchProvider("cw-test", config)
        mock_client = _make_mock_logs_client()
        mock_session = _make_mock_session_with_role(mock_client)

        with (
            patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session),
            patch(
                "logintel.providers.cloudwatch.boto3.client", return_value=mock_client
            ) as mock_boto_client,
        ):
            client = provider._get_client()
            assert client is mock_client
            mock_boto_client.assert_called_once()
            call_kwargs = mock_boto_client.call_args.kwargs
            assert call_kwargs["region_name"] == "us-east-1"
            assert call_kwargs["aws_access_key_id"] == "AKID"


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


class TestHealth:
    @pytest.mark.asyncio
    async def test_when_no_log_groups_then_returns_degraded(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1")
        provider = CloudWatchProvider("cw-test", config)
        health = await provider.health()
        assert health.status == "degraded"
        assert "No log groups" in health.message

    @pytest.mark.asyncio
    async def test_when_log_groups_exist_then_returns_healthy(self, provider):
        mock_client = _make_mock_logs_client(log_groups=[{"logGroupName": "/aws/lambda/app"}])
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            health = await provider.health()
            assert health.status == "healthy"
            assert "1 log group" in health.message

    @pytest.mark.asyncio
    async def test_when_log_group_missing_then_returns_degraded(self, provider):
        mock_client = _make_mock_logs_client(log_groups=[])
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            health = await provider.health()
            assert health.status == "degraded"
            assert "not found" in health.message.lower()

    @pytest.mark.asyncio
    async def test_when_describe_raises_client_error_then_returns_degraded(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.describe_log_groups.side_effect = Exception("AWS error")
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            health = await provider.health()
            assert health.status == "unhealthy"
            assert "AWS error" in health.message


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


class TestSearch:
    @pytest.mark.asyncio
    async def test_when_no_log_groups_then_returns_empty(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1")
        provider = CloudWatchProvider("cw-test", config)
        result = await provider.search(SearchParams(source="cw-test", query="error"))
        assert result.entries == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_when_search_succeeds_then_returns_entries(self, provider):
        mock_client = _make_mock_logs_client(
            results=[
                [
                    {"field": "@timestamp", "value": "2026-05-24T10:00:00.000Z"},
                    {"field": "@message", "value": '{"level":"INFO","message":"hello"}'},
                    {"field": "@logStream", "value": "stream1"},
                ]
            ]
        )
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.search(SearchParams(source="cw-test", query="hello"))
            assert len(result.entries) == 1
            assert result.entries[0].message == '{"level":"INFO","message":"hello"}'
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_when_search_has_time_range_then_uses_range(self, provider):
        mock_client = _make_mock_logs_client(results=[])
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            await provider.search(
                SearchParams(
                    source="cw-test",
                    query="x",
                    time_range={"from": "2026-05-24T09:00:00Z", "to": "2026-05-24T11:00:00Z"},
                )
            )
            call_kwargs = mock_client.start_query.call_args.kwargs
            assert call_kwargs["startTime"] == 1779613200
            assert call_kwargs["endTime"] == 1779620400

    @pytest.mark.asyncio
    async def test_when_start_query_raises_then_returns_empty(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.start_query.side_effect = Exception("Query failed")
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.search(SearchParams(source="cw-test", query="error"))
            assert result.entries == []

    @pytest.mark.asyncio
    async def test_when_query_returns_failed_then_returns_empty(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.get_query_results.return_value = {"status": "Failed"}
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.search(SearchParams(source="cw-test", query="error"))
            assert result.entries == []

    @pytest.mark.asyncio
    async def test_when_query_returns_cancelled_then_returns_empty(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.get_query_results.return_value = {"status": "Cancelled"}
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.search(SearchParams(source="cw-test", query="error"))
            assert result.entries == []

    @pytest.mark.asyncio
    async def test_when_query_times_out_then_returns_empty(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.get_query_results.return_value = {"status": "Running"}
        mock_session = _make_mock_session(mock_client)

        with (
            patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await provider.search(SearchParams(source="cw-test", query="error"))
            assert result.entries == []


# ------------------------------------------------------------------
# Filter
# ------------------------------------------------------------------


class TestFilter:
    @pytest.mark.asyncio
    async def test_when_no_log_groups_then_returns_empty(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1")
        provider = CloudWatchProvider("cw-test", config)
        result = await provider.filter(FilterParams(source="cw-test", level="ERROR"))
        assert result.entries == []

    @pytest.mark.asyncio
    async def test_when_filter_succeeds_then_returns_entries(self, provider):
        mock_client = _make_mock_logs_client(
            results=[
                [
                    {"field": "@timestamp", "value": "2026-05-24T10:00:00.000Z"},
                    {"field": "@message", "value": '{"level":"ERROR","message":"boom"}'},
                    {"field": "@logStream", "value": "stream1"},
                ]
            ]
        )
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.filter(FilterParams(source="cw-test", level="ERROR"))
            assert len(result.entries) == 1
            assert result.entries[0].level == "ERROR"

    @pytest.mark.asyncio
    async def test_when_filter_raises_then_returns_empty(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.start_query.side_effect = Exception("boom")
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.filter(FilterParams(source="cw-test"))
            assert result.entries == []


# ------------------------------------------------------------------
# Aggregate
# ------------------------------------------------------------------


class TestAggregate:
    @pytest.mark.asyncio
    async def test_when_no_log_groups_then_returns_empty(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1")
        provider = CloudWatchProvider("cw-test", config)
        result = await provider.aggregate(AggregateParams(source="cw-test"))
        assert result.buckets == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_when_aggregate_succeeds_then_returns_buckets(self, provider):
        mock_client = _make_mock_logs_client(
            results=[
                [
                    {"field": "bin(5m)", "value": "2026-05-24 10:00:00.000"},
                    {"field": "count()", "value": "42"},
                ]
            ]
        )
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.aggregate(AggregateParams(source="cw-test"))
            assert len(result.buckets) == 1
            assert result.buckets[0].value == 42.0

    @pytest.mark.asyncio
    async def test_when_aggregate_raises_then_returns_empty(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.start_query.side_effect = Exception("boom")
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.aggregate(AggregateParams(source="cw-test"))
            assert result.buckets == []
            assert result.total == 0


# ------------------------------------------------------------------
# Tail
# ------------------------------------------------------------------


class TestTail:
    @pytest.mark.asyncio
    async def test_when_no_log_groups_then_returns_empty(self):
        config = SourceConfig(type="cloudwatch", region="us-east-1")
        provider = CloudWatchProvider("cw-test", config)
        result = await provider.tail(TailParams(source="cw-test"))
        assert result.entries == []

    @pytest.mark.asyncio
    async def test_when_tail_succeeds_then_returns_entries(self, provider):
        mock_client = _make_mock_logs_client(
            events=[
                {
                    "timestamp": 1716544800000,
                    "message": '{"level":"INFO","message":"hello"}',
                    "logStreamName": "stream1",
                }
            ]
        )
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.tail(TailParams(source="cw-test", lines=10))
            assert len(result.entries) == 1
            assert result.entries[0].message == '{"level":"INFO","message":"hello"}'
            assert result.entries[0].level == "INFO"

    @pytest.mark.asyncio
    async def test_when_tail_has_plain_text_then_infers_level(self, provider):
        mock_client = _make_mock_logs_client(
            events=[
                {
                    "timestamp": 1716544800000,
                    "message": "WARN: something",
                    "logStreamName": "stream1",
                }
            ]
        )
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.tail(TailParams(source="cw-test"))
            assert result.entries[0].level == "WARN"

    @pytest.mark.asyncio
    async def test_when_tail_has_filter_query_then_passes_pattern(self, provider):
        mock_client = _make_mock_logs_client(events=[])
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            await provider.tail(TailParams(source="cw-test", filter_query="error"))
            call_kwargs = mock_client.filter_log_events.call_args.kwargs
            assert call_kwargs["filterPattern"] == "error"

    @pytest.mark.asyncio
    async def test_when_tail_raises_then_returns_empty(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.filter_log_events.side_effect = Exception("boom")
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            result = await provider.tail(TailParams(source="cw-test"))
            assert result.entries == []


# ------------------------------------------------------------------
# Get Schema
# ------------------------------------------------------------------


class TestGetSchema:
    @pytest.mark.asyncio
    async def test_when_schema_succeeds_then_returns_fields(self, provider):
        mock_client = _make_mock_logs_client(
            results=[
                [
                    {"field": "@timestamp", "value": "2026-05-24T10:00:00.000Z"},
                    {"field": "@message", "value": '{"level":"INFO","message":"x"}'},
                    {"field": "@logStream", "value": "stream1"},
                ]
            ]
        )
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            schema = await provider.get_schema()
            assert schema.source == "cw-test"
            assert any(f.name == "@timestamp" for f in schema.fields)
            assert schema.sample_log is not None

    @pytest.mark.asyncio
    async def test_when_schema_raises_then_returns_basic_fields(self, provider):
        mock_client = _make_mock_logs_client()
        mock_client.start_query.side_effect = Exception("boom")
        mock_session = _make_mock_session(mock_client)

        with patch("logintel.providers.cloudwatch.boto3.Session", return_value=mock_session):
            schema = await provider.get_schema()
            assert schema.source == "cw-test"
            assert any(f.name == "@timestamp" for f in schema.fields)
            assert schema.sample_log is None


# ------------------------------------------------------------------
# Stubs
# ------------------------------------------------------------------


class TestDetectPatterns:
    @pytest.mark.asyncio
    async def test_returns_empty_patterns(self, provider):
        from logintel.models.params import PatternParams

        result = await provider.detect_patterns(PatternParams(source="cw-test"))
        assert result.patterns == []
        assert result.total_errors == 0


class TestFindAnomalies:
    @pytest.mark.asyncio
    async def test_returns_empty_anomalies(self, provider):
        from logintel.models.params import AnomalyParams

        result = await provider.find_anomalies(AnomalyParams(source="cw-test"))
        assert result.anomalies == []
        assert result.metric == "log_volume"
