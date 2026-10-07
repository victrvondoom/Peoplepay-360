import json
import sqlite3

import pytest

import mg_fakes as fakes
from mg_helpers import FAST, add_mock
from peoplepay_models.bootstrap import register_env_connections
from peoplepay_models.adapters.decision import JevProvider, LayaProvider
from peoplepay_models.canonical import DecisionQuestion, InferenceRequest, Message, ModelSelection
from peoplepay_models.errors import ErrorCode, GatewayError, redact
from peoplepay_models.gateway import ModelGateway
from peoplepay_models.netguard import NetPolicy, validate_url
from peoplepay_models.registry import default_registry
from peoplepay_models.service import ModelsAPI
from peoplepay_models.store import ModelStore
from peoplepay_models.transport import FakeTransport
from peoplepay_models.vault import EncryptedSqliteVault, MemoryVault, VaultError, VaultUnavailable, generate_key, mask

KEY = "sk-LIVEKEY-abcdefghijklmnop"
U = "alice"


# ---------------------------------------------------------------- vault
def test_vault_encrypts_at_rest_and_binds_owner(tmp_path):
    v = EncryptedSqliteVault(tmp_path / "v.db", generate_key())
    ref = v.put("user:alice", {"api_key": KEY})
    raw = open(tmp_path / "v.db", "rb").read()
    assert KEY.encode() not in raw and b"LIVEKEY" not in raw
    assert v.reveal("user:alice", ref) == {"api_key": KEY}
    with pytest.raises(VaultError):
        v.reveal("user:bob", ref)                                  # other users cannot read it
    c = sqlite3.connect(tmp_path / "v.db")
    c.execute("UPDATE credentials SET owner='user:bob' WHERE ref=?", (ref,)); c.commit()
    with pytest.raises(VaultError):
        v.reveal("user:bob", ref)                                  # row moved to another owner: AAD fails authentication
    assert KEY not in repr(v) and mask(KEY) == "••••mnop" and mask("short") == "••••"


def test_vault_fails_closed_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("PEOPLEPAY_MODELS_VAULT_KEY", raising=False)
    monkeypatch.delenv("PEOPLEPAY_MODELS_VAULT_KEY_FILE", raising=False)
    with pytest.raises(VaultUnavailable):
        EncryptedSqliteVault(tmp_path / "v.db")


def test_secrets_never_appear_in_any_gateway_output_or_store(tmp_path):
    store = ModelStore(str(tmp_path / "m.db"))
    gw = ModelGateway(store=store, vault=EncryptedSqliteVault(tmp_path / "v.db", generate_key()),
                      transport=FakeTransport(fakes.openai_like(models=("gpt-x",))), registry=default_registry(),
                      net_policy=NetPolicy(mode="self_hosted"))
    api = ModelsAPI(gw)
    seen = []
    st, out = api.handle("POST", ["api", "v1", "models", "connections"], "", {"provider_type": "openai", "display_name": "Mine", "values": {"api_key": KEY}}, U)
    seen.append(out); assert st == 201
    cid = out["connection"]["id"]
    for m, p in [("GET", ["connections"]), ("GET", ["catalog"]), ("GET", ["usage"]), ("GET", ["health"]), ("GET", ["preferences"]),
                 ("GET", ["preferences", "export"]), ("GET", ["providers"]), ("POST", ["connections", cid, "test"])]:
        seen.append(api.handle(m, ["api", "v1", "models", *p], "", {}, U)[1])
    seen.append(api.handle("POST", ["api", "v1", "chat"], "", {"text": "hi"}, U)[1])
    blob = json.dumps(seen, default=str)
    assert KEY not in blob and "LIVEKEY" not in blob
    assert out["connection"]["has_credential"] is True and "credential_ref" not in out["connection"]
    for dbfile in (tmp_path / "m.db", tmp_path / "v.db"):
        assert b"LIVEKEY" not in open(dbfile, "rb").read()


def test_bad_key_error_message_is_redacted(gw):
    gw.transport.handler = fakes.openai_like(fail_status=401)
    out = gw.connect(U, "openai", "x", {"api_key": KEY})
    assert out["test"]["ok"] is False
    assert KEY not in json.dumps(out) and "SECRETSECRET" not in json.dumps(out)


def test_redact_patterns():
    s = redact(f"Authorization: Bearer {KEY} x-api-key: abc12345 AKIAABCDEFGHIJKLMNOP ?api_key=zzzzzzzz&a=1 aws_secret_access_key=wJalrXUtnFEMI/K7")
    for leak in (KEY, "abc12345", "AKIAABCDEFGHIJKLMNOP", "zzzzzzzz", "wJalrXUtnFEMI"):
        assert leak not in s
    assert redact("hello world") == "hello world"


# ---------------------------------------------------------------- SSRF
@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data", "https://10.0.0.5/v1", "http://127.0.0.1:11434",
                                 "https://192.168.1.10", "http://[::1]:8000", "https://100.64.0.1", "http://0.0.0.0", "ftp://x.test",
                                 "https://user:pw@93.184.216.34/"])
def test_cloud_mode_blocks_internal_and_odd_urls(url):
    with pytest.raises(GatewayError) as ei:
        validate_url(url, NetPolicy(mode="cloud"))
    assert ei.value.code == ErrorCode.CUSTOM_ENDPOINT_BLOCKED


def test_cloud_mode_allows_public_https_and_dns_rebinding_to_private_is_blocked():
    host, port, ip = validate_url("https://93.184.216.34/v1", NetPolicy(mode="cloud"))
    assert ip == "93.184.216.34"
    rebind = lambda h, p, **k: [(2, 1, 6, "", ("10.1.2.3", p))]
    with pytest.raises(GatewayError):
        validate_url("https://innocent.example/v1", NetPolicy(mode="cloud"), resolver=rebind)
    meta = lambda h, p, **k: [(2, 1, 6, "", ("169.254.169.254", p))]
    with pytest.raises(GatewayError):
        validate_url("https://x.example", NetPolicy(mode="self_hosted"), resolver=meta)     # metadata blocked even self-hosted


def test_self_hosted_allows_loopback_and_cloud_mode_allowlist():
    validate_url("http://127.0.0.1:11434", NetPolicy(mode="self_hosted"))
    validate_url("http://127.0.0.1:11434", NetPolicy(mode="cloud", allowlist=frozenset({"127.0.0.1"})))


def test_connect_rejects_blocked_endpoint_before_storing_anything():
    gw = ModelGateway(store=ModelStore(), transport=FakeTransport(), registry=default_registry(), net_policy=NetPolicy(mode="cloud"))
    with pytest.raises(GatewayError) as ei:
        gw.connect(U, "openai_compatible", "evil", {"base_url": "http://169.254.169.254/v1", "api_key": "k"})
    assert ei.value.code == ErrorCode.CUSTOM_ENDPOINT_BLOCKED and gw.store.list_connections() == []
    with pytest.raises(GatewayError):
        gw.connect(U, "ollama", "laptop", {"base_url": "http://localhost:11434"})       # cloud backend cannot reach a laptop


def test_unknown_config_fields_are_dropped_not_stored(gw):
    out = gw.connect(U, "openai", "x", {"api_key": KEY, "evil": "1", "credential_ref": "cred_other"}, test=False)
    assert "evil" not in out["connection"]["configuration"] and out["connection"]["has_credential"]


# ---------------------------------------------------------------- bootstrap
def test_env_keys_become_system_connections_without_persisting_secrets(gw):
    env = {"OPENAI_API_KEY": KEY, "ANTHROPIC_API_KEY": "ant-KEYKEYKEY", "OPENROUTER_API_KEY": "or-KEYKEYKEY", "NVIDIA_API_KEY": "nv-KEYKEYKEY",
           "OLLAMA_HOST": "127.0.0.1:11434", "JEV_BASE_URL": "http://10.9.8.7", "JEV_API_KEY": "jv-KEYKEYKEY", "LAYA_BASE_URL": "http://10.9.8.8",
           "AWS_ACCESS_KEY_ID": "AKIAXXXXXXXXXXXXXXXX", "AWS_REGION": "us-west-2"}
    made = register_env_connections(gw, env)
    assert set(made) == {"sys_openai", "sys_anthropic", "sys_openrouter", "sys_nvidia_nim", "sys_bedrock", "sys_ollama", "sys_jev", "sys_laya"}
    dump = json.dumps([c.__dict__ for c in gw.store.list_connections()], default=str)
    assert "KEYKEYKEY" not in dump and "LIVEKEY" not in dump
    assert all(c.system for c in gw.connections(U))


def test_no_env_registers_only_default_local_ollama_when_self_hosted(gw):
    assert register_env_connections(gw, {}) == ["sys_ollama"]
    gw2 = ModelGateway(store=ModelStore(), transport=FakeTransport(), registry=default_registry(), net_policy=NetPolicy(mode="cloud"))
    assert register_env_connections(gw2, {}) == []


# ---------------------------------------------------------------- decision providers
def mkdec(cls, **kw):
    return cls("c", {"base_url": "http://10.9.8.9"}, {"api_key": "k"}, FakeTransport(fakes.decision_like(**kw)))


QS = [DecisionQuestion("q1", "BOOLEAN", "risky?"), DecisionQuestion("q2", "CHOICE", "which?", ["a", "b"]),
      DecisionQuestion("q3", "SCORE", "how much?", scale=(0, 1))]


@pytest.mark.parametrize("cls", [JevProvider, LayaProvider])
def test_decision_providers_share_canonical_structures(cls):
    p = mkdec(cls)
    assert p.manifest.type.value == "DECISION" and p.manifest.kind == "decision"
    routes = p.discover_models()
    assert routes[0].kind == "decision" and routes[0].capabilities.has(__import__("peoplepay_models").Capability.DECISION_BOOLEAN)
    ans = p.decide("d1", {"x": 1}, QS)
    assert [a.kind for a in ans] == ["BOOLEAN", "CHOICE", "SCORE"] and ans[1].value == "a" and ans[0].confidence == 0.9
    assert not hasattr(p, "generate") and not hasattr(p, "stream")      # no prose-generation surface at all


def test_decision_provider_rejects_invalid_answers():
    with pytest.raises(GatewayError) as ei:
        mkdec(JevProvider, bad=True).decide("d1", {}, QS)
    assert ei.value.code == ErrorCode.INVALID_RESPONSE
    with pytest.raises(GatewayError):
        mkdec(LayaProvider).decide("d1", {}, [DecisionQuestion("q", "CHOICE", "p")])      # CHOICE without choices
    # unreported confidence is None, never invented
    assert mkdec(JevProvider, confidence=None).decide("d1", {}, QS[:1])[0].confidence is None


def test_decision_models_are_not_chat_routes_and_cannot_be_selected_for_prose(gw):
    gw.transport.handler = fakes.decision_like()
    out = gw.connect(U, "jev", "JEV", {"base_url": "http://10.9.8.7", "api_key": "k"})
    assert out["test"]["ok"]
    cat = gw.list_models(U)["models"]
    assert cat and all(m["selectable_as_chat"] is False for m in cat if m["provider_id"] == "jev")
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, InferenceRequest(messages=[Message.user("write me an essay")], selection=ModelSelection("model", "d1")))
    assert ei.value.code == ErrorCode.NO_ROUTE


def test_fast_path_then_escalation(gw):
    gw.transport.handler = fakes.decision_like(confidence=0.95)
    gw.connect(U, "jev", "JEV", {"base_url": "http://10.9.8.7", "api_key": "k"})
    add_mock(gw, U, "Gen", [FAST])
    esc = lambda: InferenceRequest(messages=[Message.user("explain")])
    r = gw.decide_or_escalate(U, QS[:1], {}, esc())
    assert r["path"] == "fast_decision" and not r["escalated"]
    gw.transport.handler = fakes.decision_like(confidence=0.2)
    r = gw.decide_or_escalate(U, QS[:1], {}, esc())
    assert r["path"] == "escalated" and r["response"]["text"] and "threshold" in r["reason"]
    gw.transport.handler = fakes.decision_like(confidence=None)             # unreported confidence => escalate, never assume
    assert gw.decide_or_escalate(U, QS[:1], {}, esc())["escalated"]


def test_local_only_decide_refuses_cloud_decision_provider(gw):
    gw.transport.handler = fakes.decision_like()
    gw.connect(U, "jev", "JEV", {"base_url": "http://10.9.8.7", "api_key": "k"})
    with pytest.raises(GatewayError):
        gw.decide(U, {}, QS[:1], local_only=True)


# ---------------------------------------------------------------- HTTP API surface
def test_api_roundtrip_connect_discover_chat_switch_inspect(gw):
    gw.transport.handler = fakes.openai_like(models=("gpt-a", "gpt-b"))
    api = ModelsAPI(gw)
    call = lambda m, p, b=None, q="": api.handle(m, p.split("/"), q, b or {}, U)
    st, out = call("POST", "api/v1/models/connections", {"provider_type": "openai", "display_name": "Mine", "values": {"api_key": KEY}})
    assert st == 201 and out["test"]["ok"] and out["test"]["models_found"] == 2
    st, cat = call("GET", "api/v1/models/catalog", q="q=gpt-b")
    assert [m["provider_model_id"] for m in cat["models"]] == ["gpt-b"]
    st, r1 = call("POST", "api/v1/chat", {"text": "hello", "selection": {"mode": "model", "model": "gpt-a"}})
    st, r2 = call("POST", "api/v1/chat", {"text": "again", "conversation_id": r1["conversation_id"], "selection": {"mode": "model", "model": "gpt-b"}})
    st, conv = call("GET", f"api/v1/chat/conversations/{r1['conversation_id']}")
    assert [m["served_by"]["provider_model_id"] for m in conv["messages"] if m["served_by"]] == ["gpt-a", "gpt-b"]
    st, sw = call("POST", "api/v1/models/switch-check", {"conversation_id": r1["conversation_id"], "selection": {"mode": "model", "model": "gpt-a"}})
    assert st == 200 and "Future replies" in sw["message"]
    st, ex = call("POST", "api/v1/models/explain", {"text": "hi"})
    assert ex["selected"] and "excluded" in ex
    st, e = call("POST", "api/v1/chat", {"text": ""})
    assert st == 400 and e["error"]["code"] == "INVALID_REQUEST"
    st, e = call("POST", "api/v1/chat", {"text": "x", "selection": {"mode": "bogus"}})
    assert st == 400
    st, _ = call("POST", f"api/v1/models/connections/{out['connection']['id']}/remove")
    assert st == 200 and call("GET", f"api/v1/chat/conversations/{r1['conversation_id']}")[1]["messages"][1]["served_by"]["provider_model_id"] == "gpt-a"


def test_api_sse_stream_and_cancel(gw):
    add_mock(gw, U, "A")
    st, stream = ModelsAPI(gw).handle("POST", ["api", "v1", "chat"], "", {"text": "one two three", "stream": True}, U)
    evs = list(stream)
    assert st == 200 and evs[0].type == "response.started" and evs[-1].type == "response.completed"
    st, stream = ModelsAPI(gw).handle("POST", ["api", "v1", "chat"], "", {"text": "one two three", "stream": True}, U)
    it = iter(stream); next(it); stream.cancel()
    assert list(it) == []


def test_api_error_codes_are_canonical_and_sanitized(gw):
    add_mock(gw, U, "A", script={"fail": ["RATE_LIMITED"]})
    gw.set_prefs(U, {"fallback_mode": "NONE"})
    st, e = ModelsAPI(gw).handle("POST", ["api", "v1", "chat"], "", {"text": "hi"}, U)
    assert st == 429 and e["error"]["code"] == "RATE_LIMITED" and "rate limited" in e["error"]["message"]
    assert "Traceback" not in json.dumps(e)


def test_preferences_endpoint_rejects_junk(gw):
    api = ModelsAPI(gw)
    st, e = api.handle("POST", ["api", "v1", "models", "preferences"], "", {"routing_policy": "NOPE"}, U)
    assert st == 400
    st, p = api.handle("POST", ["api", "v1", "models", "preferences"], "", {"routing_policy": "FASTEST", "admin": True}, U)
    assert "admin" not in p["preferences"]


def test_extension_client_requests_capability_not_vendor(gw):
    from peoplepay_models.client import ModelsClient
    from peoplepay_models.canonical import ImagePart
    from mg_helpers import VISION, DEEP
    add_mock(gw, U, "A", [FAST, VISION, DEEP])
    c = ModelsClient(gw, U, source="ext:greenchain")
    assert c.generate("vision.analyze", "what?", images=[ImagePart("image/png", "AAAA")]).served_by.provider_model_id in ("m-vision", "m-deep")
    assert c.generate("reasoning.deep", "think").served_by.provider_model_id == "m-deep"
    with pytest.raises(GatewayError):
        c.generate("vision.analyze", "no image")
    with pytest.raises(GatewayError):
        c.generate("nonsense.cap", "x")


def test_capability_test_upgrades_evidence(gw):
    add_mock(gw, U, "A", [{"id": "plain", "name": "Plain"}], structured_reply={"nope": 1})
    cid = gw.connections(U)[0].id
    r = gw.test_capability(U, cid, "plain", __import__("peoplepay_models").Capability.STRUCTURED_OUTPUT)
    assert r["ok"] is False                       # mock replies non-schema text unless scripted: honest negative
    c = gw.store.get_connection(cid); c.configuration["structured_reply"] = {"ok": True}; gw.store.save_connection(c)
    r = gw.test_capability(U, cid, "plain", __import__("peoplepay_models").Capability.STRUCTURED_OUTPUT)
    assert r["ok"] and r["evidence"] == "capability_test"
    assert [x for x in gw.models.get(cid)][0].capabilities.items["structured_output"] == "capability_test"


def test_benchmark_harness_is_task_specific_and_deterministic(gw):
    from peoplepay_models.bench import run_benchmark
    add_mock(gw, U, "A")
    rows = run_benchmark(gw, U, ["m-fast"])
    assert {r["category"] for r in rows} == {"intent routing", "structured extraction", "evidence relevance"}
    assert all(r["ttft_ms"] is not None and r["total_ms"] >= 0 for r in rows)


def test_gateway_overhead_is_small(gw):
    import time
    add_mock(gw, U, "A")
    gw.infer(U, InferenceRequest(messages=[Message.user("warm")]))
    t = time.perf_counter()
    for _ in range(50):
        gw.infer(U, InferenceRequest(messages=[Message.user("hello")], selection=ModelSelection(one_shot=True)))
    per_call_ms = (time.perf_counter() - t) / 50 * 1000
    assert per_call_ms < 25, per_call_ms          # routing + normalisation + sqlite telemetry on a deterministic provider


def test_ephemeral_chat_saves_nothing(gw):
    add_mock(gw, U, "A")
    st, out = ModelsAPI(gw).handle("POST", ["api", "v1", "chat"], "", {"text": "compare me", "ephemeral": True, "selection": {"mode": "model", "model": "m-fast", "one_shot": True}}, U)
    assert st == 200 and out["response"]["text"] and "conversation_id" not in out and gw.store.list_conversations(U) == []


def test_runtime_builds_from_env_and_warms_system_connections(tmp_path):
    from peoplepay_models.runtime import build_from_env
    env = {"PEOPLEPAY_MODELS_ENABLE_MOCK": "1", "PEOPLEPAY_MODELS_DB": str(tmp_path / "m.db"), "PEOPLEPAY_DEPLOYMENT": "self_hosted",
           "PEOPLEPAY_MODELS_PROBE_LOCAL_OLLAMA": "0", "PEOPLEPAY_MODELS_DISABLED_PROVIDERS": "bedrock"}
    gw = build_from_env(env)
    gw.warm_thread.join(5)
    rows = {r["connection"]["id"]: r for r in gw.health_overview("anyone")}
    assert rows["sys_mock_cloud"]["status"] == "Connected" and rows["sys_mock_cloud"]["models_found"] == 3
    assert rows["sys_mock_local"]["provider"]["local"] is False       # the mock manifest is not local; the *route* is
    assert not gw.providers.is_enabled("bedrock") and gw.vault_status()["persistent"] is False
