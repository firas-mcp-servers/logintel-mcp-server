# LogIntel MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/packaging-poetry-purple.svg)](https://python-poetry.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Universal Model Context Protocol (MCP) server** that connects LLMs to application logs across Datadog, Grafana Loki, AWS CloudWatch, and local log files.

Ask your AI assistant questions like:
- *"Why did orders spike at 2 AM?"*
- *"Find all timeout errors in the payment service from last hour"*
- *"Correlate 500 errors across api, payment, and db services"*

## Features

- 🔌 **Multi-backend support** — Datadog, Grafana Loki, AWS CloudWatch, local files
- 🔍 **Natural language queries** — Ask in plain English, get structured results
- 🧠 **Intelligent analysis** — Error pattern detection, anomaly detection, root cause analysis
- 🔗 **Cross-service correlation** — Trace ID, timestamp proximity, and field matching
- ⚡ **Streaming & pagination** — Handle large result sets without context overflow
- 🛡️ **Read-only by default** — Safe to use in production; no log mutation

## Quick Start

### Installation

```bash
# Using Poetry (development)
git clone https://github.com/firas-mcp-servers/logintel-mcp-server.git
cd logintel-mcp-server
poetry install

# Using uv (if published to PyPI)
uvx -y logintel-mcp --config ~/.logintelrc.yaml
```

### Configuration

Create a `.logintelrc.yaml` file:

```yaml
version: "1.0"

sources:
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
```

### Run the Server

```bash
# stdio transport (default)
poetry run logintel --config ./.logintelrc.yaml

# Or via Python module
poetry run python -m logintel --config ./.logintelrc.yaml
```

### Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
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
{
  "mcpServers": {
    "log-intel": {
      "command": "uvx",
      "args": ["-y", "logintel-mcp", "--config", "/path/to/.logintelrc.yaml"]
    }
  }
}
```

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Linting
poetry run ruff check src tests
poetry run ruff format src tests

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

See [AGENTS.md](AGENTS.md) for the full implementation plan. High-level phases:

| Phase | Focus | Timeline |
|-------|-------|----------|
| 0 | Foundation — scaffolding, config, health checks | Week 1 |
| 1 | Local File Provider — grep, tail, JSON parsing | Week 1-2 |
| 2 | CloudWatch Provider — Logs Insights, patterns | Week 2-3 |
| 3 | Datadog Provider — Log Search, analytics | Week 3-4 |
| 4 | Loki Provider — LogQL, label filtering | Week 4-5 |
| 5 | Intelligence Layer — root cause, correlation | Week 5-6 |
| 6 | Polish — tests, Docker, PyPI, CI/CD | Week 6-7 |

## Contributing

We welcome contributions! Please read our [Code of Conduct](CODE_OF_CONDUCT.md) and open an issue or pull request.

## License

[MIT](LICENSE)
