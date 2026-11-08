"""Offline scripted model for the support agent: deterministic rules in place of an LLM, served through the kit's
OpenAI-compatible endpoint so every framework adapter runs the same conversation through its real model path.

It plays a well-behaved model, which is the point: parity tests check that every *framework* produces the same tool
calls and final state, and that safety holds at the tool boundary (policies, record-level access) even when the
model does what an injected instruction asks."""
from __future__ import annotations

import json
import re
from typing import Any

ORDER = re.compile(r"\bORD-\d{5}\b", re.I)
INTENTS = [
    ("human", re.compile(r"\b(human|person|real agent|manager|speak to|talk to someone|third time|complaint)\b", re.I)),
    ("refund", re.compile(r"\b(refund|money back|reimburse)\b", re.I)),
    ("address", re.compile(r"\b(address|deliver(?:y)? to|ship (?:it )?to)\b", re.I)),
    ("status", re.compile(r"\b(where|status|track|arrive|shipped)\b", re.I)),
]


def _intent(text: str) -> str | None:
    return next((name for name, rx in INTENTS if rx.search(text)), None)


def _rupees(v: float) -> str:
    return f"₹{v:,.0f}"


def respond(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    users = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if not users:
        return {"content": "Hello! How can I help with your order?"}
    last = users[-1]
    text = messages[last]["content"]
    # tool calls made in this turn, with their results
    done: dict[str, dict] = {}
    names: dict[str, str] = {}
    for m in messages[last + 1:]:
        for tc in m.get("tool_calls") or []:
            names[tc["id"]] = tc["name"]
        if m["role"] == "tool":
            try:
                done[names.get(m.get("tool_call_id"), "?")] = json.loads(m["content"])
            except (TypeError, ValueError):
                done[names.get(m.get("tool_call_id"), "?")] = {"raw": m["content"]}
    # order number: this message first, then earlier user turns
    oid = next((ORDER.search(messages[i]["content"]).group(0).upper() for i in reversed(users) if ORDER.search(messages[i]["content"])), None)
    intent = _intent(text) or ("status" if ORDER.search(text) else None)
    if intent is None and oid and any(_intent(messages[i]["content"]) for i in users[:-1]):
        intent = next(_intent(messages[i]["content"]) for i in reversed(users[:-1]) if _intent(messages[i]["content"]))
    if intent is None and re.search(r"\b(it|that one|this order)\b", text, re.I) and oid:
        intent = "status"

    if intent == "human":
        if "escalate_to_human" not in done:
            return {"tool_calls": [{"name": "escalate_to_human", "arguments": {"reason": text[:120]}}]}
        t = done["escalate_to_human"]
        return {"content": f"I'm sorry about this. I've passed your conversation to a colleague (ticket {t.get('ticket_id')}); "
                           f"they'll pick it up in about {t.get('eta_minutes', 15)} minutes."}
    if intent is None:
        return {"content": "I can check an order's status, refund a delivered order, change a delivery address before it ships, "
                           "or connect you with a colleague. What would you like to do?"}
    if not oid:
        return {"content": "Could you share your order number? It looks like ORD-12345."}
    if "lookup_order" not in done:
        return {"tool_calls": [{"name": "lookup_order", "arguments": {"order_id": oid}}]}
    o = done["lookup_order"]
    if o.get("status") == "not_found":
        return {"content": f"I couldn't find order {oid} on your account. Could you check the number?"}

    if intent == "status":
        when = f" (delivered on {o['delivered_on']})" if o.get("delivered_on") else (f" (shipped on {o['shipped_on']})" if o.get("shipped_on") else "")
        return {"content": f"Order {oid} is {o['status']}{when}."}
    if intent == "refund":
        if o["status"] != "delivered":
            return {"content": f"Order {oid} is {o['status']}, so it can't be refunded yet. Refunds are for delivered orders."}
        if "issue_refund" not in done:
            return {"tool_calls": [{"name": "issue_refund", "arguments": {"order_id": oid, "amount": o["total"], "reason": text[:120]}}]}
        r = done["issue_refund"]
        if r.get("status") == "refunded":
            return {"content": f"Done: I've refunded {_rupees(r['amount'])} for order {oid} (refund {r['refund_id']}). "
                               "It should reach your original payment method in 5-7 working days."}
        if r.get("status") == "pending_approval":
            return {"content": f"A refund of {_rupees(o['total'])} for order {oid} needs a team lead's approval, so I've submitted it "
                               f"(reference {r['approval_id']}). You'll get an update here once it's reviewed."}
        return {"content": f"I couldn't refund order {oid}: {r.get('reason') or r.get('error', 'the refund was not allowed')}."}
    if intent == "address":
        m = re.search(r"\bto\s+(.+?)[.?!]*$", text, re.I)
        new = m.group(1).strip() if m else ""
        if not new:
            return {"content": f"What's the new delivery address for order {oid}?"}
        if "update_address" not in done:
            return {"tool_calls": [{"name": "update_address", "arguments": {"order_id": oid, "address": new}}]}
        r = done["update_address"]
        if r.get("status") == "updated":
            return {"content": f"Updated: order {oid} will be delivered to {r['address']}."}
        return {"content": f"I couldn't change the address: {r.get('reason', 'the change was not allowed')}."}
    return {"content": "How else can I help?"}
