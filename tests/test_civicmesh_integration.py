"""SDK, privacy, routing, provider outage and durable follow-up regressions."""
import asyncio
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from peoplepay_sdk import ExtensionContext, ExtensionRequest

from extensions.civicmesh.adapter import CivicMeshProvider, normalize
from journey.assistance import AssistanceService
from journey.capability_router import route_need
from journey.extension_runtime import CapabilityRuntime
from journey.providers import HttpSourceClient
from journey.sdk_bridge import to_echo_result
from journey.store import JourneyStore


def native_receipt(request_id="assistance-test-v1", workflow="assistance-test"):
    result = json.loads((Path(__file__).parent / "fixtures/civicmesh_native.json").read_text(encoding="utf-8"))
    result.update(request_id=request_id, workflow_id=workflow)
    return result


def sdk_request(**overrides):
    return ExtensionRequest(request_id="assistance-test-v1", capability="assistance_eligibility",
        context=ExtensionContext(trace_id="assistance-test", transaction_id="assistance-test"),
        input={"jurisdiction": "US", "need": "eviction", "facts": {"age": 72, "income_annual": 14400}, "consent": True, **overrides})


def client(*, unavailable=False):
    def handler(request):
        if unavailable:
            return httpx.Response(503, json={"detail": "provider unavailable"})
        if request.url.path == "/health":
            return httpx.Response(200, json={"engine": "ENGINE_OK"})
        body = json.loads(request.content)
        assert set(body) == {"request_id", "workflow_id", "jurisdiction", "language", "need", "facts", "consent"}
        assert "message" not in body and "actor_id" not in body
        return httpx.Response(200, json=native_receipt(body["request_id"], body["workflow_id"]))
    return HttpSourceClient("http://127.0.0.1:8092", token="x" * 32, transport=httpx.MockTransport(handler))


def runtime(unavailable=False):
    host = CapabilityRuntime()
    host.register(CivicMeshProvider(client(unavailable=unavailable)), jurisdictions={"US"},
                  input_fields={"jurisdiction", "language", "need", "facts", "consent"})
    return host


@pytest.mark.parametrize("message, intent, need", [
    ("I'm 72, have very low income, and my landlord is evicting me.", "assistance", "eviction"),
    ("I need 300 ergonomic office chairs for my company.", "procurement", None),
    ("I have a medical bill due and I'm struggling to pay.", "assistance", "medical_bill"),
    ("I lost my company and I want to kill myself", "assistance", "crisis"),
    ("My company dismissed me and my landlord is evicting me", "assistance", "eviction"),
    ("I want to kill myself but I am not suicidal", "assistance", "crisis")])
def test_real_deterministic_routing_difference(message, intent, need):
    route = route_need(message, "US")
    assert (route["intent"], route["need"]) == (intent, need)
    if intent == "procurement":
        assert route["providers"] == ["greenchain", "inflationforge"]
        assert route["civicmesh_invoked"] is False


def test_actual_native_receipt_becomes_claims_evidence_estimates():
    result = normalize(sdk_request(), native_receipt())
    normalized = to_echo_result(result)
    assert len(normalized.entities) == 6
    assert len(normalized.claims) == 12
    assert normalized.evidence and result.action_proposals
    assert normalized.entities[0].type == "Program"
    assert result.raw_result["question"]["key"] == "location"
    assert all(c.value["calibrated_probability"] is False for c in normalized.claims if c.predicate == "eligibility_score")
    assert all(e.provenance_state == "PROVENANCE_UNKNOWN" for e in normalized.evidence)
    assert result.raw_result["policy_date"] and result.raw_result["policy_version"]


@pytest.mark.parametrize("field,value", [("workflow_id", "other"), ("provider_version", "2.0.0"), ("calibrated_probability", True), ("observed_at", "2099-01-01T00:00:00+00:00")])
def test_receipt_cannot_swap_scope_version_or_score_semantics(field, value):
    raw = native_receipt()
    raw[field] = value
    with pytest.raises(ValueError):
        normalize(sdk_request(), raw)


@pytest.mark.parametrize("field,value", [("question", None), ("plan", {"steps": None}), ("programs", []), ("routes", {})])
def test_malformed_native_shape_is_rejected(field, value):
    raw = native_receipt()
    raw[field] = value
    with pytest.raises(ValueError):
        normalize(sdk_request(), raw)


def test_permission_gate_refuses_unrelated_context():
    request = sdk_request()
    request.input["payment_account"] = "never-forward-this"
    with pytest.raises(ValueError, match="PERMISSION_DENIED"):
        asyncio.run(runtime().invoke(request, "US"))


def test_provider_coverage_and_outage_do_not_crash():
    result, trace = asyncio.run(runtime().invoke(sdk_request(jurisdiction="IN"), "IN"))
    assert result is None and trace["status"] == "UNSUPPORTED_JURISDICTION"
    result, trace = asyncio.run(runtime(unavailable=True).invoke(sdk_request(), "US"))
    assert result is None and trace["status"] == "ASSISTANCE_PROVIDER_UNAVAILABLE"


class EchoFixture:
    def __init__(self):
        self.snapshots = {}
        self.fail = False

    def request(self, method, path, actor, authorization, body=None):
        from journey.service import JourneyUnavailable
        if self.fail:
            raise JourneyUnavailable("unavailable")
        if method == "GET":
            return deepcopy(self.snapshots[path.rsplit("/", 1)[-1]])
        identifier = f"decision-{body['workflow_id']}-v{body['version']}"
        snapshot = {"decision_id": identifier, "version": body["version"], "decision_hash": "a" * 64,
                    "status": "NEEDS_INFORMATION", "question": body["provider"]["raw_result"]["question"],
                    "policy_version": body["provider"]["raw_result"]["policy_version"], "options": [], "money_moved": False}
        self.snapshots[identifier] = snapshot
        return snapshot


def test_followup_keeps_same_context_and_historical_versions():
    echo = EchoFixture()
    service = AssistanceService(store=JourneyStore(), echo=echo, runtime=runtime())
    first = service.create("owner", {"message": "My landlord is evicting me, secret-name-do-not-store", "jurisdiction": "US", "consent": True,
        "facts": {"age": 72, "income_annual": 14400}})
    second = service.update(first["id"], "owner", {"facts": {"state": "TX"}})
    assert second["id"] == first["id"]
    assert second["input"]["facts"]["age"] == 72
    assert second["input"]["facts"]["income_annual"] == 14400
    assert second["input"]["facts"]["state"] == "TX"
    assert len(second["decisions"]) == 2
    assert "secret-name-do-not-store" not in json.dumps(second)
    assert len(service.explain(first["id"], "owner")["historical_decisions"]) == 2
    with pytest.raises(KeyError):
        service.store.get(first["id"], "other-owner")


def test_echo_retry_reuses_saved_provider_receipt():
    echo = EchoFixture()
    echo.fail = True
    host = runtime()
    service = AssistanceService(store=JourneyStore(), echo=echo, runtime=host)
    record = service.create("owner", {"message": "I need housing", "jurisdiction": "US", "consent": True})
    assert record["phase"] == "ECHO_UNAVAILABLE_OR_REJECTED"
    receipt = deepcopy(record["pending_receipt"])
    with pytest.raises(ValueError, match="pending"):
        service.update(record["id"], "owner", {"facts": {"age": 72}})
    echo.fail = False
    recovered = service.retry(record["id"], "owner")
    assert recovered["decision"]["version"] == 1
    assert len(host.traces) == 1
    assert receipt["request_id"] == record["id"] + "-v1"


def test_no_consent_or_irrelevant_request_never_calls_provider():
    host = runtime()
    service = AssistanceService(store=JourneyStore(), echo=EchoFixture(), runtime=host)
    with pytest.raises(ValueError, match="Consent"):
        service.create("owner", {"message": "I need housing", "jurisdiction": "US"})
    result = service.create("owner", {"message": "300 office chairs for my company", "jurisdiction": "US"})
    assert result["status"] == "ROUTED_TO_PROCUREMENT"
    assert host.traces == []
