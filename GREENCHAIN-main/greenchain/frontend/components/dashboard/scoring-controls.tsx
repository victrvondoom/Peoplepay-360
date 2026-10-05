"use client"

import { useId } from "react"

import type { TransportMode } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Slider } from "@/components/ui/slider"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  DEFAULT_SCORING_WEIGHTS,
  normalizeWeights,
  TRANSPORT_MODE_LABELS,
  TRANSPORT_MODES,
  WEIGHT_KEYS,
  WEIGHT_LABELS,
  weightsEqual,
  type ScoringLens,
} from "@/lib/scoring-lens"
import { cn } from "@/lib/utils"

interface ScoringControlsProps {
  className?: string
  disabled?: boolean
  lens: ScoringLens
  onLensChange: (lens: ScoringLens) => void
}

const SLIDER_MAX = 100
const SLIDER_STEP = 5

export function ScoringControls({
  className,
  disabled = false,
  lens,
  onLensChange,
}: ScoringControlsProps) {
  const idPrefix = useId()
  const shares = normalizeWeights(lens.weights)
  const customWeights = !weightsEqual(lens.weights, DEFAULT_SCORING_WEIGHTS)

  return (
    <div
      className={cn("flex flex-wrap items-center gap-x-4 gap-y-2", className)}
      aria-disabled={disabled || undefined}
    >
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Transport
        </span>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={lens.transportMode}
          disabled={disabled}
          aria-label="Transport mode"
          onValueChange={(value) => {
            if (value && value !== lens.transportMode) {
              onLensChange({ ...lens, transportMode: value as TransportMode })
            }
          }}
          className="border-white/12"
        >
          {TRANSPORT_MODES.map((mode) => (
            <ToggleGroupItem
              key={mode}
              value={mode}
              aria-label={`${TRANSPORT_MODE_LABELS[mode]} freight`}
              className="h-7 border-white/12 px-3 text-xs text-white/70 data-[state=on]:bg-white/[0.1] data-[state=on]:text-white"
            >
              {TRANSPORT_MODE_LABELS[mode]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <Popover>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            className="h-7 rounded-full border-white/12 bg-white/[0.03] px-3 text-xs text-white/75 hover:bg-white/[0.06] hover:text-white"
          >
            Weights
            <span className="text-white/45">
              {customWeights ? "· custom" : "· default"}
            </span>
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-sm font-medium">Score weights</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!customWeights}
              onClick={() =>
                onLensChange({
                  ...lens,
                  weights: { ...DEFAULT_SCORING_WEIGHTS },
                })
              }
              className="h-7 px-2 text-xs"
            >
              Reset
            </Button>
          </div>
          <div className="flex flex-col gap-4">
            {WEIGHT_KEYS.map((key) => {
              const labelId = `${idPrefix}-${key}`
              return (
                <div key={key} className="flex flex-col gap-2">
                  <div className="flex items-center justify-between text-xs">
                    <span id={labelId} className="text-foreground/85">
                      {WEIGHT_LABELS[key]}
                    </span>
                    <span className="font-mono text-muted-foreground tabular-nums">
                      {Math.round(shares[key] * 100)}%
                    </span>
                  </div>
                  <Slider
                    aria-labelledby={labelId}
                    min={0}
                    max={SLIDER_MAX}
                    step={SLIDER_STEP}
                    value={[Math.round(lens.weights[key] * SLIDER_MAX)]}
                    onValueChange={([next]) => {
                      const weights = {
                        ...lens.weights,
                        [key]: (next ?? 0) / SLIDER_MAX,
                      }
                      // Keep at least one dimension weighted.
                      if (WEIGHT_KEYS.some((item) => weights[item] > 0)) {
                        onLensChange({ ...lens, weights })
                      }
                    }}
                  />
                </div>
              )
            })}
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Shares are normalised to 100%. Scores compare the options within
            each component and update instantly, with no new search.
          </p>
        </PopoverContent>
      </Popover>

      {disabled ? (
        <span className="text-xs text-muted-foreground">
          Re-run the search to re-rank this scenario.
        </span>
      ) : null}
    </div>
  )
}
