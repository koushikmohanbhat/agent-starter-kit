"""Optional add-ons: `kit add evals` (GenAI Eval Framework suite for this agent) and `kit add dpdp` (DPDP hooks).

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


def add(addon: str, kit_dir: Path) -> int:
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
