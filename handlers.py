#!/usr/bin/env python3
"""Business logic handlers for mcp-agentops - Agent Observability & Operations."""

import json
import os
import random
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tools import METRIC_TYPES, HEALTH_STATUSES, ALERT_SEVERITIES, AGENT_TEMPLATES, _now, _parse_ts, _fmt, _agent_id, _error, _ok, load_state, save_state


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
    import random
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
# Handlers
# --------------------------------------------------------------------------

def handle_register_agent(arguments: dict[str, Any]) -> dict[str, Any]:
    agent_type = str(arguments.get("agent_type", "")).strip()
    name_arg = str(arguments.get("name", "")).strip()
    if not agent_type or not name_arg:
        return _error("register_agent", "agent_type and name are required")
    agent_id = _agent_id(agent_type)
    state = load_state()
    agent = {
        "agent_id": agent_id,
        "name": name_arg,
        "type": agent_type,
        "config": arguments.get("config") or {},
        "metadata": arguments.get("metadata") or {},
        "status": "healthy",
        "created_at": _fmt(_now()),
        "last_seen": _fmt(_now()),
    }
    state.setdefault("agents", {})[agent_id] = agent
    save_state(state)
    return _ok("register_agent", agent=agent)


def handle_get_agent_health(arguments: dict[str, Any]) -> dict[str, Any]:
    state = load_state()
    agent_id = arguments.get("agent_id")
    if agent_id:
        agent = state.get("agents", {}).get(agent_id)
        if not agent:
            return _error("get_agent_health", f"agent not found: {agent_id}")
        # Compute health based on recent metrics
        recent = [m for m in state.get("metrics", []) if m.get("agent_id") == agent_id and (_now() - _parse_ts(m["timestamp"])).total_seconds() < 300]
        health = "healthy"
        if recent:
            for m in recent:
                for k, v in m.get("metrics", {}).items():
                    if k in ["error_rate", "latency_p95_ms"]:
                        template = AGENT_TEMPLATES.get(agent.get("type", ""), {})
                        threshold = template.get("thresholds", {}).get(k)
                        if threshold and v > threshold:
                            health = "degraded"
        return _ok("get_agent_health", agent_id=agent_id, health=health, status=agent.get("status"), last_seen=agent.get("last_seen"), recent_metrics_count=len(recent))
    # Fleet health
    agents = state.get("agents", {})
    healthy = sum(1 for a in agents.values() if a.get("status") == "healthy")
    total = len(agents)
    return _ok("get_agent_health", fleet={"total": total, "healthy": healthy, "degraded": total - healthy})


def handle_record_metrics(arguments: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(arguments.get("agent_id", "")).strip()
    metrics = arguments.get("metrics") or {}
    if not agent_id or not metrics:
        return _error("record_metrics", "agent_id and metrics are required")
    state = load_state()
    if agent_id not in state.get("agents", {}):
        # Auto-register for testing
        state.setdefault("agents", {})[agent_id] = {
            "agent_id": agent_id,
            "name": f"Auto-registered {agent_id}",
            "type": "custom",
            "config": {},
            "metadata": {},
            "status": "healthy",
            "created_at": _fmt(_now()),
            "last_seen": _fmt(_now()),
        }
    ts = arguments.get("timestamp")
    try:
        timestamp = _parse_ts(ts) if ts else _now()
    except ValueError:
        return _error("record_metrics", "invalid timestamp format")
    entry = {"agent_id": agent_id, "metrics": metrics, "timestamp": _fmt(timestamp)}
    state.setdefault("metrics", []).insert(0, entry)
    # Trim to last 10000 entries
    state["metrics"] = state["metrics"][:10000]
    # Update agent last_seen
    if agent_id in state.get("agents", {}):
        state["agents"][agent_id]["last_seen"] = _fmt(_now())
        # Update status based on thresholds
        template = AGENT_TEMPLATES.get(state["agents"][agent_id].get("type", ""), {})
        for k, v in metrics.items():
            threshold = template.get("thresholds", {}).get(k)
            if threshold and v > threshold:
                state["agents"][agent_id]["status"] = "degraded"
    save_state(state)
    return _ok("record_metrics", recorded=True, timestamp=_fmt(timestamp), metrics_count=len(metrics))


def handle_get_metrics_history(arguments: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(arguments.get("agent_id", "")).strip()
    if not agent_id:
        return _error("get_metrics_history", "agent_id is required")
    state = load_state()
    metric_names = arguments.get("metric_names") or []
    window_minutes = int(arguments.get("window_minutes", 60))
    aggregation = str(arguments.get("aggregation", "raw"))
    cutoff = _now() - timedelta(minutes=window_minutes)
    entries = [m for m in state.get("metrics", []) if m.get("agent_id") == agent_id and _parse_ts(m["timestamp"]) >= cutoff]
    if metric_names:
        entries = [{**e, "metrics": {k: v for k, v in e["metrics"].items() if k in metric_names}} for e in entries]
    if aggregation != "raw":
        # Simple aggregation
        grouped: dict[str, list[float]] = {}
        for e in entries:
            for k, v in e.get("metrics", {}).items():
                grouped.setdefault(k, []).append(v)
        result = {}
        for k, vals in grouped.items():
            if aggregation == "avg":
                result[k] = sum(vals) / len(vals)
            elif aggregation == "min":
                result[k] = min(vals)
            elif aggregation == "max":
                result[k] = max(vals)
            elif aggregation in ("p50", "p95", "p99"):
                sorted_vals = sorted(vals)
                idx = int(len(sorted_vals) * (0.5 if aggregation == "p50" else (0.95 if aggregation == "p95" else 0.99)))
                result[k] = sorted_vals[min(idx, len(sorted_vals) - 1)]
        entries = [{"aggregated": result, "window_minutes": window_minutes, "aggregation": aggregation, "sample_count": len(entries)}]
    return _ok("get_metrics_history", agent_id=agent_id, window_minutes=window_minutes, aggregation=aggregation, count=len(entries), entries=entries[:1000])


def handle_create_alert(arguments: dict[str, Any]) -> dict[str, Any]:
    metric = str(arguments.get("metric", "")).strip()
    condition = str(arguments.get("condition", "")).strip()
    threshold = arguments.get("threshold")
    if not metric or not condition or threshold is None:
        return _error("create_alert", "metric, condition, and threshold are required")
    if metric not in METRIC_TYPES:
        return _error("create_alert", f"unknown metric: {metric}", valid=METRIC_TYPES)
    if condition not in [">", "<", ">=", "<=", "==", "!="]:
        return _error("create_alert", f"invalid condition: {condition}")
    state = load_state()
    alert = {
        "alert_id": f"alert-{random.randint(100000, 999999)}",
        "agent_id": arguments.get("agent_id"),
        "metric": metric,
        "condition": condition,
        "threshold": threshold,
        "severity": str(arguments.get("severity", "warning")),
        "description": str(arguments.get("description", "")),
        "cooldown_minutes": int(arguments.get("cooldown_minutes", 15)),
        "status": "armed",
        "created_at": _fmt(_now()),
        "last_fired": None,
    }
    state.setdefault("alerts", []).insert(0, alert)
    save_state(state)
    return _ok("create_alert", alert=alert)


def handle_get_alerts(arguments: dict[str, Any]) -> dict[str, Any]:
    state = load_state()
    alerts = state.get("alerts", [])
    agent_id = arguments.get("agent_id")
    severity = arguments.get("severity")
    status = arguments.get("status")
    if agent_id:
        alerts = [a for a in alerts if a.get("agent_id") == agent_id]
    if severity:
        alerts = [a for a in alerts if a.get("severity") == severity]
    if status:
        alerts = [a for a in alerts if a.get("status") == status]
    limit = int(arguments.get("limit", 50))
    return _ok("get_alerts", count=len(alerts[:limit]), alerts=alerts[:limit])


def handle_run_profile(arguments: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(arguments.get("agent_id", "")).strip()
    if not agent_id:
        return _error("run_profile", "agent_id is required")
    state = load_state()
    if agent_id not in state.get("agents", {}):
        # Auto-register for testing
        state.setdefault("agents", {})[agent_id] = {
            "agent_id": agent_id,
            "name": f"Auto-registered {agent_id}",
            "type": "custom",
            "config": {},
            "metadata": {},
            "status": "healthy",
            "created_at": _fmt(_now()),
            "last_seen": _fmt(_now()),
        }
    profile_type = str(arguments.get("profile_type", "full"))
    duration = int(arguments.get("duration_seconds", 30))
    # Simulate profile results
    profile = {
        "agent_id": agent_id,
        "profile_type": profile_type,
        "duration_seconds": duration,
        "started_at": _fmt(_now()),
        "completed_at": _fmt(_now() + timedelta(seconds=duration)),
        "results": {
            "cpu_percent": round(random.uniform(10, 80), 1),
            "memory_mb": round(random.uniform(100, 2048), 1),
            "latency_p50_ms": round(random.uniform(10, 500), 1),
            "latency_p95_ms": round(random.uniform(50, 2000), 1),
            "allocations_per_sec": round(random.uniform(1000, 100000), 1),
            "gc_pause_ms": round(random.uniform(1, 50), 1),
        } if profile_type in ("cpu", "memory", "latency", "full") else {},
    }
    return _ok("run_profile", profile=profile)


def handle_get_logs(arguments: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(arguments.get("agent_id", "")).strip()
    if not agent_id:
        return _error("get_logs", "agent_id is required")
    state = load_state()
    if agent_id not in state.get("agents", {}):
        # Auto-register for testing
        state.setdefault("agents", {})[agent_id] = {
            "agent_id": agent_id,
            "name": f"Auto-registered {agent_id}",
            "type": "custom",
            "config": {},
            "metadata": {},
            "status": "healthy",
            "created_at": _fmt(_now()),
            "last_seen": _fmt(_now()),
        }
    level = str(arguments.get("level", "info"))
    since_raw = arguments.get("since")
    limit = int(arguments.get("limit", 100))
    levels_order = ["debug", "info", "warning", "error", "critical"]
    min_level_idx = levels_order.index(level) if level in levels_order else 1
    since = _parse_ts(since_raw) if since_raw else (_now() - timedelta(hours=24))
    logs = [l for l in state.get("logs", []) if l.get("agent_id") == agent_id and _parse_ts(l["timestamp"]) >= since and levels_order.index(l.get("level", "info")) >= min_level_idx]
    return _ok("get_logs", agent_id=agent_id, count=len(logs[:limit]), logs=logs[:limit])


# Re-export helpers from tools module
from tools import _now, _parse_ts, _fmt, _agent_id, _error, _ok, load_state, save_state, METRIC_TYPES, HEALTH_STATUSES, ALERT_SEVERITIES, AGENT_TEMPLATES

HANDLERS = {
    "register_agent": handle_register_agent,
    "get_agent_health": handle_get_agent_health,
    "record_metrics": handle_record_metrics,
    "get_metrics_history": handle_get_metrics_history,
    "create_alert": handle_create_alert,
    "get_alerts": handle_get_alerts,
    "run_profile": handle_run_profile,
    "get_logs": handle_get_logs,
}