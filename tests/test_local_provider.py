"""Tests for LocalFileProvider."""

import json
import tempfile
from pathlib import Path

import pytest

from logintel.config import SourceConfig
from logintel.models import (
    AggregateParams,
    FilterParams,
    SearchParams,
    TailParams,
)
from logintel.providers.local import LocalFileProvider


class TestLocalFileProvider:
    """Tests for the LocalFileProvider."""

    @pytest.fixture
    def log_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def json_logs(self, log_dir):
        path = log_dir / "app.jsonl"
        with path.open("w") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-05-24T10:00:00Z",
                        "level": "ERROR",
                        "message": "DB connection failed",
                        "service": "payment",
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-05-24T10:05:00Z",
                        "level": "INFO",
                        "message": "Request processed",
                        "service": "api",
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "timestamp": "2026-05-24T10:10:00Z",
                        "level": "ERROR",
                        "message": "Timeout",
                        "service": "payment",
                    }
                )
                + "\n"
            )
        return path

    @pytest.fixture
    def plain_logs(self, log_dir):
        path = log_dir / "app.log"
        with path.open("w") as f:
            f.write("2026-05-24 10:00:00 [ERROR] payment: DB connection failed\n")
            f.write("2026-05-24 10:05:00 [INFO] api: Request processed\n")
        return path

    @pytest.fixture
    def json_provider(self, log_dir, json_logs):
        config = SourceConfig(
            type="local",
            paths=[str(log_dir / "*.jsonl")],
            parseJson=True,
            timestampField="timestamp",
            levelField="level",
            serviceField="service",
        )
        return LocalFileProvider("local-test", config)

    @pytest.fixture
    def plain_provider(self, log_dir, plain_logs):
        config = SourceConfig(
            type="local",
            paths=[str(log_dir / "*.log")],
            parseJson=False,
            regexPattern=(
                r"^(?P<timestamp>\S+ \S+) \[(?P<level>\w+)\] "
                r"(?P<service>\w+): (?P<message>.*)$"
            ),
        )
        return LocalFileProvider("local-plain", config)

    @pytest.mark.asyncio
    async def test_health_healthy(self, json_provider):
        health = await json_provider.health()
        assert health.status == "healthy"
        assert "1" in health.message

    @pytest.mark.asyncio
    async def test_health_no_files(self):
        config = SourceConfig(type="local", paths=["/nonexistent/*.log"])
        provider = LocalFileProvider("empty", config)
        health = await provider.health()
        assert health.status == "degraded"

    @pytest.mark.asyncio
    async def test_search_json(self, json_provider):
        result = await json_provider.search(SearchParams(source="local-test", query="payment"))
        assert len(result.entries) == 2
        assert all(e.service == "payment" for e in result.entries)

    @pytest.mark.asyncio
    async def test_search_level(self, json_provider):
        result = await json_provider.search(SearchParams(source="local-test", query="error"))
        assert len(result.entries) == 2
        assert all(e.level == "ERROR" for e in result.entries)

    @pytest.mark.asyncio
    async def test_search_time_range(self, json_provider):
        result = await json_provider.search(
            SearchParams(
                source="local-test",
                query="",
                time_range={"from": "2026-05-24T10:04:00Z", "to": "2026-05-24T10:06:00Z"},
            )
        )
        assert len(result.entries) == 1
        assert result.entries[0].message == "Request processed"

    @pytest.mark.asyncio
    async def test_filter_by_level(self, json_provider):
        result = await json_provider.filter(FilterParams(source="local-test", level="ERROR"))
        assert len(result.entries) == 2
        assert all(e.level == "ERROR" for e in result.entries)

    @pytest.mark.asyncio
    async def test_filter_by_service(self, json_provider):
        result = await json_provider.filter(FilterParams(source="local-test", service="api"))
        assert len(result.entries) == 1
        assert result.entries[0].service == "api"

    @pytest.mark.asyncio
    async def test_tail(self, json_provider):
        result = await json_provider.tail(TailParams(source="local-test", lines=2))
        assert len(result.entries) == 2
        assert result.entries[-1].message == "Timeout"

    @pytest.mark.asyncio
    async def test_aggregate_count_by_level(self, json_provider):
        result = await json_provider.aggregate(
            AggregateParams(source="local-test", group_by=["level"])
        )
        assert len(result.buckets) == 2
        counts = {b.key["level"]: b.count for b in result.buckets}
        assert counts["ERROR"] == 2
        assert counts["INFO"] == 1

    @pytest.mark.asyncio
    async def test_aggregate_count_by_service(self, json_provider):
        result = await json_provider.aggregate(
            AggregateParams(source="local-test", group_by=["service"])
        )
        assert len(result.buckets) == 2
        counts = {b.key["service"]: b.count for b in result.buckets}
        assert counts["payment"] == 2
        assert counts["api"] == 1

    @pytest.mark.asyncio
    async def test_plain_text_regex(self, plain_provider):
        result = await plain_provider.search(SearchParams(source="local-plain", query=""))
        assert len(result.entries) == 2
        assert result.entries[0].level == "ERROR"
        assert result.entries[0].service == "payment"

    @pytest.mark.asyncio
    async def test_get_schema(self, json_provider):
        schema = await json_provider.get_schema()
        assert schema.source == "local-test"
        field_names = {f.name for f in schema.fields}
        assert "timestamp" in field_names
        assert "level" in field_names
        assert "message" in field_names
        assert "service" in field_names
        assert "json" in schema.known_formats

    @pytest.mark.asyncio
    async def test_path_sandboxing(self, log_dir, json_logs):
        config = SourceConfig(type="local", paths=[str(log_dir / "*.jsonl")])
        provider = LocalFileProvider("sandbox", config)
        # Should allow files within the sandbox
        assert provider._is_path_allowed(json_logs)
        # Should reject files outside
        assert not provider._is_path_allowed(Path("/etc/passwd"))
