"""Persistent reference merchant for the PeoplePay unified journey.

This simulator follows the checkout lifecycle described by the Agentic Checkout
Spec, but is not an ACP implementation or a payment provider. The catalog is
merchant-owned, checkout quotes are authoritative within this simulator, and no
money moves. Gateway must verify the human approval before passing an action.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for different operation input."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def terms_hash(terms: dict[str, Any]) -> str:
    """Hash exact approved terms; changing even one field requires approval."""
    return hashlib.sha256(_canonical(terms).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, label: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be non-empty text (maximum {maximum})")
    return value


def _integer(value: Any, label: str, maximum: int = 10**14, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def default_reference_catalog() -> list[dict[str, Any]]:
    """Synthetic merchant inventory; none of these rows are live supplier offers."""
    return [
        {"supplier_id": "supplier-a", "product_id": "chair-a", "title": "Supplier A ergonomic chair",
         "unit_price_minor": 650000, "currency": "INR", "shipping_minor": 0,
         "tax_minor": 0, "delivery_days": 20},
        {"supplier_id": "supplier-b", "product_id": "chair-b", "title": "Supplier B ergonomic chair",
         "unit_price_minor": 590000, "currency": "INR", "shipping_minor": 0,
         "tax_minor": 0, "delivery_days": 25},
        {"supplier_id": "supplier-c", "product_id": "chair-c", "title": "Supplier C ergonomic chair",
         "unit_price_minor": 520000, "currency": "INR", "shipping_minor": 0,
         "tax_minor": 0, "delivery_days": 40},
    ]


class ReferenceMerchant:
    """SQLite-backed simulator with atomic idempotency and order event storage.

    Authorized actions are dictionaries with ``action_id``, ``actor_id``,
    ``transaction_id``, ``decision_id``, integer ``decision_version``,
    ``decision_hash``, ``terms_hash``, ``terms``, ``mode: reference`` and
    ``money_moved: false``. Terms contain supplier and
    product identity, quantity, integer minor-unit prices and totals, currency,
    delivery days, budget and maximum delivery days. Authentication and approval
    validation belong to Gateway; this class checks the immutable bindings and
    current merchant quote again at completion.
    """

    def __init__(self, db_path: str | Path = ":memory:",
                 catalog: list[dict[str, Any]] | None = None):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False,
                                     isolation_level=None, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=10000")
        if str(db_path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS reference_merchant_catalog (
                supplier_id TEXT NOT NULL, product_id TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (supplier_id, product_id));
            CREATE TABLE IF NOT EXISTS reference_merchant_sessions (
                id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reference_merchant_actions (
                id TEXT PRIMARY KEY, binding_hash TEXT NOT NULL, session_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reference_merchant_orders (
                id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reference_merchant_transaction_orders (
                actor_id TEXT NOT NULL, transaction_id TEXT NOT NULL, order_id TEXT NOT NULL,
                PRIMARY KEY(actor_id, transaction_id));
            CREATE TABLE IF NOT EXISTS reference_merchant_events (
                id TEXT PRIMARY KEY, order_id TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reference_merchant_idempotency (
                operation TEXT NOT NULL, key TEXT NOT NULL, input_hash TEXT NOT NULL,
                response TEXT NOT NULL, PRIMARY KEY (operation, key));
        """)
        with self._transaction():
            for row in self._conn.execute("SELECT id,data FROM reference_merchant_orders").fetchall():
                old = json.loads(row["data"])
                self._conn.execute("INSERT OR IGNORE INTO reference_merchant_transaction_orders VALUES (?,?,?)",
                                   (old["actor_id"], old["transaction_id"], row["id"]))
            for item in default_reference_catalog() if catalog is None else catalog:
                checked = self._catalog_item(item)
                self._conn.execute(
                    "INSERT OR IGNORE INTO reference_merchant_catalog VALUES (?, ?, ?)",
                    (checked["supplier_id"], checked["product_id"], _canonical(checked)))

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

    def _catalog_item(self, item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("catalog item must be an object")
        checked: dict[str, Any] = {key: _text(item.get(key), key) for key in ("supplier_id", "product_id", "title")}
        if item.get("currency") != "INR":
            raise ValueError("Reference merchant supports INR only")
        checked["currency"] = "INR"
        checked["unit_price_minor"] = _integer(item.get("unit_price_minor"), "unit_price_minor")
        for key in ("shipping_minor", "tax_minor"):
            checked[key] = _integer(item.get(key, 0), key)
        checked["delivery_days"] = _integer(item.get("delivery_days"), "delivery_days", 3650, 1)
        return checked

    def get_catalog(self) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(row["data"]) for row in self._conn.execute(
                "SELECT data FROM reference_merchant_catalog ORDER BY supplier_id, product_id")]

    def set_catalog_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Merchant-side administration, not exposed as a shopper API."""
        checked = self._catalog_item(item)
        with self._transaction():
            self._conn.execute("INSERT OR REPLACE INTO reference_merchant_catalog VALUES (?, ?, ?)",
                               (checked["supplier_id"], checked["product_id"], _canonical(checked)))
        return checked

    def quote(self, supplier_id: str, product_id: str, quantity: int,
              budget_minor: int, max_delivery_days: int) -> dict[str, Any]:
        supplier_id = _text(supplier_id, "supplier_id")
        product_id = _text(product_id, "product_id")
        quantity = _integer(quantity, "quantity", 10000, 1)
        budget_minor = _integer(budget_minor, "budget_minor")
        max_delivery_days = _integer(max_delivery_days, "max_delivery_days", 3650, 1)
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM reference_merchant_catalog WHERE supplier_id=? AND product_id=?",
                (supplier_id, product_id)).fetchone()
        if row is None:
            raise ValueError("Unknown merchant product/supplier combination")
        item = json.loads(row["data"])
        return {"supplier_id": supplier_id, "product_id": product_id, "quantity": quantity,
                "currency": item["currency"], "unit_price_minor": item["unit_price_minor"],
                "shipping_minor": item["shipping_minor"], "tax_minor": item["tax_minor"],
                "total_minor": quantity * item["unit_price_minor"] + item["shipping_minor"] + item["tax_minor"],
                "delivery_days": item["delivery_days"], "budget_minor": budget_minor,
                "max_delivery_days": max_delivery_days}

    def _action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, dict):
            raise ValueError("AuthorizedAction must be an object")
        checked: dict[str, Any] = {key: _text(action.get(key), key) for key in
                   ("action_id", "actor_id", "transaction_id", "decision_id", "decision_hash", "terms_hash")}
        if action.get("mode") != "reference" or action.get("money_moved") is not False:
            raise ValueError("Reference merchant accepts only explicitly simulated actions with money_moved=false")
        checked["mode"] = "reference"
        checked["money_moved"] = False
        checked["decision_version"] = _integer(action.get("decision_version"), "decision_version", 10**9, 1)
        if len(checked["decision_hash"]) != 64 or any(c not in "0123456789abcdef" for c in checked["decision_hash"]):
            raise ValueError("decision_hash must be a lowercase SHA-256 digest")
        terms = action.get("terms")
        if not isinstance(terms, dict):
            raise ValueError("AuthorizedAction.terms must be an object")
        for key in ("supplier_id", "product_id"):
            _text(terms.get(key), key)
        if terms.get("currency") != "INR":
            raise ValueError("Authorized terms must use INR")
        for key in ("unit_price_minor", "shipping_minor", "tax_minor", "total_minor", "budget_minor"):
            _integer(terms.get(key), key)
        _integer(terms.get("quantity"), "quantity", 10000, 1)
        for key in ("delivery_days", "max_delivery_days"):
            _integer(terms.get(key), key, 3650, 1)
        expected_total = terms["quantity"] * terms["unit_price_minor"] + terms["shipping_minor"] + terms["tax_minor"]
        if terms["total_minor"] != expected_total:
            raise ValueError("Approved total does not match approved line items")
        if terms_hash(terms) != checked["terms_hash"]:
            raise ValueError("Authorized terms hash mismatch")
        if terms["total_minor"] > terms["budget_minor"] or terms["delivery_days"] > terms["max_delivery_days"]:
            raise ValueError("Authorized terms violate budget or delivery policy")
        checked["terms"] = json.loads(_canonical(terms))
        return checked

    def _mutate(self, operation: str, key: str, request_id: str,
                payload: dict[str, Any], function: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        key = _text(key, "idempotency_key")
        request_id = _text(request_id, "request_id")
        input_hash = terms_hash(payload)
        with self._transaction():
            previous = self._conn.execute(
                "SELECT input_hash, response FROM reference_merchant_idempotency WHERE operation=? AND key=?",
                (operation, key)).fetchone()
            if previous is not None:
                if previous["input_hash"] != input_hash:
                    raise IdempotencyConflict("Idempotency key reused with different input")
                return {**json.loads(previous["response"]), "request_id": request_id, "replayed": True}
            response = {**function(), "request_id": request_id, "idempotency_key": key, "replayed": False}
            self._conn.execute("INSERT INTO reference_merchant_idempotency VALUES (?, ?, ?, ?)",
                               (operation, key, input_hash, _canonical(response)))
            return json.loads(_canonical(response))

    def _load(self, table: str, identifier: str) -> dict[str, Any]:
        # Table names are internal constants, never caller input.
        row = self._conn.execute(f"SELECT data FROM {table} WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Unknown checkout session or merchant order")
        return json.loads(row["data"])

    def _save(self, table: str, data: dict[str, Any], identifier: str = "id") -> None:
        self._conn.execute(f"INSERT OR REPLACE INTO {table} (id, data) VALUES (?, ?)",
                           (data[identifier], _canonical(data)))

    def _bind(self, session_id: str, action: dict[str, Any]) -> None:
        binding_hash = terms_hash(action)
        existing = self._conn.execute("SELECT * FROM reference_merchant_actions WHERE id=?",
                                      (action["action_id"],)).fetchone()
        if existing is not None:
            if existing["binding_hash"] != binding_hash or existing["session_id"] != session_id:
                raise ValueError("AuthorizedAction cannot be changed or reused for another checkout")
        else:
            self._conn.execute("INSERT INTO reference_merchant_actions VALUES (?, ?, ?)",
                               (action["action_id"], binding_hash, session_id))

    def _requote(self, session: dict[str, Any]) -> dict[str, Any]:
        approved = session["authorized_action"]["terms"]
        current = self.quote(approved["supplier_id"], approved["product_id"], approved["quantity"],
                             approved["budget_minor"], approved["max_delivery_days"])
        changed = terms_hash(current) != terms_hash(approved)
        reasons = []
        if changed:
            reasons.append("Merchant terms changed; renewed human approval required")
        if current["total_minor"] > current["budget_minor"]:
            reasons.append("Authoritative merchant total exceeds approved budget")
        if current["delivery_days"] > current["max_delivery_days"]:
            reasons.append("Authoritative delivery exceeds approved delivery limit")
        session.update({"terms": current, "terms_hash": terms_hash(current),
                        "status": "not_ready_for_payment" if reasons else "ready_for_payment",
                        "requires_approval": bool(reasons), "messages": reasons, "updated_at": _now()})
        return session

    def create_session(self, action: dict[str, Any], idempotency_key: str,
                       request_id: str) -> dict[str, Any]:
        checked = self._action(action)

        def create() -> dict[str, Any]:
            existing = self._conn.execute("SELECT session_id, binding_hash FROM reference_merchant_actions WHERE id=?",
                                          (checked["action_id"],)).fetchone()
            if existing is not None:
                if existing["binding_hash"] != terms_hash(checked):
                    raise ValueError("AuthorizedAction has changed")
                return self._load("reference_merchant_sessions", existing["session_id"])
            session_id = f"reference-checkout-{uuid.uuid4().hex}"
            session = {"id": session_id, "checkout_session_id": session_id,
                       "mode": "REFERENCE_SIMULATOR", "money_moved": False,
                       "authoritative_source": "reference_merchant_catalog",
                       "authorized_action": checked, "created_at": _now(), "external_order_ref": None}
            self._bind(session_id, checked)
            self._requote(session)
            self._save("reference_merchant_sessions", session)
            return session

        return self._mutate("create", idempotency_key, request_id, checked, create)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._transaction():
            session = self._load("reference_merchant_sessions", _text(session_id, "session_id"))
            if session["status"] not in ("completed", "canceled"):
                self._requote(session)
                self._save("reference_merchant_sessions", session)
            return session

    def update_session(self, session_id: str, action: dict[str, Any],
                       idempotency_key: str, request_id: str) -> dict[str, Any]:
        checked = self._action(action)
        session_id = _text(session_id, "session_id")

        def update() -> dict[str, Any]:
            session = self._load("reference_merchant_sessions", session_id)
            if session["status"] in ("completed", "canceled"):
                raise ValueError("Cannot update a completed or canceled checkout")
            previous = session["authorized_action"]
            for key in ("actor_id", "transaction_id", "decision_id"):
                if checked[key] != previous[key]:
                    raise ValueError("Renewed approval must belong to the same actor, transaction and decision")
            if checked["decision_version"] < previous["decision_version"]:
                raise ValueError("Cannot revert checkout to an older decision version")
            if checked["decision_version"] == previous["decision_version"] and checked != previous:
                raise ValueError("Changed approval requires a new immutable decision version")
            self._bind(session_id, checked)
            session["authorized_action"] = checked
            self._requote(session)
            self._save("reference_merchant_sessions", session)
            return session

        return self._mutate("update", idempotency_key, request_id,
                            {"session_id": session_id, "action": checked}, update)

    def _event(self, event_type: str, order: dict[str, Any], data: dict[str, Any],
               request_id: str) -> dict[str, Any]:
        event = {"event_id": f"reference-event-{uuid.uuid4().hex}", "schema_version": "1.0",
                 "event_type": event_type, "occurred_at": _now(),
                 "source": "reference_merchant", "mode": "REFERENCE_SIMULATOR",
                 "merchant_order_ref": order["external_order_ref"],
                 "transaction_id": order["transaction_id"], "correlation_id": order["transaction_id"],
                 "request_id": request_id, "decision_id": order["decision_id"],
                 "decision_version": order["decision_version"], "money_moved": False, "data": data}
        self._conn.execute("INSERT INTO reference_merchant_events VALUES (?, ?, ?)",
                           (event["event_id"], order["external_order_ref"], _canonical(event)))
        return event

    def complete_session(self, session_id: str, action: dict[str, Any],
                         idempotency_key: str, request_id: str) -> dict[str, Any]:
        checked = self._action(action)
        session_id = _text(session_id, "session_id")

        def complete() -> dict[str, Any]:
            session = self._load("reference_merchant_sessions", session_id)
            if checked != session["authorized_action"]:
                raise ValueError("Completion action must match the exact approved decision/version/terms")
            if session["status"] == "canceled":
                raise ValueError("Cannot complete a canceled checkout")
            if session["status"] == "completed":
                return {**session, "order": self._load("reference_merchant_orders", session["external_order_ref"])}
            existing = self._conn.execute(
                "SELECT order_id FROM reference_merchant_transaction_orders WHERE actor_id=? AND transaction_id=?",
                (checked["actor_id"], checked["transaction_id"])).fetchone()
            if existing:
                raise ValueError("This transaction already has a merchant order; a second approval cannot create another")
            self._requote(session)
            if session["requires_approval"]:
                self._save("reference_merchant_sessions", session)
                return session
            order_ref = f"reference-order-{uuid.uuid4().hex}"
            order = {"id": order_ref, "external_order_ref": order_ref,
                     "checkout_session_id": session_id, "transaction_id": checked["transaction_id"],
                     "actor_id": checked["actor_id"], "decision_id": checked["decision_id"],
                     "decision_version": checked["decision_version"], "decision_hash": checked["decision_hash"],
                     "terms_hash": checked["terms_hash"], "approved_terms": checked["terms"],
                     "status": "PLACED", "ordered_quantity": checked["terms"]["quantity"],
                     "delivered_quantity": 0, "delivery_final": False, "created_at": _now(),
                     "mode": "REFERENCE_SIMULATOR", "money_moved": False}
            self._save("reference_merchant_orders", order)
            self._conn.execute("INSERT INTO reference_merchant_transaction_orders VALUES (?,?,?)",
                               (checked["actor_id"], checked["transaction_id"], order_ref))
            session.update({"status": "completed", "external_order_ref": order_ref, "updated_at": _now()})
            self._save("reference_merchant_sessions", session)
            event = self._event("order.created", order,
                                {"status": "PLACED", "ordered_quantity": order["ordered_quantity"]}, request_id)
            return {**session, "order": order, "event": event}

        return self._mutate("complete", idempotency_key, request_id,
                            {"session_id": session_id, "action": checked}, complete)

    def cancel_session(self, session_id: str, idempotency_key: str,
                       request_id: str) -> dict[str, Any]:
        session_id = _text(session_id, "session_id")

        def cancel() -> dict[str, Any]:
            session = self._load("reference_merchant_sessions", session_id)
            if session["status"] in ("completed", "canceled"):
                raise ValueError("Cannot cancel a completed or canceled checkout")
            session.update({"status": "canceled", "updated_at": _now()})
            self._save("reference_merchant_sessions", session)
            return session

        return self._mutate("cancel", idempotency_key, request_id, {"session_id": session_id}, cancel)

    def get_order(self, external_order_ref: str) -> dict[str, Any]:
        with self._lock:
            return self._load("reference_merchant_orders", _text(external_order_ref, "external_order_ref"))

    def get_events(self, external_order_ref: str) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(row["data"]) for row in self._conn.execute(
                "SELECT data FROM reference_merchant_events WHERE order_id=? ORDER BY rowid",
                (_text(external_order_ref, "external_order_ref"),))]

    def record_delivery(self, external_order_ref: str, delivered_quantity: int,
                        idempotency_key: str, request_id: str, *, final: bool = True,
                        note: str = "") -> dict[str, Any]:
        external_order_ref = _text(external_order_ref, "external_order_ref")
        delivered_quantity = _integer(delivered_quantity, "delivered_quantity", 10000)
        if type(final) is not bool:
            raise ValueError("final must be a boolean")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("note must be text of at most 2000 characters")

        def deliver() -> dict[str, Any]:
            order = self._load("reference_merchant_orders", external_order_ref)
            if order["delivery_final"]:
                raise ValueError("Delivery already final; cannot change historical delivery evidence")
            if delivered_quantity < order["delivered_quantity"] or delivered_quantity > order["ordered_quantity"]:
                raise ValueError("Cumulative delivered quantity must increase within ordered quantity")
            missing = order["ordered_quantity"] - delivered_quantity
            discrepancy = final and missing > 0
            order.update({"delivered_quantity": delivered_quantity, "delivery_final": final,
                          "status": "DELIVERY_DISCREPANCY" if discrepancy else
                          "DELIVERED" if final else "PARTIALLY_DELIVERED", "updated_at": _now()})
            self._save("reference_merchant_orders", order)
            event = self._event("order.delivery_discrepancy" if discrepancy else "order.updated", order,
                                {"status": order["status"], "ordered_quantity": order["ordered_quantity"],
                                 "merchant_order_reference": external_order_ref,
                                 "delivered_quantity": delivered_quantity, "missing_quantity": missing,
                                 "delivery_final": final, "note": note}, request_id)
            return {"order": order, "event": event, "discrepancy": discrepancy,
                    "missing_quantity": missing, "money_moved": False}

        return self._mutate("delivery", idempotency_key, request_id,
                            {"external_order_ref": external_order_ref, "delivered_quantity": delivered_quantity,
                             "final": final, "note": note}, deliver)
