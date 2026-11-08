"""Order tools. Identity comes from ctx.user (verified by the service), never from model arguments, so a customer
can only ever see or change their own orders: another customer's order looks exactly like a missing one."""
from __future__ import annotations

from agent_kit.tools import ToolContext

NOT_FOUND = {"status": "not_found", "message": "No order with that number on this customer's account."}
LOCKED = ("shipped", "delivered", "cancelled")


def lookup_order(order_id: str, *, ctx: ToolContext) -> dict:
    """Look up one of the customer's orders by its number (e.g. ORD-10001): status, items, total and dates."""
    o = ctx.services["orders"].get(order_id, ctx.user.id)
    if o is None:
        return NOT_FOUND
    return {k: o.get(k) for k in ("order_id", "status", "items", "total", "currency", "delivered_on", "shipped_on", "refunded") if o.get(k) is not None}


def update_address(order_id: str, address: str, *, ctx: ToolContext) -> dict:
    """Change the delivery address of an order that has not shipped yet."""
    orders = ctx.services["orders"]
    o = orders.get(order_id, ctx.user.id)
    if o is None:
        return NOT_FOUND
    if o["status"] in LOCKED:
        return {"status": "denied", "reason": f"the order is already {o['status']}, so the address can't be changed"}
    if len(address.strip()) < 8:
        return {"status": "denied", "reason": "the new address looks incomplete"}
    return orders.set_address(o["order_id"], ctx.user.id, address.strip())
