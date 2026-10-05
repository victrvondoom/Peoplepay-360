import type { SearchWeights, TransportMode } from "@/lib/api"
import type {
  SupplyScenario,
  SupplyScenarioManufacturerNode,
} from "@/lib/supply-chain-scenario"

/**
 * Client-side re-ranking: the "lens" a scenario is viewed through (transport
 * mode + dimension weights). Mirrors backend `ScoreAssembler.score_candidates`
 * so switching modes or moving a weight slider re-scores instantly, with no
 * new search.
 */
export interface ScoringLens {
  transportMode: TransportMode
  weights: SearchWeights
}

export const TRANSPORT_MODES: readonly TransportMode[] = [
  "sea",
  "rail",
  "road",
  "air",
] as const

export const TRANSPORT_MODE_LABELS: Record<TransportMode, string> = {
  air: "Air",
  rail: "Rail",
  road: "Road",
  sea: "Sea",
}

export const WEIGHT_KEYS: readonly (keyof SearchWeights)[] = [
  "manufacturing",
  "transport",
  "grid_carbon",
  "certifications",
  "climate_risk",
] as const

export const WEIGHT_LABELS: Record<keyof SearchWeights, string> = {
  certifications: "Certifications",
  climate_risk: "Climate risk",
  grid_carbon: "Grid carbon",
  manufacturing: "Manufacturing",
  transport: "Transport",
}

export const DEFAULT_SCORING_WEIGHTS: SearchWeights = {
  certifications: 0.1,
  climate_risk: 0.05,
  grid_carbon: 0.2,
  manufacturing: 0.4,
  transport: 0.25,
}

export function createScoringLens(
  transportMode: TransportMode = "sea"
): ScoringLens {
  return { transportMode, weights: { ...DEFAULT_SCORING_WEIGHTS } }
}

/** Weights scaled to sum to 1; falls back to the defaults if all are zero. */
export function normalizeWeights(weights: SearchWeights): SearchWeights {
  const total = WEIGHT_KEYS.reduce(
    (sum, key) => sum + Math.max(0, weights[key]),
    0
  )
  if (!(total > 0)) {
    return { ...DEFAULT_SCORING_WEIGHTS }
  }
  return {
    certifications: Math.max(0, weights.certifications) / total,
    climate_risk: Math.max(0, weights.climate_risk) / total,
    grid_carbon: Math.max(0, weights.grid_carbon) / total,
    manufacturing: Math.max(0, weights.manufacturing) / total,
    transport: Math.max(0, weights.transport) / total,
  }
}

export function weightsEqual(left: SearchWeights, right: SearchWeights) {
  const a = normalizeWeights(left)
  const b = normalizeWeights(right)
  return WEIGHT_KEYS.every((key) => Math.abs(a[key] - b[key]) < 1e-6)
}

/** Min-max scale to 0-100 (lower input -> lower output); all-equal -> 50. */
function normaliseTo100(values: number[]): number[] {
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (max === min) {
    return values.map(() => 50)
  }
  return values.map((value) => ((value - min) / (max - min)) * 100)
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)))
}

type ScoredFields = Pick<
  SupplyScenarioManufacturerNode,
  | "climateRiskScore"
  | "ecoScore"
  | "gridCarbonScore"
  | "transportEmissionsTco2e"
>

/**
 * Re-score every manufacturer that carries `scoringInputs`, within its
 * component (scores are relative to the options for that component).
 * Manufacturers without inputs keep their stored values. Pure: returns a new
 * scenario and never mutates the input.
 */
export function applyScoringLens(
  scenario: SupplyScenario,
  lens: ScoringLens
): SupplyScenario {
  const weights = normalizeWeights(lens.weights)
  const patches = new Map<string, ScoredFields>()

  for (const component of scenario.components) {
    const group = scenario.manufacturers.filter(
      (manufacturer) =>
        manufacturer.componentId === component.id &&
        Boolean(manufacturer.scoringInputs)
    )
    if (group.length === 0) {
      continue
    }

    const inputs = group.map((manufacturer) => manufacturer.scoringInputs!)
    const transport = inputs.map(
      (input) => input.transportTco2eByMode[lens.transportMode]
    )
    const manufacturingNorm = normaliseTo100(
      inputs.map((input) => input.manufacturingTco2e)
    )
    const transportNorm = normaliseTo100(transport)
    const gridNorm = normaliseTo100(inputs.map((input) => input.gridGco2Kwh))
    const certNorm = normaliseTo100(inputs.map((input) => input.certAdjustment))
    const riskNorm = normaliseTo100(inputs.map((input) => input.climateRisk))

    group.forEach((manufacturer, index) => {
      const impact =
        weights.manufacturing * manufacturingNorm[index] +
        weights.transport * transportNorm[index] +
        weights.grid_carbon * gridNorm[index] +
        weights.certifications * certNorm[index] +
        weights.climate_risk * riskNorm[index]

      patches.set(manufacturer.id, {
        climateRiskScore: Math.round(inputs[index].climateRisk * 10) / 10,
        ecoScore: clampScore(impact),
        gridCarbonScore: clampScore(100 - gridNorm[index]),
        transportEmissionsTco2e: transport[index],
      })
    })
  }

  if (patches.size === 0) {
    return scenario
  }

  return {
    ...scenario,
    graph: {
      ...scenario.graph,
      nodes: scenario.graph.nodes.map((node) => {
        const patch =
          node.data.kind === "manufacturer" ? patches.get(node.id) : undefined
        return patch ? { ...node, data: { ...node.data, ...patch } } : node
      }),
    },
    manufacturers: scenario.manufacturers.map((manufacturer) => {
      const patch = patches.get(manufacturer.id)
      return patch ? { ...manufacturer, ...patch } : manufacturer
    }),
  }
}

/** True when at least one manufacturer can be re-ranked client-side. */
export function scenarioSupportsLens(scenario: SupplyScenario | null) {
  return Boolean(
    scenario?.manufacturers.some((manufacturer) =>
      Boolean(manufacturer.scoringInputs)
    )
  )
}
