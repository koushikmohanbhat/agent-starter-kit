from agent_kit.cli import main


def test_init_check_add_and_prompts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SESSION_STORE", "memory://")
    d = tmp_path / "proj"
    assert main(["init", str(d)]) == 0
    assert (d / "agent.yaml").exists() and (d / ".env.example").exists() and not (d / "__pycache__").exists()
    assert main(["check", str(d)]) == 0
    assert main(["add", "evals", str(d)]) == 0 and (d / "evals/suite.yaml").exists()
    assert main(["add", "dpdp", str(d)]) == 0 and (d / "dpdp_hooks.py").exists()
    assert "inbound: dpdp_hooks:inbound" in (d / "agent.yaml").read_text()
    assert main(["prompts", "lock", "--dir", str(d)]) == 0
    assert main(["init", str(d)]) == 2                                   # refuses a non-empty folder


def test_run_prints_tools(kit, capsys):
    assert main(["run", "I want a refund for ORD-10001", str(kit)]) == 0
    out = capsys.readouterr().out
    assert "→ lookup_order" in out and "→ issue_refund" in out and "refunded" in out


def test_evals_addon_cases_are_valid():
    import json
    from pathlib import Path
    rows = [json.loads(line) for line in (Path(__file__).resolve().parents[1] / "addon_files/evals/data/cases.jsonl").read_text().splitlines()]
    assert len({r["id"] for r in rows}) == len(rows) >= 15
    assert all("final_state" in r["reference"] for r in rows)


def test_add_connectors(kit):
    from agent_kit.addons import add
    (kit / ".env.example").write_text("KIT_AUTH=dev\n")
    assert add("connectors", kit) == 0
    assert add("connectors", kit) == 0
    text = (kit / "agent.yaml").read_text()
    assert text.count("\nmcp_tools:") == 1 and "/mcp/${CONNECTOR_HUB_PROFILE:-support-agent}" in text
    assert "CONNECTOR_HUB_API_KEY" in (kit / ".env.example").read_text()
    from agent_kit.config import load_agent
    d = load_agent(kit / "agent.yaml")
    assert d.mcp_tools[0]["headers_env"] == {"X-API-Key": "CONNECTOR_HUB_API_KEY"}
