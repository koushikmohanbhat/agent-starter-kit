"""Mock order API with the routes HttpOrders expects. Run: uvicorn mock_api.app:app --port 8081 (from the kit folder).

Replace with the customer's order system, or put a facade with these routes in front of it."""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from orders_client import InMemoryOrders
from pydantic import BaseModel

app = FastAPI(title="Mock order API")
db = InMemoryOrders()
TOKEN = os.environ.get("ORDER_API_TOKEN")


def _auth(authorization: str | None):
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad token")


class AddressIn(BaseModel):
    customer_id: str
    address: str


class RefundIn(BaseModel):
    customer_id: str
    amount: float
    reason: str = ""


class TicketIn(BaseModel):
    customer_id: str
    reason: str
    session_id: str = ""


@app.get("/orders/{order_id}")
def get_order(order_id: str, customer_id: str, authorization: str | None = Header(None)):
    _auth(authorization)
    o = db.get(order_id, customer_id)
    if o is None:
        raise HTTPException(404, "not found")
    return o


@app.post("/orders/{order_id}/address")
def set_address(order_id: str, body: AddressIn, authorization: str | None = Header(None)):
    _auth(authorization)
    if db.get(order_id, body.customer_id) is None:
        raise HTTPException(404, "not found")
    return db.set_address(order_id.upper(), body.customer_id, body.address)


@app.post("/orders/{order_id}/refunds")
def refund(order_id: str, body: RefundIn, authorization: str | None = Header(None)):
    _auth(authorization)
    if db.get(order_id, body.customer_id) is None:
        raise HTTPException(404, "not found")
    return db.refund(order_id.upper(), body.customer_id, body.amount, body.reason)


@app.post("/tickets")
def ticket(body: TicketIn, authorization: str | None = Header(None)):
    _auth(authorization)
    return db.ticket(body.customer_id, body.reason, body.session_id)


@app.get("/_state")
def state():
    return db.state()
