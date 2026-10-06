"""Coordinator fault injection; the merchant, Gateway ledger and stores are real.

The ECHO contract double isolates crash recovery from graph availability. The
separate unified-journey suite exercises the real HTTP/FalkorDB decision engine.
"""

from copy import deepcopy
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from beacon.assurance import EventKind
from beacon.peoplepay.transaction import Transaction
from gateway.app import GatewayState
from gateway.merchant import ReferenceMerchant
from journey.models import REFERENCE_REQUIREMENT, digest
from journey.service import EchoClient, JourneyService, JourneyUnavailable
from journey.store import JourneyStore
from transaction.store import InMemoryTransactionStore


class EchoContract:
    def __init__(self):
        self.calls = []
        self.decisions = {}

    def request(self, method, path, actor, authorization, body=None):
        self.calls.append((method, path))
        if method == "GET":
            if path.endswith("/current"):
                raise KeyError("no uncommitted decision")
            return deepcopy(self.decisions[path.rsplit("/", 1)[1]])
        if path.endswith("/approve"):
            decision = self.decisions[path.split("/")[-2]]
            candidate = next(item for item in decision["candidates"] if item["supplier_id"] == body["supplier_id"])
            return {"action_id": "approval-" + decision["decision_id"], "actor_id": actor,
                    "transaction_id": decision["transaction_id"], "decision_id": decision["decision_id"],
                    "decision_version": decision["decision_version"], "decision_hash": decision["decision_hash"],
                    "terms": deepcopy(candidate["terms"]), "terms_hash": candidate["terms_hash"],
                    "mode": "reference", "money_moved": False}
        decision = make_decision(body["transaction_id"], body["version"], body["merchant_quotes"], body["providers"])
        self.decisions[decision["decision_id"]] = deepcopy(decision)
        return decision


def make_decision(transaction_id, version, quotes, providers=None):
    decision = {"decision_id": f"decision-{version}", "decision_version": version,
            "actor_id": "owner", "requirement": deepcopy(REFERENCE_REQUIREMENT), "transaction_id": transaction_id,
            "recommended_supplier_id": "supplier-b", "policy_outcome": "REFERENCE_ONLY",
            "evaluated_at": "2026-10-05T12:00:00+00:00", "warnings": ["REFERENCE_ONLY"],
            "provider_receipts": providers or [], "normalized_results": [],
            "candidates": [{"supplier_id": quote["supplier_id"], "supplier_name": quote["supplier_id"],
                            "terms": quote, "terms_hash": digest(quote), "raw_provider_score": 75.0,
                            "echo_score": 70.0, "policy_violations": [], "eligible": True}
                           for quote in quotes]}
    decision["decision_hash"] = digest(decision)
    return decision


@pytest.fixture
def seeded(tmp_path):
    transactions = InMemoryTransactionStore()
    gateway = GatewayState(store=transactions, capabilities={})
    merchant = ReferenceMerchant(tmp_path / "merchant.sqlite3")
    store = JourneyStore(tmp_path / "journeys.sqlite3")
    echo = EchoContract()
    service = JourneyService(gateway, store=store, merchant=merchant, echo=echo)
    txn = Transaction.create(user_id="owner", raw_utterance=str(REFERENCE_REQUIREMENT["description"]), actor="gateway:owner")
    transactions.put(txn)
    quotes = [merchant.quote(item["supplier_id"], item["product_id"], 300, 200000000, 30)
              for item in merchant.get_catalog()]
    decision = make_decision(txn.transaction_id, 1, quotes)
    echo.decisions[decision["decision_id"]] = deepcopy(decision)
    record = {"id": "journey-" + "1" * 32, "actor_id": "owner", "transaction_id": txn.transaction_id,
              "mode": "reference", "requirement": deepcopy(REFERENCE_REQUIREMENT), "phase": "AWAITING_APPROVAL",
              "decisions": [{"id": decision["decision_id"], "version": 1, "hash": decision["decision_hash"]}],
              "decision": decision, "approval": None, "checkout": None, "order": None,
              "delivery_event": None, "dispute": None, "last_error": None}
    store.put(record)
    try:
        yield service, record, echo
    finally:
        store.connection.close()
        merchant.close()


def approve_body(record):
    return {"decision_hash": record["decision"]["decision_hash"], "decision_version": 1,
            "supplier_id": "supplier-b", "human_confirmation": True, "confirm_reference": True}


def fail_gateway_order_checkpoint(monkeypatch, service):
    put = service.store.put
    failed = False

    def interrupted(record):
        nonlocal failed
        if record.get("order") and not failed:
            failed = True
            raise sqlite3.OperationalError("injected failure after merchant order commit")
        return put(record)

    monkeypatch.setattr(service.store, "put", interrupted)


def test_refresh_recovers_committed_order_before_advancing_decision(seeded, monkeypatch):
    service, record, _ = seeded
    fail_gateway_order_checkpoint(monkeypatch, service)
    with pytest.raises(sqlite3.OperationalError):
        service.approve(record["id"], "owner", approve_body(record), None)
    retained = service.store.get(record["id"], "owner")
    assert retained["order"] is None and retained["approval"]
    committed = service.merchant.get_order_for_transaction("owner", record["transaction_id"])
    assert committed
    refreshed = service.refresh(record["id"], "owner", None)
    assert refreshed["order"] == committed
    assert refreshed["approval"]["decision_version"] == 1
    assert refreshed["approved_decision"]["decision_version"] == 1
    assert refreshed["decision"]["decision_version"] == 2
    assert refreshed["phase"] == "ORDER_CREATED"
    assert len(service.merchant.get_events(committed["external_order_ref"])) == 1
    assert service.explain(record["id"], "owner", None)["decision_version"] == 1


def test_approval_retry_recovers_exact_order_without_echo_or_duplicate_authorization(seeded, monkeypatch):
    service, record, echo = seeded
    fail_gateway_order_checkpoint(monkeypatch, service)
    with pytest.raises(sqlite3.OperationalError):
        service.approve(record["id"], "owner", approve_body(record), None)
    def unavailable(*args, **kwargs):
        raise JourneyUnavailable("ECHO offline after persisted human approval")
    monkeypatch.setattr(echo, "request", unavailable)
    recovered = service.approve(record["id"], "owner", approve_body(record), None)
    assert recovered["order"]["decision_version"] == 1
    events = service.gateway.store.get(record["transaction_id"]).ledger.events
    assert len([item for item in events if item.kind is EventKind.AUTHORIZATION_GRANTED]) == 1
    assert len([item for item in events if item.kind is EventKind.CHECKOUT_OBSERVED]) == 1
    assert recovered["order"]["money_moved"] is False


@pytest.mark.parametrize("changed", [{"decision_version": True}, {"extra": "ignored-before"}, {"decision_hash": "bad"}])
def test_completed_order_retry_still_validates_strict_approval_input(seeded, changed):
    service, record, _ = seeded
    service.approve(record["id"], "owner", approve_body(record), None)
    with pytest.raises(ValueError):
        service.approve(record["id"], "owner", {**approve_body(record), **changed}, None)


def test_recovery_rejects_mismatched_order_binding_and_other_owner(seeded, monkeypatch):
    service, record, _ = seeded
    fail_gateway_order_checkpoint(monkeypatch, service)
    with pytest.raises(sqlite3.OperationalError):
        service.approve(record["id"], "owner", approve_body(record), None)
    getter = service.merchant.get_order_for_transaction
    def mismatched(actor, transaction_id):
        return {**getter(actor, transaction_id), "decision_hash": "f" * 64}
    monkeypatch.setattr(service.merchant, "get_order_for_transaction", mismatched)
    with pytest.raises(ValueError, match="sealed approval"):
        service.approve(record["id"], "owner", approve_body(record), None)
    with pytest.raises(KeyError):
        service.approve(record["id"], "intruder", approve_body(record), None)
    assert service.store.get(record["id"], "owner")["order"] is None


def test_proxy_missing_configuration_can_retry_retained_bundle_without_duplicate_delivery(seeded, monkeypatch):
    service, record, _ = seeded
    monkeypatch.setenv("PEOPLEPAY_PROXY_API_URL", "http://127.0.0.1:65530")
    monkeypatch.delenv("PEOPLEPAY_PROXY_SESSION_FILE", raising=False)
    service.approve(record["id"], "owner", approve_body(record), None)
    with pytest.raises(JourneyUnavailable, match="draft retry is safe"):
        service.delivery(record["id"], "owner", {"delivered_quantity": 260, "event_id": "delivery-once"})
    pending = service.store.get(record["id"], "owner")
    assert pending["dispute_bundle"]["discrepancy"]["missing_quantity"] == 40
    assert not pending.get("proxy_handoff_started")
    assert not pending.get("proxy_requires_reconciliation")
    with pytest.raises(KeyError):
        service.retry_dispute(record["id"], "intruder")
    monkeypatch.delenv("PEOPLEPAY_PROXY_API_URL")
    ready = service.retry_dispute(record["id"], "owner")
    assert ready["phase"] == "DISPUTE_DRAFT_READY"
    assert ready["last_error"] is None
    assert ready["dispute"]["bundle_hash"] == pending["dispute_bundle"]["bundle_hash"]
    assert len(service.merchant.get_events(ready["order"]["external_order_ref"])) == 2
    assert service.retry_dispute(record["id"], "owner")["dispute"]["draft_id"] == ready["dispute"]["draft_id"]


@pytest.mark.parametrize("status,raw", [(409, b"[]"), (200, b'"string"'), (200, b"\xff")])
def test_echo_malformed_error_and_invalid_utf8_are_bounded_unavailability(status, raw):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(JourneyUnavailable):
            EchoClient(f"http://127.0.0.1:{server.server_port}").request("GET", "/decision", "owner", None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
