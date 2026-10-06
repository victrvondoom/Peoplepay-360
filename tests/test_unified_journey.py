"""Actual Gateway HTTP -> ECHO HTTP -> FalkorDB procurement lifecycle.

Provider inputs replay captured native outputs; merchant and PROXY are labelled
reference simulators. No ECHO engine or graph is stubbed. Set
REQUIRE_JOURNEY_GRAPH=1 to make missing local infrastructure a hard failure.
The suite owns a UUID graph and temporary SQLite files only.
"""

from __future__ import annotations

import http.client
import json
import os
import queue
import subprocess
import threading
import time
from typing import Any
from collections import deque
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

from gateway.app import GatewayState, make_handler
from gateway.auth import issue_token
from gateway.merchant import ReferenceMerchant
from journey.models import REFERENCE_REQUIREMENT
from journey.service import EchoClient, JourneyService
from journey.store import JourneyStore
from transaction.sqlite_store import SqliteTransactionStore

ROOT = Path(__file__).resolve().parents[1]
ECHO_BOOTSTRAP = """
import socket
import uvicorn
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(2048)
print('PEOPLEPAY_TEST_PORT=' + str(sock.getsockname()[1]), flush=True)
config = uvicorn.Config('echo.api:app', log_level='warning')
uvicorn.Server(config).run(sockets=[sock])
"""


def _unavailable(reason):
    if os.getenv("REQUIRE_JOURNEY_GRAPH") == "1":
        pytest.fail(reason)
    pytest.skip(reason + "; REQUIRE_JOURNEY_GRAPH=1 requires this integration")


def _request(port, method, path, actor, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {issue_token(actor)}"}
    try:
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


@pytest.fixture(scope="module")
def echo_http():
    executables = [ROOT / ".venv-echo" / "Scripts" / "python.exe",
                   ROOT / ".venv-echo" / "bin" / "python"]
    executable = next((path for path in executables if path.is_file()), None)
    if executable is None:
        _unavailable("The isolated .venv-echo interpreter is absent")
    graph_name = "journey_test_" + uuid4().hex
    environment = dict(os.environ)
    environment.update({"ECHO_GRAPH_NAME": graph_name,
                        "BEACON_GATEWAY_SECRET": "journey-integration-test-secret-only"})
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("BEACON_GATEWAY_SECRET", environment["BEACON_GATEWAY_SECRET"])
        process = subprocess.Popen(
            [str(executable), "-u", "-c", ECHO_BOOTSTRAP], cwd=ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ports: queue.Queue[int] = queue.Queue()
        logs: deque[str] = deque(maxlen=100)
        assert process.stdout is not None
        process_output = process.stdout

        def read_output():
            for line in process_output:
                logs.append(line.rstrip())
                if line.startswith("PEOPLEPAY_TEST_PORT="):
                    ports.put(int(line.split("=", 1)[1]))

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            try:
                port = ports.get(timeout=15)
            except queue.Empty:
                _unavailable("ECHO failed to bind a test socket: " + "\n".join(logs))
            deadline = time.monotonic() + 25
            ready = False
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    # Exercise the first request on a new graph without a health
                    # probe creating it first. A missing journey is a normal404.
                    if not ready:
                        initial_status, _ = _request(port, "GET", "/echo/v1/journeys/journey-" + "0" * 32 + "/current", "health-probe")
                        assert initial_status == 404
                    status, health = _request(port, "GET", "/health", "health-probe")
                    ready = status == 200 and health.get("graph") is True and health.get("graph_name") == graph_name
                    if ready:
                        break
                except (OSError, ValueError, http.client.HTTPException):
                    pass
                time.sleep(0.05)
            if not ready:
                _unavailable("ECHO/FalkorDB was unavailable: " + "\n".join(logs))
            yield {"port": port, "origin": f"http://127.0.0.1:{port}", "graph_name": graph_name}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=2)
            process_output.close()
            # Delete only the generated test graph, never the configured user graph.
            if graph_name.startswith("journey_test_") and len(graph_name) == 45:
                cleanup = subprocess.run(
                    [str(executable), "-c",
                     "from echo.graph_store import EchoGraphStore; EchoGraphStore().graph.delete()"],
                    cwd=ROOT, env=environment, capture_output=True, text=True, timeout=15,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if ready and cleanup.returncode:
                    pytest.fail("Cannot remove the dedicated journey test graph: " + cleanup.stderr[-1000:])


class GatewayHarness:
    def __init__(self, directory, echo):
        self.directory = directory
        self.echo = echo
        self.start()

    def start(self):
        self.transactions = SqliteTransactionStore(self.directory / "transactions.sqlite3")
        self.journeys = JourneyStore(self.directory / "journeys.sqlite3")
        self.merchant = ReferenceMerchant(self.directory / "merchant.sqlite3")
        self.state = GatewayState(store=self.transactions, capabilities={})
        self.service = JourneyService(self.state, store=self.journeys, merchant=self.merchant,
                                      echo=EchoClient(self.echo["origin"]))
        self.state._journey = self.service
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.state))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.transactions.close()
        self.journeys.connection.close()
        self.merchant.close()

    def restart(self):
        self.close()
        self.start()

    def request(self, method, path, body=None, actor="buyer-a"):
        return _request(self.port, method, path, actor, body)

    def create(self, mode="reference"):
        status, result = self.request("POST", "/api/v1/journeys",
                                      {"requirement": deepcopy(REFERENCE_REQUIREMENT), "mode": mode})
        assert status == 201, result
        return result

    def approve(self, record, **overrides):
        decision = record["decision"]
        body = {"decision_hash": decision["decision_hash"], "decision_version": decision["decision_version"],
                "supplier_id": "supplier-b", "human_confirmation": True, "confirm_reference": True, **overrides}
        return self.request("POST", f"/api/v1/journeys/{record['id']}/approve", body)


@pytest.fixture
def gateway_http(tmp_path, echo_http):
    harness = GatewayHarness(tmp_path, echo_http)
    try:
        yield harness
    finally:
        harness.close()


def test_chairs_to_order_to_partial_delivery_to_preserved_dispute(gateway_http):
    gateway = gateway_http
    record = gateway.create()
    decision = record["decision"]
    assert decision["recommended_supplier_id"] == "supplier-b"
    assert decision["decision_version"] == 1
    assert decision["policy_outcome"] == "REFERENCE_ONLY"
    candidate = next(row for row in decision["candidates"] if row["supplier_id"] == "supplier-b")
    assert candidate["terms"]["quantity"] == 300
    assert candidate["terms"]["total_minor"] == 177000000
    assert candidate["evidence_ids"]
    assert {row["extension_id"] for row in decision["provider_receipts"]} == {"greenchain", "inflationforge"}
    assert len(decision["normalized_results"]) == 2
    assert next(row for row in decision["normalized_results"] if row["extension_id"] == "greenchain")["claims"]
    inflation = next(row for row in decision["normalized_results"] if row["extension_id"] == "inflationforge")
    assert not inflation["claims"]  # The native city basket does not cover chairs.
    assert any("NOT_TRACKED" in warning for warning in inflation["warnings"])
    assert len(decision["ingestion"]) == 2
    assert "MERCHANT_SIMULATOR_NO_MONEY_MOVED" in decision["warnings"]
    status, ordered = gateway.approve(record)
    assert status == 200, ordered
    assert ordered["phase"] == "ORDER_CREATED"
    assert ordered["checkout"]["status"] == "completed"
    assert ordered["order"]["external_order_ref"].startswith("reference-order-")
    assert ordered["order"]["money_moved"] is False
    assert ordered["approval"]["terms_hash"] == candidate["terms_hash"]
    assert ordered["approval"]["decision_hash"] == decision["decision_hash"]
    status, disputed = gateway.request("POST", f"/api/v1/journeys/{record['id']}/delivery",
                                       {"delivered_quantity": 260, "event_id": "delivery-260"})
    assert status == 200, disputed
    assert disputed["phase"] == "DISPUTE_DRAFT_READY"
    assert disputed["dispute"]["submitted"] is False
    assert disputed["dispute"]["requires_human_review"] is True
    bundle = disputed["dispute"]["bundle"]
    assert bundle["discrepancy"] == {"kind": "partial_delivery", "ordered_quantity": 300,
                                    "delivered_quantity": 260, "missing_quantity": 40}
    assert bundle["requirement"] == REFERENCE_REQUIREMENT
    assert bundle["decision"]["decision_hash"] == decision["decision_hash"]
    assert bundle["approved_terms"] == ordered["approval"]["terms"]
    assert bundle["merchant_order_reference"] == ordered["order"]["external_order_ref"]
    assert bundle["transaction_reference"] == record["transaction_id"]
    status, replay = gateway.request("POST", f"/api/v1/journeys/{record['id']}/delivery",
                                     {"delivered_quantity": 260, "event_id": "delivery-260"})
    assert status == 200
    assert replay["dispute"]["draft_id"] == disputed["dispute"]["draft_id"]
    assert len(gateway.merchant.get_events(bundle["merchant_order_reference"])) == 2
    gateway.restart()
    status, reloaded = gateway.request("GET", f"/api/v1/journeys/{record['id']}")
    assert status == 200
    assert reloaded["dispute_bundle"]["bundle_hash"] == bundle["bundle_hash"]
    status, explanation = gateway.request("GET", f"/api/v1/journeys/{record['id']}/explain")
    assert status == 200, explanation
    assert explanation["decision_hash"] == decision["decision_hash"]
    assert explanation["approved_terms"]["total_minor"] == 177000000
    assert gateway.transactions.get(record["transaction_id"]).ledger.verify_chain()[0] is True


def test_wrong_hash_false_confirmation_and_other_actor_never_authorize(gateway_http, echo_http):
    record = gateway_http.create()
    for overrides in ({"decision_hash": "0" * 64}, {"decision_version": 2},
                      {"human_confirmation": False}, {"confirm_reference": False},
                      {"supplier_id": "supplier-c"}):
        status, response = gateway_http.approve(record, **overrides)
        assert status == 409, response
        assert gateway_http.journeys.get(record["id"], "buyer-a")["order"] is None
    assert gateway_http.request("GET", f"/api/v1/journeys/{record['id']}", actor="buyer-b")[0] == 404
    assert gateway_http.request("GET", f"/api/v1/journeys/{record['id']}/explain", actor="buyer-b")[0] == 404
    assert gateway_http.request("POST", f"/api/v1/journeys/{record['id']}/approve", {}, actor="buyer-b")[0] == 404
    assert gateway_http.request("GET", "/api/v1/journeys", actor="buyer-b")[1]["journeys"] == []
    decision_id = record["decision"]["decision_id"]
    assert _request(echo_http["port"], "GET", f"/echo/v1/journeys/decisions/{decision_id}", "buyer-b")[0] == 404


def test_authoritative_repricing_blocks_order_then_new_decision_can_be_approved(gateway_http):
    record = gateway_http.create()
    item = next(row for row in gateway_http.merchant.get_catalog() if row["supplier_id"] == "supplier-b")
    gateway_http.merchant.set_catalog_item({**item, "unit_price_minor": 610000})
    status, blocked = gateway_http.approve(record)
    assert status == 200, blocked
    assert blocked["phase"] == "REAPPROVAL_REQUIRED"
    assert blocked["order"] is None
    assert blocked["checkout"]["external_order_ref"] is None
    assert blocked["checkout"]["requires_approval"] is True
    status, refreshed = gateway_http.request("POST", f"/api/v1/journeys/{record['id']}/refresh", {})
    assert status == 200, refreshed
    assert refreshed["decision"]["decision_version"] == 2
    assert refreshed["decision"]["decision_hash"] != record["decision"]["decision_hash"]
    old_approval = {"decision_hash": record["decision"]["decision_hash"], "decision_version": 1,
                    "supplier_id": "supplier-b", "human_confirmation": True, "confirm_reference": True}
    assert gateway_http.request("POST", f"/api/v1/journeys/{record['id']}/approve", old_approval)[0] == 409
    status, ordered = gateway_http.approve(refreshed)
    assert status == 200, ordered
    assert ordered["order"]["approved_terms"]["total_minor"] == 183000000
    assert ordered["order"]["decision_version"] == 2


def test_refresh_explains_current_changes_without_rewriting_approved_history(gateway_http):
    record = gateway_http.create()
    status, ordered = gateway_http.approve(record)
    assert status == 200, ordered
    original_decision = deepcopy(ordered["approved_decision"])
    original_order = deepcopy(ordered["order"])
    item = next(row for row in gateway_http.merchant.get_catalog() if row["supplier_id"] == "supplier-b")
    gateway_http.merchant.set_catalog_item({**item, "unit_price_minor": 630000})
    status, refreshed = gateway_http.request("POST", f"/api/v1/journeys/{record['id']}/refresh", {})
    assert status == 200, refreshed
    assert refreshed["approved_decision"] == original_decision
    assert refreshed["order"] == original_order
    terms_change = next(row for row in refreshed["changes"]["changes"]
                        if row.get("supplier_id") == "supplier-b" and row["field"] == "terms")
    assert terms_change["at_decision"]["total_minor"] == 177000000
    assert terms_change["current"]["total_minor"] == 189000000
    assert refreshed["changes"]["historical_snapshot_preserved"] is True
    status, explanation = gateway_http.request("GET", f"/api/v1/journeys/{record['id']}/explain")
    assert status == 200
    assert explanation["decision_hash"] == original_decision["decision_hash"]
    assert explanation["candidate"]["terms"]["total_minor"] == 177000000
    assert gateway_http.approve(refreshed)[0] == 409


def test_missing_live_provider_origins_fail_without_reference_fallback(gateway_http, monkeypatch):
    monkeypatch.delenv("PEOPLEPAY_GREENCHAIN_API_URL", raising=False)
    monkeypatch.delenv("PEOPLEPAY_INFLATIONFORGE_API_URL", raising=False)
    status, result = gateway_http.request("POST", "/api/v1/journeys",
                                         {"requirement": REFERENCE_REQUIREMENT, "mode": "live"})
    assert status == 503, result
    preserved = gateway_http.journeys.list("buyer-a")[0]
    assert preserved["mode"] == "live"
    assert preserved["phase"] == "EVIDENCE_BLOCKED"
    assert preserved["decision"] is None
    assert preserved["order"] is None


def test_cancelled_transaction_cannot_authorize_a_new_journey_order(gateway_http):
    record = gateway_http.create()
    status, _ = gateway_http.request("POST", f"/transactions/{record['transaction_id']}/cancel", {})
    assert status == 200
    status, refused = gateway_http.approve(record)
    assert status == 409 and "cancelled" in refused["error"]
    assert gateway_http.journeys.get(record["id"], "buyer-a")["order"] is None


def test_gateway_stale_writes_cannot_erase_another_workers_order(tmp_path):
    first, second = JourneyStore(tmp_path / "cas.sqlite3"), JourneyStore(tmp_path / "cas.sqlite3")
    record: dict[str, Any] = {"id": "journey-1", "actor_id": "owner", "order": None}
    try:
        first.put(record)
        stale = second.get(record["id"], "owner")
        record["order"] = {"id": "external-order"}
        first.put(record)
        with pytest.raises(ValueError, match="concurrently"):
            second.put(stale)
        assert second.get(record["id"], "owner")["order"]["id"] == "external-order"
    finally:
        first.connection.close()
        second.connection.close()


def test_proxy_ambiguous_failure_keeps_bundle_and_blocks_duplicate_native_case(gateway_http):
    gateway = gateway_http
    record = gateway.create()
    assert gateway.approve(record)[0] == 200
    calls = []
    def fail(bundle, actor):
        calls.append(bundle["bundle_hash"])
        raise RuntimeError("native provider lost response")
    gateway.service.proxy_factory = fail
    payload = {"delivered_quantity": 260, "event_id": "ambiguous-native-handoff"}
    assert gateway.request("POST", f"/api/v1/journeys/{record['id']}/delivery", payload)[0] == 503
    retained = gateway.journeys.get(record["id"], "buyer-a")
    assert retained["dispute_bundle"]["discrepancy"]["missing_quantity"] == 40
    assert retained["proxy_requires_reconciliation"]
    assert gateway.request("POST", f"/api/v1/journeys/{record['id']}/delivery", payload)[0] == 503
    assert len(calls) == 1
    assert gateway.request("POST", f"/api/v1/journeys/{record['id']}/retry-dispute", {})[0] == 503
    assert len(calls) == 1


def test_dispute_retry_http_route_preserves_bundle_and_enforces_owner_and_no_overrides(gateway_http, monkeypatch):
    gateway = gateway_http
    record = gateway.create()
    assert gateway.approve(record)[0] == 200
    monkeypatch.setenv("PEOPLEPAY_PROXY_API_URL", "http://127.0.0.1:65530")
    monkeypatch.delenv("PEOPLEPAY_PROXY_SESSION_FILE", raising=False)
    path = f"/api/v1/journeys/{record['id']}"
    assert gateway.request("POST", path + "/delivery", {"delivered_quantity": 260, "event_id": "retained-delivery"})[0] == 503
    retained = gateway.journeys.get(record["id"], "buyer-a")
    assert not retained.get("proxy_handoff_started")
    assert gateway.request("POST", path + "/retry-dispute", {}, actor="buyer-b")[0] == 404
    assert gateway.request("POST", path + "/retry-dispute", {"bundle": "override"})[0] == 409
    monkeypatch.delenv("PEOPLEPAY_PROXY_API_URL")
    status, ready = gateway.request("POST", path + "/retry-dispute", {})
    assert status == 200, ready
    assert ready["dispute"]["bundle_hash"] == retained["dispute_bundle"]["bundle_hash"]
    assert ready["dispute"]["submitted"] is False
    assert ready["phase"] == "DISPUTE_DRAFT_READY"
    assert len(gateway.merchant.get_events(ready["order"]["external_order_ref"])) == 2


def test_journey_storage_failure_is_a_sanitized_503(gateway_http, monkeypatch):
    import sqlite3
    record = gateway_http.create()
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("sensitive-store-location")
    monkeypatch.setattr(gateway_http.journeys, "get", unavailable)
    status, response = gateway_http.request("GET", f"/api/v1/journeys/{record['id']}")
    assert status == 503
    assert "sensitive-store-location" not in str(response)
