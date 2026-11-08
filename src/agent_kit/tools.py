"""The tool contract: plain typed Python functions, written once and given to every framework adapter.

    def lookup_order(order_id: str, *, ctx: ToolContext) -> dict:
        '''Look up an order by its id (e.g. ORD-10001).'''

- The JSON schema comes from the type hints (pydantic), the description from the docstring.
- `ctx` (end user, session, services) is injected by the kit and never shown to the model, so identity can't be
  forged by a prompt: tools enforce record-level access from `ctx.user`, not from model arguments.
- Every call goes through `BoundTool.call`: policy check (allow / deny / require approval), limits, events, errors.
"""
from __future__ import annotations

import importlib
import inspect
import json
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter, create_model

from .policies import PolicySet


@dataclass
class User:
    id: str
    tenant: str = "default"
    roles: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "tenant": self.tenant, "roles": list(self.roles)}


@dataclass
class ToolContext:
    user: User
    session_id: str
    services: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]
    fn: Callable[..., Any]
    wants_ctx: bool


def import_ref(ref: str, base_dir: str | Path):
    """Import "module:attr" preferring the kit folder, so two kits with same-named modules don't clash."""
    mod_name, _, attr = ref.partition(":")
    base = str(Path(base_dir).resolve())
    if base not in sys.path:
        sys.path.insert(0, base)
    mod = sys.modules.get(mod_name)
    if mod is not None and not str(getattr(mod, "__file__", "")).startswith(base):
        mod = None
    if mod is None:
        for k in [k for k in sys.modules if k == mod_name or k.startswith(mod_name + ".")]:
            del sys.modules[k]
        mod = importlib.import_module(mod_name)
    return getattr(mod, attr) if attr else mod


def spec_from_function(fn: Callable[..., Any]) -> ToolSpec:
    sig = inspect.signature(fn)
    fields: dict[str, Any] = {}
    wants_ctx = False
    for name, p in sig.parameters.items():
        if name == "ctx":
            wants_ctx = True
            continue
        ann = p.annotation if p.annotation is not inspect.Parameter.empty else str
        fields[name] = (ann, ... if p.default is inspect.Parameter.empty else p.default)
    model = create_model(f"{fn.__name__}_args", **fields)  # type: ignore[call-overload]
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    schema.setdefault("properties", {})
    schema["additionalProperties"] = False
    doc = inspect.getdoc(fn) or fn.__name__
    return ToolSpec(fn.__name__, doc.split("\n\n")[0].strip(), schema, fn, wants_ctx)


def _jsonable(v: Any) -> Any:
    if isinstance(v, BaseModel):
        return v.model_dump(mode="json")
    try:
        json.dumps(v)
        return v
    except TypeError:
        return TypeAdapter(type(v)).dump_python(v, mode="json")


class LimitExceeded(RuntimeError):
    pass


class BoundTool:
    """A tool bound to one run: identity, policies, approvals, limits and event reporting.

    Framework adapters wrap `call` (or `call_sync`) in the framework's own tool type."""

    def __init__(self, spec: ToolSpec, ctx: ToolContext, policies: PolicySet, run: RunState):
        self.spec, self.ctx, self.policies, self.run = spec, ctx, policies, run
        self.name, self.description, self.schema = spec.name, spec.description, spec.schema

    def call_sync(self, args: dict[str, Any] | None) -> dict[str, Any]:
        args = dict(args or {})
        rec = {"id": f"call_{uuid.uuid4().hex[:10]}", "name": self.name, "args": args}
        self.run.tool_calls.append(rec)
        self.run.emit({"type": "tool_call", **rec})
        if len(self.run.tool_calls) > self.run.max_tool_calls:
            out = {"status": "error", "error": "tool call limit reached for this turn"}
            rec["result"] = out
            self.run.emit({"type": "tool_result", "id": rec["id"], "name": self.name, "result": out})
            return out
        from . import telemetry
        with telemetry.span(f"execute_tool {self.name}", {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": self.name,
                                                          "gen_ai.tool.call.id": rec["id"], "session.id": self.ctx.session_id}) as sp:
            out = self._execute(rec, args)
            if sp is not None:
                sp.set_attribute("agent_kit.tool.status", str(out.get("status", "ok")))
        rec["result"] = out
        self.run.emit({"type": "tool_result", "id": rec["id"], "name": self.name, "result": out})
        return out

    def _execute(self, rec: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        d = self.policies.evaluate(self.name, args, self.ctx.user.as_dict())
        if d.action == "deny":
            out = {"status": "denied", "reason": d.message}
        elif d.action == "require_approval":
            ap = self.run.request_approval(self.name, args, d.policy.approver_role if d.policy else "approver", d.message)
            out = {"status": "pending_approval", "approval_id": ap["id"],
                   "message": "This action needs approval from a human. It has been submitted; tell the customer it is pending review."}
        else:
            t0 = time.perf_counter()
            try:
                res = self.spec.fn(**args, ctx=self.ctx) if self.spec.wants_ctx else self.spec.fn(**args)
                out = _jsonable(res)
                if not isinstance(out, dict):
                    out = {"result": out}
            except TypeError as e:
                out = {"status": "error", "error": f"invalid arguments: {e}"}
            except Exception as e:  # noqa: BLE001 - tool errors are reported to the model, not raised
                out = {"status": "error", "error": f"{type(e).__name__}: {e}"}
            rec["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return out

    async def call(self, args: dict[str, Any] | None) -> dict[str, Any]:
        import asyncio
        return await asyncio.to_thread(self.call_sync, args)


class RunState:
    """Per-turn state shared by the bound tools: tool-call log, events and approval requests."""

    def __init__(self, session_id: str, user: User, max_tool_calls: int, emit: Callable[[dict], None] | None,
                 approvals: Any = None):
        self.session_id, self.user, self.max_tool_calls = session_id, user, max_tool_calls
        self.tool_calls: list[dict[str, Any]] = []
        self.approvals_requested: list[dict[str, Any]] = []
        self._emit, self._approvals = emit, approvals

    def emit(self, ev: dict[str, Any]) -> None:
        if self._emit:
            self._emit(ev)

    def request_approval(self, tool: str, args: dict[str, Any], role: str, reason: str) -> dict[str, Any]:
        ap = {"id": f"apr_{uuid.uuid4().hex[:12]}", "session_id": self.session_id, "tool": tool, "args": args,
              "approver_role": role, "reason": reason, "status": "pending", "user": self.user.as_dict(),
              "created_at": time.time()}
        if self._approvals is not None:
            self._approvals.put_approval(ap)
        self.approvals_requested.append(ap)
        self.emit({"type": "approval_required", "approval": {k: ap[k] for k in ("id", "tool", "args", "approver_role", "reason")}})
        return ap


def load_tools(refs: list[str], base_dir: str | Path) -> list[ToolSpec]:
    specs = []
    for ref in refs:
        fn = import_ref(ref, base_dir)
        specs.append(spec_from_function(fn))
    names = [s.name for s in specs]
    if len(names) != len(set(names)):
        raise ValueError(f"tool names must be unique: {names}")
    return specs
