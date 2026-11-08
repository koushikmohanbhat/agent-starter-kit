"""The agent service: the same HTTP API whatever framework runs underneath.

  POST   /v1/chat                 {message, session_id?, stream?}  -> reply, tool calls, pending approvals (SSE if stream)
  GET    /v1/sessions/{id}        transcript (own sessions only)
  DELETE /v1/sessions/{id}        delete a session
  GET    /v1/approvals            pending approvals (approver roles only; own tenant)
  POST   /v1/approvals/{id}       {approve: bool, reason?}  -> runs or drops the held action, tells the customer
  DELETE /v1/users/{user_id}      erase one end user's sessions and approvals (privacy_admin role)
  GET    /v1/agent                definition summary (framework, model, prompt version, tools, policies)
  GET    /healthz, /readyz
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..runtime import AgentRuntime, ApprovalError, RefusedByHook
from ..tools import User
from .auth import authenticate, mode


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    stream: bool = False


class DecisionIn(BaseModel):
    approve: bool
    reason: str = ""


def create_app(kit_dir: str | Path | None = None, runtime: AgentRuntime | None = None) -> FastAPI:
    kit_dir = Path(kit_dir or os.environ.get("KIT_DIR", "."))
    mode()                                   # fail fast on a missing or unsafe auth configuration
    state: dict[str, Any] = {"rt": runtime}

    @asynccontextmanager
    async def lifespan(_app):
        if state["rt"] is None:
            state["rt"] = AgentRuntime.from_path(kit_dir)
        yield

    app = FastAPI(title="agent-starter-kit", version=__version__, lifespan=lifespan)

    def rt() -> AgentRuntime:
        return state["rt"]

    @app.exception_handler(HTTPException)
    async def _http(_req, exc: HTTPException):
        return JSONResponse({"error": {"status": exc.status_code, "message": exc.detail}}, status_code=exc.status_code)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    def readyz():
        r = rt()
        try:
            r.store.get_session("readyz-probe")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(503, f"session store unavailable: {type(e).__name__}") from None
        return {"status": "ready", "framework": r.framework, "model": r.model.name, "provider": r.model.provider}

    @app.get("/v1/agent")
    def agent(user: User = Depends(authenticate)):
        r = rt()
        return {"name": r.definition.name, "description": r.definition.description, "framework": r.framework,
                "model": {"provider": r.model.provider, "name": r.model.name},
                "prompt": {"id": r.instructions.id, "version": r.instructions.version, "hash": r.instructions.hash},
                "tools": [{"name": t.name, "description": t.description} for t in r.tool_specs],
                "policies": [p.model_dump() for p in r.definition.policies], "limits": r.definition.limits.model_dump()}

    @app.post("/v1/chat")
    async def chat(body: ChatIn, user: User = Depends(authenticate)):
        r = rt()
        if not body.stream:
            try:
                res = await r.chat(body.message, user, body.session_id)
            except RefusedByHook as e:
                raise HTTPException(403, str(e)) from None
            return res.as_dict()
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit(ev: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(q.put_nowait, ev)

        async def worker():
            try:
                await r.chat(body.message, user, body.session_id, emit=emit)
            except Exception as e:  # noqa: BLE001
                emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                emit({"type": "_end"})

        task = asyncio.create_task(worker())

        async def gen():
            while True:
                ev = await q.get()
                if ev["type"] == "_end":
                    break
                yield f"event: {ev['type']}\ndata: {json.dumps(ev, default=str)}\n\n"
            await task
        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    def _own(sid: str, user: User) -> dict[str, Any]:
        s = rt().store.get_session(sid)
        if not s or s["user_id"] != user.id or s["tenant"] != user.tenant:
            raise HTTPException(404, "session not found")
        return s

    @app.get("/v1/sessions/{sid}")
    def get_session(sid: str, user: User = Depends(authenticate)):
        s = _own(sid, user)
        return {"id": s["id"], "messages": [{k: m.get(k) for k in ("role", "content", "ts", "approval")} for m in s["messages"]],
                "created_at": s["created_at"], "updated_at": s["updated_at"]}

    @app.delete("/v1/sessions/{sid}")
    def delete_session(sid: str, user: User = Depends(authenticate)):
        _own(sid, user)
        rt().store.delete_session(sid)
        return {"deleted": sid}

    def _approver_roles() -> set[str]:
        return {p.approver_role for p in rt().definition.policies}

    @app.get("/v1/approvals")
    def approvals(status: str = "pending", user: User = Depends(authenticate)):
        if not (_approver_roles() & set(user.roles)):
            raise HTTPException(403, "an approver role is required")
        return {"approvals": [a for a in rt().store.list_approvals(status, user.tenant) if a["approver_role"] in user.roles]}

    @app.post("/v1/approvals/{aid}")
    async def decide(aid: str, body: DecisionIn, user: User = Depends(authenticate)):
        try:
            return await rt().decide(aid, body.approve, user, body.reason)
        except KeyError:
            raise HTTPException(404, "approval not found") from None
        except PermissionError as e:
            raise HTTPException(403, str(e)) from None
        except ApprovalError as e:
            raise HTTPException(409, str(e)) from None

    @app.delete("/v1/users/{user_id}")
    def erase_user(user_id: str, user: User = Depends(authenticate)):
        if "privacy_admin" not in user.roles:
            raise HTTPException(403, "the privacy_admin role is required")
        n = rt().erase_user(user_id, user.tenant)
        return {"user_id": user_id, "tenant": user.tenant, "deleted_records": n, "at": time.time()}

    if os.environ.get("KIT_AUTH", "").lower() == "dev":
        from .devpage import PAGE

        @app.get("/", response_class=HTMLResponse)
        def dev_page():
            return PAGE

    return app
