"""agent.yaml: the framework-neutral agent definition. Values may use ${VAR} / ${VAR:-default} from the environment
(and a .env file), so the definition can be committed without any environment-specific settings."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
FRAMEWORKS = ("openai_agents", "langgraph", "adk", "strands")
PROVIDERS = ("openai", "openai_compatible", "anthropic", "bedrock", "gemini", "scripted")
_SECRETISH = re.compile(r"(api_?key|secret|password|token)$", re.I)


class ConfigError(ValueError):
    pass


class MissingEnvError(ConfigError):
    pass


def load_env_file(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines into os.environ (real environment variables win)."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def interpolate_env(obj: Any, where: str = "") -> Any:
    if isinstance(obj, str):
        def rep(m: re.Match) -> str:
            name, default = m.group(1), m.group(2)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise MissingEnvError(f"{where or 'config'}: environment variable {name} is not set (and has no default)")
        return _ENV_REF.sub(rep, obj)
    if isinstance(obj, dict):
        return {k: interpolate_env(v, f"{where}.{k}" if where else str(k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [interpolate_env(v, f"{where}[{i}]") for i, v in enumerate(obj)]
    return obj


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    provider: Literal[PROVIDERS] = "openai"  # type: ignore[valid-type]
    name: str = ""
    base_url: str | None = None          # openai_compatible / scripted
    api_key_env: str | None = None       # env var holding the key (never the key itself)
    region: str | None = None            # bedrock
    project: str | None = None           # gemini on Google Cloud (Agent Platform / Vertex)
    location: str | None = None
    script: str | None = None            # scripted: "module:respond" in the kit folder (offline model)
    settings: dict[str, Any] = Field(default_factory=dict)   # temperature, max_tokens, ...

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None


class PolicySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    require_approval_if: str | None = None
    deny_if: str | None = None
    message: str | None = None
    approver_role: str = "approver"


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_turns: int = 12
    max_tool_calls: int = 8
    timeout_s: float = 60.0


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str = ""
    framework: Literal[FRAMEWORKS] = "openai_agents"  # type: ignore[valid-type]
    model: ModelConfig = Field(default_factory=ModelConfig)
    instructions: dict[str, Any]          # {prompt: id, stage: prod} or {text: "..."}
    prompts_dir: str = "prompts"
    tools: list[str]                      # "module:function", relative to the kit folder
    policies: list[PolicySpec] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)
    session: dict[str, Any] = Field(default_factory=dict)
    escalation: dict[str, Any] = Field(default_factory=dict)
    services: dict[str, str] = Field(default_factory=dict)   # name -> "module:factory" (e.g. the order API client)
    test_state: str | None = None         # "module:fn(tool_calls) -> dict": outcome of a turn, returned only in test mode
    hooks: dict[str, str] = Field(default_factory=dict)      # inbound / on_session_saved / redact / on_user_erased (add-ons)
    base_dir: str = "."

    @field_validator("tools")
    @classmethod
    def _tools(cls, v):
        if not v:
            raise ValueError("an agent needs at least one tool")
        return v

    def path(self, p: str) -> Path:
        pp = Path(p)
        return pp if pp.is_absolute() else Path(self.base_dir) / pp


def _reject_inline_secrets(data: Any, where: str = "") -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            if _SECRETISH.search(str(k)) and isinstance(v, str) and v and not k.endswith("_env"):
                raise ConfigError(f"{where}{k}: secrets must not be written in agent.yaml; use {k}_env: <ENV_VAR> instead")
            _reject_inline_secrets(v, f"{where}{k}.")
    elif isinstance(data, list):
        for i, v in enumerate(data):
            _reject_inline_secrets(v, f"{where}[{i}].")


def load_agent(path: str | Path, overrides: dict[str, Any] | None = None) -> AgentDefinition:
    p = Path(path)
    if p.is_dir():
        p = p / "agent.yaml"
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    _reject_inline_secrets(raw)
    data = interpolate_env(raw, p.name)
    for k, v in (overrides or {}).items():
        cur = data
        parts = k.split(".")
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = v
    data.setdefault("base_dir", str(p.parent))
    return AgentDefinition(**data)
