from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from statistics import mean
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scenario_editing import (
    SupplyScenarioComponentNodePayload,
    SupplyScenarioManufacturerNodePayload,
    SupplyScenarioPayload,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _normalize_narrative_text(value: Any) -> str:
    if isinstance(value, list):
        parts = [_normalize_narrative_text(item) for item in value]
        return " ".join(part for part in parts if part)
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return ""


class ScenarioScoringWeightsPayload(StrictModel):
    manufacturing: float = Field(ge=0)
    transport: float = Field(ge=0)
    grid_carbon: float = Field(ge=0)
    certifications: float = Field(ge=0)
    climate_risk: float = Field(ge=0)


class ScenarioScoringPayload(StrictModel):
    """The transport mode and dimension weights the dashboard scored with."""

    transportMode: Literal["sea", "air", "rail", "road"]
    weights: ScenarioScoringWeightsPayload


class ScenarioReportRequestPayload(StrictModel):
    scenario: SupplyScenarioPayload
    selectedManufacturerByComponent: dict[str, str] = Field(default_factory=dict)
    scoring: ScenarioScoringPayload | None = None


class ScenarioReportResponsePayload(StrictModel):
    contentBase64: str
    fileName: str
    format: Literal["pdf", "tex"]
    generatedAt: str
    mimeType: str
    model: str


class ReportNarrativeComponentPayload(StrictModel):
    componentLabel: str
    takeaway: str
    decisionNote: str


class ReportNarrativePayload(StrictModel):
    strapline: str
    executiveSummary: list[str]
    pathNarrative: str
    componentFindings: list[ReportNarrativeComponentPayload]
    riskNarrative: str
    recommendedActions: list[str]
    closingNote: str

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_narrative_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)

        if "pathNarrative" not in normalized:
            normalized["pathNarrative"] = _normalize_narrative_text(
                normalized.pop("pathComparison", "")
            )
        else:
            normalized["pathNarrative"] = _normalize_narrative_text(
                normalized["pathNarrative"]
            )

        if "riskNarrative" not in normalized:
            normalized["riskNarrative"] = _normalize_narrative_text(
                normalized.pop("riskReadout", "")
            )
        else:
            normalized["riskNarrative"] = _normalize_narrative_text(
                normalized["riskNarrative"]
            )

        return normalized


class ReportGenerationConfigError(RuntimeError):
    pass


class ReportGenerationProviderError(RuntimeError):
    pass


def _normalize_gemini_base_url(value: str | None) -> str:
    raw = (value or "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
    if not raw:
        return "https://generativelanguage.googleapis.com/v1beta"
    return raw


def _get_gemini_settings() -> tuple[str, str, str, str | None]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ReportGenerationConfigError(
            "GEMINI_API_KEY is not set. Add it to backend/.env before using report downloads."
        )

    model = os.environ.get("GEMINI_MODEL", "gemma-4-26b-a4b-it").strip()
    if not model:
        raise ReportGenerationConfigError(
            "GEMINI_MODEL is empty. Set it to a valid Gemini API model name."
        )

    thinking_level = os.environ.get("GEMINI_THINKING_LEVEL", "").strip() or None
    base_url = _normalize_gemini_base_url(os.environ.get("GEMINI_BASE_URL"))
    return api_key, model, base_url, thinking_level


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "scenario"


def _report_timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())


def _report_generated_at() -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())


def _format_decimal(value: float | int, digits: int = 1) -> str:
    rounded = round(float(value), digits)
    if digits == 0:
        return str(int(round(rounded)))
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.{digits}f}"


def _format_signed(value: float | int, digits: int = 1, suffix: str = "") -> str:
    numeric = float(value)
    sign = "+" if numeric > 0 else ""
    return f"{sign}{_format_decimal(numeric, digits)}{suffix}"


def _manufacturer_metrics(
    manufacturer: SupplyScenarioManufacturerNodePayload,
) -> dict[str, Any]:
    manufacturing = manufacturer.manufacturingEmissionsTco2e
    total_q50 = manufacturing.q50 + manufacturer.transportEmissionsTco2e
    return {
        "id": manufacturer.id,
        "name": manufacturer.name,
        "isCurrent": manufacturer.isCurrent,
        "location": {
            "city": manufacturer.location.city,
            "country": manufacturer.location.country,
            "countryCode": manufacturer.location.countryCode,
        },
        "certifications": manufacturer.certifications,
        "signals": {
            "ecoScore": manufacturer.ecoScore,
            "climateRiskScore": manufacturer.climateRiskScore,
            "gridCarbonScore": manufacturer.gridCarbonScore,
            "manufacturingEmissionsTco2e": {
                "q10": manufacturing.q10,
                "q50": manufacturing.q50,
                "q90": manufacturing.q90,
            },
            "transportEmissionsTco2e": manufacturer.transportEmissionsTco2e,
            "estimatedTotalQ50Tco2e": _round(total_q50),
        },
    }


def _is_placeholder_current_signals(
    manufacturer: SupplyScenarioManufacturerNodePayload,
) -> bool:
    manufacturing = manufacturer.manufacturingEmissionsTco2e
    return (
        manufacturer.isCurrent
        and manufacturer.ecoScore == 50
        and manufacturer.gridCarbonScore == 50
        and manufacturer.climateRiskScore == 50
        and manufacturer.transportEmissionsTco2e == 0
        and manufacturing.q10 == 0
        and manufacturing.q50 == 0
        and manufacturing.q90 == 0
    )


def _path_summary(
    label: str,
    manufacturers: list[SupplyScenarioManufacturerNodePayload],
) -> dict[str, Any]:
    if not manufacturers:
        return {
            "label": label,
            "componentCount": 0,
            "manufacturers": [],
            "totals": {},
        }

    manufacturing_q10 = sum(item.manufacturingEmissionsTco2e.q10 for item in manufacturers)
    manufacturing_q50 = sum(item.manufacturingEmissionsTco2e.q50 for item in manufacturers)
    manufacturing_q90 = sum(item.manufacturingEmissionsTco2e.q90 for item in manufacturers)
    transport_total = sum(item.transportEmissionsTco2e for item in manufacturers)

    certifications = sorted(
        {
            certification
            for manufacturer in manufacturers
            for certification in manufacturer.certifications
        }
    )

    return {
        "label": label,
        "componentCount": len(manufacturers),
        "manufacturers": [
            {
                "componentId": manufacturer.componentId,
                "componentLabel": manufacturer.componentLabel,
                **_manufacturer_metrics(manufacturer),
            }
            for manufacturer in manufacturers
        ],
        "totals": {
            "manufacturingQ10Tco2e": _round(manufacturing_q10),
            "manufacturingQ50Tco2e": _round(manufacturing_q50),
            "manufacturingQ90Tco2e": _round(manufacturing_q90),
            "transportTco2e": _round(transport_total),
            "estimatedTotalQ50Tco2e": _round(manufacturing_q50 + transport_total),
            "averageEcoScore": _round(mean(item.ecoScore for item in manufacturers), 1),
            "averageClimateRiskScore": _round(
                mean(item.climateRiskScore for item in manufacturers), 1
            ),
            "averageGridCarbonScore": _round(
                mean(item.gridCarbonScore for item in manufacturers), 1
            ),
            "uniqueCertifications": certifications,
            "uniqueCertificationCount": len(certifications),
        },
    }


def _delta_summary(
    baseline: SupplyScenarioManufacturerNodePayload,
    candidate: SupplyScenarioManufacturerNodePayload,
) -> dict[str, Any]:
    baseline_total = (
        baseline.manufacturingEmissionsTco2e.q50 + baseline.transportEmissionsTco2e
    )
    candidate_total = (
        candidate.manufacturingEmissionsTco2e.q50 + candidate.transportEmissionsTco2e
    )
    absolute_delta = candidate_total - baseline_total
    percent_delta = 0.0
    if baseline_total > 0:
        percent_delta = (absolute_delta / baseline_total) * 100

    return {
        "estimatedTotalQ50Tco2eDelta": _round(absolute_delta),
        "estimatedTotalQ50PctDelta": _round(percent_delta, 1),
        "ecoScoreDelta": _round(candidate.ecoScore - baseline.ecoScore, 1),
        "transportTco2eDelta": _round(
            candidate.transportEmissionsTco2e - baseline.transportEmissionsTco2e
        ),
        "manufacturingQ50Tco2eDelta": _round(
            candidate.manufacturingEmissionsTco2e.q50
            - baseline.manufacturingEmissionsTco2e.q50
        ),
        "gridCarbonScoreDelta": _round(
            candidate.gridCarbonScore - baseline.gridCarbonScore, 1
        ),
        "climateRiskScoreDelta": _round(
            candidate.climateRiskScore - baseline.climateRiskScore, 1
        ),
    }


def _path_delta_summary(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_totals = baseline.get("totals", {})
    candidate_totals = candidate.get("totals", {})
    baseline_total = float(baseline_totals.get("estimatedTotalQ50Tco2e") or 0)
    candidate_total = float(candidate_totals.get("estimatedTotalQ50Tco2e") or 0)
    absolute_delta = candidate_total - baseline_total
    percent_delta = 0.0
    if baseline_total > 0:
        percent_delta = (absolute_delta / baseline_total) * 100

    return {
        "estimatedTotalQ50Tco2eDelta": _round(absolute_delta),
        "estimatedTotalQ50PctDelta": _round(percent_delta, 1),
        "manufacturingQ50Tco2eDelta": _round(
            float(candidate_totals.get("manufacturingQ50Tco2e") or 0)
            - float(baseline_totals.get("manufacturingQ50Tco2e") or 0)
        ),
        "transportTco2eDelta": _round(
            float(candidate_totals.get("transportTco2e") or 0)
            - float(baseline_totals.get("transportTco2e") or 0)
        ),
        "averageEcoScoreDelta": _round(
            float(candidate_totals.get("averageEcoScore") or 0)
            - float(baseline_totals.get("averageEcoScore") or 0),
            1,
        ),
        "averageClimateRiskScoreDelta": _round(
            float(candidate_totals.get("averageClimateRiskScore") or 0)
            - float(baseline_totals.get("averageClimateRiskScore") or 0),
            1,
        ),
        "averageGridCarbonScoreDelta": _round(
            float(candidate_totals.get("averageGridCarbonScore") or 0)
            - float(baseline_totals.get("averageGridCarbonScore") or 0),
            1,
        ),
    }


def _resolve_selected_manufacturer(
    component: SupplyScenarioComponentNodePayload,
    manufacturers_by_component: dict[str, list[SupplyScenarioManufacturerNodePayload]],
    selected_by_component: dict[str, str],
) -> SupplyScenarioManufacturerNodePayload:
    options = manufacturers_by_component[component.id]
    selected_id = selected_by_component.get(component.id)
    if selected_id:
        selected = next((item for item in options if item.id == selected_id), None)
        if selected:
            return selected

    current = next((item for item in options if item.isCurrent), None)
    if current:
        return current

    return options[0]


_WEIGHT_LABELS = {
    "manufacturing": "manufacturing",
    "transport": "transport",
    "grid_carbon": "grid carbon",
    "certifications": "certifications",
    "climate_risk": "climate risk",
}


def _scoring_summary(scoring: ScenarioScoringPayload | None) -> dict[str, Any] | None:
    if scoring is None:
        return None
    weights = scoring.weights.model_dump()
    total = sum(weights.values())
    return {
        "transportMode": scoring.transportMode,
        "weightSharesPct": {
            key: _round(value / total * 100, 1) if total > 0 else 0.0
            for key, value in weights.items()
        },
    }


def _scoring_weights_text(scoring: dict[str, Any]) -> str:
    shares = scoring["weightSharesPct"]
    return ", ".join(
        f"{_WEIGHT_LABELS.get(key, key)} {_format_decimal(value, 0)}%"
        for key, value in shares.items()
    )


def _build_report_context(
    scenario: SupplyScenarioPayload,
    selected_by_component: dict[str, str],
    scoring: ScenarioScoringPayload | None = None,
) -> dict[str, Any]:
    manufacturers_by_component = {
        component.id: [
            manufacturer
            for manufacturer in scenario.manufacturers
            if manufacturer.componentId == component.id
        ]
        for component in scenario.components
    }

    current_path: list[SupplyScenarioManufacturerNodePayload] = []
    selected_path: list[SupplyScenarioManufacturerNodePayload] = []
    best_eco_path: list[SupplyScenarioManufacturerNodePayload] = []
    components_summary: list[dict[str, Any]] = []
    placeholder_current_components: list[dict[str, str]] = []

    for component in scenario.components:
        options = manufacturers_by_component.get(component.id, [])
        if not options:
            continue

        current = next((item for item in options if item.isCurrent), options[0])
        selected = _resolve_selected_manufacturer(
            component, manufacturers_by_component, selected_by_component
        )
        best_eco = min(options, key=lambda item: (item.ecoScore, not item.isCurrent))

        current_path.append(current)
        selected_path.append(selected)
        best_eco_path.append(best_eco)

        if _is_placeholder_current_signals(current):
            placeholder_current_components.append(
                {
                    "componentLabel": component.label,
                    "manufacturerName": current.name,
                }
            )

        option_summaries = sorted(
            (_manufacturer_metrics(option) for option in options),
            key=lambda option: (
                float(option["signals"]["ecoScore"]),
                option["name"].lower(),
            ),
        )
        components_summary.append(
            {
                "componentId": component.id,
                "componentLabel": component.label,
                "currentManufacturerId": current.id,
                "currentManufacturerName": current.name,
                "selectedManufacturerId": selected.id,
                "selectedManufacturerName": selected.name,
                "bestEcoManufacturerId": best_eco.id,
                "bestEcoManufacturerName": best_eco.name,
                "selectedDiffersFromCurrent": selected.id != current.id,
                "selectedMatchesBestEco": selected.id == best_eco.id,
                "currentVsSelected": _delta_summary(current, selected),
                "currentVsBestEco": _delta_summary(current, best_eco),
                "manufacturers": option_summaries,
            }
        )

    current_summary = _path_summary("Current path", current_path)
    selected_summary = _path_summary("Selected path", selected_path)
    best_eco_summary = _path_summary("Best eco path", best_eco_path)

    current_hotspots = sorted(
        (
            {
                "componentLabel": manufacturer.componentLabel,
                "manufacturerName": manufacturer.name,
                "estimatedTotalQ50Tco2e": _round(
                    manufacturer.manufacturingEmissionsTco2e.q50
                    + manufacturer.transportEmissionsTco2e
                ),
            }
            for manufacturer in current_path
        ),
        key=lambda item: float(str(item["estimatedTotalQ50Tco2e"])),
        reverse=True,
    )[:3]

    reduction_opportunities = sorted(
        (
            {
                "componentLabel": component["componentLabel"],
                "currentManufacturerId": component["currentManufacturerId"],
                "currentManufacturerName": component["currentManufacturerName"],
                "bestEcoManufacturerId": component["bestEcoManufacturerId"],
                "bestEcoManufacturerName": component["bestEcoManufacturerName"],
                "estimatedTotalQ50Tco2eDelta": component["currentVsBestEco"][
                    "estimatedTotalQ50Tco2eDelta"
                ],
                "estimatedTotalQ50PctDelta": component["currentVsBestEco"][
                    "estimatedTotalQ50PctDelta"
                ],
            }
            for component in components_summary
        ),
        key=lambda item: item["estimatedTotalQ50Tco2eDelta"],
    )[:3]

    selected_changes = [
        {
            "componentLabel": component["componentLabel"],
            "currentManufacturerId": component["currentManufacturerId"],
            "currentManufacturerName": component["currentManufacturerName"],
            "selectedManufacturerId": component["selectedManufacturerId"],
            "selectedManufacturerName": component["selectedManufacturerName"],
        }
        for component in components_summary
        if component["selectedDiffersFromCurrent"]
    ]

    return {
        "scenario": {
            "id": scenario.id,
            "title": scenario.title,
            "quantity": scenario.quantity,
            "unit": scenario.unit,
            "updatedAt": scenario.updatedAt,
            "destination": {
                "label": scenario.destination.label,
                "country": scenario.destination.location.country,
                "countryCode": scenario.destination.location.countryCode,
            },
            "stats": scenario.stats.model_dump(mode="json"),
        },
        "signalDirections": {
            "ecoScore": "lower is better",
            "climateRiskScore": "lower is better",
            "gridCarbonScore": "higher is better",
            "manufacturingEmissionsTco2e": "lower is better",
            "transportEmissionsTco2e": "lower is better",
            "estimatedTotalQ50Tco2e": "lower is better",
            "certifications": "more relevant certifications are generally better",
        },
        "paths": {
            "current": current_summary,
            "selected": selected_summary,
            "bestEco": best_eco_summary,
            "selectedVsCurrent": _path_delta_summary(current_summary, selected_summary),
            "bestEcoVsCurrent": _path_delta_summary(current_summary, best_eco_summary),
        },
        "components": components_summary,
        "highlights": {
            "selectedPathDiffersFromCurrent": bool(selected_changes),
            "selectedPathMatchesBestEco": all(
                component["selectedMatchesBestEco"] for component in components_summary
            )
            if components_summary
            else True,
            "selectedRouteChanges": selected_changes,
            "currentHotspots": current_hotspots,
            "biggestReductionOpportunities": reduction_opportunities,
        },
        "provenance": {
            "scenarioUpdatedAt": scenario.updatedAt,
            "currentBaselineHasPlaceholderSignals": bool(
                placeholder_current_components
            ),
            "placeholderCurrentComponents": placeholder_current_components,
        },
        "scoring": _scoring_summary(scoring),
    }


def _build_report_prompt(context: dict[str, Any]) -> str:
    context_json = json.dumps(context, separators=(",", ":"), ensure_ascii=True)
    return (
        "Generate a structured sustainability report narrative for a supply-chain scenario.\n\n"
        "Return JSON only. No markdown, no code fences, no commentary.\n\n"
        "Requirements:\n"
        "- Treat the JSON as the source of truth. Do not invent facts, suppliers, or metrics.\n"
        "- Use every signal family somewhere in the response: eco score, climate risk, "
        "grid carbon score, manufacturing q10/q50/q90, transport emissions, certifications, "
        "component-level deltas, and path-level totals.\n"
        "- Compare three paths when available: current, selected, and best eco.\n"
        "- Explain tradeoffs, not just the lowest-emissions option.\n"
        "- Prefer short, direct business prose and ASCII punctuation.\n"
        "- Use plain CO2e instead of special subscripts or Unicode chemistry notation.\n"
        "- Keep the output concise and decision-oriented.\n"
        "- Avoid list-shaped prose for extended analysis. Use compact paragraph text for path and risk narrative.\n"
        "- The JSON shape must be:\n"
        "  {\n"
        '    "strapline": string,\n'
        '    "executiveSummary": string[],\n'
        '    "pathNarrative": string,\n'
        '    "componentFindings": [{"componentLabel": string, "takeaway": string, "decisionNote": string}],\n'
        '    "riskNarrative": string,\n'
        '    "recommendedActions": string[],\n'
        '    "closingNote": string\n'
        "  }\n"
        "- executiveSummary should contain 2 to 3 short standalone lines.\n"
        "- recommendedActions should contain 2 to 4 concise bullets.\n"
        "- pathNarrative and riskNarrative should each be a short paragraph, not a list.\n"
        "- componentFindings should focus on the most decision-relevant components, not every component.\n"
        "- If the selected path already matches the best eco path, say so directly.\n"
        "- Mention uncertainty correctly: q10/q50/q90 refer to manufacturing emissions only.\n"
        "- When scoring is present, transport emissions and eco scores reflect that transport mode "
        "and those dimension weights; say so when explaining the ranking.\n"
        "- If current baseline placeholder signals are present, say the baseline is partially inferred from uploaded supplier identity rather than fully scored.\n\n"
        f"Signal bundle JSON:\n{context_json}"
    )


def _extract_text_response(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ReportGenerationProviderError(
            "Gemini response did not include any candidates."
        )

    content = candidates[0].get("content")
    if not isinstance(content, dict):
        raise ReportGenerationProviderError(
            "Gemini response did not include a candidate content payload."
        )

    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ReportGenerationProviderError(
            "Gemini response did not include text parts."
        )

    text = "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ).strip()

    if not text:
        raise ReportGenerationProviderError(
            "Gemini response did not include any text content."
        )

    return text


def _build_report_contents(prompt: str) -> list[dict[str, Any]]:
    return [{"role": "user", "parts": [{"text": prompt}]}]


def _decode_report_narrative(raw_text: str) -> ReportNarrativePayload:
    decoded = json.loads(raw_text)
    return ReportNarrativePayload.model_validate(decoded)


def _latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _latex_bullets(items: list[str]) -> str:
    if not items:
        return (
            "\\begin{itemize}[leftmargin=1.15em,itemsep=0.14em,topsep=0.18em,parsep=0pt,partopsep=0pt]"
            "\\item No additional commentary available."
            "\\end{itemize}"
        )

    rows = "\n".join(f"\\item {_latex_escape(item)}" for item in items)
    return (
        "\\begin{itemize}[leftmargin=1.15em,itemsep=0.14em,topsep=0.18em,parsep=0pt,partopsep=0pt]\n"
        f"{rows}\n"
        "\\end{itemize}"
    )


def _latex_paragraphs(items: list[str]) -> str:
    paragraphs = [
        _normalize_narrative_text(item)
        for item in items
        if _normalize_narrative_text(item)
    ]
    if not paragraphs:
        return _latex_paragraph("")

    escaped = [f"\\noindent {_latex_escape(item)}" for item in paragraphs]
    return "\n\n".join(escaped)


def _latex_paragraph(
    value: str,
    *,
    fallback: str = "No additional commentary available.",
) -> str:
    paragraph = _normalize_narrative_text(value) or fallback
    return f"\\noindent {_latex_escape(paragraph)}"


def _component_display_comparison(component: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if component["selectedDiffersFromCurrent"]:
        return "Selected vs current", component["currentVsSelected"]
    if component["bestEcoManufacturerId"] != component["currentManufacturerId"]:
        return "Current vs best eco", component["currentVsBestEco"]
    return "Already optimized", component["currentVsSelected"]


def _component_manufacturer_summary(
    component: dict[str, Any], manufacturer_id: str
) -> dict[str, Any] | None:
    return next(
        (
            manufacturer
            for manufacturer in component["manufacturers"]
            if manufacturer["id"] == manufacturer_id
        ),
        None,
    )


def _component_metric_grid(
    component: dict[str, Any],
) -> tuple[str, str, list[tuple[str, str]], list[tuple[str, str]]]:
    comparison_label, delta = _component_display_comparison(component)

    if comparison_label == "Already optimized":
        current = _component_manufacturer_summary(
            component, component["currentManufacturerId"]
        )
        if current:
            signals = current["signals"]
            return (
                comparison_label,
                "Current absolute signals",
                [
                    (
                        "Total q50",
                        f'{_format_decimal(signals["estimatedTotalQ50Tco2e"], 1)} tCO2e',
                    ),
                    (
                        "Transport",
                        f'{_format_decimal(signals["transportEmissionsTco2e"], 1)} tCO2e',
                    ),
                    (
                        "Grid score",
                        _format_decimal(signals["gridCarbonScore"], 1),
                    ),
                ],
                [
                    (
                        "Manufacturing",
                        f'{_format_decimal(signals["manufacturingEmissionsTco2e"]["q50"], 1)} tCO2e',
                    ),
                    ("Eco score", _format_decimal(signals["ecoScore"], 1)),
                    (
                        "Climate risk",
                        _format_decimal(signals["climateRiskScore"], 1),
                    ),
                ],
            )

    return (
        comparison_label,
        "Delta vs comparison route",
        [
            (
                "Total",
                f'{_format_signed(delta["estimatedTotalQ50Tco2eDelta"], 1, " tCO2e")} '
                f'({_format_signed(delta["estimatedTotalQ50PctDelta"], 1, "%")})',
            ),
            (
                "Transport",
                _format_signed(delta["transportTco2eDelta"], 1, " tCO2e"),
            ),
            ("Grid score", _format_signed(delta["gridCarbonScoreDelta"], 1)),
        ],
        [
            (
                "Manufacturing",
                _format_signed(delta["manufacturingQ50Tco2eDelta"], 1, " tCO2e"),
            ),
            ("Eco score", _format_signed(delta["ecoScoreDelta"], 1)),
            (
                "Climate risk",
                _format_signed(delta["climateRiskScoreDelta"], 1),
            ),
        ],
    )


def _latex_component_metric_table(rows: list[tuple[str, str]]) -> str:
    table_rows = []
    for index, (label, value) in enumerate(rows):
        row_suffix = r" \\[0.26em]" if index < len(rows) - 1 else r" \\"
        table_rows.append(
            f'\\strut {{\\color{{muted}} {_latex_escape(label)}}} & \\strut {_latex_escape(value)}{row_suffix}'
        )
    joined_rows = "\n".join(table_rows)

    return (
        "\\footnotesize\n"
        "\\begin{tabular*}{\\linewidth}{@{}l@{\\extracolsep{\\fill}}r@{}}\n"
        f"{joined_rows}\n"
        "\\end{tabular*}"
    )


def _summary_metrics(context: dict[str, Any]) -> list[dict[str, str]]:
    selected_delta = context["paths"]["selectedVsCurrent"]
    best_eco_delta = context["paths"]["bestEcoVsCurrent"]
    current_total = context["paths"]["current"]["totals"].get("estimatedTotalQ50Tco2e", 0)
    current_matches_best_eco = all(
        component["bestEcoManufacturerId"] == component["currentManufacturerId"]
        for component in context["components"]
    )

    if context["highlights"]["selectedPathDiffersFromCurrent"]:
        primary_card = {
            "tone": "primary",
            "title": "Selected vs current",
            "value": _format_signed(
                selected_delta["estimatedTotalQ50Tco2eDelta"], 1, " tCO2e"
            ),
            "detail": (
                f'{_format_signed(selected_delta["estimatedTotalQ50PctDelta"], 1, "%")} '
                "total q50 change"
            ),
        }
    else:
        primary_card = {
            "tone": "primary",
            "title": "Current path total",
            "value": f'{_format_decimal(current_total, 1)} tCO2e',
            "detail": "Selected route currently matches the live baseline.",
        }

    if current_matches_best_eco:
        best_eco_card = {
            "tone": "accent",
            "title": "Best eco route",
            "value": "Already selected",
            "detail": "Current suppliers already match the eco leader.",
        }
    else:
        best_eco_card = {
            "tone": "accent",
            "title": (
                "Best eco reduction"
                if best_eco_delta["estimatedTotalQ50Tco2eDelta"] < 0
                else "Best eco tradeoff"
            ),
            "value": _format_signed(
                best_eco_delta["estimatedTotalQ50Tco2eDelta"], 1, " tCO2e"
            ),
            "detail": (
                f'{_format_signed(best_eco_delta["averageEcoScoreDelta"], 1)} eco '
                "vs current path"
            ),
        }

    return [primary_card, best_eco_card]


def _build_specific_closing_note(context: dict[str, Any]) -> str:
    current_totals = context["paths"]["current"]["totals"]
    selected_delta = context["paths"]["selectedVsCurrent"]
    best_eco_delta = context["paths"]["bestEcoVsCurrent"]
    selected_matches_best = context["highlights"]["selectedPathMatchesBestEco"]
    selected_differs = context["highlights"]["selectedPathDiffersFromCurrent"]
    current_total = _format_decimal(
        current_totals.get("estimatedTotalQ50Tco2e", 0), 1
    )
    current_eco = _format_decimal(current_totals.get("averageEcoScore", 0), 1)
    current_grid = _format_decimal(
        current_totals.get("averageGridCarbonScore", 0), 1
    )
    current_risk = _format_decimal(
        current_totals.get("averageClimateRiskScore", 0), 1
    )

    def movement(delta: dict[str, Any]) -> str:
        return (
            f'{_format_signed(delta["estimatedTotalQ50Tco2eDelta"], 1, " tCO2e")} '
            f'({_format_signed(delta["estimatedTotalQ50PctDelta"], 1, "%")}) total q50, '
            f'{_format_signed(delta["averageEcoScoreDelta"], 1)} avg eco, '
            f'{_format_signed(delta["averageGridCarbonScoreDelta"], 1)} grid, and '
            f'{_format_signed(delta["averageClimateRiskScoreDelta"], 1)} climate risk'
        )

    if not selected_differs and selected_matches_best:
        return (
            f"Recommendation: keep the current path. It already matches the best eco route at "
            f"{current_total} tCO2e total q50, with average eco {current_eco}, grid {current_grid}, "
            f"and climate risk {current_risk}."
        )

    if selected_differs and selected_matches_best:
        return (
            "Recommendation: adopt the selected path. Versus current, it changes "
            f"{movement(selected_delta)}."
        )

    if selected_differs and not selected_matches_best:
        return (
            "Recommendation: treat the selected path as an interim move rather than the final target. "
            f"Versus current, it changes {movement(selected_delta)}, while the best eco route would change "
            f"{movement(best_eco_delta)}."
        )

    if float(best_eco_delta["estimatedTotalQ50Tco2eDelta"]) < 0:
        return (
            "Recommendation: move toward the best eco route. Relative to the current baseline, it would change "
            f"{movement(best_eco_delta)}."
        )

    return (
        "Recommendation: keep the current path unless eco score improvement is worth the emissions and resilience tradeoff. "
        f"Moving to the best eco route would change {movement(best_eco_delta)} versus current."
    )


def _baseline_provenance_note(context: dict[str, Any]) -> str | None:
    provenance = context.get("provenance", {})
    placeholder_components = provenance.get("placeholderCurrentComponents", [])
    if not placeholder_components:
        return None

    labels = ", ".join(item["componentLabel"] for item in placeholder_components)
    return (
        "Current baseline signals are partially inferred for "
        f"{labels}. The search response did not return scored current matches for those components, "
        "so the app created placeholder current suppliers from the uploaded baseline rows with provisional "
        "eco, grid, and climate scores of 50 and zero emissions until a scored current result is available."
    )


def _latex_summary_cards(context: dict[str, Any]) -> str:
    metrics = _summary_metrics(context)
    provenance_note = _baseline_provenance_note(context)

    metric_boxes = "\n\\hfill\n".join(
        (
            "\\begin{minipage}[t]{0.49\\linewidth}\n"
            "\\metriccard"
            f'{{{_latex_escape(metric["tone"])}}}'
            f'{{{_latex_escape(metric["title"])}}}'
            f'{{{_latex_escape(metric["value"])}}}'
            f'{{{_latex_escape(metric["detail"])}}}\n'
            "\\end{minipage}"
        )
        for metric in metrics
    )

    provenance_markup = ""
    if provenance_note:
        provenance_markup = f"""

\\vspace{{0.28em}}
\\begin{{tcolorbox}}[
  colback=accentSoft,
  colframe=accent!32!line,
  boxrule=0.55pt,
  sharp corners,
  left=2.2mm,right=2.2mm,top=1.4mm,bottom=1.4mm
]
{{\\sffamily\\scriptsize\\color{{accent}} Baseline signal note}}\\\\[0.15em]
{{\\footnotesize\\color{{ink}} {_latex_escape(provenance_note)}}}
\\end{{tcolorbox}}
""".rstrip()

    return f"""
\\noindent
{metric_boxes}
{provenance_markup}
""".strip()


def _latex_component_box(
    component: dict[str, Any],
    finding: ReportNarrativeComponentPayload | None,
) -> str:
    comparison_label, _, left_metrics, right_metrics = _component_metric_grid(component)
    takeaway = finding.takeaway if finding else "No narrative generated for this component."
    decision_note = finding.decisionNote if finding else "Review this component directly in the dashboard."
    left_metric_table = _latex_component_metric_table(left_metrics)
    right_metric_table = _latex_component_metric_table(right_metrics)

    return f"""
\\begin{{tcolorbox}}[
  colback=paper,
  colframe=line,
  colbacktitle=primarySoft,
  coltitle=primaryDeep,
  boxrule=0.65pt,
  sharp corners,
  left=2.6mm,right=2.6mm,top=2mm,bottom=2mm,
  title={{\\sffamily\\bfseries {_latex_escape(component["componentLabel"])}}}
]
{{\\sffamily\\scriptsize\\color{{muted}} Comparison shown: {_latex_escape(comparison_label)}}}

\\vspace{{0.18em}}
\\small
\\begin{{tabularx}}{{\\linewidth}}{{@{{}}>{{\\bfseries}}p{{0.22\\linewidth}}X@{{}}}}
\\textbf{{Current route}} & {_latex_escape(component["currentManufacturerName"])} \\\\
\\textbf{{Selected route}} & {_latex_escape(component["selectedManufacturerName"])} \\\\
\\textbf{{Best eco route}} & {_latex_escape(component["bestEcoManufacturerName"])} \\\\
\\end{{tabularx}}

\\vspace{{0.24em}}
\\noindent
\\begin{{minipage}}[t]{{0.485\\linewidth}}
{left_metric_table}
\\end{{minipage}}
\\hfill
\\begin{{minipage}}[t]{{0.485\\linewidth}}
{right_metric_table}
\\end{{minipage}}

\\vspace{{0.42em}}
\\footnotesize\\textbf{{Takeaway.}} {_latex_escape(takeaway)}

\\vspace{{0.18em}}
\\footnotesize\\textbf{{Decision note.}} {_latex_escape(decision_note)}
\\end{{tcolorbox}}
""".strip()


def _latex_path_table(context: dict[str, Any]) -> str:
    def row(path_key: str) -> tuple[str, dict[str, Any]]:
        path = context["paths"][path_key]
        return path["label"], path["totals"]

    rows = []
    for path_key in ("current", "selected", "bestEco"):
        label, totals = row(path_key)
        rows.append(
            " & ".join(
                [
                    _latex_escape(label),
                    _latex_escape(_format_decimal(totals.get("estimatedTotalQ50Tco2e", 0), 1)),
                    _latex_escape(_format_decimal(totals.get("manufacturingQ50Tco2e", 0), 1)),
                    _latex_escape(_format_decimal(totals.get("transportTco2e", 0), 1)),
                    _latex_escape(_format_decimal(totals.get("averageEcoScore", 0), 1)),
                    _latex_escape(_format_decimal(totals.get("averageGridCarbonScore", 0), 1)),
                    _latex_escape(_format_decimal(totals.get("averageClimateRiskScore", 0), 1)),
                ]
            )
            + r" \\"
        )

    table_rows = "\n".join(rows)
    return f"""
\\begin{{tcolorbox}}[
  colback=paper,
  colframe=line,
  boxrule=0.6pt,
  sharp corners,
  left=2mm,right=2mm,top=1.2mm,bottom=0.9mm,
  boxsep=0mm
]
\\footnotesize
\\arrayrulecolor{{line}}
\\setlength{{\\tabcolsep}}{{6pt}}
\\begin{{tabularx}}{{\\linewidth}}{{@{{}}>{{\\raggedright\\arraybackslash}}X*{{6}}{{>{{\\raggedleft\\arraybackslash}}p{{0.11\\linewidth}}}}@{{}}}}
\\toprule
\\textbf{{Path}} & \\textbf{{Total q50}} & \\textbf{{Mfg q50}} & \\textbf{{Transport}} & \\textbf{{Avg eco}} & \\textbf{{Grid}} & \\textbf{{Risk}} \\\\
\\midrule
{table_rows}
\\bottomrule
\\end{{tabularx}}
\\end{{tcolorbox}}
""".strip()


def _build_latex_document(
    context: dict[str, Any],
    narrative: ReportNarrativePayload,
    *,
    generated_at: str,
    model: str,
) -> str:
    scenario = context["scenario"]
    closing_note = _build_specific_closing_note(context)
    scoring = context.get("scoring")
    transport_header = (
        f" \\quad \\textbullet \\quad Transport: {_latex_escape(scoring['transportMode'].title())}"
        if scoring
        else ""
    )
    weights_note = (
        f" Eco scores use weights: {_latex_escape(_scoring_weights_text(scoring))}."
        if scoring
        else ""
    )
    findings_by_component = {
        finding.componentLabel.lower(): finding for finding in narrative.componentFindings
    }

    component_boxes = "\n\n".join(
        _latex_component_box(
            component,
            findings_by_component.get(component["componentLabel"].lower()),
        )
        for component in context["components"]
    )
    if not component_boxes:
        component_boxes = (
            "\\begin{tcolorbox}[colback=paper,colframe=line,boxrule=0.6pt,sharp corners]"
            "No component alternatives are available in the current scenario."
            "\\end{tcolorbox}"
        )

    hotspot_lines = context["highlights"]["currentHotspots"]
    hotspot_markup = _latex_bullets(
        [
            f'{item["componentLabel"]}: {item["manufacturerName"]} at {item["estimatedTotalQ50Tco2e"]} tCO2e q50.'
            for item in hotspot_lines
        ]
    )
    opportunity_markup = _latex_bullets(
        [
            f'{item["componentLabel"]}: switching from {item["currentManufacturerName"]} to '
            f'{item["bestEcoManufacturerName"]} changes total q50 by '
            f'{_format_signed(item["estimatedTotalQ50Tco2eDelta"], 1, " tCO2e")} '
            f'({_format_signed(item["estimatedTotalQ50PctDelta"], 1, "%")}).'
            for item in context["highlights"]["biggestReductionOpportunities"]
        ]
    )

    return f"""
\\documentclass[10pt]{{article}}
\\usepackage[a4paper,margin=14mm]{{geometry}}
\\usepackage[table]{{xcolor}}
\\usepackage{{fontspec}}
\\usepackage{{booktabs}}
\\usepackage{{tabularx}}
\\usepackage{{array}}
\\usepackage{{enumitem}}
\\usepackage[hidelinks]{{hyperref}}
\\usepackage[most]{{tcolorbox}}
\\usepackage{{fancyhdr}}
\\usepackage{{microtype}}
\\usepackage{{titlesec}}

\\definecolor{{pagebg}}{{HTML}}{{FBFAF6}}
\\definecolor{{paper}}{{HTML}}{{FFFFFF}}
\\definecolor{{panelTint}}{{HTML}}{{F3F7F2}}
\\definecolor{{ink}}{{HTML}}{{24313D}}
\\definecolor{{muted}}{{HTML}}{{6C7784}}
\\definecolor{{line}}{{HTML}}{{DCE4DE}}
\\definecolor{{primary}}{{HTML}}{{2B8A5B}}
\\definecolor{{primaryDeep}}{{HTML}}{{206847}}
\\definecolor{{primarySoft}}{{HTML}}{{EAF5EE}}
\\definecolor{{accent}}{{HTML}}{{C7922B}}
\\definecolor{{accentSoft}}{{HTML}}{{FBF4E5}}
\\definecolor{{signal}}{{HTML}}{{BF5F2D}}

\\defaultfontfeatures{{Ligatures=TeX, Scale=MatchLowercase}}
\\IfFontExistsTF{{Avenir Next}}{{
  \\setmainfont{{Avenir Next}}
  \\setsansfont{{Avenir Next}}
}}{{%
  \\IfFontExistsTF{{Helvetica Neue}}{{
    \\setmainfont{{Helvetica Neue}}
    \\setsansfont{{Helvetica Neue}}
  }}{{
    \\setmainfont{{TeX Gyre Heros}}
    \\setsansfont{{TeX Gyre Heros}}
  }}
}}
\\IfFontExistsTF{{Iowan Old Style}}{{
  \\newfontfamily\\headingfont{{Iowan Old Style}}
}}{{%
  \\IfFontExistsTF{{Palatino}}{{
    \\newfontfamily\\headingfont{{Palatino}}
  }}{{
    \\newfontfamily\\headingfont{{TeX Gyre Pagella}}
  }}
}}
\\newcommand{{\\reportlabel}}[1]{{{{\\sffamily\\fontsize{{8}}{{10}}\\selectfont\\addfontfeatures{{LetterSpace=12}}\\MakeUppercase{{#1}}}}}}
\\renewcommand{{\\arraystretch}}{{1.16}}
\\setlength{{\\parindent}}{{0pt}}
\\setlength{{\\parskip}}{{0.22em}}

\\pagestyle{{fancy}}
\\fancyhf{{}}
\\renewcommand{{\\headrulewidth}}{{0pt}}
\\fancyfoot[L]{{\\sffamily\\footnotesize\\color{{muted}} GreenChain}}
\\fancyfoot[R]{{\\sffamily\\footnotesize\\color{{muted}} \\thepage}}

\\titleformat{{\\section}}{{\\sffamily\\fontsize{{14}}{{16}}\\selectfont\\bfseries\\color{{ink}}}}{{}}{{0pt}}{{}}
\\titleformat{{\\subsection}}{{\\sffamily\\fontsize{{10.5}}{{12.5}}\\selectfont\\bfseries\\color{{ink}}}}{{}}{{0pt}}{{}}
\\titlespacing*{{\\section}}{{0pt}}{{0.62em}}{{0.12em}}
\\titlespacing*{{\\subsection}}{{0pt}}{{0.34em}}{{0.08em}}

\\newcommand{{\\metriccard}}[4]{{
\\begin{{tcolorbox}}[
  colback=paper,
  colframe=#1!22!line,
  borderline north={{1.8pt}}{{0pt}}{{#1}},
  boxrule=0.7pt,
  sharp corners,
  left=2.4mm,right=2.4mm,top=1.8mm,bottom=1.8mm
]
{{\\sffamily\\scriptsize\\color{{#1}} #2}}\\\\[0.35em]
{{\\sffamily\\fontsize{{18}}{{20}}\\selectfont\\bfseries\\color{{ink}} #3}}\\\\[0.2em]
{{\\footnotesize\\color{{muted}} #4}}
\\end{{tcolorbox}}
}}

\\begin{{document}}
\\thispagestyle{{empty}}
\\pagecolor{{pagebg}}
\\color{{ink}}

\\begin{{tcolorbox}}[
  colback=paper,
  colframe=line,
  borderline north={{2.3pt}}{{0pt}}{{primary}},
  sharp corners,
  left=5.2mm,right=5.2mm,top=4.6mm,bottom=4.2mm
]
{{\\color{{primary}}\\reportlabel{{Supply Chain Sustainability Report}}}}\\\\[0.55em]
{{\\headingfont\\fontsize{{25}}{{27}}\\selectfont\\bfseries\\color{{ink}} {_latex_escape(scenario["title"])}}}\\\\[0.12em]
{{\\normalsize\\color{{muted}} {_latex_escape(narrative.strapline)}}}\\\\[0.52em]
{{\\footnotesize\\color{{muted}} {_latex_escape(f'{scenario["quantity"]:,} {scenario["unit"]}')} \\quad \\textbullet \\quad Destination: {_latex_escape(scenario["destination"]["country"])}{transport_header} \\quad \\textbullet \\quad Generated {_latex_escape(generated_at)}}}
\\end{{tcolorbox}}

\\vspace{{0.28em}}

{_latex_summary_cards(context)}

\\section*{{Summary}}
{_latex_paragraphs(narrative.executiveSummary)}

\\section*{{Path Snapshot}}
{_latex_path_table(context)}

\\vspace{{0.2em}}
{_latex_paragraph(narrative.pathNarrative)}

\\section*{{Component Calls}}
{component_boxes}

\\section*{{Signal Readout}}
\\subsection*{{Narrative}}
{_latex_paragraph(narrative.riskNarrative)}

\\subsection*{{Current Hotspots}}
{hotspot_markup}

\\subsection*{{Best Eco Deltas}}
{opportunity_markup}

\\section*{{Next Steps}}
{_latex_bullets(narrative.recommendedActions)}

\\begin{{tcolorbox}}[
  colback=accentSoft,
  colframe=accent!40!line,
  boxrule=0.7pt,
  sharp corners,
  left=2.6mm,right=2.6mm,top=2mm,bottom=2mm
]
\\textbf{{Closing note.}} {_latex_escape(closing_note)}
\\end{{tcolorbox}}

\\vfill
{{\\footnotesize\\color{{muted}} Scenario source: {_latex_escape(scenario["updatedAt"])}. Built from GreenChain scenario signals using {_latex_escape(model)}. Manufacturing uncertainty bands q10, q50, and q90 refer to manufacturing emissions only.{weights_note}}}

\\end{{document}}
""".strip()


def _find_xelatex() -> str | None:
    configured = os.environ.get("GREENCHAIN_LATEX_ENGINE", "").strip()
    if configured:
        return configured
    return shutil.which("xelatex")


def _compile_latex_pdf(tex_source: str, file_stem: str) -> bytes | None:
    engine = _find_xelatex()
    if not engine:
        return None

    with tempfile.TemporaryDirectory(prefix="greenchain-report-") as temp_dir:
        temp_path = Path(temp_dir)
        tex_path = temp_path / f"{file_stem}.tex"
        pdf_path = temp_path / f"{file_stem}.pdf"
        tex_path.write_text(tex_source, encoding="utf-8")

        command = [
            engine,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(temp_path),
            str(tex_path),
        ]

        for _ in range(2):
            result = subprocess.run(
                command,
                cwd=temp_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return None

        if not pdf_path.exists():
            return None

        return pdf_path.read_bytes()


async def generate_scenario_report_with_gemini(
    scenario: SupplyScenarioPayload,
    selected_by_component: dict[str, str] | None = None,
    scoring: ScenarioScoringPayload | None = None,
) -> ScenarioReportResponsePayload:
    api_key, model, base_url, thinking_level = _get_gemini_settings()
    selected_lookup = selected_by_component or {}
    context = _build_report_context(scenario, selected_lookup, scoring)
    prompt = _build_report_prompt(context)
    generated_at = _report_generated_at()

    contents = _build_report_contents(prompt)
    narrative: ReportNarrativePayload | None = None
    parse_error: str | None = None

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(1, 4):
            request_body: dict[str, Any] = {
                "systemInstruction": {
                    "parts": [
                        {
                            "text": (
                                "You are GreenChain's report writer. "
                                "Return compact factual JSON grounded only in the supplied scenario metrics. "
                                "Prefer direct comparisons, quantified statements, and decision-oriented language."
                            )
                        }
                    ]
                },
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 4096,
                },
            }

            if thinking_level:
                request_body["generationConfig"]["thinkingConfig"] = {
                    "thinkingLevel": thinking_level
                }

            try:
                response = await client.post(
                    f"{base_url}/models/{model}:generateContent",
                    headers=headers,
                    json=request_body,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip()
                raise ReportGenerationProviderError(
                    f"Gemini request failed with {exc.response.status_code}: "
                    f"{detail or exc.response.reason_phrase}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ReportGenerationProviderError(
                    f"Gemini request failed: {type(exc).__name__}: {exc}"
                ) from exc

            raw_text = _extract_text_response(response.json())

            try:
                narrative = _decode_report_narrative(raw_text)
            except Exception as exc:  # noqa: BLE001
                parse_error = str(exc)
                if attempt >= 3:
                    break
                contents = [
                    *contents,
                    {"role": "model", "parts": [{"text": raw_text}]},
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "Your previous response was invalid JSON for the required schema. "
                                    f"Problem: {parse_error}. "
                                    "Retry and return only valid JSON."
                                )
                            }
                        ],
                    },
                ]
            else:
                break

    if narrative is None:
        raise ReportGenerationProviderError(
            "Gemini failed to return valid JSON for the report after 3 attempts."
            + (f" Last error: {parse_error}" if parse_error else "")
        )

    file_stem = f"greenchain-{_slugify(scenario.title)}-report-{_report_timestamp()}"
    tex_source = _build_latex_document(
        context,
        narrative,
        generated_at=generated_at,
        model=model,
    )
    pdf_bytes = _compile_latex_pdf(tex_source, file_stem)

    if pdf_bytes is not None:
        return ScenarioReportResponsePayload(
            contentBase64=base64.b64encode(pdf_bytes).decode("ascii"),
            fileName=f"{file_stem}.pdf",
            format="pdf",
            generatedAt=generated_at,
            mimeType="application/pdf",
            model=model,
        )

    return ScenarioReportResponsePayload(
        contentBase64=base64.b64encode(tex_source.encode("utf-8")).decode("ascii"),
        fileName=f"{file_stem}.tex",
        format="tex",
        generatedAt=generated_at,
        mimeType="application/x-tex",
        model=model,
    )
