"""kit: the agent starter kit CLI.

  kit init <dir> [--kit support-agent]       copy a kit into a new project (offline-ready)
  kit check [dir]                            validate agent.yaml, tools, policies, prompt and model settings
  kit run "message" [--user ID] [dir]        one turn from the terminal
  kit dev [dir] [--port 8080]                local service + dev chat page (KIT_AUTH=dev)
  kit serve [dir]                            production service (needs KIT_AUTH=oidc|api_key)
  kit test --parity [dir]                    run the parity conversations on every framework adapter
  kit prompts lock | promote <id> <ver> --stage prod
  kit add evals | dpdp [dir]                 optional add-ons (4.1 eval pack, 5.5 DPDP hooks)
  kit deploy --print aws-ecs|cloud-run|agentcore|agent-runtime   print the deploy steps (never deploys silently)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from .config import FRAMEWORKS, ConfigError, load_env_file


def kits_root() -> Path:
    installed = Path(str(resources.files("agent_kit"))) / "kits"
    if installed.is_dir():
        return installed
    return Path(__file__).resolve().parents[2] / "kits"


def _kit_dir(d: str | None) -> Path:
    p = Path(d or os.environ.get("KIT_DIR", "."))
    if not (p / "agent.yaml").exists():
        raise SystemExit(f"error: no agent.yaml in {p.resolve()} (run `kit init <dir>` first, or pass the kit folder)")
    return p


def cmd_init(a) -> int:
    src = kits_root() / a.kit
    if not src.is_dir():
        print(f"error: unknown kit {a.kit!r} (available: {', '.join(sorted(p.name for p in kits_root().iterdir() if p.is_dir()))})", file=sys.stderr)
        return 2
    dst = Path(a.directory)
    if dst.exists() and any(dst.iterdir()) and not a.force:
        print(f"error: {dst} is not empty (use --force)", file=sys.stderr)
        return 2
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".kit", "*.pyc"))
    common = kits_root().parent / "templates" if (kits_root().parent / "templates").is_dir() else None
    for name, target in (("env.example", ".env.example"), ("gitignore", ".gitignore")):
        f = (common / name) if common else None
        if f and f.exists() and not (dst / target).exists():
            shutil.copy2(f, dst / target)
    print(f"created {dst} from kit {a.kit}\n\nnext:\n  cd {dst}\n  kit test --parity      # offline, all four frameworks\n  kit dev                # http://127.0.0.1:8080\n"
          "  then see README.md: connect a model (MODEL_PROVIDER) and your order system (ORDER_API_URL)")
    return 0


def cmd_check(a) -> int:
    from .runtime import AgentRuntime
    d = _kit_dir(a.directory)
    try:
        rt = AgentRuntime.from_path(d, framework=a.framework)
    except Exception as e:  # noqa: BLE001
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"ok: {rt.definition.name} · framework {rt.framework} · model {rt.model.provider} {rt.model.name}"
          f" · prompt {rt.instructions.id}@{rt.instructions.version} · {len(rt.tool_specs)} tools · {len(rt.definition.policies)} policies")
    return 0


def cmd_run(a) -> int:
    from .runtime import AgentRuntime
    from .tools import User
    rt = AgentRuntime.from_path(_kit_dir(a.directory), framework=a.framework, overrides={"session.store": "memory://"})

    def emit(ev):
        if ev["type"] == "tool_call":
            print(f"  → {ev['name']} {json.dumps(ev['args'])}")
        elif ev["type"] == "tool_result":
            print(f"  ← {json.dumps(ev['result'])[:200]}")
        elif ev["type"] == "approval_required":
            print(f"  ⏸ approval required ({ev['approval']['approver_role']}): {ev['approval']['reason']}")
    r = asyncio.run(rt.chat(a.message, User(a.user, a.tenant, a.roles.split(",") if a.roles else []), emit=emit))
    print(f"\n{r.message}\n\n[{r.framework} · {r.model} · {r.usage} · {r.latency_ms:.0f} ms]")
    return 0


def _serve(a, dev: bool) -> int:
    import uvicorn
    d = _kit_dir(a.directory)
    if dev:
        os.environ.setdefault("KIT_AUTH", "dev")
        os.environ.setdefault("KIT_ENV", "dev")
    if a.framework:
        os.environ["AGENT_FRAMEWORK"] = a.framework
    from .service import create_app
    try:
        app = create_app(d)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 2
    host = a.host or ("127.0.0.1" if dev else "0.0.0.0")  # noqa: S104 - containers bind all interfaces
    if dev:
        print(f"dev chat page: http://{host}:{a.port}/")
    uvicorn.run(app, host=host, port=a.port, log_level="info")
    return 0


def cmd_test(a) -> int:
    from .parity import cross_check, matrix, run_sync
    d = _kit_dir(a.directory)
    res = run_sync(d, a.framework or None, a.only or None)
    print(matrix(res))
    bad = [r for r in res if not r.passed]
    for r in bad:
        print(f"\n✗ {r.framework} / {r.conversation}:\n  " + "\n  ".join(r.problems))
    dis = cross_check(res)
    for p in dis:
        print(f"\n✗ {p}")
    n = len(res)
    print(f"\n{n - len(bad)}/{n} passed" + ("" if not dis else f", {len(dis)} disagreement(s)"))
    if a.json:
        Path(a.json).write_text(json.dumps([r.__dict__ for r in res], indent=1, default=str), encoding="utf-8")
    return 1 if bad or dis else 0


def cmd_prompts(a) -> int:
    import yaml

    from .prompts import lock
    d = _kit_dir(a.directory)
    pdir = d / "prompts"
    data = lock(pdir)
    if a.action == "promote":
        data["prompts"][a.id]["stages"][a.stage] = a.version
        if a.version not in data["prompts"][a.id]["versions"]:
            print(f"error: {a.id}@{a.version} not found", file=sys.stderr)
            return 2
        (d / "prompts.lock").write_text("# generated by `kit prompts lock`; promote with `kit prompts promote`\n" + yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
        print(f"{a.id}: {a.stage} -> {a.version}")
    else:
        print("locked: " + ", ".join(f"{k}@{v}" for k, e in data["prompts"].items() for v in e["versions"]))
    return 0


def cmd_add(a) -> int:
    from .addons import add
    return add(a.addon, _kit_dir(a.directory))


DEPLOY = {
    "aws-ecs": "deploy/terraform/aws-ecs",
    "cloud-run": "deploy/terraform/gcp-cloud-run",
    "agentcore": "deploy/agentcore",
    "agent-runtime": "deploy/agent-runtime",
}


def cmd_deploy(a) -> int:
    root = Path(__file__).resolve().parents[2]
    p = root / DEPLOY[a.target] / "README.md"
    if not p.exists():
        print(f"see https://github.com/koushikmohanbhat/agent-starter-kit/tree/main/{DEPLOY[a.target]}")
        return 0
    print(p.read_text(encoding="utf-8"))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_env_file(os.environ.get("KIT_ENV_FILE", ".env"))
    ap = argparse.ArgumentParser(prog="kit", description="framework-neutral agent starter kit")
    ap.add_argument("--version", action="version", version=f"agent-starter-kit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create a project from a kit")
    p.add_argument("directory")
    p.add_argument("--kit", default="support-agent")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)

    for name, fn, hlp in (("check", cmd_check, "validate the kit"),):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("directory", nargs="?")
        p.add_argument("--framework", choices=FRAMEWORKS)
        p.set_defaults(fn=fn)

    p = sub.add_parser("run", help="one turn from the terminal")
    p.add_argument("message")
    p.add_argument("directory", nargs="?")
    p.add_argument("--user", default="cust-001")
    p.add_argument("--tenant", default="default")
    p.add_argument("--roles", default="")
    p.add_argument("--framework", choices=FRAMEWORKS)
    p.set_defaults(fn=cmd_run)

    for name, dev in (("dev", True), ("serve", False)):
        p = sub.add_parser(name, help="local service + dev page" if dev else "production service")
        p.add_argument("directory", nargs="?")
        p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
        p.add_argument("--host")
        p.add_argument("--framework", choices=FRAMEWORKS)
        p.set_defaults(fn=lambda a, dev=dev: _serve(a, dev))

    p = sub.add_parser("test", help="parity suite across framework adapters")
    p.add_argument("directory", nargs="?")
    p.add_argument("--parity", action="store_true", help="(default) run parity.yaml")
    p.add_argument("--framework", action="append", choices=FRAMEWORKS)
    p.add_argument("--only", action="append", help="conversation id")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_test)

    p = sub.add_parser("prompts", help="lock / promote prompt versions")
    p.add_argument("action", choices=["lock", "promote"])
    p.add_argument("id", nargs="?")
    p.add_argument("version", nargs="?")
    p.add_argument("--stage", default="prod")
    p.add_argument("--dir", dest="directory")
    p.set_defaults(fn=cmd_prompts)

    p = sub.add_parser("add", help="optional add-ons")
    p.add_argument("addon", choices=["evals", "dpdp"])
    p.add_argument("directory", nargs="?")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("deploy", help="print deploy steps for a target")
    p.add_argument("--print", dest="target", required=True, choices=sorted(DEPLOY))
    p.set_defaults(fn=cmd_deploy)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
