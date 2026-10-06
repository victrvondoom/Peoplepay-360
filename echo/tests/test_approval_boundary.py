"""Owner, freshness and retry boundaries with real isolated graph persistence."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from echo import approval
from echo.demo_data import REQUIREMENT_ID
from echo.engine import EchoEngine
from echo.graph_store import EchoGraphStore
from echo.models import stable_id
from gateway.auth import issue_token


@pytest.fixture()
def isolated_store():
    store = EchoGraphStore(graph_name=f"echo_approval_test_{uuid4().hex}")
    try:
        assert store.ping()
    except Exception as exc:
        pytest.skip(f"FalkorDB unavailable: {exc}")
    try:
        yield store
    finally:
        store.graph.delete()


def request(identity="owner", authorization="Bearer caller-token"):
    return Request({"type": "http", "method": "POST", "path": "/approve",
                    "headers": [(b"x-beacon-user", identity.encode()),
                                (b"authorization", authorization.encode())]})


def recommendation(store):
    store.upsert_node("User", {"id": "owner"})
    store.upsert_node("Requirement", {"id": "approval-req", "user_id": "owner",
                                       "description": "Review two units", "quantity": 2,
                                       "budget_minor": 50000, "currency": "USD"})
    store.upsert_node("Supplier", {"id": "approval-supplier", "name": "Test supplier",
                                    "identity_status": "MATCHED", "synthetic": False})
    store.upsert_node("CandidatePolicy", {"id": "approval-policy", "requirement_id": "approval-req",
                                           "supplier_id": "approval-supplier", "raw_score": 80.0, "active": True})
    store.link("Requirement", "approval-req", "HAS_POLICY", "CandidatePolicy", "approval-policy")
    store.upsert_node("Claim", {"id": "approval-claim", "requirement_id": "approval-req", "kind": "fact"})
    store.link("Supplier", "approval-supplier", "HAS_CLAIM", "Claim", "approval-claim")
    for index in (1, 2, 3):
        source_id, evidence_id = f"approval-source-{index}", f"approval-evidence-{index}"
        store.upsert_node("Source", {"id": source_id, "active": True,
                                     "source_url": f"https://test-source-{index}.test/evidence",
                                     "provenance_state": "KNOWN", "synthetic": False})
        store.upsert_node("Evidence", {"id": evidence_id, "active": True, "confidence": 0.9,
                                       "observed_at": "2020-01-01T00:00:00+00:00",
                                       "provenance_state": "KNOWN", "verification_state": "UNVERIFIED"})
        store.link("Claim", "approval-claim", "SUPPORTED_BY", "Evidence", evidence_id)
        store.link("Evidence", evidence_id, "FROM_SOURCE", "Source", source_id)
    engine = EchoEngine(store)
    result = engine.analyze_requirement("approval-req")
    assert result["decision_status"] == "RECOMMEND"
    return engine, result["decision_id"]


def successful_gateway(calls):
    def post(path, payload, identity, authorization):
        calls.append((path, payload, identity, authorization))
        return {"id": "gateway-test-transaction", "state": "DRAFT"} if path == "/transactions" else {"state": "PLANNED"}
    return post


def test_synthetic_reassessment_cannot_create_gateway_transaction(isolated_store, monkeypatch):
    engine = EchoEngine(isolated_store)
    first = engine.run_false_consensus_demo()
    reassessed = engine.analyze_requirement(REQUIREMENT_ID, parent_decision_id=first["decision_id"])
    calls: list[Any] = []
    monkeypatch.setattr(approval, "gateway_post", successful_gateway(calls))
    with pytest.raises(HTTPException) as error:
        approval.approve(isolated_store, engine, reassessed["decision_id"], "echo-demo-user", request())
    assert error.value.status_code == 409
    assert calls == []


def test_owner_mismatch_cannot_approve_existing_recommendation(isolated_store, monkeypatch):
    engine, decision_id = recommendation(isolated_store)
    calls: list[Any] = []
    monkeypatch.setattr(approval, "gateway_post", successful_gateway(calls))
    with pytest.raises(HTTPException) as error:
        approval.approve(isolated_store, engine, decision_id, "other-owner", request("other-owner"))
    assert error.value.status_code == 404
    assert calls == []


@pytest.mark.parametrize("change", ["expiry", "source_revoke", "confidence", "dependency", "policy"])
def test_changed_decision_evidence_requires_new_human_review(isolated_store, monkeypatch, change):
    engine, decision_id = recommendation(isolated_store)
    if change == "expiry":
        isolated_store.upsert_node("Evidence", {"id": "approval-evidence-1", "valid_until": "2000-01-01T00:00:00+00:00"})
    elif change == "source_revoke":
        isolated_store.invalidate_source("approval-source-1", "revoked", datetime.now(timezone.utc).isoformat())
    elif change == "confidence":
        isolated_store.upsert_node("Evidence", {"id": "approval-evidence-1", "confidence": 0.1})
    elif change == "dependency":
        isolated_store.upsert_node("Source", {"id": "new-upstream", "provenance_state": "KNOWN", "active": True})
        isolated_store.link("Source", "approval-source-1", "DERIVED_FROM", "Source", "new-upstream")
    else:
        isolated_store.upsert_node("CandidatePolicy", {"id": "approval-policy", "raw_score": 70.0})
    calls: list[Any] = []
    monkeypatch.setattr(approval, "gateway_post", successful_gateway(calls))
    with pytest.raises(HTTPException) as error:
        approval.approve(isolated_store, engine, decision_id, "owner", request())
    assert error.value.status_code == 409
    assert calls == []


def test_plan_failure_retries_same_transaction_and_approved_replay_has_no_gateway_calls(isolated_store, monkeypatch):
    engine, decision_id = recommendation(isolated_store)
    calls = []
    fail_plan = [True]

    def post(path, payload, identity, authorization):
        calls.append((path, payload, identity, authorization))
        if path == "/transactions":
            return {"id": "gateway-test-transaction", "state": "DRAFT"}
        if fail_plan[0]:
            fail_plan[0] = False
            raise HTTPException(status_code=502, detail="fake gateway plan failure")
        return {"state": "PLANNED"}

    monkeypatch.setattr(approval, "gateway_post", post)
    with pytest.raises(HTTPException) as error:
        approval.approve(isolated_store, engine, decision_id, "owner", request())
    assert error.value.status_code == 502
    second = approval.approve(isolated_store, engine, decision_id, "owner", request())
    third = approval.approve(isolated_store, engine, decision_id, "owner", request())
    assert second["transaction_id"] == "gateway-test-transaction"
    assert third["idempotent_replay"] is True
    assert [call[0] for call in calls] == ["/transactions", "/transactions/gateway-test-transaction/plan", "/transactions/gateway-test-transaction/plan"]
    assert all(call[2:] == ("owner", "Bearer caller-token") for call in calls)


@pytest.mark.parametrize("bad_create", ["timeout", "no_transaction_id"])
def test_uncertain_creation_requires_reconciliation_and_never_creates_again(isolated_store, monkeypatch, bad_create):
    engine, decision_id = recommendation(isolated_store)
    calls = []

    def post(path, payload, identity, authorization):
        calls.append(path)
        if bad_create == "timeout":
            raise HTTPException(status_code=502, detail="fake gateway timeout")
        return {"state": "DRAFT"}

    monkeypatch.setattr(approval, "gateway_post", post)
    with pytest.raises(HTTPException) as first:
        approval.approve(isolated_store, engine, decision_id, "owner", request())
    assert first.value.status_code == 502
    with pytest.raises(HTTPException) as retry:
        approval.approve(isolated_store, engine, decision_id, "owner", request())
    assert retry.value.status_code == 409
    assert calls == ["/transactions"]
    rows = isolated_store.read_only_rows("MATCH (a:Approval {id: $id}) RETURN a.state",
                                         {"id": stable_id("approval", decision_id, "owner")})
    assert rows == [["RECONCILIATION_REQUIRED"]]


def test_verified_routes_reject_missing_authentication_and_body_impersonation(isolated_store, monkeypatch):
    monkeypatch.setenv("BEACON_GATEWAY_SECRET", "isolated-test-secret")
    monkeypatch.setenv("ECHO_ADMIN_TOKEN", "isolated-admin-secret")
    from echo import api
    monkeypatch.setattr(api, "store", isolated_store)
    monkeypatch.setattr(api, "engine", EchoEngine(isolated_store))
    client = TestClient(api.app)
    create = {"user_id": "owner", "description": "Two units", "quantity": 2, "budget_minor": 10000}
    assert client.post("/echo/requirements", json=create).status_code == 401
    assert client.post("/echo/decisions/does-not-exist/approve",
                       json={"user_id": "owner", "human_confirmation": True}).status_code == 401
    assert client.get("/echo/decisions/does-not-exist/trace").status_code == 401
    assert client.post("/echo/v1/extensions/execute", json={"request_id": "r", "capability": "supplier_discovery"}).status_code == 401
    assert client.post("/echo/sources/nonexistent/invalidate", json={"reason": "test"}).status_code == 401
    auth = {"Authorization": "Bearer " + issue_token("owner"), "X-Beacon-User": "other-owner"}
    assert client.post("/echo/requirements", json=create, headers=auth).status_code == 201
    create["user_id"] = "other-owner"
    assert client.post("/echo/requirements", json=create, headers=auth).status_code == 403
    assert client.post("/echo/decisions/nonexistent/approve",
                       json={"user_id": "other-owner", "human_confirmation": True}, headers=auth).status_code == 403
    assert client.post("/echo/decisions/nonexistent/approve",
                       json={"user_id": "owner", "human_confirmation": "true"}, headers=auth).status_code == 422
    large = client.post("/echo/v1/extensions/execute", content=b"x" * 65537)
    assert large.status_code == 413
