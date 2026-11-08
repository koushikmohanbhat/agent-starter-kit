"""mcp_tools: tools from an MCP server (a stand-in for the connector hub) bound like local tools."""
import json
import socket
import threading
import time

import pytest

pytest.importorskip("mcp")

import uvicorn  # noqa: E402
from mcp import types  # noqa: E402
from mcp.server import Server  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from agent_kit.config import PolicySpec  # noqa: E402
from agent_kit.mcp_tools import load_mcp_tools  # noqa: E402
from agent_kit.policies import PolicySet  # noqa: E402
from agent_kit.tools import BoundTool, RunState, ToolContext, User  # noqa: E402

SEEN = []


def hub_like_server():
    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[
            types.Tool(name="get_policy", description="Get a policy.\n\nMore detail.",
                       input_schema={"type": "object", "properties": {"policy_number": {"type": "string"}},
                                     "required": ["policy_number"]}),
            types.Tool(name="open_claim", description="Open a claim.",
                       input_schema={"type": "object", "properties": {"amount": {"type": "number"}}})])

    async def call_tool(ctx, params):
        h = ctx.request.headers
        SEEN.append({"key": h.get("x-api-key"), "user": h.get("x-end-user-id"), "roles": h.get("x-end-user-roles")})
        if h.get("x-api-key") != "k1":
            return types.CallToolResult(content=[types.TextContent(type="text", text="bad key")], is_error=True)
        if params.name == "open_claim":
            payload = {"status": "pending_approval", "approval_id": "apr_1", "message": "needs a supervisor"}
        elif params.arguments.get("policy_number") == "POL-0":
            return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(
                {"status": "error", "message": "policy POL-0 was not found"}))],
                structured_content={"status": "error", "message": "policy POL-0 was not found"}, is_error=True)
        else:
            payload = {"policy_number": params.arguments["policy_number"], "status": "active", "for": h.get("x-end-user-id")}
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload))],
                                    structured_content=payload)

    return Server("hub-like", on_list_tools=list_tools, on_call_tool=call_tool)


@pytest.fixture(scope="module")
def hub_url():
    app = hub_like_server().streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0",
                                                transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True


def test_mcp_tools_bind_and_forward_identity(hub_url, monkeypatch):
    monkeypatch.setenv("HUB_KEY", "k1")
    specs = load_mcp_tools([{"url": hub_url, "headers_env": {"X-API-Key": "HUB_KEY"}, "prefix": "ins_"}])
    assert [s.name for s in specs] == ["ins_get_policy", "ins_open_claim"]
    assert specs[0].description == "Get a policy." and specs[0].schema["required"] == ["policy_number"]
    user = User("cust-001", "default", ["customer"])
    run = RunState("s1", user, 8, None)
    ctx = ToolContext(user, "s1")
    pol = PolicySet([PolicySpec(tool="ins_open_claim", deny_if="args.amount > 1000000", message="too big")])
    get = BoundTool(specs[0], ctx, pol, run)
    out = get.call_sync({"policy_number": "POL-1"})
    assert out == {"policy_number": "POL-1", "status": "active", "for": "cust-001"}
    assert SEEN[-1] == {"key": "k1", "user": "cust-001", "roles": "customer"}
    assert get.call_sync({"policy_number": "POL-0"}) == {"status": "error", "error": "policy POL-0 was not found"}
    claim = BoundTool(specs[1], ctx, pol, run)
    assert claim.call_sync({"amount": 5})["status"] == "pending_approval"        # the hub holds it
    assert claim.call_sync({"amount": 5_000_000})["status"] == "denied"          # the kit's own policy first


def test_include_and_errors(hub_url, monkeypatch):
    monkeypatch.setenv("HUB_KEY", "k1")
    assert [s.name for s in load_mcp_tools([{"url": hub_url, "headers_env": {"X-API-Key": "HUB_KEY"},
                                             "include": ["get_policy"]}])] == ["get_policy"]
    with pytest.raises(RuntimeError, match="NOPE_KEY"):
        load_mcp_tools([{"url": hub_url, "headers_env": {"X-API-Key": "NOPE_KEY"}}])
    with pytest.raises(RuntimeError, match="could not list tools"):
        load_mcp_tools([{"url": "http://127.0.0.1:9/mcp", "forward_user": False}])


def test_policy_items_not_shadowed():
    ps = PolicySet([PolicySpec(tool="t", deny_if="len(args.items) > 2")])
    assert ps.evaluate("t", {"items": [1, 2, 3]}, {"id": "u", "roles": []}).action == "deny"
