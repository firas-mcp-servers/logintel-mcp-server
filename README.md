# LogIntel MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/packaging-poetry-purple.svg)](https://python-poetry.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/firas-mcp-servers/logintel-mcp-server/actions/workflows/test.yml/badge.svg)](https://github.com/firas-mcp-servers/logintel-mcp-server/actions/workflows/test.yml)

> **Universal Model Context Protocol (MCP) server** that connects LLMs to application logs across Datadog, Grafana Loki, AWS CloudWatch, and local log files.

Ask your AI assistant questions like:
- *"Why did orders spike at 2 AM?"*
- *"Find all timeout errors in the payment service from last hour"*
- *"Correlate 500 errors across api, payment, and db services"*
- *"Compare error rates before and after the deployment at 3 PM"*

## Features

- 🔌 **Multi-backend support** — Datadog, Grafana Loki, AWS CloudWatch, local files
- 🔍 **Natural language queries** — Ask in plain English, get structured results
- 📁 **Local file provider** — Search, filter, tail, and aggregate JSON/regex/plain-text logs
- ☁️ **CloudWatch provider** — Query AWS CloudWatch Logs Insights with natural language
- 📊 **Datadog provider** — Search and aggregate via Datadog Logs v2 API
- 🔥 **Loki provider** — Query Grafana Loki with LogQL label matchers and metric queries
- 🧠 **Intelligent analysis** — Root cause analysis, cross-service correlation, anomaly detection
- 🔗 **Cross-service correlation** — Trace ID, timestamp proximity, and field matching
- ⚡ **Caching & pagination** — TTL cache for repeated queries; cursor-based pagination
- 🛡️ **Read-only by default** — Safe to use in production; no log mutation

### MCP Tools

| Tool | Description |
|------|-------------|
| `list_log_sources` | List all configured log sources |
| `get_source_health` | Check connectivity of a source |
| `get_source_schema` | Get field/schema info for a source |
| `search_logs` | Search logs with natural language or query |
| `filter_logs` | Filter by time, level, service, host, custom fields |
| `tail_logs` | Return latest N entries from a source |
| `aggregate_logs` | Count/group by field, time bucketing |
| `summarize_logs` | Generate natural language summary |
| `correlate_logs` | Cross-source correlation by trace_id or timestamp |
| `analyze_root_cause` | Multi-step incident root cause analysis |
| `compare_time_periods` | Before/after comparison with diff report |
| `detect_error_patterns` | Detect recurring error patterns |
| `find_anomalies` | Statistical anomaly detection |
| `natural_language_to_query` | Translate NL to provider query syntax |
| `explain_query` | Explain a provider-native query in plain English |

### MCP Prompts

| Prompt | Description |
|--------|-------------|
| `investigate_incident` | Structured 6-step SRE investigation workflow |
| `oncall_summary` | Generate a concise shift summary |

## Quick Start

### Installation

#### PyPI (recommended)

```bash
pip install logintel-mcp

# Or with uv
uv pip install logintel-mcp
uvx -y logintel-mcp --config ~/.logintelrc.yaml
```

#### Docker (GHCR)

```bash
docker run --rm -v "$HOME/.logintelrc.yaml:/etc/logintel/.logintelrc.yaml" \
  ghcr.io/firas-mcp-servers/logintel-mcp-server:latest
```

#### From source

```bash
git clone https://github.com/firas-mcp-servers/logintel-mcp-server.git
cd logintel-mcp-server
poetry install
```

### Configuration

Create a `.logintelrc.yaml` file:

```yaml
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
    defaultLabels:
      app: "api"

  cloudwatch-app:
    type: cloudwatch
    region: "us-east-1"
    profile: "production"
    logGroups:
      - "/aws/lambda/my-app"

  local-app:
    type: local
    paths:
      - "/var/log/myapp/*.log"
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

### Run the Server

```bash
# stdio transport (default)
logintel-mcp --config ~/.logintelrc.yaml

# Or via Python module
python -m logintel --config ~/.logintelrc.yaml
```

### Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Or with Docker:

```json
{
  "mcpServers": {
    "log-intel": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/path/to/.logintelrc.yaml:/etc/logintel/.logintelrc.yaml",
        "ghcr.io/firas-mcp-servers/logintel-mcp-server:latest"
      ]
    }
  }
}
```

### Cursor Integration

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "log-intel": {
      "command": "python",
      "args": ["-m", "logintel", "--config", "./.logintelrc.yaml"]
    }
  }
}
```

## Development

```bash
# Install dependencies
poetry install --with dev

# Run tests (100% coverage gate)
poetry run pytest --cov=src/logintel --cov-fail-under=100

# Or use the convenience tasks
poetry run poe test       # full suite with coverage
poetry run poe test-fast  # quick run without coverage
poetry run poe lint       # ruff check
poetry run poe fix        # ruff check --fix + ruff format
poetry run poe check      # lint + test combo

# Run MCP Inspector for manual testing
poetry run python -m logintel --config ./examples/config.yaml
# In another terminal:
npx -y @modelcontextprotocol/inspector
```

## Architecture

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

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Foundation — scaffolding, config, health checks | ✅ Complete |
| 1 | Local File Provider | ✅ Complete |
| 2 | CloudWatch Provider | ✅ Complete |
| 3 | Datadog Provider | ✅ Complete |
| 4 | Loki Provider | ✅ Complete |
| 5 | Intelligence Layer — root cause, correlation, caching | ✅ Complete |
| 6 | Polish — Docker, PyPI, npm, CI/CD, docs | ✅ Complete |

## License

[MIT](LICENSE)
