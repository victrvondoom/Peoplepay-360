import type { ManufacturerResult, SearchResponse } from "@/lib/api"
import { getCountryCentroid, getCountryName } from "@/lib/country-coords"
import type {
  ScenarioSearchCsv,
  ScenarioSearchCsvComponentRow,
} from "@/lib/csv-to-search"
import {
  type ManufacturerScoringInputs,
  type SupplyScenario,
  type SupplyScenarioComponentNode,
  type SupplyScenarioDestination,
  type SupplyScenarioGraphEdge,
  type SupplyScenarioGraphNode,
  type SupplyScenarioLocation,
  type SupplyScenarioManufacturerNode,
  type SupplyScenarioProductNode,
} from "@/lib/supply-chain-scenario"

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function buildLocation(
  countryCode: string,
  city: string | null
): SupplyScenarioLocation {
  const iso = countryCode.trim().toUpperCase()
  const centroid = getCountryCentroid(iso)
  const name = getCountryName(iso)
  return {
    city: city?.trim() || name,
    country: name,
    countryCode: iso,
    lat: centroid.lat,
    lng: centroid.lng,
  }
}

function climateRiskFromRating(
  rating: ManufacturerResult["env_rating"]
): number {
  if (rating === "green") return 20
  if (rating === "amber") return 50
  return 80
}

function climateRiskScore(result: ManufacturerResult): number {
  const risk = result.scores.climate_risk_score
  return typeof risk === "number" && Number.isFinite(risk)
    ? clamp(Math.round(risk * 10) / 10, 0, 100)
    : climateRiskFromRating(result.env_rating)
}

function gridScoreFromNorm(gridNorm: number): number {
  return clamp(Math.round(100 - gridNorm), 0, 100)
}

/**
 * The API's composite_score is "higher = better"; the dashboard's ecoScore is
 * an impact score where lower is better (green < 40, red >= 60).
 */
function ecoScoreFromComposite(composite: number): number {
  return clamp(Math.round(100 - composite), 0, 100)
}

function toScoringInputs(
  inputs: ManufacturerResult["scoring_inputs"]
): ManufacturerScoringInputs | null {
  if (!inputs) {
    return null
  }
  const byMode = inputs.transport_tco2e_by_mode
  return {
    certAdjustment: inputs.cert_adjustment,
    climateRisk: inputs.climate_risk,
    gridGco2Kwh: inputs.grid_gco2_kwh,
    manufacturingTco2e: inputs.manufacturing_tco2e,
    transportTco2eByMode: {
      air: byMode.air,
      rail: byMode.rail,
      road: byMode.road,
      sea: byMode.sea,
    },
  }
}

function describeSearchRun(
  response: SearchResponse,
  componentCount: number
): string {
  const parts = [
    `Live search · ${componentCount} components · ${response.duration_seconds.toFixed(1)}s`,
  ]
  const cacheHits = response.cache_hits ?? 0
  if (cacheHits > 0) {
    parts.push(`${cacheHits} from cache`)
  }
  const fallbacks = response.fallback_components ?? []
  if (fallbacks.length > 0) {
    parts.push(`placeholder suppliers for ${fallbacks.join(", ")}`)
  }
  return parts.join(" · ")
}

function slugify(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40) || "node"
  )
}

function normalizeComponentKey(value: string): string {
  return value.trim().toLowerCase()
}

function radialPosition(index: number, total: number, radius: number) {
  if (total <= 0) return { x: 0, y: 0 }
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2
  return {
    x: Math.round(Math.cos(angle) * radius),
    y: Math.round(Math.sin(angle) * radius),
  }
}

function offsetPosition(
  base: { x: number; y: number },
  offset: { x: number; y: number }
) {
  return {
    x: base.x + offset.x,
    y: base.y + offset.y,
  }
}

function buildManufacturerNode(
  result: ManufacturerResult,
  componentId: string,
  componentLabel: string,
  index: number
): SupplyScenarioManufacturerNode {
  return {
    certifications: result.certifications,
    climateRiskScore: climateRiskScore(result),
    componentId,
    componentLabel,
    ecoScore: ecoScoreFromComposite(result.composite_score),
    graphPosition: { x: 0, y: 0 },
    gridCarbonScore: gridScoreFromNorm(result.rank_scores.grid_norm),
    id: `mfr_${result.is_current ? "current" : "alt"}_${slugify(componentLabel)}_${result.rank}_${slugify(result.name)}_${index}`,
    industry: result.industry
      ? { code: result.industry.code, title: result.industry.title }
      : null,
    isCurrent: Boolean(result.is_current),
    kind: "manufacturer",
    location: buildLocation(result.country, result.city),
    manufacturingEmissionsTco2e: {
      q10: result.emission_factor.q10_tco2e,
      q50: result.emission_factor.q50_tco2e,
      q90: result.emission_factor.q90_tco2e,
    },
    name: result.name,
    scoringInputs: toScoringInputs(result.scoring_inputs),
    transportEmissionsTco2e: result.scores.transport_tco2e,
  }
}

function createFallbackCurrentResult(
  component: ScenarioSearchCsvComponentRow,
  transportMode: string
): ManufacturerResult {
  return {
    cert_score: {
      cert_score: 0,
      disclosure_penalty: component.currentCertifications.length === 0,
      matched_certs: component.currentCertifications,
      multiplier: 1,
    },
    certifications: component.currentCertifications,
    city: component.currentCity,
    component: component.component,
    composite_score: 50,
    country: component.currentCountry,
    disclosure_status: component.currentDisclosureStatus,
    emission_factor: {
      q10_tco2e: 0,
      q50_tco2e: 0,
      q90_tco2e: 0,
    },
    env_rating: "amber",
    is_current: true,
    name: component.currentManufacturer,
    rank: 1,
    rank_scores: {
      cert_norm: 50,
      grid_norm: 50,
      manufacturing_norm: 50,
      risk_norm: 50,
      transport_norm: 50,
    },
    scores: {
      cert_score: 0,
      climate_risk_score: 50,
      grid_carbon_gco2_kwh: 0,
      manufacturing_tco2e: 0,
      total_tco2e: 0,
      transport_tco2e: 0,
    },
    sustainability_url: component.currentWebsite,
    transport: {
      distance_km: 0,
      mode: "sea",
      transport_tco2e: 0,
      weight_kg: 0,
    },
    transport_mode: transportMode,
  }
}

export interface ApiResultToScenarioOptions {
  /**
   * Only include these component indexes (positions in `csv.components`).
   * Used while a search streams in; every component keeps its final layout
   * slot so the graph doesn't reshuffle as the rest arrive.
   */
  componentIndexes?: ReadonlySet<number>
  /** Reuse an id across partial updates of the same run. */
  scenarioId?: string
}

export function apiResultToScenario(
  response: SearchResponse,
  csv: ScenarioSearchCsv,
  options: ApiResultToScenarioOptions = {}
): SupplyScenario {
  const productLabel = csv.product
  const productSlug = slugify(productLabel)
  const productId = `product_${productSlug}`
  const resultGroups = new Map<string, ManufacturerResult[]>()

  response.results.forEach((result) => {
    const componentName = result.component?.trim()
    if (!componentName) {
      return
    }

    const normalizedComponent = normalizeComponentKey(componentName)
    const nextGroup = resultGroups.get(normalizedComponent) ?? []
    nextGroup.push(result)
    resultGroups.set(normalizedComponent, nextGroup)
  })

  const components: SupplyScenarioComponentNode[] = []
  const manufacturers: SupplyScenarioManufacturerNode[] = []

  csv.components.forEach((componentRow, componentIndex) => {
    if (
      options.componentIndexes &&
      !options.componentIndexes.has(componentIndex)
    ) {
      return
    }
    const componentLabel = componentRow.component
    const componentId = `component_${productSlug}_${slugify(componentLabel)}`
    const scoredResults =
      resultGroups.get(normalizeComponentKey(componentLabel)) ?? []

    const currentResult =
      scoredResults.find((result) => result.is_current) ??
      createFallbackCurrentResult(componentRow, csv.transportMode)
    const alternateResults = scoredResults.filter(
      (result) => !result.is_current
    )
    const manufacturerNodes = [currentResult, ...alternateResults].map(
      (result, index) =>
        buildManufacturerNode(result, componentId, componentLabel, index)
    )

    const componentPosition = radialPosition(
      componentIndex,
      Math.max(csv.components.length, 1),
      Math.max(260, 140 + csv.components.length * 70)
    )
    const ringRadius = Math.max(320, 120 + manufacturerNodes.length * 52)
    manufacturerNodes.forEach((manufacturer, index) => {
      manufacturer.graphPosition = offsetPosition(
        componentPosition,
        radialPosition(index, manufacturerNodes.length, ringRadius)
      )
    })

    manufacturers.push(...manufacturerNodes)
    components.push({
      graphPosition: componentPosition,
      id: componentId,
      kind: "component",
      label: componentLabel,
      manufacturerIds: manufacturerNodes.map((manufacturer) => manufacturer.id),
    })
  })

  const product: SupplyScenarioProductNode = {
    childIds: components.map((component) => component.id),
    graphPosition: { x: -180, y: -180 },
    id: productId,
    kind: "product",
    label: productLabel,
    subtitle: `${csv.quantity.toLocaleString()} ${csv.unit}`,
  }

  const destination: SupplyScenarioDestination = {
    id: "destination_main",
    label: getCountryName(csv.destination),
    location: buildLocation(csv.destination, null),
  }

  const graphNodes: SupplyScenarioGraphNode[] = [
    product,
    ...components,
    ...manufacturers,
  ].map((node) => ({
    data: node,
    id: node.id,
    position: node.graphPosition,
  }))

  const graphEdges: SupplyScenarioGraphEdge[] = [
    ...components.map((component) => ({
      id: `edge_${productId}_${component.id}`,
      sourceId: productId,
      targetId: component.id,
    })),
    ...manufacturers.map((manufacturer) => ({
      id: `edge_${manufacturer.componentId}_${manufacturer.id}`,
      sourceId: manufacturer.componentId,
      targetId: manufacturer.id,
    })),
  ]

  const routes = manufacturers.map((manufacturer) => ({
    componentId: manufacturer.componentId,
    destinationId: destination.id,
    id: `route_${manufacturer.id}_${destination.id}`,
    isCurrent: manufacturer.isCurrent,
    manufacturerId: manufacturer.id,
  }))

  return {
    components,
    destination,
    graph: {
      edges: graphEdges,
      nodes: graphNodes,
    },
    id: options.scenarioId ?? `scenario_${productSlug}_${Date.now()}`,
    manufacturers,
    product,
    quantity: csv.quantity,
    routes,
    stats: {
      componentCount: components.length,
      currentRouteCount: routes.filter((route) => route.isCurrent).length,
      graphEdgeCount: graphEdges.length,
      graphNodeCount: graphNodes.length,
      routeCount: routes.length,
      siteCount: manufacturers.length + 1,
    },
    title: productLabel,
    unit: csv.unit,
    updatedAt: describeSearchRun(response, components.length),
  }
}
