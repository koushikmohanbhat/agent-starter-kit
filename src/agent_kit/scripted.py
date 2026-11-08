"""An offline, deterministic model behind an OpenAI-compatible Chat Completions endpoint.

Every framework adapter can talk to an OpenAI-compatible endpoint, so one scripted model gives every framework the
same offline behaviour through its *real* model path (HTTP, tool-call parsing, streaming). That is what makes the
parity suite meaningful, and lets the kit run, demo and pass CI with no API keys.

A script is a function `respond(messages, tools) -> {"content": str} | {"tool_calls": [{"name": ..., "arguments": {...}}]}`
that sees the conversation in Chat Completions format. Kits ship their own (e.g. kits/support-agent/scripted_model.py).
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

Script = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return "" if content is None else str(content)


def normalise(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        n = {"role": m.get("role"), "content": text_of(m.get("content"))}
        if m.get("tool_calls"):
            n["tool_calls"] = [{"id": t.get("id"), "name": t["function"]["name"],
                                "arguments": json.loads(t["function"].get("arguments") or "{}")} for t in m["tool_calls"]]
        if m.get("tool_call_id"):
            n["tool_call_id"] = m["tool_call_id"]
        out.append(n)
    return out


def _tokens(s: str) -> int:
    return max(1, len(s) // 4)


def build_app(script: Script):
    app = FastAPI(title="agent-kit scripted model")
    calls: list[dict[str, Any]] = []
    app.state.calls = calls

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": [{"id": "scripted", "object": "model", "owned_by": "agent-kit"}]}

    @app.post("/v1/chat/completions")
    async def chat(req: Request):
        body = await req.json()
        msgs = normalise(body.get("messages", []))
        tools = [t.get("function", t) for t in body.get("tools") or []]
        out = script(msgs, tools)
        calls.append({"messages": msgs, "tools": [t.get("name") for t in tools], "out": out})
        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        model = body.get("model", "scripted")
        prompt_t = _tokens(json.dumps(body.get("messages", [])))
        tcs = [{"id": f"call_{uuid.uuid4().hex[:10]}", "type": "function",
                "function": {"name": t["name"], "arguments": json.dumps(t.get("arguments", {}))}} for t in out.get("tool_calls", [])]
        content = out.get("content") if not tcs else (out.get("content") or None)
        compl_t = _tokens((content or "") + json.dumps([t["function"] for t in tcs]))
        usage = {"prompt_tokens": prompt_t, "completion_tokens": compl_t, "total_tokens": prompt_t + compl_t}
        finish = "tool_calls" if tcs else "stop"
        if not body.get("stream"):
            msg: dict[str, Any] = {"role": "assistant", "content": content}
            if tcs:
                msg["tool_calls"] = tcs
            return JSONResponse({"id": cid, "object": "chat.completion", "created": int(time.time()), "model": model,
                                 "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": usage})

        def chunk(delta: dict[str, Any], fr: str | None = None, extra: dict | None = None) -> str:
            d = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                 "choices": [{"index": 0, "delta": delta, "finish_reason": fr}], **(extra or {})}
            return f"data: {json.dumps(d)}\n\n"

        def gen():
            yield chunk({"role": "assistant", "content": ""})
            if content:
                for i in range(0, len(content), 40):
                    yield chunk({"content": content[i:i + 40]})
            for i, t in enumerate(tcs):
                yield chunk({"tool_calls": [{"index": i, "id": t["id"], "type": "function",
                                             "function": {"name": t["function"]["name"], "arguments": t["function"]["arguments"]}}]})
            yield chunk({}, finish)
            if (body.get("stream_options") or {}).get("include_usage"):
                yield f"data: {json.dumps({'id': cid, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [], 'usage': usage})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


class ScriptedServer:
    """Runs the scripted model on 127.0.0.1:<free port> in a background thread."""

    def __init__(self, script: Script, port: int | None = None):
        import uvicorn
        self.app = build_app(script)
        self.port = port or _free_port()
        self.server = uvicorn.Server(uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.app.state.calls

    def start(self) -> ScriptedServer:
        self.thread.start()
        for _ in range(200):
            if self.server.started:
                return self
            time.sleep(0.02)
        raise RuntimeError("scripted model server did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_servers: dict[str, ScriptedServer] = {}
_lock = threading.Lock()


def ensure_server(script_ref: str, base_dir: str) -> ScriptedServer:
    """One shared scripted server per script in this process."""
    from .tools import import_ref
    key = f"{base_dir}:{script_ref}"
    with _lock:
        if key not in _servers:
            _servers[key] = ScriptedServer(import_ref(script_ref, base_dir)).start()
        return _servers[key]
