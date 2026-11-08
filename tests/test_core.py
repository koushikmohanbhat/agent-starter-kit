import pytest

from agent_kit.config import ConfigError, MissingEnvError, PolicySpec, interpolate_env, load_agent
from agent_kit.policies import PolicyError, PolicySet, compile_rule
from agent_kit.prompts import resolve
from agent_kit.stores import open_store
from agent_kit.tools import spec_from_function


def test_policies_allow_deny_approval_and_sandbox():
    ps = PolicySet([PolicySpec(tool="refund", require_approval_if="args.amount > 5000", approver_role="lead"),
                    PolicySpec(tool="refund", deny_if="'blocked' in user.roles", message="blocked users can't refund")])
    assert ps.evaluate("refund", {"amount": 100}, {"roles": []}).action == "allow"
    assert ps.evaluate("refund", {"amount": "12999"}, {"roles": []}).action == "require_approval"
    assert ps.evaluate("refund", {"amount": 1}, {"roles": ["blocked"]}).action == "deny"      # deny beats approval
    assert ps.evaluate("refund", {}, {"roles": []}).action == "allow"                          # missing arg is not an error
    for bad in ("__import__('os')", "args.__class__", "open('x')", "x > 1", "[c for c in args]"):
        with pytest.raises(PolicyError):
            compile_rule(bad)


def test_tool_schema_hides_ctx_and_uses_docstring():
    from agent_kit.tools import ToolContext

    def issue_refund(order_id: str, amount: float, reason: str = "", *, ctx: ToolContext) -> dict:
        """Refund an order.

        More detail that should not be in the description."""
        return {}
    s = spec_from_function(issue_refund)
    assert s.wants_ctx and s.description == "Refund an order."
    assert set(s.schema["properties"]) == {"order_id", "amount", "reason"}
    assert s.schema["required"] == ["order_id", "amount"] and s.schema["additionalProperties"] is False


def test_env_interpolation_and_inline_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("X", "1")
    assert interpolate_env({"a": "${X}", "b": "${Y:-d}"}) == {"a": "1", "b": "d"}
    with pytest.raises(MissingEnvError):
        interpolate_env("${NOPE}")
    (tmp_path / "agent.yaml").write_text("name: a\ninstructions: {text: hi}\ntools: [m:f]\nmodel: {provider: openai, api_key: sk-123}\n")
    with pytest.raises(ConfigError, match="api_key_env"):
        load_agent(tmp_path)


def test_prompt_lock_detects_edits(kit):
    ins = resolve(kit / "prompts", {"prompt": "support_agent", "stage": "prod"})
    assert ins.version == "1.0.0" and ins.hash.startswith("sha256:")
    (kit / "prompts/support_agent/1.0.0/system.md").write_text("edited")
    with pytest.raises(ValueError, match="edited after it was locked"):
        resolve(kit / "prompts", {"prompt": "support_agent", "stage": "prod"})


@pytest.mark.parametrize("url", ["memory://", "sqlite:///{tmp}/s.db"])
def test_stores_sessions_approvals_and_erasure(url, tmp_path):
    st = open_store(url.format(tmp=tmp_path))
    st.save_session({"id": "s1", "user_id": "u1", "tenant": "t", "messages": [], "created_at": 1, "updated_at": 9e12})
    st.save_session({"id": "s2", "user_id": "u2", "tenant": "t", "messages": [], "created_at": 1, "updated_at": 9e12})
    st.put_approval({"id": "a1", "status": "pending", "user": {"id": "u1", "tenant": "t"}, "created_at": 1})
    assert st.get_session("s1")["user_id"] == "u1" and len(st.list_approvals("pending", "t")) == 1
    assert st.delete_user("u1", "t") == 2
    assert st.get_session("s1") is None and st.get_session("s2") is not None and st.list_approvals() == []
    st.save_session({"id": "old", "user_id": "u", "tenant": "t", "messages": [], "created_at": 1, "updated_at": 1})
    assert st.get_session("old") is None        # expired by ttl
