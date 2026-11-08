"""AgentRuntime: one agent definition + one framework adapter + sessions + approvals.

    rt = AgentRuntime.from_path("kits/support-agent")
    result = await rt.chat("Where is ORD-10003?", user=User("cust-001"))
    await rt.decide(result.pending_approvals[0]["id"], approve=True, approver=User("lead-1", roles=["support_lead"]))
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import telemetry
from .adapters import get_adapter, resolve_model
from .config import AgentDefinition, load_agent
from .policies import PolicySet
from .prompts import resolve
from .stores import Store, open_store
from .tools import BoundTool, RunState, ToolContext, User, import_ref, load_tools


class ApprovalError(ValueError):
    pass


class RefusedByHook(PermissionError):
    """An inbound hook refused the message (e.g. the DPDP add-on when consent for the purpose was withdrawn)."""


@dataclass
class ChatResult:
    session_id: str
    message: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] | None = None
    usage: dict[str, int] = field(default_factory=dict)
    framework: str = ""
    model: str = ""
    prompt: dict[str, str] = field(default_factory=dict)
    trace_id: str | None = None
    latency_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class AgentRuntime:
    def __init__(self, definition: AgentDefinition, store: Store | None = None, services: dict[str, Any] | None = None,
                 framework: str | None = None):
        self.definition = definition
        self.framework = framework or definition.framework
        self.tool_specs = load_tools(definition.tools, definition.base_dir)
        if definition.mcp_tools:
            from .mcp_tools import load_mcp_tools
            self.tool_specs += load_mcp_tools(definition.mcp_tools)
            names = [t.name for t in self.tool_specs]
            dupes = sorted({n for n in names if names.count(n) > 1})
            if dupes:
                raise ValueError(f"tool names must be unique (use mcp_tools.prefix): {dupes}")
        self.policies = PolicySet(definition.policies)
        unknown = {p.tool for p in definition.policies} - {t.name for t in self.tool_specs}
        if unknown:
            raise ValueError(f"policies refer to unknown tools: {sorted(unknown)}")
        self.instructions = resolve(definition.path(definition.prompts_dir), definition.instructions)
        sess = definition.session
        self.store = store or open_store(sess.get("store", "memory://"), float(sess.get("ttl_hours", 72)))
        import os
        self.test_mode = os.environ.get("KIT_TEST_MODE", "false").lower() == "true"
        self._service_factories = {k: import_ref(v, definition.base_dir) for k, v in definition.services.items()}
        self.services = services if services is not None else {k: f() for k, f in self._service_factories.items()}
        self._sandboxes: dict[str, dict[str, Any]] = {}
        self.turn_state = import_ref(definition.test_state, definition.base_dir) if definition.test_state else None
        self.hooks = {k: import_ref(v, definition.base_dir) for k, v in definition.hooks.items()}
        if "redact" in self.hooks:
            telemetry.set_redactor(self.hooks["redact"])
        self.model = resolve_model(definition.model, definition.base_dir)
        self.adapter = get_adapter(self.framework, definition, self.model)

    @classmethod
    def from_path(cls, path: str | Path, **kw) -> AgentRuntime:
        overrides = kw.pop("overrides", None)
        return cls(load_agent(path, overrides), **kw)

    # ---- sessions ---------------------------------------------------------------------
    def _session(self, sid: str | None, user: User) -> dict[str, Any]:
        s = self.store.get_session(sid) if sid else None
        if s and (s["user_id"] != user.id or s["tenant"] != user.tenant):
            s = None          # never continue another user's session; start a new one instead
        if s is None:
            now = time.time()
            s = {"id": sid if sid and not self.store.get_session(sid) else f"ses_{uuid.uuid4().hex[:16]}", "user_id": user.id,
                 "tenant": user.tenant, "messages": [], "created_at": now, "updated_at": now}
        return s

    def _append(self, s: dict[str, Any], role: str, content: str, **extra) -> None:
        s["messages"].append({"role": role, "content": content, "ts": time.time(), **extra})
        s["updated_at"] = time.time()

    # ---- one turn ---------------------------------------------------------------------
    async def chat(self, message: str, user: User, session_id: str | None = None,
                   emit: Callable[[dict[str, Any]], None] | None = None) -> ChatResult:
        t0 = time.perf_counter()
        s = self._session(session_id, user)
        if "inbound" in self.hooks:
            message = self.hooks["inbound"](message, user, s["id"])      # may tokenise, or raise RefusedByHook
        history = [{"role": m["role"], "content": m["content"]} for m in s["messages"] if m["role"] in ("user", "assistant")]
        run = RunState(s["id"], user, self.definition.limits.max_tool_calls, emit, self.store)
        services = self.services
        if self.test_mode:      # each session gets its own sandboxed services, so eval cases don't affect each other
            services = self._sandboxes.setdefault(s["id"], {k: f() for k, f in self._service_factories.items()})
        ctx = ToolContext(user=user, session_id=s["id"], services=services)
        tools = [BoundTool(t, ctx, self.policies, run) for t in self.tool_specs]
        ins = self.instructions
        attrs = {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": self.definition.name, "gen_ai.provider.name": self.model.provider,
                 "gen_ai.request.model": self.model.name, "session.id": s["id"], "prompt.id": ins.id, "prompt.version": ins.version,
                 "prompt.hash": ins.hash, "agent_kit.framework": self.framework, "enduser.id": user.id}
        with telemetry.span(f"invoke_agent {self.definition.name}", attrs) as sp:
            ctx.trace_id = telemetry.trace_id()
            import asyncio
            try:
                res = await asyncio.wait_for(self.adapter.run(ins.text, tools, history, message), timeout=self.definition.limits.timeout_s)
                text = res.text.strip()
            except asyncio.TimeoutError:
                res, text = None, "Sorry, that took too long. Please try again, or ask for a human agent."
            if sp is not None and res is not None:
                sp.set_attribute("gen_ai.usage.input_tokens", res.usage.get("input_tokens", 0))
                sp.set_attribute("gen_ai.usage.output_tokens", res.usage.get("output_tokens", 0))
        self._append(s, "user", message)
        self._append(s, "assistant", text, tool_calls=[{k: c[k] for k in ("name", "args", "result") if k in c} for c in run.tool_calls])
        self.store.save_session(s)
        if "on_session_saved" in self.hooks:
            self.hooks["on_session_saved"](s, user)
        out = ChatResult(session_id=s["id"], message=text, tool_calls=run.tool_calls,
                         pending_approvals=[{k: a[k] for k in ("id", "tool", "args", "approver_role", "reason", "status")}
                                            for a in run.approvals_requested],
                         usage=res.usage if res else {}, framework=self.framework, model=self.model.name,
                         prompt={"id": ins.id, "version": ins.version, "hash": ins.hash}, trace_id=ctx.trace_id,
                         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
        if self.test_mode and self.turn_state:
            out.state = self.turn_state(run.tool_calls)
        if emit:
            emit({"type": "final", **{k: v for k, v in out.as_dict().items() if k != "tool_calls"}})
        return out

    def erase_user(self, user_id: str, tenant: str) -> int:
        n = self.store.delete_user(user_id, tenant)
        if "on_user_erased" in self.hooks:
            self.hooks["on_user_erased"](user_id, tenant)
        return n

    # ---- approvals ----------------------------------------------------------------------
    async def decide(self, approval_id: str, approve: bool, approver: User, reason: str = "") -> dict[str, Any]:
        """Approve (runs the held tool call with the original user's identity) or reject; tells the customer either way."""
        ap = self.store.get_approval(approval_id)
        if ap is None:
            raise KeyError(approval_id)
        if ap["status"] != "pending":
            raise ApprovalError(f"approval {approval_id} is already {ap['status']}")
        if ap["approver_role"] not in approver.roles:
            raise PermissionError(f"approving {ap['tool']} needs the {ap['approver_role']} role")
        if ap["user"]["tenant"] != approver.tenant:
            raise PermissionError("approver is in a different tenant")
        spec = next(t for t in self.tool_specs if t.name == ap["tool"])
        owner = User(ap["user"]["id"], ap["user"]["tenant"], ap["user"].get("roles", []))
        result = None
        if approve:
            services = self._sandboxes.get(ap["session_id"], self.services) if self.test_mode else self.services
            ctx = ToolContext(user=owner, session_id=ap["session_id"], services=services)
            with telemetry.span(f"execute_tool {spec.name}", {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": spec.name,
                                                              "agent_kit.approval_id": approval_id, "session.id": ap["session_id"]}):
                try:
                    res = spec.fn(**ap["args"], ctx=ctx) if spec.wants_ctx else spec.fn(**ap["args"])
                    result = json.loads(json.dumps(res, default=str))
                except Exception as e:  # noqa: BLE001
                    result = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        ap.update(status="approved" if approve else "rejected", decided_by=approver.id, decided_at=time.time(), decision_reason=reason,
                  result=result)
        self.store.put_approval(ap)
        msg = self._approval_message(ap)
        s = self.store.get_session(ap["session_id"])
        if s is not None:
            self._append(s, "assistant", msg, approval={"id": approval_id, "status": ap["status"]})
            self.store.save_session(s)
        return {"approval": ap, "message": msg}

    def _approval_message(self, ap: dict[str, Any]) -> str:
        """Templated (not model-generated), so the outcome reported to the customer is exactly what happened."""
        tmpl = (self.definition.escalation.get("approval_messages") or {})
        key = ap["status"] if ap["status"] == "rejected" or not (ap.get("result") or {}).get("status") == "error" else "error"
        default = {"approved": "Good news: your request ({tool}) was approved and has been completed.",
                   "rejected": "Your request ({tool}) was reviewed and could not be approved. {decision_reason}",
                   "error": "Your request ({tool}) was approved, but something went wrong completing it. A colleague will follow up."}
        fmt = {**ap["args"], **(ap.get("result") or {}), "tool": ap["tool"], "decision_reason": ap.get("decision_reason") or ""}
        try:
            return (tmpl.get(key) or default[key]).format(**fmt).strip()
        except (KeyError, IndexError):
            return default[key].format(**fmt).strip()
