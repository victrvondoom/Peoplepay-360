"""Explicit owner approval, current evidence gate, and recoverable Gateway planning."""

import http.client
import json
import os
from datetime import datetime, timezone
from threading import RLock
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from echo.engine import EchoEngine
from echo.graph_store import EchoGraphStore
from echo.models import stable_id

APPROVAL_LOCK = RLock()


def gateway_post(path: str, payload: dict, identity: str, authorization: str | None) -> dict:
    endpoint = os.getenv("PEOPLEPAY_GATEWAY_URL", "http://127.0.0.1:8080")
    parts = urlsplit(endpoint)
    if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in {"", "/"}):
        raise HTTPException(status_code=503, detail="PeoplePay gateway configuration is invalid")
    headers = {"Content-Type": "application/json", "X-Beacon-User": identity}
    if authorization:
        # Forward the authenticated caller's identity, never a global user-impersonating token.
        headers["Authorization"] = authorization
    connection = (http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection)(
        parts.hostname, port=parts.port, timeout=8,
    )
    try:
        connection.request("POST", path, body=json.dumps(payload).encode(), headers=headers)
        response = connection.getresponse()
        data = response.read(262145)
        if not 200 <= response.status < 300 or len(data) > 262144:
            raise ValueError("gateway request was unsuccessful")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("gateway result was not an object")
        return result
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="PeoplePay gateway did not confirm the planning request") from exc
    finally:
        connection.close()


def approve(store: EchoGraphStore, engine: EchoEngine, decision_id: str,
            identity: str, request: Request) -> dict:
    with APPROVAL_LOCK:
        rows = store.read_only_rows(
            "MATCH (d:Decision {id: $id, user_id: $user}) "
            "MATCH (r:Requirement {id: d.requirement_id, user_id: $user}) "
            "RETURN d.requirement_id, d.status, d.recommended_supplier_id, d.demo_scope, "
            "d.evidence_stale, r.demo_scope, r.description, r.quantity, r.budget_minor, r.currency",
            {"id": decision_id, "user": identity},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="decision not found")
        requirement_id, status, supplier_id, scope, stale, req_scope, description, quantity, budget, currency = rows[0]
        if scope or req_scope:
            raise HTTPException(status_code=409, detail="synthetic decisions cannot create transactions")
        if status != "RECOMMEND" or not supplier_id or stale:
            raise HTTPException(status_code=409, detail="decision requires fresh evidence review")
        synthetic = store.read_only_rows(
            "MATCH (d:Decision {id: $id})-[:CONSIDERED]->(c:DecisionCandidate) "
            "OPTIONAL MATCH (c)-[:USED_SOURCE]->(s:Source) "
            "RETURN max(CASE WHEN s.synthetic = true OR s.demo_scope IS NOT NULL THEN 1 ELSE 0 END)",
            {"id": decision_id},
        )
        if synthetic and synthetic[0][0]:
            raise HTTPException(status_code=409, detail="synthetic evidence cannot create transactions")
        if budget is None:
            raise HTTPException(status_code=409, detail="a user-approved budget is required")
        approval_id = stable_id("approval", decision_id, identity)
        previous = store.read_only_rows(
            "MATCH (a:Approval {id: $id}) RETURN a.state, a.transaction_id, a.result_json",
            {"id": approval_id},
        )
        if previous and previous[0][0] == "APPROVED":
            return {**json.loads(previous[0][2]), "idempotent_replay": True}
        if previous and previous[0][0] in {"CREATE_IN_FLIGHT", "RECONCILIATION_REQUIRED"}:
            raise HTTPException(status_code=409, detail="gateway creation needs reconciliation before retry")
        # Re-evaluate at the approval boundary; freshness or conflicts can change eligibility.
        current = engine.analyze_requirement(requirement_id, parent_decision_id=decision_id)
        if current["decision_status"] != "RECOMMEND" or current["recommended_supplier_id"] != supplier_id:
            raise HTTPException(status_code=409, detail="evidence changed; review the new decision before approval")
        snapshot = store.read_only_rows(
            "MATCH (d:Decision {id: $id})-[:CONSIDERED]->(c:DecisionCandidate {supplier_id: $supplier}) "
            "RETURN c.evidence_snapshot_json, c.raw_score, d.scoring_policy_json", {"id": decision_id, "supplier": supplier_id},
        )
        current_candidate = next(c for c in current["candidates"] if c["supplier_id"] == supplier_id)
        def semantics(paths):
            fields = ("claim_id", "evidence_id", "source_id", "root_source_id", "path_source_ids",
                      "dependency_edge_ids", "confidence", "observed_at", "valid_from", "valid_until",
                      "snapshot_id", "content_hash", "provenance_state", "lineage_unresolved")
            return {json.dumps({key: path.get(key) for key in fields}, sort_keys=True) for path in paths}
        original_paths = json.loads(snapshot[0][0]) if snapshot else []
        if (not snapshot or semantics(original_paths) != semantics(current_candidate["evidence_paths"])
                or snapshot[0][1] != current_candidate["raw_score"]
                or json.loads(snapshot[0][2]) != current["scoring_policy"]):
            raise HTTPException(status_code=409, detail="decision evidence changed; review the new decision")
        now = datetime.now(timezone.utc).isoformat()
        transaction_id = previous[0][1] if previous else None
        if not transaction_id:
            store.upsert_node("Approval", {"id": approval_id, "decision_id": decision_id,
                                            "user_id": identity, "human_confirmed": True,
                                            "state": "CREATE_IN_FLIGHT", "requested_at": now})
            store.link("Decision", decision_id, "HAS_APPROVAL", "Approval", approval_id)
            store.link("Approval", approval_id, "APPROVED_BY", "User", identity)
            try:
                transaction = gateway_post("/transactions", {"raw_utterance": description},
                                           identity, request.headers.get("Authorization"))
                transaction_id = transaction.get("id")
                if not isinstance(transaction_id, str) or not transaction_id:
                    raise HTTPException(status_code=502, detail="gateway returned no transaction id")
            except HTTPException:
                store.upsert_node("Approval", {"id": approval_id, "state": "RECONCILIATION_REQUIRED"})
                raise
            store.upsert_node("Approval", {"id": approval_id, "state": "PLAN_PENDING", "transaction_id": transaction_id})
            store.upsert_node("Transaction", {"id": transaction_id, "requirement_id": requirement_id,
                                               "decision_id": decision_id, "supplier_id": supplier_id,
                                               "gateway_state": "DRAFT", "created_at": now, "money_moved": False})
            store.link("Decision", decision_id, "CREATED", "Transaction", transaction_id)
        plan = gateway_post(f"/transactions/{transaction_id}/plan", {
            "summary": f"Compare {quantity} units from ECHO recommendation {supplier_id}",
            "steps": ["Review supplier evidence and quote", "Confirm price, availability and delivery"],
            "amount_minor": int(budget), "currency": currency,
        }, identity, request.headers.get("Authorization"))
        result = {"decision_id": decision_id, "approval_id": approval_id, "transaction_id": transaction_id,
                  "plan": plan, "money_moved": False, "idempotent_replay": False}
        store.upsert_node("Approval", {"id": approval_id, "state": "APPROVED", "approved_at": now,
                                        "result_json": json.dumps(result, sort_keys=True)})
        store.upsert_node("Transaction", {"id": transaction_id, "gateway_state": "PLANNED"})
        return result
