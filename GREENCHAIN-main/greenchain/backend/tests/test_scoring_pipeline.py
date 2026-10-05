from __future__ import annotations

import json
import os
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import main
from backend.db import cache_get, cache_put, create_dataset_intake, init_db
from backend.ml_bridge import get_emissions_model
from backend.ml_scorer import compute_composite_scores
from backend.naics_classifier import _CURATED, classify_naics, lookup_naics
from backend.report_generation import (
    ScenarioScoringPayload,
    _build_latex_document,
    _build_report_context,
    ReportNarrativePayload,
)
from backend.scenario_editing import (
    SupplyScenarioPayload,
    _to_editable_scenario,
    normalize_edited_scenario,
)
from backend.tools import calculate_transport_emissions, score_certifications
from backend.transport import rescore_transport, transport_tco2e, transport_tco2e_by_mode

# `backend.ml_bridge` (imported above) puts backend/ml_runtime on sys.path.
from ml.inference import EmissionsModel, certification_adjustment  # type: ignore
from ml.reference_data import (  # type: ignore
    EMBER_GRID_INTENSITY,
    NAICS_DETAIL,
    ND_GAIN_RISK,
)


class TempDbTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(
            os.environ,
            {"DB_PATH": os.path.join(self.tempdir.name, "test.db")},
            clear=False,
        )
        self.env_patch.start()
        init_db()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tempdir.cleanup()
        super().tearDown()


class ReferenceDataTests(unittest.TestCase):
    def test_real_datasets_are_loaded(self) -> None:
        self.assertGreaterEqual(len(NAICS_DETAIL), 1000)
        self.assertGreaterEqual(len(EMBER_GRID_INTENSITY), 170)
        self.assertGreaterEqual(len(ND_GAIN_RISK), 160)

    def test_quantiles_are_ordered(self) -> None:
        model = get_emissions_model()
        for country, naics in [("CN", "315220"), ("PT", "315220"), ("US", "33"), ("IN", "331318")]:
            prediction = model.predict(country_iso=country, naics4=naics, revenue_usd_m=25)
            self.assertLessEqual(prediction["q10_tco2e"], prediction["q50_tco2e"])
            self.assertLessEqual(prediction["q50_tco2e"], prediction["q90_tco2e"])

    def test_partial_naics_prefix_uses_sector_median_not_first_code(self) -> None:
        index = EmissionsModel._build_naics_prefix_index()
        steel_mill = NAICS_DETAIL["331110"][2]
        _sector, generic_value = EmissionsModel._lookup_naics("33", index)
        self.assertLess(generic_value, steel_mill)
        # Exact codes still resolve to their own intensity.
        self.assertEqual(EmissionsModel._lookup_naics("331110", index)[1], steel_mill)


class CertificationTests(unittest.TestCase):
    def test_every_recognised_certification_lowers_the_multiplier(self) -> None:
        self.assertAlmostEqual(certification_adjustment(["iso14001"]), 0.95)
        self.assertAlmostEqual(certification_adjustment(["cdp_a"]), 0.90)
        self.assertAlmostEqual(certification_adjustment(["cdp_b"]), 0.94)
        self.assertAlmostEqual(certification_adjustment(["sbt_committed"]), 0.92)
        self.assertAlmostEqual(certification_adjustment(["sbt_achieved"]), 0.90)
        self.assertAlmostEqual(certification_adjustment(["bcorp"]), 0.96)

    def test_spelling_variants_and_family_best(self) -> None:
        self.assertAlmostEqual(
            certification_adjustment(["ISO 14001:2015", "CDP A-", "Science Based Targets"]),
            1.0 - 0.05 - 0.10 - 0.08,
        )
        # Only the strongest CDP rating counts.
        self.assertAlmostEqual(certification_adjustment(["cdp_a", "cdp_b"]), 0.90)

    def test_disclosure_penalty_only_when_nothing_disclosed(self) -> None:
        self.assertAlmostEqual(certification_adjustment([]), 1.15)
        self.assertAlmostEqual(certification_adjustment(["fsc"]), 1.0)
        self.assertTrue(score_certifications([])["disclosure_penalty"])
        self.assertFalse(score_certifications(["fsc"])["disclosure_penalty"])

    def test_agent_tool_matches_composite_scorer(self) -> None:
        result = score_certifications(["iso14001", "cdp_a", "cdp_b"])
        self.assertEqual(result["matched_certs"], ["iso14001", "cdp_a", "cdp_b"])
        self.assertEqual(result["cert_score"], 60)
        self.assertAlmostEqual(result["multiplier"], 0.85)


class TransportTests(unittest.TestCase):
    def test_formula_uses_tonnes_and_kilograms_per_tonne_km(self) -> None:
        # 1 t over 10,000 km by sea at 0.011 kgCO2e/t-km = 110 kg = 0.11 t.
        self.assertAlmostEqual(transport_tco2e(10_000, 1_000, "sea"), 0.11)
        by_mode = transport_tco2e_by_mode(10_000, 1_000)
        self.assertEqual(set(by_mode), {"sea", "air", "rail", "road"})
        self.assertGreater(by_mode["air"], by_mode["road"])
        self.assertGreater(by_mode["road"], by_mode["rail"])
        self.assertGreater(by_mode["rail"], by_mode["sea"])

    def test_matches_calculator_used_during_search(self) -> None:
        computed = calculate_transport_emissions("CN", "US", 5_000, "air")
        expected = transport_tco2e(computed["distance_km"], 5_000, "air")
        self.assertAlmostEqual(computed["transport_tco2e"], expected, places=1)

    def test_rescore_transport_is_not_off_by_a_thousand(self) -> None:
        manufacturers = [
            {
                "transport": {"distance_km": 10_000, "weight_kg": 1_000, "mode": "sea"},
                "scores": {"manufacturing_tco2e": 5.0},
            }
        ]
        rescored = rescore_transport(manufacturers, "air")
        self.assertAlmostEqual(rescored[0]["transport"]["transport_tco2e"], 6.02)
        self.assertAlmostEqual(rescored[0]["scores"]["total_tco2e"], 11.02)


class NaicsClassifierTests(unittest.TestCase):
    def test_curated_codes_are_real_useeio_industries(self) -> None:
        for phrase, (code, title) in _CURATED.items():
            self.assertIn(code, NAICS_DETAIL, phrase)
            self.assertEqual(NAICS_DETAIL[code][1], title, phrase)

    def test_examples(self) -> None:
        cases = {
            "cotton t-shirts": "315220",
            "Circuit Boards": "334412",
            "LED desk lamp": "335121",
            "aluminium housing": "331318",
            "power adapter": "335999",
            "electronic connector": "334417",
            "ball bearings": "332991",
            "running shoes": "316210",
        }
        for product, code in cases.items():
            self.assertEqual(classify_naics(product).code, code, product)

    def test_unknown_product_falls_back_to_generic_manufacturing(self) -> None:
        match = classify_naics("zzqx")
        self.assertEqual(match.code, "33")
        self.assertEqual(match.method, "fallback")

    def test_lookup_naics_only_accepts_exact_codes(self) -> None:
        adhesive = lookup_naics("325520")
        assert adhesive is not None
        self.assertEqual(adhesive.title, "Adhesive Manufacturing")
        self.assertIsNone(lookup_naics("3255"))
        self.assertIsNone(lookup_naics("999999"))


class ScoringInputsTests(unittest.TestCase):
    def test_scoring_inputs_cover_every_mode_and_match_scored_transport(self) -> None:
        candidates = [
            {
                "name": name,
                "country": country,
                "certifications": certs,
                "emission_factor": {"q50_tco2e": q50},
                "transport": calculate_transport_emissions(country, "US", 2_000, "rail"),
            }
            for name, country, certs, q50 in [
                ("A", "CN", ["iso14001"], 40.0),
                ("B", "DE", ["sbt_committed"], 25.0),
                ("C", "VN", [], 30.0),
            ]
        ]
        scored = compute_composite_scores(candidates, transport_mode="rail")
        self.assertEqual(len(scored), 3)
        for result in scored:
            inputs = result["scoring_inputs"]
            self.assertEqual(set(inputs["transport_tco2e_by_mode"]), {"sea", "air", "rail", "road"})
            self.assertAlmostEqual(
                result["scores"]["transport_tco2e"],
                inputs["transport_tco2e_by_mode"]["rail"],
                places=3,
            )
        sbt = next(result for result in scored if result["name"] == "B")
        self.assertAlmostEqual(sbt["scoring_inputs"]["cert_adjustment"], 0.92)

    def test_scoring_inputs_omitted_without_distance(self) -> None:
        scored = compute_composite_scores(
            [
                {"name": "A", "country": "CN", "emission_factor": {"q50_tco2e": 1}, "transport": {"transport_tco2e": 1}},
                {"name": "B", "country": "DE", "emission_factor": {"q50_tco2e": 2}, "transport": {"transport_tco2e": 2}},
            ],
            transport_mode="sea",
        )
        self.assertTrue(all("scoring_inputs" not in result for result in scored))


def _search_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "product": "LED desk lamp",
        "quantity": 8000,
        "destination": "US",
        "transport_mode": "sea",
        "components": [
            {
                "component": "aluminum housing",
                "current_manufacturer": "MetalForm Precision",
                "current_country": "CN",
                "current_certifications": ["iso14001"],
                "current_revenue_usd_m": 38,
                "current_renewable_pct": 22,
            },
            {
                "component": "led module",
                "current_manufacturer": "LuxLED Korea",
                "current_country": "KR",
            },
        ],
    }
    body.update(overrides)
    return body


def _agent_output(component: str) -> str:
    return json.dumps(
        [
            {
                "name": f"{component} Works Portugal",
                "country": "PT",
                "city": "Porto",
                "certifications": ["ISO 14001", "SBTi"],
                "disclosure_status": "verified",
                # Deliberately garbled tool output: must be recomputed server-side.
                "emission_factor": {"q50_tco2e": -5, "revenue_usd_m": 40},
                "transport": {"transport_tco2e": "lots"},
            },
            {
                "name": f"{component} Vietnam Co",
                "country": "VN",
                "certifications": [],
                "disclosure_status": "none",
            },
            {"name": "No Country Ltd", "country": "Nowhere"},
        ]
    )


class SearchEndpointTests(TempDbTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(main.app)

    def _mock_agent(self) -> AsyncMock:
        async def fake_run(**kwargs: Any) -> str:
            return _agent_output(kwargs["product"])

        return AsyncMock(side_effect=fake_run)

    def test_search_enriches_scores_and_exposes_scoring_inputs(self) -> None:
        with patch.object(main, "run_supply_chain_research", self._mock_agent()):
            response = self.client.post("/search", json=_search_body())
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["cache_hits"], 0)
        self.assertEqual(payload["fallback_components"], [])

        names = {result["name"] for result in payload["results"]}
        self.assertNotIn("No Country Ltd", names)
        self.assertIn("MetalForm Precision", names)

        for result in payload["results"]:
            ef = result["emission_factor"]
            self.assertGreater(ef["q50_tco2e"], 0)
            self.assertLessEqual(ef["q10_tco2e"], ef["q50_tco2e"])
            self.assertLessEqual(ef["q50_tco2e"], ef["q90_tco2e"])
            self.assertIn("scoring_inputs", result)
            self.assertIn("industry", result)

        housing = [r for r in payload["results"] if r["component"] == "aluminum housing"]
        self.assertTrue(all(r["industry"]["code"] == "331318" for r in housing))

    def test_second_search_is_served_from_cache(self) -> None:
        agent = self._mock_agent()
        with patch.object(main, "run_supply_chain_research", agent):
            first = self.client.post("/search", json=_search_body())
            second = self.client.post("/search", json=_search_body(transport_mode="air"))
            fresh = self.client.post("/search", json=_search_body(use_cache=False))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(agent.await_count, 4)  # 2 components x (first + fresh)
        self.assertEqual(second.json()["cache_hits"], 2)
        self.assertEqual(second.json()["transport_mode"], "air")
        self.assertEqual(fresh.json()["cache_hits"], 0)

    def test_missing_keys_fall_back_to_placeholders(self) -> None:
        failing = AsyncMock(side_effect=RuntimeError("no agent"))
        env = {"DEDALUS_API_KEY": "", "ANTHROPIC_API_KEY": "", "BRAVE_API_KEY": ""}
        with patch.object(main, "run_supply_chain_research", failing), patch.dict(os.environ, env):
            response = self.client.post("/search", json=_search_body())
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["fallback_components"], ["aluminum housing", "led module"])
        self.assertTrue(all("scoring_inputs" in result for result in payload["results"]))

    def test_agent_failure_with_keys_is_a_502(self) -> None:
        failing = AsyncMock(side_effect=RuntimeError("upstream down"))
        env = {
            "DEDALUS_API_KEY": "x",
            "ANTHROPIC_API_KEY": "x",
            "BRAVE_API_KEY": "x",
            "GREENCHAIN_ALLOW_MOCK_COMPONENT_SEARCH": "",
        }
        with patch.object(main, "run_supply_chain_research", failing), patch.dict(os.environ, env):
            response = self.client.post("/search", json=_search_body())
        self.assertEqual(response.status_code, 502)
        self.assertIn("upstream down", response.json()["detail"])

    def test_stream_reports_progress_then_result(self) -> None:
        with patch.object(main, "run_supply_chain_research", self._mock_agent()):
            response = self.client.post("/search/stream", json=_search_body())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = [
            json.loads(line[len("data: "):])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        types = [event["type"] for event in events]
        self.assertEqual(types[0], "started")
        self.assertEqual(types.count("component"), 2)
        self.assertEqual(types[-1], "complete")
        self.assertEqual(events[0]["components"], ["aluminum housing", "led module"])
        self.assertEqual(events[-1]["response"]["count"], len(events[-1]["response"]["results"]))
        completed = [event["completed"] for event in events if event["type"] == "component"]
        self.assertEqual(completed, [1, 2])

        # Each component event carries that component's scored results, and
        # together they match the final response.
        streamed: list[dict[str, Any]] = []
        for event in events:
            if event["type"] != "component":
                continue
            self.assertEqual(len(event["results"]), event["count"])
            self.assertTrue(
                all(result["component"] == event["component"] for result in event["results"])
            )
            streamed.extend(event["results"])
        final_names = sorted(result["name"] for result in events[-1]["response"]["results"])
        self.assertEqual(sorted(result["name"] for result in streamed), final_names)

    def test_stream_reports_errors_as_events(self) -> None:
        failing = AsyncMock(side_effect=RuntimeError("upstream down"))
        env = {
            "DEDALUS_API_KEY": "x",
            "ANTHROPIC_API_KEY": "x",
            "BRAVE_API_KEY": "x",
            "GREENCHAIN_ALLOW_MOCK_COMPONENT_SEARCH": "",
        }
        with patch.object(main, "run_supply_chain_research", failing), patch.dict(os.environ, env):
            response = self.client.post("/search/stream", json=_search_body())
        events = [
            json.loads(line[len("data: "):])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["status"], 502)

    def test_request_validation(self) -> None:
        bad_requests = [
            _search_body(transport_mode="teleport"),
            _search_body(weights={"manufacturing": -1}),
            _search_body(weights={"manufacturing": 0, "transport": 0}),
            _search_body(weights={"vibes": 1}),
            _search_body(
                components=[
                    {"component": "x", "current_manufacturer": "y", "current_country": "USA"}
                ]
            ),
        ]
        for body in bad_requests:
            response = self.client.post("/search", json=body)
            self.assertEqual(response.status_code, 422, body)

    def test_partial_weights_are_accepted(self) -> None:
        with patch.object(main, "run_supply_chain_research", self._mock_agent()):
            response = self.client.post(
                "/search", json=_search_body(weights={"transport": 1})
            )
        self.assertEqual(response.status_code, 200, response.text)


class CacheAndIntakeTests(TempDbTestCase):
    def test_cache_round_trip_and_ttl_disable(self) -> None:
        cache_put("k", "[1]")
        self.assertEqual(cache_get("k"), "[1]")
        with patch.dict(os.environ, {"GREENCHAIN_DISCOVERY_CACHE_TTL_HOURS": "0"}):
            self.assertIsNone(cache_get("k"))

    def test_dataset_intake_module_imports_and_records(self) -> None:
        from backend import dataset_intakes

        self.assertTrue(callable(dataset_intakes.store_dataset_intake_upload))
        create_dataset_intake(
            intake_id="intake_test",
            filename="scenario.csv",
            stored_path="/tmp/scenario.csv",
            row_count=1,
            status="uploaded",
            schema_version="scenario_csv_v1",
        )


def _scenario_with_scoring_inputs() -> SupplyScenarioPayload:
    def manufacturer(mid: str, current: bool, name: str, country: str) -> dict[str, Any]:
        return {
            "certifications": ["iso14001"],
            "climateRiskScore": 31.0,
            "componentId": "component_handle",
            "componentLabel": "Handle",
            "ecoScore": 40,
            "graphPosition": {"x": 0, "y": 0},
            "gridCarbonScore": 50,
            "id": mid,
            "industry": {"code": "326199", "title": "All Other Plastics Product Manufacturing"},
            "isCurrent": current,
            "kind": "manufacturer",
            "location": {"city": "X", "country": country, "countryCode": country[:2].upper(), "lat": 0, "lng": 0},
            "manufacturingEmissionsTco2e": {"q10": 1.0, "q50": 2.0, "q90": 3.0},
            "name": name,
            "scoringInputs": {
                "certAdjustment": 0.95,
                "climateRisk": 31.0,
                "gridGco2Kwh": 329.6,
                "manufacturingTco2e": 1.9,
                "transportTco2eByMode": {"sea": 0.1, "air": 5.5, "rail": 0.25, "road": 0.9},
            },
            "transportEmissionsTco2e": 0.1,
        }

    manufacturers = [
        manufacturer("mfr_current", True, "Current Co", "Germany"),
        manufacturer("mfr_alt", False, "Alt Co", "Portugal"),
    ]
    component = {
        "graphPosition": {"x": 0, "y": 0},
        "id": "component_handle",
        "kind": "component",
        "label": "Handle",
        "manufacturerIds": ["mfr_current", "mfr_alt"],
    }
    product = {
        "childIds": ["component_handle"],
        "graphPosition": {"x": 0, "y": 0},
        "id": "product_widget",
        "kind": "product",
        "label": "Widget",
        "subtitle": "1,000 units",
    }
    return SupplyScenarioPayload.model_validate(
        {
            "components": [component],
            "destination": {
                "id": "destination_main",
                "label": "US",
                "location": {"city": "NYC", "country": "United States", "countryCode": "US", "lat": 40, "lng": -74},
            },
            "graph": {
                "edges": [],
                "nodes": [
                    {"data": product, "id": product["id"], "position": {"x": 0, "y": 0}},
                    {"data": component, "id": component["id"], "position": {"x": 0, "y": 0}},
                    *[
                        {"data": item, "id": item["id"], "position": {"x": 0, "y": 0}}
                        for item in manufacturers
                    ],
                ],
            },
            "id": "scenario_widget",
            "manufacturers": manufacturers,
            "product": product,
            "quantity": 1000,
            "routes": [],
            "stats": {
                "componentCount": 1,
                "currentRouteCount": 1,
                "graphEdgeCount": 0,
                "graphNodeCount": 4,
                "routeCount": 2,
                "siteCount": 3,
            },
            "title": "Widget",
            "unit": "units",
            "updatedAt": "test",
        }
    )


class ScenarioSchemaTests(unittest.TestCase):
    def test_scoring_inputs_survive_edit_normalisation(self) -> None:
        scenario = _scenario_with_scoring_inputs()
        normalized = normalize_edited_scenario(scenario, _to_editable_scenario(scenario))
        self.assertIsNotNone(normalized.manufacturers[0].scoringInputs)
        industry = normalized.manufacturers[0].industry
        assert industry is not None
        self.assertEqual(industry.code, "326199")
        manufacturer_nodes = [
            node for node in normalized.graph.nodes if node.data.kind == "manufacturer"
        ]
        self.assertTrue(all(node.data.scoringInputs is not None for node in manufacturer_nodes))

    def test_report_mentions_scoring_lens(self) -> None:
        scenario = _scenario_with_scoring_inputs()
        scoring = ScenarioScoringPayload.model_validate(
            {
                "transportMode": "air",
                "weights": {
                    "manufacturing": 2,
                    "transport": 1,
                    "grid_carbon": 1,
                    "certifications": 0,
                    "climate_risk": 0,
                },
            }
        )
        context = _build_report_context(scenario, {}, scoring)
        self.assertEqual(context["scoring"]["transportMode"], "air")
        self.assertEqual(context["scoring"]["weightSharesPct"]["manufacturing"], 50.0)

        narrative = ReportNarrativePayload(
            strapline="s",
            executiveSummary=["a"],
            pathNarrative="p",
            componentFindings=[],
            riskNarrative="r",
            recommendedActions=["x"],
            closingNote="c",
        )
        latex = _build_latex_document(context, narrative, generated_at="now", model="m")
        self.assertIn("Transport: Air", latex)
        self.assertIn(r"manufacturing 50\%", latex)

    def test_report_without_scoring_is_unchanged(self) -> None:
        context = _build_report_context(_scenario_with_scoring_inputs(), {})
        self.assertIsNone(context["scoring"])


if __name__ == "__main__":
    unittest.main()
