"""Regression tests for the defects found in the October 2026 audit.

Each test was written against a reproduction of the defect and fails on the code before its fix. They use mock and fake
providers only: nothing here claims a live provider works.
"""
import base64
import json
import threading
import time

import pytest

from mg_fakes import openai_like
from mg_helpers import FAST, add_mock, calls
from peoplepay_models import limits
from peoplepay_models.adapters.mock import MockAdapter
from peoplepay_models.canonical import (Conversation, DataClass, InferenceRequest, Message, ModelSelection,
                                        ProviderConnection)
from peoplepay_models.errors import ErrorCode, GatewayError
from peoplepay_models.gateway import ModelGateway
from peoplepay_models.netguard import NetPolicy
from peoplepay_models.registry import default_registry
from peoplepay_models.service import ModelsAPI
from peoplepay_models.store import ModelStore
from peoplepay_models.transport import FakeTransport
from peoplepay_models.vault import EncryptedSqliteVault, MemoryVault, generate_key

U = "alice"
SECRET = "sk-LIVE-HEADER-SECRET-123456"
PRICED = dict(FAST, pricing={"input_per_mtok": 1000.0, "output_per_mtok": 1000.0})


def req(text="hi", **kw):
    return InferenceRequest(messages=[Message.user(text)], selection=kw.pop("selection", ModelSelection()), **kw)


def make_gw(*, mode="self_hosted", vault=None, store=None, allowlist=frozenset(), handler=None):
    MockAdapter.reset()
    return ModelGateway(store=store or ModelStore(), vault=vault or MemoryVault(), transport=FakeTransport(handler),
                        registry=default_registry(enable_mock=True), net_policy=NetPolicy(mode=mode, allowlist=allowlist))


# ====================================================================== custom header secrets
def test_custom_header_values_are_vaulted_never_stored_in_plaintext_or_returned():
    gw = make_gw(handler=openai_like(("m1",)))
    out = gw.connect(U, "openai_compatible", "mine", {"base_url": "http://127.0.0.1:9/v1",
                                                      "headers": {"x-api-key": SECRET, "X-Org": "acme"}}, test=False)
    cid = out["connection"]["id"]
    for surface in (json.dumps(out), json.dumps(gw.health_overview(U)), json.dumps([c.public() for c in gw.connections(U)])):
        assert SECRET not in surface and "acme" not in surface
    assert out["connection"]["configuration"]["header_names"] == ["X-Org", "x-api-key"]      # names only
    assert SECRET not in json.dumps([c.__dict__ for c in gw.store.list_connections()], default=str)   # not in the database row
    gw.refresh_models(U, cid)
    gw.chat(U, "hi", selection=ModelSelection("model", "m1"))
    sent = [c for c in gw.transport.calls if c["url"].endswith("/chat/completions")][-1]["headers"]
    assert sent["x-api-key"] == SECRET and sent["X-Org"] == "acme"                           # the provider still gets them


def test_invalid_custom_headers_are_refused_without_echoing_their_value():
    gw = make_gw()
    for bad in ({"Bad Name": "v"}, {"X-A": "line\r\nbreak"}, {f"X-{i}": "v" for i in range(11)}, ["x"], {"X-A": ["list"]}):
        with pytest.raises(GatewayError) as e:
            gw.connect(U, "openai_compatible", "x", {"base_url": "http://127.0.0.1:9/v1", "headers": bad}, test=False)
        assert e.value.code == ErrorCode.INVALID_REQUEST and "line" not in str(e.value.to_dict())


def test_updating_a_connection_cannot_set_what_creating_one_drops_and_keeps_headers_vaulted():
    gw = make_gw()
    cid = gw.connect(U, "openai_compatible", "m", {"base_url": "http://127.0.0.1:9/v1"}, test=False)["connection"]["id"]
    gw.update_connection(U, cid, values={"headers": {"x-api-key": SECRET}, "route_label": "Direct (OpenAI)",
                                         "script": {"fail": ["RATE_LIMITED"]}, "local": True})
    row = gw.store.get_connection(cid)
    assert not {"headers", "route_label", "script", "local"} & set(row.configuration)
    assert SECRET not in json.dumps(row.public())
    assert json.loads(gw.vault.reveal(row.owner_scope, row.credential_ref)["__headers__"]) == {"x-api-key": SECRET}
    gw.update_connection(U, cid, values={"models_endpoint": "/models"})                       # an unrelated update keeps them
    row = gw.store.get_connection(cid)
    assert json.loads(gw.vault.reveal(row.owner_scope, row.credential_ref)["__headers__"]) == {"x-api-key": SECRET}
    gw.update_connection(U, cid, values={"headers": {}})                                      # and an empty object clears them
    row = gw.store.get_connection(cid)
    assert json.loads(gw.vault.reveal(row.owner_scope, row.credential_ref)["__headers__"]) == {}


def test_legacy_plaintext_headers_are_redacted_and_migrated_into_a_persistent_vault(tmp_path):
    pytest.importorskip("cryptography")
    store = ModelStore(str(tmp_path / "models.db"))
    store.save_connection(ProviderConnection(id="conn_legacy", provider_type="openai_compatible", display_name="old",
                                             owner_scope="user:alice",
                                             configuration={"base_url": "http://127.0.0.1:9/v1", "headers": {"x-api-key": SECRET}}))
    # An in-memory vault forgets on restart, so nothing may be moved into it -- but the value is still never returned.
    volatile = make_gw(store=store, handler=openai_like(("m1",)))
    assert store.get_connection("conn_legacy").configuration["headers"] == {"x-api-key": SECRET}
    assert SECRET not in json.dumps(volatile.connections(U)[0].public())
    # A persistent vault takes it, durably, before the plaintext is removed.
    vault = EncryptedSqliteVault(tmp_path / "vault.db", generate_key())
    gw = make_gw(store=store, vault=vault, handler=openai_like(("m1",)))
    row = store.get_connection("conn_legacy")
    assert "headers" not in row.configuration and row.credential_ref
    assert json.loads(vault.reveal("user:alice", row.credential_ref)["__headers__"]) == {"x-api-key": SECRET}
    assert gw.migrate_legacy_secrets() == 0                                                   # idempotent
    gw.refresh_models(U, "conn_legacy")
    gw.chat(U, "hi", selection=ModelSelection("model", "m1"))
    assert [c for c in gw.transport.calls if c["url"].endswith("/chat/completions")][-1]["headers"]["x-api-key"] == SECRET


# ====================================================================== daily cost limit
def test_daily_cost_limit_refuses_the_call_before_it_is_made(gw):
    cid = add_mock(gw, U, "P", [PRICED])
    gw.set_prefs(U, {"daily_cost_limit": 0.0001})
    with pytest.raises(GatewayError) as e:
        gw.infer(U, req())
    assert e.value.code == ErrorCode.QUOTA_EXHAUSTED and "daily cost limit" in str(e.value.to_dict())
    assert calls(cid) == 0 and gw.store.usage_rows(U) == []                                   # no provider call, no spend


def test_the_cap_bites_once_recorded_spend_reaches_it(gw):
    cid = add_mock(gw, U, "P", [PRICED])
    gw.set_prefs(U, {"daily_cost_limit": 0.05})
    served = 0
    for _ in range(50):
        try:
            gw.infer(U, req("hi", max_output_tokens=10))
            served += 1
        except GatewayError as e:
            assert e.code == ErrorCode.QUOTA_EXHAUSTED
            break
    else:
        pytest.fail("the daily cost limit never took effect")
    assert 1 <= served < 50 and calls(cid) == served


def test_the_cap_governs_streaming_too(gw):
    add_mock(gw, U, "P", [PRICED])
    gw.set_prefs(U, {"daily_cost_limit": 0.0})
    events = list(gw.stream(U, InferenceRequest(messages=[Message.user("hi")], stream=True)))
    assert [e.type for e in events] == ["error"] and events[0].data["code"] == "QUOTA_EXHAUSTED"


def test_free_local_routes_are_never_capped_and_a_capped_cloud_route_falls_back_to_them(gw):
    cloud = add_mock(gw, U, "cloud", [PRICED])
    local = add_mock(gw, U, "local", [{"id": "loc", "name": "L"}], local=True)
    gw.set_prefs(U, {"daily_cost_limit": 0.0, "preferred_routes": [gw.models.get(cloud)[0].key]})
    resp = gw.infer(U, req())
    assert resp.served_by.connection_id == local and calls(cloud) == 0
    assert any(a.status == "skipped" and "daily cost limit" in a.reason for a in resp.attempts)


def test_a_paid_route_with_no_known_price_is_refused_while_a_cap_is_set(gw):
    add_mock(gw, U, "unpriced", [FAST])
    assert gw.infer(U, req()).text                                                            # no cap: served as before
    gw.set_prefs(U, {"daily_cost_limit": 5.0})
    with pytest.raises(GatewayError) as e:
        gw.infer(U, req())
    assert e.value.code == ErrorCode.QUOTA_EXHAUSTED and "cannot be enforced" in str(e.value.to_dict())


def test_a_failed_attempt_does_not_leak_its_reservation(gw):
    cid = add_mock(gw, U, "P", [PRICED], script={"fail": ["SERVER_ERROR"]})
    gw.set_prefs(U, {"daily_cost_limit": 0.02, "fallback_mode": "NONE"})      # one worst-case call (0.014) fits, two do not
    with pytest.raises(GatewayError) as e:
        gw.infer(U, req(max_output_tokens=10))
    assert e.value.code == ErrorCode.SERVER_ERROR
    assert gw.infer(U, req(max_output_tokens=10)).text                          # refused if the failed attempt still held 0.014
    assert calls(cid) == 2


def test_concurrent_requests_cannot_all_pass_the_same_cap_check(gw, monkeypatch):
    add_mock(gw, U, "P", [PRICED])
    gw.set_prefs(U, {"daily_cost_limit": 0.035, "fallback_mode": "NONE"})      # worst case 0.014 each: two fit, a third does not
    inside, gate, results = [], threading.Event(), []
    original = MockAdapter.generate

    def slow(self, spec):
        inside.append(1)
        gate.wait(10)
        return original(self, spec)
    monkeypatch.setattr(MockAdapter, "generate", slow)

    def worker():
        try:
            gw.infer(U, req(max_output_tokens=10))
            results.append("ok")
        except GatewayError as e:
            results.append(e.code.value)
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(200):                                                        # the refused two return immediately
        if len(results) >= 2:
            break
        time.sleep(0.02)
    try:
        assert results.count("QUOTA_EXHAUSTED") == 2 and len(inside) == 2
    finally:
        gate.set()
        for t in threads:
            t.join(10)
    assert results.count("ok") == 2


# ====================================================================== duplicate failure accounting
def _failing_midstream(monkeypatch, code=ErrorCode.SERVER_ERROR):
    from peoplepay_models.canonical import StreamEvent

    def broken(self, spec):
        yield StreamEvent("response.started", {})
        yield StreamEvent("text.delta", {"text": "partial "})
        raise GatewayError(code, "boom mid-stream")
    monkeypatch.setattr(MockAdapter, "stream", broken)


def test_a_failure_after_output_has_started_is_counted_exactly_once(gw, monkeypatch):
    cid = add_mock(gw, U, "S", [FAST])
    _failing_midstream(monkeypatch)
    events = list(gw.stream(U, InferenceRequest(messages=[Message.user("hi")], stream=True)))
    assert events[-1].type == "error"
    assert len(events[-1].data["attempts"]) == 1                               # was 2: the same failure recorded twice
    assert gw.health_mgr._conn[cid].consecutive_failures == 1                  # was 2, which marked the connection DEGRADED
    assert gw.health_mgr.snapshot(cid)["state"] == "HEALTHY"
    assert len(gw.store.usage_rows(U)) == 1 and gw.metrics["errors.mock"] == 1


def test_two_real_failures_still_degrade_the_connection(gw, monkeypatch):
    cid = add_mock(gw, U, "S", [FAST])
    _failing_midstream(monkeypatch)
    for _ in range(2):
        list(gw.stream(U, InferenceRequest(messages=[Message.user("hi")], stream=True)))
    assert gw.health_mgr.snapshot(cid)["state"] == "DEGRADED"


def test_a_rate_limit_after_output_backs_off_once_not_twice(gw, monkeypatch):
    cid = add_mock(gw, U, "S", [FAST])
    _failing_midstream(monkeypatch, ErrorCode.RATE_LIMITED)
    list(gw.stream(U, InferenceRequest(messages=[Message.user("hi")], stream=True)))
    assert gw.health_mgr.snapshot(cid)["rate_limit_count"] == 1                # the cooldown doubles with each count


# ====================================================================== preferences
@pytest.mark.parametrize("patch", [
    {"favorites": 5}, {"favorites": [["x"]]}, {"favorites": ["x"] * 201}, {"aliases": "nope"}, {"aliases": {"a": 1}},
    {"model_tiers": []}, {"model_tiers": {"m": "huge"}}, {"max_attempts": "lots"}, {"max_attempts": 0}, {"max_attempts": True},
    {"daily_cost_limit": "free"}, {"daily_cost_limit": float("nan")}, {"daily_cost_limit": float("inf")},
    {"daily_cost_limit": -5}, {"daily_cost_limit": True}, {"preferred_routes": 3}, {"local_only": "yes"},
    {"routing_policy": "NOPE"}, {"routing_policy": None}, {"fallback_mode": 1}, {"context_strategy": "forget"},
    {"internal_models": 7}, {"default_model": ["a"]}])
def test_malformed_preferences_are_refused_and_nothing_is_saved(gw, patch):
    add_mock(gw, U, "A", [FAST])
    before = gw.get_prefs(U)
    with pytest.raises(GatewayError) as e:
        gw.set_prefs(U, patch)
    assert e.value.code == ErrorCode.INVALID_REQUEST and next(iter(patch)) in e.value.to_dict()["detail"]
    assert gw.get_prefs(U) == before
    assert gw.infer(U, req()).text                                             # and the user can still use the gateway


def test_valid_preferences_round_trip_including_clearing(gw):
    add_mock(gw, U, "A", [FAST])
    good = {"routing_policy": "FASTEST", "fallback_mode": "ASK", "local_only": False, "favorites": ["a::b"], "max_attempts": 3,
            "daily_cost_limit": 2.5, "default_model": "", "model_tiers": {"a::b": "deep"}, "context_strategy": "ask"}
    assert gw.set_prefs(U, good) == good
    assert gw.set_prefs(U, {"daily_cost_limit": None})["daily_cost_limit"] is None
    assert gw.import_prefs(U, gw.export_prefs(U))["routing_policy"] == "FASTEST"       # export -> import is accepted


def test_preferences_already_poisoned_in_storage_cannot_break_requests_and_heal_on_next_write(gw):
    add_mock(gw, U, "A", [FAST])
    gw.store.save_prefs(U, {"favorites": 5, "preferred_routes": 3, "daily_cost_limit": "x", "local_only": "yes",
                            "routing_policy": "NOPE", "max_attempts": True, "aliases": "nope", "default_model": "keep-me-not"})
    assert gw.list_models(U)["models"] and gw.infer(U, req()).text            # used to raise TypeError on every request
    assert {k: v for k, v in gw.get_prefs(U).items() if k != "recent"} == {"default_model": "keep-me-not"}   # valid survive, invalid dropped
    gw.set_prefs(U, {"routing_policy": "FASTEST"})
    healed = {k: v for k, v in gw.store.get_prefs(U).items() if k != "recent"}
    assert healed == {"default_model": "keep-me-not", "routing_policy": "FASTEST"}                          # and the store is clean again


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/v1/models/preferences", ["x"]),
    ("POST", "/api/v1/models/preferences/import", {"preferences": ["x"]}),
    ("POST", "/api/v1/models/connections", {"provider_type": "mock", "display_name": "x", "values": "zz"}),
    ("POST", "/api/v1/models/connections/c/update", {"values": "zz"}),
    ("POST", "/api/v1/models/decide", {"questions": "x"}),
    ("POST", "/api/v1/models/decide", {"questions": [1]}),
    ("POST", "/api/v1/chat", {"text": "hi", "max_output_tokens": -5}),
    ("POST", "/api/v1/chat", {"text": "hi", "max_output_tokens": True}),
    ("POST", "/api/v1/chat", {"text": "hi", "selection": {"model": 123}}),
    ("POST", "/api/v1/chat", {"text": "hi", "conversation_id": 7}),
    ("POST", "/api/v1/chat", {"text": "hi", "attachments": "x"})])
def test_malformed_requests_get_a_400_not_a_crash(gw, method, path, body):
    status, out = ModelsAPI(gw).handle(method, path.strip("/").split("/"), "", body, U)
    assert status == 400 and out["error"]["code"] == "INVALID_REQUEST"


def test_an_unexpected_exception_answers_500_and_leaks_nothing(gw, monkeypatch):
    def boom(owner, since=None):
        raise RuntimeError("secret internal detail /srv/app/db.py")
    monkeypatch.setattr(gw, "usage", boom)
    status, out = ModelsAPI(gw).handle("GET", ["api", "v1", "models", "usage"], "", {}, U)
    assert status == 500 and out["error"]["code"] == "SERVER_ERROR" and "secret internal detail" not in json.dumps(out)


# ====================================================================== attachment limits
def _b64(n):
    return base64.b64encode(b"\0" * n).decode()


def _image(n, media_type="image/png"):
    return {"kind": "image", "media_type": media_type, "data_b64": _b64(n)}


def _chat(api, attachments):
    return api.handle("POST", ["api", "v1", "chat"], "", {"text": "hi", "attachments": attachments, "ephemeral": True}, U)[0]


def test_attachment_limits_are_enforced_at_the_service_layer(gw):
    add_mock(gw, U, "V", [dict(FAST, vision=True)])
    api = ModelsAPI(gw)
    assert _chat(api, [_image(1000)]) == 200
    assert _chat(api, [_image(limits.MAX_IMAGE_BYTES)]) == 200                                # exactly at the limit
    assert _chat(api, [_image(limits.MAX_IMAGE_BYTES + 1)]) == 400                            # used to be accepted at 30 MiB
    assert _chat(api, [_image(3 * 1024 * 1024)] * 3) == 400                                   # 9 MiB in total
    assert _chat(api, [_image(10)] * (limits.MAX_ATTACHMENTS + 1)) == 400
    assert _chat(api, [_image(10, "image/svg+xml")]) == 400
    assert _chat(api, [{"kind": "image", "media_type": "image/png", "data_b64": "!!not base64!!"}]) == 400
    assert _chat(api, [{"kind": "image", "media_type": "image/png", "data_b64": 12345}]) == 400
    assert _chat(api, ["x"]) == 400


def test_the_http_body_limit_is_derived_from_the_same_numbers_the_service_validates():
    assert limits.MAX_MODEL_BODY_BYTES >= limits.base64_length(limits.MAX_ATTACHMENT_BYTES_TOTAL)
    assert limits.MAX_MODEL_BODY_BYTES >= limits.base64_length(limits.MAX_IMAGE_BYTES) + 4096   # one max image + text fits
    assert len(_b64(limits.MAX_IMAGE_BYTES)) == limits.base64_length(limits.MAX_IMAGE_BYTES)


# ====================================================================== privacy classification and labels
def test_a_conversation_never_drops_below_the_highest_data_class_it_has_held(gw):
    cloud = add_mock(gw, U, "cloud", [FAST])
    local = add_mock(gw, U, "local", [{"id": "loc", "name": "L"}], local=True)
    first = gw.chat(U, "my passport number is X1234567", data_class=DataClass.SENSITIVE)
    assert first["response"]["served_by"]["connection_id"] == local
    cid = first["conversation_id"]
    assert gw.get_conversation(U, cid).data_class == DataClass.SENSITIVE
    gw.set_prefs(U, {"preferred_routes": [gw.models.get(cloud)[0].key]})                       # even if the user prefers the cloud
    second = gw.chat(U, "continue", conversation_id=cid, data_class=DataClass.PUBLIC)         # a lower class is declared
    assert second["response"]["served_by"]["connection_id"] == local                           # the history is still SENSITIVE
    assert gw.get_conversation(U, cid).data_class == DataClass.SENSITIVE


def test_the_ratchet_holds_when_streaming_and_only_ever_rises(gw):
    cloud = add_mock(gw, U, "cloud", [FAST])
    local = add_mock(gw, U, "local", [{"id": "loc", "name": "L"}], local=True)
    gw.set_prefs(U, {"preferred_routes": [gw.models.get(cloud)[0].key]})
    first = gw.chat(U, "hello", data_class=DataClass.INTERNAL)
    assert first["response"]["served_by"]["connection_id"] == cloud                            # INTERNAL may use the cloud
    cid = first["conversation_id"]
    done = [e for e in gw.chat_stream(U, "now something private", conversation_id=cid, data_class=DataClass.SENSITIVE)
            if e.type == "response.completed"][0]
    assert done.data["response"]["served_by"]["connection_id"] == local
    later = [e for e in gw.chat_stream(U, "and a public question", conversation_id=cid, data_class=DataClass.PUBLIC)
             if e.type == "response.completed"][0]
    assert later.data["response"]["served_by"]["connection_id"] == local                       # raised once, never lowered
    assert gw.get_conversation(U, cid).data_class == DataClass.SENSITIVE


def test_conversations_saved_before_the_watermark_existed_still_load():
    assert Conversation.from_dict({"id": "c", "messages": []}).data_class == DataClass.INTERNAL
    assert Conversation.from_dict({"id": "c", "messages": [], "data_class": "garbage"}).data_class == DataClass.INTERNAL
    assert Conversation.from_dict(Conversation(owner="a", data_class=DataClass.RESTRICTED).to_dict()).data_class == DataClass.RESTRICTED


def test_a_user_cannot_relabel_a_route_or_script_a_provider(gw):
    c = gw.connect(U, "openai_compatible", "x", {"base_url": "http://127.0.0.1:9/v1", "manual_models": "m", "test": True,
                                                 "route_label": "Direct (OpenAI)", "script": {"fail": ["RATE_LIMITED"]},
                                                 "local": True}, test=False)["connection"]
    assert not {"route_label", "script", "local"} & set(c["configuration"])
    gw.refresh_models(U, c["id"])
    route = gw.models.get(c["id"])[0]
    assert route.route == "Custom endpoint" and route.local is False


@pytest.mark.parametrize("mode,url,declared,allow,expected", [
    ("self_hosted", "http://127.0.0.1:9/v1", "local", (), "local"),                    # loopback may be local
    ("self_hosted", "http://10.0.0.5:9/v1", "local", (), "organization"),              # private network: at most organization
    ("self_hosted", "http://93.184.216.34/v1", "local", (), "cloud"),                  # public: cloud however it is labelled
    ("self_hosted", "http://93.184.216.34/v1", "organization", (), "cloud"),
    ("self_hosted", "http://93.184.216.34/v1", "organization", ("93.184.216.34",), "organization"),   # admin vouched for it
    ("self_hosted", "http://93.184.216.34/v1", "cloud", (), "cloud"),                  # a user may always be more cautious
    ("self_hosted", "http://127.0.0.1:9/v1", "cloud", (), "cloud"),
    ("cloud", "https://93.184.216.34/v1", "organization", (), "cloud"),
    ("cloud", "https://93.184.216.34/v1", "local", (), "cloud")])
def test_a_declared_data_boundary_is_capped_by_where_the_endpoint_really_is(mode, url, declared, allow, expected):
    gw = make_gw(mode=mode, allowlist=frozenset(allow))
    c = gw.connect(U, "openai_compatible", "e", {"base_url": url, "privacy": declared, "manual_models": "m"}, test=False)["connection"]
    assert c["configuration"]["privacy"] == expected


def test_sensitive_data_is_never_routed_to_a_public_host_that_claims_to_be_the_organization():
    gw = make_gw()
    c = gw.connect(U, "openai_compatible", "claims-org", {"base_url": "http://93.184.216.34/v1", "privacy": "organization",
                                                          "manual_models": "m"}, test=False)["connection"]
    gw.refresh_models(U, c["id"])
    plan, _, _ = gw.plan(U, InferenceRequest(messages=[Message.user("x")], data_class=DataClass.SENSITIVE))
    assert plan.ordered == [] and any("privacy" in why for _, why in plan.excluded)


def test_updating_a_connection_cannot_loosen_its_boundary():
    gw = make_gw()
    cid = gw.connect(U, "openai_compatible", "e", {"base_url": "http://93.184.216.34/v1", "privacy": "cloud"}, test=False)["connection"]["id"]
    out = gw.update_connection(U, cid, values={"privacy": "local"})
    assert out["configuration"]["privacy"] == "cloud"
