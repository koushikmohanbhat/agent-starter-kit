"""The order system the tools talk to. Two interchangeable clients behind one interface:

- InMemoryOrders: seeded from data/orders.json (offline mode, tests, parity).
- HttpOrders:     the customer's order API, or the bundled mock (mock_api/app.py). Set ORDER_API_URL.

To connect the customer's system, implement the same five methods against their API (or put a small facade with
the mock API's routes in front of it). The tools don't change.
"""
from __future__ import annotations

import copy
import json
import os
import uuid
from pathlib import Path
from typing import Any

SEED = Path(__file__).parent / "data" / "orders.json"


class InMemoryOrders:
    def __init__(self, seed: Path = SEED):
        self.orders = {o["order_id"]: o for o in json.loads(seed.read_text(encoding="utf-8"))["orders"]}
        self.refunds: list[dict[str, Any]] = []
        self.address_updates: list[dict[str, Any]] = []
        self.tickets: list[dict[str, Any]] = []

    def get(self, order_id: str, customer_id: str) -> dict[str, Any] | None:
        o = self.orders.get(order_id.strip().upper())
        return copy.deepcopy(o) if o and o["customer_id"] == customer_id else None

    def set_address(self, order_id: str, customer_id: str, address: str) -> dict[str, Any]:
        o = self.orders[order_id]
        o["address"] = address
        self.address_updates.append({"order_id": order_id, "address": address})
        return {"status": "updated", "order_id": order_id, "address": address}

    def refund(self, order_id: str, customer_id: str, amount: float, reason: str) -> dict[str, Any]:
        rid = f"RF-{uuid.uuid5(uuid.NAMESPACE_URL, order_id).hex[:8].upper()}"
        self.orders[order_id]["refunded"] = True
        self.refunds.append({"order_id": order_id, "amount": amount, "refund_id": rid})
        return {"status": "refunded", "order_id": order_id, "amount": amount, "currency": self.orders[order_id]["currency"], "refund_id": rid}

    def ticket(self, customer_id: str, reason: str, session_id: str) -> dict[str, Any]:
        tid = f"TCK-{len(self.tickets) + 1:04d}"
        self.tickets.append({"ticket_id": tid, "customer_id": customer_id, "reason": reason, "session_id": session_id})
        return {"status": "escalated", "ticket_id": tid, "eta_minutes": 15}

    def state(self) -> dict[str, Any]:
        return {"refunds": [r["order_id"] for r in self.refunds], "address_updates": [a["order_id"] for a in self.address_updates],
                "tickets": len(self.tickets)}


class HttpOrders:
    """Same interface over HTTP (the mock API's routes). Auth header from ORDER_API_TOKEN if set."""

    def __init__(self, base_url: str, token: str | None = None):
        import httpx
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=15,
                                 headers={"Authorization": f"Bearer {token}"} if token else {})

    def get(self, order_id, customer_id):
        r = self.http.get(f"/orders/{order_id}", params={"customer_id": customer_id})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def set_address(self, order_id, customer_id, address):
        return self._post(f"/orders/{order_id}/address", {"customer_id": customer_id, "address": address})

    def refund(self, order_id, customer_id, amount, reason):
        return self._post(f"/orders/{order_id}/refunds", {"customer_id": customer_id, "amount": amount, "reason": reason})

    def ticket(self, customer_id, reason, session_id):
        return self._post("/tickets", {"customer_id": customer_id, "reason": reason, "session_id": session_id})

    def _post(self, path, body):
        r = self.http.post(path, json=body)
        r.raise_for_status()
        return r.json()


def make_client():
    url = os.environ.get("ORDER_API_URL")
    return HttpOrders(url, os.environ.get("ORDER_API_TOKEN")) if url else InMemoryOrders()


def turn_state(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    """What a turn did, for eval graders (returned only when KIT_TEST_MODE=true)."""
    res = [(c["name"], c.get("result") or {}) for c in tool_calls]
    return {"refunds": sum(1 for n, r in res if n == "issue_refund" and r.get("status") == "refunded"),
            "pending_approvals": sum(1 for n, r in res if r.get("status") == "pending_approval"),
            "address_updated": any(n == "update_address" and r.get("status") == "updated" for n, r in res),
            "escalated": any(n == "escalate_to_human" and r.get("status") == "escalated" for n, r in res)}
