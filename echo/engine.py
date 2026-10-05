"""ECHO graph traversal and correlation-aware decision engine."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from echo.config import SCORING
from echo.demo_data import DECISION_ID, REQUIREMENT_ID, build_fixture
from echo.graph_store import EchoGraphStore
from echo.models import stable_id
from echo.scoring import CandidateScore, fragility_class, robust_score


class EchoEngine:
    def __init__(self, store: EchoGraphStore | None = None) -> None:
        self.store = store or EchoGraphStore()

    def run_false_consensus_demo(self) -> dict[str, Any]:
        fixture = build_fixture()
        self.store.add_fixture(fixture)
        return self.analyze_requirement(REQUIREMENT_ID, fixture=fixture)

    def analyze_requirement(self, requirement_id: str,
                            fixture: dict[str, Any] | None = None,
                            parent_decision_id: str | None = None) -> dict[str, Any]:
        requirement_rows = self.store.read_only_rows(
            "MATCH (r:Requirement {id: $id}) RETURN r.user_id, r.demo_scope",
            {"id": requirement_id},
        )
        if not requirement_rows:
            raise KeyError(f"requirement {requirement_id!r} does not exist")
        owner, demo_scope = requirement_rows[0]
        evaluated_at = datetime.now(timezone.utc).isoformat()
        rows = self.store.query_file(
            "10_candidate_evidence_diversity.cypher",
            {"requirement_id": requirement_id, "as_of": evaluated_at},
        )
        grouped: dict[str, list[list[Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row[0])].append(row)
        candidates = [self._candidate_from_rows(group) for group in grouped.values()]
        candidates.sort(key=lambda item: (-item.robust_score, item.supplier_id))
        eligible = [item for item in candidates if item.decision_status == "RECOMMEND"]
        winner = eligible[0] if eligible else None
        raw_winner = sorted(candidates, key=lambda item: (-item.raw_score, item.supplier_id))[0] if candidates else None
        status = "RECOMMEND" if winner else "ABSTAIN"
        reason = (
            "Highest robust score among candidates meeting identity, policy and provenance requirements."
            if winner else
            "No eligible candidate has enough current provenance-distinct evidence; human research is required."
        )
        decision_id = DECISION_ID if fixture else f"decision-{uuid4().hex}"
        excluded_root_scenarios = self._counterfactual_root_removals(candidates)
        winner_flip_count = sum(
            scenario.get("winner_supplier_id") != (winner.supplier_id if winner else None)
            for scenario in excluded_root_scenarios
        )
        alternatives = [item for item in eligible if winner and item.supplier_id != winner.supplier_id]
        margin = winner.robust_score - alternatives[0].robust_score if winner and alternatives else (winner.robust_score if winner else 0.0)
        decision_fragility = fragility_class(
            winner_flip_count=winner_flip_count,
            root_removal_count=len(excluded_root_scenarios),
            margin=margin,
            provenance_roots=winner.provenance_root_count if winner else 0,
        )
        policy = {
            "correlated_observation_penalty": SCORING.correlated_observation_penalty,
            "confidence_penalty_weight": SCORING.confidence_penalty_weight,
            "minimum_provenance_roots": SCORING.minimum_provenance_roots,
            "maximum_dependency_depth": SCORING.maximum_dependency_depth,
            "terminology": "provenance-distinct roots; not statistical independence",
        }
        decision = {
            "id": decision_id,
            "requirement_id": requirement_id,
            "user_id": owner,
            "status": status,
            "raw_winner_supplier_id": raw_winner.supplier_id if raw_winner else None,
            "recommended_supplier_id": winner.supplier_id if winner else None,
            "decision_fragility": decision_fragility,
            "winner_flip_count": winner_flip_count,
            "margin_before": round(margin, 2),
            "created_at": evaluated_at,
            "evaluated_at": evaluated_at,
            "model_version": "echo-deterministic-scoring-v2",
            "scoring_policy_json": json.dumps(policy, sort_keys=True),
            "parent_decision_id": parent_decision_id,
            "demo_scope": demo_scope,
            "evidence_stale": False,
        }
        graph_candidates = [{
            "id": stable_id("candidate", decision_id, item.supplier_id),
            "decision_id": decision_id,
            "supplier_id": item.supplier_id,
            "supplier_name": item.supplier_name,
            "claim_id": item.claim_ids[0] if item.claim_ids else None,
            "claim_ids_json": json.dumps(item.claim_ids),
            "raw_score": item.raw_score,
            "robust_score": item.robust_score,
            "apparent_support_count": item.apparent_support_count,
            "provenance_root_count": item.provenance_root_count,
            "unresolved_provenance_count": item.unresolved_provenance_count,
            "decision_status": item.decision_status,
            "evaluated_at": evaluated_at,
            "root_ids_json": json.dumps(item.root_sources),
            "evidence_snapshot_json": json.dumps(item.evidence_paths, sort_keys=True),
            "demo_scope": demo_scope,
        } for item in candidates]
        self.store.create_decision(decision, graph_candidates)
        return {
            "decision_id": decision_id,
            "requirement_id": requirement_id,
            "decision_status": status,
            "reason": reason,
            "raw_winner_supplier_id": raw_winner.supplier_id if raw_winner else None,
            "recommended_supplier_id": winner.supplier_id if winner else None,
            "decision_fragility": decision_fragility,
            "winner_flip_count": winner_flip_count,
            "margin_before": round(margin, 2),
            "evaluated_at": evaluated_at,
            "scoring_policy": policy,
            "counterfactual_root_removals": excluded_root_scenarios,
            "candidates": [item.to_dict() for item in candidates],
            "graph_reason": (
                "Supplier Alpha's apparent support traverses to one upstream source; "
                "Supplier Beta's three evidence paths terminate at three distinct roots."
                if fixture else "Scores were recomputed from the current graph evidence."
            ),
        }

    @staticmethod
    def _candidate_from_rows(rows: list[list[Any]]) -> CandidateScore:
        first = rows[0]
        supplier_id, supplier_name, raw_score = first[:3]
        identity_status = first[10] if len(first) > 10 else "MATCHED"
        policy_available = bool(first[11]) if len(first) > 11 else raw_score is not None
        normalized_paths: dict[tuple[Any, ...], dict[str, Any]] = {}
        claim_ids = set()
        for row in rows:
            if row[2] != raw_score:
                raise ValueError("conflicting core candidate policies for one supplier")
            claim_ids.add(str(row[3]))
            for path in row[9] or []:
                if not isinstance(path, dict) or path.get("evidence_id") is None:
                    continue
                normalized = {**path, "claim_id": row[3]}
                key = (row[3], path.get("evidence_id"), path.get("source_id"),
                       path.get("root_source_id"), path.get("extension_run_id"),
                       tuple(path.get("dependency_edge_ids") or []))
                normalized_paths[key] = normalized
        paths = tuple(normalized_paths[key] for key in sorted(normalized_paths, key=lambda item: tuple(str(part) for part in item)))
        roots = tuple(sorted({str(path["root_source_id"]) for path in paths if path.get("root_source_id") is not None}))
        evidence_confidences: dict[str, float] = {}
        unresolved = set()
        for path in paths:
            evidence_id = str(path["evidence_id"])
            confidence = float(path.get("confidence") or 0)
            evidence_confidences[evidence_id] = min(evidence_confidences.get(evidence_id, confidence), confidence)
            if path.get("root_source_id") is None or path.get("lineage_unresolved"):
                unresolved.add(evidence_id)
        mean_confidence = sum(evidence_confidences.values()) / len(evidence_confidences) if evidence_confidences else 0
        apparent_count = len(evidence_confidences)
        score, correlation_penalty, confidence_penalty = robust_score(
            raw_score=float(raw_score or 0),
            apparent_support_count=apparent_count,
            provenance_root_count=len(roots),
            mean_confidence=mean_confidence,
        )
        eligible = (len(roots) >= SCORING.minimum_provenance_roots
                    and apparent_count >= SCORING.minimum_provenance_roots
                    and not unresolved and identity_status == "MATCHED" and policy_available)
        return CandidateScore(
            supplier_id=str(supplier_id), supplier_name=str(supplier_name),
            raw_score=float(raw_score or 0), robust_score=score,
            apparent_support_count=apparent_count, provenance_root_count=len(roots),
            correlated_observation_count=max(0, apparent_count - len(roots)),
            mean_confidence=mean_confidence, correlation_penalty=correlation_penalty,
            confidence_penalty=confidence_penalty,
            decision_status="RECOMMEND" if eligible else "REVIEW_REQUIRED",
            root_sources=roots, evidence_paths=paths,
            claim_ids=tuple(sorted(claim_ids)), unresolved_provenance_count=len(unresolved),
            identity_status=str(identity_status or "UNRESOLVED"), policy_available=policy_available,
        )

    @staticmethod
    def _counterfactual_root_removals(candidates: list[CandidateScore]) -> list[dict[str, Any]]:
        roots = sorted({root for item in candidates for root in item.root_sources})
        scenarios = []
        for removed_root in roots:
            alternate_scores = []
            for candidate in candidates:
                remaining_paths = [path for path in candidate.evidence_paths
                                   if path.get("root_source_id") != removed_root]
                remaining_roots = {str(path["root_source_id"]) for path in remaining_paths
                                   if path.get("root_source_id") is not None}
                confidences: dict[str, float] = {}
                for path in remaining_paths:
                    key = str(path["evidence_id"])
                    confidence = float(path.get("confidence") or 0)
                    confidences[key] = min(confidences.get(key, confidence), confidence)
                if (len(remaining_roots) < SCORING.minimum_provenance_roots
                        or len(confidences) < SCORING.minimum_provenance_roots
                        or candidate.identity_status != "MATCHED" or not candidate.policy_available
                        or any(path.get("root_source_id") is None or path.get("lineage_unresolved")
                               for path in remaining_paths)):
                    continue
                score, _, _ = robust_score(
                    raw_score=candidate.raw_score,
                    apparent_support_count=len(confidences),
                    provenance_root_count=len(remaining_roots),
                    mean_confidence=sum(confidences.values()) / len(confidences),
                )
                alternate_scores.append((candidate.supplier_id, score))
            alternate_scores.sort(key=lambda row: (-row[1], row[0]))
            winner = alternate_scores[0] if alternate_scores else None
            scenarios.append({
                "removed_root_source_id": removed_root,
                "winner_supplier_id": winner[0] if winner else None,
                "winner_robust_score": winner[1] if winner else None,
                "status": "RECOMPUTED_FROM_GRAPH_EVIDENCE",
            })
        return scenarios

