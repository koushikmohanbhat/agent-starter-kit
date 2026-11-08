"""Optional add-ons: `kit add evals` (GenAI Eval Framework suite for this agent), `kit add dpdp` (DPDP hooks) and
`kit add connectors` (tools from the connector hub, agent-connector-hub, over MCP).

Both only add files and configuration to the project; the kit itself never imports them."""
from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path


def _files(name: str) -> Path:
    installed = Path(str(resources.files("agent_kit"))) / "addon_files" / name
    return installed if installed.is_dir() else Path(__file__).resolve().parents[2] / "addon_files" / name


HOOKS = """
hooks:                                                  # added by `kit add dpdp`
  inbound: dpdp_hooks:inbound
  on_session_saved: dpdp_hooks:on_session_saved
  redact: dpdp_hooks:redact
  on_user_erased: dpdp_hooks:on_user_erased
"""


CONNECTORS = """
mcp_tools:                                              # added by `kit add connectors`
  - url: "${CONNECTOR_HUB_URL:-http://127.0.0.1:8000}/mcp/${CONNECTOR_HUB_PROFILE:-support-agent}"
    headers_env: {X-API-Key: CONNECTOR_HUB_API_KEY}
    forward_user: true
    prefix: "${CONNECTOR_HUB_PREFIX:-}"
"""
CONNECTORS_ENV = """
# Connector hub (kit add connectors): governed enterprise tools over MCP. The hub runs with HUB_AUTH=api_key.
CONNECTOR_HUB_URL=http://127.0.0.1:8000
CONNECTOR_HUB_PROFILE=support-agent
CONNECTOR_HUB_API_KEY=
"""


def add(addon: str, kit_dir: Path) -> int:
    if addon == "connectors":
        y = kit_dir / "agent.yaml"
        text = y.read_text(encoding="utf-8")
        if "\nmcp_tools:" not in text:
            y.write_text(text.rstrip() + "\n" + CONNECTORS, encoding="utf-8")
        env = kit_dir / ".env.example"
        if env.is_file() and "CONNECTOR_HUB_URL" not in env.read_text(encoding="utf-8"):
            env.write_text(env.read_text(encoding="utf-8").rstrip() + "\n" + CONNECTORS_ENV, encoding="utf-8")
        print("added mcp_tools: to agent.yaml\n\nnext:\n  pip install 'agent-starter-kit[connectors]'\n"
              "  run the hub (pip install agent-connector-hub; HUB_AUTH=api_key HUB_API_KEYS=... hub serve)\n"
              "  set CONNECTOR_HUB_URL, CONNECTOR_HUB_PROFILE and CONNECTOR_HUB_API_KEY, then kit dev")
        return 0
    src = _files(addon)
    if addon == "evals":
        dst = kit_dir / "evals"
        if dst.exists():
            print(f"{dst} already exists; leaving it as is")
            return 0
        shutil.copytree(src, dst)
        print(f"added {dst}\n\nnext:\n  pip install 'agent-starter-kit[evals]'\n  see {dst / 'README.md'} (start the service in test mode, then genai-evals run)")
        return 0
    if addon == "dpdp":
        for f in src.iterdir():
            target = kit_dir / f.name if f.suffix == ".py" else kit_dir / f"DPDP-{f.name}"
            if not target.exists():
                shutil.copy2(f, target)
        y = kit_dir / "agent.yaml"
        text = y.read_text(encoding="utf-8")
        if "\nhooks:" not in text:
            y.write_text(text.rstrip() + "\n" + HOOKS, encoding="utf-8")
        print("added dpdp_hooks.py and a hooks: block in agent.yaml\n\nnext: install the DPDP Data Rights Framework, set DPDP_CONFIG and "
              "DPDP_PURPOSE, and read DPDP-README.md")
        return 0
    raise ValueError(addon)
