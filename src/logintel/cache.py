"""Query result caching for LogIntel."""

from __future__ import annotations

import json
import logging
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger("logintel.cache")


class QueryCache:
    """LRU cache with TTL for provider query results."""

    def __init__(self, maxsize: int = 100, ttl: int = 60) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    def _make_key(self, source: str, method: str, params: dict[str, Any]) -> str:
        """Build a hashable cache key from query parameters."""
        return json.dumps(
            {"source": source, "method": method, "params": params},
            sort_keys=True,
            default=str,
        )

    def get(self, source: str, method: str, params: dict[str, Any]) -> Any | None:
        """Retrieve a cached result if present and not expired."""
        key = self._make_key(source, method, params)
        result = self._cache.get(key)
        if result is not None:
            logger.debug("Cache hit for %s:%s", source, method)
        return result

    def set(self, source: str, method: str, params: dict[str, Any], result: Any) -> None:
        """Store a result in the cache."""
        key = self._make_key(source, method, params)
        self._cache[key] = result
        logger.debug("Cache set for %s:%s", source, method)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("Cache cleared")
