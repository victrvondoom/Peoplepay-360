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
