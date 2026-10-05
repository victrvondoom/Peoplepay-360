import copy
import hashlib
import json

import httpx
import pytest

from journey.proxy import (
    NativeProxyAdapter,
    NativeProxyError,
    build_bundle,
    create_draft,
    verify_bundle,
)


def context():
    return {
        "requirement": {"text": "Procure 300 chairs under INR 20 lakh", "quantity": 300},
        "decision": {"decision_id": "decision-1", "version": 2, "evidence": [
            {"id": "greenchain-estimate", "provider": "GreenChain", "estimated": True},
            {"id": "inflation-observation", "provider": "InflationForge", "observed_at": "2026-10-01T00:00:00Z"},
        ], "raw_provider_results": {"greenchain": {"supplier_score": 0.89}}},
        "selected_supplier": {"id": "supplier-b", "name": "Supplier B"},
        "approved_terms": {"quantity": 300, "currency": "INR", "max_total_minor": 200000000},
        "transaction_reference": "peoplepay-transaction-1",
        "merchant_order_reference": "merchant-order-1",
        "delivery_event": {"event_id": "delivery-1", "data": {
            "merchant_order_reference": "merchant-order-1", "ordered_quantity": 300,
            "delivered_quantity": 260, "recorded_at": "2026-10-07T12:00:00Z",
        }},
        "actor_id": "owner",
        "correlation_id": "journey-1",
    }


def test_partial_delivery_carries_every_original_evidence_field_without_submission():
    source = context()
    bundle = build_bundle(**source)
    source["approved_terms"]["quantity"] = 260
    source["decision"]["evidence"].clear()
    draft = create_draft(bundle)
    assert draft["bundle"]["approved_terms"]["quantity"] == 300
    assert len(draft["bundle"]["decision"]["evidence"]) == 2
    assert draft["bundle"]["decision"]["raw_provider_results"]["greenchain"]["supplier_score"] == 0.89
    assert draft["bundle"]["discrepancy"] == {
        "kind": "partial_delivery", "ordered_quantity": 300,
        "delivered_quantity": 260, "missing_quantity": 40,
    }
    assert draft["bundle"]["transaction_reference"] == "peoplepay-transaction-1"
    assert draft["bundle"]["merchant_order_reference"] == "merchant-order-1"
    assert "40 units unaccounted" in draft["draft_text"]
    assert draft["mode"] == "REFERENCE_SIMULATOR"
    assert draft["status"] == "draft" and draft["requires_human_review"]
    assert draft["submitted"] is False
    assert create_draft(bundle)["draft_id"] == draft["draft_id"]


@pytest.mark.parametrize("field", ["requirement", "decision", "selected_supplier", "approved_terms", "delivery_event"])
def test_every_context_fragment_is_hash_bound(field):
    bundle = build_bundle(**context())
    bundle[field]["tampered"] = True
    with pytest.raises(ValueError, match="changed after snapshot"):
        verify_bundle(bundle)


@pytest.mark.parametrize("field", ["transaction_reference", "merchant_order_reference", "actor_id", "correlation_id"])
def test_every_linkage_reference_is_hash_bound(field):
    bundle = build_bundle(**context())
    bundle[field] = "different"
    with pytest.raises(ValueError, match="changed after snapshot"):
        create_draft(bundle)


def test_rejects_other_order_or_inconsistent_original_quantity():
    source = context()
    source["delivery_event"]["data"]["merchant_order_reference"] = "another-order"
    with pytest.raises(ValueError, match="another merchant order"):
        build_bundle(**source)
    source = context()
    source["delivery_event"]["data"]["ordered_quantity"] = 260
    with pytest.raises(ValueError, match="differs from approved terms"):
        build_bundle(**source)


@pytest.mark.parametrize("quantity", [300, 301, True, -1, 260.0])
def test_no_partial_delivery_draft_for_full_delivery_or_invalid_event(quantity):
    source = context()
    source["delivery_event"]["data"]["delivered_quantity"] = quantity
    with pytest.raises(ValueError):
        build_bundle(**source)


def test_native_proxy_receives_complete_json_evidence_and_generates_only_draft():
    requests = []
    bundle = build_bundle(**context())

    def handle(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer mapped-session"
        if request.url.path == "/api/v1/cases":
            payload = json.loads(request.content)
            assert payload["domain"] == "ecommerce"
            assert payload["institution_name"] == "Supplier B"
            assert "approved 300" in payload["summary"]
            assert bundle["bundle_hash"] in payload["summary"]
            return httpx.Response(201, json={"id": "proxy-case-1", "user_id": "mapped-owner", "domain": "ecommerce", "status": "intake"})
        if request.url.path == "/api/v1/case/upload":
            assert b'name="case_id"\r\n\r\nproxy-case-1' in request.content
            assert b'filename="peoplepay-evidence.json"' in request.content
            assert json.dumps(bundle, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() in request.content
            return httpx.Response(200, json={"id": "document-1", "case_id": "proxy-case-1", "user_id": "mapped-owner"})
        assert request.url.path == "/api/v1/case/appeal"
        assert json.loads(request.content) == {"case_id": "proxy-case-1"}
        return httpx.Response(200, json={"case_id": "proxy-case-1", "appeal_draft": "Native draft: please investigate the missing 40 chairs."})

    adapter = NativeProxyAdapter("http://127.0.0.1:8093", transport=httpx.MockTransport(handle))
    draft = adapter.create_draft(bundle, bearer_token="mapped-session", proxy_user_id="mapped-owner")
    assert [request.method for request in requests] == ["POST", "POST", "POST"]
    assert draft["mode"] == "NATIVE_SERVICE"
    assert draft["native_case_id"] == "proxy-case-1"
    assert draft["bundle"] == bundle
    assert draft["requires_human_review"] and draft["submitted"] is False
    assert "mapped-session" not in json.dumps(draft)


def test_native_proxy_rejects_mismatched_user_before_upload():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "case-1", "user_id": "wrong-user", "domain": "ecommerce", "status": "intake"})

    adapter = NativeProxyAdapter("http://127.0.0.1:8093", transport=httpx.MockTransport(handle))
    with pytest.raises(NativeProxyError, match="another mapped user") as error:
        adapter.create_draft(build_bundle(**context()), bearer_token="session", proxy_user_id="owner")
    assert error.value.case_id == "case-1"
    assert len(requests) == 1


def test_native_proxy_preserves_progress_without_retrying_ambiguous_upload_failure():
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(201, json={"id": "case-1", "user_id": "owner", "domain": "ecommerce", "status": "intake"})
        raise httpx.ReadTimeout("response lost")

    adapter = NativeProxyAdapter("http://127.0.0.1:8093", transport=httpx.MockTransport(handle))
    with pytest.raises(NativeProxyError) as error:
        adapter.create_draft(build_bundle(**context()), bearer_token="session", proxy_user_id="owner")
    assert error.value.case_id == "case-1"
    assert len(requests) == 2


def test_native_proxy_does_not_label_missing_native_output_a_draft():
    def handle(request):
        if request.url.path.endswith("/cases"):
            return httpx.Response(201, json={"id": "case-1", "user_id": "owner", "domain": "ecommerce", "status": "intake"})
        if request.url.path.endswith("/upload"):
            return httpx.Response(200, json={"id": "doc-1", "user_id": "owner", "case_id": "case-1"})
        return httpx.Response(200, json={"case_id": "case-1", "appeal_draft": ""})

    adapter = NativeProxyAdapter("http://127.0.0.1:8093", transport=httpx.MockTransport(handle))
    with pytest.raises(NativeProxyError, match="no appeal draft"):
        adapter.create_draft(build_bundle(**context()), bearer_token="session", proxy_user_id="owner")


def test_native_proxy_refuses_insecure_tokens_redirects_and_unbounded_results():
    with pytest.raises(ValueError, match="HTTPS"):
        NativeProxyAdapter("http://proxy.example")
    adapter = NativeProxyAdapter("https://proxy.example", transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://another.example"})
    ))
    with pytest.raises(NativeProxyError, match="HTTP 302"):
        adapter.create_draft(build_bundle(**context()), bearer_token="session", proxy_user_id="owner")
    adapter = NativeProxyAdapter("http://127.0.0.1", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * (512 * 1024 + 1))
    ))
    with pytest.raises(NativeProxyError, match="exceeded"):
        adapter.create_draft(build_bundle(**context()), bearer_token="session", proxy_user_id="owner")


def test_bundle_limits_reject_nonfinite_and_large_evidence():
    source = context()
    source["decision"]["score"] = float("nan")
    with pytest.raises(ValueError, match="finite JSON"):
        build_bundle(**source)
    source = context()
    source["decision"]["raw_document"] = "x" * (512 * 1024)
    with pytest.raises(ValueError, match="512 KiB"):
        build_bundle(**source)


def test_draft_copy_is_detached_from_verified_bundle():
    bundle = build_bundle(**context())
    draft = create_draft(bundle)
    draft["bundle"]["approved_terms"]["quantity"] = 260
    assert verify_bundle(copy.deepcopy(bundle))["approved_terms"]["quantity"] == 300


def test_missing_fields_are_validation_errors_even_with_recomputed_hash():
    bundle = build_bundle(**context())
    del bundle["decision"]
    bundle["bundle_hash"] = hashlib.sha256(json.dumps(
        {key: value for key, value in bundle.items() if key != "bundle_hash"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()
    with pytest.raises(ValueError, match="missing or unsupported"):
        verify_bundle(bundle)


def test_native_resume_rejects_another_case_context_without_uploading():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "existing-case", "user_id": "owner", "domain": "ecommerce",
            "status": "intake", "summary": "An unrelated previous dispute",
            "institution_name": "Supplier B",
        })

    adapter = NativeProxyAdapter("http://127.0.0.1", transport=httpx.MockTransport(handle))
    with pytest.raises(NativeProxyError, match="does not match"):
        adapter.create_draft(
            build_bundle(**context()), bearer_token="session", proxy_user_id="owner",
            native_case_id="existing-case",
        )
    assert len(requests) == 1 and requests[0].method == "GET"
