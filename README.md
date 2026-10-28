# mcp-agentops

MCP server for **Agent Observability & Operations** — health checks, metrics collection,
alerting, log aggregation, performance profiling, debugging hooks, and operational tooling
for agent fleets.

## Tools

### `register_agent`
Register a new agent in the observability fleet.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_type` | string enum | **required** | `trading`, `monitoring`, `compliance`, `research`, `custom` |
| `name` | string | **required** | Human-readable name |
| `config` | object | - | Agent-specific configuration |
| `metadata` | object | - | Additional metadata (tags, environment, owner) |

Returns the created agent with generated `agent_id`, status, and timestamps.

### `get_agent_health`
Get real-time health status for a specific agent or fleet-wide.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | string | - | Specific agent ID; omit for fleet-wide health |

Returns health status (`healthy`/`degraded`/`unhealthy`), last seen, and recent metrics count.

### `record_metrics`
Record a metrics snapshot for an agent.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | string | **required** | Agent identifier |
| `metrics` | object | **required** | Metric name to value mapping |
| `timestamp` | string | now | ISO-8601 timestamp |

Updates agent status based on configured thresholds.

### `get_metrics_history`
Retrieve historical metrics with optional aggregation.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | string | **required** | Agent identifier |
| `metric_names` | array | - | Specific metrics to retrieve |
| `window_minutes` | integer | 60 | Time window |
| `aggregation` | string enum | `raw` | `raw`, `avg`, `min`, `max`, `p50`, `p95`, `p99` |

Returns raw entries or aggregated results.

### `create_alert`
Create an alert rule or trigger a manual alert.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | string | - | Agent to alert on; omit for fleet-wide |
| `metric` | string enum | **required** | Metric to monitor (from METRIC_TYPES) |
| `condition` | string enum | **required** | `>`, `<`, `>=`, `<=`, `==`, `!=` |
| `threshold` | number | **required** | Threshold value |
| `severity` | string enum | `warning` | `info`, `warning`, `critical`, `emergency` |
| `description` | string | - | Human-readable description |
| `cooldown_minutes` | integer | 15 | Cooldown between firings |

Returns the created alert rule with `alert_id`.

### `get_alerts`
Retrieve active and historical alerts with filtering.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | string | - | Filter by agent |
| `severity` | string enum | - | Filter by severity |
| `status` | string enum | - | `firing`, `resolved`, `acknowledged` |
| `limit` | integer | 50 | Maximum results |

### `run_profile`
Run a performance profile on an agent.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | string | **required** | Agent to profile |
| `profile_type` | string enum | `full` | `cpu`, `memory`, `latency`, `full` |
| `duration_seconds` | integer | 30 | Profiling duration |

Returns simulated profile results with CPU, memory, latency stats.

### `get_logs`
Retrieve aggregated logs for an agent with filtering.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_id` | string | **required** | Agent identifier |
| `level` | string enum | `info` | `debug`, `info`, `warning`, `error`, `critical` |
| `since` | string | 24h ago | ISO-8601 timestamp |
| `limit` | integer | 100 | Maximum log entries |

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

State persisted in `./state/`. Override with `MCP_AGENTOPS_STATE_DIR`.

## Connecting to an MCP client

```json
{
  "mcpServers": {
    "agentops": {
      "command": "python3",
      "args": ["/tmp/v3-services/mcp-agentops/main.py"]
    }
  }
}
```

## License

MIT