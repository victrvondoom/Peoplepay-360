"""FalkorDB graph access. Query text is fixed; all user/data values are params."""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from falkordb import FalkorDB  # type: ignore[import-untyped]  # Upstream ships no type marker.

from echo.models import stable_id

QUERY_DIR = Path(__file__).parent / "queries"
DEPENDENCY_TYPES = {"DERIVED_FROM", "CITES", "MIRRORS"}

NODE_QUERIES = {
    label: f"MERGE (n:{label} {{id: $id}}) SET n += $props RETURN n.id"
    for label in (
        "User", "Requirement", "Agent", "AgentRun", "Supplier", "Product", "Offer",
        "Claim", "Evidence", "Source", "SourceSnapshot", "Certification", "RiskSignal",
        "PriceObservation", "DeliveryPromise", "Decision", "DecisionCandidate", "Approval",
        "Transaction", "Order", "DeliveryEvent", "Dispute", "Policy", "CandidatePolicy",
        "Extension", "ExtensionVersion", "ExtensionRun", "IngestionEvent",
        "EntityRepresentation", "Organization", "Place", "ExtensionObservation",
    )
}

RELATION_QUERIES = {
    "CREATED": "MERGE (a)-[r:CREATED {id: $rel_id}]->(b)",
    "FOR_PRODUCT": "MERGE (a)-[r:FOR_PRODUCT {id: $rel_id}]->(b)",
    "EXECUTED": "MERGE (a)-[r:EXECUTED {id: $rel_id}]->(b)",
    "OBSERVED": "MERGE (a)-[r:OBSERVED {id: $rel_id}]->(b)",
    "PRODUCED": "MERGE (a)-[r:PRODUCED {id: $rel_id}]->(b)",
    "HAS_CLAIM": "MERGE (a)-[r:HAS_CLAIM {id: $rel_id}]->(b)",
    "ABOUT": "MERGE (a)-[r:ABOUT {id: $rel_id}]->(b)",
    "SUPPORTED_BY": "MERGE (a)-[r:SUPPORTED_BY {id: $rel_id}]->(b)",
    "CONTRADICTS": "MERGE (a)-[r:CONTRADICTS {id: $rel_id}]->(b)",
    "FROM_SOURCE": "MERGE (a)-[r:FROM_SOURCE {id: $rel_id}]->(b)",
    "OBSERVED_AT": "MERGE (a)-[r:OBSERVED_AT {id: $rel_id}]->(b)",
    "DERIVED_FROM": "MERGE (a)-[r:DERIVED_FROM {id: $rel_id}]->(b)",
    "CITES": "MERGE (a)-[r:CITES {id: $rel_id}]->(b)",
    "MIRRORS": "MERGE (a)-[r:MIRRORS {id: $rel_id}]->(b)",
    "OFFERED_BY": "MERGE (a)-[r:OFFERED_BY {id: $rel_id}]->(b)",
    "FOR_SUPPLIER": "MERGE (a)-[r:FOR_SUPPLIER {id: $rel_id}]->(b)",
    "CONSIDERED": "MERGE (a)-[r:CONSIDERED {id: $rel_id}]->(b)",
    "REPRESENTS": "MERGE (a)-[r:REPRESENTS {id: $rel_id}]->(b)",
    "USED_CLAIM": "MERGE (a)-[r:USED_CLAIM {id: $rel_id}]->(b)",
    "APPROVED_BY": "MERGE (a)-[r:APPROVED_BY {id: $rel_id}]->(b)",
    "HAS_APPROVAL": "MERGE (a)-[r:HAS_APPROVAL {id: $rel_id}]->(b)",
    "REASSESSES": "MERGE (a)-[r:REASSESSES {id: $rel_id}]->(b)",
    "HAS_CERTIFICATION": "MERGE (a)-[r:HAS_CERTIFICATION {id: $rel_id}]->(b)",
    "CERTIFIES": "MERGE (a)-[r:CERTIFIES {id: $rel_id}]->(b)",
    "INVALIDATES": "MERGE (a)-[r:INVALIDATES {id: $rel_id}]->(b)",
    "HAS_EVENT": "MERGE (a)-[r:HAS_EVENT {id: $rel_id}]->(b)",
    "CREATED_ORDER": "MERGE (a)-[r:CREATED_ORDER {id: $rel_id}]->(b)",
    "ABOUT_TRANSACTION": "MERGE (a)-[r:ABOUT_TRANSACTION {id: $rel_id}]->(b)",
    "REFERENCES": "MERGE (a)-[r:REFERENCES {id: $rel_id}]->(b)",
    "HAS_VERSION": "MERGE (a)-[r:HAS_VERSION {id: $rel_id}]->(b)",
    "HAS_POLICY": "MERGE (a)-[r:HAS_POLICY {id: $rel_id}]->(b)",
    "RESOLVES_TO": "MERGE (a)-[r:RESOLVES_TO {id: $rel_id}]->(b)",
    "INGESTED": "MERGE (a)-[r:INGESTED {id: $rel_id}]->(b)",
    "USED_SOURCE": "MERGE (a)-[r:USED_SOURCE {id: $rel_id}]->(b)",
    "USED_EVIDENCE": "MERGE (a)-[r:USED_EVIDENCE {id: $rel_id}]->(b)",
}


class EchoGraphStore:
    """Narrow persistence seam around one named FalkorDB property graph."""

    def __init__(self, *, host: str | None = None, port: int | None = None,
                 graph_name: str | None = None, password: str | None = None) -> None:
        self.host = host or os.getenv("ECHO_FALKORDB_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("ECHO_FALKORDB_PORT", "16380"))
        self.graph_name = graph_name or os.getenv("ECHO_GRAPH_NAME", "peoplepay_echo")
        self.password = password if password is not None else os.getenv("ECHO_FALKORDB_PASSWORD")
        self._client: FalkorDB | None = None
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            self._client = FalkorDB(host=self.host, port=self.port, password=self.password)
            self._graph = self._client.select_graph(self.graph_name)
        return self._graph

    def ping(self) -> bool:
        result = self.graph.query("RETURN 1 AS ok")
        return bool(result.result_set and result.result_set[0][0] == 1)

    def query_file(self, name: str, params: dict[str, Any]) -> list[list[Any]]:
        query = (QUERY_DIR / name).read_text(encoding="utf-8")
        bound = {"as_of": datetime.now(timezone.utc).isoformat(), **params}
        return self.graph.ro_query(query, params=bound, timeout=5000).result_set

    def clear_demo_scope(self, scope: str) -> None:
        self.graph.query("MATCH (n) WHERE n.demo_scope = $scope DETACH DELETE n",
                         params={"scope": scope}, timeout=10000)

    def upsert_node(self, label: str, props: dict[str, Any]) -> None:
        query = NODE_QUERIES.get(label)
        if query is None:
            raise ValueError(f"unrecognized graph node label: {label}")
        clean = {key: value for key, value in props.items() if value is not None}
        self.graph.query(query, params={"id": clean["id"], "props": clean}, timeout=5000)

    def link(self, from_label: str, from_id: str, relationship: str,
             to_label: str, to_id: str, props: dict[str, Any] | None = None) -> str:
        rel_query = RELATION_QUERIES.get(relationship)
        if rel_query is None:
            raise ValueError(f"unrecognized graph relationship: {relationship}")
        if from_label not in NODE_QUERIES or to_label not in NODE_QUERIES:
            raise ValueError("unrecognized graph node label")
        rel_id = stable_id("edge", relationship, from_id, to_id)
        query = (
            f"MATCH (a:{from_label} {{id: $from_id}}), (b:{to_label} {{id: $to_id}}) "
            f"{rel_query} SET r += $props RETURN r.id"
        )
        self.graph.query(query, params={
            "from_id": from_id, "to_id": to_id, "rel_id": rel_id,
            "props": {**(props or {}), "id": rel_id},
        }, timeout=5000)
        return rel_id

    def create_decision(self, decision: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
        self.upsert_node("Decision", decision)
        if decision.get("parent_decision_id"):
            self.link("Decision", decision["id"], "REASSESSES",
                      "Decision", decision["parent_decision_id"])
        for candidate in candidates:
            self.upsert_node("DecisionCandidate", candidate)
            self.link("Decision", decision["id"], "CONSIDERED",
                      "DecisionCandidate", candidate["id"])
            self.link("DecisionCandidate", candidate["id"], "REPRESENTS",
                      "Supplier", candidate["supplier_id"])
            if candidate.get("claim_id"):
                self.link("Decision", decision["id"], "USED_CLAIM",
                          "Claim", candidate["claim_id"])
            for claim_id in json.loads(candidate.get("claim_ids_json", "[]")):
                self.link("Decision", decision["id"], "USED_CLAIM", "Claim", claim_id)
            for path in json.loads(candidate.get("evidence_snapshot_json", "[]")):
                for source_id in ({path.get("source_id"), path.get("root_source_id")}
                                  | set(path.get("path_source_ids") or [])) - {None}:
                    self.link("DecisionCandidate", candidate["id"], "USED_SOURCE", "Source", source_id)
                if path.get("evidence_id"):
                    self.link("DecisionCandidate", candidate["id"], "USED_EVIDENCE",
                              "Evidence", path["evidence_id"])

    def apply_extension_batch(self, *, requirement_id: str, user_id: str, event_id: str,
                              result_hash: str, nodes: dict[str, list[dict[str, Any]]],
                              edges: list[dict[str, Any]], event: dict[str, Any]) -> bool:
        """Apply a core-built proposal batch in one serialized graph statement.

        Values are bound parameters; only labels and edges from core whitelists
        are used to form query templates. Extensions never call this interface.
        Existing source/evidence properties remain immutable on repeated ingestion.
        """
        params: dict[str, Any] = {"requirement_id": requirement_id, "user_id": user_id,
                                  "event_id": event_id, "result_hash": result_hash,
                                  "event": event}
        clauses = [
            "MATCH (requirement:Requirement {id: $requirement_id, user_id: $user_id})",
            "MERGE (event:IngestionEvent {id: $event_id}) "
            "ON CREATE SET event += $event, event.result_hash = $result_hash, event.applied = false",
            "WITH event WHERE event.result_hash = $result_hash AND event.applied = false",
        ]
        for index, (label, records) in enumerate(nodes.items()):
            if label not in NODE_QUERIES:
                raise ValueError("proposal batch contains a noncanonical graph label")
            if not records:
                continue
            key = f"nodes_{index}"
            params[key] = [{k: v for k, v in item.items() if v is not None} for item in records]
            clauses.append(f"UNWIND ${key} AS props MERGE (node:{label} {{id: props.id}}) "
                           "ON CREATE SET node += props")
            if label == "Claim":
                clauses.append("SET node.conflict_open = coalesce(node.conflict_open, false) OR coalesce(props.conflict_open, false)")
            clauses.append("WITH DISTINCT event")
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for edge in edges:
            triple = (edge["from_label"], edge["type"], edge["to_label"])
            if triple[0] not in NODE_QUERIES or triple[2] not in NODE_QUERIES or triple[1] not in RELATION_QUERIES:
                raise ValueError("proposal batch contains a noncanonical graph relationship")
            grouped.setdefault(triple, []).append(edge)
        for index, ((from_label, relationship, to_label), records) in enumerate(grouped.items()):
            key = f"edges_{index}"
            params[key] = records
            clauses.extend([
                f"UNWIND ${key} AS edge MATCH (a:{from_label} {{id: edge.from_id}}), (b:{to_label} {{id: edge.to_id}})",
                f"MERGE (a)-[rel:{relationship} {{id: edge.id}}]->(b) ON CREATE SET rel += edge.props",
                "WITH DISTINCT event",
            ])
        clauses.append("SET event.applied = true RETURN event.id")
        result = self.graph.query(" ".join(clauses), params=params, timeout=10000)
        return bool(result.result_set)

    def add_fixture(self, fixture: dict[str, Any]) -> None:
        """Load only the fixed, clearly marked synthetic demonstration fixture."""
        scope = fixture["requirement"]["demo_scope"]
        # The graph name is dedicated to ECHO; only nodes in this exact synthetic namespace are reset.
        self.graph.query("MERGE (v:SchemaVersion {id: 'echo'}) SET v.version = 1")
        self.clear_demo_scope(scope)
        self.upsert_node("User", {"id": fixture["requirement"]["user_id"],
                                   "display_name": "Synthetic demo user", "demo_scope": scope})
        self.upsert_node("Requirement", fixture["requirement"])
        self.link("User", fixture["requirement"]["user_id"], "CREATED",
                  "Requirement", fixture["requirement"]["id"])
        self.upsert_node("Product", fixture["product"])
        self.link("Requirement", fixture["requirement"]["id"], "FOR_PRODUCT",
                  "Product", fixture["product"]["id"])
        for agent in fixture["agents"]:
            self.upsert_node("Agent", agent)
        for run in fixture["runs"]:
            self.upsert_node("AgentRun", run)
            self.link("Agent", run["agent_id"], "EXECUTED", "AgentRun", run["id"])
        for supplier in fixture["suppliers"]:
            self.upsert_node("Supplier", supplier)
            self.link("Product", fixture["product"]["id"], "OFFERED_BY",
                      "Supplier", supplier["id"])
        claims_by_id = {claim["id"]: claim for claim in fixture["claims"]}
        suppliers_by_id = {item["id"]: item for item in fixture["suppliers"]}
        for claim in fixture["claims"]:
            self.upsert_node("Claim", claim)
            supplier_id = next(
                sid for sid, cid in fixture["claim_by_supplier"].items() if cid == claim["id"]
            )
            self.link("Supplier", supplier_id, "HAS_CLAIM", "Claim", claim["id"])
            self.link("Claim", claim["id"], "ABOUT", "Supplier", supplier_id)
            self.link("Claim", claim["id"], "ABOUT", "Product", fixture["product"]["id"])
        for source in fixture["sources"]:
            from echo.models import normalize_source_url

            source = {**source, "source_url": normalize_source_url(source["source_url"])}
            self.upsert_node("Source", source)
            snapshot_id = stable_id("snapshot", source["id"], source["content_hash"])
            self.upsert_node("SourceSnapshot", {
                "id": snapshot_id, "source_id": source["id"],
                "observed_at": source["observed_at"],
                "source_published_at": source["source_published_at"],
                "content_hash": source["content_hash"],
                "snapshot_text": source["snapshot_text"], "demo_scope": scope,
            })
            self.link("Source", source["id"], "OBSERVED_AT", "SourceSnapshot", snapshot_id)
        for dependency in fixture["dependencies"]:
            self.link("Source", dependency["source_id"], dependency["relationship"],
                      "Source", dependency["root_id"], {
                          "evidence_mode": dependency["evidence_mode"],
                          "relationship_confidence": 1.0,
                          "explanation": "Explicit link in synthetic demo fixture",
                          "observed_at": fixture["requirement"]["created_at"],
                          "demo_scope": scope,
                      })
        for evidence in fixture["evidence"]:
            self.upsert_node("Evidence", evidence)
            self.link("Claim", evidence["claim_id"], "SUPPORTED_BY", "Evidence", evidence["id"])
            self.link("Evidence", evidence["id"], "FROM_SOURCE", "Source", evidence["source_id"])
            self.link("AgentRun", evidence["agent_run_id"], "OBSERVED", "Evidence", evidence["id"])
            claim_id = evidence["claim_id"]
            self.link("AgentRun", evidence["agent_run_id"], "PRODUCED", "Claim", claim_id)
        # Keep variables intentionally referenced above so malformed fixtures fail before scoring.
        if len(claims_by_id) != len(fixture["claims"]) or not suppliers_by_id:
            raise ValueError("demo fixture must have unique claims and at least one supplier")

    def invalidate_source(self, source_id: str, reason: str, at: str) -> None:
        result = self.graph.query(
            "MATCH (source:Source {id: $id}) SET source.active = false, "
            "source.invalidated_at = $at, source.invalidation_reason = $reason RETURN source.id",
            params={"id": source_id, "at": at, "reason": " ".join(reason.split())[:500]},
            timeout=5000,
        )
        if not result.result_set:
            raise KeyError(f"no source {source_id!r}")

    def read_only_rows(self, query: str, params: dict[str, Any]) -> list[list[Any]]:
        """Execute a code-owned read query; callers never provide Cypher text."""
        return self.graph.ro_query(query, params=params, timeout=5000).result_set
