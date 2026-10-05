import type { TransportMode } from "@/lib/api"
import {
  parseScenarioSearchCsv,
  type ScenarioSearchCsv,
} from "@/lib/csv-to-search"
import type { SupplyScenario } from "@/lib/supply-chain-scenario"

export const SCHEMA_VERSION = "scenario_csv_v2"
export const REQUIRED_SCENARIO_CSV_HEADERS = [
  "product",
  "quantity",
  "destination",
  "component",
  "current_manufacturer",
  "current_country",
] as const
export const OPTIONAL_SCENARIO_CSV_HEADERS = [
  "unit",
  "transport_mode",
  "target_count",
  "current_city",
  "current_website",
  "current_certifications",
  "current_disclosure_status",
  "current_revenue_usd_m",
  "current_renewable_pct",
] as const

export type ScenarioCsvPreview = {
  filename: string
  headers: string[]
  normalized: ScenarioSearchCsv & {
    componentCount: number
  }
}

function parseHeaders(text: string): string[] {
  const firstLine = text.replace(/^\uFEFF/, "").split(/\r?\n/, 1)[0] ?? ""
  if (!firstLine.trim()) {
    return []
  }

  const headers: string[] = []
  let current = ""
  let inQuotes = false

  for (let index = 0; index < firstLine.length; index += 1) {
    const character = firstLine[index]

    if (inQuotes) {
      if (character === '"') {
        if (firstLine[index + 1] === '"') {
          current += '"'
          index += 1
        } else {
          inQuotes = false
        }
      } else {
        current += character
      }
      continue
    }

    if (character === '"') {
      inQuotes = true
      continue
    }

    if (character === ",") {
      headers.push(current.trim().toLowerCase())
      current = ""
      continue
    }

    current += character
  }

  headers.push(current.trim().toLowerCase())
  return headers.filter(Boolean)
}

function csvCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? "" : String(value)
  // The parser reads one record per line, so flatten any line breaks.
  const singleLine = text.replace(/[\r\n]+/g, " ").trim()
  return /[",]/.test(singleLine)
    ? `"${singleLine.replace(/"/g, '""')}"`
    : singleLine
}

/**
 * Serialize a scenario to the v2 CSV format (one row per component, the
 * scenario fields repeated on each row). Round-trips through
 * `parseScenarioSearchCsv`, so a scenario built in the app is validated and
 * searched exactly like an uploaded file.
 */
export function scenarioToCsv(scenario: ScenarioSearchCsv): string {
  const headers = [
    ...REQUIRED_SCENARIO_CSV_HEADERS,
    ...OPTIONAL_SCENARIO_CSV_HEADERS,
  ]
  const rows = scenario.components.map((component) => {
    const values: Record<(typeof headers)[number], string | number | null> = {
      component: component.component,
      current_certifications: component.currentCertifications.join("|"),
      current_city: component.currentCity,
      current_country: component.currentCountry,
      current_disclosure_status: component.currentDisclosureStatus,
      current_manufacturer: component.currentManufacturer,
      current_renewable_pct: component.currentRenewablePct,
      current_revenue_usd_m: component.currentRevenueUsdM,
      current_website: component.currentWebsite,
      destination: scenario.destination,
      product: scenario.product,
      quantity: scenario.quantity,
      target_count: scenario.targetCount,
      transport_mode: scenario.transportMode,
      unit: scenario.unit,
    }
    return headers.map((header) => csvCell(values[header])).join(",")
  })
  return [headers.join(","), ...rows].join("\n") + "\n"
}

/**
 * Rebuild editable search input from a scenario on screen (used for the demo,
 * which has no original CSV): product, destination, quantity, and each
 * component's current supplier. Details the scenario doesn't keep (website,
 * revenue, renewable share, disclosure) start empty.
 */
export function supplyScenarioToSearchInput(
  scenario: SupplyScenario,
  transportMode: TransportMode
): ScenarioSearchCsv {
  return {
    components: scenario.components.map((component) => {
      const options = scenario.manufacturers.filter(
        (manufacturer) => manufacturer.componentId === component.id
      )
      const current =
        options.find((manufacturer) => manufacturer.isCurrent) ?? options[0]
      const location = current?.location
      return {
        component: component.label,
        currentCertifications: current?.certifications ?? [],
        // Locations without a known city fall back to the country name.
        currentCity:
          location && location.city !== location.country ? location.city : null,
        currentCountry: location?.countryCode ?? "",
        currentDisclosureStatus: "none",
        currentManufacturer: current?.name ?? "",
        currentRenewablePct: null,
        currentRevenueUsdM: null,
        currentWebsite: null,
      }
    }),
    destination: scenario.destination.location.countryCode,
    product: scenario.product.label || scenario.title,
    quantity: scenario.quantity,
    targetCount: null,
    transportMode,
    unit: scenario.unit,
  }
}

export function validateScenarioCsvFile(
  file: File,
  text: string
): ScenarioCsvPreview {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    throw new Error("Only .csv files are supported.")
  }

  const parsed = parseScenarioSearchCsv(text)
  if (!parsed.ok) {
    throw new Error(parsed.error)
  }

  return {
    filename: file.name,
    headers: parseHeaders(text),
    normalized: {
      ...parsed.scenario,
      componentCount: parsed.scenario.components.length,
    },
  }
}
