<!-- From: /Users/firasmosbehi/Desktop/personal/Log Intelligence MCP/AGENTS.md -->
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
3. **Natural Language First** — High-level tools accept natural language and translate to provider-specific query languages.
4. **Streaming for Large Results** — Support pagination and result limits to avoid context window overflow.
5. **Correlation as First-Class** — Cross-service correlation tools can query multiple backends simultaneously.
6. **Caching & Deduplication** — In-memory LRU cache for repeated queries; deduplicate similar error patterns.

---

## Supported Backends

| Backend | Protocol | Query Language | Key Capabilities |
|---------|----------|---------------|-----------------|
| **Datadog** | REST API | Lucene-like + facet search | Full-text search, facets, analytics, trace correlation |
| **Grafana Loki** | HTTP API | LogQL | Label filtering, metric extraction from logs, trace correlation |
| **AWS CloudWatch** | AWS SDK | CloudWatch Logs Insights | SQL-like queries, pattern detection, anomaly detection |
| **Local Log Files** | filesystem | regex / grep | Tail, search, parse structured logs (JSON), multi-file correlation |

### Future Backends
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
    "tools": { "listChanged": true },
    "resources": { "subscribe": true, "listChanged": true },
    "prompts": { "listChanged": true }
  }
}
```

---

## Tool Registry

### Discovery & Metadata Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `list_log_sources` | List all configured log sources | ✅ |
| `get_source_schema` | Get field/schema info for a source | ✅ |
| `get_source_health` | Check connectivity and health of a log source | ✅ |

### Core Query Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `search_logs` | Search logs with natural language or structured query | ✅ |
| `filter_logs` | Filter logs by structured criteria | ✅ |
| `aggregate_logs` | Aggregate/group logs | ✅ |
| `tail_logs` | Stream/follow logs in real-time | ✅ |

### Intelligence & Analysis Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `detect_error_patterns` | Group similar errors, find recurring patterns | ✅ |
| `find_anomalies` | Detect statistical anomalies in log volume, error rates | ✅ |
| `correlate_logs` | Correlate logs across services by trace ID or timestamp | ✅ |
| `analyze_root_cause` | Analyze surrounding logs to suggest root cause | ✅ |
| `summarize_logs` | Generate natural language summary of a set of logs | ✅ |
| `compare_time_periods` | Compare logs between two time windows | ✅ |

### Translation & Helper Tools

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `natural_language_to_query` | Translate NL to the target backend's query language | ✅ |
| `explain_query` | Explain what a backend-specific query does | ✅ |

---

## Prompt Registry

| Prompt | Description |
|--------|-------------|
| `investigate_incident` | Structured investigation workflow: detect anomalies → search → correlate → RCA → summarize |
| `oncall_summary` | Generate a shift summary: errors, anomalies, top issues, recommended actions |

---

## Technology Stack

```
Runtime:     Python 3.11+
Framework:   mcp (FastMCP from official python-sdk)
Transport:   stdio (default) + HTTP (optional)
Validation:  Pydantic
HTTP Client: httpx
AWS SDK:     boto3
Config:      pydantic-settings
Caching:     cachetools (TTLCache)
Testing:     pytest, pytest-asyncio, pytest-httpx, respx, moto
Linting:     ruff
Type check:  pyright
Packaging:   Poetry
Docker:      python:3.14-slim multi-stage
CI/CD:       GitHub Actions
```

---

## Implementation Status

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Foundation — LogProvider ABC, config, MCP server scaffolding | ✅ |
| 1 | Local File Provider — JSON/regex/plain-text parsing, 100% coverage | ✅ |
| 2 | CloudWatch Provider — Logs Insights, cross-account STS, 100% coverage | ✅ |
| 3 | Datadog Provider — Logs v2 API, analytics, 100% coverage | ✅ |
| 4 | Loki Provider — LogQL, label filtering, metric queries, 100% coverage | ✅ |
| 5 | Intelligence Layer — cache, correlate, RCA, compare, NL2Query, prompts | ✅ |
| 6 | Polish — Docker, PyPI, npm, GitHub Actions CI/CD, docs | ✅ |

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
    site: "datadoghq.com"
    defaultIndexes: ["main", "prod"]

  loki-default:
    type: loki
    url: "http://localhost:3100"
    basicAuth:
      username: "admin"
      password: "${LOKI_PASSWORD}"
    tenantId: "tenant-1"
    defaultLabels:
      app: "api"

  cloudwatch-app:
    type: cloudwatch
    region: "us-east-1"
    profile: "production"
    logGroups:
      - "/aws/lambda/my-app"
    # crossAccountRoleArn: "arn:aws:iam::123456789012:role/CrossAccountRole"

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
  anomalySensitivity: "medium"
  maxCorrelationDepth: 3
```

---

## Key Implementation Decisions

### 1. Provider Interface

All providers implement a common async interface:

```python
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
```

### 2. NL2Query Strategy

Instead of fine-tuning a model, use **in-context learning** with the connected LLM:

- Build a system prompt with provider-specific query syntax reference + examples
- Include source schema in context
- Let the host LLM translate natural language → native query
- The MCP server validates and executes the generated query
- Fallback: return helpful error with query syntax docs

### 3. Result Format

All tools return a standardized log entry format:

```python
class LogEntry(BaseModel):
    timestamp: str       # ISO 8601
    level: str           # ERROR, WARN, INFO, DEBUG, TRACE
    message: str         # Raw or rendered message
    service: str | None  # Service name
    host: str | None     # Host/container
    trace_id: str | None # Distributed trace ID
    span_id: str | None  # Span ID
    source: str          # Source ID
    fields: dict[str, Any]  # Extracted structured fields
    raw: Any | None      # Provider-specific raw data
```

### 4. Security & Safety

- **Read-only**: All tools declare `readOnlyHint: true`
- **Credential isolation**: API keys via env vars only
- **Path sandboxing** (local provider): Only access paths listed in config
- **Query timeouts**: Configurable timeouts (default 30s)
- **Result limits**: Hard cap at 1000 entries per query
- **No PII extraction**: Don't build tools that extract user data

### 5. Correlation Engine

The `correlate_logs` and `analyze_root_cause` tools use a simple but effective strategy:

1. **Trace ID correlation**: Match `traceId` across sources (fastest, most accurate)
2. **Timestamp proximity**: Find logs within ±correlationWindow of target events
3. **Field matching**: Match on `service`, `host`, `requestId`, `userId`
4. **Causality heuristic**: ERROR → preceding WARN/INFO in same service; upstream before downstream

Results are scored by correlation strength and presented with confidence levels.

---

## Development Workflow

### Local Testing with MCP Inspector

```bash
# Install dependencies
poetry install

# Run tests
poetry run poe test

# Start server
poetry run python -m logintel --config ./examples/config.yaml

# In another terminal, run MCP Inspector
npx -y @modelcontextprotocol/inspector
```

### Claude Desktop Integration

```json
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
{
  "mcpServers": {
    "log-intel": {
      "command": "npx",
      "args": ["-y", "logintel-mcp-server", "--config", "./.logintelrc.yaml"]
    }
  }
}
```

---

## Testing Strategy

1. **Unit tests** — Each provider's query builder, result parser, utility functions
2. **Integration tests** — Mocked provider APIs, server tool dispatch
3. **E2E tests** — MCP Inspector automation or direct JSON-RPC over stdio
4. **Coverage gate** — 100% across all `src/` modules

---

## Package Naming

| Registry | Package |
|----------|---------|
| PyPI | `logintel-mcp` |
| npm | `logintel-mcp-server` |
| GitHub Container Registry | `ghcr.io/firas-mcp-servers/logintel-mcp-server` |
| GitHub | `firas-mcp-servers/logintel-mcp-server` |

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
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Datadog Log Search API](https://docs.datadoghq.com/api/latest/logs/)
- [Grafana Loki HTTP API](https://grafana.com/docs/loki/latest/api/)
- [CloudWatch Logs Insights Query Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)

---

*Last updated: 2026-05-24*
