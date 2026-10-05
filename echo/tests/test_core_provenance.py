"""Regression checks use disposable graphs, never the operator's ECHO graph."""

import json
from uuid import uuid4

import pytest

from echo.demo_data import DEMO_SCOPE, REQUIREMENT_ID
from echo.engine import EchoEngine
from echo.graph_store import EchoGraphStore


@pytest.fixture()
def isolated_store():
    store = EchoGraphStore(graph_name=f"echo_core_test_{uuid4().hex}")
    try:
        assert store.ping()
    except Exception as exc:
        pytest.skip(f"FalkorDB unavailable: {exc}")
    try:
        yield store
    finally:
        # This graph name was generated for this test; no shared graph is deleted.
        store.graph.delete()


def requirement(store, requirement_id="test-requirement"):
    store.upsert_node("Requirement", {"id": requirement_id, "user_id": "test-owner"})
    return requirement_id


def supplier(store, requirement_id, supplier_id="test-supplier", raw_score=80,
             identity_status="MATCHED", policy=True):
    store.upsert_node("Supplier", {"id": supplier_id, "name": supplier_id,
                                   "identity_status": identity_status, "raw_score": 99})
    if policy:
        policy_id = f"policy-{requirement_id}-{supplier_id}"
        store.upsert_node("CandidatePolicy", {"id": policy_id,
                                               "requirement_id": requirement_id,
                                               "supplier_id": supplier_id,
                                               "raw_score": raw_score, "active": True})
        store.link("Requirement", requirement_id, "HAS_POLICY", "CandidatePolicy", policy_id)
    return supplier_id


def observation(store, requirement_id, supplier_id, index, *, claim_id=None,
                evidence_id=None, source_id=None, confidence=0.9,
                provenance_state="KNOWN", **evidence_props):
    claim_id = claim_id or f"claim-{index}"
    evidence_id = evidence_id or f"evidence-{index}"
    source_id = source_id or f"source-{index}"
    store.upsert_node("Claim", {"id": claim_id, "requirement_id": requirement_id})
    store.link("Supplier", supplier_id, "HAS_CLAIM", "Claim", claim_id)
    store.upsert_node("Source", {"id": source_id, "active": True,
                                 "provenance_state": provenance_state,
                                 "source_url": f"https://{source_id}.example/evidence"})
    store.upsert_node("Evidence", {"id": evidence_id, "active": True,
                                   "confidence": confidence, "observed_at": "2020-01-01T00:00:00+00:00",
                                   "content_hash": f"hash-{index}", "provenance_state": "KNOWN", **evidence_props})
    store.link("Claim", claim_id, "SUPPORTED_BY", "Evidence", evidence_id)
    store.link("Evidence", evidence_id, "FROM_SOURCE", "Source", source_id)
    return claim_id, evidence_id, source_id


def test_demo_reassessment_preserves_synthetic_scope(isolated_store):
    engine = EchoEngine(isolated_store)
    demo = engine.run_false_consensus_demo()
    revised = engine.analyze_requirement(REQUIREMENT_ID, parent_decision_id=demo["decision_id"])
    rows = isolated_store.read_only_rows(
        "MATCH (d:Decision {id: $id}) RETURN d.demo_scope, d.user_id",
        {"id": revised["decision_id"]},
    )
    assert rows == [[DEMO_SCOPE, "echo-demo-user"]]
    assert revised["recommended_supplier_id"] == "supplier-beta-demo"


def test_trace_is_candidate_scoped_and_immutable(isolated_store):
    engine = EchoEngine(isolated_store)
    result = engine.run_false_consensus_demo()
    before = isolated_store.query_file("05_decision_trace.cypher", {"decision_id": result["decision_id"]})
    traces = {row[4]: json.loads(row[8]) for row in before}
    assert len(traces["supplier-alpha-demo"]) == 8
    assert len(traces["supplier-beta-demo"]) == 3
    assert len(traces["supplier-gamma-demo"]) == 1
    assert all(path["source_id"].startswith("source-alpha") for path in traces["supplier-alpha-demo"])
    isolated_store.invalidate_source("source-beta-root-1", "test revoked source", "2030-01-01T00:00:00+00:00")
    engine.analyze_requirement(REQUIREMENT_ID, parent_decision_id=result["decision_id"])
    after = isolated_store.query_file("05_decision_trace.cypher", {"decision_id": result["decision_id"]})
    assert {row[4]: row[8] for row in after} == {row[4]: row[8] for row in before}


def test_multiple_claims_create_one_supplier_candidate_and_deduplicate_evidence(isolated_store):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    observation(isolated_store, req, sid, 1, claim_id="first", evidence_id="same", confidence=0.8)
    observation(isolated_store, req, sid, 1, claim_id="second", evidence_id="same", confidence=0.8)
    observation(isolated_store, req, sid, 2, claim_id="third", confidence=1.0)
    result = EchoEngine(isolated_store).analyze_requirement(req)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["apparent_support_count"] == 2
    assert candidate["provenance_root_count"] == 2
    assert candidate["mean_confidence"] == pytest.approx(0.9)
    assert candidate["claim_ids"] == ("first", "second", "third")
    rows = isolated_store.read_only_rows(
        "MATCH (d:Decision {id: $id})-[:CONSIDERED]->(c) RETURN count(c)",
        {"id": result["decision_id"]},
    )
    assert rows == [[1]]


def test_expired_future_and_inactive_sources_are_excluded(isolated_store):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    observation(isolated_store, req, sid, "current")
    observation(isolated_store, req, sid, "expired", valid_until="2001-01-01T00:00:00+00:00")
    observation(isolated_store, req, sid, "future", valid_from="2100-01-01T00:00:00+00:00")
    _, _, inactive_source = observation(isolated_store, req, sid, "inactive")
    isolated_store.invalidate_source(inactive_source, "test", "2020-01-01T00:00:00+00:00")
    result = EchoEngine(isolated_store).analyze_requirement(req)
    assert result["decision_status"] == "ABSTAIN"
    assert result["candidates"][0]["apparent_support_count"] == 1
    assert result["candidates"][0]["provenance_root_count"] == 1


def test_unknown_source_provenance_is_not_a_terminal_root(isolated_store):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    observation(isolated_store, req, sid, 1, provenance_state="UNKNOWN")
    observation(isolated_store, req, sid, 2, provenance_state="UNKNOWN")
    result = EchoEngine(isolated_store).analyze_requirement(req)
    assert result["decision_status"] == "ABSTAIN"
    candidate = result["candidates"][0]
    assert candidate["provenance_root_count"] == 0
    assert candidate["unresolved_provenance_count"] == 2


@pytest.mark.parametrize("failure", ["inactive_intermediate", "cycle", "depth_limit"])
def test_unresolved_dependency_paths_require_review(isolated_store, failure):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    _, _, first = observation(isolated_store, req, sid, "first")
    observation(isolated_store, req, sid, "independent")
    count = 10 if failure == "depth_limit" else 2
    previous = first
    for index in range(count):
        source_id = f"upstream-{index}"
        isolated_store.upsert_node("Source", {"id": source_id, "active": True,
                                               "provenance_state": "KNOWN"})
        isolated_store.link("Source", previous, "DERIVED_FROM", "Source", source_id)
        previous = source_id
    if failure == "inactive_intermediate":
        isolated_store.invalidate_source("upstream-0", "test", "2020-01-01T00:00:00+00:00")
    elif failure == "cycle":
        isolated_store.link("Source", previous, "MIRRORS", "Source", first)
    result = EchoEngine(isolated_store).analyze_requirement(req)
    assert result["decision_status"] == "ABSTAIN"
    assert result["candidates"][0]["unresolved_provenance_count"] == 1


def test_nondemo_candidate_requires_requirement_policy_and_matched_identity(isolated_store):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req, policy=False)
    observation(isolated_store, req, sid, 1)
    observation(isolated_store, req, sid, 2)
    engine = EchoEngine(isolated_store)
    assert engine.analyze_requirement(req)["decision_status"] == "ABSTAIN"
    supplier(isolated_store, "another-requirement", sid, raw_score=99)
    assert engine.analyze_requirement(req)["decision_status"] == "ABSTAIN"
    supplier(isolated_store, req, sid, raw_score=70, identity_status="AMBIGUOUS")
    assert engine.analyze_requirement(req)["decision_status"] == "ABSTAIN"
    supplier(isolated_store, req, sid, raw_score=70)
    result = engine.analyze_requirement(req)
    assert result["decision_status"] == "RECOMMEND"
    assert result["candidates"][0]["raw_score"] == 70


@pytest.mark.parametrize("branch_state", ["UNKNOWN", "INACTIVE", "CYCLE"])
def test_resolved_branch_does_not_hide_unresolved_dependency_branch(isolated_store, branch_state):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    _, _, first = observation(isolated_store, req, sid, "first")
    observation(isolated_store, req, sid, "independent")
    isolated_store.upsert_node("Source", {"id": "known-root", "active": True,
                                           "provenance_state": "KNOWN"})
    isolated_store.link("Source", first, "DERIVED_FROM", "Source", "known-root")
    isolated_store.upsert_node("Source", {"id": "bad-branch", "active": branch_state != "INACTIVE",
                                           "provenance_state": "UNKNOWN" if branch_state == "UNKNOWN" else "KNOWN"})
    isolated_store.link("Source", first, "CITES", "Source", "bad-branch")
    if branch_state == "CYCLE":
        isolated_store.link("Source", "bad-branch", "MIRRORS", "Source", first)
    result = EchoEngine(isolated_store).analyze_requirement(req)
    candidate = result["candidates"][0]
    assert candidate["provenance_root_count"] == 2
    assert candidate["unresolved_provenance_count"] == 1
    assert result["decision_status"] == "ABSTAIN"


def test_empty_requirement_persists_abstention_and_owner(isolated_store):
    req = requirement(isolated_store)
    result = EchoEngine(isolated_store).analyze_requirement(req)
    assert result["decision_status"] == "ABSTAIN"
    assert result["candidates"] == []
    rows = isolated_store.read_only_rows(
        "MATCH (d:Decision {id: $id}) RETURN d.status, d.requirement_id, d.user_id",
        {"id": result["decision_id"]},
    )
    assert rows == [["ABSTAIN", req, "test-owner"]]
    trace = isolated_store.query_file("05_decision_trace.cypher", {"decision_id": result["decision_id"]})
    assert len(trace) == 1 and trace[0][3] is None


@pytest.mark.parametrize("problem", ["unknown_evidence", "missing_observation_time", "conflict", "model_output", "model_evidence"])
def test_known_source_does_not_upgrade_problematic_claim_evidence(isolated_store, problem):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    claim_id, evidence_id, _ = observation(isolated_store, req, sid, "problem")
    observation(isolated_store, req, sid, "known")
    if problem == "unknown_evidence":
        isolated_store.upsert_node("Evidence", {"id": evidence_id, "provenance_state": "UNKNOWN"})
    elif problem == "missing_observation_time":
        isolated_store.graph.query(
            "MATCH (e:Evidence {id: $id}) SET e.observed_at = NULL", params={"id": evidence_id}
        )
    elif problem == "conflict":
        isolated_store.upsert_node("Claim", {"id": claim_id, "conflict_open": True})
    elif problem == "model_output":
        isolated_store.upsert_node("Claim", {"id": claim_id, "kind": "model_output"})
    else:
        isolated_store.upsert_node("Evidence", {"id": evidence_id, "verification_state": "MODEL_OUTPUT"})
    result = EchoEngine(isolated_store).analyze_requirement(req)
    assert result["candidates"][0]["provenance_root_count"] == 2
    assert result["candidates"][0]["unresolved_provenance_count"] == 1
    assert result["decision_status"] == "ABSTAIN"


def test_multiple_extension_producers_are_preserved_without_inflating_support(isolated_store):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    _, evidence_id, _ = observation(isolated_store, req, sid, "shared")
    observation(isolated_store, req, sid, "other")
    for run_id in ("extension-run-a", "extension-run-b"):
        isolated_store.upsert_node("ExtensionRun", {"id": run_id})
        isolated_store.link("ExtensionRun", run_id, "OBSERVED", "Evidence", evidence_id)
    result = EchoEngine(isolated_store).analyze_requirement(req)
    candidate = result["candidates"][0]
    assert candidate["apparent_support_count"] == 2
    assert candidate["provenance_root_count"] == 2
    assert {path["extension_run_id"] for path in candidate["evidence_paths"]
            if path["evidence_id"] == evidence_id} == {"extension-run-a", "extension-run-b"}
    trace = isolated_store.query_file("05_decision_trace.cypher", {"decision_id": result["decision_id"]})
    snapshot = json.loads(trace[0][8])
    assert {path["extension_run_id"] for path in snapshot if path["evidence_id"] == evidence_id} == {
        "extension-run-a", "extension-run-b"
    }


def test_historical_source_impact_uses_frozen_dependency_path(isolated_store):
    req = requirement(isolated_store)
    sid = supplier(isolated_store, req)
    _, _, leaf = observation(isolated_store, req, sid, "leaf")
    observation(isolated_store, req, sid, "independent")
    for source_id in ("middle", "terminal"):
        isolated_store.upsert_node("Source", {"id": source_id, "active": True, "provenance_state": "KNOWN"})
    edge_one = isolated_store.link("Source", leaf, "DERIVED_FROM", "Source", "middle")
    edge_two = isolated_store.link("Source", "middle", "CITES", "Source", "terminal")
    result = EchoEngine(isolated_store).analyze_requirement(req)
    snapshot = result["candidates"][0]["evidence_paths"]
    derived_path = next(path for path in snapshot if path["source_id"] == leaf)
    assert derived_path["path_source_ids"] == [leaf, "middle", "terminal"]
    assert derived_path["dependency_edge_ids"] == [edge_one, edge_two]
    impacted = isolated_store.query_file("06_impacted_decisions.cypher", {"source_id": "middle"})
    assert any(row[0] == result["decision_id"] for row in impacted)
    isolated_store.upsert_node("Source", {"id": "later-root", "active": True, "provenance_state": "KNOWN"})
    isolated_store.link("Source", "terminal", "DERIVED_FROM", "Source", "later-root")
    later_impacted = isolated_store.query_file("06_impacted_decisions.cypher", {"source_id": "later-root"})
    assert later_impacted == []
    trace = isolated_store.query_file("05_decision_trace.cypher", {"decision_id": result["decision_id"]})
    frozen = next(path for path in json.loads(trace[0][8]) if path["source_id"] == leaf)
    assert frozen["path_source_ids"] == [leaf, "middle", "terminal"]
