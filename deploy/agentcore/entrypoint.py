"""Amazon Bedrock AgentCore Runtime entrypoint: the same agent and runtime, behind AgentCore's invoke contract.

AgentCore Runtime runs the container, gives each conversation a runtime session, and (with an inbound JWT
authorizer from AgentCore Identity) validates the caller's token before invoking. Payload:
    {"prompt": "...", "user_id": "<end user>", "tenant": "default"}
Use the API service (kit serve) instead when you need the approvals and session endpoints over HTTP; AgentCore
Runtime exposes only invoke, so approvals are decided through `kit` or a separate ops service sharing the store.

Status: implemented against the bedrock-agentcore SDK's BedrockAgentCoreApp; not yet deployed live.
"""
from __future__ import annotations

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # pip install bedrock-agentcore

from agent_kit.runtime import AgentRuntime
from agent_kit.tools import User

app = BedrockAgentCoreApp()
runtime = AgentRuntime.from_path(os.environ.get("KIT_DIR", "/app"))


@app.entrypoint
async def invoke(payload: dict, context=None) -> dict:
    user = User(str(payload.get("user_id") or "anonymous"), str(payload.get("tenant", "default")))
    session_id = getattr(context, "session_id", None) or payload.get("session_id")
    r = await runtime.chat(str(payload.get("prompt", "")), user, session_id)
    return {"message": r.message, "session_id": r.session_id, "tool_calls": [{"name": c["name"], "args": c["args"]} for c in r.tool_calls],
            "pending_approvals": r.pending_approvals, "framework": r.framework, "model": r.model}


if __name__ == "__main__":
    app.run()
