#!/usr/bin/env python3
"""MCP server: mcp-agentops - Agent Observability & Operations.

Agent observability: health checks, metrics collection, alerting, log aggregation,
performance profiling, debugging hooks, and operational tooling for agent fleets.
"""

from __future__ import annotations

import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from tools import TOOLS
from handlers import HANDLERS

SERVICE_NAME = "mcp-agentops"
VERSION = "1.0.0"

app = Server(SERVICE_NAME)


@app.list_tools()
async def list_tools():
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text='{"status": "error", "error": "unknown tool ' + name + '"}')]
    try:
        result = handler(arguments or {})
    except Exception as exc:
        return [TextContent(type="text", text='{"status": "error", "error": "' + str(exc).replace('"', '\\"') + '"}')]
    result.setdefault("status", "ok")
    result.setdefault("tool", name)
    result.setdefault("service", SERVICE_NAME)
    result.setdefault("version", VERSION)
    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import json
    asyncio.run(_main())