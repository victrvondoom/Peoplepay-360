"""Persistent local commerce workflows; sandbox checkout never moves money."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlparse

from beacon.assurance import EventKind, State, utcnow
from beacon.assurance.money import Money
from beacon.peoplepay.authority import Permission
from beacon.peoplepay.agent import parse_budget
from beacon.peoplepay.mandate import CartLine, CheckoutSnapshot
from beacon.peoplepay.transaction import Transaction


def _text(body: dict[str, Any], key: str, *, maximum: int = 500) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{key} must be non-empty text of at most {maximum} characters")
    return value.strip()


def _minor(value: Any, label: str) -> int:
    if type(value) is not int or value < 0 or value > 10**12:
        raise ValueError(f"{label} must be a non-negative integer in minor units")
    return value


def save_cart(txn: Transaction, body: dict[str, Any], actor: str) -> dict[str, Any]:
    txn.require_permission(Permission.PLANNING, actor=actor)
    if txn.state is State.CANCELLED:
        raise ValueError("Transaction is cancelled")
    if txn.context.get("fulfillment", {}).get("order"):
        raise ValueError("This cart already has an order; create a new transaction")
    raw_lines = body.get("items")
    if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 50:
        raise ValueError("items must contain between 1 and 50 products")
    currency = _text(body, "currency", maximum=3).upper()
    if currency not in ("INR", "USD", "EUR", "GBP"):
        raise ValueError("Supported currencies: INR, USD, EUR, GBP")
    items, lines = [], []
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            raise ValueError("Each item must be an object")
        title = _text(raw, "title", maximum=200)
        merchant = _text(raw, "merchant", maximum=200)
        variant = _text(raw, "variant", maximum=200)
        quantity = raw.get("quantity")
        if type(quantity) is not int or not 1 <= quantity <= 100:
            raise ValueError("quantity must be an integer between 1 and 100")
        price = _minor(raw.get("unit_price_minor"), "unit_price_minor")
        url = raw.get("url", "")
        if not isinstance(url, str) or len(url) > 2000:
            raise ValueError("Invalid product URL")
        if url and (urlparse(url).scheme != "https" or not urlparse(url).hostname):
            raise ValueError("Product links must use HTTPS")
        line = CartLine(str(index), merchant, title, variant, quantity, Money(price, currency))
        lines.append(line)
        items.append({"title": title, "merchant": merchant, "variant": variant,
                      "quantity": quantity, "unit_price_minor": price, "url": url})
    shipping = _minor(body.get("shipping_minor"), "shipping_minor")
    tax = _minor(body.get("tax_minor"), "tax_minor")
    snapshot = CheckoutSnapshot.create(
        lines, shipping=Money(shipping, currency), tax=Money(tax, currency),
    )
    cart = {"items": items, "currency": currency, "shipping_minor": shipping,
            "tax_minor": tax, "total": snapshot.total.to_dict(),
            "cart_hash": snapshot.cart_hash, "source": "SELF_REPORTED",
            "saved_at": utcnow().isoformat()}
    txn.attach_context("product", {"cart": cart}, actor=actor)
    return cart


def sandbox_checkout(txn: Transaction, body: dict[str, Any], actor: str) -> dict[str, Any]:
    txn.require_permission(Permission.PLANNING, actor=actor)
    if txn.state is State.CANCELLED:
        raise ValueError("Transaction is cancelled")
    cart = txn.context.get("product", {}).get("cart")
    if not cart:
        raise ValueError("Save a cart before checkout")
    if body.get("confirm_sandbox") is not True:
        raise ValueError("Explicit sandbox confirmation is required")
    if body.get("cart_hash") != cart["cart_hash"]:
        raise ValueError("Cart changed; review and confirm the new total")
    existing = txn.context.get("fulfillment", {}).get("order")
    if existing:
        return {"order": existing, "replayed": True}
    budget = txn.mandate.max_amount if txn.mandate else parse_budget(txn.raw_utterance)
    if budget and (cart["currency"] != budget.currency or cart["total"]["minor"] > budget.minor):
        raise ValueError("Cart exceeds the stated budget or uses another currency")
    order = {"order_id": f"sandbox-{uuid.uuid4().hex[:12]}", "mode": "SANDBOX",
             "money_moved": False, "status": "PLACED", "cart": cart,
             "created_at": utcnow().isoformat(), "updates": []}
    txn.attach_context("fulfillment", {"order": order}, actor=actor)
    txn.ledger.append(EventKind.AGENT_ACTION, actor=actor,
                      detail={"action": "sandbox_checkout", "order_id": order["order_id"],
                              "mode": "SANDBOX", "money_moved": False})
    return {"order": order, "replayed": False}


def update_delivery(txn: Transaction, body: dict[str, Any], actor: str) -> dict[str, Any]:
    txn.require_permission(Permission.PLANNING, actor=actor)
    order = txn.context.get("fulfillment", {}).get("order")
    if not order:
        raise ValueError("No order exists for this transaction")
    transitions = {"PLACED": {"SHIPPED", "CANCELLED"},
                   "SHIPPED": {"DELIVERED", "DELIVERY_FAILED"},
                   "DELIVERY_FAILED": {"SHIPPED", "CANCELLED"},
                   "DELIVERED": set(), "CANCELLED": set()}
    status = _text(body, "status")
    if status not in transitions.get(order["status"], set()):
        raise ValueError(f"Cannot change delivery from {order['status']} to {status}")
    note = _text(body, "note", maximum=2000)
    updated = {**order, "status": status, "updates": [*order["updates"],
        {"status": status, "note": note, "at": utcnow().isoformat(),
         "source": "USER_RECORDED", "actor": actor}]}
    txn.attach_context("fulfillment", {**txn.context.get("fulfillment", {}), "order": updated}, actor=actor)
    return {"order": updated}


def create_dispute(txn: Transaction, body: dict[str, Any], actor: str) -> dict[str, Any]:
    txn.require_permission(Permission.PLANNING, actor=actor)
    order = txn.context.get("fulfillment", {}).get("order")
    if not order:
        raise ValueError("An order is required before preparing a dispute")
    issue = _text(body, "issue", maximum=4000)
    remedy = _text(body, "remedy", maximum=1000)
    draft = (f"Subject: Request concerning order {order['order_id']}\n\n"
             f"Order reference: {order['order_id']}\n"
             f"Recorded order status: {order['status']}\n\n"
             f"Issue reported by customer:\n{issue}\n\n"
             f"Requested resolution:\n{remedy}\n\n"
             "Please acknowledge this request and provide the next steps.")
    dispute = {"issue": issue, "remedy": remedy, "draft": draft,
               "status": "DRAFT", "submitted": False, "mode": order["mode"],
               "created_at": utcnow().isoformat()}
    txn.attach_context("fulfillment", {"order": order, "dispute": dispute}, actor=actor)
    return {"dispute": dispute}
