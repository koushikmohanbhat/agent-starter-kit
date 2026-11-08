"""Refund tool. Business rules live here (delivered orders only, at most the order total, once); the approval rule
for large refunds lives in agent.yaml policies, so it applies whatever the model or framework does."""
from __future__ import annotations

from agent_kit.tools import ToolContext

from .orders import NOT_FOUND


def issue_refund(order_id: str, amount: float, reason: str = "", *, ctx: ToolContext) -> dict:
    """Refund a delivered order, up to its total. Refunds above the limit are held for a team lead's approval."""
    orders = ctx.services["orders"]
    o = orders.get(order_id, ctx.user.id)
    if o is None:
        return NOT_FOUND
    if o["status"] != "delivered":
        return {"status": "denied", "reason": f"only delivered orders can be refunded (this one is {o['status']})"}
    if o.get("refunded"):
        return {"status": "denied", "reason": "this order has already been refunded"}
    if amount <= 0 or amount > o["total"]:
        return {"status": "denied", "reason": f"the refund must be between 0 and the order total ({o['total']:.0f} {o['currency']})"}
    return orders.refund(o["order_id"], ctx.user.id, float(amount), reason)
