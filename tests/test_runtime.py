import pytest

from agent_kit.runtime import AgentRuntime, ApprovalError
from agent_kit.tools import User

CUST, LEAD = User("cust-001"), User("lead-1", roles=["support_lead"])


@pytest.fixture
def rt(kit):
    return AgentRuntime.from_path(kit)


async def test_identity_scoping_and_sessions(rt):
    r = await rt.chat("Refund ORD-10005 to my card", CUST)
    assert r.tool_calls[0]["result"]["status"] == "not_found"            # another customer's order looks missing
    assert rt.services["orders"].state()["refunds"] == []
    r2 = await rt.chat("Where is ORD-10003?", User("cust-002"), session_id=r.session_id)
    assert r2.session_id != r.session_id                                  # can't continue another user's session


async def test_approval_flow_and_permissions(rt):
    r = await rt.chat("Please refund my headphones, order ORD-10004", CUST)
    (ap,) = r.pending_approvals
    assert "approval" in r.message and rt.services["orders"].state()["refunds"] == []
    with pytest.raises(PermissionError):
        await rt.decide(ap["id"], True, User("someone", roles=[]))
    out = await rt.decide(ap["id"], True, LEAD)
    assert out["approval"]["status"] == "approved" and "₹12,999" in out["message"]
    assert rt.services["orders"].state()["refunds"] == ["ORD-10004"]
    with pytest.raises(ApprovalError):
        await rt.decide(ap["id"], False, LEAD)
    msgs = rt.store.get_session(r.session_id)["messages"]
    assert msgs[-1]["approval"]["status"] == "approved"                  # the customer sees the outcome in the session


async def test_rejection_and_limit(rt):
    r = await rt.chat("Please refund my headphones, order ORD-10004", CUST)
    out = await rt.decide(r.pending_approvals[0]["id"], False, LEAD, "Outside the return window.")
    assert out["approval"]["status"] == "rejected" and "Outside the return window" in out["message"]
    assert rt.services["orders"].state()["refunds"] == []


async def test_test_mode_sandboxes_sessions(kit, monkeypatch):
    monkeypatch.setenv("KIT_TEST_MODE", "true")
    rt = AgentRuntime.from_path(kit)
    a = await rt.chat("I want a refund for ORD-10001, it arrived damaged", CUST)
    b = await rt.chat("I want a refund for ORD-10001, it arrived damaged", CUST)
    assert a.state == b.state == {"refunds": 1, "pending_approvals": 0, "address_updated": False, "escalated": False}
    assert rt.services["orders"].state()["refunds"] == []                # the shared service was never touched


async def test_inbound_hook_can_refuse(kit):
    (kit / "hook.py").write_text("from agent_kit.runtime import RefusedByHook\n"
                                 "def inbound(m, user, sid):\n    if user.id == 'withdrawn':\n        raise RefusedByHook('no consent')\n    return m.replace('secret', '<TOKEN>')\n")
    y = kit / "agent.yaml"
    y.write_text(y.read_text() + "\nhooks: {inbound: 'hook:inbound'}\n")
    rt = AgentRuntime.from_path(kit)
    r = await rt.chat("Where is ORD-10003? secret", CUST)
    assert rt.store.get_session(r.session_id)["messages"][0]["content"].endswith("<TOKEN>")
    from agent_kit.runtime import RefusedByHook
    with pytest.raises(RefusedByHook):
        await rt.chat("hi", User("withdrawn"))
