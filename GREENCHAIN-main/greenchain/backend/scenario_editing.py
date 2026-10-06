from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Literal, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .db import (
    append_scenario_revision,
    ensure_scenario_history_baseline,
    get_active_scenario_revision,
    get_baseline_scenario_revision,
    get_scenario_revision,
)

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupplyScenarioGraphPositionPayload(StrictModel):
    x: float
    y: float


class SupplyScenarioLocationPayload(StrictModel):
    city: str
    country: str
    countryCode: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class SupplyScenarioManufacturingEmissionsPayload(StrictModel):
    q10: float = Field(ge=0)
    q50: float = Field(ge=0)
    q90: float = Field(ge=0)


class SupplyScenarioTransportByModePayload(StrictModel):
    sea: float = Field(ge=0)
    air: float = Field(ge=0)
    rail: float = Field(ge=0)
    road: float = Field(ge=0)


class SupplyScenarioScoringInputsPayload(StrictModel):
    """Raw per-supplier signals the dashboard re-ranks with (weights / transport mode)."""

    certAdjustment: float = Field(gt=0)
    climateRisk: float = Field(ge=0, le=100)
    gridGco2Kwh: float = Field(ge=0)
    manufacturingTco2e: float = Field(ge=0)
    transportTco2eByMode: SupplyScenarioTransportByModePayload


class SupplyScenarioIndustryPayload(StrictModel):
    code: str
    title: str


class SupplyScenarioProductNodePayload(StrictModel):
    childIds: list[str]
    graphPosition: SupplyScenarioGraphPositionPayload
    id: str
    kind: Literal["product"]
    label: str
    subtitle: str | None = None


class SupplyScenarioComponentNodePayload(StrictModel):
    graphPosition: SupplyScenarioGraphPositionPayload
    id: str
    kind: Literal["component"]
    label: str
    manufacturerIds: list[str]


class SupplyScenarioManufacturerNodePayload(StrictModel):
    certifications: list[str]
    climateRiskScore: float = Field(ge=0, le=100)
    componentId: str
    componentLabel: str
    ecoScore: float = Field(ge=0, le=100)
    graphPosition: SupplyScenarioGraphPositionPayload
    gridCarbonScore: float = Field(ge=0, le=100)
    id: str
    industry: SupplyScenarioIndustryPayload | None = None
    isCurrent: bool
    kind: Literal["manufacturer"]
    location: SupplyScenarioLocationPayload
    manufacturingEmissionsTco2e: SupplyScenarioManufacturingEmissionsPayload
    name: str
    scoringInputs: SupplyScenarioScoringInputsPayload | None = None
    transportEmissionsTco2e: float = Field(ge=0)


class SupplyScenarioGraphNodeDataPayload(StrictModel):
    certifications: list[str] | None = None
    childIds: list[str] | None = None
    climateRiskScore: float | None = None
    componentId: str | None = None
    componentLabel: str | None = None
    ecoScore: float | None = None
    graphPosition: SupplyScenarioGraphPositionPayload
    gridCarbonScore: float | None = None
    id: str
    industry: SupplyScenarioIndustryPayload | None = None
    isCurrent: bool | None = None
    kind: Literal["product", "component", "manufacturer"]
    label: str | None = None
    location: SupplyScenarioLocationPayload | None = None
    manufacturerIds: list[str] | None = None
    manufacturingEmissionsTco2e: SupplyScenarioManufacturingEmissionsPayload | None = None
    name: str | None = None
    scoringInputs: SupplyScenarioScoringInputsPayload | None = None
    subtitle: str | None = None
    transportEmissionsTco2e: float | None = None


class SupplyScenarioGraphNodePayload(StrictModel):
    data: SupplyScenarioGraphNodeDataPayload
    id: str
    position: SupplyScenarioGraphPositionPayload


class SupplyScenarioGraphEdgePayload(StrictModel):
    id: str
    sourceId: str
    targetId: str


class SupplyScenarioDestinationPayload(StrictModel):
    id: str
    label: str
    location: SupplyScenarioLocationPayload


class SupplyScenarioRoutePayload(StrictModel):
    componentId: str
    destinationId: str
    id: str
    isCurrent: bool
    manufacturerId: str


class SupplyScenarioStatsPayload(StrictModel):
    componentCount: int = Field(ge=0)
    currentRouteCount: int = Field(ge=0)
    graphEdgeCount: int = Field(ge=0)
    graphNodeCount: int = Field(ge=0)
    routeCount: int = Field(ge=0)
    siteCount: int = Field(ge=0)


class SupplyScenarioPayload(StrictModel):
    components: list[SupplyScenarioComponentNodePayload]
    destination: SupplyScenarioDestinationPayload
    graph: "SupplyScenarioGraphPayload"
    id: str
    manufacturers: list[SupplyScenarioManufacturerNodePayload]
    product: SupplyScenarioProductNodePayload
    quantity: int = Field(ge=1)
    routes: list[SupplyScenarioRoutePayload]
    stats: SupplyScenarioStatsPayload
    title: str
    unit: str
    updatedAt: str


class SupplyScenarioGraphPayload(StrictModel):
    edges: list[SupplyScenarioGraphEdgePayload]
    nodes: list[SupplyScenarioGraphNodePayload]


class ScenarioEditRequestPayload(StrictModel):
    prompt: str
    scenario: SupplyScenarioPayload


class EditableScenarioPayload(StrictModel):
    components: list[SupplyScenarioComponentNodePayload]
    destination: SupplyScenarioDestinationPayload
    id: str
    manufacturers: list[SupplyScenarioManufacturerNodePayload]
    product: SupplyScenarioProductNodePayload
    quantity: int = Field(ge=1)
    title: str
    unit: str


class ScenarioEditIntentPayload(StrictModel):
    message: str
    op: Literal["filter", "undo", "reject"]
    undo_steps: int = Field(default=1, ge=1)


class ScenarioEditNodeDecisionPayload(StrictModel):
    decision: Literal["keep", "remove"]
    message: str
    reason: str


class ScenarioEditResponsePayload(StrictModel):
    message: str
    scenario: SupplyScenarioPayload | None = None
    status: Literal["applied", "rejected"]


_K2ResponseT = TypeVar(
    "_K2ResponseT", ScenarioEditIntentPayload, ScenarioEditNodeDecisionPayload
)


class ScenarioEditConfigError(RuntimeError):
    pass


class ScenarioEditProviderError(RuntimeError):
    pass


class ScenarioEditValidationError(ValueError):
    pass


def _normalize_base_url(value: str | None) -> str:
    raw = (value or "https://api.k2think.ai/v1").strip().rstrip("/")
    if not raw:
        return "https://api.k2think.ai/v1"
    return raw


def _get_k2think_settings() -> tuple[str, str, str, float]:
    api_key = os.environ.get("K2THINK_API_KEY", "").strip()
    if not api_key:
        raise ScenarioEditConfigError(
            "K2THINK_API_KEY is not set. Add it to backend/.env before using prompt edits."
        )

    model = os.environ.get("K2THINK_MODEL", "MBZUAI-IFM/K2-Think-v2").strip()
    if not model:
        raise ScenarioEditConfigError(
            "K2THINK_MODEL is empty. Set it to your K2 Think model name."
        )

    base_url = _normalize_base_url(os.environ.get("K2THINK_BASE_URL"))
    timeout_raw = os.environ.get("K2THINK_TIMEOUT_SECONDS", "120").strip()
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise ScenarioEditConfigError(
            "K2THINK_TIMEOUT_SECONDS must be a number."
        ) from exc
    if timeout_seconds <= 0:
        raise ScenarioEditConfigError(
            "K2THINK_TIMEOUT_SECONDS must be greater than 0."
        )
    return api_key, model, base_url, timeout_seconds


def _format_updated_at() -> str:
    return f"Edited {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}"


def _product_subtitle(quantity: int, unit: str) -> str:
    return f"{quantity:,} {unit}"


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ScenarioEditValidationError(f"{field_name} cannot be empty.")
    return normalized


def _normalize_location(
    location: SupplyScenarioLocationPayload, *, field_prefix: str
) -> SupplyScenarioLocationPayload:
    return location.model_copy(
        update={
            "city": _non_empty(location.city, f"{field_prefix} city"),
            "country": _non_empty(location.country, f"{field_prefix} country"),
            "countryCode": _non_empty(
                location.countryCode, f"{field_prefix} country code"
            ).upper(),
        }
    )


def _rebuild_graph(
    product: SupplyScenarioProductNodePayload,
    components: list[SupplyScenarioComponentNodePayload],
    manufacturers: list[SupplyScenarioManufacturerNodePayload],
) -> SupplyScenarioGraphPayload:
    graph_nodes = [
        SupplyScenarioGraphNodePayload(
            data=_build_graph_node_data(product),
            id=product.id,
            position=product.graphPosition,
        ),
        *[
            SupplyScenarioGraphNodePayload(
                data=_build_graph_node_data(component),
                id=component.id,
                position=component.graphPosition,
            )
            for component in components
        ],
        *[
            SupplyScenarioGraphNodePayload(
                data=_build_graph_node_data(manufacturer),
                id=manufacturer.id,
                position=manufacturer.graphPosition,
            )
            for manufacturer in manufacturers
        ],
    ]

    graph_edges = [
        *[
            SupplyScenarioGraphEdgePayload(
                id=f"edge_{product.id}_{component.id}",
                sourceId=product.id,
                targetId=component.id,
            )
            for component in components
        ],
        *[
            SupplyScenarioGraphEdgePayload(
                id=f"edge_{manufacturer.componentId}_{manufacturer.id}",
                sourceId=manufacturer.componentId,
                targetId=manufacturer.id,
            )
            for manufacturer in manufacturers
        ],
    ]

    return SupplyScenarioGraphPayload(edges=graph_edges, nodes=graph_nodes)


def _rebuild_routes(
    destination: SupplyScenarioDestinationPayload,
    manufacturers: list[SupplyScenarioManufacturerNodePayload],
) -> list[SupplyScenarioRoutePayload]:
    return [
        SupplyScenarioRoutePayload(
            componentId=manufacturer.componentId,
            destinationId=destination.id,
            id=f"route_{manufacturer.id}",
            isCurrent=manufacturer.isCurrent,
            manufacturerId=manufacturer.id,
        )
        for manufacturer in manufacturers
    ]


def _build_graph_node_data(
    node: (
        SupplyScenarioProductNodePayload
        | SupplyScenarioComponentNodePayload
        | SupplyScenarioManufacturerNodePayload
    ),
) -> SupplyScenarioGraphNodeDataPayload:
    if node.kind == "product":
        return SupplyScenarioGraphNodeDataPayload(
            childIds=node.childIds,
            graphPosition=node.graphPosition,
            id=node.id,
            kind=node.kind,
            label=node.label,
            subtitle=node.subtitle,
        )

    if node.kind == "component":
        return SupplyScenarioGraphNodeDataPayload(
            graphPosition=node.graphPosition,
            id=node.id,
            kind=node.kind,
            label=node.label,
            manufacturerIds=node.manufacturerIds,
        )

    return SupplyScenarioGraphNodeDataPayload(
        certifications=node.certifications,
        climateRiskScore=node.climateRiskScore,
        componentId=node.componentId,
        componentLabel=node.componentLabel,
        ecoScore=node.ecoScore,
        graphPosition=node.graphPosition,
        gridCarbonScore=node.gridCarbonScore,
        id=node.id,
        industry=node.industry,
        isCurrent=node.isCurrent,
        kind=node.kind,
        location=node.location,
        manufacturingEmissionsTco2e=node.manufacturingEmissionsTco2e,
        name=node.name,
        scoringInputs=node.scoringInputs,
        transportEmissionsTco2e=node.transportEmissionsTco2e,
    )


def _to_editable_scenario(scenario: SupplyScenarioPayload) -> EditableScenarioPayload:
    return EditableScenarioPayload(
        components=scenario.components,
        destination=scenario.destination,
        id=scenario.id,
        manufacturers=scenario.manufacturers,
        product=scenario.product,
        quantity=scenario.quantity,
        title=scenario.title,
        unit=scenario.unit,
    )


def normalize_edited_scenario(
    original: SupplyScenarioPayload,
    candidate: EditableScenarioPayload | SupplyScenarioPayload,
) -> SupplyScenarioPayload:
    title = _non_empty(candidate.title, "Scenario title")
    unit = _non_empty(candidate.unit, "Scenario unit")
    quantity = candidate.quantity

    components = [
        component.model_copy(update={"label": _non_empty(component.label, "Component label")})
        for component in candidate.components
    ]
    component_ids = [component.id for component in components]
    if not component_ids:
        raise ScenarioEditValidationError("Scenario must contain at least one component.")
    if len(component_ids) != len(set(component_ids)):
        raise ScenarioEditValidationError("Component IDs must be unique.")

    component_by_id = {component.id: component for component in components}

    if len(candidate.product.childIds) != len(set(candidate.product.childIds)):
        raise ScenarioEditValidationError("Product childIds must be unique.")
    if candidate.product.childIds != component_ids:
        raise ScenarioEditValidationError(
            "Product childIds must match the component IDs in order."
        )

    product = candidate.product.model_copy(
        update={
            "label": _non_empty(candidate.product.label, "Product label"),
            "subtitle": _product_subtitle(quantity, unit),
        }
    )

    manufacturers: list[SupplyScenarioManufacturerNodePayload] = []
    manufacturer_ids: list[str] = []
    current_count_by_component: dict[str, int] = {
        component.id: 0 for component in components
    }

    for manufacturer in candidate.manufacturers:
        if manufacturer.componentId not in component_by_id:
            raise ScenarioEditValidationError(
                f"Manufacturer {manufacturer.id} references unknown component {manufacturer.componentId}."
            )

        component_label = component_by_id[manufacturer.componentId].label
        normalized_manufacturer = manufacturer.model_copy(
            update={
                "name": _non_empty(manufacturer.name, "Manufacturer name"),
                "componentLabel": component_label,
                "location": _normalize_location(
                    manufacturer.location, field_prefix="Manufacturer"
                ),
            }
        )
        manufacturers.append(normalized_manufacturer)
        manufacturer_ids.append(normalized_manufacturer.id)
        if normalized_manufacturer.isCurrent:
            current_count_by_component[normalized_manufacturer.componentId] += 1

    if not manufacturer_ids:
        raise ScenarioEditValidationError("Scenario must contain at least one manufacturer.")
    if len(manufacturer_ids) != len(set(manufacturer_ids)):
        raise ScenarioEditValidationError("Manufacturer IDs must be unique.")

    for component in components:
        if len(component.manufacturerIds) != len(set(component.manufacturerIds)):
            raise ScenarioEditValidationError(
                f"Component {component.id} has duplicate manufacturerIds."
            )

        if not component.manufacturerIds:
            raise ScenarioEditValidationError(
                f"Component {component.id} must reference at least one manufacturer."
            )

        expected_ids = [
            manufacturer.id
            for manufacturer in manufacturers
            if manufacturer.componentId == component.id
        ]
        if component.manufacturerIds != expected_ids:
            raise ScenarioEditValidationError(
                f"Component {component.id} manufacturerIds must match its manufacturers in order."
            )

        if current_count_by_component.get(component.id, 0) != 1:
            raise ScenarioEditValidationError(
                f"Component {component.id} must have exactly one current manufacturer."
            )

    destination = candidate.destination.model_copy(
        update={
            "label": _non_empty(candidate.destination.label, "Destination label"),
            "location": _normalize_location(
                candidate.destination.location, field_prefix="Destination"
            ),
        }
    )

    routes = _rebuild_routes(destination, manufacturers)
    graph = _rebuild_graph(product, components, manufacturers)
    stats = SupplyScenarioStatsPayload(
        componentCount=len(components),
        currentRouteCount=sum(route.isCurrent for route in routes),
        graphEdgeCount=len(graph.edges),
        graphNodeCount=len(graph.nodes),
        routeCount=len(routes),
        siteCount=len(manufacturers) + 1,
    )

    return SupplyScenarioPayload(
        components=components,
        destination=destination,
        graph=graph,
        id=original.id,
        manufacturers=manufacturers,
        product=product,
        quantity=quantity,
        routes=routes,
        stats=stats,
        title=title,
        unit=unit,
        updatedAt=_format_updated_at(),
    )


def _build_scenario_summary(scenario: SupplyScenarioPayload) -> dict[str, object]:
    return {
        "scenario_id": scenario.id,
        "title": scenario.title,
        "destination": {
            "label": scenario.destination.label,
            "country": scenario.destination.location.country,
            "country_code": scenario.destination.location.countryCode,
        },
        "component_count": len(scenario.components),
        "alternate_manufacturer_count": sum(
            1 for manufacturer in scenario.manufacturers if not manufacturer.isCurrent
        ),
        "components": [
            {
                "id": component.id,
                "label": component.label,
                "current_manufacturers": [
                    manufacturer.name
                    for manufacturer in scenario.manufacturers
                    if manufacturer.componentId == component.id
                    and manufacturer.isCurrent
                ],
                "alternate_count": sum(
                    1
                    for manufacturer in scenario.manufacturers
                    if manufacturer.componentId == component.id
                    and not manufacturer.isCurrent
                ),
            }
            for component in scenario.components
        ],
    }


def _build_alternate_node_summary(
    manufacturer: SupplyScenarioManufacturerNodePayload,
) -> dict[str, object]:
    return {
        "id": manufacturer.id,
        "name": manufacturer.name,
        "country": manufacturer.location.country,
        "country_code": manufacturer.location.countryCode,
        "city": manufacturer.location.city,
        "certifications": manufacturer.certifications,
        "climate_risk_score": manufacturer.climateRiskScore,
        "eco_score": manufacturer.ecoScore,
        "grid_carbon_score": manufacturer.gridCarbonScore,
        "manufacturing_emissions_tco2e": manufacturer.manufacturingEmissionsTco2e.model_dump(
            mode="json"
        ),
        "transport_emissions_tco2e": manufacturer.transportEmissionsTco2e,
    }


def _build_intent_messages(
    prompt: str, scenario: SupplyScenarioPayload
) -> list[dict[str, str]]:
    scenario_json = json.dumps(_build_scenario_summary(scenario), separators=(",", ":"))
    return [
        {
            "role": "system",
            "content": (
                "You classify supply-chain dashboard prompts. "
                "Return JSON only with fields: op, undo_steps, message. "
                "Valid ops are: filter, undo, reject. "
                "Use op='undo' when the prompt asks to revert or undo one or more prompt-made changes. "
                "Set undo_steps to the number of changes to undo; default to 1. "
                "Use op='filter' when the prompt asks to show, hide, keep, remove, limit, or otherwise filter manufacturer options. "
                "Use op='reject' when the prompt is unrelated to filtering alternates or undoing prior prompt edits. "
                "Current manufacturers, product nodes, and component nodes are always kept outside this classification."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User prompt:\n{prompt.strip()}\n\n"
                "Scenario summary:\n"
                f"{scenario_json}"
            ),
        },
    ]


def _build_node_decision_messages(
    prompt: str,
    scenario: SupplyScenarioPayload,
    component: SupplyScenarioComponentNodePayload,
    manufacturer: SupplyScenarioManufacturerNodePayload,
) -> list[dict[str, str]]:
    component_current_manufacturers = [
        node.name
        for node in scenario.manufacturers
        if node.componentId == component.id and node.isCurrent
    ]
    payload = {
        "prompt": prompt.strip(),
        "scenario": {
            "title": scenario.title,
            "destination": scenario.destination.location.country,
        },
        "component": {
            "id": component.id,
            "label": component.label,
            "current_manufacturers": component_current_manufacturers,
        },
        "alternate_manufacturer": _build_alternate_node_summary(manufacturer),
    }
    return [
        {
            "role": "system",
            "content": (
                "You decide whether a single alternate manufacturer should remain visible in a filtered supply-chain dashboard. "
                "Current manufacturers, product nodes, and component nodes are always preserved elsewhere and are not part of this decision. "
                "Return JSON only with fields: decision, message, reason. "
                "Valid decisions are keep or remove. "
                "Use keep if the manufacturer satisfies the prompt or if the prompt is ambiguous for this node. "
                "Use remove only when the alternate clearly does not satisfy the prompt."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, separators=(",", ":")),
        },
    ]


def _extract_json_object_text(raw_content: str) -> str:
    text = raw_content.strip()
    if not text:
        raise ValueError("K2 Think returned an empty response body.")

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if not text:
            raise ValueError("K2 Think returned an empty fenced JSON body.")

    if text.startswith("{"):
        return text

    start = text.find("{")
    if start == -1:
        raise ValueError("K2 Think response did not contain a JSON object.")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("K2 Think response contained an unterminated JSON object.")


async def _call_k2_json(
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    model: str,
    base_url: str,
    messages: list[dict[str, str]],
    response_model: type[_K2ResponseT],
    temperature: float = 0.1,
) -> _K2ResponseT:
    parse_error: str | None = None
    conversation: list[dict[str, str]] = list(messages)

    for attempt in range(1, 4):
        request_body = {
            "model": model,
            "messages": conversation,
            "stream": False,
            "temperature": temperature,
        }

        try:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=request_body,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            raise ScenarioEditProviderError(
                f"K2 Think request failed with {exc.response.status_code}: {detail or exc.response.reason_phrase}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ScenarioEditProviderError(
                f"K2 Think request failed: {type(exc).__name__}: {exc}"
            ) from exc

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ScenarioEditProviderError(
                "K2 Think response did not include a chat completion payload."
            ) from exc

        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )

        try:
            decoded = json.loads(_extract_json_object_text(content))
            return response_model.model_validate(decoded)
        except Exception as exc:  # noqa: BLE001
            parse_error = str(exc)

        if attempt < 3:
            conversation = [
                *conversation,
                {
                    "role": "assistant",
                    "content": content if isinstance(content, str) else json.dumps(content),
                },
                {
                    "role": "user",
                    "content": (
                        "Your previous response was invalid. "
                        f"Problem: {parse_error}. "
                        "Return only valid JSON matching the required response schema."
                    ),
                },
            ]

    raise ScenarioEditProviderError(
        "K2 Think failed to return valid JSON for the scenario edit response after 3 attempts."
        + (f" Last error: {parse_error}" if parse_error else "")
    )


async def classify_prompt_with_k2(
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    model: str,
    base_url: str,
    prompt: str,
    scenario: SupplyScenarioPayload,
) -> ScenarioEditIntentPayload:
    result = await _call_k2_json(
        client=client,
        headers=headers,
        model=model,
        base_url=base_url,
        messages=_build_intent_messages(prompt, scenario),
        response_model=ScenarioEditIntentPayload,
    )
    return result


async def evaluate_alternate_node_with_k2(
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    model: str,
    base_url: str,
    prompt: str,
    scenario: SupplyScenarioPayload,
    component: SupplyScenarioComponentNodePayload,
    manufacturer: SupplyScenarioManufacturerNodePayload,
) -> ScenarioEditNodeDecisionPayload:
    result = await _call_k2_json(
        client=client,
        headers=headers,
        model=model,
        base_url=base_url,
        messages=_build_node_decision_messages(prompt, scenario, component, manufacturer),
        response_model=ScenarioEditNodeDecisionPayload,
    )
    return result


def apply_filtered_scenario(
    original_scenario: SupplyScenarioPayload,
    keep_set: set[str],
) -> SupplyScenarioPayload:
    filtered_manufacturers = [
        manufacturer
        for manufacturer in original_scenario.manufacturers
        if manufacturer.isCurrent or manufacturer.id in keep_set
    ]
    component_ids = {component.id for component in original_scenario.components}
    filtered_components = [
        component.model_copy(
            update={
                "manufacturerIds": [
                    manufacturer.id
                    for manufacturer in filtered_manufacturers
                    if manufacturer.componentId == component.id
                ]
            }
        )
        for component in original_scenario.components
        if component.id in component_ids
    ]
    candidate = EditableScenarioPayload(
        components=filtered_components,
        destination=original_scenario.destination,
        id=original_scenario.id,
        manufacturers=filtered_manufacturers,
        product=original_scenario.product,
        quantity=original_scenario.quantity,
        title=original_scenario.title,
        unit=original_scenario.unit,
    )
    return normalize_edited_scenario(original_scenario, candidate)


def _load_scenario_from_snapshot(snapshot_json: str) -> SupplyScenarioPayload:
    try:
        payload = json.loads(snapshot_json)
    except json.JSONDecodeError as exc:
        raise ScenarioEditValidationError(
            "Stored scenario history contained invalid JSON."
        ) from exc
    return SupplyScenarioPayload.model_validate(payload)


def restore_scenario_revision(
    scenario_id: str, steps: int, prompt: str
) -> tuple[SupplyScenarioPayload, bool]:
    active_revision = get_active_scenario_revision(scenario_id)
    if active_revision is None:
        raise ScenarioEditValidationError("No scenario history was found to undo.")

    target_revision = active_revision
    remaining_steps = max(1, steps)
    while remaining_steps > 0 and target_revision["parent_id"] is not None:
        parent_revision = get_scenario_revision(int(target_revision["parent_id"]))
        if parent_revision is None:
            break
        target_revision = parent_revision
        remaining_steps -= 1

    reached_beginning = remaining_steps > 0 and target_revision["parent_id"] is None
    restored_scenario = _load_scenario_from_snapshot(target_revision["snapshot_json"])
    append_scenario_revision(
        scenario_id=scenario_id,
        parent_id=target_revision["parent_id"],
        op_type="undo",
        prompt_text=prompt,
        snapshot_json=target_revision["snapshot_json"],
    )
    return restored_scenario, reached_beginning


def _scenario_to_snapshot_json(scenario: SupplyScenarioPayload) -> str:
    return json.dumps(scenario.model_dump(mode="json"), separators=(",", ":"))


async def edit_scenario_with_k2(
    prompt: str, scenario: SupplyScenarioPayload
) -> ScenarioEditResponsePayload:
    api_key, model, base_url, timeout_seconds = _get_k2think_settings()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    baseline_snapshot = _scenario_to_snapshot_json(scenario)
    ensure_scenario_history_baseline(scenario.id, baseline_snapshot)
    baseline_revision = get_baseline_scenario_revision(scenario.id)
    if baseline_revision is None:
        raise ScenarioEditValidationError("No baseline scenario history revision was found.")
    baseline_scenario = _load_scenario_from_snapshot(baseline_revision["snapshot_json"])

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        intent = await classify_prompt_with_k2(
            client=client,
            headers=headers,
            model=model,
            base_url=base_url,
            prompt=prompt,
            scenario=baseline_scenario,
        )

        if intent.op == "reject":
            return ScenarioEditResponsePayload(
                message=intent.message,
                status="rejected",
            )

        if intent.op == "undo":
            restored_scenario, reached_beginning = restore_scenario_revision(
                scenario.id, intent.undo_steps, prompt
            )
            message = intent.message
            if reached_beginning:
                message = (
                    f"{intent.message} Reached the earliest available scenario state."
                )
            return ScenarioEditResponsePayload(
                message=message,
                scenario=restored_scenario,
                status="applied",
            )

        active_revision = get_active_scenario_revision(scenario.id)
        if active_revision is None:
            raise ScenarioEditValidationError("No active scenario history revision was found.")

        alternate_manufacturers = [
            manufacturer
            for manufacturer in baseline_scenario.manufacturers
            if not manufacturer.isCurrent
        ]
        if not alternate_manufacturers:
            return ScenarioEditResponsePayload(
                message="No alternate manufacturers were available to filter.",
                scenario=baseline_scenario,
                status="applied",
            )

        component_by_id = {component.id: component for component in baseline_scenario.components}
        keep_ids: set[str] = set()
        evaluation_warnings: list[str] = []
        semaphore = asyncio.Semaphore(6)

        async def evaluate_manufacturer(
            manufacturer: SupplyScenarioManufacturerNodePayload,
        ) -> tuple[str, bool]:
            component = component_by_id[manufacturer.componentId]
            async with semaphore:
                try:
                    result = await evaluate_alternate_node_with_k2(
                        client=client,
                        headers=headers,
                        model=model,
                        base_url=base_url,
                        prompt=prompt,
                        scenario=baseline_scenario,
                        component=component,
                        manufacturer=manufacturer,
                    )
                except ScenarioEditProviderError:
                    evaluation_warnings.append(
                        f"Preserved {manufacturer.name} because K2 evaluation failed."
                    )
                    return manufacturer.id, True

            return manufacturer.id, result.decision == "keep"

        decisions = await asyncio.gather(
            *(evaluate_manufacturer(manufacturer) for manufacturer in alternate_manufacturers)
        )
        keep_ids.update(
            manufacturer_id
            for manufacturer_id, should_keep in decisions
            if should_keep
        )

        filtered_scenario = apply_filtered_scenario(baseline_scenario, keep_ids)
        append_scenario_revision(
            scenario_id=scenario.id,
            parent_id=int(active_revision["id"]),
            op_type="filter",
            prompt_text=prompt,
            snapshot_json=_scenario_to_snapshot_json(filtered_scenario),
        )

        removed_count = sum(1 for _, should_keep in decisions if not should_keep)
        kept_count = len(keep_ids)
        message = (
            f"{intent.message} Kept {kept_count} alternate manufacturer"
            f"{'' if kept_count == 1 else 's'} and removed {removed_count}."
        )
        if evaluation_warnings:
            message = f"{message} {' '.join(evaluation_warnings)}"

        return ScenarioEditResponsePayload(
            message=message,
            scenario=filtered_scenario,
            status="applied",
        )
