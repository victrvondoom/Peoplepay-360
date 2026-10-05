"use client"

import { useId, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { TransportMode } from "@/lib/api"
import { getCountryOptions } from "@/lib/country-coords"
import {
  parseScenarioSearchCsv,
  type ScenarioSearchCsv,
  type ScenarioSearchCsvComponentRow,
} from "@/lib/csv-to-search"
import { scenarioToCsv } from "@/lib/scenario-csv"
import { cn } from "@/lib/utils"

const TRANSPORT_MODES: { label: string; value: TransportMode }[] = [
  { label: "Sea", value: "sea" },
  { label: "Rail", value: "rail" },
  { label: "Road", value: "road" },
  { label: "Air", value: "air" },
]

const DISCLOSURE_STATUSES: {
  label: string
  value: ScenarioSearchCsvComponentRow["currentDisclosureStatus"]
}[] = [
  { label: "No disclosure", value: "none" },
  { label: "Partial disclosure", value: "partial" },
  { label: "Verified disclosure", value: "verified" },
]

interface ComponentDraft {
  certifications: string
  city: string
  country: string
  key: string
  manufacturer: string
  name: string
  renewablePct: string
  revenueUsdM: string
  disclosureStatus: ScenarioSearchCsvComponentRow["currentDisclosureStatus"]
  website: string
}

let draftKeySeed = 0
function nextDraftKey() {
  draftKeySeed += 1
  return `draft_${draftKeySeed}`
}

function createComponentDraft(
  row?: ScenarioSearchCsvComponentRow
): ComponentDraft {
  return {
    certifications: row?.currentCertifications.join(", ") ?? "",
    city: row?.currentCity ?? "",
    country: row?.currentCountry ?? "",
    key: nextDraftKey(),
    manufacturer: row?.currentManufacturer ?? "",
    name: row?.component ?? "",
    renewablePct: row?.currentRenewablePct?.toString() ?? "",
    revenueUsdM: row?.currentRevenueUsdM?.toString() ?? "",
    disclosureStatus: row?.currentDisclosureStatus ?? "none",
    website: row?.currentWebsite ?? "",
  }
}

interface ScenarioBuilderFormProps {
  /** Pre-fill the form, e.g. to edit the scenario already on the dashboard. */
  initialScenario?: ScenarioSearchCsv | null
  onSubmit: (csvText: string) => void
  submitLabel?: string
}

/**
 * In-app alternative to uploading a scenario CSV: the same product,
 * destination, transport, and per-component fields, entered as a form. Its
 * output is the same CSV text the file upload accepts, so both paths run
 * through one validator and one search request shape.
 */
export function ScenarioBuilderForm({
  initialScenario = null,
  onSubmit,
  submitLabel = "Run search",
}: ScenarioBuilderFormProps) {
  const formId = useId()
  const [product, setProduct] = useState(initialScenario?.product ?? "")
  const [quantity, setQuantity] = useState(
    initialScenario?.quantity.toString() ?? ""
  )
  const [unit, setUnit] = useState(initialScenario?.unit ?? "units")
  const [destination, setDestination] = useState(
    initialScenario?.destination ?? ""
  )
  const [transportMode, setTransportMode] = useState<TransportMode>(
    initialScenario?.transportMode ?? "sea"
  )
  const [targetCount, setTargetCount] = useState(
    initialScenario?.targetCount?.toString() ?? ""
  )
  const [components, setComponents] = useState<ComponentDraft[]>(() =>
    initialScenario && initialScenario.components.length > 0
      ? initialScenario.components.map((row) => createComponentDraft(row))
      : [createComponentDraft()]
  )
  const [error, setError] = useState<string | null>(null)

  const countryOptions = getCountryOptions()

  function updateComponent(key: string, patch: Partial<ComponentDraft>) {
    setComponents((previous) =>
      previous.map((component) =>
        component.key === key ? { ...component, ...patch } : component
      )
    )
  }

  function addComponent() {
    setComponents((previous) => [...previous, createComponentDraft()])
  }

  function removeComponent(key: string) {
    setComponents((previous) =>
      previous.length > 1
        ? previous.filter((component) => component.key !== key)
        : previous
    )
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)

    const csvText = scenarioToCsv({
      components: components.map((component) => ({
        component: component.name.trim(),
        currentCertifications: component.certifications
          .split(/[|,]/)
          .map((value) => value.trim())
          .filter(Boolean),
        currentCity: component.city.trim() || null,
        currentCountry: component.country,
        currentDisclosureStatus: component.disclosureStatus,
        currentManufacturer: component.manufacturer.trim(),
        currentRenewablePct: component.renewablePct
          ? Number(component.renewablePct)
          : null,
        currentRevenueUsdM: component.revenueUsdM
          ? Number(component.revenueUsdM)
          : null,
        currentWebsite: component.website.trim() || null,
      })),
      destination,
      product: product.trim(),
      quantity: Number(quantity),
      targetCount: targetCount ? Number(targetCount) : null,
      transportMode,
      unit: unit.trim() || "units",
    })

    // Reuse the CSV parser so the form and file-upload paths validate
    // identically and never drift apart.
    const parsed = parseScenarioSearchCsv(csvText)
    if (!parsed.ok) {
      setError(parsed.error)
      return
    }

    onSubmit(csvText)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${formId}-product`}>Product</Label>
          <Input
            id={`${formId}-product`}
            value={product}
            onChange={(event) => setProduct(event.target.value)}
            placeholder="e.g. LED desk lamp"
            required
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${formId}-quantity`}>Quantity</Label>
          <div className="flex gap-2">
            <Input
              id={`${formId}-quantity`}
              type="number"
              min={1}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              placeholder="8000"
              required
              className="flex-1"
            />
            <Input
              value={unit}
              onChange={(event) => setUnit(event.target.value)}
              placeholder="units"
              className="w-24"
              aria-label="Unit"
            />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${formId}-destination`}>Destination</Label>
          <Select value={destination} onValueChange={setDestination}>
            <SelectTrigger id={`${formId}-destination`} className="w-full">
              <SelectValue placeholder="Select a country" />
            </SelectTrigger>
            <SelectContent>
              {countryOptions.map((country) => (
                <SelectItem key={country.code} value={country.code}>
                  {country.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${formId}-transport`}>Transport mode</Label>
          <Select
            value={transportMode}
            onValueChange={(value) => setTransportMode(value as TransportMode)}
          >
            <SelectTrigger id={`${formId}-transport`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TRANSPORT_MODES.map((mode) => (
                <SelectItem key={mode.value} value={mode.value}>
                  {mode.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={`${formId}-target-count`}>
            Alternates per component{" "}
            <span className="text-muted-foreground">(optional)</span>
          </Label>
          <Input
            id={`${formId}-target-count`}
            type="number"
            min={1}
            max={30}
            value={targetCount}
            onChange={(event) => setTargetCount(event.target.value)}
            placeholder="Default backend behavior"
          />
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-foreground">Components</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addComponent}
          >
            Add component
          </Button>
        </div>

        {components.map((component, index) => (
          <div
            key={component.key}
            className={cn(
              "flex flex-col gap-4 rounded-2xl border border-border/70 bg-background/35 p-4"
            )}
          >
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Component {index + 1}
              </p>
              {components.length > 1 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => removeComponent(component.key)}
                >
                  Remove
                </Button>
              ) : null}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-name`}>
                  Component or material
                </Label>
                <Input
                  id={`${formId}-c${index}-name`}
                  value={component.name}
                  onChange={(event) =>
                    updateComponent(component.key, { name: event.target.value })
                  }
                  placeholder="e.g. aluminum housing"
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-manufacturer`}>
                  Current supplier
                </Label>
                <Input
                  id={`${formId}-c${index}-manufacturer`}
                  value={component.manufacturer}
                  onChange={(event) =>
                    updateComponent(component.key, {
                      manufacturer: event.target.value,
                    })
                  }
                  placeholder="Current manufacturer name"
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-country`}>
                  Supplier country
                </Label>
                <Select
                  value={component.country}
                  onValueChange={(value) =>
                    updateComponent(component.key, { country: value })
                  }
                >
                  <SelectTrigger
                    id={`${formId}-c${index}-country`}
                    className="w-full"
                  >
                    <SelectValue placeholder="Select a country" />
                  </SelectTrigger>
                  <SelectContent>
                    {countryOptions.map((country) => (
                      <SelectItem key={country.code} value={country.code}>
                        {country.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-city`}>
                  Supplier city{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id={`${formId}-c${index}-city`}
                  value={component.city}
                  onChange={(event) =>
                    updateComponent(component.key, { city: event.target.value })
                  }
                  placeholder="e.g. Shenzhen"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-website`}>
                  Sustainability page{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id={`${formId}-c${index}-website`}
                  type="url"
                  value={component.website}
                  onChange={(event) =>
                    updateComponent(component.key, {
                      website: event.target.value,
                    })
                  }
                  placeholder="https://…"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-disclosure`}>
                  Disclosure status
                </Label>
                <Select
                  value={component.disclosureStatus}
                  onValueChange={(value) =>
                    updateComponent(component.key, {
                      disclosureStatus:
                        value as ComponentDraft["disclosureStatus"],
                    })
                  }
                >
                  <SelectTrigger
                    id={`${formId}-c${index}-disclosure`}
                    className="w-full"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DISCLOSURE_STATUSES.map((status) => (
                      <SelectItem key={status.value} value={status.value}>
                        {status.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-revenue`}>
                  Annual revenue, $M{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id={`${formId}-c${index}-revenue`}
                  type="number"
                  min={0}
                  step="0.1"
                  value={component.revenueUsdM}
                  onChange={(event) =>
                    updateComponent(component.key, {
                      revenueUsdM: event.target.value,
                    })
                  }
                  placeholder="25"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${formId}-c${index}-renewable`}>
                  Renewable energy %{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id={`${formId}-c${index}-renewable`}
                  type="number"
                  min={0}
                  max={100}
                  value={component.renewablePct}
                  onChange={(event) =>
                    updateComponent(component.key, {
                      renewablePct: event.target.value,
                    })
                  }
                  placeholder="0–100"
                />
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor={`${formId}-c${index}-certifications`}>
                Certifications{" "}
                <span className="text-muted-foreground">
                  (optional, one per line or comma-separated)
                </span>
              </Label>
              <Textarea
                id={`${formId}-c${index}-certifications`}
                value={component.certifications}
                onChange={(event) =>
                  updateComponent(component.key, {
                    certifications: event.target.value,
                  })
                }
                placeholder="iso14001, sbt_committed"
                rows={2}
              />
            </div>
          </div>
        ))}
      </div>

      {error ? (
        <div className="rounded-2xl border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="flex justify-end">
        <Button type="submit">{submitLabel}</Button>
      </div>
    </form>
  )
}
