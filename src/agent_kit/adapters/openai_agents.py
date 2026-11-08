"""OpenAI Agents SDK adapter: Agent + FunctionTool + Runner (the SDK's own loop, guardrails and tracing).

Models: OpenAI through the Responses API; OpenAI-compatible endpoints (gateways, the offline scripted model) through
Chat Completions; Anthropic, Bedrock and Gemini through the SDK's LiteLLM model (`[openai,litellm]`)."""
from __future__ import annotations

import json
import os

from .base import AdapterResult, FrameworkAdapter, MissingDependency, litellm_name


class Adapter(FrameworkAdapter):
    name, extra = "openai_agents", "openai"

    def _model(self):
        from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel
        from openai import AsyncOpenAI
        m = self.model
        if m.provider == "openai" and not m.base_url:
            return OpenAIResponsesModel(model=m.name, openai_client=AsyncOpenAI(api_key=m.api_key))
        if m.openai_like:
            return OpenAIChatCompletionsModel(model=m.name, openai_client=AsyncOpenAI(base_url=m.base_url, api_key=m.api_key or "none"))
        try:
            from agents.extensions.models.litellm_model import LitellmModel
        except ImportError as e:  # pragma: no cover - optional extra
            raise MissingDependency("openai_agents", "openai,litellm", e) from e
        return LitellmModel(model=litellm_name(m), api_key=m.api_key)

    async def run(self, instructions, tools, history, message):
        try:
            from agents import Agent, FunctionTool, ModelSettings, RunConfig, Runner, set_tracing_disabled
        except ImportError as e:  # pragma: no cover
            raise MissingDependency("openai_agents", self.extra, e) from e
        if not os.environ.get("OPENAI_API_KEY") or self.model.provider != "openai":
            set_tracing_disabled(True)      # the kit emits its own OTel spans; SDK tracing needs an OpenAI key

        def wrap(t):
            async def on_invoke(_ctx, args_json: str) -> str:
                return json.dumps(await t.call(json.loads(args_json or "{}")))
            return FunctionTool(name=t.name, description=t.description, params_json_schema=t.schema,
                                on_invoke_tool=on_invoke, strict_json_schema=False)

        st = self.model.settings
        agent = Agent(name=self.definition.name, instructions=instructions, tools=[wrap(t) for t in tools], model=self._model(),
                      model_settings=ModelSettings(temperature=st.get("temperature"), max_tokens=st.get("max_tokens")))
        items = [{"role": h["role"], "content": h["content"]} for h in history] + [{"role": "user", "content": message}]
        res = await Runner.run(agent, input=items, max_turns=self.definition.limits.max_turns,
                               run_config=RunConfig(workflow_name=self.definition.name))
        u = res.context_wrapper.usage
        return AdapterResult(str(res.final_output or ""), {"input_tokens": u.input_tokens or 0, "output_tokens": u.output_tokens or 0},
                             self.model.name, res)
