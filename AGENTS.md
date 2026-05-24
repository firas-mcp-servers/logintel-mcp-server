# Application Log Intelligence MCP Server

## Project Vision

Build a **universal Model Context Protocol (MCP) server** that connects LLMs to application logs across Datadog, Grafana Loki, AWS CloudWatch, and local log files. The LLM can search, filter, aggregate logs, detect error patterns, correlate across services, and suggest root causes — all through natural language queries like *"Why did orders spike at 2 AM?"* or *"Find all timeout errors in the payment service from last hour."*

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Host (Claude/Cursor/etc.)            │
│                         ┌─────────┐                         │
│                         │  LLM    │                         │
│                         └────┬────┘                         │
│                              │ MCP Protocol (JSON-RPC)      │
└──────────────────────────────┼───────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  LogIntel MCP Server │
                    │   (this project)     │
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
   ┌─────▼─────┐       ┌──────▼──────┐     ┌───────▼───────┐
   │  Datadog  │       │Grafana Loki │     │AWS CloudWatch │
   │   APIs    │       │  HTTP API   │     │  Logs Insights│
   └───────────┘       └─────────────┘     └───────────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │
                        ┌──────▼──────┐
                        │ Local Files │
                        │  (fs/grep)  │
                        └─────────────┘
```

### Key Design Principles

1. **Provider Abstraction** — All backends implement a common `LogProvider` interface. Adding a new backend = implementing one interface.
2. **Read-Only by Default** — All tools are read-only (`annotations.readOnlyHint: true`). No log mutation.
3. **Natural Language First** — High-level tools accept natural language and translate to provider-specific query languages via LLM-powered NL2Query.
4. **Streaming for Large Results** — Support pagination and result limits to avoid context window overflow.
5. **Correlation as First-Class** — Cross-service correlation tools can query multiple backends simultaneously.
6. **Caching & Deduplication** — In-memory LRU cache for repeated queries; deduplicate similar error patterns.

---

## Supported Backends (Phase 1)

| Backend | Protocol | Query Language | Key Capabilities |
|---------|----------|---------------|-----------------|
| **Datadog** | REST API | Lucene-like + facet search | Full-text search, facets, patterns, anomaly detection, trace correlation |
| **Grafana Loki** | HTTP API | LogQL | Label filtering, pattern matching, metric extraction from logs, trace correlation |
| **AWS CloudWatch** | AWS SDK | CloudWatch Logs Insights | SQL-like queries, pattern detection, anomaly detection, metric filters |
| **Local Log Files** | filesystem | regex / grep | Tail, search, parse structured logs (JSON), multi-file correlation |

### Future Backends (Phase 2+)
- Elasticsearch / OpenSearch
- Splunk
- New Relic
- Azure Monitor Logs
- Google Cloud Logging
- Journald / syslog

---

## MCP Capabilities

```json
{
  "protocolVersion": "2025-06-18",
  "capabilities": {
    "tools": {
      "listChanged": true
    },
    "resources": {
      "subscribe": true,
      "listChanged": true
    },
    "prompts": {
      "listChanged": true
    }
  }
}
```

---

## Tool Registry

### Discovery & Metadata Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `list_log_sources` | List all configured log sources (Datadog indexes, Loki streams, CW log groups, local files) | ✅ |
| `get_source_schema` | Get field/schema info for a source (available facets, labels, fields, known log formats) | ✅ |
| `get_source_health` | Check connectivity and health of a log source | ✅ |

### Core Query Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `search_logs` | Search logs with natural language or structured query. Returns matching log entries with pagination. | ✅ |
| `filter_logs` | Filter logs by structured criteria (time range, severity, service, host, custom fields) | ✅ |
| `aggregate_logs` | Aggregate/group logs (count by service, error rate over time, top error messages) | ✅ |
| `tail_logs` | Stream/follow logs in real-time from a source (returns latest N entries) | ✅ |

### Intelligence & Analysis Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `detect_error_patterns` | Automatically group similar errors, find recurring patterns, surface new anomalies | ✅ |
| `find_anomalies` | Detect statistical anomalies in log volume, error rates, latency patterns | ✅ |
| `correlate_logs` | Correlate logs across services by trace ID, timestamp proximity, or shared fields | ✅ |
| `analyze_root_cause` | Given an incident time/service, analyze surrounding logs to suggest root cause | ✅ |
| `summarize_logs` | Generate natural language summary of a set of logs (e.g., "3 distinct errors, 2 related to DB timeouts") | ✅ |
| `compare_time_periods` | Compare logs between two time windows (e.g., before/after deployment) | ✅ |

### Translation & Helper Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `natural_language_to_query` | Translate a natural language question into the target backend's query language | ✅ |
| `explain_query` | Explain what a backend-specific query does in plain English | ✅ |

---

## Resource Registry

| Resource URI | Description |
|-------------|-------------|
| `logintel://sources` | List of all configured log sources |
| `logintel://sources/{source_id}/schema` | Schema/field definitions for a specific source |
| `logintel://sources/{source_id}/recent_errors` | Recent error patterns for a source (auto-updated) |
| `logintel://saved_queries` | User-saved or commonly-used queries |

---

## Prompt Registry

| Prompt | Description |
|--------|-------------|
| `investigate_incident` | Structured investigation workflow: detect anomalies → search logs → correlate → suggest root cause |
| `oncall_summary` | Generate a shift summary: errors, anomalies, top issues, recommended actions |
| `deployment_impact` | Compare pre/post deployment logs to detect regressions |

---

## Technology Stack

### Python + Poetry

```
Runtime:       Python 3.11+
Package Mgr:   Poetry (pyproject.toml)
Framework:     mcp (FastMCP from official python-sdk)
Transport:     stdio (default) + HTTP (optional)
Validation:    Pydantic v2
HTTP Client:   httpx
AWS SDK:       boto3
Config:        pydantic-settings
Caching:       cachetools
Testing:       pytest + pytest-asyncio + pytest-httpx
CLI Entry:     logintel (poetry script or python -m logintel)
```

---

## Implementation Phases

### Phase 0: Foundation (Week 1)

- [ ] Project scaffolding (Python, MCP SDK, build setup)
- [ ] `LogProvider` abstraction interface
- [ ] Configuration system (sources, credentials, defaults)
- [ ] `list_log_sources` tool
- [ ] `get_source_health` tool
- [ ] Basic error handling and logging (to stderr only!)
- [ ] MCP Inspector testing setup

### Phase 1: Local File Provider (Week 1-2)

- [ ] Implement `LocalFileProvider`
- [ ] `search_logs` — grep/regex across files, with time range filtering
- [ ] `filter_logs` — structured filter by level, service, timestamp
- [ ] `tail_logs` — follow log files (tail -f equivalent)
- [ ] Support JSON-structured log parsing (auto-extract fields)
- [ ] Support plain text logs with regex field extraction
- [ ] `aggregate_logs` — count, group by field, time bucketing
- [ ] `summarize_logs` — feed logs to LLM for summarization

### Phase 2: CloudWatch Provider (Week 2-3)

- [ ] Implement `CloudWatchProvider`
- [ ] `search_logs` — CloudWatch Logs Insights queries
- [ ] `filter_logs` — translate to Insights filter syntax
- [ ] `aggregate_logs` — stats commands in Insights
- [ ] `detect_error_patterns` — use `patterns` command
- [ ] `find_anomalies` — use anomaly detection API
- [ ] `natural_language_to_query` — NL → CloudWatch Logs Insights query
- [ ] Cross-account observability support

### Phase 3: Datadog Provider (Week 3-4)

- [ ] Implement `DatadogProvider`
- [ ] `search_logs` — Log Search API (Lucene syntax)
- [ ] `filter_logs` — facet-based filtering
- [ ] `aggregate_logs` — Log Analytics API
- [ ] `detect_error_patterns` — Pattern Inspector API
- [ ] `find_anomalies` — Watchdog integration
- [ ] `correlate_logs` — trace/log correlation via APM
- [ ] `natural_language_to_query` — NL → Datadog search query

### Phase 4: Loki Provider (Week 4-5)

- [ ] Implement `LokiProvider`
- [ ] `search_logs` — LogQL label matchers + line filters
- [ ] `filter_logs` — LogQL parsing + field filters
- [ ] `aggregate_logs` — LogQL metric queries
- [ ] `detect_error_patterns` — pattern extraction via query-time analysis
- [ ] `natural_language_to_query` — NL → LogQL
- [ ] Trace correlation via trace IDs in labels

### Phase 5: Intelligence Layer (Week 5-6)

- [ ] `analyze_root_cause` — multi-step agentic workflow
- [ ] `correlate_logs` — cross-source correlation engine
- [ ] `compare_time_periods` — before/after analysis
- [ ] Caching layer for repeated queries
- [ ] Result pagination and streaming for large datasets
- [ ] `investigate_incident` prompt template
- [ ] `oncall_summary` prompt template

### Phase 6: Polish & Distribution (Week 6-7)

- [ ] Comprehensive test suite (unit + integration)
- [ ] Docker image
- [ ] PyPI package publishing
- [ ] Claude Desktop / Cursor config examples
- [ ] Documentation and usage examples
- [ ] GitHub Actions CI/CD

---

## Tool Schemas (Detailed)

### `search_logs`

```json
{
  "name": "search_logs",
  "description": "Search logs using natural language or a structured query. Use this when the user asks to find specific log events, error messages, or investigate behavior.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "source": {
        "type": "string",
        "description": "Log source ID (e.g., 'datadog-prod', 'loki-default', 'cloudwatch-app', '/var/log/app'). Use list_log_sources to discover available sources."
      },
      "query": {
        "type": "string",
        "description": "Natural language query (e.g., 'timeout errors in payment service') or provider-specific query string."
      },
      "timeRange": {
        "type": "object",
        "properties": {
          "from": { "type": "string", "description": "ISO 8601 timestamp or relative (e.g., 'now-1h')" },
          "to": { "type": "string", "description": "ISO 8601 timestamp or relative (e.g., 'now')" }
        }
      },
      "limit": {
        "type": "integer",
        "default": 100,
        "description": "Max number of log entries to return (max 1000)"
      },
      "offset": {
        "type": "string",
        "description": "Pagination cursor for continuing a previous search"
      }
    },
    "required": ["source", "query"]
  },
  "annotations": {
    "readOnlyHint": true,
    "title": "Search Logs",
    "openWorldHint": false
  }
}
```

### `detect_error_patterns`

```json
{
  "name": "detect_error_patterns",
  "description": "Analyze logs to detect recurring error patterns, group similar errors, and surface anomalies. Use this when the user asks about error trends, frequent failures, or unusual error spikes.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "source": { "type": "string" },
      "timeRange": {
        "type": "object",
        "properties": {
          "from": { "type": "string" },
          "to": { "type": "string" }
        }
      },
      "service": {
        "type": "string",
        "description": "Optional: restrict to a specific service"
      },
      "minOccurrences": {
        "type": "integer",
        "default": 5,
        "description": "Minimum occurrences to be considered a pattern"
      }
    },
    "required": ["source"]
  },
  "annotations": {
    "readOnlyHint": true,
    "title": "Detect Error Patterns"
  }
}
```

### `analyze_root_cause`

```json
{
  "name": "analyze_root_cause",
  "description": "Given an incident timeframe and affected service, analyze surrounding logs across all available sources to identify likely root causes. Use this when investigating outages, error spikes, or performance degradation.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service": { "type": "string", "description": "Primary affected service" },
      "timeRange": {
        "type": "object",
        "properties": {
          "from": { "type": "string" },
          "to": { "type": "string" }
        },
        "required": ["from", "to"]
      },
      "symptom": {
        "type": "string",
        "description": "Description of the observed issue (e.g., '500 errors', 'high latency', 'connection timeouts')"
      },
      "sources": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Sources to analyze. If omitted, all sources are queried."
      },
      "correlationWindow": {
        "type": "string",
        "default": "5m",
        "description": "Time window for cross-service correlation (e.g., '2m', '10m')"
      }
    },
    "required": ["service", "timeRange", "symptom"]
  },
  "annotations": {
    "readOnlyHint": true,
    "title": "Analyze Root Cause"
  }
}
```

### `natural_language_to_query`

```json
{
  "name": "natural_language_to_query",
  "description": "Translate a natural language question into the target backend's native query language. Use this to help the user understand how their question maps to the underlying query syntax.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "source": { "type": "string" },
      "question": { "type": "string", "description": "Natural language question (e.g., 'Show me all ERROR logs from the api service in the last 30 minutes')" }
    },
    "required": ["source", "question"]
  },
  "annotations": {
    "readOnlyHint": true,
    "title": "Natural Language to Query"
  }
}
```

---

## Configuration Schema

```yaml
# .logintelrc.yaml
version: "1.0"

sources:
  datadog-prod:
    type: datadog
    apiKey: "${DATADOG_API_KEY}"
    appKey: "${DATADOG_APP_KEY}"
    site: "datadoghq.com"  # or "datadoghq.eu"
    defaultIndexes: ["main", "prod"]

  loki-default:
    type: loki
    url: "http://localhost:3100"
    # optional: basicAuth, tenantId

  cloudwatch-app:
    type: cloudwatch
    region: "us-east-1"
    profile: "production"  # AWS profile name
    # optional: crossAccountRoleArn

  local-app:
    type: local
    paths:
      - "/var/log/myapp/*.log"
      - "/var/log/nginx/*.log"
    parseJson: true
    timestampField: "timestamp"
    levelField: "level"
    serviceField: "service"

defaults:
  timeRange: "1h"
  maxResults: 100
  timezone: "UTC"

intelligence:
  enableCaching: true
  cacheTtlSeconds: 60
  anomalySensitivity: "medium"  # low, medium, high
  maxCorrelationDepth: 3
```

---

## Key Implementation Decisions

### 1. Provider Interface

All providers implement a common async interface:

```python
from abc import ABC, abstractmethod
from typing import Protocol

class LogProvider(ABC):
    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def type(self) -> str: ...

    @abstractmethod
    async def health(self) -> HealthStatus: ...

    @abstractmethod
    async def search(self, params: SearchParams) -> SearchResult: ...

    @abstractmethod
    async def filter(self, params: FilterParams) -> SearchResult: ...

    @abstractmethod
    async def aggregate(self, params: AggregateParams) -> AggregateResult: ...

    @abstractmethod
    async def tail(self, params: TailParams) -> SearchResult: ...

    @abstractmethod
    async def get_schema(self) -> SchemaInfo: ...

    @abstractmethod
    async def detect_patterns(self, params: PatternParams) -> PatternResult: ...

    @abstractmethod
    async def find_anomalies(self, params: AnomalyParams) -> AnomalyResult: ...
    # Optional: native_query, explain_query
```

### 2. NL2Query Strategy

Instead of fine-tuning a model, use **in-context learning** with the connected LLM:

- Build a system prompt with provider-specific query syntax reference + examples
- Include source schema (available fields, labels, facets) in context
- Let the host LLM translate natural language → native query
- The MCP server validates and executes the generated query
- Fallback: if translation fails, return helpful error with query syntax docs

This avoids model hosting complexity while leveraging the host LLM's reasoning.

### 3. Result Format

All tools return a standardized log entry format:

```python
from pydantic import BaseModel
from typing import Optional, Any

class LogEntry(BaseModel):
    timestamp: str                 # ISO 8601
    level: str                     # ERROR, WARN, INFO, DEBUG, TRACE
    message: str                   # Raw or rendered message
    service: Optional[str] = None  # Service name
    host: Optional[str] = None     # Host/container
    trace_id: Optional[str] = None # Distributed trace ID
    span_id: Optional[str] = None  # Span ID
    source: str                    # Source ID
    fields: dict[str, Any]         # Extracted structured fields
    raw: Any                       # Provider-specific raw data
```

### 4. Security & Safety

- **Read-only**: All tools declare `readOnlyHint: true`
- **Credential isolation**: API keys via env vars only, never in config files committed to repo
- **Path sandboxing** (local provider): Only access paths listed in config; reject `..` traversal
- **Query timeouts**: All provider queries have configurable timeouts (default 30s)
- **Result limits**: Hard cap at 1000 entries per query; paginate beyond that
- **No PII extraction**: Don't build tools that specifically extract user data, emails, IPs, etc.

### 5. Correlation Engine

The `correlate_logs` and `analyze_root_cause` tools use a simple but effective strategy:

1. **Trace ID correlation**: Match `traceId` across sources (fastest, most accurate)
2. **Timestamp proximity**: Find logs within ±correlationWindow of target events
3. **Field matching**: Match on `service`, `host`, `requestId`, `userId` fields
4. **Causality heuristic**: ERROR → preceding WARN/INFO in same service; upstream service errors before downstream

Results are scored by correlation strength and presented with confidence levels.

---

## Development Workflow

### Local Testing with MCP Inspector

```bash
# Install dependencies
poetry install

# Run server directly
poetry run logintel --config ./examples/config.yaml

# Or via Python module
poetry run python -m logintel --config ./examples/config.yaml

# In another terminal, run MCP Inspector
npx -y @modelcontextprotocol/inspector
# Connect to: stdio → poetry run python -m logintel --config ./examples/config.yaml
```

### Claude Desktop Integration

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "log-intel": {
      "command": "poetry",
      "args": ["run", "python", "-m", "logintel", "--config", "/path/to/.logintelrc.yaml"]
    }
  }
}
```

Or with `uvx` (if published to PyPI):

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "log-intel": {
      "command": "uvx",
      "args": ["-y", "logintel-mcp", "--config", "/path/to/.logintelrc.yaml"]
    }
  }
}
```

### Cursor Integration

```json
// .cursor/mcp.json
{
  "mcpServers": {
    "log-intel": {
      "command": "poetry",
      "args": ["run", "python", "-m", "logintel", "--config", "./.logintelrc.yaml"]
    }
  }
}
```

Or with `uvx` (if published to PyPI):

```json
// .cursor/mcp.json
{
  "mcpServers": {
    "log-intel": {
      "command": "uvx",
      "args": ["-y", "logintel-mcp", "--config", "./.logintelrc.yaml"]
    }
  }
}
```

---

## Testing Strategy

1. **Unit tests** — Each provider's query builder, result parser, utility functions (pytest)
2. **Integration tests** — Mocked provider APIs (using pytest-httpx for HTTP, moto for AWS, aioresponses for async)
3. **E2E tests** — MCP Inspector automation or direct JSON-RPC over stdio tests
4. **Test fixtures** — Sample logs in JSON, plain text, and provider-native formats

---

## Package Naming

- **PyPI**: `logintel-mcp` (or `mcp-server-log-intel`)
- **GitHub**: `logintel/mcp-server`
- **Docker**: `ghcr.io/logintel/mcp-server:latest`

---

## Success Metrics

1. A user can ask *"Why did orders spike at 2 AM?"* and get a coherent analysis
2. A user can ask *"Find all timeout errors in payment service from last hour"* and get precise results from any configured backend
3. Cross-service correlation works across at least 2 backends in a single query
4. NL2Query produces valid provider-native queries >85% of the time for common patterns
5. Root cause analysis surfaces the actual issue in the top 3 suggestions >70% of the time

---

## References

- [MCP Specification](https://modelcontextprotocol.io/specification/2025-06-18)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) (reference only)
- [Datadog Log Search API](https://docs.datadoghq.com/api/latest/logs/)
- [Grafana Loki HTTP API](https://grafana.com/docs/loki/latest/api/)
- [CloudWatch Logs Insights Query Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)
- [NL2LogQL Research](https://arxiv.org/abs/2412.03612)
- [LogAI Library](https://github.com/salesforce/logai)

---

*Last updated: 2026-05-24*
