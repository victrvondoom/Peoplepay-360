"""
annotate_demo_scenario.py
-------------------------
Recomputes the scoring fields of the offline demo scenario
(frontend/lib/sampledata.json) with the live backend scoring pipeline, so the
demo re-ranks under the dashboard's transport toggle and weight sliders
exactly like a real search.

Per manufacturer it writes `scoringInputs`, `industry`, the scores the
dashboard shows at the default lens (sea freight, default weights), and
orders the q10/q50/q90 band. Supplier identities, locations, certifications
and q50 values are left untouched.

Run from the repo root:
    python -m backend.scripts.annotate_demo_scenario
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.ml_scorer import compute_composite_scores
from backend.naics_classifier import classify_naics
from backend.tools import calculate_transport_emissions

DEMO_PATH = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "sampledata.json"
BASELINE_MODE = "sea"


def annotate(data: dict[str, Any]) -> dict[str, Any]:
    scenario = data["scenario"]
    destination = scenario["destination"]["country"]
    manufacturers = [node for node in data["nodes"] if node.get("nodeKind") == "manufacturer"]
    components = {node["component"] for node in manufacturers}
    weight_kg = max(1.0, scenario["quantity"] * 0.5 / max(len(components), 1))

    by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in manufacturers:
        band = sorted(node["manufacturingEmissionsTco2e"].values())
        node["manufacturingEmissionsTco2e"] = {"q10": band[0], "q50": band[1], "q90": band[2]}
        by_component[node["component"]].append(node)

    for component, nodes in by_component.items():
        industry = classify_naics(component)
        candidates = [
            {
                "name": node["id"],  # unique key to merge results back
                "country": node["location"]["country"],
                "certifications": node["certifications"],
                "emission_factor": {"q50_tco2e": node["manufacturingEmissionsTco2e"]["q50"]},
                "transport": calculate_transport_emissions(
                    node["location"]["country"], destination, weight_kg, BASELINE_MODE
                ),
            }
            for node in nodes
        ]
        scored = {
            result["name"]: result
            for result in compute_composite_scores(candidates, transport_mode=BASELINE_MODE)
        }
        for node in nodes:
            result = scored[node["id"]]
            inputs = result["scoring_inputs"]
            node["ecoScore"] = round(100 - result["composite_score"])
            node["gridCarbonScore"] = round(100 - result["rank_scores"]["grid_norm"])
            node["climateRiskScore"] = round(inputs["climate_risk"], 1)
            node["transportEmissionsTco2e"] = inputs["transport_tco2e_by_mode"][BASELINE_MODE]
            node["industry"] = {"code": industry.code, "title": industry.title}
            node["scoringInputs"] = {
                "certAdjustment": inputs["cert_adjustment"],
                "climateRisk": inputs["climate_risk"],
                "gridGco2Kwh": inputs["grid_gco2_kwh"],
                "manufacturingTco2e": inputs["manufacturing_tco2e"],
                "transportTco2eByMode": inputs["transport_tco2e_by_mode"],
            }

    return data


def main() -> None:
    data = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    annotate(data)
    DEMO_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Annotated {DEMO_PATH}")


if __name__ == "__main__":
    main()
