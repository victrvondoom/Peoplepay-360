"""Regressions for checkout recovery and preserved dispute authority."""

from copy import deepcopy

import httpx
import pytest

from gateway.merchant import ReferenceMerchant, terms_hash
from journey.proxy import NativeProxyAdapter, NativeProxyError, build_bundle, create_draft


def approved_action(merchant, version=1):
    terms = merchant.quote("supplier-b", "chair-b", 300, 200000000, 30)
    return {"action_id": f"approval-{version}", "actor_id": "buyer", "transaction_id": "txn-1",
            "decision_id": f"decision-v{version}", "decision_version": version, "decision_hash": "a" * 64,
            "terms": terms, "terms_hash": terms_hash(terms), "mode": "reference", "money_moved": False}


def dispute_context():
    merchant = ReferenceMerchant()
    try:
        action = approved_action(merchant)
        session = merchant.create_session(action, "create", "request-create")
        order = merchant.complete_session(session["id"], action, "complete", "request-complete")
        delivery = merchant.record_delivery(order["external_order_ref"], 260, "delivery", "request-delivery")
        requirement = {"description": "Procure 300 ergonomic chairs", "quantity": 300}
        decision = {"decision_id": action["decision_id"], "decision_version": 1, "actor_id": "buyer",
                    "transaction_id": "txn-1", "requirement": deepcopy(requirement),
                    "candidates": [{"supplier_id": "supplier-b", "eligible": True, "terms": deepcopy(action["terms"])}]}
        decision["decision_hash"] = terms_hash(decision)
        return {"requirement": requirement, "decision": decision,
                "selected_supplier": {"supplier_id": "supplier-b", "name": "Supplier B"},
                "approved_terms": action["terms"], "transaction_reference": "txn-1",
                "merchant_order_reference": order["external_order_ref"], "delivery_event": delivery["event"],
                "actor_id": "buyer", "correlation_id": "journey-1"}
    finally:
        merchant.close()


def test_checkout_can_use_renewed_echo_decision_identity_without_losing_owner():
    merchant = ReferenceMerchant()
    try:
        first = approved_action(merchant)
        session = merchant.create_session(first, "create", "request-1")
        item = next(item for item in merchant.get_catalog() if item["supplier_id"] == "supplier-b")
        merchant.set_catalog_item({**item, "unit_price_minor": 610000})
        revised = approved_action(merchant, version=2)
        assert revised["decision_id"] != first["decision_id"]
        updated = merchant.update_session(session["id"], revised, "update", "request-2")
        assert updated["status"] == "ready_for_payment"
        final = merchant.complete_session(session["id"], revised, "complete", "request-3")
        assert final["order"]["decision_id"] == revised["decision_id"]
        assert final["order"]["approved_terms"]["total_minor"] == 183000000
        assert final["money_moved"] is False
    finally:
        merchant.close()


@pytest.mark.parametrize("changed", [{"actor_id": "another-buyer"}, {"transaction_id": "another-txn"}])
def test_new_decision_does_not_change_checkout_actor_or_transaction(changed):
    merchant = ReferenceMerchant()
    try:
        first = approved_action(merchant)
        session = merchant.create_session(first, "create", "request-1")
        with pytest.raises(ValueError, match="same actor and transaction"):
            merchant.update_session(session["id"], {**approved_action(merchant, 2), **changed}, "update", "request-2")
    finally:
        merchant.close()


def test_recovery_order_lookup_is_scoped_detached_and_preserves_final_delivery(tmp_path):
    path = tmp_path / "merchant-recovery.sqlite3"
    merchant = ReferenceMerchant(path)
    action = approved_action(merchant)
    assert merchant.get_order_for_transaction("buyer", "txn-1") is None
    session = merchant.create_session(action, "create", "request-1")
    checkout = merchant.complete_session(session["id"], action, "complete", "request-2")
    merchant.record_delivery(checkout["external_order_ref"], 260, "delivery", "request-3")
    merchant.close()
    restarted = ReferenceMerchant(path)
    try:
        recovered = restarted.get_order_for_transaction("buyer", "txn-1")
        assert recovered is not None
        assert recovered["checkout_session_id"] == session["id"]
        assert recovered["delivery_final"] is True and recovered["delivered_quantity"] == 260
        assert recovered["decision_id"] == action["decision_id"]
        assert recovered["terms_hash"] == action["terms_hash"]
        assert restarted.get_order_for_transaction("another-buyer", "txn-1") is None
        assert restarted.get_order_for_transaction("buyer", "another-txn") is None
        recovered["approved_terms"]["quantity"] = 1
        unchanged = restarted.get_order_for_transaction("buyer", "txn-1")
        assert unchanged is not None and unchanged["approved_terms"]["quantity"] == 300
        assert len(restarted.get_events(checkout["external_order_ref"])) == 2
    finally:
        restarted.close()


@pytest.mark.parametrize("key,value", [("action_id", "bad\nidentifier"), ("actor_id", "bad\x7fidentifier"),
                                      ("transaction_id", "bad\ud800identifier")])
def test_checkout_identifier_validation_rejects_control_and_surrogate_characters(key, value):
    merchant = ReferenceMerchant()
    try:
        with pytest.raises(ValueError):
            merchant.create_session({**approved_action(merchant), key: value}, "create", "request-1")
    finally:
        merchant.close()


def test_checkout_terms_are_bounded_before_storage():
    merchant = ReferenceMerchant()
    try:
        action = approved_action(merchant)
        action["terms"]["unbounded_metadata"] = "x" * 65536
        with pytest.raises(ValueError, match="64 KiB"):
            merchant.create_session(action, "create", "request-1")
    finally:
        merchant.close()


@pytest.mark.parametrize("fragment,key,value", [
    ("decision", "actor_id", "another-buyer"),
    ("decision", "transaction_id", "another-transaction"),
    ("delivery_event", "transaction_id", "another-transaction"),
    ("delivery_event", "merchant_order_ref", "another-order"),
    ("delivery_event", "decision_id", "another-decision"),
    ("delivery_event", "decision_version", 2),
    ("delivery_event", "decision_version", True),
    ("selected_supplier", "supplier_id", "supplier-a"),
    ("requirement", "quantity", 200),
])
def test_proxy_does_not_hash_inconsistent_preserved_authority(fragment, key, value):
    source = dispute_context()
    source[fragment][key] = value
    with pytest.raises(ValueError):
        build_bundle(**source)


@pytest.mark.parametrize("key,value", [("ordered_quantity", 300.0), ("missing_quantity", 30),
                                      ("delivery_final", False), ("delivery_final", 1)])
def test_proxy_receipt_must_be_final_and_exact(key, value):
    source = dispute_context()
    source["delivery_event"]["data"][key] = value
    with pytest.raises(ValueError):
        build_bundle(**source)


def test_proxy_requires_the_original_eligible_candidate_and_decision_hash():
    source = dispute_context()
    source["decision"]["candidates"][0]["eligible"] = False
    source["decision"]["decision_hash"] = terms_hash({k: v for k, v in source["decision"].items() if k != "decision_hash"})
    with pytest.raises(ValueError, match="eligible candidate"):
        build_bundle(**source)
    source = dispute_context()
    source["decision"]["candidates"][0]["terms"]["unit_price_minor"] += 1
    with pytest.raises(ValueError, match="decision hash"):
        build_bundle(**source)
    preserved = build_bundle(**dispute_context())
    draft = create_draft(preserved)
    assert draft["bundle"]["discrepancy"]["missing_quantity"] == 40
    assert draft["submitted"] is False


def native_adapter(handler):
    return NativeProxyAdapter("http://127.0.0.1:8093", transport=httpx.MockTransport(handler))


def native_case(bundle=None, **changes):
    return {"id": "case-1", "user_id": "proxy-buyer", "domain": "ecommerce", "status": "intake",
            "institution_name": "Supplier B", "summary": f"Evidence SHA-256 {bundle['bundle_hash'] if bundle else 'unknown'}.", **changes}


@pytest.mark.parametrize("status", [None, "unknown", "analyzing", "submitted", "resolved", "closed"])
def test_native_handoff_rejects_nonopen_case_state_before_upload(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(201, json=native_case(status=status))

    with pytest.raises(NativeProxyError, match="open ecommerce") as error:
        native_adapter(handler).create_draft(build_bundle(**dispute_context()), bearer_token="mapped-token", proxy_user_id="proxy-buyer")
    assert error.value.case_id == "case-1"
    assert len(requests) == 1


def test_native_resume_response_must_match_the_requested_case_id():
    bundle = build_bundle(**dispute_context())
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=native_case(bundle, id="another-case"))

    with pytest.raises(NativeProxyError, match="different resume case") as error:
        native_adapter(handler).create_draft(bundle, bearer_token="mapped-token", proxy_user_id="proxy-buyer", native_case_id="case-1")
    assert error.value.case_id == "case-1"
    assert len(requests) == 1 and requests[0].method == "GET"


def test_empty_resume_id_and_nonascii_token_fail_without_creating_case():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(500)
    adapter = native_adapter(handler)
    for keywords in ({"native_case_id": ""}, {"bearer_token": "not-an-ascii-\u00e9-token"}, {"bearer_token": "token with spaces"}):
        with pytest.raises(ValueError):
            adapter.create_draft(build_bundle(**dispute_context()), **{"bearer_token": "token", "proxy_user_id": "proxy-buyer", **keywords})
    assert requests == []


@pytest.mark.parametrize("response", [b'{"id":"case-1","user_id":"proxy-buyer","score":NaN}',
                                     b'{"id":"case-1","id":"case-2"}',
                                     b'{"id":"\\ud800"}', b'[' * 2000 + b']' * 2000],
                         ids=["nonfinite", "duplicate_keys", "invalid_unicode", "deep_json"])
def test_native_response_rejects_nonfinite_ambiguous_invalid_unicode_and_deep_json(response):
    with pytest.raises(NativeProxyError, match="invalid JSON"):
        native_adapter(lambda request: httpx.Response(200, content=response)).create_draft(
            build_bundle(**dispute_context()), bearer_token="token", proxy_user_id="proxy-buyer")


@pytest.mark.parametrize("analysis", [{"status": "submitted"}, {"submitted": True}, {"user_id": "another-user"}])
def test_native_result_cannot_claim_submitted_or_foreign_analysis_is_a_draft(analysis):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/cases"):
            return httpx.Response(201, json=native_case())
        if request.url.path.endswith("/upload"):
            return httpx.Response(200, json={"id": "doc-1", "case_id": "case-1", "user_id": "proxy-buyer"})
        return httpx.Response(200, json={"case_id": "case-1", "appeal_draft": "Please investigate.", **analysis})

    with pytest.raises(NativeProxyError) as error:
        native_adapter(handler).create_draft(build_bundle(**dispute_context()), bearer_token="token", proxy_user_id="proxy-buyer")
    assert error.value.case_id == "case-1"
    assert len(requests) == 3


def test_native_evidence_must_have_an_identifier_before_appeal_call():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/cases"):
            return httpx.Response(201, json=native_case())
        return httpx.Response(200, json={"case_id": "case-1", "user_id": "proxy-buyer"})

    with pytest.raises(NativeProxyError, match="document identifier") as error:
        native_adapter(handler).create_draft(build_bundle(**dispute_context()), bearer_token="token", proxy_user_id="proxy-buyer")
    assert error.value.case_id == "case-1"
    assert len(requests) == 2
