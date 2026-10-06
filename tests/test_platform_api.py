import http.client
import json
import threading
from http.server import ThreadingHTTPServer

from gateway.app import GatewayState, make_handler
from tests.test_platform_workflow import engine


def test_workflow_api_enforces_actor_ownership_and_replay():
    state = GatewayState(capabilities={})
    state._workflow_engine = engine()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def request(method, path, body=None, actor=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            conn.request(method, path, json.dumps(body) if body is not None else None,
                {"Content-Type": "application/json", **({"X-Beacon-User": actor} if actor else {})})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()
    try:
        assert request("GET", "/api/v1/extensions")[0] == 401
        status, record = request("POST", "/api/v1/workflows", {"intent": "price context", "jurisdiction": "US",
            "steps": [{"capability": "price.observe", "input": {"product": "chairs"}}]}, "owner")
        assert status == 201
        path = "/api/v1/workflows/" + record["id"]
        assert request("GET", path, actor="other")[0] == 404
        status, evaluated = request("POST", path+"/run", {"event_id": "event-run"}, "owner")
        assert status == 200 and evaluated["state"] == "REVIEW_REQUIRED"
        assert request("POST", path+"/run", {"event_id": "event-run"}, "owner")[1] == evaluated
        assert request("POST", path+"/approve", {"decision_id": "forged", "version": 1, "scope_hash": "forged", "event_id": "event-approve"}, "owner")[0] == 409
        catalog = request("GET", "/api/v1/extensions", actor="other")[1]
        assert "last_invocation" not in catalog["extensions"][0]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
