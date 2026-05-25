"""Unit tests for LogProvider base class scenarios."""

import pytest

from logintel.providers.base import LogProvider


class TestLogProviderOptionalMethods:
    """Scenarios for optional methods on the LogProvider base class."""

    @pytest.mark.asyncio
    async def test_when_native_query_is_called_on_base_then_raises_not_implemented(self):
        """Given a minimal LogProvider implementation, native_query raises NotImplementedError."""

        class MinimalProvider(LogProvider):
            @property
            def id(self):
                return "test"

            @property
            def type(self):
                return "test"

            async def health(self):
                return None  # type: ignore[return-value]

            async def search(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def filter(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def aggregate(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def tail(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def get_schema(self):
                return None  # type: ignore[return-value]

            async def detect_patterns(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def find_anomalies(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

        provider = MinimalProvider()
        with pytest.raises(NotImplementedError, match="does not support native_query"):
            await provider.native_query("SELECT * FROM logs")

    @pytest.mark.asyncio
    async def test_when_explain_query_is_called_on_base_then_raises_not_implemented(self):
        """Given a minimal LogProvider implementation, explain_query raises NotImplementedError."""

        class MinimalProvider(LogProvider):
            @property
            def id(self):
                return "test"

            @property
            def type(self):
                return "test"

            async def health(self):
                return None  # type: ignore[return-value]

            async def search(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def filter(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def aggregate(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def tail(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def get_schema(self):
                return None  # type: ignore[return-value]

            async def detect_patterns(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

            async def find_anomalies(self, params):  # noqa: ANN001, ANN202
                return None  # type: ignore[return-value]

        provider = MinimalProvider()
        with pytest.raises(NotImplementedError, match="does not support explain_query"):
            await provider.explain_query("SELECT * FROM logs")
