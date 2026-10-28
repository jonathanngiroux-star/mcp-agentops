#!/usr/bin/env python3
"""Tool definitions and shared helpers for mcp-agentops - Agent Observability & Operations."""

import random
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mcp.types import Tool

METRIC_TYPES = [
    "latency_p50_ms",
    "latency_p95_ms",
    "latency_p99_ms",
    "throughput_rps",
    "error_rate",
    "token_usage",
    "memory_mb",
    "cpu_percent",
    "queue_depth",
    "active_sessions",
]

HEALTH_STATUSES = ["healthy", "degraded", "unhealthy", "unknown"]

ALERT_SEVERITIES = ["info", "warning", "critical", "emergency"]

AGENT_TEMPLATES = {
    "trading": {
        "type": "trading",
        "metrics": ["latency_p50_ms", "latency_p95_ms", "throughput_rps", "error_rate", "queue_depth"],
        "thresholds": {"latency_p95_ms": 500, "error_rate": 0.01, "queue_depth": 1000},
    },
    "monitoring": {
        "type": "monitoring",
        "metrics": ["latency_p50_ms", "latency_p95_ms", "throughput_rps", "error_rate"],
        "thresholds": {"latency_p95_ms": 200, "error_rate": 0.005},
    },
    "compliance": {
        "type": "compliance",
        "metrics": ["latency_p50_ms", "latency_p95_ms", "error_rate", "token_usage"],
        "thresholds": {"latency_p95_ms": 1000, "error_rate": 0.02, "token_usage": 100000},
    },
    "research": {
        "type": "research",
        "metrics": ["latency_p50_ms", "latency_p95_ms", "memory_mb", "cpu_percent"],
        "thresholds": {"latency_p95_ms": 2000, "memory_mb": 2048, "cpu_percent": 80},
    },
}


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def _state_dir() -> Path:
    override = os.environ.get("MCP_AGENTOPS_STATE_DIR")
    path = Path(override) if override else Path(__file__).resolve().parent / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path() -> Path:
    return _state_dir() / "agentops_state.json"


def _default_state() -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "agents": {},
        "metrics": [],
        "alerts": [],
        "logs": [],
        "profiles": [],
    }


def load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        state = _default_state()
        save_state(state)
        return state
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        state = _default_state()
    base = _default_state()
    base.update(state)
    for key, default in _default_state().items():
        if key not in base:
            base[key] = default
    return state


def save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".agentops_state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _agent_id(agent_type: str) -> str:
    return f"agent-{agent_type}-{random.randint(1000, 9999)}"


def _error(tool: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": "error", "tool": tool, "error": message}
    payload.update(extra)
    return payload


def _ok(tool: str, **fields: Any) -> dict[str, Any]:
    payload = {"status": "ok", "tool": tool, "service": "mcp-agentops", "version": "1.0.0"}
    payload.update(fields)
    return payload


# --------------------------------------------------------------------------
# Tool definitions
# --------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="register_agent",
        description="Register a new agent in the observability fleet with type, config, and metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_type": {"type": "string", "enum": ["trading", "monitoring", "compliance", "research", "custom"], "description": "Type of agent to register."},
                "name": {"type": "string", "description": "Human-readable name for the agent."},
                "config": {"type": "object", "description": "Agent-specific configuration."},
                "metadata": {"type": "object", "description": "Additional metadata (tags, environment, owner, etc.)."},
            },
            "required": ["agent_type", "name"],
        },
    ),
    Tool(
        name="get_agent_health",
        description="Get real-time health status for a specific agent or all agents.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Specific agent ID; omit for fleet-wide health."},
            },
            "required": [],
        },
    ),
    Tool(
        name="record_metrics",
        description="Record a metrics snapshot for an agent.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent identifier."},
                "metrics": {"type": "object", "description": "Metric name to value mapping."},
                "timestamp": {"type": "string", "description": "ISO-8601 timestamp; defaults to now."},
            },
            "required": ["agent_id", "metrics"],
        },
    ),
    Tool(
        name="get_metrics_history",
        description="Retrieve historical metrics for an agent with optional time window and aggregation.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent identifier."},
                "metric_names": {"type": "array", "items": {"type": "string"}, "description": "Specific metrics to retrieve; omit for all."},
                "window_minutes": {"type": "integer", "default": 60, "description": "Time window in minutes."},
                "aggregation": {"type": "string", "enum": ["raw", "avg", "min", "max", "p50", "p95", "p99"], "default": "raw", "description": "Aggregation method."},
            },
            "required": ["agent_id"],
        },
    ),
    Tool(
        name="create_alert",
        description="Create an alert rule or trigger a manual alert.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent to alert on; omit for fleet-wide."},
                "metric": {"type": "string", "enum": METRIC_TYPES, "description": "Metric to monitor."},
                "condition": {"type": "string", "enum": [">", "<", ">=", "<=", "==", "!="], "description": "Comparison operator."},
                "threshold": {"type": "number", "description": "Threshold value."},
                "severity": {"type": "string", "enum": ["info", "warning", "critical", "emergency"], "default": "warning", "description": "Alert severity."},
                "description": {"type": "string", "description": "Human-readable alert description."},
                "cooldown_minutes": {"type": "integer", "default": 15, "description": "Cooldown between alert firings."},
            },
            "required": ["metric", "condition", "threshold"],
        },
    ),
    Tool(
        name="get_alerts",
        description="Retrieve active and historical alerts.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Filter by agent."},
                "severity": {"type": "string", "enum": ["info", "warning", "critical", "emergency"], "description": "Filter by severity."},
                "status": {"type": "string", "enum": ["firing", "resolved", "acknowledged"], "description": "Filter by alert status."},
                "limit": {"type": "integer", "default": 50, "description": "Maximum results."},
            },
            "required": [],
        },
    ),
    Tool(
        name="run_profile",
        description="Run a performance profile on an agent (CPU, memory, latency profiling).",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent to profile."},
                "profile_type": {"type": "string", "enum": ["cpu", "memory", "latency", "full"], "default": "full", "description": "Type of profile to run."},
                "duration_seconds": {"type": "integer", "default": 30, "description": "Profiling duration in seconds."},
            },
            "required": ["agent_id"],
        },
    ),
    Tool(
        name="get_logs",
        description="Retrieve aggregated logs for an agent with filtering.",
        inputSchema={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent identifier."},
                "level": {"type": "string", "enum": ["debug", "info", "warning", "error", "critical"], "description": "Minimum log level."},
                "since": {"type": "string", "description": "ISO-8601 timestamp to filter from."},
                "limit": {"type": "integer", "default": 100, "description": "Maximum log entries."},
            },
            "required": ["agent_id"],
        },
    ),
]