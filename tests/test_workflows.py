"""Exercise persistent user workflows through real HTTP requests."""
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from gateway.app import GatewayState, make_handler
from transaction.sqlite_store import SqliteTransactionStore


def test_plan_validate_cancel_survive_reload(tmp_path, monkeypatch):
    monkeypatch.delenv("BEACON_GATEWAY_SECRET", raising=False)
    store = SqliteTransactionStore(tmp_path / "workflow.db")
    state = GatewayState(store=store, capabilities={})
    assert state.store is store
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(path, body=None):
        request = Request(
            f"http://127.0.0.1:{server.server_port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Beacon-User": "owner", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5) as response:
            assert b"PeoplePay Workspace" in response.read()
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        with pytest.raises(HTTPError) as missing:
            call("/../gateway/auth.py")
        assert missing.value.code == 404
        for utterance in (123, {"text": "Desk"}, ["Desk"]):
            with pytest.raises(HTTPError) as invalid:
                call("/transactions", {"raw_utterance": utterance})
            assert invalid.value.code == 400
        txn = call("/transactions", {"raw_utterance": "Desk under INR 1000"})
        route = "/transactions/" + txn["transaction_id"]
        assert call(route + "/timeline")["integrity"]["intact"]
        for suffix in ("/unknown", "/timeline/extra"):
            with pytest.raises(HTTPError) as missing_route:
                call(route + suffix)
            assert missing_route.value.code == 404
        call(route + "/plan", {
            "summary": "Desk", "steps": ["Compare desks"],
            "amount_minor": 110000, "currency": "INR",
        })
        validation = call(route + "/validate", {})
        assert not validation["valid"]
        assert any("budget" in problem for problem in validation["problems"])
        assert validation["payment_status"] == "NOT_CONFIGURED"
        assert call(route + "/evidence")["nodes"]
        cart = call(route + "/cart", {
            "items": [{"title": "Desk", "merchant": "Shop", "variant": "Standard",
                       "quantity": 1, "unit_price_minor": 50000}],
            "currency": "INR", "shipping_minor": 0, "tax_minor": 0,
        })["cart"]
        confirmation = {"cart_hash": cart["cart_hash"], "confirm_sandbox": True}
        order = call(route + "/sandbox-checkout", confirmation)["order"]
        assert call(route + "/sandbox-checkout", confirmation)["replayed"]
        with pytest.raises(HTTPError) as unavailable:
            call(route + "/checkout", confirmation)
        assert unavailable.value.code == 503
        request = Request(f"http://127.0.0.1:{server.server_port}{route}/context",
                          headers={"X-Beacon-User": "another-owner"})
        with pytest.raises(HTTPError) as denied:
            urlopen(request, timeout=5)
        assert denied.value.code == 404
        call(route + "/delivery", {"status": "SHIPPED", "note": "Manual entry"})
        call(route + "/dispute", {"issue": "Damage reported", "remedy": "Replace"})
        call(route + "/cancel", {})
        assert call(route)["state"] == "CANCELLED"
        with SqliteTransactionStore(tmp_path / "workflow.db") as reopened:
            loaded = reopened.get(txn["transaction_id"])
            assert loaded.plan is not None
            assert loaded.plan["summary"] == "Desk"
            assert loaded.context["fulfillment"]["order"]["order_id"] == order["order_id"]
            assert not loaded.context["fulfillment"]["dispute"]["submitted"]
            assert len(loaded.graph.nodes) >= 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        store.close()
