from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.db import (
    append_scenario_revision,
    count_scenario_revisions,
    ensure_scenario_history_baseline,
    get_active_scenario_revision,
    get_baseline_scenario_revision,
    init_db,
)
from backend.scenario_editing import (
    ScenarioEditConfigError,
    ScenarioEditIntentPayload,
    ScenarioEditProviderError,
    SupplyScenarioPayload,
    _extract_json_object_text,
    _build_intent_messages,
    _to_editable_scenario,
    apply_filtered_scenario,
    classify_prompt_with_k2,
    edit_scenario_with_k2,
    normalize_edited_scenario,
    restore_scenario_revision,
    _get_k2think_settings,
)


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
            "graph": {
                "edges": [
                    {
                        "id": "edge_product_component",
                        "sourceId": "product_widget",
                        "targetId": "component_handle",
                    },
                    {
                        "id": "edge_component_current",
                        "sourceId": "component_handle",
                        "targetId": "mfr_current",
                    },
                    {
                        "id": "edge_component_alt",
                        "sourceId": "component_handle",
                        "targetId": "mfr_alt",
                    },
                ],
                "nodes": [
                    {
                        "data": {
                            "childIds": ["component_handle"],
                            "graphPosition": {"x": -20, "y": -30},
                            "id": "product_widget",
                            "kind": "product",
                            "label": "Widget",
                            "subtitle": "1,000 units",
                        },
                        "id": "product_widget",
                        "position": {"x": -20, "y": -30},
                    },
                    {
                        "data": {
                            "graphPosition": {"x": 10, "y": 20},
                            "id": "component_handle",
                            "kind": "component",
                            "label": "Handle",
                            "manufacturerIds": ["mfr_current", "mfr_alt"],
                        },
                        "id": "component_handle",
                        "position": {"x": 10, "y": 20},
                    },
                    {
                        "data": {
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
                            "manufacturingEmissionsTco2e": {
                                "q10": 1.0,
                                "q50": 2.0,
                                "q90": 3.0,
                            },
                            "name": "Current Manufacturing",
                            "transportEmissionsTco2e": 4.0,
                        },
                        "id": "mfr_current",
                        "position": {"x": 30, "y": 40},
                    },
                    {
                        "data": {
                            "certifications": ["sbt"],
                            "climateRiskScore": 20,
                            "componentId": "component_handle",
                            "componentLabel": "Handle",
                            "ecoScore": 30,
                            "graphPosition": {"x": 50, "y": 60},
                            "gridCarbonScore": 22,
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
                            "manufacturingEmissionsTco2e": {
                                "q10": 0.8,
                                "q50": 1.4,
                                "q90": 2.1,
                            },
                            "name": "Alt Manufacturing",
                            "transportEmissionsTco2e": 2.5,
                        },
                        "id": "mfr_alt",
                        "position": {"x": 50, "y": 60},
                    },
                ],
            },
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
                    "certifications": ["sbt"],
                    "climateRiskScore": 20,
                    "componentId": "component_handle",
                    "componentLabel": "Handle",
                    "ecoScore": 30,
                    "graphPosition": {"x": 50, "y": 60},
                    "gridCarbonScore": 22,
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
                "graphEdgeCount": 3,
                "graphNodeCount": 4,
                "routeCount": 2,
                "siteCount": 3,
            },
            "title": "Widget",
            "unit": "units",
            "updatedAt": "Sample dataset",
        }
    )


class ScenarioEditingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "scenario-edit.db")
        self.env_patch = patch.dict(os.environ, {"DB_PATH": self.db_path}, clear=False)
        self.env_patch.start()
        init_db()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tempdir.cleanup()
        super().tearDown()

    def test_normalize_edited_scenario_applies_real_filter_edits(self) -> None:
        original = make_scenario()
        candidate = _to_editable_scenario(original)
        candidate.title = "Widget Mk II"
        candidate.quantity = 5000
        candidate.unit = "cases"
        candidate.destination.label = "Detroit"
        candidate.destination.location.city = "Detroit"
        candidate.components[0].label = "Grip"
        candidate.manufacturers[1].name = "Better Alt Manufacturing"
        candidate.manufacturers[1].ecoScore = 19
        candidate.manufacturers[1].isCurrent = True
        candidate.manufacturers = [candidate.manufacturers[1]]
        candidate.components[0].manufacturerIds = ["mfr_alt"]
        candidate.product.childIds = ["component_handle"]

        normalized = normalize_edited_scenario(original, candidate)

        self.assertEqual(normalized.title, "Widget Mk II")
        self.assertEqual(normalized.unit, "cases")
        self.assertEqual(normalized.quantity, 5000)
        self.assertEqual(normalized.product.subtitle, "5,000 cases")
        self.assertEqual(normalized.components[0].label, "Grip")
        self.assertEqual(normalized.manufacturers[0].componentLabel, "Grip")
        self.assertEqual(len(normalized.manufacturers), 1)
        self.assertEqual(normalized.manufacturers[0].id, "mfr_alt")
        self.assertEqual(normalized.manufacturers[0].name, "Better Alt Manufacturing")
        self.assertTrue(normalized.manufacturers[0].isCurrent)
        self.assertEqual(normalized.components[0].manufacturerIds, ["mfr_alt"])
        self.assertEqual(
            [edge.id for edge in normalized.graph.edges],
            [
                "edge_product_widget_component_handle",
                "edge_component_handle_mfr_alt",
            ],
        )
        self.assertEqual(normalized.stats.graphNodeCount, 3)
        self.assertEqual(normalized.stats.routeCount, 1)
        self.assertTrue(normalized.updatedAt.startswith("Edited "))

    def test_normalize_edited_scenario_rejects_inconsistent_component_membership(self) -> None:
        original = make_scenario()
        candidate = _to_editable_scenario(original)
        candidate.manufacturers = [candidate.manufacturers[1]]
        candidate.components[0].manufacturerIds = ["mfr_current"]

        with self.assertRaisesRegex(
            Exception, "manufacturerIds must match its manufacturers in order"
        ):
            normalize_edited_scenario(original, candidate)

    def test_apply_filtered_scenario_keeps_current_nodes(self) -> None:
        scenario = make_scenario()
        filtered = apply_filtered_scenario(scenario, keep_set=set())

        self.assertEqual(len(filtered.components), 1)
        self.assertEqual(len(filtered.manufacturers), 1)
        self.assertEqual(filtered.manufacturers[0].id, "mfr_current")
        self.assertTrue(filtered.manufacturers[0].isCurrent)
        self.assertEqual(filtered.components[0].manufacturerIds, ["mfr_current"])
        self.assertEqual(filtered.stats.routeCount, 1)

    def test_history_helpers_track_active_revision(self) -> None:
        scenario = make_scenario()
        baseline = ensure_scenario_history_baseline(
            scenario.id,
            json.dumps(scenario.model_dump(mode="json")),
        )
        self.assertEqual(baseline["op_type"], "baseline")
        stored_baseline = get_baseline_scenario_revision(scenario.id)
        assert stored_baseline is not None
        self.assertEqual(stored_baseline["id"], baseline["id"])
        self.assertEqual(count_scenario_revisions(scenario.id), 1)

        filtered = apply_filtered_scenario(scenario, keep_set=set())
        revision = append_scenario_revision(
            scenario_id=scenario.id,
            parent_id=int(baseline["id"]),
            op_type="filter",
            prompt_text="Show only current manufacturers",
            snapshot_json=json.dumps(filtered.model_dump(mode="json")),
        )
        active = get_active_scenario_revision(scenario.id)

        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active["id"], revision["id"])
        self.assertEqual(active["parent_id"], baseline["id"])
        self.assertEqual(count_scenario_revisions(scenario.id), 2)

    def test_restore_scenario_revision_undoes_multiple_steps(self) -> None:
        scenario = make_scenario()
        baseline = ensure_scenario_history_baseline(
            scenario.id,
            json.dumps(scenario.model_dump(mode="json")),
        )
        current_only = apply_filtered_scenario(scenario, keep_set=set())
        revision_1 = append_scenario_revision(
            scenario_id=scenario.id,
            parent_id=int(baseline["id"]),
            op_type="filter",
            prompt_text="Keep current only",
            snapshot_json=json.dumps(current_only.model_dump(mode="json")),
        )
        scenario_with_renamed_current = current_only.model_copy(deep=True)
        scenario_with_renamed_current.manufacturers[0].name = "Current Manufacturing Renamed"
        revision_2 = append_scenario_revision(
            scenario_id=scenario.id,
            parent_id=int(revision_1["id"]),
            op_type="filter",
            prompt_text="Rename current",
            snapshot_json=json.dumps(scenario_with_renamed_current.model_dump(mode="json")),
        )

        restored, reached_beginning = restore_scenario_revision(
            scenario.id,
            steps=2,
            prompt="undo the last 2 changes",
        )
        active = get_active_scenario_revision(scenario.id)

        self.assertFalse(reached_beginning)
        self.assertEqual(restored.title, scenario.title)
        self.assertEqual(len(restored.manufacturers), 2)
        self.assertEqual(restored.manufacturers[1].id, "mfr_alt")
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active["op_type"], "undo")
        self.assertIsNone(active["parent_id"])
        self.assertEqual(count_scenario_revisions(scenario.id), 4)
        self.assertEqual(int(revision_2["id"]), 3)

    def test_get_k2think_settings_requires_api_key(self) -> None:
        with patch.dict(
            os.environ,
            {"K2THINK_API_KEY": "", "K2THINK_MODEL": "MBZUAI-IFM/K2-Think-v2"},
            clear=False,
        ):
            with self.assertRaises(ScenarioEditConfigError):
                _get_k2think_settings()

    def test_build_intent_messages_uses_compact_summary(self) -> None:
        scenario = make_scenario()
        messages = _build_intent_messages("Only keep Asian manufacturers", scenario)
        payload = messages[1]["content"].split("Scenario summary:\n", 1)[1]
        parsed = json.loads(payload)
        self.assertNotIn("graph", parsed)
        self.assertNotIn("routes", parsed)
        self.assertNotIn("stats", parsed)
        self.assertEqual(parsed["alternate_manufacturer_count"], 1)

    def test_extract_json_object_text_handles_reasoning_prefix(self) -> None:
        raw = (
            'The prompt asks for undo.\n</think>\n'
            '{"op":"undo","undo_steps":1,"message":"Undoing the last change."}'
        )
        extracted = _extract_json_object_text(raw)
        parsed = json.loads(extracted)
        self.assertEqual(parsed["op"], "undo")
        self.assertEqual(parsed["undo_steps"], 1)

    def test_extract_json_object_text_handles_fenced_json(self) -> None:
        raw = (
            "```json\n"
            '{"decision":"keep","message":"Keep it.","reason":"Matches filter."}\n'
            "```"
        )
        extracted = _extract_json_object_text(raw)
        parsed = json.loads(extracted)
        self.assertEqual(parsed["decision"], "keep")

    def test_extract_json_object_text_rejects_missing_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "did not contain a JSON object"):
            _extract_json_object_text("No structured output here")

    async def test_classify_prompt_with_k2_parses_undo_steps(self) -> None:
        scenario = make_scenario()
        response_payload = {
            "choices": [
                {
                    "message": {
                        "content": (
                            "I will classify this as undo.\n</think>\n"
                            + json.dumps(
                                {
                                    "op": "undo",
                                    "undo_steps": 2,
                                    "message": "Undoing the last 2 changes.",
                                }
                            )
                        )
                    }
                }
            ]
        }
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = response_payload

        with patch.dict(
            os.environ,
            {
                "K2THINK_API_KEY": "test-key",
                "K2THINK_MODEL": "MBZUAI-IFM/K2-Think-v2",
            },
            clear=False,
        ):
            with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
                import httpx

                async with httpx.AsyncClient(timeout=5) as client:
                    result = await classify_prompt_with_k2(
                        client=client,
                        headers={
                            "Authorization": "Bearer test-key",
                            "accept": "application/json",
                            "Content-Type": "application/json",
                        },
                        model="MBZUAI-IFM/K2-Think-v2",
                        base_url="https://api.k2think.ai/v1",
                        prompt="undo the last 2 changes",
                        scenario=scenario,
                    )

        self.assertIsInstance(result, ScenarioEditIntentPayload)
        self.assertEqual(result.op, "undo")
        self.assertEqual(result.undo_steps, 2)

    async def test_edit_scenario_with_k2_filters_alternates_only(self) -> None:
        scenario = make_scenario()
        classify_response = Mock()
        classify_response.raise_for_status.return_value = None
        classify_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "op": "filter",
                                "undo_steps": 1,
                                "message": "Filtering alternates.",
                            }
                        )
                    }
                }
            ]
        }
        node_response = Mock()
        node_response.raise_for_status.return_value = None
        node_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "decision": "remove",
                                "message": "Remove this alternate.",
                                "reason": "Germany is not in Asia.",
                            }
                        )
                    }
                }
            ]
        }

        with patch.dict(
            os.environ,
            {
                "K2THINK_API_KEY": "test-key",
                "K2THINK_MODEL": "MBZUAI-IFM/K2-Think-v2",
            },
            clear=False,
        ):
            with patch(
                "httpx.AsyncClient.post",
                new=AsyncMock(side_effect=[classify_response, node_response]),
            ) as mock_post:
                result = await edit_scenario_with_k2(
                    "Show me only Asian manufacturers",
                    scenario,
                )

        self.assertEqual(mock_post.await_count, 2)
        self.assertEqual(result.status, "applied")
        assert result.scenario is not None
        self.assertEqual(len(result.scenario.manufacturers), 1)
        self.assertEqual(result.scenario.manufacturers[0].id, "mfr_current")
        self.assertIn("removed 1", result.message)
        self.assertEqual(count_scenario_revisions(scenario.id), 2)

    async def test_edit_scenario_with_k2_supports_undo(self) -> None:
        scenario = make_scenario()
        classify_filter = Mock()
        classify_filter.raise_for_status.return_value = None
        classify_filter.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "op": "filter",
                                "undo_steps": 1,
                                "message": "Filtering alternates.",
                            }
                        )
                    }
                }
            ]
        }
        node_remove = Mock()
        node_remove.raise_for_status.return_value = None
        node_remove.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "decision": "remove",
                                "message": "Remove this alternate.",
                                "reason": "Does not match.",
                            }
                        )
                    }
                }
            ]
        }
        classify_undo = Mock()
        classify_undo.raise_for_status.return_value = None
        classify_undo.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "op": "undo",
                                "undo_steps": 1,
                                "message": "Undoing the last change.",
                            }
                        )
                    }
                }
            ]
        }

        with patch.dict(
            os.environ,
            {
                "K2THINK_API_KEY": "test-key",
                "K2THINK_MODEL": "MBZUAI-IFM/K2-Think-v2",
            },
            clear=False,
        ):
            with patch(
                "httpx.AsyncClient.post",
                new=AsyncMock(side_effect=[classify_filter, node_remove, classify_undo]),
            ):
                filtered = await edit_scenario_with_k2("Show only Asian manufacturers", scenario)
                assert filtered.scenario is not None
                undone = await edit_scenario_with_k2(
                    "undo the changes that were just made",
                    filtered.scenario,
                )

        self.assertEqual(filtered.status, "applied")
        self.assertEqual(undone.status, "applied")
        assert undone.scenario is not None
        self.assertEqual(len(undone.scenario.manufacturers), 2)
        self.assertEqual(undone.scenario.manufacturers[1].id, "mfr_alt")

    async def test_edit_scenario_with_k2_filters_from_baseline_each_time(self) -> None:
        scenario = make_scenario()
        classify_filter_remove = Mock()
        classify_filter_remove.raise_for_status.return_value = None
        classify_filter_remove.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "op": "filter",
                                "undo_steps": 1,
                                "message": "Filtering to South America.",
                            }
                        )
                    }
                }
            ]
        }
        node_remove = Mock()
        node_remove.raise_for_status.return_value = None
        node_remove.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "decision": "remove",
                                "message": "Remove this alternate.",
                                "reason": "Germany is not in South America.",
                            }
                        )
                    }
                }
            ]
        }
        classify_filter_keep = Mock()
        classify_filter_keep.raise_for_status.return_value = None
        classify_filter_keep.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "op": "filter",
                                "undo_steps": 1,
                                "message": "Filtering to Asia.",
                            }
                        )
                    }
                }
            ]
        }
        node_keep = Mock()
        node_keep.raise_for_status.return_value = None
        node_keep.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "decision": "keep",
                                "message": "Keep this alternate.",
                                "reason": "Germany fixture kept to prove baseline reuse in tests.",
                            }
                        )
                    }
                }
            ]
        }

        with patch.dict(
            os.environ,
            {
                "K2THINK_API_KEY": "test-key",
                "K2THINK_MODEL": "MBZUAI-IFM/K2-Think-v2",
            },
            clear=False,
        ):
            with patch(
                "httpx.AsyncClient.post",
                new=AsyncMock(
                    side_effect=[
                        classify_filter_remove,
                        node_remove,
                        classify_filter_keep,
                        node_keep,
                    ]
                ),
            ):
                south_america = await edit_scenario_with_k2(
                    "Show me only manufacturers in South America",
                    scenario,
                )
                assert south_america.scenario is not None
                asia = await edit_scenario_with_k2(
                    "Show me some in Asia",
                    south_america.scenario,
                )

        assert asia.scenario is not None
        self.assertEqual(len(south_america.scenario.manufacturers), 1)
        self.assertEqual(len(asia.scenario.manufacturers), 2)
        self.assertEqual(asia.scenario.manufacturers[1].id, "mfr_alt")

    async def test_edit_scenario_with_k2_keeps_node_when_k2_eval_fails(self) -> None:
        scenario = make_scenario()
        classify_filter = Mock()
        classify_filter.raise_for_status.return_value = None
        classify_filter.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "op": "filter",
                                "undo_steps": 1,
                                "message": "Filtering alternates.",
                            }
                        )
                    }
                }
            ]
        }

        with patch.dict(
            os.environ,
            {
                "K2THINK_API_KEY": "test-key",
                "K2THINK_MODEL": "MBZUAI-IFM/K2-Think-v2",
            },
            clear=False,
        ):
            with patch(
                "httpx.AsyncClient.post",
                new=AsyncMock(
                    side_effect=[
                        classify_filter,
                        ScenarioEditProviderError("K2 Think request failed: ReadTimeout"),
                    ]
                ),
            ):
                result = await edit_scenario_with_k2(
                    "Show only Asian manufacturers",
                    scenario,
                )

        self.assertEqual(result.status, "applied")
        assert result.scenario is not None
        self.assertEqual(len(result.scenario.manufacturers), 2)
        self.assertIn("Preserved Alt Manufacturing", result.message)


if __name__ == "__main__":
    unittest.main()
