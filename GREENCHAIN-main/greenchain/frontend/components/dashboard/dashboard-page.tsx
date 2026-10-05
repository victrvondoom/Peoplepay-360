"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import {
  DashboardShell,
  type SearchProgressComponent,
} from "@/components/dashboard/dashboard-shell"
import type { UploadPanelStatus } from "@/components/dashboard/upload-panel"
import { ScenarioBuilderForm } from "@/components/launch/scenario-builder-form"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  editScenario,
  generateScenarioReport,
  searchStream,
  type SearchStreamEvent,
} from "@/lib/api"
import { apiResultToScenario } from "@/lib/api-to-scenario"
import {
  parseScenarioSearchCsv,
  type ScenarioSearchCsv,
} from "@/lib/csv-to-search"
import { supplyScenarioToSearchInput } from "@/lib/scenario-csv"
import {
  clearDashboardEntry,
  persistDemoDashboardEntry,
} from "@/lib/dashboard-entry"
import {
  clearPendingScenarioCsv,
  consumePendingScenarioCsv,
} from "@/lib/scenario-handoff"
import {
  applyScoringLens,
  createScoringLens,
  normalizeWeights,
  scenarioSupportsLens,
  type ScoringLens,
} from "@/lib/scoring-lens"
import {
  sampleSupplyScenario,
  type SupplyScenario,
} from "@/lib/supply-chain-scenario"

interface DashboardPageProps {
  isHandoff: boolean
  startsInDemo: boolean
}

interface ReportProgressState {
  label: string
  value: number
}

interface ScenarioEditHistoryState {
  future: SupplyScenario[]
  past: SupplyScenario[]
}

const MAX_SCENARIO_EDIT_HISTORY = 50

function createDefaultPrompt() {
  return `Request goes here`
}

function getReportProgressState(elapsedMs: number): ReportProgressState {
  if (elapsedMs < 1200) {
    return { label: "Collecting route signals", value: 0.18 }
  }

  if (elapsedMs < 3200) {
    return { label: "Writing the narrative", value: 0.46 }
  }

  if (elapsedMs < 6200) {
    return { label: "Typesetting the PDF", value: 0.74 }
  }

  return { label: "Finalizing download", value: 0.92 }
}

function downloadBase64File(
  fileName: string,
  contentBase64: string,
  mimeType: string
) {
  const decoded = atob(contentBase64)
  const bytes = Uint8Array.from(decoded, (character) => character.charCodeAt(0))
  const blob = new Blob([bytes], { type: mimeType })
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = objectUrl
  anchor.download = fileName
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

function trimScenarioHistory(stack: SupplyScenario[]) {
  return stack.length > MAX_SCENARIO_EDIT_HISTORY
    ? stack.slice(stack.length - MAX_SCENARIO_EDIT_HISTORY)
    : stack
}

function isEditableTarget(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT")
  )
}

function isKimiPromptTarget(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    Boolean(target.closest("[data-kimi-prompt-input='true']"))
  )
}

function createSearchProgress(labels: string[]): SearchProgressComponent[] {
  return labels.map(
    (label): SearchProgressComponent => ({
      cached: false,
      count: 0,
      fallback: false,
      label,
      status: "pending",
    })
  )
}

function applySearchEvent(
  components: SearchProgressComponent[],
  event: SearchStreamEvent
): SearchProgressComponent[] {
  if (event.type !== "component") {
    return components
  }
  return components.map(
    (item, index): SearchProgressComponent =>
      index === event.index
        ? {
            ...item,
            cached: event.cached,
            count: event.count,
            fallback: event.fallback,
            status: "done",
          }
        : item
  )
}

export function DashboardPage({ isHandoff, startsInDemo }: DashboardPageProps) {
  const [scenario, setScenario] = useState<SupplyScenario | null>(() =>
    startsInDemo ? sampleSupplyScenario : null
  )
  const [scenarioSource, setScenarioSource] = useState<
    "demo" | "search" | null
  >(() => (startsInDemo ? "demo" : null))
  const [status, setStatus] = useState<UploadPanelStatus>(() =>
    isHandoff ? "loading" : "idle"
  )
  const [error, setError] = useState<string | null>(null)
  const [promptValue, setPromptValue] = useState("")
  const [promptPlaceholder, setPromptPlaceholder] = useState(() =>
    startsInDemo ? createDefaultPrompt() : ""
  )
  const [promptPending, setPromptPending] = useState(false)
  const [promptError, setPromptError] = useState<string | null>(null)
  const [reportPending, setReportPending] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)
  const [reportElapsedMs, setReportElapsedMs] = useState(0)
  const [scenarioEditHistory, setScenarioEditHistory] =
    useState<ScenarioEditHistoryState>({
      future: [],
      past: [],
    })
  const [scoringLens, setScoringLens] = useState<ScoringLens>(() =>
    createScoringLens()
  )
  const [searchProgress, setSearchProgress] = useState<
    SearchProgressComponent[] | null
  >(null)
  const [searchElapsedSeconds, setSearchElapsedSeconds] = useState(0)
  // The inputs behind the current live scenario, used to pre-fill "Edit scenario".
  const [scenarioInput, setScenarioInput] = useState<ScenarioSearchCsv | null>(
    null
  )
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorKey, setEditorKey] = useState(0)
  const [editorInitial, setEditorInitial] = useState<ScenarioSearchCsv | null>(
    null
  )
  const handoffConsumedRef = useRef(false)
  const searchAbortRef = useRef<AbortController | null>(null)

  // The scenario as displayed: re-ranked for the chosen transport mode and
  // weights. `scenario` stays the stored source of truth.
  const viewScenario = useMemo(
    () => (scenario ? applyScoringLens(scenario, scoringLens) : null),
    [scenario, scoringLens]
  )
  const scoringDisabled = !scenarioSupportsLens(scenario)

  const abortActiveSearch = useCallback(() => {
    searchAbortRef.current?.abort()
    searchAbortRef.current = null
  }, [])

  useEffect(() => {
    const abortRef = searchAbortRef
    return () => abortRef.current?.abort()
  }, [])

  useEffect(() => {
    if (status !== "loading") {
      return
    }

    const startedAt = Date.now()
    const intervalId = window.setInterval(() => {
      setSearchElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000))
    }, 1000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [status])

  useEffect(() => {
    if (!reportPending) {
      return
    }

    const startedAt = Date.now()
    const intervalId = window.setInterval(() => {
      setReportElapsedMs(Date.now() - startedAt)
    }, 220)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [reportPending])

  const resetScenarioEditHistory = useCallback(() => {
    setScenarioEditHistory({
      future: [],
      past: [],
    })
  }, [])

  const handleUndoPromptEdit = useCallback(() => {
    if (promptPending || !scenario || scenarioEditHistory.past.length === 0) {
      return false
    }

    const previousScenario =
      scenarioEditHistory.past[scenarioEditHistory.past.length - 1]

    setScenarioEditHistory((previousState) => ({
      future: trimScenarioHistory([scenario, ...previousState.future]),
      past: previousState.past.slice(0, -1),
    }))
    setScenario(previousScenario)
    setPromptError(null)
    setReportPending(false)
    setReportElapsedMs(0)
    setReportError(null)
    return true
  }, [promptPending, scenario, scenarioEditHistory.past])

  const handleRedoPromptEdit = useCallback(() => {
    if (promptPending || !scenario || scenarioEditHistory.future.length === 0) {
      return false
    }

    const [nextScenario, ...remainingFuture] = scenarioEditHistory.future

    setScenarioEditHistory((previousState) => ({
      future: remainingFuture,
      past: trimScenarioHistory([...previousState.past, scenario]),
    }))
    setScenario(nextScenario)
    setPromptError(null)
    setReportPending(false)
    setReportElapsedMs(0)
    setReportError(null)
    return true
  }, [promptPending, scenario, scenarioEditHistory.future])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) {
        return
      }

      if (event.key.toLowerCase() !== "z") {
        return
      }

      if (isEditableTarget(event.target) && !isKimiPromptTarget(event.target)) {
        return
      }

      const handled = event.shiftKey
        ? handleRedoPromptEdit()
        : handleUndoPromptEdit()

      if (handled) {
        event.preventDefault()
        event.stopPropagation()
      }
    }

    window.addEventListener("keydown", handleKeyDown, { capture: true })
    return () =>
      window.removeEventListener("keydown", handleKeyDown, { capture: true })
  }, [handleRedoPromptEdit, handleUndoPromptEdit])

  const runScenarioCsvText = useCallback(
    async (text: string) => {
      abortActiveSearch()
      clearDashboardEntry()
      setStatus("loading")
      setError(null)
      setPromptError(null)
      setReportPending(false)
      setReportElapsedMs(0)
      setReportError(null)
      setScenario(null)
      setScenarioSource(null)
      setSearchProgress(null)
      setSearchElapsedSeconds(0)
      resetScenarioEditHistory()

      const parsed = parseScenarioSearchCsv(text)
      if (!parsed.ok) {
        setStatus("error")
        setError(parsed.error)
        return
      }

      const scenarioCsv = parsed.scenario
      setScenarioInput(scenarioCsv)
      // Set the lens up front so streamed partial results already use the
      // scenario's transport mode.
      setScoringLens(createScoringLens(scenarioCsv.transportMode))
      const controller = new AbortController()
      searchAbortRef.current = controller
      const streamScenarioId = `scenario_${Date.now()}`
      const arrivedComponentIndexes = new Set<number>()

      try {
        const response = await searchStream(
          {
            components: scenarioCsv.components.map((component) => ({
              component: component.component,
              current_certifications: component.currentCertifications,
              current_city: component.currentCity,
              current_country: component.currentCountry,
              current_disclosure_status: component.currentDisclosureStatus,
              current_manufacturer: component.currentManufacturer,
              current_renewable_pct: component.currentRenewablePct,
              current_revenue_usd_m: component.currentRevenueUsdM,
              current_website: component.currentWebsite,
            })),
            product: scenarioCsv.product,
            quantity: scenarioCsv.quantity,
            destination: scenarioCsv.destination,
            countries: [],
            target_count: scenarioCsv.targetCount ?? undefined,
            transport_mode: scenarioCsv.transportMode,
          },
          (event) => {
            if (event.type === "started") {
              setSearchProgress(createSearchProgress(event.components))
            } else if (event.type === "component") {
              setSearchProgress((previous) =>
                previous ? applySearchEvent(previous, event) : previous
              )
              // Render this component's results immediately rather than
              // waiting for every component to finish: the graph and globe
              // fill in as the search progresses.
              arrivedComponentIndexes.add(event.index)
              const partialScenario = apiResultToScenario(
                {
                  product: scenarioCsv.product,
                  destination: scenarioCsv.destination,
                  transport_mode: scenarioCsv.transportMode,
                  countries: [],
                  duration_seconds: event.elapsed_seconds,
                  count: event.results.length,
                  results: event.results,
                },
                scenarioCsv,
                {
                  componentIndexes: new Set(arrivedComponentIndexes),
                  scenarioId: streamScenarioId,
                }
              )
              setScenario(partialScenario)
              setScenarioSource("search")
            }
          },
          controller.signal
        )

        if (controller.signal.aborted) {
          return
        }

        const nextScenario = apiResultToScenario(response, scenarioCsv, {
          scenarioId: streamScenarioId,
        })
        setScenario(nextScenario)
        setScenarioSource("search")
        setPromptValue("")
        setPromptPlaceholder(createDefaultPrompt())
        setReportPending(false)
        setReportElapsedMs(0)
        setReportError(null)
        resetScenarioEditHistory()
        setStatus("idle")
      } catch (caught) {
        if (controller.signal.aborted) {
          return
        }
        const message =
          caught instanceof Error
            ? caught.message
            : "Unknown error during search."
        setStatus("error")
        setError(message)
      } finally {
        if (searchAbortRef.current === controller) {
          searchAbortRef.current = null
        }
      }
    },
    [abortActiveSearch, resetScenarioEditHistory]
  )

  useEffect(() => {
    if (isHandoff) {
      if (handoffConsumedRef.current) return
      handoffConsumedRef.current = true

      const pendingCsv = consumePendingScenarioCsv()
      if (!pendingCsv) {
        queueMicrotask(() => {
          setScenario(null)
          setScenarioSource(null)
          setStatus("error")
          setError("No scenario CSV was transferred from /launch.")
          resetScenarioEditHistory()
        })
        return
      }

      queueMicrotask(() => {
        void runScenarioCsvText(pendingCsv)
      })
      return
    }

    clearPendingScenarioCsv()

    if (startsInDemo) {
      persistDemoDashboardEntry()
      queueMicrotask(() => {
        setScenario(sampleSupplyScenario)
        setScenarioSource("demo")
        setScenarioInput(null)
        setScoringLens(createScoringLens())
        setPromptValue("")
        setPromptPlaceholder(createDefaultPrompt())
        setStatus("idle")
        setError(null)
        setPromptError(null)
        setReportPending(false)
        setReportElapsedMs(0)
        setReportError(null)
        resetScenarioEditHistory()
      })
      return
    }

    clearDashboardEntry()
    queueMicrotask(() => {
      setScenario(null)
      setScenarioSource(null)
      setPromptValue("")
      setStatus("idle")
      setError(null)
      setPromptError(null)
      setReportPending(false)
      setReportElapsedMs(0)
      setReportError(null)
      resetScenarioEditHistory()
    })
  }, [isHandoff, resetScenarioEditHistory, runScenarioCsvText, startsInDemo])

  const handleUseDemo = useCallback(() => {
    abortActiveSearch()
    clearPendingScenarioCsv()
    persistDemoDashboardEntry()
    setStatus("idle")
    setError(null)
    setScenario(sampleSupplyScenario)
    setScenarioSource("demo")
    setScenarioInput(null)
    setScoringLens(createScoringLens())
    setSearchProgress(null)
    setPromptValue("")
    setPromptPlaceholder(createDefaultPrompt())
    setPromptError(null)
    setReportPending(false)
    setReportElapsedMs(0)
    setReportError(null)
    resetScenarioEditHistory()
  }, [abortActiveSearch, resetScenarioEditHistory])

  const handleReset = useCallback(() => {
    abortActiveSearch()
    clearPendingScenarioCsv()
    clearDashboardEntry()
    setStatus("idle")
    setError(null)
    setScenario(null)
    setScenarioSource(null)
    setScenarioInput(null)
    setScoringLens(createScoringLens())
    setSearchProgress(null)
    setPromptValue("")
    setPromptError(null)
    setReportPending(false)
    setReportElapsedMs(0)
    setReportError(null)
    resetScenarioEditHistory()
  }, [abortActiveSearch, resetScenarioEditHistory])

  const handlePromptSubmit = useCallback(async () => {
    if (!scenario || !viewScenario || !promptValue.trim() || promptPending) {
      return
    }
    if (status === "loading") {
      setPromptError(
        "Wait for the search to finish before editing the scenario."
      )
      return
    }

    setPromptPending(true)
    setPromptError(null)

    try {
      // Send the scenario as displayed, so the editor judges the scores the
      // user is looking at.
      const response = await editScenario({
        prompt: promptValue,
        scenario: viewScenario,
      })

      if (response.status === "applied" && response.scenario) {
        setScenarioEditHistory((previousState) => ({
          future: [],
          past: scenario
            ? trimScenarioHistory([...previousState.past, scenario])
            : previousState.past,
        }))
        setScenario(response.scenario)
        setPromptError(null)
        return
      }

      setPromptError(response.message)
    } catch (caught) {
      setPromptError(
        caught instanceof Error
          ? caught.message
          : "Scenario edit failed unexpectedly."
      )
    } finally {
      setPromptPending(false)
    }
  }, [promptPending, promptValue, scenario, status, viewScenario])

  const handleDownloadReport = useCallback(
    async ({
      scenario: activeScenario,
      selectedManufacturerByComponent,
    }: {
      scenario: SupplyScenario
      selectedManufacturerByComponent: Record<string, string>
    }) => {
      if (reportPending) {
        return
      }

      setReportPending(true)
      setReportElapsedMs(0)
      setReportError(null)

      try {
        const response = await generateScenarioReport({
          scenario: activeScenario,
          scoring: scenarioSupportsLens(activeScenario)
            ? {
                transportMode: scoringLens.transportMode,
                weights: normalizeWeights(scoringLens.weights),
              }
            : undefined,
          selectedManufacturerByComponent,
        })
        downloadBase64File(
          response.fileName,
          response.contentBase64,
          response.mimeType
        )
      } catch (caught) {
        setReportError(
          caught instanceof Error
            ? caught.message
            : "Scenario report failed unexpectedly."
        )
      } finally {
        setReportPending(false)
        setReportElapsedMs(0)
      }
    },
    [reportPending, scoringLens]
  )

  const handleOpenEditor = useCallback(() => {
    if (!scenario) {
      return
    }
    // Live runs reopen with their original inputs; the demo is rebuilt from
    // what's on screen. Either way, start from the transport mode in view.
    const input =
      scenarioInput ??
      supplyScenarioToSearchInput(scenario, scoringLens.transportMode)
    setEditorInitial({ ...input, transportMode: scoringLens.transportMode })
    setEditorKey((key) => key + 1)
    setEditorOpen(true)
  }, [scenario, scenarioInput, scoringLens.transportMode])

  const handleEditorSubmit = useCallback(
    (csvText: string) => {
      setEditorOpen(false)
      void runScenarioCsvText(csvText)
    },
    [runScenarioCsvText]
  )

  return (
    <>
      <DashboardShell
        error={error}
        onDownloadReport={handleDownloadReport}
        onEditScenario={handleOpenEditor}
        onFile={() => undefined}
        onPromptChange={setPromptValue}
        onPromptSubmit={handlePromptSubmit}
        onReset={handleReset}
        onUseDemo={handleUseDemo}
        promptError={promptError}
        promptPending={promptPending}
        promptPlaceholder={promptPlaceholder}
        promptValue={promptValue}
        reportError={reportError}
        reportProgress={getReportProgressState(reportElapsedMs)}
        reportPending={reportPending}
        scenario={viewScenario}
        scenarioSource={scenarioSource}
        scoringDisabled={scoringDisabled}
        scoringLens={scoringLens}
        onScoringLensChange={setScoringLens}
        searchProgress={
          searchProgress
            ? {
                components: searchProgress,
                elapsedSeconds: searchElapsedSeconds,
              }
            : null
        }
        showUploadPanel={false}
        status={status}
      />
      <Sheet open={editorOpen} onOpenChange={setEditorOpen}>
        <SheetContent
          side="right"
          className="w-full overflow-y-auto data-[side=right]:sm:max-w-2xl"
        >
          <SheetHeader>
            <SheetTitle>Edit scenario</SheetTitle>
            <SheetDescription>
              Change the product, destination, transport mode, or components,
              then re-run the search. Results stream in as each component
              finishes.
            </SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-6">
            {editorOpen ? (
              <ScenarioBuilderForm
                key={editorKey}
                initialScenario={editorInitial}
                onSubmit={handleEditorSubmit}
                submitLabel="Re-run search"
              />
            ) : null}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
