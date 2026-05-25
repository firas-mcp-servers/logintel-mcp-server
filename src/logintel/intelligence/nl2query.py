"""Natural-language to provider query translation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("logintel.intelligence.nl2query")


def translate(question: str, provider_type: str) -> dict[str, Any]:
    """Translate a natural-language question into a provider-native query."""
    q_lower = question.lower()

    if provider_type == "datadog":
        return _translate_datadog(q_lower, question)
    if provider_type == "loki":
        return _translate_loki(q_lower, question)
    if provider_type == "cloudwatch":
        return _translate_cloudwatch(q_lower, question)
    if provider_type == "local":
        return _translate_local(q_lower, question)

    return {"query": question, "provider": provider_type, "note": "Direct pass-through"}


def _translate_datadog(q_lower: str, original: str) -> dict[str, Any]:
    """Simple keyword-based Datadog query translation."""
    parts: list[str] = []

    if "error" in q_lower:
        parts.append("status:error")
    elif "warn" in q_lower or "warning" in q_lower:
        parts.append("status:warn")
    elif "info" in q_lower:
        parts.append("status:info")

    # Service extraction
    for prefix in ("service:", "from service ", "in service "):
        if prefix in q_lower:
            svc = original.lower().split(prefix, 1)[1].split()[0]
            parts.append(f"service:{svc}")
            break

    # Host extraction
    if "host:" in q_lower:
        host = original.lower().split("host:", 1)[1].split()[0]
        parts.append(f"host:{host}")

    query = " ".join(parts) if parts else "*"
    return {"query": query, "provider": "datadog", "time_range": _infer_time_range(q_lower)}


def _translate_loki(q_lower: str, original: str) -> dict[str, Any]:
    """Simple keyword-based Loki LogQL translation."""
    labels: dict[str, str] = {}
    line_filter = ""

    if "error" in q_lower:
        labels["level"] = "error"
    elif "warn" in q_lower or "warning" in q_lower:
        labels["level"] = "warn"
    elif "info" in q_lower:
        labels["level"] = "info"

    for prefix in ("service:", "from service ", "in service "):
        if prefix in q_lower:
            svc = original.lower().split(prefix, 1)[1].split()[0]
            labels["service"] = svc
            break

    if "host:" in q_lower:
        host = original.lower().split("host:", 1)[1].split()[0]
        labels["host"] = host

    selector = "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}" if labels else "{}"

    # Simple keyword extraction for line filter
    keywords = [w for w in original.split() if w.lower() not in _STOPWORDS and len(w) > 3]
    if keywords and not labels:
        line_filter = f' |= "{keywords[0]}"'

    query = f"{selector}{line_filter}"
    return {"query": query, "provider": "loki", "time_range": _infer_time_range(q_lower)}


def _translate_cloudwatch(q_lower: str, original: str) -> dict[str, Any]:
    """Simple keyword-based CloudWatch Logs Insights translation."""
    filters: list[str] = []

    if "error" in q_lower:
        filters.append("fields @timestamp, @message | filter @message like /error/i")
    elif "warn" in q_lower or "warning" in q_lower:
        filters.append("fields @timestamp, @message | filter @message like /warn/i")
    else:
        filters.append("fields @timestamp, @message")

    query = " | ".join(filters)
    return {"query": query, "provider": "cloudwatch", "time_range": _infer_time_range(q_lower)}


def _translate_local(q_lower: str, original: str) -> dict[str, Any]:
    """Simple keyword-based local file query translation."""
    patterns: list[str] = []

    if "error" in q_lower:
        patterns.append("ERROR")
    elif "warn" in q_lower or "warning" in q_lower:
        patterns.append("WARN")
    elif "info" in q_lower:
        patterns.append("INFO")

    query = patterns[0] if patterns else original
    return {"query": query, "provider": "local", "time_range": _infer_time_range(q_lower)}


def _infer_time_range(q_lower: str) -> str:
    """Infer a relative time range from the question."""
    if "last hour" in q_lower or "past hour" in q_lower or "1 hour" in q_lower:
        return "1h"
    if "last 30 minutes" in q_lower or "30 minutes" in q_lower or "half hour" in q_lower:
        return "30m"
    if "last 5 minutes" in q_lower or "5 minutes" in q_lower:
        return "5m"
    if "last 24 hours" in q_lower or "past day" in q_lower or "1 day" in q_lower:
        return "24h"
    if "last week" in q_lower or "past week" in q_lower or "1 week" in q_lower:
        return "7d"
    return "1h"


_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "can",
    "could",
    "may",
    "might",
    "must",
    "show",
    "me",
    "find",
    "get",
    "all",
    "from",
    "in",
    "for",
    "with",
    "about",
    "and",
    "or",
    "but",
    "not",
    "no",
    "yes",
    "to",
    "of",
    "on",
    "at",
    "by",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "my",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "what",
    "which",
    "who",
    "when",
    "where",
    "why",
    "how",
    "logs",
    "log",
    "service",
    "host",
    "error",
    "warn",
    "warning",
    "info",
    "level",
}


def explain(query: str, provider_type: str) -> str:
    """Explain what a provider-native query does in plain English."""
    if provider_type == "datadog":
        return _explain_datadog(query)
    if provider_type == "loki":
        return _explain_loki(query)
    if provider_type == "cloudwatch":
        return _explain_cloudwatch(query)
    if provider_type == "local":
        return _explain_local(query)
    return f"Query for {provider_type}: {query}"


def _explain_datadog(query: str) -> str:
    parts: list[str] = ["Datadog log search query"]
    if "status:error" in query.lower():
        parts.append("filters for ERROR-level logs")
    if "status:warn" in query.lower():
        parts.append("filters for WARN-level logs")
    if "service:" in query.lower():
        svc = query.lower().split("service:", 1)[1].split()[0]
        parts.append(f"from service '{svc}'")
    if "host:" in query.lower():
        host = query.lower().split("host:", 1)[1].split()[0]
        parts.append(f"on host '{host}'")
    if "@" in query:
        parts.append("with custom field filters")
    if query == "*":
        parts.append("matches all logs")
    return ", ".join(parts) + "."


def _explain_loki(query: str) -> str:
    parts: list[str] = ["Loki LogQL query"]
    if "{}" in query:
        parts.append("selects all streams")
    if 'level="error"' in query.lower():
        parts.append("filters for ERROR-level logs")
    if 'level="warn"' in query.lower():
        parts.append("filters for WARN-level logs")
    if "service=" in query.lower():
        svc = query.lower().split('service="', 1)[1].split('"')[0]
        parts.append(f"from service '{svc}'")
    if "|=" in query:
        kw = query.split('|= "', 1)[1].split('"')[0] if '|= "' in query else "keyword"
        parts.append(f"containing '{kw}'")
    return ", ".join(parts) + "."


def _explain_cloudwatch(query: str) -> str:
    if "filter @message" in query.lower():
        return "CloudWatch Logs Insights query that filters log messages by keyword."
    return "CloudWatch Logs Insights query that retrieves all log fields."


def _explain_local(query: str) -> str:
    return f"Local file grep/regex search for: '{query}'"
