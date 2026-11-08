"""The framework adapter contract.

An adapter builds the framework's native agent from the neutral definition and runs one turn:

    result = await adapter.run(instructions, tools, history, message)

- `tools` are `BoundTool`s (identity, policies, approvals and limits already applied); the adapter wraps them in the
  framework's tool type and must not call tool functions any other way.
- `history` is the session so far as plain {"role": "user"|"assistant", "content": str} turns.
- The adapter returns the final text and usage. Tool calls and approval events are reported by the tools themselves,
  so they are identical on every framework.

Adapters use the framework's own loop, tool calling and model clients. Nothing here re-implements an agent loop.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..config import AgentDefinition, ModelConfig
from ..tools import BoundTool


class AdapterError(RuntimeError):
    pass


class MissingDependency(AdapterError):
    def __init__(self, framework: str, extra: str, err: Exception):
        super().__init__(f"the {framework} adapter needs `pip install agent-starter-kit[{extra}]` ({err})")


@dataclass
class AdapterResult:
    text: str
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    model: str = ""
    raw: Any = None


@dataclass
class ResolvedModel:
    """A model reference every adapter can turn into its own model object."""
    provider: str            # openai | openai_compatible | anthropic | bedrock | gemini
    name: str
    base_url: str | None = None
    api_key: str | None = None
    region: str | None = None
    project: str | None = None
    location: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def openai_like(self) -> bool:
        return self.provider in ("openai", "openai_compatible")


def resolve_model(m: ModelConfig, base_dir: str) -> ResolvedModel:
    if m.provider == "scripted":
        from ..scripted import ensure_server
        if not m.script:
            raise AdapterError("model.provider: scripted needs model.script (module:function in the kit folder)")
        srv = ensure_server(m.script, base_dir)
        return ResolvedModel("openai_compatible", m.name or "scripted", srv.base_url, "offline", settings=m.settings)
    if not m.name:
        raise AdapterError(f"model.name is required for provider {m.provider} (set MODEL_NAME)")
    key = m.api_key()
    if m.provider == "openai":
        key = key or os.environ.get("OPENAI_API_KEY")
    if m.provider == "anthropic":
        key = key or os.environ.get("ANTHROPIC_API_KEY")
    return ResolvedModel(m.provider, m.name, m.base_url, key, m.region or os.environ.get("AWS_REGION"),
                         m.project or os.environ.get("GOOGLE_CLOUD_PROJECT"), m.location or os.environ.get("GOOGLE_CLOUD_LOCATION"),
                         m.settings)


def litellm_name(m: ResolvedModel) -> str:
    """Model id in LiteLLM form, for adapters that reach non-native providers through LiteLLM."""
    return {"openai": f"openai/{m.name}", "openai_compatible": f"openai/{m.name}", "anthropic": f"anthropic/{m.name}",
            "bedrock": f"bedrock/{m.name}", "gemini": f"vertex_ai/{m.name}"}[m.provider]


class FrameworkAdapter:
    name = "base"
    extra = ""

    def __init__(self, definition: AgentDefinition, model: ResolvedModel):
        self.definition, self.model = definition, model

    async def run(self, instructions: str, tools: list[BoundTool], history: list[dict[str, str]], message: str) -> AdapterResult:
        raise NotImplementedError


def get_adapter(name: str, definition: AgentDefinition, model: ResolvedModel) -> FrameworkAdapter:
    import importlib
    mods = {"openai_agents": "openai_agents", "langgraph": "langgraph_", "adk": "adk", "strands": "strands_"}
    if name not in mods:
        raise AdapterError(f"unknown framework {name!r} (expected one of {', '.join(mods)})")
    mod = importlib.import_module(f"agent_kit.adapters.{mods[name]}")
    return mod.Adapter(definition, model)
