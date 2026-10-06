"""Real ECHO graph snapshots, exact approval binding and six-day reassessment."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest

from echo.graph_store import EchoGraphStore
from echo.journey import ApproveJourney, EvaluateJourney, JourneyEcho, reconcile_entities
from gateway.merchant import ReferenceMerchant
from journey.models import REFERENCE_REQUIREMENT
from journey.providers import GreenChainProvider, InflationForgeProvider, reference_provider_clients
from peoplepay_sdk import Entity, ExtensionContext, ExtensionRequest, ExtensionResult


@pytest.fixture
def graph():
    name = "journey_decision_test_" + uuid4().hex
    store = EchoGraphStore(graph_name=name)
    try:
        assert store.ping()
    except Exception as exc:
        if os.getenv("REQUIRE_JOURNEY_GRAPH") == "1":
            pytest.fail(f"Real ECHO graph required: {exc}")
        pytest.skip(f"Real ECHO graph unavailable: {exc}")
    try:
        yield store
    finally:
        # This UUID graph belongs exclusively to the test fixture.
        if store.graph_name == name and name.startswith("journey_decision_test_"):
            store.graph.delete()


def body():
    async def receipts():
        clients = reference_provider_clients()
        results = []
        for provider in (GreenChainProvider(clients[0], mode="reference"), InflationForgeProvider(clients[1], mode="reference")):
            results.append(await provider.execute(ExtensionRequest(
                request_id="test-" + provider.metadata().id, capability=provider.capabilities()[0].name,
                context=ExtensionContext(trace_id="test"), input={"product": "ergonomic office chairs", "quantity": 300, "destination": "IN"})))
        return results
    merchant = ReferenceMerchant()
    try:
        quotes = [merchant.quote(item["supplier_id"], item["product_id"], 300, 200000000, 30) for item in merchant.get_catalog()]
    finally:
        merchant.close()
    return EvaluateJourney.model_validate({"journey_id": "journey-" + uuid4().hex, "transaction_id": "txn-test",
        "version": 1, "mode": "reference", "requirement": REFERENCE_REQUIREMENT,
        "providers": [result.model_dump(mode="json") for result in asyncio.run(receipts())], "merchant_quotes": quotes})


def approval(decision, **overrides):
    return ApproveJourney(decision_hash=decision["decision_hash"], decision_version=decision["decision_version"],
        supplier_id=overrides.pop("supplier_id", "supplier-b"), human_confirmation=True, confirm_reference=True, **overrides)


def test_six_days_later_preserved_decision_and_new_quote_remain_distinct(graph):
    initial_time = datetime.now(timezone.utc) - timedelta(days=6)
    clock = [initial_time]
    engine = JourneyEcho(graph, clock=lambda: clock[0])
    request = body()
    first = engine.evaluate(request, "owner")
    authorized = engine.approve(first["decision_id"], "owner", approval(first))
    clock[0] += timedelta(days=6)
    updated = request.model_dump(mode="json")
    updated["version"] = 2
    changed = next(item for item in updated["merchant_quotes"] if item["supplier_id"] == "supplier-b")
    changed["unit_price_minor"] = 630000
    changed["total_minor"] = 189000000
    second = engine.evaluate(EvaluateJourney.model_validate(updated), "owner")
    old = engine.get(first["decision_id"], "owner")
    assert old == first
    assert old["evaluated_at"] == initial_time.isoformat()
    assert second["evaluated_at"] == (initial_time + timedelta(days=6)).isoformat()
    assert authorized["terms"]["total_minor"] == 177000000
    assert next(item for item in second["candidates"] if item["supplier_id"] == "supplier-b")["terms"]["total_minor"] == 189000000
    with pytest.raises(ValueError, match="superseded"):
        engine.approve(first["decision_id"], "owner", approval(first))
    with pytest.raises(KeyError):
        engine.get(first["decision_id"], "another-owner")


def test_immutable_version_exact_approval_and_snapshot_tampering_fail_closed(graph):
    engine = JourneyEcho(graph)
    request = body()
    decision = engine.evaluate(request, "owner")
    assert engine.evaluate(request, "owner") == decision
    modified = request.model_dump(mode="json")
    modified["merchant_quotes"][0]["delivery_days"] += 1
    with pytest.raises(ValueError, match="different receipts"):
        engine.evaluate(EvaluateJourney.model_validate(modified), "owner")
    engine.approve(decision["decision_id"], "owner", approval(decision))
    with pytest.raises(ValueError, match="existing approval"):
        engine.approve(decision["decision_id"], "owner", approval(decision, supplier_id="supplier-a"))
    altered = deepcopy(decision)
    altered["recommended_supplier_id"] = "supplier-c"
    import json
    graph.upsert_node("Decision", {"id": decision["decision_id"], "journey_snapshot_json": json.dumps(altered)})
    with pytest.raises(ValueError, match="integrity"):
        engine.get(decision["decision_id"], "owner")


def test_aliases_merge_only_with_exact_identifier_and_preserve_provider_provenance():
    def result(provider, name, domain):
        return ExtensionResult(request_id="test", extension_id=provider, extension_version="1.0.0", status="success",
            entities=[Entity(id="s-" + provider, entity_type="supplier", name=name, identifiers={"domain": domain} if domain else {})])
    reconciled = reconcile_entities([result("greenchain", "Herman Miller Inc.", "hermanmiller.com"),
                                    result("inflationforge", "Herman Miller", "hermanmiller.com")])
    assert len(reconciled) == 1
    assert len(reconciled[0]["aliases"]) == 2
    assert {item["extension_id"] for item in reconciled[0]["representations"]} == {"greenchain", "inflationforge"}
    assert reconciled[0]["identity_verified"] is False
    assert len(reconcile_entities([result("greenchain", "Herman Miller Inc.", None),
                                   result("inflationforge", "Herman Miller", None)])) == 2


def test_price_priority_records_the_weights_actually_used(graph):
    request = body().model_dump(mode="json")
    request["requirement"]["prioritize_sustainability"] = False
    decision = JourneyEcho(graph).evaluate(EvaluateJourney.model_validate(request), "owner")
    assert decision["policy"]["sustainability_weight"] == 0
    assert decision["policy"]["price_weight"] == 1
    for candidate in decision["candidates"]:
        expected = round(100 * (1 - candidate["terms"]["total_minor"] / REFERENCE_REQUIREMENT["budget_minor"]), 4)
        assert candidate["echo_score"] == expected
    # Cheapest C still fails delivery; policy constraints precede ranking.
    assert decision["recommended_supplier_id"] == "supplier-b"


@pytest.mark.parametrize("field,value", [("total_minor", -1), ("delivery_days", 0), ("total_minor", "bad"), ("quantity", True)])
def test_invalid_merchant_quote_rejected_before_policy(field, value):
    request = body().model_dump(mode="json")
    request["merchant_quotes"][0][field] = value
    with pytest.raises(ValueError):
        EvaluateJourney.model_validate(request)


@pytest.mark.parametrize("score", [None, True, -1, 101, "90", 10**400])
def test_unavailable_or_invalid_provider_score_cannot_win_sustainability_policy(graph, score):
    request = body()
    supplier = request.providers[0].entities[0]
    supplier.attributes["provider_score"] = score
    supplier.attributes["claims"][0]["value"] = score
    decision = JourneyEcho(graph).evaluate(request, "owner")
    candidate = next(item for item in decision["candidates"] if item["supplier_id"] == "supplier-b")
    assert candidate["raw_provider_score"] is None
    assert candidate["sustainability_score"] is None
    assert "SUSTAINABILITY_SCORE_UNAVAILABLE" in candidate["policy_violations"]
    assert not candidate["eligible"]
    assert decision["recommended_supplier_id"] != "supplier-b"


def test_conflicting_score_claim_cannot_support_supplier_ranking(graph):
    request = body()
    request.providers[0].entities[0].attributes["claims"][0]["value"] = 1
    decision = JourneyEcho(graph).evaluate(request, "owner")
    candidate = next(item for item in decision["candidates"] if item["supplier_id"] == "supplier-b")
    assert "SUSTAINABILITY_SCORE_EVIDENCE_MISSING_OR_CONFLICTING" in candidate["policy_violations"]
    assert not candidate["eligible"]


def test_duplicate_supplier_domain_is_ambiguous_instead_of_first_match_winning(graph):
    request = body()
    duplicate = request.providers[0].entities[0].model_copy(deep=True)
    duplicate.id += "-duplicate"
    duplicate.attributes["claims"] = []
    duplicate.attributes["estimates"] = []
    request.providers[0].entities.append(duplicate)
    decision = JourneyEcho(graph).evaluate(request, "owner")
    candidate = next(item for item in decision["candidates"] if item["supplier_id"] == "supplier-b")
    assert not candidate["eligible"]
    assert any("AMBIGUOUS" in item for item in candidate["policy_violations"])


@pytest.mark.parametrize("change", ["malformed_second_provider", "unreviewed_version", "mode", "quantity", "product"])
def test_invalid_receipts_are_rejected_before_graph_ingestion(graph, change):
    request = body()
    if change == "malformed_second_provider":
        request.providers[1].entities.append(Entity(id="bad-product", entity_type="product", name="Bad",
            attributes={"claims": {"bad": "shape"}}))
    elif change == "unreviewed_version":
        request.providers[0].extension_version = "2.0.0"
    elif change == "mode":
        request.providers[0].raw_result["mode"] = "live"
    elif change == "quantity":
        request.providers[0].raw_result["request_context"]["quantity"] = 1
    else:
        request.providers[0].raw_result["request_context"]["product"] = "different product"
    before = graph.read_only_rows("MATCH (n) RETURN count(n)", {})
    with pytest.raises(ValueError):
        JourneyEcho(graph).evaluate(request, "owner")
    assert graph.read_only_rows("MATCH (n) RETURN count(n)", {}) == before


def test_corrupt_stored_approval_cannot_be_replayed(graph):
    import json
    engine = JourneyEcho(graph)
    decision = engine.evaluate(body(), "owner")
    action = engine.approve(decision["decision_id"], "owner", approval(decision))
    action["actor_id"] = "another-owner"
    graph.upsert_node("Approval", {"id": action["action_id"], "action_json": json.dumps(action)})
    with pytest.raises(ValueError, match="binding"):
        engine.approve(decision["decision_id"], "owner", approval(decision))


def journey_api(graph):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from echo.auth import caller
    from echo.journey import build_journey_router
    app = FastAPI()
    app.include_router(build_journey_router(graph))
    app.dependency_overrides[caller] = lambda: "owner"
    return TestClient(app)


def test_snapshot_integrity_error_is_a_controlled_conflict_in_both_read_routes(graph):
    decision = JourneyEcho(graph).evaluate(body(), "owner")
    graph.upsert_node("Decision", {"id": decision["decision_id"], "journey_snapshot_json": "[]"})
    with journey_api(graph) as client:
        for path in (f"/echo/v1/journeys/decisions/{decision['decision_id']}",
                     f"/echo/v1/journeys/{decision['journey_id']}/current"):
            response = client.get(path)
            assert response.status_code == 409
            assert response.json()["detail"] == "historical decision snapshot failed its integrity check"


def test_graph_outage_is_sanitized_unavailability_for_every_journey_route(graph, monkeypatch):
    from redis.exceptions import ConnectionError
    request = body()
    decision = JourneyEcho(graph).evaluate(request, "owner")
    def offline():
        raise ConnectionError("sensitive-host-password")
    monkeypatch.setattr(graph, "ping", offline)
    with journey_api(graph) as client:
        calls = [("GET", f"/echo/v1/journeys/decisions/{decision['decision_id']}", None),
            ("GET", f"/echo/v1/journeys/{decision['journey_id']}/current", None),
            ("POST", "/echo/v1/journeys/evaluate", request.model_dump(mode="json")),
            ("POST", f"/echo/v1/journeys/decisions/{decision['decision_id']}/approve", approval(decision).model_dump())]
        for method, path, payload in calls:
            response = client.request(method, path, json=payload)
            assert response.status_code == 503
            assert response.json()["detail"] == "ECHO graph service is unavailable"
