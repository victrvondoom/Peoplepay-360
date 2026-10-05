import type { SupplyScenario } from "@/lib/supply-chain-scenario"
import { getApiBaseUrl } from "@/lib/api-base-url"

export type TransportMode = "sea" | "air" | "rail" | "road"
export type EnvRating = "green" | "amber" | "red"
export type DisclosureStatus = "verified" | "partial" | "none"

export interface SearchWeights {
  manufacturing: number
  transport: number
  grid_carbon: number
  certifications: number
  climate_risk: number
}

export interface ScenarioComponentSearchRequest {
  component: string
  current_certifications?: string[]
  current_city?: string | null
  current_country: string
  current_disclosure_status?: "verified" | "partial" | "none"
  current_manufacturer: string
  current_renewable_pct?: number | null
  current_revenue_usd_m?: number | null
  current_website?: string | null
}

export interface SearchRequest {
  components?: ScenarioComponentSearchRequest[]
  product: string
  quantity: number
  destination: string
  countries: string[]
  transport_mode?: TransportMode
  require_certifications?: string[]
  target_count?: number
  use_cache?: boolean
  weights?: SearchWeights
}

/** Raw per-supplier signals the dashboard re-ranks with, without a new search. */
export interface ManufacturerScoringInputsResult {
  cert_adjustment: number
  climate_risk: number
  grid_gco2_kwh: number
  manufacturing_tco2e: number
  transport_tco2e_by_mode: Record<TransportMode, number>
}

export interface ManufacturerIndustryResult {
  code: string
  confidence: "high" | "medium" | "low"
  method: "curated" | "lexical" | "agent" | "fallback"
  title: string
}

export interface ManufacturerResult {
  component?: string
  rank: number
  name: string
  country: string
  city: string | null
  sustainability_url: string | null
  certifications: string[]
  composite_score: number
  env_rating: EnvRating
  disclosure_status: DisclosureStatus
  is_current?: boolean
  transport_mode: string
  scores: {
    manufacturing_tco2e: number
    transport_tco2e: number
    grid_carbon_gco2_kwh: number
    cert_score: number
    climate_risk_score?: number
    total_tco2e: number
  }
  rank_scores: {
    manufacturing_norm: number
    transport_norm: number
    grid_norm: number
    cert_norm: number
    risk_norm?: number
  }
  emission_factor: {
    q10_tco2e: number
    q50_tco2e: number
    q90_tco2e: number
    intensity_tco2e_per_usdm?: number
    grid_gco2_kwh?: number
    [key: string]: number | undefined
  }
  transport: {
    transport_tco2e: number
    distance_km: number
    mode: string
    glec_factor?: number
    weight_kg?: number
    origin_port?: string | null
    dest_port?: string | null
    [key: string]: unknown
  }
  cert_score: {
    multiplier: number
    cert_score: number
    matched_certs: string[]
    disclosure_penalty: boolean
  }
  industry?: ManufacturerIndustryResult
  scoring_inputs?: ManufacturerScoringInputsResult
}

export interface SearchResponse {
  product: string
  destination: string
  transport_mode: string
  countries: string[]
  duration_seconds: number
  count: number
  results: ManufacturerResult[]
  cache_hits?: number
  fallback_components?: string[]
}

export type SearchStreamEvent =
  | { type: "started"; total: number; components: string[] }
  | { type: "heartbeat"; elapsed_seconds: number }
  | {
      type: "component"
      index: number
      component: string
      completed: number
      total: number
      count: number
      cached: boolean
      fallback: boolean
      elapsed_seconds: number
      /** This component's scored manufacturers, for rendering before the rest finish. */
      results: ManufacturerResult[]
    }
  | { type: "complete"; response: SearchResponse }
  | { type: "error"; status: number; detail: string }

export interface ScenarioScoring {
  transportMode: TransportMode
  weights: SearchWeights
}

export interface ScenarioEditRequest {
  prompt: string
  scenario: SupplyScenario
}

export interface ScenarioEditResponse {
  message: string
  scenario: SupplyScenario | null
  status: "applied" | "rejected"
}

export interface ScenarioReportRequest {
  scenario: SupplyScenario
  scoring?: ScenarioScoring
  selectedManufacturerByComponent?: Record<string, string>
}

export interface ScenarioReportResponse {
  contentBase64: string
  fileName: string
  format: "pdf" | "tex"
  generatedAt: string
  mimeType: string
  model: string
}

export const API_BASE_URL = getApiBaseUrl()

async function readErrorDetail(response: Response) {
  const text = await response.text().catch(() => response.statusText)
  let detail = text || response.statusText
  try {
    const parsed = JSON.parse(text) as { detail?: string | { msg: string }[] }
    if (typeof parsed.detail === "string") {
      detail = parsed.detail
    }
  } catch {
    /* keep raw body */
  }
  return detail
}

export async function getHealth(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    cache: "no-store",
  })
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`)
  }
  return response.json()
}

export async function search(request: SearchRequest): Promise<SearchResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
    })
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? `Search request could not reach the backend: ${error.message}`
        : "Search request could not reach the backend."
    )
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response)
    throw new Error(`Search failed (${response.status}): ${detail}`)
  }

  return response.json()
}

function parseSearchStreamBlock(block: string): SearchStreamEvent | null {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n")

  if (!data) {
    return null
  }

  try {
    return JSON.parse(data) as SearchStreamEvent
  } catch {
    throw new Error("Search stream sent an unreadable event.")
  }
}

/**
 * Same search as `search()`, streamed from /search/stream so the caller can
 * show per-component progress. Resolves with the final response.
 */
export async function searchStream(
  request: SearchRequest,
  onEvent: (event: SearchStreamEvent) => void,
  signal?: AbortSignal
): Promise<SearchResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/search/stream`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      cache: "no-store",
      signal,
    })
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? `Search request could not reach the backend: ${error.message}`
        : "Search request could not reach the backend."
    )
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response)
    throw new Error(`Search failed (${response.status}): ${detail}`)
  }

  if (!response.body) {
    throw new Error("Search stream returned an empty body.")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      buffer = buffer.replace(/\r\n/g, "\n")

      const blocks = buffer.split("\n\n")
      buffer = done ? "" : (blocks.pop() ?? "")

      for (const block of blocks) {
        const event = parseSearchStreamBlock(block)
        if (!event) {
          continue
        }
        if (event.type === "error") {
          throw new Error(`Search failed (${event.status}): ${event.detail}`)
        }
        onEvent(event)
        if (event.type === "complete") {
          return event.response
        }
      }

      if (done) {
        break
      }
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined)
    throw error
  }

  throw new Error("Search stream ended before the result arrived.")
}

export async function editScenario(
  request: ScenarioEditRequest
): Promise<ScenarioEditResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/scenario/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
    })
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? `Scenario edit request could not reach the backend: ${error.message}`
        : "Scenario edit request could not reach the backend."
    )
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response)
    throw new Error(`Scenario edit failed (${response.status}): ${detail}`)
  }

  return response.json()
}

export async function generateScenarioReport(
  request: ScenarioReportRequest
): Promise<ScenarioReportResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/scenario/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
    })
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? `Scenario report request could not reach the backend: ${error.message}`
        : "Scenario report request could not reach the backend."
    )
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response)
    throw new Error(`Scenario report failed (${response.status}): ${detail}`)
  }

  return response.json()
}
