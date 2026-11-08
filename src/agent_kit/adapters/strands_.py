"""Strands Agents adapter: Agent + PythonAgentTool (neutral JSON-schema tools) with the agent's own event loop.

Models: Bedrock natively (BedrockModel); OpenAI and OpenAI-compatible endpoints (incl. the offline scripted model)
through OpenAIModel (`[strands]` installs strands-agents[openai]); Anthropic through AnthropicModel; Gemini through
LiteLLMModel when installed."""
from __future__ import annotations

import json

from .base import AdapterError, AdapterResult, FrameworkAdapter, MissingDependency, litellm_name


class Adapter(FrameworkAdapter):
    name, extra = "strands", "strands"

    def _model(self):
        m, st = self.model, self.model.settings
        params = {k: st[k] for k in ("temperature", "max_tokens") if k in st}
        try:
            if m.openai_like:
                from strands.models.openai import OpenAIModel
                ca = {"api_key": m.api_key or "none", **({"base_url": m.base_url} if m.base_url else {})}
                return OpenAIModel(client_args=ca, model_id=m.name, params=params)
            if m.provider == "bedrock":
                from strands.models import BedrockModel
                return BedrockModel(model_id=m.name, region_name=m.region, **params)
            if m.provider == "anthropic":
                from strands.models.anthropic import AnthropicModel
                return AnthropicModel(client_args={"api_key": m.api_key}, model_id=m.name, max_tokens=st.get("max_tokens", 1024),
                                      params={k: v for k, v in params.items() if k != "max_tokens"})
            if m.provider == "gemini":
                from strands.models.litellm import LiteLLMModel
                return LiteLLMModel(model_id=litellm_name(m), params=params)
        except ImportError as e:
            raise MissingDependency("strands", f"strands,{m.provider}", e) from e
        raise AdapterError(f"strands adapter: unsupported provider {m.provider}")

    async def run(self, instructions, tools, history, message):
        try:
            from strands import Agent
            from strands.tools.tools import PythonAgentTool
        except ImportError as e:  # pragma: no cover
            raise MissingDependency("strands", self.extra, e) from e

        def wrap(t):
            spec = {"name": t.name, "description": t.description, "inputSchema": {"json": t.schema}}

            def fn(tool_use, **_):
                out = t.call_sync(tool_use.get("input") or {})
                return {"toolUseId": tool_use["toolUseId"], "status": "success", "content": [{"text": json.dumps(out)}]}
            return PythonAgentTool(t.name, spec, fn)

        msgs = [{"role": h["role"], "content": [{"text": h["content"]}]} for h in history]
        agent = Agent(model=self._model(), tools=[wrap(t) for t in tools], system_prompt=instructions, messages=msgs,
                      callback_handler=None, name=self.definition.name)
        res = await agent.invoke_async(message)
        text = "".join(c.get("text", "") for c in (res.message or {}).get("content", []) if isinstance(c, dict))
        u = getattr(getattr(res, "metrics", None), "accumulated_usage", {}) or {}
        return AdapterResult(text or str(res), {"input_tokens": u.get("inputTokens", 0), "output_tokens": u.get("outputTokens", 0)},
                             self.model.name, res)
