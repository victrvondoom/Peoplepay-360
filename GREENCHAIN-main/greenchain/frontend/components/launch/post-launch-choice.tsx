"use client"

import { useRef, useState, type ChangeEvent, type DragEvent } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  ArrowRight01Icon,
  Csv01Icon,
  DownloadSquare01Icon,
  FileImportIcon,
  MapsGlobal01Icon,
  Tick02Icon,
} from "@hugeicons/core-free-icons"

import { ScenarioBuilderForm } from "@/components/launch/scenario-builder-form"
import { GreenChainLogo } from "@/components/green-chain-logo"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"
import { savePendingScenarioCsv } from "@/lib/scenario-handoff"
import {
  OPTIONAL_SCENARIO_CSV_HEADERS,
  REQUIRED_SCENARIO_CSV_HEADERS,
  type ScenarioCsvPreview,
  validateScenarioCsvFile,
} from "@/lib/scenario-csv"
import { persistDemoDashboardEntry } from "@/lib/dashboard-entry"
import { sampleSupplyScenario } from "@/lib/supply-chain-scenario"
import { cn } from "@/lib/utils"

const TEMPLATE_PATH = "/templates/scenario_csv_v2.csv"

const demoDestination = sampleSupplyScenario.destination.location
const demoComponents = sampleSupplyScenario.components
  .map((c) => c.label)
  .join(", ")
const demoSummaryLine = `${sampleSupplyScenario.title} · ${sampleSupplyScenario.quantity.toLocaleString()} ${sampleSupplyScenario.unit} · ${demoDestination.city}, ${demoDestination.country}`

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <TableRow>
      <TableCell className="w-40 text-muted-foreground">{label}</TableCell>
      <TableCell className="whitespace-normal text-foreground">
        {value}
      </TableCell>
    </TableRow>
  )
}

export function PostLaunchChoice() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ScenarioCsvPreview | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  async function loadFile(nextFile: File) {
    setSelectedFile(null)
    setPreview(null)
    setValidationError(null)
    setUploadError(null)

    try {
      const text = await nextFile.text()
      const nextPreview = validateScenarioCsvFile(nextFile, text)
      setSelectedFile(nextFile)
      setPreview(nextPreview)
    } catch (error) {
      setValidationError(
        error instanceof Error ? error.message : "Unable to read this CSV."
      )
    }
  }

  function openFilePicker() {
    fileInputRef.current?.click()
  }

  async function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0]
    if (!nextFile) return

    await loadFile(nextFile)
    event.target.value = ""
  }

  async function handleDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault()
    setIsDragging(false)

    const nextFile = event.dataTransfer.files?.[0]
    if (!nextFile) return

    await loadFile(nextFile)
  }

  async function handleSubmit() {
    if (!selectedFile || !preview) return

    setIsSubmitting(true)
    setUploadError(null)

    try {
      const text = await selectedFile.text()
      savePendingScenarioCsv(text)
      router.push("/dashboard?handoff=1")
    } catch (error) {
      setUploadError(
        error instanceof Error
          ? error.message
          : "Could not open this scenario in the dashboard."
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleBuiltScenario(csvText: string) {
    savePendingScenarioCsv(csvText)
    router.push("/dashboard?handoff=1")
  }

  const previewRows = preview
    ? [
        ["Product", preview.normalized.product],
        ["Quantity", preview.normalized.quantity.toString()],
        ["Destination", preview.normalized.destination],
        ["Unit", preview.normalized.unit],
        ["Transport mode", preview.normalized.transportMode],
        ["Components", preview.normalized.componentCount.toString()],
        [
          "Current suppliers",
          preview.normalized.components
            .map(
              (component) =>
                `${component.component}: ${component.currentManufacturer}`
            )
            .join(" | "),
        ],
        [
          "Alternates per component",
          preview.normalized.targetCount?.toString() ??
            "Default backend behavior",
        ],
      ]
    : []

  return (
    <main className="dashboard-shell min-h-svh">
      <div className="mx-auto flex min-h-svh w-full max-w-[1500px] flex-col px-6 py-6 md:px-10">
        <header className="flex flex-col gap-5 border-b border-border/70 pb-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-4">
            <Link
              href="/"
              className="inline-flex w-fit items-center transition-opacity hover:opacity-90"
            >
              <GreenChainLogo variant="onDark" className="h-9 w-auto" />
            </Link>
            <div className="max-w-3xl">
              <h1 className="font-heading text-4xl tracking-[-0.05em] text-white sm:text-5xl">
                Build a scenario or open the demo
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
                Fill in the form or import a CSV — both are validated here
                before the dashboard runs searches.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button asChild variant="outline">
              <a href={TEMPLATE_PATH} download>
                <HugeiconsIcon
                  icon={DownloadSquare01Icon}
                  strokeWidth={2}
                  data-icon="inline-start"
                />
                Download template
              </a>
            </Button>
            <Button asChild>
              <Link
                href="/dashboard"
                onClick={() => persistDemoDashboardEntry()}
              >
                <HugeiconsIcon
                  icon={MapsGlobal01Icon}
                  strokeWidth={2}
                  data-icon="inline-start"
                />
                Continue with demo
              </Link>
            </Button>
          </div>
        </header>

        <section className="flex flex-1 items-start pt-7 pb-10 md:pt-8">
          <div className="grid w-full gap-6 xl:grid-cols-[1.28fr_0.92fr] xl:items-start">
            <Card className="panel-surface gap-0 rounded-[2rem] border-border/70 bg-card/92 py-0">
              <Tabs defaultValue="build">
                <CardHeader className="gap-4 border-b border-border/70 py-6">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <CardTitle>Scenario</CardTitle>
                    <TabsList>
                      <TabsTrigger value="build">Build</TabsTrigger>
                      <TabsTrigger value="upload">Upload CSV</TabsTrigger>
                    </TabsList>
                  </div>
                  <CardDescription>
                    Product, destination, transport mode, and one row per
                    component — build it here or import a CSV with the same
                    columns.
                  </CardDescription>
                </CardHeader>

                <TabsContent value="build" className="mt-0">
                  <CardContent className="py-6">
                    <ScenarioBuilderForm onSubmit={handleBuiltScenario} />
                  </CardContent>
                </TabsContent>

                <TabsContent value="upload" className="mt-0">
                  <CardContent className="flex flex-col gap-6 py-6">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".csv,text/csv"
                      className="hidden"
                      onChange={handleInputChange}
                    />

                    <button
                      type="button"
                      onClick={openFilePicker}
                      onDragEnter={(event) => {
                        event.preventDefault()
                        setIsDragging(true)
                      }}
                      onDragLeave={(event) => {
                        event.preventDefault()
                        setIsDragging(false)
                      }}
                      onDragOver={(event) => {
                        event.preventDefault()
                        setIsDragging(true)
                      }}
                      onDrop={handleDrop}
                      className={cn(
                        "flex min-h-52 w-full flex-col items-center justify-center gap-4 rounded-[1.6rem] border border-dashed px-6 py-8 text-center transition-colors",
                        isDragging
                          ? "border-primary bg-primary/8"
                          : "border-border bg-background/35 hover:border-primary/50 hover:bg-background/50"
                      )}
                    >
                      <div className="flex size-16 items-center justify-center rounded-full border border-border/80 bg-muted/40">
                        <HugeiconsIcon icon={Csv01Icon} strokeWidth={2} />
                      </div>
                      <div className="max-w-lg">
                        <p className="text-lg font-medium text-foreground">
                          Drop a file or browse
                        </p>
                        <p className="mt-2 text-sm leading-6 text-muted-foreground">
                          Pipe-delimited lists in cells where needed, e.g.{" "}
                          <code>iso14001|sbt_committed</code>.
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
                        <span className="text-muted-foreground/90">
                          Required columns:{" "}
                          {REQUIRED_SCENARIO_CSV_HEADERS.join(", ")}
                        </span>
                      </div>
                    </button>

                    <div className="flex justify-end">
                      <Button asChild variant="outline" size="sm">
                        <a href={TEMPLATE_PATH} download>
                          <HugeiconsIcon
                            icon={DownloadSquare01Icon}
                            strokeWidth={2}
                            data-icon="inline-start"
                          />
                          Download template
                        </a>
                      </Button>
                    </div>

                    {validationError ? (
                      <div className="rounded-2xl border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive">
                        {validationError}
                      </div>
                    ) : null}

                    {preview ? (
                      <section className="rounded-[1.4rem] border border-border/70 bg-background/35 p-4">
                        <p className="text-xs text-muted-foreground">
                          {preview.filename}
                        </p>

                        <div className="mt-4">
                          <Table>
                            <TableBody>
                              {previewRows.map(([label, value]) => (
                                <PreviewRow
                                  key={label}
                                  label={label}
                                  value={value}
                                />
                              ))}
                            </TableBody>
                          </Table>
                        </div>

                        <p className="mt-4 border-t border-border/60 pt-4 text-xs leading-5 text-muted-foreground">
                          Optional CSV columns:{" "}
                          {OPTIONAL_SCENARIO_CSV_HEADERS.join(", ")}
                        </p>
                      </section>
                    ) : null}

                    {uploadError ? (
                      <div className="rounded-2xl border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive">
                        {uploadError}
                      </div>
                    ) : null}
                  </CardContent>

                  <CardFooter className="flex flex-wrap justify-end gap-3 border-t border-border/70 py-5">
                    <div className="flex flex-wrap items-center gap-3">
                      <Button
                        variant="outline"
                        onClick={openFilePicker}
                        disabled={isSubmitting}
                      >
                        Choose another file
                      </Button>
                      <Button
                        onClick={handleSubmit}
                        disabled={!selectedFile || !preview || isSubmitting}
                      >
                        {isSubmitting ? (
                          <>
                            <HugeiconsIcon
                              icon={FileImportIcon}
                              strokeWidth={2}
                              data-icon="inline-start"
                            />
                            Opening dashboard
                          </>
                        ) : (
                          <>
                            <HugeiconsIcon
                              icon={FileImportIcon}
                              strokeWidth={2}
                              data-icon="inline-start"
                            />
                            Open in dashboard
                          </>
                        )}
                      </Button>
                    </div>
                  </CardFooter>
                </TabsContent>
              </Tabs>
            </Card>

            <Card className="panel-surface h-fit gap-0 rounded-[2rem] border-border/70 bg-card/92 py-0">
              <CardHeader className="gap-2 border-b border-border/70 py-4">
                <CardTitle>Demo</CardTitle>
                <CardDescription className="text-sm leading-relaxed">
                  {demoSummaryLine}
                </CardDescription>
              </CardHeader>

              <CardContent className="py-4">
                <div className="grid gap-2.5 text-sm text-muted-foreground">
                  <div className="flex items-start gap-2.5">
                    <HugeiconsIcon
                      icon={Tick02Icon}
                      strokeWidth={2}
                      className="mt-0.5 shrink-0 text-primary"
                    />
                    <span>
                      Supply components:{" "}
                      <span className="text-foreground">{demoComponents}</span>
                    </span>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <HugeiconsIcon
                      icon={Tick02Icon}
                      strokeWidth={2}
                      className="mt-0.5 shrink-0 text-primary"
                    />
                    <span>
                      {sampleSupplyScenario.stats.graphNodeCount} graph nodes,{" "}
                      {sampleSupplyScenario.stats.routeCount} routes — same data
                      as <code className="text-xs">sampledata.json</code>
                    </span>
                  </div>
                </div>
              </CardContent>

              <CardFooter className="border-t border-border/70 py-4">
                <Button asChild className="w-full">
                  <Link
                    href="/dashboard"
                    onClick={() => persistDemoDashboardEntry()}
                  >
                    <HugeiconsIcon
                      icon={ArrowRight01Icon}
                      strokeWidth={2}
                      data-icon="inline-start"
                    />
                    Continue with demo
                  </Link>
                </Button>
              </CardFooter>
            </Card>
          </div>
        </section>
      </div>
    </main>
  )
}
