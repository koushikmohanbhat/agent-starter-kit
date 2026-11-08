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
