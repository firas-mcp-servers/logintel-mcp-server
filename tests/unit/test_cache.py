"""Unit tests for QueryCache."""

from logintel.cache import QueryCache


class TestQueryCache:
    """Scenarios for the query result cache."""

    def test_when_cache_miss_then_returns_none(self):
        cache = QueryCache(maxsize=10, ttl=60)
        assert cache.get("src", "search", {"q": "error"}) is None

    def test_when_cache_hit_then_returns_cached_value(self):
        cache = QueryCache(maxsize=10, ttl=60)
        cache.set("src", "search", {"q": "error"}, {"result": "ok"})
        assert cache.get("src", "search", {"q": "error"}) == {"result": "ok"}

    def test_when_different_params_then_separate_entries(self):
        cache = QueryCache(maxsize=10, ttl=60)
        cache.set("src", "search", {"q": "error"}, {"result": "errors"})
        cache.set("src", "search", {"q": "warn"}, {"result": "warnings"})
        assert cache.get("src", "search", {"q": "error"}) == {"result": "errors"}
        assert cache.get("src", "search", {"q": "warn"}) == {"result": "warnings"}

    def test_when_clear_then_all_entries_removed(self):
        cache = QueryCache(maxsize=10, ttl=60)
        cache.set("src", "search", {"q": "error"}, {"result": "ok"})
        cache.clear()
        assert cache.get("src", "search", {"q": "error"}) is None

    def test_when_ttl_expires_then_returns_none(self):
        cache = QueryCache(maxsize=10, ttl=0)
        cache.set("src", "search", {"q": "error"}, {"result": "ok"})
        assert cache.get("src", "search", {"q": "error"}) is None

    def test_when_dict_params_then_keys_are_sorted_for_consistency(self):
        cache = QueryCache(maxsize=10, ttl=60)
        cache.set("src", "search", {"b": 2, "a": 1}, {"result": "ok"})
        assert cache.get("src", "search", {"a": 1, "b": 2}) == {"result": "ok"}
