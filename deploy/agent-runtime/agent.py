"""Google Cloud Agent Runtime (Gemini Enterprise Agent Platform; formerly Vertex AI Agent Engine) wrapper.

Agent Runtime deploys a Python object with `set_up()` and `query()` (a custom agent template). This class wraps the
kit runtime, so any adapter (ADK is the natural fit on Google Cloud) runs the same definition:

    from agent import KitAgent
    remote = agent_engines.create(KitAgent(kit_dir="kit"), requirements=["agent-starter-kit[adk]"], extra_packages=["kit"])
    remote.query(prompt="Where is ORD-10003?", user_id="cust-001")

The SDK entry point has moved with the platform rename; check the Agent Platform docs for the current module name.
Status: implemented, not yet deployed live.
"""
from __future__ import annotations

import asyncio


class KitAgent:
    def __init__(self, kit_dir: str = "kit"):
        self.kit_dir = kit_dir
        self._rt = None

    def set_up(self) -> None:
        from agent_kit.runtime import AgentRuntime
        self._rt = AgentRuntime.from_path(self.kit_dir)

    def query(self, *, prompt: str, user_id: str, tenant: str = "default", session_id: str | None = None) -> dict:
        from agent_kit.tools import User
        if self._rt is None:
            self.set_up()
        r = asyncio.run(self._rt.chat(prompt, User(user_id, tenant), session_id))
        return {"message": r.message, "session_id": r.session_id, "tool_calls": [{"name": c["name"], "args": c["args"]} for c in r.tool_calls],
                "pending_approvals": r.pending_approvals, "framework": r.framework, "model": r.model}
