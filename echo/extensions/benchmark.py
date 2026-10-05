"""Repeatable synthetic graph scenarios for the ECHO evidence policy."""

from __future__ import annotations

import copy
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from echo.demo_data import REQUIREMENT_ID, build_fixture
from echo.engine import EchoEngine
from echo.graph_store import EchoGraphStore


def scenarios() -> list[tuple[str, Callable[[dict], None]]]:
    rows: list[tuple[str, Callable[[dict], None]]] = []
    rows.append(("baseline", lambda f: None))

    def alpha_count(count: int):
        def change(f):
            original = [e for e in f["evidence"] if e["id"].startswith("evidence-alpha-")]
            copies = []
            for i in range(count):
                item = dict(original[i % len(original)])
                item["id"] = f"bench-alpha-{count}-{i}"
                copies.append(item)
            f["evidence"] = [e for e in f["evidence"] if not e["id"].startswith("evidence-alpha-")] + copies
        return change

    for n in (1, 4, 16, 64):
        rows.append((f"alpha_observations_{n}", alpha_count(n)))

    def beta_roots(count: int):
        def change(f):
            beta = [e for e in f["evidence"] if e["id"].startswith("evidence-beta-")]
            beta = beta[:count]
            f["evidence"] = [e for e in f["evidence"] if not e["id"].startswith("evidence-beta-")] + beta
        return change

    for n in (0, 1, 2, 3):
        rows.append((f"beta_available_roots_{n}", beta_roots(n)))

    def dependency_mode(mode: str):
        def change(f):
            if mode == "none":
                f["dependencies"] = []
            elif mode == "one":
                f["dependencies"] = f["dependencies"][:1]
            elif mode == "unknown":
                f["dependencies"] = [dict(d, evidence_mode="UNRESOLVED") for d in f["dependencies"][:1]]
        return change

    for mode in ("none", "one", "unknown"):
        rows.append((f"alpha_dependencies_{mode}", dependency_mode(mode)))

    def change_source(state: str):
        def change(f):
            if state == "inactive":
                for source in f["sources"]:
                    if source["id"] == "source-beta-root-1":
                        source["active"] = False
            elif state == "unknown":
                for source in f["sources"]:
                    if source["id"] == "source-beta-root-1":
                        source["provenance_state"] = "UNKNOWN"
            elif state == "stale":
                for evidence in f["evidence"]:
                    if evidence["id"] == "evidence-beta-1":
                        evidence["observed_at"] = "2000-01-01T00:00:00+00:00"
        return change

    for state in ("inactive", "unknown", "stale"):
        rows.append((f"beta_source_{state}", change_source(state)))
    return rows


def run() -> dict:
    results = []
    for name, mutate in scenarios():
        fixture = copy.deepcopy(build_fixture())
        mutate(fixture)
        graph = EchoGraphStore(graph_name=f"echo_bench_{uuid4().hex}")
        try:
            graph.add_fixture(fixture)
            start = time.perf_counter()
            result = EchoEngine(graph).analyze_requirement(REQUIREMENT_ID, fixture=fixture)
            elapsed_ms = (time.perf_counter() - start) * 1000
            winner = next((c for c in result["candidates"] if c["supplier_id"] == result["recommended_supplier_id"]), None)
            results.append({"scenario": name, "decision_status": result["decision_status"],
                            "raw_winner": result["raw_winner_supplier_id"],
                            "recommended_supplier": result["recommended_supplier_id"],
                            "candidate_count": len(result["candidates"]),
                            "winner_provenance_roots": winner["provenance_root_count"] if winner else 0,
                            "winner_unresolved_paths": winner["unresolved_provenance_count"] if winner else 0,
                            "trace_candidates": len(result["candidates"]),
                            "trace_paths": sum(len(c["evidence_paths"]) for c in result["candidates"]),
                            "elapsed_ms": round(elapsed_ms, 3)})
        finally:
            graph.graph.delete()
    latencies = [r["elapsed_ms"] for r in results]
    return {"schema_version": "1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "method": "one isolated FalkorDB graph per deterministic synthetic scenario; wall time covers engine evaluation only",
            "scope": "policy and trace behavior under explicit fixture mutations; not live provider quality, procurement accuracy, throughput or statistical independence",
            "scenario_count": len(results), "latency_ms": {"median": round(statistics.median(latencies), 3),
                "max": round(max(latencies), 3)}, "all_scenarios_have_decisions": all(r["decision_status"] for r in results),
            "results": results}


if __name__ == "__main__":
    payload = run()
    output = Path(__file__).resolve().parents[2] / "docs" / "extensions" / "benchmark-results.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scenario_count": payload["scenario_count"], "latency_ms": payload["latency_ms"],
                      "output": str(output)}, indent=2))
