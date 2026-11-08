"""Tools from MCP servers, such as the connector hub (agent-connector-hub), listed at start-up and called per turn.

    mcp_tools:
      - url: "${CONNECTOR_HUB_URL:-http://127.0.0.1:8000}/mcp/${CONNECTOR_HUB_PROFILE:-support-agent}"
        headers_env: {X-API-Key: CONNECTOR_HUB_API_KEY}   # header -> env var holding its value
        forward_user: true      # send X-End-User-Id / X-End-User-Roles / X-Tenant for the hub's api_key mode
        include: []             # only these tool names (default: all the server lists)
        prefix: ""              # prepended to tool names, to avoid clashes with local tools

The kit's own policies apply to these tools too; the hub applies its own (identity, approvals, audit) on top.
A hub result with status pending_approval is passed to the model as-is: the action waits for a person in the hub.
Needs the [connectors] extra (the MCP Python SDK).
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .tools import ToolContext, ToolSpec


class McpToolsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    headers_env: dict[str, str] = Field(default_factory=dict)
    forward_user: bool = True
    include: list[str] = Field(default_factory=list)
    prefix: str = ""
    timeout_s: float = 30.0


def _run(coro):
    """Run a coroutine from sync code, also when the calling thread already has an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def target():
        try:
            box["v"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001
            box["e"] = e
    t = threading.Thread(target=target)
    t.start()
    t.join()
    if "e" in box:
        raise box["e"]
    return box["v"]


def _headers(cfg: McpToolsConfig, ctx: ToolContext | None) -> dict[str, str]:
    h = {}
    for name, env in cfg.headers_env.items():
        v = os.environ.get(env)
        if not v:
            raise RuntimeError(f"mcp_tools {cfg.url}: environment variable {env} (for {name}) is not set")
        h[name] = v
    if cfg.forward_user and ctx is not None:
        h.update({"X-End-User-Id": ctx.user.id, "X-End-User-Roles": ",".join(ctx.user.roles), "X-Tenant": ctx.user.tenant})
    return h


def _client(cfg: McpToolsConfig, ctx: ToolContext | None):
    try:
        import httpx2
        from mcp.client import Client
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as e:  # pragma: no cover - depends on the extra
        raise RuntimeError("mcp_tools needs the MCP SDK: pip install 'agent-starter-kit[connectors]'") from e
    return Client(streamable_http_client(cfg.url, http_client=httpx2.AsyncClient(headers=_headers(cfg, ctx),
                                                                                 timeout=cfg.timeout_s)))


async def _list(cfg: McpToolsConfig) -> list[Any]:
    async with _client(cfg, None if not cfg.forward_user else _probe_ctx()) as c:
        return (await c.list_tools()).tools


def _probe_ctx() -> ToolContext:
    from .tools import User
    return ToolContext(User(os.environ.get("KIT_MCP_LIST_AS", "agent-kit"), "default", []), "startup")


def _result(r) -> dict[str, Any]:
    value = r.structured_content
    if value is None:
        text = "\n".join(getattr(c, "text", "") for c in (r.content or []))
        try:
            value = json.loads(text)
        except ValueError:
            value = {"result": text}
    if not isinstance(value, dict):
        value = {"result": value}
    if r.is_error:
        return {"status": "error", "error": value.get("message") or value.get("result") or "the tool failed"}
    return value


def _spec(cfg: McpToolsConfig, tool) -> ToolSpec:
    upstream = tool.name

    def fn(ctx: ToolContext, **args) -> dict[str, Any]:
        async def call():
            async with _client(cfg, ctx) as c:
                return _result(await c.call_tool(upstream, args))
        return _run(call())

    schema = dict(tool.input_schema or {"type": "object", "properties": {}})
    schema.setdefault("properties", {})
    desc = (tool.description or upstream).split("\n\n")[0].strip()
    return ToolSpec(cfg.prefix + upstream, desc, schema, lambda ctx=None, **a: fn(ctx, **a), True)


def load_mcp_tools(configs: list[dict[str, Any]]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for raw in configs:
        cfg = McpToolsConfig(**raw)
        try:
            tools = _run(_list(cfg))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"mcp_tools: could not list tools at {cfg.url}: {type(e).__name__}: {e}") from None
        for t in tools:
            if cfg.include and t.name not in cfg.include:
                continue
            specs.append(_spec(cfg, t))
    return specs
