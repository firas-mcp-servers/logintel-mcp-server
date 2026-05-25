"""Unit tests for LocalFileProvider OSError handling scenarios."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from logintel.config import SourceConfig
from logintel.models import FilterParams, SearchParams, TailParams
from logintel.providers.local import LocalFileProvider


class TestLocalFileProviderOSErrorPaths:
    """Scenarios where file operations raise OSError."""

    @pytest.fixture
    def provider(self, tmp_path):
        log_file = tmp_path / "app.jsonl"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-24T10:00:00Z",
                    "level": "INFO",
                    "message": "ok",
                }
            )
            + "\n"
        )
        config = SourceConfig(
            type="local",
            paths=[str(tmp_path / "*.jsonl")],
            parseJson=True,
        )
        return LocalFileProvider("test", config)

    @pytest.mark.asyncio
    async def test_when_search_fails_to_open_file_then_returns_empty(self, provider):
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            result = await provider.search(SearchParams(source="test", query="ok"))
            assert result.entries == []

    @pytest.mark.asyncio
    async def test_when_filter_fails_to_open_file_then_returns_empty(self, provider):
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            result = await provider.filter(FilterParams(source="test"))
            assert result.entries == []

    @pytest.mark.asyncio
    async def test_when_tail_fails_to_open_file_then_returns_empty(self, provider):
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            result = await provider.tail(TailParams(source="test"))
            assert result.entries == []

    def test_when_read_entries_fails_to_open_file_then_returns_empty(self, provider):
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            entries = provider._read_entries([Path(provider._paths[0])], "test")
            assert entries == []

    def test_when_read_entries_reverse_fails_to_open_file_then_returns_empty(self, provider):
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            entries = provider._read_entries_reverse([Path(provider._paths[0])], "test")
            assert entries == []
