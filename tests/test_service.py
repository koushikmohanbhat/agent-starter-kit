import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from agent_kit.service import create_app
from agent_kit.service.auth import AuthConfigError


def client(kit, monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return TestClient(create_app(kit))


def test_auth_mode_is_required_and_dev_is_guarded(kit, monkeypatch):
    with pytest.raises(AuthConfigError):
        create_app(kit)
    monkeypatch.setenv("KIT_AUTH", "dev")
    with pytest.raises(AuthConfigError, match="KIT_ENV=dev"):
        create_app(kit)


def test_api_key_chat_stream_sessions_and_approvals(kit, monkeypatch):
    with client(kit, monkeypatch, KIT_AUTH="api_key", KIT_API_KEYS="k1,k2") as c:
        assert c.post("/v1/chat", json={"message": "hi"}).status_code == 401
        h = {"X-API-Key": "k2", "X-End-User-Id": "cust-001"}
        r = c.post("/v1/chat", headers=h, json={"message": "Please refund my headphones, order ORD-10004"}).json()
        assert r["pending_approvals"] and r["framework"] == "openai_agents" and r["prompt"]["version"] == "1.0.0"
        assert c.get(f"/v1/sessions/{r['session_id']}", headers={**h, "X-End-User-Id": "cust-002"}).status_code == 404
        assert c.get("/v1/approvals", headers=h).status_code == 403
        lead = {"X-API-Key": "k1", "X-End-User-Id": "lead-1", "X-End-User-Roles": "support_lead"}
        (ap,) = c.get("/v1/approvals", headers=lead).json()["approvals"]
        d = c.post(f"/v1/approvals/{ap['id']}", headers=lead, json={"approve": True}).json()
        assert d["approval"]["status"] == "approved"
        assert c.post(f"/v1/approvals/{ap['id']}", headers=lead, json={"approve": True}).status_code == 409
        with c.stream("POST", "/v1/chat", headers=h, json={"message": "Where is ORD-10003?", "stream": True}) as s:
            events = [json.loads(line[6:]) for line in s.iter_lines() if line.startswith("data: ")]
        assert [e["type"] for e in events] == ["tool_call", "tool_result", "final"] and "shipped" in events[-1]["message"]
        assert c.get("/v1/agent", headers=h).json()["tools"][0]["name"] == "lookup_order"
        assert c.get("/readyz").json()["status"] == "ready"
        assert c.delete("/v1/users/cust-001", headers=h).status_code == 403
        admin = {"X-API-Key": "k1", "X-End-User-Id": "dpo", "X-End-User-Roles": "privacy_admin"}
        assert c.delete("/v1/users/cust-001", headers=admin).json()["deleted_records"] >= 2
        assert c.get(f"/v1/sessions/{r['session_id']}", headers=h).status_code == 404


def test_oidc_jwt(kit, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeJWKS:
        def get_signing_key_from_jwt(self, token):
            return type("K", (), {"key": key.public_key()})()
    monkeypatch.setattr("agent_kit.service.auth._jwks", lambda url: FakeJWKS())
    with client(kit, monkeypatch, KIT_AUTH="oidc", KIT_OIDC_ISSUER="https://idp.example", KIT_OIDC_AUDIENCE="support-agent") as c:
        def tok(**over):
            claims = {"sub": "cust-001", "iss": "https://idp.example", "aud": "support-agent", "exp": int(time.time()) + 300, **over}
            return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}
        assert c.post("/v1/chat", headers=tok(), json={"message": "Where is ORD-10003?"}).json()["message"].startswith("Order ORD-10003")
        assert c.post("/v1/chat", headers=tok(aud="other"), json={"message": "x"}).status_code == 401
        assert c.post("/v1/chat", headers=tok(exp=1), json={"message": "x"}).status_code == 401


def test_dev_page(kit, monkeypatch):
    with client(kit, monkeypatch, KIT_AUTH="dev", KIT_ENV="dev") as c:
        assert "agent-starter-kit" in c.get("/").text
        assert c.post("/v1/chat", headers={"X-User-Id": "cust-001"}, json={"message": "Where is ORD-10003?"}).status_code == 200
