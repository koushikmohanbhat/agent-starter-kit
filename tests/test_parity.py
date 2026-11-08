import pytest
from conftest import KIT

from agent_kit.parity import available_frameworks, cross_check, run_parity

AVAILABLE = available_frameworks()


@pytest.mark.parametrize("framework", AVAILABLE)
async def test_parity(framework, monkeypatch):
    monkeypatch.setenv("SESSION_STORE", "memory://")
    res = await run_parity(KIT, [framework])
    bad = [f"{r.conversation}: {r.problems}" for r in res if not r.passed]
    assert not bad, "\n".join(bad)


async def test_adapters_agree():
    if len(AVAILABLE) < 2:
        pytest.skip("needs two adapters installed")
    res = await run_parity(KIT, AVAILABLE, only=["refund-needs-approval", "multi-turn", "prompt-injection"])
    bad = [f"{r.framework}/{r.conversation}: {r.problems}" for r in res if not r.passed]
    assert not bad, "\n".join(bad)
    assert cross_check(res) == []
