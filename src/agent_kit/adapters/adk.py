"""Google ADK adapter: LlmAgent + a neutral BaseTool + Runner over an in-memory ADK session rebuilt from the kit's
session for each turn (the kit's store stays the source of truth).

Models: Gemini natively (on the Gemini Enterprise Agent Platform / Vertex AI, or the Gemini API); everything else,
including the offline scripted model, through ADK's LiteLLM model (`[adk]` installs litellm)."""
from __future__ import annotations

import uuid

from .base import AdapterResult, FrameworkAdapter, MissingDependency, litellm_name


class Adapter(FrameworkAdapter):
    name, extra = "adk", "adk"

    def _model(self):
        m = self.model
        if m.provider == "gemini":
            return m.name
        from google.adk.models.lite_llm import LiteLlm
        kw = {"api_base": m.base_url} if m.base_url else {}
        return LiteLlm(model=litellm_name(m), api_key=m.api_key or ("none" if m.base_url else None), **kw)

    async def run(self, instructions, tools, history, message):
        try:
            from google.adk.agents import LlmAgent
            from google.adk.events import Event
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.adk.tools import BaseTool
            from google.genai import types
        except ImportError as e:  # pragma: no cover
            raise MissingDependency("adk", self.extra, e) from e

        class NeutralTool(BaseTool):
            def __init__(self, t):
                super().__init__(name=t.name, description=t.description)
                self._t = t

            def _get_declaration(self):
                return types.FunctionDeclaration(name=self._t.name, description=self._t.description,
                                                 parameters_json_schema=self._t.schema)

            async def run_async(self, *, args, tool_context):
                return await self._t.call(dict(args or {}))

        st = self.model.settings
        gen = types.GenerateContentConfig(**{k: st[k] for k in ("temperature",) if k in st}, max_output_tokens=st.get("max_tokens"))
        agent = LlmAgent(name=self.definition.name.replace("-", "_"), instruction=instructions, model=self._model(),
                         tools=[NeutralTool(t) for t in tools], generate_content_config=gen)
        svc = InMemorySessionService()
        app, uid, sid = "agent_kit", "user", uuid.uuid4().hex
        session = await svc.create_session(app_name=app, user_id=uid, session_id=sid)
        for h in history:
            author, role = ("user", "user") if h["role"] == "user" else (agent.name, "model")
            await svc.append_event(session, Event(author=author, invocation_id=uuid.uuid4().hex,
                                                  content=types.Content(role=role, parts=[types.Part(text=h["content"])])))
        runner = Runner(agent=agent, app_name=app, session_service=svc)
        text, usage = "", {"input_tokens": 0, "output_tokens": 0}
        async for ev in runner.run_async(user_id=uid, session_id=sid,
                                         new_message=types.Content(role="user", parts=[types.Part(text=message)])):
            um = getattr(ev, "usage_metadata", None)
            if um is not None:
                usage["input_tokens"] += getattr(um, "prompt_token_count", 0) or 0
                usage["output_tokens"] += getattr(um, "candidates_token_count", 0) or 0
            if ev.is_final_response() and ev.content and ev.content.parts:
                text = "".join(p.text or "" for p in ev.content.parts if getattr(p, "text", None))
        return AdapterResult(text, usage, self.model.name)
