"""The Model Gateway as mounted on the real PeoplePay HTTP gateway (MOCK VERIFIED: deterministic providers)."""
from __future__ import annotations

import http.client
import json
import re
import threading
from http.server import ThreadingHTTPServer

import pytest

from peoplepay_models.adapters.mock import MockAdapter
from peoplepay_models.gateway import ModelGateway
from peoplepay_models.netguard import NetPolicy
from peoplepay_models.registry import default_registry
from peoplepay_models.store import ModelStore
from peoplepay_models.transport import FakeTransport

H = {"X-Beacon-User": "alice", "Content-Type": "application/json"}


@pytest.fixture
def served(monkeypatch):
    monkeypatch.delenv("BEACON_GATEWAY_SECRET", raising=False)
    import gateway.app as app

    MockAdapter.reset()
    made = []

    def start(mode="self_hosted"):
        gw = ModelGateway(store=ModelStore(), transport=FakeTransport(), registry=default_registry(enable_mock=True),
                          net_policy=NetPolicy(mode=mode))
        srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(app.GatewayState(capabilities={}, models=gw)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        made.append(srv)
        return gw, lambda: http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)

    yield start
    for s in made:
        s.shutdown(); s.server_close()
    MockAdapter.reset()


def call(conn, method, path, body=None, headers=H):
    c = conn()
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    r = c.getresponse()
    raw = r.read()
    c.close()
    return r.status, dict(r.getheaders()), raw


def test_pages_and_every_referenced_asset_are_served_with_csp(served):
    _, conn = served()
    for page in ("/ask", "/models"):
        st, hdr, raw = call(conn, "GET", page, headers={})
        assert st == 200 and "script-src 'self'" in hdr["Content-Security-Policy"]
        html = raw.decode()
        assets = re.findall(r'(?:src|href)="(/[^"#]+\.(?:js|css))"', html)
        assert assets
        for a in assets:
            assert call(conn, "GET", a, headers={})[0] == 200, a
        assert "style=" not in html and "onclick=" not in html and "<script>" not in html        # CSP-clean markup


def test_unauthenticated_api_is_rejected_and_health_is_open_and_minimal(served):
    _, conn = served()
    assert call(conn, "GET", "/api/v1/models/connections", headers={})[0] == 401
    assert call(conn, "POST", "/api/v1/chat", {"text": "x"}, headers={})[0] == 401
    st, _, raw = call(conn, "GET", "/health/models", headers={})
    body = json.loads(raw)
    assert st == 200 and set(body) >= {"providers_registered", "connected", "oldest_catalog_age_s"} and "display_name" not in raw.decode()


def test_connect_catalog_chat_switch_and_sse_over_http(served):
    gw, conn = served()
    st, _, raw = call(conn, "POST", "/api/v1/models/connections", {"provider_type": "mock", "display_name": "Demo", "values": {"models": [
        {"id": "m-a", "name": "A"}, {"id": "m-b", "name": "B", "vision": True}]}})
    assert st == 201 and json.loads(raw)["test"]["models_found"] == 2
    st, _, raw = call(conn, "GET", "/api/v1/models/catalog?q=m-b")
    assert [m["provider_model_id"] for m in json.loads(raw)["models"]] == ["m-b"]
    st, _, raw = call(conn, "POST", "/api/v1/chat", {"text": "one", "selection": {"mode": "model", "model": "m-a"}})
    r1 = json.loads(raw)
    st, _, raw = call(conn, "POST", "/api/v1/chat", {"text": "two", "conversation_id": r1["conversation_id"], "selection": {"mode": "model", "model": "m-b"}})
    assert json.loads(raw)["response"]["served_by"]["provider_model_id"] == "m-b"
    c = conn()
    c.request("POST", "/api/v1/chat", body=json.dumps({"text": "stream please", "stream": True}), headers=H)
    resp = c.getresponse()
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("text/event-stream")
    events = [json.loads(l[5:]) for l in resp.read().decode().split("\n\n") if l.startswith("data:")]
    assert events[0]["type"] == "response.started" and events[-1]["type"] == "response.completed" and any(e["type"] == "text.delta" for e in events)
    # a user cannot see another user's conversation or connection
    bob = {"X-Beacon-User": "bob", "Content-Type": "application/json"}
    assert json.loads(call(conn, "GET", "/api/v1/models/connections", headers=bob)[2])["connections"] == []
    assert call(conn, "GET", f"/api/v1/chat/conversations/{r1['conversation_id']}", headers=bob)[0] == 400


def test_client_disconnect_mid_stream_does_not_break_the_server(served):
    gw, conn = served()
    call(conn, "POST", "/api/v1/models/connections", {"provider_type": "mock", "display_name": "Demo", "values": {}})
    c = conn()
    c.request("POST", "/api/v1/chat", body=json.dumps({"text": "a b c d e f g h", "stream": True}), headers=H)
    r = c.getresponse(); r.read(40); c.close()          # the "stop" button: drop the connection
    assert call(conn, "GET", "/health/models", headers={})[0] == 200
    assert call(conn, "POST", "/api/v1/chat", {"text": "still alive"})[0] == 200


def test_cloud_deployment_refuses_credential_storage_without_verified_auth(served):
    gw, conn = served("cloud")
    st, _, raw = call(conn, "POST", "/api/v1/models/connections", {"provider_type": "openai", "display_name": "x", "values": {"api_key": "sk-TESTTESTTEST1234"}})
    assert st == 403 and "verified authentication" in raw.decode() and gw.store.list_connections() == []
    assert b"TESTTEST" not in raw


def test_models_api_errors_do_not_leak_internals(served):
    _, conn = served()
    st, _, raw = call(conn, "POST", "/api/v1/chat", {"text": "no providers"})
    body = json.loads(raw)
    assert st == 409 and body["error"]["code"] == "NO_ROUTE" and "Traceback" not in raw.decode()
