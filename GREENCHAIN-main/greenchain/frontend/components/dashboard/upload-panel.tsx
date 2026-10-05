"use client"

import { useRef, useState, type ChangeEvent, type DragEvent } from "react"

import { HugeiconsIcon } from "@hugeicons/react"
import { Cancel01Icon } from "@hugeicons/core-free-icons"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type UploadPanelStatus = "idle" | "loading" | "error"

interface UploadPanelProps {
  className?: string
  error: string | null
  onFile: (file: File) => void
  onReset: () => void
  onUseDemo: () => void
  scenarioSource: "demo" | "search" | null
  scenarioTitle: string | null
  status: UploadPanelStatus
}

function UploadGlyph({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      <path d="M7 18a4 4 0 1 1 .8-7.92A6 6 0 0 1 19 9a4.5 4.5 0 0 1 .5 8.97" />
      <path d="M12 12v8" />
      <path d="m8.5 15.5 3.5-3.5 3.5 3.5" />
    </svg>
  )
}

function Spinner({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden
      className={cn("animate-spin", className)}
    >
      <path d="M12 3a9 9 0 1 0 9 9" opacity={0.9} />
      <path d="M12 3a9 9 0 0 1 9 9" opacity={0.25} />
    </svg>
  )
}

export function UploadPanel({
  className,
  error,
  onFile,
  onReset,
  onUseDemo,
  scenarioSource,
  scenarioTitle,
  status,
}: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragActive, setIsDragActive] = useState(false)
  const [isManuallyExpanded, setIsManuallyExpanded] = useState(false)
  const isExpanded = !scenarioSource || status !== "idle" || isManuallyExpanded

  function openFilePicker() {
    if (status === "loading") return
    inputRef.current?.click()
  }

  function handleUseDemoClick() {
    setIsManuallyExpanded(false)
    onUseDemo()
  }

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) {
      setIsManuallyExpanded(false)
      onFile(file)
    }
    event.target.value = ""
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragActive(false)
    if (status === "loading") return

    const file = event.dataTransfer.files?.[0]
    if (file) {
      setIsManuallyExpanded(false)
      onFile(file)
    }
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    if (status === "loading") return
    setIsDragActive(true)
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragActive(false)
  }

  if (scenarioSource && status === "idle" && !isExpanded) {
    const compactEyebrow =
      scenarioSource === "demo" ? "Demo loaded" : "Scenario loaded"
    const compactTitle =
      scenarioSource === "demo"
        ? `${scenarioTitle ?? "Sample scenario"} is already on screen`
        : `${scenarioTitle ?? "Search results"} is already loaded`
    const compactDescription =
      scenarioSource === "demo"
        ? "Keep the graph visible and open the uploader only when you want to replace the sample."
        : "Open the uploader to run another CSV, or switch back to the demo sample."

    return (
      <section
        className={cn(
          "panel-surface flex flex-col gap-4 rounded-2xl px-4 py-4 lg:flex-row lg:items-center lg:justify-between",
          className
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          hidden
          onChange={handleFileInputChange}
        />

        <div className="min-w-0">
          <p className="text-[10px] font-medium tracking-[0.28em] text-white/40 uppercase">
            {compactEyebrow}
          </p>
          <p className="mt-1 text-sm font-medium text-white/85">
            {compactTitle}
          </p>
          <p className="mt-1 text-xs text-white/48">{compactDescription}</p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setIsManuallyExpanded(true)}
          >
            Open uploader
          </Button>
          {scenarioSource === "search" ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleUseDemoClick}
            >
              Switch to demo
            </Button>
          ) : null}
        </div>
      </section>
    )
  }

  return (
    <section
      className={cn(
        "panel-surface flex flex-col gap-3 rounded-2xl px-4 py-4",
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-medium tracking-[0.28em] text-white/40 uppercase">
            Upload
          </p>
          <p className="mt-1 text-sm font-medium text-white/85">
            Upload a scenario CSV with one current supplier per component
          </p>
          <p className="mt-1 text-xs text-white/48">
            Required columns: product, quantity, destination, component,
            current_manufacturer, current_country. One row per component.
          </p>
        </div>
        {status === "error" ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onReset}
            className="rounded-full text-white/70 hover:bg-white/[0.05] hover:text-white"
          >
            <HugeiconsIcon icon={Cancel01Icon} strokeWidth={2} />
            Reset
          </Button>
        ) : scenarioSource ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setIsManuallyExpanded(false)}
            className="rounded-full text-white/70 hover:bg-white/[0.05] hover:text-white"
          >
            Hide uploader
          </Button>
        ) : null}
      </div>

      <div
        onClick={openFilePicker}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault()
            openFilePicker()
          }
        }}
        role="button"
        tabIndex={0}
        aria-disabled={status === "loading"}
        className={cn(
          "relative flex min-h-[112px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/[0.14] bg-[rgba(10,10,18,0.48)] px-4 py-5 text-center transition-colors",
          status === "loading"
            ? "cursor-wait opacity-80"
            : "cursor-pointer hover:border-white/[0.26] hover:bg-[rgba(14,14,22,0.6)]",
          isDragActive && "border-primary/60 bg-[rgba(18,26,20,0.7)]",
          status === "error" && "border-red-400/40"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          hidden
          onChange={handleFileInputChange}
        />

        {status === "loading" ? (
          <>
            <Spinner className="h-6 w-6 text-white/70" />
            <p className="text-sm font-medium text-white/85">
              Searching manufacturers…
            </p>
            <p className="text-xs text-white/48">
              Running agent + ML scoring. This takes 15–60 seconds.
            </p>
          </>
        ) : status === "error" ? (
          <>
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-red-400/10 text-red-300">
              !
            </div>
            <p className="text-sm font-medium text-red-200">
              {error ?? "Something went wrong."}
            </p>
            <p className="text-xs text-white/48">
              Click to try a different CSV or press Reset.
            </p>
          </>
        ) : (
          <>
            <UploadGlyph className="h-6 w-6 text-white/60" />
            <p className="text-sm font-medium text-white/85">
              Drop a CSV here, or click to browse
            </p>
            <p className="text-xs text-white/48">
              Multi-row scenario CSV · triggers a live component search
            </p>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 pt-1">
        {scenarioSource === "demo" ? (
          <span className="text-xs text-white/55">Demo scenario active</span>
        ) : (
          <button
            type="button"
            onClick={handleUseDemoClick}
            disabled={status === "loading"}
            className="text-xs text-white/55 underline-offset-4 transition-colors hover:text-white hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          >
            {scenarioSource === "search"
              ? "Switch back to demo data"
              : "Or use demo data (sample Lint Roller scenario)"}
          </button>
        )}
        <span className="font-mono text-[10px] tracking-[0.18em] text-white/30 uppercase">
          {status === "loading"
            ? "Running"
            : status === "error"
              ? "Error"
              : "Ready"}
        </span>
      </div>
    </section>
  )
}
