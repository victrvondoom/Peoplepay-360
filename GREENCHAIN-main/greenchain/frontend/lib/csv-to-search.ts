import type { TransportMode } from "@/lib/api"

export interface ScenarioSearchCsvComponentRow {
  component: string
  currentCertifications: string[]
  currentCity: string | null
  currentCountry: string
  currentDisclosureStatus: "verified" | "partial" | "none"
  currentManufacturer: string
  currentRenewablePct: number | null
  currentRevenueUsdM: number | null
  currentWebsite: string | null
}

export interface ScenarioSearchCsv {
  components: ScenarioSearchCsvComponentRow[]
  destination: string
  product: string
  quantity: number
  targetCount: number | null
  transportMode: TransportMode
  unit: string
}

const REQUIRED_COLUMNS = [
  "product",
  "quantity",
  "destination",
  "component",
  "current_manufacturer",
  "current_country",
] as const

type RequiredColumn = (typeof REQUIRED_COLUMNS)[number]
type OptionalColumn =
  | "unit"
  | "transport_mode"
  | "target_count"
  | "current_city"
  | "current_website"
  | "current_certifications"
  | "current_disclosure_status"
  | "current_revenue_usd_m"
  | "current_renewable_pct"
type CsvColumn = RequiredColumn | OptionalColumn

type ParseResult =
  | { ok: true; scenario: ScenarioSearchCsv }
  | { ok: false; error: string }

const VALID_TRANSPORT_MODES: readonly TransportMode[] = [
  "sea",
  "air",
  "rail",
  "road",
] as const

const VALID_DISCLOSURE_STATUSES = ["verified", "partial", "none"] as const

function splitCsvLine(line: string): string[] {
  const fields: string[] = []
  let current = ""
  let inQuotes = false

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index]

    if (inQuotes) {
      if (character === '"') {
        if (line[index + 1] === '"') {
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
      fields.push(current)
      current = ""
      continue
    }

    current += character
  }

  fields.push(current)
  return fields.map((field) => field.trim())
}

function parsePipeList(value: string): string[] {
  return value
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean)
}

function readCell(
  headers: string[],
  values: string[],
  column: CsvColumn
): string {
  const index = headers.indexOf(column)
  return index >= 0 ? values[index]?.trim() ?? "" : ""
}

function parsePositiveNumber(raw: string, column: string): number | null {
  if (!raw) {
    return null
  }

  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${column} must be a positive number (got "${raw}").`)
  }

  return value
}

function parsePercent(raw: string, column: string): number | null {
  if (!raw) {
    return null
  }

  const value = Number(raw)
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(`${column} must be between 0 and 100 (got "${raw}").`)
  }

  return value
}

function parseIso2(raw: string, column: string): string {
  const value = raw.toUpperCase()
  if (value.length !== 2) {
    throw new Error(`${column} must be an ISO-2 country code (got "${raw}").`)
  }
  return value
}

function parseTransportMode(raw: string): TransportMode {
  const value = (raw || "sea").toLowerCase() as TransportMode
  if (!VALID_TRANSPORT_MODES.includes(value)) {
    throw new Error(
      `transport_mode must be one of ${VALID_TRANSPORT_MODES.join(", ")}.`
    )
  }
  return value
}

function parseDisclosureStatus(
  raw: string
): ScenarioSearchCsvComponentRow["currentDisclosureStatus"] {
  const value =
    (raw || "none").toLowerCase() as ScenarioSearchCsvComponentRow["currentDisclosureStatus"]

  if (!VALID_DISCLOSURE_STATUSES.includes(value)) {
    throw new Error(
      `current_disclosure_status must be one of ${VALID_DISCLOSURE_STATUSES.join(", ")}.`
    )
  }

  return value
}

function ensureScenarioFieldConsistency(
  label: string,
  currentValue: string,
  nextValue: string,
  rowNumber: number
) {
  if (currentValue !== nextValue) {
    throw new Error(
      `${label} must be identical on every row (mismatch on row ${rowNumber}).`
    )
  }
}

export function parseScenarioSearchCsv(text: string): ParseResult {
  const normalized = text.replace(/\r\n?/g, "\n").trim()

  if (!normalized) {
    return { ok: false, error: "CSV is empty." }
  }

  const lines = normalized.split("\n").filter((line) => line.trim().length > 0)
  if (lines.length < 2) {
    return { ok: false, error: "CSV must have a header row and at least one data row." }
  }

  try {
    const headers = splitCsvLine(lines[0]).map((header) => header.toLowerCase())
    const seenHeaders = new Set<string>()
    for (const header of headers) {
      if (!header) {
        throw new Error("Header names cannot be empty.")
      }
      if (seenHeaders.has(header)) {
        throw new Error(`Duplicate header: ${header}.`)
      }
      seenHeaders.add(header)
    }

    for (const column of REQUIRED_COLUMNS) {
      if (!headers.includes(column)) {
        throw new Error(`Missing required column: ${column}.`)
      }
    }

    let product = ""
    let quantity = 0
    let destination = ""
    let unit = "units"
    let transportMode: TransportMode = "sea"
    let targetCount: number | null = null
    const components: ScenarioSearchCsvComponentRow[] = []
    const componentNames = new Set<string>()

    lines.slice(1).forEach((line, index) => {
      const rowNumber = index + 2
      const values = splitCsvLine(line)

      if (values.length > headers.length) {
        throw new Error(`Row ${rowNumber} has more columns than the header.`)
      }

      const rowProduct = readCell(headers, values, "product")
      const rowQuantityRaw = readCell(headers, values, "quantity")
      const rowDestination = readCell(headers, values, "destination")
      const rowComponent = readCell(headers, values, "component")
      const rowCurrentManufacturer = readCell(
        headers,
        values,
        "current_manufacturer"
      )
      const rowCurrentCountry = readCell(headers, values, "current_country")
      const rowUnit = readCell(headers, values, "unit") || "units"
      const rowTransportMode = parseTransportMode(
        readCell(headers, values, "transport_mode")
      )
      const rowTargetCountRaw = readCell(headers, values, "target_count")

      if (!rowProduct) {
        throw new Error(`product is required on row ${rowNumber}.`)
      }
      if (!rowQuantityRaw) {
        throw new Error(`quantity is required on row ${rowNumber}.`)
      }
      if (!rowDestination) {
        throw new Error(`destination is required on row ${rowNumber}.`)
      }
      if (!rowComponent) {
        throw new Error(`component is required on row ${rowNumber}.`)
      }
      if (!rowCurrentManufacturer) {
        throw new Error(`current_manufacturer is required on row ${rowNumber}.`)
      }
      if (!rowCurrentCountry) {
        throw new Error(`current_country is required on row ${rowNumber}.`)
      }

      const rowQuantity = parsePositiveNumber(rowQuantityRaw, "quantity")
      if (rowQuantity === null) {
        throw new Error(`quantity is required on row ${rowNumber}.`)
      }

      const rowTargetCount = parsePositiveNumber(rowTargetCountRaw, "target_count")
      const normalizedDestination = parseIso2(rowDestination, "destination")
      const normalizedCurrentCountry = parseIso2(
        rowCurrentCountry,
        "current_country"
      )
      const normalizedComponent = rowComponent.trim()

      if (components.length === 0) {
        product = rowProduct
        quantity = Math.floor(rowQuantity)
        destination = normalizedDestination
        unit = rowUnit
        transportMode = rowTransportMode
        targetCount = rowTargetCount ? Math.floor(rowTargetCount) : null
      } else {
        ensureScenarioFieldConsistency("product", product, rowProduct, rowNumber)
        ensureScenarioFieldConsistency(
          "quantity",
          quantity.toString(),
          Math.floor(rowQuantity).toString(),
          rowNumber
        )
        ensureScenarioFieldConsistency(
          "destination",
          destination,
          normalizedDestination,
          rowNumber
        )
        ensureScenarioFieldConsistency("unit", unit, rowUnit, rowNumber)
        ensureScenarioFieldConsistency(
          "transport_mode",
          transportMode,
          rowTransportMode,
          rowNumber
        )
        ensureScenarioFieldConsistency(
          "target_count",
          (targetCount ?? "").toString(),
          rowTargetCount ? Math.floor(rowTargetCount).toString() : "",
          rowNumber
        )
      }

      const componentKey = normalizedComponent.toLowerCase()
      if (componentNames.has(componentKey)) {
        throw new Error(
          `Each component can appear only once (duplicate "${normalizedComponent}").`
        )
      }
      componentNames.add(componentKey)

      const currentWebsite = readCell(headers, values, "current_website")
      if (
        currentWebsite &&
        !currentWebsite.startsWith("http://") &&
        !currentWebsite.startsWith("https://")
      ) {
        throw new Error(
          `current_website must start with http:// or https:// on row ${rowNumber}.`
        )
      }

      const currentRevenueUsdM = parsePositiveNumber(
        readCell(headers, values, "current_revenue_usd_m"),
        "current_revenue_usd_m"
      )
      const currentRenewablePct = parsePercent(
        readCell(headers, values, "current_renewable_pct"),
        "current_renewable_pct"
      )

      components.push({
        component: normalizedComponent,
        currentCertifications: parsePipeList(
          readCell(headers, values, "current_certifications")
        ),
        currentCity: readCell(headers, values, "current_city") || null,
        currentCountry: normalizedCurrentCountry,
        currentDisclosureStatus: parseDisclosureStatus(
          readCell(headers, values, "current_disclosure_status")
        ),
        currentManufacturer: rowCurrentManufacturer,
        currentRenewablePct,
        currentRevenueUsdM,
        currentWebsite: currentWebsite || null,
      })
    })

    return {
      ok: true,
      scenario: {
        components,
        destination,
        product,
        quantity,
        targetCount,
        transportMode,
        unit,
      },
    }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "Could not parse the CSV.",
    }
  }
}
