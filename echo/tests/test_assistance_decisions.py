"""Real FalkorDB provenance, ownership and immutable assistance snapshots."""
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from echo.assistance import AssistanceDecisions, EvaluateAssistance
from echo.graph_store import EchoGraphStore
from extensions.civicmesh.adapter import normalize
from peoplepay_sdk import ExtensionContext, ExtensionRequest


@pytest.fixture
def graph():
    name = "assistance_test_" + uuid4().hex
    store = EchoGraphStore(graph_name=name)
    try:
        assert store.ping()
    except Exception:
        if os.getenv("REQUIRE_JOURNEY_GRAPH") == "1":
            pytest.fail("FalkorDB required")
        pytest.skip("FalkorDB unavailable")
    try:
        yield store
    finally:
        if store.graph_name == name and name.startswith("assistance_test_"):
            store.graph.delete()


def body():
    workflow = "assistance-" + uuid4().hex
    raw = json.loads((Path(__file__).resolve().parents[2] / "tests/fixtures/civicmesh_native.json").read_text(encoding="utf-8"))
    raw.update(workflow_id=workflow, request_id=workflow + "-v1")
    request = ExtensionRequest(request_id=raw["request_id"], capability="assistance_eligibility",
        context=ExtensionContext(transaction_id=workflow, trace_id=workflow),
        input={"jurisdiction": "US", "need": "eviction", "facts": {}, "consent": True})
    return EvaluateAssistance(workflow_id=workflow, version=1, provider=normalize(request, raw))


def test_real_graph_and_version_history(graph):
    service = AssistanceDecisions(graph)
    request = body()
    first = service.evaluate(request, "owner")
    assert first["ingestion"]["claim_count"] == 12
    assert graph.read_only_rows("MATCH (p:Program) RETURN count(p)", {})[0][0] == 6
    assert graph.read_only_rows("MATCH (d:Decision)-[:USED_CLAIM]->(c:Claim) RETURN count(c)", {})[0][0] == 12
    assert service.evaluate(request, "owner") == first
    updated = request.model_dump(mode="json")
    updated["version"] = 2
    updated["provider"]["request_id"] = request.workflow_id + "-v2"
    updated["provider"]["raw_result"]["policy_date"] = "2026-10-07"
    second = service.evaluate(EvaluateAssistance.model_validate(updated), "owner")
    assert first["policy_date"] != second["policy_date"]
    assert service.get(first["decision_id"], "owner") == first
    assert first["money_moved"] is False
    with pytest.raises(KeyError):
        service.get(first["decision_id"], "other")


def test_medical_payment_option_is_manual_unverified_and_unapproved(graph):
    request = body()
    request.payment_option = {"amount_minor": 100000, "currency": "USD"}
    result = AssistanceDecisions(graph).evaluate(request, "owner")
    option = result["options"][-1]
    assert option["type"] == "pay" and option["requires_review"] is True
    assert option["evidence_state"] == "MANUAL_INPUT_UNVERIFIED"
    assert graph.read_only_rows("MATCH (a:Approval) RETURN count(a)", {})[0][0] == 0


def test_conflicting_version_is_rejected(graph):
    service = AssistanceDecisions(graph)
    request = body()
    service.evaluate(request, "owner")
    changed = request.model_dump(mode="json")
    changed["payment_option"] = {"amount_minor": 400, "currency": "USD"}
    with pytest.raises(ValueError, match="conflict"):
        service.evaluate(EvaluateAssistance.model_validate(changed), "owner")


@pytest.mark.parametrize("change", ["workflow", "verified", "criteria"])
def test_invalid_advisory_receipt_cannot_mutate_graph(graph, change):
    request = body().model_dump(mode="json")
    if change == "workflow":
        request["provider"]["request_id"] = "other-workflow-v1"
    elif change == "verified":
        request["provider"]["evidence"][0]["provenance_state"] = "known"
    else:
        request["provider"]["entities"][0]["attributes"]["claims"][0]["value"] = None
    with pytest.raises(ValueError):
        AssistanceDecisions(graph).evaluate(EvaluateAssistance.model_validate(request), "owner")
    assert graph.read_only_rows("MATCH (r:Requirement) RETURN count(r)", {})[0][0] == 0


def test_retry_recovers_a_missing_version_marker(graph):
    service = AssistanceDecisions(graph)
    request = body()
    first = service.evaluate(request, "owner")
    graph.upsert_node("Requirement", {"id": request.workflow_id, "assistance_version": 0})
    assert service.evaluate(request, "owner") == first
    assert graph.read_only_rows("MATCH (r:Requirement {id: $id}) RETURN r.assistance_version", {"id": request.workflow_id}) == [[1]]


def test_corrupt_historical_snapshot_is_not_trusted(graph):
    service = AssistanceDecisions(graph)
    first = service.evaluate(body(), "owner")
    corrupted = {**first, "policy_version": "changed-after-decision"}
    graph.upsert_node("Decision", {"id": first["decision_id"], "assistance_snapshot_json": json.dumps(corrupted)})
    with pytest.raises(ValueError, match="invalid preserved"):
        service.get(first["decision_id"], "owner")
