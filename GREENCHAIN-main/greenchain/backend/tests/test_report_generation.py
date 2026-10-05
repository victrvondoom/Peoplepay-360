from __future__ import annotations

import base64
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.report_generation import (
    ReportGenerationConfigError,
    ReportNarrativePayload,
    _build_report_context,
    _build_latex_document,
    _get_gemini_settings,
    _latex_escape,
    generate_scenario_report_with_gemini,
)
from backend.scenario_editing import SupplyScenarioPayload


def make_scenario() -> SupplyScenarioPayload:
    return SupplyScenarioPayload.model_validate(
        {
            "components": [
                {
                    "graphPosition": {"x": 10, "y": 20},
                    "id": "component_handle",
                    "kind": "component",
                    "label": "Handle",
                    "manufacturerIds": ["mfr_current", "mfr_alt"],
                }
            ],
            "destination": {
                "id": "destination_main",
                "label": "Chicago",
                "location": {
                    "city": "Chicago",
                    "country": "United States",
                    "countryCode": "US",
                    "lat": 41.8781,
                    "lng": -87.6298,
                },
            },
            "graph": {"edges": [], "nodes": []},
            "id": "scenario_widget_001",
            "manufacturers": [
                {
                    "certifications": ["iso14001"],
                    "climateRiskScore": 25,
                    "componentId": "component_handle",
                    "componentLabel": "Handle",
                    "ecoScore": 55,
                    "graphPosition": {"x": 30, "y": 40},
                    "gridCarbonScore": 35,
                    "id": "mfr_current",
                    "isCurrent": True,
                    "kind": "manufacturer",
                    "location": {
                        "city": "Cleveland",
                        "country": "United States",
                        "countryCode": "US",
                        "lat": 41.4993,
                        "lng": -81.6944,
                    },
                    "manufacturingEmissionsTco2e": {"q10": 1.0, "q50": 2.0, "q90": 3.0},
                    "name": "Current Manufacturing",
                    "transportEmissionsTco2e": 4.0,
                },
                {
                    "certifications": ["sbt", "iso14001"],
                    "climateRiskScore": 20,
                    "componentId": "component_handle",
                    "componentLabel": "Handle",
                    "ecoScore": 30,
                    "graphPosition": {"x": 50, "y": 60},
                    "gridCarbonScore": 72,
                    "id": "mfr_alt",
                    "isCurrent": False,
                    "kind": "manufacturer",
                    "location": {
                        "city": "Hamburg",
                        "country": "Germany",
                        "countryCode": "DE",
                        "lat": 53.5511,
                        "lng": 9.9937,
                    },
                    "manufacturingEmissionsTco2e": {"q10": 0.8, "q50": 1.4, "q90": 2.1},
                    "name": "Alt Manufacturing",
                    "transportEmissionsTco2e": 2.5,
                },
            ],
            "product": {
                "childIds": ["component_handle"],
                "graphPosition": {"x": -20, "y": -30},
                "id": "product_widget",
                "kind": "product",
                "label": "Widget",
                "subtitle": "1,000 units",
            },
            "quantity": 1000,
            "routes": [
                {
                    "componentId": "component_handle",
                    "destinationId": "destination_main",
                    "id": "route_current",
                    "isCurrent": True,
                    "manufacturerId": "mfr_current",
                },
                {
                    "componentId": "component_handle",
                    "destinationId": "destination_main",
                    "id": "route_alt",
                    "isCurrent": False,
                    "manufacturerId": "mfr_alt",
                },
            ],
            "stats": {
                "componentCount": 1,
                "currentRouteCount": 1,
                "graphEdgeCount": 0,
                "graphNodeCount": 0,
                "routeCount": 2,
                "siteCount": 3,
            },
            "title": "Widget",
            "unit": "units",
            "updatedAt": "Sample dataset",
        }
    )


class ReportGenerationTests(unittest.IsolatedAsyncioTestCase):
    def test_get_gemini_settings_requires_api_key(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with self.assertRaises(ReportGenerationConfigError):
                _get_gemini_settings()

    def test_build_report_context_uses_selected_route(self) -> None:
        scenario = make_scenario()

        context = _build_report_context(
            scenario,
            selected_by_component={"component_handle": "mfr_alt"},
        )

        self.assertTrue(context["highlights"]["selectedPathDiffersFromCurrent"])
        self.assertTrue(context["highlights"]["selectedPathMatchesBestEco"])
        self.assertEqual(
            context["components"][0]["selectedManufacturerId"],
            "mfr_alt",
        )
        self.assertLess(
            context["paths"]["selectedVsCurrent"]["estimatedTotalQ50Tco2eDelta"],
            0,
        )
        self.assertFalse(
            context["provenance"]["currentBaselineHasPlaceholderSignals"]
        )

    def test_build_report_context_flags_placeholder_current_signals(self) -> None:
        scenario = make_scenario()
        scenario.manufacturers[0].ecoScore = 50
        scenario.manufacturers[0].gridCarbonScore = 50
        scenario.manufacturers[0].climateRiskScore = 50
        scenario.manufacturers[0].transportEmissionsTco2e = 0
        scenario.manufacturers[0].manufacturingEmissionsTco2e.q10 = 0
        scenario.manufacturers[0].manufacturingEmissionsTco2e.q50 = 0
        scenario.manufacturers[0].manufacturingEmissionsTco2e.q90 = 0

        context = _build_report_context(scenario, selected_by_component={})

        self.assertTrue(
            context["provenance"]["currentBaselineHasPlaceholderSignals"]
        )
        self.assertEqual(
            context["provenance"]["placeholderCurrentComponents"][0][
                "componentLabel"
            ],
            "Handle",
        )

    def test_latex_escape_escapes_special_characters(self) -> None:
        escaped = _latex_escape("A&B_50%")
        self.assertEqual(escaped, r"A\&B\_50\%")

    def test_report_narrative_payload_accepts_legacy_list_fields(self) -> None:
        narrative = ReportNarrativePayload.model_validate(
            {
                "strapline": "Legacy payload.",
                "executiveSummary": ["Summary line."],
                "pathComparison": ["Path sentence one.", "Path sentence two."],
                "componentFindings": [],
                "riskReadout": ["Risk sentence one.", "Risk sentence two."],
                "recommendedActions": ["Do the thing."],
                "closingNote": "Done.",
            }
        )

        self.assertEqual(
            narrative.pathNarrative,
            "Path sentence one. Path sentence two.",
        )
        self.assertEqual(
            narrative.riskNarrative,
            "Risk sentence one. Risk sentence two.",
        )

    def test_build_latex_document_renders_component_content(self) -> None:
        scenario = make_scenario()
        context = _build_report_context(
            scenario,
            selected_by_component={"component_handle": "mfr_alt"},
        )
        latex = _build_latex_document(
            context,
            narrative=ReportNarrativePayload.model_validate(
                {
                    "strapline": "A tighter route with lower operational drag.",
                    "executiveSummary": [
                        "The selected path lowers total q50 emissions versus the baseline."
                    ],
                    "pathNarrative": "The selected path improves transport and manufacturing signals.",
                    "componentFindings": [
                        {
                            "componentLabel": "Handle",
                            "takeaway": "The alternate supplier is cleaner and still balanced.",
                            "decisionNote": "Promote this route if procurement risk is acceptable.",
                        }
                    ],
                    "riskNarrative": "Climate and grid signals both improve.",
                    "recommendedActions": ["Pilot the alternate supplier for the handle."],
                    "closingNote": "The selected path is already the best eco route.",
                }
            ),
            generated_at="2026-04-19 00:00 UTC",
            model="gemma-4-26b-a4b-it",
        )
        self.assertIn("Widget", latex)
        self.assertIn("Handle", latex)
        self.assertIn("Pilot the alternate supplier", latex)
        self.assertNotIn("Selection status", latex)
        self.assertIn("Recommendation:", latex)
        self.assertNotIn("The selected path is already the best eco route.", latex)

    def test_build_latex_document_uses_current_total_when_selected_matches_current(self) -> None:
        scenario = make_scenario()
        context = _build_report_context(scenario, selected_by_component={})
        latex = _build_latex_document(
            context,
            narrative=ReportNarrativePayload.model_validate(
                {
                    "strapline": "Baseline route remains active.",
                    "executiveSummary": [
                        "Current path remains the active operating baseline."
                    ],
                    "pathNarrative": "No manual changes were applied, so the report anchors on the current path total instead of a zero delta.",
                    "componentFindings": [],
                    "riskNarrative": "The risk readout stays narrative even when the selected route has not changed.",
                    "recommendedActions": ["Review best eco alternatives before changing suppliers."],
                    "closingNote": "The baseline still needs an explicit decision if optimization is a priority.",
                }
            ),
            generated_at="2026-04-19 00:00 UTC",
            model="gemma-4-26b-a4b-it",
        )

        self.assertIn("Current path total", latex)
        self.assertIn("6 tCO2e", latex)
        self.assertIn("live baseline", latex)
        self.assertIn("Recommendation: move toward the best eco route.", latex)

    def test_build_latex_document_uses_absolute_component_signals_when_optimized(self) -> None:
        scenario = make_scenario()
        scenario.manufacturers[0].ecoScore = 10
        scenario.manufacturers[1].ecoScore = 30
        context = _build_report_context(scenario, selected_by_component={})
        latex = _build_latex_document(
            context,
            narrative=ReportNarrativePayload.model_validate(
                {
                    "strapline": "Baseline route remains active.",
                    "executiveSummary": [
                        "The current supplier already matches the eco leader for the handle."
                    ],
                    "pathNarrative": "No supplier switch is needed for the optimized component in this test.",
                    "componentFindings": [
                        {
                            "componentLabel": "Handle",
                            "takeaway": "The current supplier is already the best option.",
                            "decisionNote": "No immediate change is required.",
                        }
                    ],
                    "riskNarrative": "The current route stays in place.",
                    "recommendedActions": ["Retain the current handle supplier."],
                    "closingNote": "No change needed.",
                }
            ),
            generated_at="2026-04-19 00:00 UTC",
            model="gemma-4-26b-a4b-it",
        )

        self.assertIn("Comparison shown: Already optimized", latex)
        self.assertNotIn("Delta vs comparison route", latex)
        self.assertIn("6 tCO2e", latex)

    def test_build_latex_document_calls_out_placeholder_baseline_signals(self) -> None:
        scenario = make_scenario()
        scenario.manufacturers[0].ecoScore = 50
        scenario.manufacturers[0].gridCarbonScore = 50
        scenario.manufacturers[0].climateRiskScore = 50
        scenario.manufacturers[0].transportEmissionsTco2e = 0
        scenario.manufacturers[0].manufacturingEmissionsTco2e.q10 = 0
        scenario.manufacturers[0].manufacturingEmissionsTco2e.q50 = 0
        scenario.manufacturers[0].manufacturingEmissionsTco2e.q90 = 0
        context = _build_report_context(scenario, selected_by_component={})
        latex = _build_latex_document(
            context,
            narrative=ReportNarrativePayload.model_validate(
                {
                    "strapline": "Baseline route remains active.",
                    "executiveSummary": [
                        "Current path remains the active operating baseline."
                    ],
                    "pathNarrative": "The current baseline is partially inferred in this test case.",
                    "componentFindings": [],
                    "riskNarrative": "Signals are placeholder here.",
                    "recommendedActions": ["Review the current supplier baseline before using it as truth."],
                    "closingNote": "Confirm the current supplier scores first.",
                }
            ),
            generated_at="2026-04-19 00:00 UTC",
            model="gemma-4-26b-a4b-it",
        )

        self.assertIn("Baseline signal note", latex)
        self.assertIn("placeholder current suppliers", latex)

    async def test_generate_scenario_report_with_gemini_returns_pdf_payload(self) -> None:
        scenario = make_scenario()

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "strapline": "A tighter route with lower emissions.",
                                        "executiveSummary": [
                                            "The selected path outperforms the current route.",
                                            "The selected route also matches the best eco route.",
                                        ],
                                        "pathNarrative": (
                                            "Transport and manufacturing both improve on the selected path, "
                                            "while grid and climate scores also move in the right direction."
                                        ),
                                        "componentFindings": [
                                            {
                                                "componentLabel": "Handle",
                                                "takeaway": "The Hamburg supplier reduces total q50 materially.",
                                                "decisionNote": "Shift the handle first because the tradeoff is favorable.",
                                            }
                                        ],
                                        "riskNarrative": (
                                            "Manufacturing uncertainty bands still apply to factory emissions only, "
                                            "and certification coverage improves under the alternate."
                                        ),
                                        "recommendedActions": [
                                            "Pilot the alternate handle supplier.",
                                            "Track realized logistics costs after switching.",
                                        ],
                                        "closingNote": "The selected path is a strong default recommendation.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "GEMINI_MODEL": "gemma-4-26b-a4b-it",
            },
            clear=False,
        ):
            with patch(
                "httpx.AsyncClient.post",
                new=AsyncMock(return_value=mock_response),
            ) as mock_post, patch(
                "backend.report_generation._compile_latex_pdf",
                return_value=b"%PDF-1.4 fake pdf bytes",
            ):
                result = await generate_scenario_report_with_gemini(
                    scenario,
                    selected_by_component={"component_handle": "mfr_alt"},
                )

        self.assertEqual(result.model, "gemma-4-26b-a4b-it")
        self.assertEqual(result.format, "pdf")
        self.assertEqual(result.mimeType, "application/pdf")
        self.assertTrue(result.fileName.endswith(".pdf"))
        self.assertTrue(base64.b64decode(result.contentBase64).startswith(b"%PDF-1.4"))
        await_args = mock_post.await_args
        assert await_args is not None
        self.assertIn("/models/gemma-4-26b-a4b-it:generateContent", await_args.args[0])


if __name__ == "__main__":
    unittest.main()
