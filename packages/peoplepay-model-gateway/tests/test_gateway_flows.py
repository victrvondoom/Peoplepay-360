"""End-to-end gateway behaviour on deterministic mock providers (MOCK VERIFIED)."""
import pytest

from mg_helpers import DEEP, FAST, VISION, add_mock, calls
from peoplepay_models import CancelToken
from peoplepay_models.adapters.mock import MockAdapter
from peoplepay_models.canonical import (Capability as C, Conversation, DataClass, FallbackMode, ImagePart, InferenceRequest, Message,
                                        ModelSelection, RoutingPolicy, TextPart, ToolDefinition, ToolCallPart)
from peoplepay_models.errors import ErrorCode, GatewayError

U = "alice"
IMG = ImagePart("image/png", "AAAA")


def req(text="hi", **kw):
    sel = kw.pop("selection", ModelSelection())
    return InferenceRequest(messages=[Message.user(text)], selection=sel, **kw)


# ---------------------------------------------------------------- switching / conversation
def test_conversation_survives_switching_models_and_records_served_by(gw):
    a = add_mock(gw, U, "A", [{"id": "model-a", "name": "A"}])
    b = add_mock(gw, U, "B", [{"id": "model-b", "name": "B"}])
    r1 = gw.chat(U, "first", selection=ModelSelection("model", "model-a"))
    cid = r1["conversation_id"]
    r2 = gw.chat(U, "second", conversation_id=cid, selection=ModelSelection("model", "model-b"))
    conv = gw.get_conversation(U, cid)
    assert [m.role for m in conv.messages] == ["user", "assistant", "user", "assistant"]
    assert conv.messages[1].served_by.provider_model_id == "model-a" and conv.messages[3].served_by.provider_model_id == "model-b"
    assert conv.messages[1].served_by.connection_id == a and conv.messages[3].served_by.connection_id == b
    assert "first" in conv.messages[0].text                      # history intact
    assert gw.check_switch(U, cid, ModelSelection("model", "model-a"))["message"].startswith("Future replies will use")


def test_conversation_is_owner_scoped(gw):
    add_mock(gw, U, "A")
    cid = gw.chat(U, "secret plans")["conversation_id"]
    with pytest.raises(GatewayError):
        gw.get_conversation("mallory", cid)


def test_switch_to_text_only_with_images_warns_and_blocks_without_consent(gw):
    add_mock(gw, U, "T", [{"id": "text-only", "name": "T"}])
    add_mock(gw, U, "V", [VISION])
    cid = gw.chat(U, "look", attachments=[IMG], selection=ModelSelection("model", "m-vision"))["conversation_id"]
    chk = gw.check_switch(U, cid, ModelSelection("model", "text-only"))
    assert not chk["ok"] and chk["warnings"][0]["code"] == "IMAGES_UNSUPPORTED"
    assert chk["warnings"][0]["alternatives"]
    # explicit text-only pick: auto-routing sees the vision requirement and refuses to use the text-only model...
    r = gw.chat(U, "and now?", conversation_id=cid, selection=ModelSelection("model", "text-only"))
    assert r["response"]["served_by"]["provider_model_id"] == "m-vision"        # capable model chosen, not a silent image drop
    assert "image" not in r["response"]["text"].lower() or "saw" in r["response"]["text"]


def test_image_to_text_only_only_blocked_with_consent_flow(gw):
    add_mock(gw, U, "T", [{"id": "text-only", "name": "T"}])
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, InferenceRequest(messages=[Message("user", [TextPart("see"), IMG])], selection=ModelSelection("model", "text-only")))
    assert ei.value.code == ErrorCode.UNSUPPORTED_CAPABILITY and ei.value.extra.get("needs_consent") == "drop_images"
    ok = gw.infer(U, InferenceRequest(messages=[Message("user", [TextPart("see"), IMG])], selection=ModelSelection("model", "text-only"),
                                      metadata={"allow_drop_unsupported": True}))
    assert any("omitted" in n for n in ok.notes) and "saw" not in ok.text      # the model never received the image


def test_removed_model_keeps_history_reference(gw):
    cid_conn = add_mock(gw, U, "A", [{"id": "gone", "name": "Gone"}, {"id": "stay", "name": "Stay"}])
    cid = gw.chat(U, "x", selection=ModelSelection("model", "gone"))["conversation_id"]
    MockAdapter.reset()
    c = gw.store.get_connection(cid_conn); c.configuration["models"] = [{"id": "stay", "name": "Stay"}]; gw.store.save_connection(c)
    gw.refresh_models(U, cid_conn)
    gone = [r for r in gw.models.get(cid_conn) if r.provider_model_id == "gone"][0]
    assert gone.availability == "unavailable"
    assert gw.get_conversation(U, cid).messages[1].served_by.provider_model_id == "gone"
    assert all(m["provider_model_id"] != "gone" for m in gw.list_models(U)["models"])


# ---------------------------------------------------------------- fallback
def test_rate_limit_falls_back_once_with_metadata_and_cooldown(gw):
    a = add_mock(gw, U, "Primary", [{"id": "p", "name": "P", "context": 100000}], script={"fail": ["RATE_LIMITED"]}, retry_after=45)
    b = add_mock(gw, U, "Backup", [{"id": "b", "name": "B", "context": 100000}])
    gw.set_prefs(U, {"preferred_routes": [f"{a}::p"]})
    resp = gw.infer(U, req())
    assert resp.served_by.provider_model_id == "b" and resp.served_by.fallback_reason == "RATE_LIMITED"
    assert [x.status for x in resp.attempts] == ["error", "ok"]
    assert any("Fallback used" in e for e in resp.routing_explanation)
    assert gw.health_mgr.connection_state(a).value == "RATE_LIMITED"
    # cooldown: primary is not hammered again
    assert gw.infer(U, req()).served_by.provider_model_id == "b"
    assert len([x for x in gw.infer(U, req()).attempts if x.route_key.startswith(a)]) == 0


def test_cooldown_expires_with_injected_clock():
    from conftest import Clock
    from peoplepay_models.health import HealthManager
    clk = Clock(); h = HealthManager(clk)
    h.record_failure("c", "c::m", GatewayError(ErrorCode.RATE_LIMITED, "x", retry_after=60))
    assert h.blocked("c", "c::m")[0]
    clk.advance(61)
    assert not h.blocked("c", "c::m")[0]
    h.record_success("c", "c::m", 5.0)
    assert h.connection_state("c").value == "HEALTHY"


def test_no_fallback_mode_raises(gw):
    add_mock(gw, U, "P", [{"id": "p", "name": "P"}], script={"fail": ["RATE_LIMITED"]})
    add_mock(gw, U, "B", [{"id": "b", "name": "B"}])
    gw.set_prefs(U, {"preferred_routes": [r.key for r in gw.models.get(gw.connections(U)[0].id)]})
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req(fallback_mode=FallbackMode.NONE))
    assert ei.value.code == ErrorCode.RATE_LIMITED


def test_ask_mode_returns_proposal_not_silent_switch(gw):
    a = add_mock(gw, U, "P", [{"id": "p", "name": "P"}], script={"fail": ["PROVIDER_UNAVAILABLE"]})
    add_mock(gw, U, "B", [{"id": "b", "name": "B"}])
    gw.set_prefs(U, {"preferred_routes": [f"{a}::p"]})
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req(fallback_mode=FallbackMode.ASK))
    assert ei.value.extra["ask_before_switching"] and ei.value.extra["alternatives"]


def test_non_eligible_errors_do_not_fall_back(gw):
    a = add_mock(gw, U, "P", [{"id": "p", "name": "P"}], script={"fail": ["INVALID_REQUEST"]})
    add_mock(gw, U, "B", [{"id": "b", "name": "B"}])
    gw.set_prefs(U, {"preferred_routes": [f"{a}::p"]})
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req())
    assert ei.value.code == ErrorCode.INVALID_REQUEST


def test_fallback_never_loops_and_is_bounded(gw):
    ids = [add_mock(gw, U, f"P{i}", [{"id": f"m{i}", "name": f"M{i}"}], script={"fail": ["TIMEOUT"] * 5}) for i in range(5)]
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req())
    att = ei.value.extra["attempts"]
    assert len(att) <= 3 and len({a["route_key"] for a in att}) == len(att)       # hard maximum, no route repeated


def test_fallback_requires_same_capabilities(gw):
    a = add_mock(gw, U, "V", [VISION], script={"fail": ["RATE_LIMITED"]})
    add_mock(gw, U, "T", [{"id": "text-only", "name": "T"}])
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, InferenceRequest(messages=[Message("user", [TextPart("see"), IMG])]))
    assert ei.value.code == ErrorCode.RATE_LIMITED                # text-only model never offered as a fallback for vision


def test_cancellation_stops_future_fallback(gw):
    add_mock(gw, U, "P", [{"id": "p", "name": "P"}], script={"fail": ["RATE_LIMITED"]})
    add_mock(gw, U, "B", [{"id": "b", "name": "B"}])
    tok = CancelToken(); tok.cancel()
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req(), cancel=tok)
    assert ei.value.code == ErrorCode.CANCELLED


def test_low_cost_fallback_does_not_jump_to_expensive_or_unknown_price(gw):
    cheap = {"id": "cheap", "name": "Cheap", "pricing": {"input_per_mtok": 0.1, "output_per_mtok": 0.2}}
    pricey = {"id": "pricey", "name": "Pricey", "pricing": {"input_per_mtok": 10, "output_per_mtok": 50}}
    unknown = {"id": "unknown", "name": "Unknown"}
    add_mock(gw, U, "A", [cheap], script={"fail": ["RATE_LIMITED"]})
    add_mock(gw, U, "B", [pricey, unknown])
    with pytest.raises(GatewayError):
        gw.infer(U, req(routing_policy=RoutingPolicy.LOW_COST))


# ---------------------------------------------------------------- privacy / local only
def test_local_only_never_touches_cloud(gw):
    cloud = add_mock(gw, U, "Cloud", [{"id": "c", "name": "C"}])
    loc = add_mock(gw, U, "Local", [{"id": "l", "name": "L"}], local=True)
    gw.set_prefs(U, {"local_only": True})
    resp = gw.infer(U, req())
    assert resp.served_by.provider_model_id == "l" and resp.served_by.route.startswith("Local")
    assert calls(cloud) == 0                              # cloud provider was never invoked


def test_local_only_with_local_offline_does_not_use_cloud_and_asks_user(gw):
    cloud = add_mock(gw, U, "Cloud", [{"id": "c", "name": "C"}])
    loc = add_mock(gw, U, "Local", [{"id": "l", "name": "L"}], local=True)
    gw.set_prefs(U, {"local_only": True})
    c = gw.store.get_connection(loc); c.configuration["offline"] = True; gw.store.save_connection(c)
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req())
    assert ei.value.code == ErrorCode.LOCAL_PROVIDER_OFFLINE
    assert calls(cloud) == 0


def test_local_only_no_local_provider_asks_to_change_privacy_mode(gw):
    add_mock(gw, U, "Cloud", [{"id": "c", "name": "C"}])
    gw.set_prefs(U, {"local_only": True})
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req())
    assert ei.value.extra["ask_privacy_change"] is True


def test_sensitive_data_excluded_from_cloud_and_no_auto_fallback(gw):
    add_mock(gw, U, "Cloud", [{"id": "c", "name": "C"}])
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req(data_class=DataClass.RESTRICTED))
    assert ei.value.code == ErrorCode.PRIVACY_POLICY_BLOCKED
    loc = add_mock(gw, U, "Local", [{"id": "l", "name": "L"}], local=True, script={"fail": ["TIMEOUT"]})
    # sensitive data + automatic fallback is downgraded to ASK
    add_mock(gw, U, "Local2", [{"id": "l2", "name": "L2"}], local=True)
    gw.set_prefs(U, {"preferred_routes": [f"{loc}::l"]})
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req(data_class=DataClass.SENSITIVE))
    assert ei.value.extra.get("ask_before_switching")


def test_org_policy_denies_provider(gw):
    from peoplepay_models.policy import OrgPolicy
    add_mock(gw, U, "Cloud", [{"id": "c", "name": "C"}])
    gw.org_policy = OrgPolicy(no_external_cloud=True)
    with pytest.raises(GatewayError):
        gw.infer(U, req())


# ---------------------------------------------------------------- auto routing
def test_auto_routing_by_task(gw):
    add_mock(gw, U, "A", [{"id": "tiny-mini", "name": "Mini", "context": 16000}, {"id": "plain", "name": "Plain", "context": 16000}, DEEP, VISION])
    simple = gw.infer(U, req("what is 2+2?"))
    assert simple.served_by.provider_model_id == "tiny-mini"          # simple => fast tier
    deep = gw.infer(U, req("analyse", task="analysis"))
    assert deep.served_by.provider_model_id == "m-deep"                # reasoning-capable
    vis = gw.infer(U, InferenceRequest(messages=[Message("user", [TextPart("what is this"), IMG])]))
    assert vis.served_by.provider_model_id in ("m-vision", "m-deep")   # a vision-capable route, never the text-only ones


def test_explain_lists_excluded_and_reasons(gw):
    add_mock(gw, U, "A", [{"id": "txt", "name": "T"}, VISION])
    ex = gw.explain(U, InferenceRequest(messages=[Message("user", [TextPart("x"), IMG])]))
    assert "vision" in ex["requirements"] and ex["selected"].startswith("Vision")
    assert any("lacks vision" in e["reason"] for e in ex["excluded"])
    assert any("Vision required" in s for s in ex["explanation"])


def test_one_shot_selection_does_not_change_recent_or_default(gw):
    add_mock(gw, U, "A", [FAST, DEEP])
    gw.infer(U, req(selection=ModelSelection("model", "m-deep", one_shot=True)))
    assert not gw.get_prefs(U).get("recent")
    gw.infer(U, req(selection=ModelSelection("model", "m-deep")))
    assert gw.get_prefs(U)["recent"]


def test_pinned_provider_route_and_aliases(gw):
    a = add_mock(gw, U, "A", [{"id": "same-model", "name": "Same"}])
    b = add_mock(gw, U, "B", [{"id": "same-model", "name": "Same"}])
    r = gw.infer(U, req(selection=ModelSelection("model", "same-model", connection_id=b)))
    assert r.served_by.connection_id == b
    groups = gw.list_models(U)["groups"]
    assert len([g for g in groups if g["canonical_model_id"] == "same-model"][0]["routes"]) == 2      # one model, two routes
    gw.set_prefs(U, {"aliases": {"Company Claude": f"{a}::same-model"}})
    assert gw.infer(U, req(selection=ModelSelection("model", "Company Claude"))).served_by.connection_id == a


# ---------------------------------------------------------------- tools / structured / context
def test_structured_output_is_validated_and_bad_json_never_trusted(gw):
    add_mock(gw, U, "A", [DEEP], structured_reply={"ok": True})
    schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
    r = gw.infer(U, req(response_schema=schema))
    assert r.parts[0].data == {"ok": True}
    c = gw.connections(U)[0]; c.configuration["structured_reply"] = {"ok": "yes"}; gw.store.save_connection(c)
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req(response_schema=schema))
    assert ei.value.code == ErrorCode.INVALID_RESPONSE


def test_tool_call_never_authorizes_consequential_actions():
    from peoplepay_models.tools import ToolRegistry
    reg = ToolRegistry(); ran = []
    reg.register(ToolDefinition("purchase", "buy"), lambda a: ran.append(a) or "bought", consequential=True)
    reg.register(ToolDefinition("lookup", "read"), lambda a: "found")
    res, pending = reg.execute(ToolCallPart("1", "purchase", {"sku": "x"}))
    assert not ran and pending and res.is_error and "approval" in res.content
    assert reg.execute(ToolCallPart("2", "lookup", {}))[0].content == "found"


def test_tool_call_normalized_through_gateway(gw):
    add_mock(gw, U, "A", [DEEP], call_tool=True, tool_args={"q": 1})
    r = gw.infer(U, req(tools=[ToolDefinition("lookup", "d")]))
    assert isinstance(r.parts[0], ToolCallPart) and r.parts[0].arguments == {"q": 1}


def test_malformed_tool_call_triggers_fallback_not_crash(gw):
    a = add_mock(gw, U, "A", [dict(DEEP, id="bad")], bad_tool_call=True)
    add_mock(gw, U, "B", [dict(DEEP, id="good")])
    gw.set_prefs(U, {"preferred_routes": [f"{a}::bad"]})
    assert gw.infer(U, req(tools=[ToolDefinition("t", "d")])).served_by.provider_model_id == "good"


def test_context_overflow_trims_older_messages_and_says_so(gw):
    add_mock(gw, U, "A", [{"id": "small", "name": "S", "context": 600}])
    conv = Conversation(owner=U, messages=[Message.user("x" * 150) if i % 2 == 0 else Message.assistant("y" * 150) for i in range(12)])
    conv.add(Message.user("latest question"))
    r = gw.infer(U, InferenceRequest(conversation=conv, max_output_tokens=50))
    assert any("context trimmed" in n for n in r.notes) and "latest question" in r.text


def test_context_too_large_when_recent_alone_exceeds(gw):
    add_mock(gw, U, "A", [{"id": "small", "name": "S", "context": 100}])
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req("z" * 5000))
    assert ei.value.code in (ErrorCode.NO_ROUTE, ErrorCode.CONTEXT_TOO_LARGE)


# ---------------------------------------------------------------- streaming
def test_stream_events_are_canonical_and_persisted(gw):
    add_mock(gw, U, "A")
    evs = list(gw.chat_stream(U, "hello there"))
    types = [e.type for e in evs]
    assert types[0] == "response.started" and types[-1] == "response.completed" and "text.delta" in types and "usage" in types
    cid = evs[-1].data["conversation_id"]
    assert len(gw.get_conversation(U, cid).messages) == 2


def test_stream_error_is_event_not_exception(gw):
    add_mock(gw, U, "A", script={"fail": ["INVALID_CREDENTIALS"]})
    evs = list(gw.chat_stream(U, "hi"))
    assert evs[-1].type == "error" and evs[-1].data["code"] == "INVALID_CREDENTIALS"


def test_stream_cancel_stops(gw):
    add_mock(gw, U, "A")
    tok = CancelToken()
    out = []
    for e in gw.chat_stream(U, "one two three four", cancel=tok):
        out.append(e)
        if e.type == "text.delta":
            tok.cancel()
    assert out[-1].type == "error" and out[-1].data["code"] == "CANCELLED"


# ---------------------------------------------------------------- usage / health / catalog caching
def test_usage_is_honest_about_unknowns(gw):
    add_mock(gw, U, "A"); add_mock(gw, U, "L", [{"id": "l", "name": "L"}], local=True)
    gw.infer(U, req())
    gw.set_prefs(U, {"local_only": True}); gw.infer(U, req())
    u = gw.usage(U)["providers"]
    cloud = [v for v in u.values() if not v["cost_note"] or "unknown" in v["cost_note"]]
    assert all(v["estimated_cost"] is None for v in u.values())              # no pricing => no invented cost
    assert any("local hardware" in (v["cost_note"] or "") for v in u.values())
    assert all(v["quota"] == "Quota information unavailable." for v in u.values())


def test_catalog_is_cached_listing_never_discovers(gw):
    cid = add_mock(gw, U, "A")
    before = calls(cid)
    for _ in range(5):
        gw.list_models(U); gw.health_overview(U)
    assert calls(cid) == before
    assert gw.models.age(cid) is not None and not gw.models.is_stale(cid)


def test_manual_refresh_keeps_old_catalog_on_failure(gw):
    cid = add_mock(gw, U, "A")
    c = gw.store.get_connection(cid); c.configuration["offline"] = True; gw.store.save_connection(c)
    with pytest.raises(GatewayError):
        gw.refresh_models(U, cid)
    assert gw.models.get(cid) and gw.models.last_error(cid)


def test_disabled_connection_not_routable_and_provider_can_vanish(gw):
    a = add_mock(gw, U, "A", [{"id": "a", "name": "A"}]); b = add_mock(gw, U, "B", [{"id": "b", "name": "B"}])
    gw.update_connection(U, a, enabled=False)
    assert gw.infer(U, req()).served_by.connection_id == b
    gw.remove_connection(U, b)
    with pytest.raises(GatewayError) as ei:
        gw.infer(U, req())
    assert ei.value.code == ErrorCode.NO_ROUTE and "Connect a provider" in ei.value.detail


def test_no_providers_configured_does_not_crash(gw):
    assert gw.health_overview(U) == [] and gw.list_models(U)["count"] == 0 and gw.usage(U)["total_requests"] == 0


# ---------------------------------------------------------------- scoping / BYOK
def test_user_connections_are_private_to_their_owner(gw):
    a = add_mock(gw, "alice", "Alice key")
    assert gw.connections("bob") == []
    with pytest.raises(GatewayError):
        gw.test_connection("bob", a)
    with pytest.raises(GatewayError):
        gw.remove_connection("bob", a)
    with pytest.raises(GatewayError) as ei:
        gw.infer("bob", req())
    assert ei.value.code == ErrorCode.NO_ROUTE


def test_system_connection_visible_but_not_removable(gw):
    gw.register_system_connection("sys_x", "mock", "System", {"models": [FAST]}, {})
    gw.refresh_models("alice", "sys_x")
    assert gw.connections("alice")[0].system
    with pytest.raises(GatewayError) as ei:
        gw.remove_connection("alice", "sys_x")
    assert ei.value.code == ErrorCode.AUTHORIZATION_REQUIRED
    assert gw.infer("bob", req()).text


def test_preferences_export_contains_no_secrets_or_connections(gw):
    gw.connect(U, "openai", "Mine", {"api_key": "sk-TOPSECRETVALUE123456"}, test=False)
    gw.set_prefs(U, {"routing_policy": "FASTEST", "favorites": ["x"]})
    blob = str(gw.export_prefs(U))
    assert "TOPSECRET" not in blob and "conn_" not in blob and "FASTEST" in blob
    gw.apply_preset(U, "local_coding"); assert gw.get_prefs(U)["local_only"] is True


def test_provenance_marks_model_inference(gw):
    add_mock(gw, U, "A")
    p = gw.provenance(gw.infer(U, req()), source="ext:rumi")
    assert p["origin"] == "MODEL_INFERENCE" and p["provider"] == "mock" and p["source"] == "ext:rumi" and p["model"]


def test_platform_owner_can_disable_provider(gw):
    add_mock(gw, U, "A")
    gw.providers.disable("mock")
    assert gw.connections(U) == []
    with pytest.raises(GatewayError):
        gw.connect(U, "mock", "again", {})


def test_requested_label_is_human_readable_not_a_route_key(gw):
    a = add_mock(gw, U, "P", [{"id": "p", "name": "Pretty Name"}], script={"fail": ["RATE_LIMITED"]})
    add_mock(gw, U, "B", [{"id": "b", "name": "B"}])
    r = gw.infer(U, req(selection=ModelSelection("model", f"{a}::p")))
    assert r.model_requested == "Pretty Name" and r.served_by.requested == "Pretty Name" and "conn_" not in r.model_requested
    assert gw.infer(U, req()).model_requested == "Auto"


def test_default_model_applies_only_to_default_mode_and_explicit_auto_stays_auto(gw):
    add_mock(gw, U, "A", [{"id": "tiny-mini", "name": "Mini"}, DEEP])
    gw.set_prefs(U, {"default_model": "m-deep"})
    assert gw.infer(U, req(selection=ModelSelection("default"))).served_by.provider_model_id == "m-deep"
    assert gw.infer(U, req(selection=ModelSelection("auto"))).served_by.provider_model_id == "tiny-mini"    # explicit Auto is not overridden


def test_conversation_roundtrips_every_part_type_and_rejects_unknown_kinds():
    from peoplepay_models.canonical import (FilePart, ServedBy, StructuredPart, ToolResultPart, part_from_dict)
    conv = Conversation(owner=U, title="t")
    conv.add(Message("user", [TextPart("hi"), IMG, FilePart("a.pdf", "application/pdf", "AAAA")]))
    conv.add(Message("assistant", [ToolCallPart("c1", "lookup", {"q": 1}), StructuredPart({"k": [1, 2]}, "s")],
                     served_by=ServedBy("openai", "conn_1", "m", "m-2024", "Direct (OpenAI)", "Auto", None)))
    conv.add(Message("tool", [ToolResultPart("c1", "found", False)]))
    again = Conversation.from_dict(__import__("json").loads(__import__("json").dumps(conv.to_dict())))
    assert again.to_dict() == conv.to_dict() and again.required_input_kinds() == {"text", "image", "file", "tool_call", "structured", "tool_result"}
    with pytest.raises(ValueError):
        part_from_dict({"kind": "hologram"})
