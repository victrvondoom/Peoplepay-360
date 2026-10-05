"use client"

import { memo, useCallback, useEffect, useRef, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { MapsGlobal01Icon, Route03Icon } from "@hugeicons/core-free-icons"
import { useDefaultLayout } from "react-resizable-panels"

import { InteractiveGlobe } from "@/components/dashboard/interactive-globe"
import { Button } from "@/components/ui/button"
import {
  LaggedHandleVisual,
  LaggedPanelShell,
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
  useResizeMotion,
} from "@/components/ui/resizable"
import { getEcoDotStyles, getEcoSelectionStyles } from "@/lib/eco-visuals"
import {
  type SupplyScenario,
  type SupplyScenarioComponentNode,
  type SupplyScenarioManufacturerNode,
  type SupplyScenarioSelectableNodeId,
} from "@/lib/supply-chain-scenario"
import { cn, panelLayoutStorage } from "@/lib/utils"

interface GlobeViewProps {
  bestEcoManufacturerByComponent: Record<string, string>
  className?: string
  hoveredNodeId: SupplyScenarioSelectableNodeId | null
  onHoverNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onSelectNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onToggleRouteCollapsed: (componentId: string) => void
  onToggleRouteVisible: (componentId: string) => void
  pinnedManufacturerByComponent: Record<string, string>
  routeCollapsedByComponent: Record<string, boolean>
  routeVisibleByComponent: Record<string, boolean>
  scenario: SupplyScenario
  selectedNodeId: SupplyScenarioSelectableNodeId | null
}

const CORNER_STAR_DOTS = [
  { left: "6%", opacity: 0.5, size: 1.4, top: "10%" },
  { left: "11%", opacity: 0.76, size: 2.1, top: "15%" },
  { left: "17%", opacity: 0.44, size: 1.2, top: "8%" },
  { left: "82%", opacity: 0.42, size: 1.2, top: "9%" },
  { left: "88%", opacity: 0.74, size: 2, top: "14%" },
  { left: "93%", opacity: 0.52, size: 1.4, top: "11%" },
  { left: "8%", opacity: 0.4, size: 1.1, top: "84%" },
  { left: "14%", opacity: 0.68, size: 1.8, top: "89%" },
  { left: "19%", opacity: 0.34, size: 1, top: "80%" },
  { left: "80%", opacity: 0.3, size: 1, top: "86%" },
  { left: "87%", opacity: 0.64, size: 1.8, top: "91%" },
  { left: "92%", opacity: 0.46, size: 1.2, top: "83%" },
] as const

const GLOBE_SPLIT_ID = "dashboard-globe-split"
const GLOBE_CANVAS_PANEL_ID = "dashboard-globe-canvas-panel"
const GLOBE_ROUTES_PANEL_ID = "dashboard-globe-routes-panel"
const GLOBE_SPLIT_DEFAULT = {
  [GLOBE_CANVAS_PANEL_ID]: 66,
  [GLOBE_ROUTES_PANEL_ID]: 34,
}

function getManufacturerForComponent(
  scenario: SupplyScenario,
  component: SupplyScenarioComponentNode
) {
  return component.manufacturerIds
    .map((manufacturerId) =>
      scenario.manufacturers.find(
        (manufacturer) => manufacturer.id === manufacturerId
      )
    )
    .filter((manufacturer): manufacturer is SupplyScenarioManufacturerNode =>
      Boolean(manufacturer)
    )
}

function getLinkedComponentId(
  scenario: SupplyScenario,
  nodeId: SupplyScenarioSelectableNodeId | null
) {
  if (!nodeId) {
    return null
  }

  const component = scenario.components.find((item) => item.id === nodeId)

  if (component) {
    return component.id
  }

  const manufacturer = scenario.manufacturers.find((item) => item.id === nodeId)

  return manufacturer?.componentId ?? null
}

function getManufacturerStatusStyles(isCurrent: boolean) {
  return isCurrent
    ? {
        badgeClassName:
          "border border-amber-300/24 bg-amber-300/10 text-amber-200",
      }
    : {
        badgeClassName:
          "border border-slate-400/22 bg-slate-400/[0.08] text-slate-300/90",
      }
}

function ManufacturerRow({
  disabled = false,
  isFocused,
  isMostSustainable,
  isPinned,
  manufacturer,
  onHoverNode,
  onSelectNode,
}: {
  disabled?: boolean
  isFocused: boolean
  isMostSustainable: boolean
  isPinned: boolean
  manufacturer: SupplyScenarioManufacturerNode
  onHoverNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onSelectNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
}) {
  const statusStyles = getManufacturerStatusStyles(manufacturer.isCurrent)
  const ecoDotStyles = getEcoDotStyles(manufacturer.ecoScore)
  const ecoSelectionStyles = getEcoSelectionStyles(manufacturer.ecoScore)

  return (
    <button
      type="button"
      onClick={() => {
        if (!disabled) {
          onSelectNode(manufacturer.id)
        }
      }}
      onMouseEnter={() => {
        if (!disabled) {
          onHoverNode(manufacturer.id)
        }
      }}
      onMouseLeave={() => {
        if (!disabled) {
          onHoverNode(null)
        }
      }}
      className={cn(
        "group flex w-full items-center gap-2.5 px-2.5 py-2 text-left transition-colors",
        disabled ? "cursor-default" : "",
        isFocused
          ? ""
          : isPinned
            ? ""
            : manufacturer.isCurrent
              ? "bg-transparent hover:bg-white/[0.04]"
              : "bg-transparent hover:bg-white/[0.03]"
      )}
      style={{
        background: isFocused
          ? ecoSelectionStyles.surfaceStrong
          : isPinned
            ? ecoSelectionStyles.surface
            : undefined,
        boxShadow:
          isFocused || isPinned
            ? `inset 2px 0 0 ${ecoSelectionStyles.edge}${isFocused ? `, ${ecoSelectionStyles.glow}` : ""}`
            : "none",
        opacity: disabled ? 0.62 : 1,
      }}
    >
      <span
        className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
        style={{
          background: ecoDotStyles.background,
          boxShadow: ecoDotStyles.shadow,
        }}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-white/84">
          {manufacturer.name}
        </p>
        <p className="text-[10px] text-white/36">
          {manufacturer.location.city}, {manufacturer.location.country}
        </p>
      </div>
      <span
        className={cn(
          "rounded-full px-1.5 py-0.5 text-[9px] font-medium",
          statusStyles.badgeClassName
        )}
      >
        {manufacturer.isCurrent ? "Current" : "Alternate"}
      </span>
      {isMostSustainable ? (
        <span
          className="hidden rounded-full border px-2 py-1 text-[10px] font-medium md:inline-flex"
          style={{
            background: ecoSelectionStyles.surface,
            borderColor: ecoSelectionStyles.edge,
            color: ecoSelectionStyles.accent,
          }}
        >
          Most sustainable
        </span>
      ) : null}
      {isPinned ? (
        <span
          className="hidden rounded-full border px-2 py-1 text-[10px] font-medium md:inline-flex"
          style={{
            background: ecoSelectionStyles.surface,
            borderColor: ecoSelectionStyles.edge,
            color: ecoSelectionStyles.accent,
          }}
        >
          Selected
        </span>
      ) : null}
      <span className="hidden font-mono text-[10px] tracking-[0.14em] text-white/32 uppercase sm:block">
        {manufacturer.location.countryCode}
      </span>
    </button>
  )
}

function GlobeCanvasSection({
  bestEcoManufacturerByComponent,
  hoveredNodeId,
  isSplitLayout,
  onHoverNode,
  onSelectNode,
  pinnedManufacturerByComponent,
  routeVisibleByComponent,
  scenario,
  selectedNodeId,
  visibleRouteCount,
}: {
  bestEcoManufacturerByComponent: Record<string, string>
  hoveredNodeId: SupplyScenarioSelectableNodeId | null
  isSplitLayout: boolean
  onHoverNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onSelectNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  pinnedManufacturerByComponent: Record<string, string>
  routeVisibleByComponent: Record<string, boolean>
  scenario: SupplyScenario
  selectedNodeId: SupplyScenarioSelectableNodeId | null
  visibleRouteCount: number
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div
        className={cn(
          "relative flex flex-1 items-center justify-center overflow-hidden rounded-xl border border-white/[0.08]",
          isSplitLayout ? "min-h-0" : "min-h-[27rem] md:min-h-[31rem]"
        )}
        style={{
          background:
            "radial-gradient(circle at 50% 46%, color-mix(in oklab, var(--primary) 10%, transparent), transparent 34%), radial-gradient(circle at 48% 52%, color-mix(in oklab, var(--foreground) 6%, transparent), transparent 52%), linear-gradient(180deg, rgba(6,10,14,0.98), rgba(4,7,10,1))",
        }}
      >
        <div className="pointer-events-none absolute inset-0">
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(circle at 8% 12%, rgba(255,255,255,0.02), transparent 18%), radial-gradient(circle at 91% 13%, color-mix(in oklab, var(--primary) 12%, transparent), transparent 16%), radial-gradient(circle at 10% 88%, rgba(255,255,255,0.014), transparent 16%), radial-gradient(circle at 89% 87%, color-mix(in oklab, var(--foreground) 8%, transparent), transparent 16%)",
            }}
          />
          {CORNER_STAR_DOTS.map((star, index) => (
            <span
              key={`${star.left}-${star.top}-${index}`}
              className="absolute rounded-full bg-white"
              style={{
                boxShadow: `0 0 ${star.size * 5}px rgba(255,255,255,${Math.min(
                  star.opacity * 0.35,
                  0.24
                )})`,
                height: star.size,
                left: star.left,
                opacity: star.opacity,
                top: star.top,
                width: star.size,
              }}
            />
          ))}
        </div>
        <div className="absolute inset-5 rounded-full border border-white/[0.09]" />
        <div className="absolute inset-14 rounded-full border border-white/[0.06]" />

        <InteractiveGlobe
          bestEcoManufacturerByComponent={bestEcoManufacturerByComponent}
          className="relative z-10"
          hoveredNodeId={hoveredNodeId}
          key={scenario.id}
          onHoverNode={onHoverNode}
          onSelectNode={onSelectNode}
          pinnedManufacturerByComponent={pinnedManufacturerByComponent}
          routeVisibleByComponent={routeVisibleByComponent}
          scenario={scenario}
          selectedNodeId={selectedNodeId}
        />
      </div>

      <p className="flex items-start gap-2 text-[10px] leading-snug text-white/34">
        <HugeiconsIcon
          icon={Route03Icon}
          strokeWidth={1.7}
          className="mt-0.5 h-3 w-3 shrink-0 text-white/28"
        />
        <span>
          Eco-colored arcs · {visibleRouteCount} visible route
          {visibleRouteCount === 1 ? "" : "s"} · scroll the graph out for
          manufacturer detail · tap a manufacturer to reroute.
        </span>
      </p>
    </div>
  )
}

function RoutesList({
  bestEcoManufacturerByComponent,
  hoveredNodeId,
  onHoverNode,
  onSelectNode,
  onToggleRouteCollapsed,
  onToggleRouteVisible,
  pinnedManufacturerByComponent,
  routeCollapsedByComponent,
  routeVisibleByComponent,
  scenario,
  selectedNodeId,
}: {
  bestEcoManufacturerByComponent: Record<string, string>
  hoveredNodeId: SupplyScenarioSelectableNodeId | null
  onHoverNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onSelectNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onToggleRouteCollapsed: (componentId: string) => void
  onToggleRouteVisible: (componentId: string) => void
  pinnedManufacturerByComponent: Record<string, string>
  routeCollapsedByComponent: Record<string, boolean>
  routeVisibleByComponent: Record<string, boolean>
  scenario: SupplyScenario
  selectedNodeId: SupplyScenarioSelectableNodeId | null
}) {
  const selectedComponentId = getLinkedComponentId(scenario, selectedNodeId)
  const hoveredComponentId = getLinkedComponentId(scenario, hoveredNodeId)

  return (
    <div className="space-y-2.5">
      <p className="dashboard-section-label">Routes</p>

      <div className="grid gap-2">
        {scenario.components.map((component) => {
          const manufacturers = getManufacturerForComponent(scenario, component)
          const currentManufacturer =
            manufacturers.find((manufacturer) => manufacturer.isCurrent) ??
            manufacturers[0]
          const activeManufacturer =
            manufacturers.find(
              (manufacturer) =>
                pinnedManufacturerByComponent[component.id] === manufacturer.id
            ) ?? currentManufacturer
          const componentDotStyles = activeManufacturer
            ? getEcoDotStyles(activeManufacturer.ecoScore)
            : null
          const componentSelectionStyles = activeManufacturer
            ? getEcoSelectionStyles(activeManufacturer.ecoScore)
            : null
          const isFocusedComponent =
            selectedComponentId === component.id ||
            hoveredComponentId === component.id
          const currentCount = manufacturers.filter(
            (manufacturer) => manufacturer.isCurrent
          ).length
          const isRouteVisible = routeVisibleByComponent[component.id] ?? true
          const isCollapsed = routeCollapsedByComponent[component.id] ?? true
          const toggleRouteLabel = isRouteVisible
            ? `Hide ${component.label} route`
            : `Show ${component.label} route`
          const toggleFoldLabel = isCollapsed
            ? `Expand ${component.label} manufacturers`
            : `Collapse ${component.label} manufacturers`

          return (
            <div
              key={component.id}
              className={cn(
                "rounded-lg border transition-colors",
                isFocusedComponent
                  ? "border-white/[0.12]"
                  : "border-white/[0.07] hover:border-white/[0.09]"
              )}
              style={{
                background: isFocusedComponent
                  ? `linear-gradient(180deg, ${componentSelectionStyles?.surfaceStrong ?? "rgba(255,255,255,0.06)"}, rgba(7,12,16,0.76))`
                  : isRouteVisible
                    ? "rgba(7,12,16,0.58)"
                    : "rgba(7,12,16,0.4)",
                boxShadow: isFocusedComponent
                  ? `0 0 0 1px ${componentSelectionStyles?.edge ?? "rgba(255,255,255,0.12)"}, inset 0 1px 0 rgba(255,255,255,0.04), ${componentSelectionStyles?.glow ?? "none"}`
                  : "inset 0 1px 0 rgba(255,255,255,0.03)",
                opacity: isRouteVisible ? 1 : 0.74,
              }}
              onMouseEnter={() => {
                if (isRouteVisible) {
                  onHoverNode(component.id)
                }
              }}
              onMouseLeave={() => {
                if (isRouteVisible) {
                  onHoverNode(null)
                }
              }}
            >
              <div className="flex items-start gap-2.5 px-3 py-2.5">
                <button
                  type="button"
                  onClick={() => {
                    if (isRouteVisible) {
                      onSelectNode(component.id)
                    }
                  }}
                  className="min-w-0 flex-1 text-left"
                >
                  <div className="flex items-center gap-1.5">
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{
                        background:
                          componentDotStyles?.background ??
                          "color-mix(in oklab, var(--primary) 82%, white 8%)",
                        boxShadow:
                          componentDotStyles?.shadow ??
                          "0 0 10px color-mix(in oklab, var(--primary) 26%, transparent)",
                      }}
                    />
                    <p className="truncate text-[13px] font-medium text-white/86">
                      {component.label}
                    </p>
                  </div>
                  <p className="mt-0.5 text-[11px] text-white/34">
                    {currentCount} current ·{" "}
                    {manufacturers.length - currentCount} alternate
                  </p>
                </button>
                <div className="flex shrink-0 items-center gap-1">
                  <span className="dashboard-chip-muted px-2 py-0.5 text-[9px] tracking-[0.08em]">
                    {manufacturers.length} sites
                  </span>
                  <button
                    type="button"
                    aria-label={toggleRouteLabel}
                    aria-pressed={isRouteVisible}
                    title={toggleRouteLabel}
                    onClick={() => onToggleRouteVisible(component.id)}
                    className={cn(
                      "flex h-6 w-6 items-center justify-center rounded-full border transition-colors",
                      isRouteVisible
                        ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
                        : "border-white/[0.08] bg-white/[0.04] text-white/42"
                    )}
                  >
                    <span aria-hidden="true" className="relative block h-3 w-3">
                      <span className="absolute inset-px rounded-full border border-current" />
                      {isRouteVisible ? (
                        <span className="absolute inset-[3px] rounded-full bg-current" />
                      ) : (
                        <span className="absolute top-1/2 right-px left-px h-px -rotate-45 bg-current" />
                      )}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-expanded={!isCollapsed}
                    aria-label={toggleFoldLabel}
                    title={toggleFoldLabel}
                    onClick={() => onToggleRouteCollapsed(component.id)}
                    className="flex h-6 w-6 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.04] text-[10px] font-semibold text-white/62 transition-colors hover:border-white/[0.12] hover:text-white/82"
                  >
                    <span aria-hidden="true">{isCollapsed ? "v" : "^"}</span>
                  </button>
                </div>
              </div>

              <div
                className="grid transition-[grid-template-rows,opacity] duration-300 ease-out"
                style={{
                  gridTemplateRows: isCollapsed ? "0fr" : "1fr",
                  opacity: isCollapsed ? 0 : 1,
                }}
              >
                <div className="min-h-0 overflow-hidden">
                  <div className="px-2.5 pb-2.5">
                    <div className="overflow-hidden rounded-lg border border-white/[0.05] bg-[rgba(6,6,12,0.44)]">
                      {manufacturers.map((manufacturer, index) => {
                        const isFocusedManufacturer =
                          selectedNodeId === manufacturer.id ||
                          hoveredNodeId === manufacturer.id
                        const isPinnedManufacturer =
                          pinnedManufacturerByComponent[component.id] ===
                          manufacturer.id
                        const isMostSustainableManufacturer =
                          bestEcoManufacturerByComponent[component.id] ===
                          manufacturer.id

                        return (
                          <div
                            key={manufacturer.id}
                            className={cn(
                              index > 0 ? "border-t border-white/[0.05]" : ""
                            )}
                          >
                            <ManufacturerRow
                              disabled={!isRouteVisible}
                              isFocused={isFocusedManufacturer}
                              isMostSustainable={isMostSustainableManufacturer}
                              isPinned={isPinnedManufacturer}
                              manufacturer={manufacturer}
                              onHoverNode={(nodeId) =>
                                !isRouteVisible
                                  ? onHoverNode(null)
                                  : nodeId
                                    ? onHoverNode(nodeId)
                                    : onHoverNode(component.id)
                              }
                              onSelectNode={(nodeId) => {
                                if (isRouteVisible) {
                                  onSelectNode(nodeId)
                                }
                              }}
                            />
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export const GlobeView = memo(function GlobeView({
  bestEcoManufacturerByComponent,
  className,
  hoveredNodeId,
  onHoverNode,
  onSelectNode,
  onToggleRouteCollapsed,
  onToggleRouteVisible,
  pinnedManufacturerByComponent,
  routeCollapsedByComponent,
  routeVisibleByComponent,
  scenario,
  selectedNodeId,
}: GlobeViewProps) {
  const [isSplitLayout, setIsSplitLayout] = useState(false)
  const globeSplitRef = useRef<HTMLDivElement>(null)
  const {
    defaultLayout: persistedGlobeLayout,
    onLayoutChanged: persistGlobeLayout,
  } = useDefaultLayout({
    id: GLOBE_SPLIT_ID,
    panelIds: [GLOBE_CANVAS_PANEL_ID, GLOBE_ROUTES_PANEL_ID],
    storage: panelLayoutStorage,
  })
  const {
    measure: measureGlobeHandleIndicator,
    active: isGlobeHandleActive,
    lagOffset: globeHandleLagOffset,
    onHandlePointerDownCapture: handleGlobeResizePointerDown,
  } = useResizeMotion(globeSplitRef)
  const visibleRouteCount = scenario.components.filter(
    (component) => routeVisibleByComponent[component.id] ?? true
  ).length
  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 768px)")
    const syncLayoutMode = () => setIsSplitLayout(mediaQuery.matches)

    syncLayoutMode()
    mediaQuery.addEventListener("change", syncLayoutMode)

    return () => {
      mediaQuery.removeEventListener("change", syncLayoutMode)
    }
  }, [])

  const handleGlobeLayoutChange = useCallback(() => {
    measureGlobeHandleIndicator()
  }, [measureGlobeHandleIndicator])

  const handleGlobeLayoutChanged = useCallback(
    (layout: Record<string, number>) => {
      persistGlobeLayout(layout)
      measureGlobeHandleIndicator()
    },
    [measureGlobeHandleIndicator, persistGlobeLayout]
  )

  useEffect(() => {
    if (!isSplitLayout) {
      return
    }

    const frameId = window.requestAnimationFrame(() => {
      measureGlobeHandleIndicator()
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [isSplitLayout, measureGlobeHandleIndicator])

  return (
    <section
      className={cn(
        "panel-surface flex min-h-0 flex-col overflow-hidden rounded-2xl",
        className
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <div
            className="h-2 w-2 rounded-full"
            style={{
              background: "color-mix(in oklab, var(--primary) 76%, white 8%)",
              boxShadow:
                "0 0 9px color-mix(in oklab, var(--primary) 44%, transparent)",
            }}
          />
          <div>
            <h2 className="text-sm font-medium text-white/85">
              Geographic Routes
            </h2>
            <p className="text-[11px] text-white/30">
              {scenario.destination.label},{" "}
              {scenario.destination.location.country}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="dashboard-chip-accent">
            {scenario.stats.siteCount} sites
          </span>
          <Button
            variant="ghost"
            size="xs"
            className="dashboard-control-surface text-white/70 hover:bg-white/[0.05] hover:text-white"
            onClick={() => {
              onHoverNode(null)
              onSelectNode(null)
            }}
          >
            <HugeiconsIcon
              icon={MapsGlobal01Icon}
              strokeWidth={2}
              data-icon="inline-start"
            />
            Overview
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {isSplitLayout ? (
          <div className="flex h-full min-h-0 flex-col px-4 py-4">
            <div ref={globeSplitRef} className="relative min-h-0 flex-1">
              <ResizablePanelGroup
                id={GLOBE_SPLIT_ID}
                className="min-h-0 flex-1"
                defaultLayout={persistedGlobeLayout ?? GLOBE_SPLIT_DEFAULT}
                onLayoutChange={handleGlobeLayoutChange}
                onLayoutChanged={handleGlobeLayoutChanged}
                orientation="vertical"
              >
                <ResizablePanel
                  id={GLOBE_CANVAS_PANEL_ID}
                  className="min-h-0 overflow-visible"
                  minSize="18rem"
                >
                  <div className="h-full min-h-0 overflow-visible pr-1">
                    <LaggedPanelShell
                      edge="trailing"
                      lagOffset={globeHandleLagOffset.y}
                      orientation="horizontal"
                    >
                      <GlobeCanvasSection
                        bestEcoManufacturerByComponent={
                          bestEcoManufacturerByComponent
                        }
                        hoveredNodeId={hoveredNodeId}
                        isSplitLayout={isSplitLayout}
                        onHoverNode={onHoverNode}
                        onSelectNode={onSelectNode}
                        pinnedManufacturerByComponent={
                          pinnedManufacturerByComponent
                        }
                        routeVisibleByComponent={routeVisibleByComponent}
                        scenario={scenario}
                        selectedNodeId={selectedNodeId}
                        visibleRouteCount={visibleRouteCount}
                      />
                    </LaggedPanelShell>
                  </div>
                </ResizablePanel>
                <ResizableHandle
                  className="my-1 h-3 rounded-full bg-transparent after:h-6 aria-[orientation=horizontal]:h-3 aria-[orientation=horizontal]:after:h-6"
                  onPointerDownCapture={handleGlobeResizePointerDown}
                >
                  <LaggedHandleVisual
                    active={isGlobeHandleActive}
                    introDelayMs={320}
                    orientation="horizontal"
                  />
                </ResizableHandle>
                <ResizablePanel
                  id={GLOBE_ROUTES_PANEL_ID}
                  className="min-h-0 overflow-visible"
                  minSize="16rem"
                >
                  <div className="h-full min-h-0 overflow-visible pl-1">
                    <LaggedPanelShell
                      edge="leading"
                      lagOffset={globeHandleLagOffset.y}
                      orientation="horizontal"
                    >
                      <div className="h-full min-h-0 overflow-y-auto">
                        <RoutesList
                          bestEcoManufacturerByComponent={
                            bestEcoManufacturerByComponent
                          }
                          hoveredNodeId={hoveredNodeId}
                          onHoverNode={onHoverNode}
                          onSelectNode={onSelectNode}
                          onToggleRouteCollapsed={onToggleRouteCollapsed}
                          onToggleRouteVisible={onToggleRouteVisible}
                          pinnedManufacturerByComponent={
                            pinnedManufacturerByComponent
                          }
                          routeCollapsedByComponent={routeCollapsedByComponent}
                          routeVisibleByComponent={routeVisibleByComponent}
                          scenario={scenario}
                          selectedNodeId={selectedNodeId}
                        />
                      </div>
                    </LaggedPanelShell>
                  </div>
                </ResizablePanel>
              </ResizablePanelGroup>
            </div>
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto px-4 py-4">
            <GlobeCanvasSection
              bestEcoManufacturerByComponent={bestEcoManufacturerByComponent}
              hoveredNodeId={hoveredNodeId}
              isSplitLayout={isSplitLayout}
              onHoverNode={onHoverNode}
              onSelectNode={onSelectNode}
              pinnedManufacturerByComponent={pinnedManufacturerByComponent}
              routeVisibleByComponent={routeVisibleByComponent}
              scenario={scenario}
              selectedNodeId={selectedNodeId}
              visibleRouteCount={visibleRouteCount}
            />
            <RoutesList
              bestEcoManufacturerByComponent={bestEcoManufacturerByComponent}
              hoveredNodeId={hoveredNodeId}
              onHoverNode={onHoverNode}
              onSelectNode={onSelectNode}
              onToggleRouteCollapsed={onToggleRouteCollapsed}
              onToggleRouteVisible={onToggleRouteVisible}
              pinnedManufacturerByComponent={pinnedManufacturerByComponent}
              routeCollapsedByComponent={routeCollapsedByComponent}
              routeVisibleByComponent={routeVisibleByComponent}
              scenario={scenario}
              selectedNodeId={selectedNodeId}
            />
          </div>
        )}
      </div>
    </section>
  )
})
