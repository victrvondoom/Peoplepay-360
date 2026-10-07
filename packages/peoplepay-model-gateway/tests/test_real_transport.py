"""Exercises the real HttpTransport against a local stub server (MOCK VERIFIED: the server is ours,
not a live provider). Covers the pinned-IP connection, NDJSON/SSE streaming, redirects, and offline detection."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from peoplepay_models.canonical import Message, ModelSelection, InferenceRequest
from peoplepay_models.errors import ErrorCode, GatewayError
from peoplepay_models.gateway import ModelGateway
from peoplepay_models.netguard import NetPolicy
from peoplepay_models.registry import default_registry
from peoplepay_models.store import ModelStore
from peoplepay_models.transport import HttpTransport

U = "alice"


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json", extra=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(raw)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path == "/api/tags": return self._send(200, {"models": [{"name": "qwen:7b"}]})
        if self.path == "/redir": return self._send(302, b"", extra={"Location": "http://169.254.169.254/"})
        self._send(404, {})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/show": return self._send(200, {"capabilities": ["completion"]})
        if self.path == "/api/chat":
            lines = [json.dumps({"message": {"content": w}}) for w in ("local ", "answer")] + [json.dumps({"done": True, "prompt_eval_count": 4, "eval_count": 2})]
            if body.get("stream"): return self._send(200, ("\n".join(lines) + "\n").encode(), "application/x-ndjson")
            return self._send(200, {"message": {"content": "local answer"}, "done": True, "prompt_eval_count": 4, "eval_count": 2})
        self._send(404, {})


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def make_gw(mode="self_hosted"):
    return ModelGateway(store=ModelStore(), transport=HttpTransport(NetPolicy(mode=mode)), registry=default_registry(),
                        net_policy=NetPolicy(mode=mode))


def test_local_ollama_discovery_and_inference_over_real_http(server):
    gw = make_gw()
    out = gw.connect(U, "ollama", "Local", {"base_url": f"http://127.0.0.1:{server}"})
    assert out["test"]["ok"] and out["test"]["models_found"] == 1
    gw.set_prefs(U, {"local_only": True})
    r = gw.infer(U, InferenceRequest(messages=[Message.user("hi")]))
    assert r.text == "local answer" and r.served_by.route == "Local (Ollama)" and r.usage.input_tokens == 4
    ev = list(gw.chat_stream(U, "hi"))
    assert "".join(e.data["text"] for e in ev if e.type == "text.delta") == "local answer" and ev[-1].type == "response.completed"


def test_cloud_backend_cannot_reach_loopback_ollama(server):
    gw = make_gw("cloud")
    with pytest.raises(GatewayError) as ei:
        gw.connect(U, "ollama", "Laptop", {"base_url": f"http://127.0.0.1:{server}"})
    assert ei.value.code == ErrorCode.CUSTOM_ENDPOINT_BLOCKED


def test_offline_local_provider_is_reported_not_silently_cloud():
    gw = make_gw()
    out = gw.connect(U, "ollama", "Dead", {"base_url": "http://127.0.0.1:9"})        # nothing listens on port 9
    assert out["test"]["ok"] is False
    gw.set_prefs(U, {"local_only": True})
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, InferenceRequest(messages=[Message.user("hi")]))
    assert ei.value.extra.get("ask_privacy_change")


def test_redirects_are_not_followed(server):
    t = HttpTransport(NetPolicy(mode="self_hosted"))
    resp = t.request("GET", f"http://127.0.0.1:{server}/redir")
    assert resp.status == 302                  # surfaced as-is; never followed to the metadata address
