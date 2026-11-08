"""Parity suite: run the same conversations on every framework adapter and check they agree.

For each conversation and adapter: the sequence of tool calls, the final state of the kit's services (e.g. refunds
issued), the approvals requested and a phrase in the final reply must match the expectation in parity.yaml. An
optional `then_approve` step approves the pending request and checks the state again. Each conversation starts from
fresh services, so results don't leak between runs."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .runtime import AgentRuntime
from .tools import User


@dataclass
class ParityResult:
    framework: str
    conversation: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    reply: str = ""


ADAPTER_MODULES = {"openai_agents": "agents", "langgraph": "langgraph", "adk": "google.adk", "strands": "strands"}


def available_frameworks() -> list[str]:
    """Adapters whose framework is installed (checks the full module, e.g. google.adk, not just a namespace)."""
    import importlib.util
    out = []
    for fw, mod in ADAPTER_MODULES.items():
        try:
            if importlib.util.find_spec(mod) is not None:
                out.append(fw)
        except (ImportError, ValueError):
            pass
    return out


def _state_of(services: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for svc in services.values():
        if hasattr(svc, "state"):
            out.update(svc.state())
    return out


def _check_state(want: dict[str, Any], got: dict[str, Any]) -> list[str]:
    return [f"state.{k}: expected {v!r}, got {got.get(k)!r}" for k, v in (want or {}).items() if got.get(k) != v]


async def run_conversation(kit_dir: Path, framework: str, conv: dict[str, Any], user: User) -> ParityResult:
    rt = AgentRuntime.from_path(kit_dir, framework=framework, overrides={"session.store": "memory://", "model.provider": "scripted"})
    exp = conv.get("expect", {})
    sid, tools, pending, reply = None, [], [], ""
    for msg in conv["turns"]:
        r = await rt.chat(msg, user, sid)
        sid, reply = r.session_id, r.message
        tools += [c["name"] for c in r.tool_calls]
        pending += r.pending_approvals
    st = _state_of(rt.services)
    probs = []
    if tools != exp.get("tools", tools):
        probs.append(f"tools: expected {exp['tools']}, got {tools}")
    probs += _check_state(exp.get("state"), st)
    if "approvals" in exp and len(pending) != exp["approvals"]:
        probs.append(f"approvals: expected {exp['approvals']}, got {len(pending)}")
    if exp.get("says") and exp["says"].lower() not in reply.lower():
        probs.append(f"reply should mention {exp['says']!r}: {reply[:120]!r}")
    if conv.get("then_approve") and pending:
        ta = conv["then_approve"]
        a = ta.get("approver", {})
        res = await rt.decide(pending[0]["id"], True, User(a.get("id", "approver"), user.tenant, a.get("roles", [])))
        st = _state_of(rt.services)
        probs += _check_state(ta.get("state"), st)
        if ta.get("says") and ta["says"].lower() not in res["message"].lower():
            probs.append(f"approval message should mention {ta['says']!r}: {res['message'][:120]!r}")
    return ParityResult(framework, conv["id"], not probs, probs, tools, st, reply)


async def run_parity(kit_dir: str | Path, frameworks: list[str] | None = None, only: list[str] | None = None) -> list[ParityResult]:
    kit_dir = Path(kit_dir)
    spec = yaml.safe_load((kit_dir / "parity.yaml").read_text(encoding="utf-8"))
    u = spec.get("user", {})
    user = User(u.get("id", "user"), u.get("tenant", "default"), u.get("roles", []))
    out = []
    for fw in frameworks or available_frameworks():
        for conv in spec["conversations"]:
            if only and conv["id"] not in only:
                continue
            try:
                out.append(await run_conversation(kit_dir, fw, conv, user))
            except Exception as e:  # noqa: BLE001 - a broken adapter is a parity failure, not a crash
                out.append(ParityResult(fw, conv["id"], False, [f"{type(e).__name__}: {e}"]))
    return out


def cross_check(results: list[ParityResult]) -> list[str]:
    """Adapters must also agree with each other (tool sequence and state), not just with the expectation."""
    probs = []
    by_conv: dict[str, list[ParityResult]] = {}
    for r in results:
        by_conv.setdefault(r.conversation, []).append(r)
    for conv, rs in by_conv.items():
        sigs = {(tuple(r.tools), tuple(sorted((k, str(v)) for k, v in r.state.items()))) for r in rs if not r.problems or r.tools}
        if len(sigs) > 1:
            probs.append(f"{conv}: adapters disagree: " + "; ".join(f"{r.framework}={r.tools}" for r in rs))
    return probs


def matrix(results: list[ParityResult]) -> str:
    fws = list(dict.fromkeys(r.framework for r in results))
    convs = list(dict.fromkeys(r.conversation for r in results))
    by = {(r.framework, r.conversation): r for r in results}
    lines = ["| conversation | " + " | ".join(fws) + " |", "|---|" + "---|" * len(fws)]
    for c in convs:
        lines.append(f"| {c} | " + " | ".join("✓" if by[(f, c)].passed else "✗" for f in fws) + " |")
    return "\n".join(lines)


def run_sync(*a, **kw) -> list[ParityResult]:
    return asyncio.run(run_parity(*a, **kw))
