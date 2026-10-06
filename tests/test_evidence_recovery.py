"""Malformed receipts and historical observations cannot acquire authority."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from peoplepay_sdk import ExtensionContext, ExtensionRequest

from journey.providers import GreenChainProvider, InflationForgeProvider, ReferenceSourceClient
from journey.sdk_bridge import to_echo_result


def request(capability="supplier_discovery", **overrides):
    return ExtensionRequest(request_id="evidence-recovery", capability=capability,
        context=ExtensionContext(user_id="owner", trace_id="evidence-recovery"), input={"product": "ergonomic office chairs",
        "quantity": 300, "destination": "IN", "transport_mode": "road", **overrides})


def receipt():
    return asyncio.run(GreenChainProvider(ReferenceSourceClient("greenchain"), mode="reference").execute(request()))


@pytest.mark.parametrize("field,value", [("claims", {}), ("claims", [None]), ("estimates", "bad"),
    ("evidence_ids", "not-a-list"), ("evidence_ids", ["unknown"])])
def test_bridge_rejects_malformed_entity_proposals(field, value):
    result = receipt()
    result.entities[0].attributes[field] = value
    with pytest.raises(ValueError):
        to_echo_result(result)


@pytest.mark.parametrize("field,value", [("id", None), ("predicate", None), ("text", {}),
    ("subject_id", "another-entity"), ("kind", "verified"), ("evidence_ids", "string")])
def test_bridge_rejects_malformed_claim_proposals(field, value):
    result = receipt()
    result.entities[0].attributes["claims"][0][field] = value
    with pytest.raises(ValueError):
        to_echo_result(result)


def test_bridge_rejects_duplicate_evidence_and_missing_estimate_identity():
    result = receipt()
    claim = result.entities[0].attributes["claims"][0]
    claim["evidence_ids"] *= 2
    with pytest.raises(ValueError, match="duplicate"):
        to_echo_result(result)
    result = receipt()
    del result.entities[0].attributes["estimates"][0]["id"]
    with pytest.raises(ValueError, match="id and kind"):
        to_echo_result(result)


def test_bridge_naive_receipt_time_is_rejected_and_future_evidence_stays_unknown():
    result = receipt()
    result.raw_result["received_at"] = "2026-10-01T00:00:00"
    with pytest.raises(ValueError, match="timezone"):
        to_echo_result(result)
    result = receipt()
    result.raw_result["mode"] = "live"
    result.evidence[0].provenance_state = "known"
    result.evidence[0].source_uri = "https://supplier.example.org/source"
    result.evidence[0].observed_at = datetime.now(timezone.utc) + timedelta(days=2)
    normalized = to_echo_result(result)
    assert normalized.sources[0].provenance_state == "PROVENANCE_UNKNOWN"
    assert "FUTURE_SOURCE_TIMESTAMP" in normalized.warnings
    assert "INVALID_SOURCE_TIMESTAMP_ORDER" in normalized.warnings


class AlteredClient(ReferenceSourceClient):
    def __init__(self, project, change):
        super().__init__(project)
        change(self.data)


@pytest.mark.parametrize("change", ["boolean_count", "mode", "country", "partial_quantiles"])
def test_greenchain_context_and_partial_estimates_fail_closed(change):
    def alter(data):
        response = data["response"]
        if change == "boolean_count":
            response["count"] = True
        elif change == "mode":
            response["transport_mode"] = "air"
        elif change == "country":
            response["results"][0]["country"] = " "
        else:
            response["results"][0]["emission_factor"].update(q10_tco2e=100, q50_tco2e=None, q90_tco2e=1)
    result = asyncio.run(GreenChainProvider(AlteredClient("greenchain", alter)).execute(request()))
    assert not result.entities and not result.evidence
    assert result.raw_result["error_type"] == "ValueError"


@pytest.mark.parametrize("change", ["duplicate_catalog", "missing_retrieval", "duplicate_observation",
    "kind", "boolean_year", "wrong_year"])
def test_inflationforge_observation_identity_and_time_contract(change):
    def alter(data):
        if change == "duplicate_catalog":
            data["items"].append(deepcopy(data["items"][0]))
        elif change == "missing_retrieval":
            data["snapshot"].pop("retrieved_at")
        else:
            row = next(item for item in data["observations"] if item["item_id"] == "milk-gallon" and item["city_id"] == "chicago")
            if change == "duplicate_observation":
                data["observations"].append(deepcopy(row))
            elif change == "kind":
                row["kind"] = "UNKNOWN"
            elif change == "boolean_year":
                row["year"] = True
            else:
                row["year"] = 1900
    result = asyncio.run(InflationForgeProvider(AlteredClient("inflationforge", alter)).execute(
        request("price_intelligence", product="Milk", item_id="milk-gallon", city_id="chicago")))
    assert not result.entities and not result.evidence
    assert result.raw_result["error_type"] == "ValueError"


def test_future_and_archived_prices_are_labelled_without_becoming_current_quotes():
    future = datetime.now(timezone.utc) + timedelta(days=2)
    def alter(data):
        for row in data["observations"]:
            row.update(observed_at=future.isoformat(), retrieved_at=future.isoformat(), year=future.year, kind="ARCHIVED")
    result = asyncio.run(InflationForgeProvider(AlteredClient("inflationforge", alter)).execute(
        request("price_intelligence", product="Milk", item_id="milk-gallon", city_id="chicago")))
    assert result.entities and all(item.provenance_state == "unknown" for item in result.evidence)
    assert any(item.startswith("FUTURE_SOURCE_TIMESTAMP") for item in result.warnings)
    assert "HISTORICAL_OBSERVATION_NOT_CURRENT_QUOTE" in result.warnings
    assert all(not item.attributes["is_merchant_quote"] for item in result.entities)
    old = asyncio.run(InflationForgeProvider(ReferenceSourceClient("inflationforge")).execute(
        request("price_intelligence", product="Milk", item_id="milk-gallon", city_id="chicago")))
    assert any(item.startswith("STALE_PRICE_OBSERVATION") for item in old.warnings)
