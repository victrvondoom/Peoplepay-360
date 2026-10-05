"use client"

import React, { useState, useEffect, useRef, useCallback } from "react"
import {
  Cancel01Icon,
  Factory01Icon,
  Leaf01Icon,
  Maximize02Icon,
  PuzzleIcon,
  ZoomInAreaIcon,
  ZoomOutAreaIcon,
} from "@hugeicons/core-free-icons"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  type SupplyScenario,
  type SupplyScenarioComponentNode,
  type SupplyScenarioGraphEdge,
  type SupplyScenarioGraphNode,
  type SupplyScenarioManufacturerNode,
  type SupplyScenarioSelectableNodeId,
} from "@/lib/supply-chain-scenario"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Data + types
// ---------------------------------------------------------------------------

type GraphNodeState = SupplyScenarioGraphNode
const GRAPH_MIN_SCALE = 0.15
const GRAPH_MAX_SCALE = 4
const MANUFACTURER_REVEAL_SCALE_FACTOR = 0.92
const MANUFACTURER_HIDE_SCALE_FACTOR = 1.02
const MOST_SUSTAINABLE_EDGE = {
  core: "#6EE7B7",
  coreStrong: "#ECFDF5",
  glowSoft: "rgba(52,211,153,0.42)",
  glowStrong: "rgba(52,211,153,0.72)",
  pulseSoft: "rgba(167,243,208,0.34)",
  pulseStrong: "rgba(209,250,229,0.92)",
}

interface GraphViewportSize {
  height: number
  width: number
}

interface GraphVector {
  x: number
  y: number
}

interface ForceSimulationConfig {
  anchorStrengthComponent: number
  anchorStrengthManufacturer: number
  collisionPadding: number
  collisionStrength: number
  damping: number
  linkSpacing: number
  longRangeRepulsion: number
  maxSpeed: number
  readableGap: number
  settleThreshold: number
  springStrength: number
}

interface GraphTransform {
  scale: number
  x: number
  y: number
}

const DEFAULT_GRAPH_TRANSFORM: GraphTransform = { x: 0, y: 0, scale: 1 }

interface FloatingPanelPosition {
  x: number
  y: number
}

interface FloatingPanelDragState {
  offsetX: number
  offsetY: number
  pointerId: number
}

interface ComponentInsight {
  best: SupplyScenarioManufacturerNode | null
  current: SupplyScenarioManufacturerNode | null
  manufacturers: SupplyScenarioManufacturerNode[]
  selected: SupplyScenarioManufacturerNode | null
}

interface SelectedPathEntry {
  component: SupplyScenarioComponentNode
  insight: ComponentInsight
}

interface GraphStatsOverlayMetric {
  emphasized?: boolean
  label: string
  value: string
}

interface GraphStatsOverlayData {
  accentColor: string
  eyebrow: string
  metrics: GraphStatsOverlayMetric[]
  title?: string
  description?: string
}

// ---------------------------------------------------------------------------
// Design helpers
// ---------------------------------------------------------------------------

const CERT_LABELS: Record<string, string> = {
  iso14001: "ISO 14001",
  sbt: "SBT",
  cdp_a: "CDP A-List",
}

function formatCount(value: number) {
  return value.toLocaleString()
}

function formatScore(value: number) {
  return `${Math.round(value)}/100`
}

function formatTco2e(value: number) {
  return `${value.toLocaleString(undefined, {
    maximumFractionDigits: 1,
    minimumFractionDigits: value > 0 && value < 10 ? 1 : 0,
  })} tCO2e`
}

function getEstimatedRouteTotalTco2e(
  manufacturer: SupplyScenarioManufacturerNode
) {
  return (
    manufacturer.manufacturingEmissionsTco2e.q50 +
    manufacturer.transportEmissionsTco2e
  )
}

function getCurrentManufacturer(
  manufacturers: SupplyScenarioManufacturerNode[]
) {
  return (
    manufacturers.find((manufacturer) => manufacturer.isCurrent) ??
    manufacturers[0] ??
    null
  )
}

function getBestEcoManufacturer(
  manufacturers: SupplyScenarioManufacturerNode[],
  bestEcoManufacturerId?: string
) {
  return (
    manufacturers.find(
      (manufacturer) => manufacturer.id === bestEcoManufacturerId
    ) ??
    manufacturers.reduce<SupplyScenarioManufacturerNode | null>(
      (best, manufacturer) => {
        if (!best || manufacturer.ecoScore < best.ecoScore) {
          return manufacturer
        }

        if (
          manufacturer.ecoScore === best.ecoScore &&
          manufacturer.isCurrent &&
          !best.isCurrent
        ) {
          return manufacturer
        }

        return best
      },
      null
    )
  )
}

function getSelectedManufacturer(
  manufacturers: SupplyScenarioManufacturerNode[],
  pinnedManufacturerId?: string
) {
  return (
    manufacturers.find(
      (manufacturer) => manufacturer.id === pinnedManufacturerId
    ) ?? getCurrentManufacturer(manufacturers)
  )
}

function DrawerMetricCard({
  label,
  sublabel,
  value,
}: {
  label: string
  sublabel?: string
  value: string
}) {
  return (
    <div
      className="dashboard-drawer-section rounded-lg p-2.5"
      style={{
        background:
          "linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015) 16%, rgba(255,255,255,0.01) 100%)",
        border: "1px solid rgba(255,255,255,0.06)",
        boxShadow:
          "inset 0 1px 0 rgba(255,255,255,0.035), 0 12px 28px rgba(0,0,0,0.16)",
      }}
    >
      <p className="mb-1 text-[9px] text-white/30">{label}</p>
      <p className="text-sm font-semibold text-white/82">{value}</p>
      {sublabel ? (
        <p className="mt-1 text-[10px] leading-relaxed text-white/30">
          {sublabel}
        </p>
      ) : null}
    </div>
  )
}

function EcoScoreRing({
  score,
  size = 40,
  strokeWidth = 4,
}: {
  score: number
  size?: number
  strokeWidth?: number
}) {
  const cfg = getEcoConfig(score)
  const radius = (size - strokeWidth - 4) / 2
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference * (1 - score / 100)

  return (
    <div
      className="relative shrink-0"
      style={{
        filter: `drop-shadow(0 0 10px color-mix(in oklab, ${cfg.color} 24%, transparent))`,
        height: size,
        width: size,
      }}
    >
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={cfg.color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          style={{
            transition: "stroke-dashoffset 720ms cubic-bezier(0.22,1,0.36,1)",
          }}
        />
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="text-[11px] leading-none font-semibold"
          style={{ color: cfg.color }}
        >
          {Math.round(score)}
        </span>
        <span className="mt-0.5 text-[7px] leading-none text-white/28">
          eco
        </span>
      </div>
    </div>
  )
}

function RouteComparisonCard({
  label,
  manufacturer,
  accent,
  highlighted = false,
}: {
  label: string
  manufacturer: SupplyScenarioManufacturerNode
  accent: string
  highlighted?: boolean
}) {
  return (
    <div
      className="dashboard-drawer-section rounded-lg p-2.5"
      style={{
        background: highlighted
          ? `linear-gradient(180deg, color-mix(in oklab, ${accent} 10%, rgba(7,12,16,0.72)), rgba(7,12,16,0.6))`
          : "rgba(7,12,16,0.58)",
        border: `1px solid ${highlighted ? `color-mix(in oklab, ${accent} 28%, transparent)` : "rgba(255,255,255,0.06)"}`,
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.035)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[8px] font-medium tracking-[0.14em] text-white/26 uppercase">
            {label}
          </p>
          <p className="mt-0.5 truncate text-[13px] font-semibold text-white/84">
            {manufacturer.name}
          </p>
          <p className="text-[10px] leading-relaxed text-white/34">
            {manufacturer.location.city}, {manufacturer.location.country}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {manufacturer.isCurrent ? (
              <span className="dashboard-chip-muted">Current</span>
            ) : null}
            {highlighted ? (
              <span className="dashboard-chip-accent">Selected</span>
            ) : null}
            {manufacturer.certifications.slice(0, 1).map((cert) => (
              <span key={cert} className="dashboard-chip-muted">
                {CERT_LABELS[cert] ?? cert}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 items-start gap-2">
          <EcoScoreRing
            score={manufacturer.ecoScore}
            size={38}
            strokeWidth={3.5}
          />
          <div className="pt-0.5 text-right">
            <p className="text-[8px] text-white/26">Q50</p>
            <p className="text-[13px] font-semibold whitespace-nowrap text-white/84">
              {formatTco2e(getEstimatedRouteTotalTco2e(manufacturer))}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function GraphStatsOverlay({ data }: { data: GraphStatsOverlayData }) {
  return (
    <div
      className="pointer-events-none absolute top-4 left-4 z-20 w-[min(18rem,calc(100%-2rem))] rounded-xl p-2.5"
      style={{
        background: `linear-gradient(180deg, color-mix(in oklab, ${data.accentColor} 8%, rgba(13,16,24,0.95)), rgba(8,10,16,0.91))`,
        border: `1px solid color-mix(in oklab, ${data.accentColor} 24%, rgba(255,255,255,0.08))`,
        boxShadow:
          "inset 0 1px 0 rgba(255,255,255,0.05), 0 20px 40px rgba(0,0,0,0.28)",
        backdropFilter: "blur(18px)",
      }}
    >
      <div
        className="pointer-events-none absolute inset-x-3 top-0 h-px rounded-full"
        style={{
          background: `linear-gradient(90deg, transparent, color-mix(in oklab, ${data.accentColor} 48%, white 10%), transparent)`,
        }}
      />
      <p
        className="text-[8px] font-medium tracking-[0.18em] uppercase"
        style={{
          color: `color-mix(in oklab, ${data.accentColor} 66%, white 18%)`,
        }}
      >
        {data.eyebrow}
      </p>
      {data.title ? (
        <h3 className="mt-1 text-[14px] leading-tight font-semibold text-white/88">
          {data.title}
        </h3>
      ) : null}
      {data.description ? (
        <p className="mt-0.5 text-[10px] leading-snug text-white/44">
          {data.description}
        </p>
      ) : null}

      <div
        className={cn(
          "space-y-1.5",
          data.title || data.description ? "mt-3" : "mt-2"
        )}
      >
        {data.metrics.map((metric) => (
          <div
            key={metric.label}
            className="rounded-lg px-2.5 py-1.5"
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.015))",
              border: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            <div className="flex items-end justify-between gap-3">
              <p className="text-[8px] tracking-[0.12em] text-white/28 uppercase">
                {metric.label}
              </p>
              <p
                className={cn(
                  "leading-none font-semibold whitespace-nowrap text-white/86",
                  metric.emphasized ? "text-[15px]" : "text-[12px]"
                )}
              >
                {metric.value}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function getManufacturerStatusPresentation(isCurrent: boolean) {
  return isCurrent
    ? {
        badgeBackground: "rgba(252,211,77,0.1)",
        badgeBorder: "rgba(252,211,77,0.22)",
        badgeText: "#FCD34D",
        label: "CURRENT",
        pulseClassName: "bg-amber-300",
      }
    : {
        badgeBackground: "rgba(148,163,184,0.1)",
        badgeBorder: "rgba(148,163,184,0.24)",
        badgeText: "#CBD5E1",
        label: "ALTERNATE",
        pulseClassName: "bg-slate-400",
      }
}

function getEcoConfig(score: number) {
  if (score < 40)
    return {
      color: "#34d399",
      glow: "0 0 18px rgba(52,211,153,0.45)",
      ring: "rgba(52,211,153,0.35)",
      bg: "rgba(52,211,153,0.08)",
      panelBg:
        "linear-gradient(180deg, rgba(18,30,27,0.97), rgba(10,20,18,0.95))",
      panelBorder: "rgba(52,211,153,0.32)",
      text: "#34d399",
      label: "Low Impact",
    }
  if (score < 60)
    return {
      color: "#fbbf24",
      glow: "0 0 18px rgba(251,191,36,0.40)",
      ring: "rgba(251,191,36,0.35)",
      bg: "rgba(251,191,36,0.08)",
      panelBg:
        "linear-gradient(180deg, rgba(33,26,14,0.98), rgba(22,18,10,0.96))",
      panelBorder: "rgba(251,191,36,0.32)",
      text: "#fbbf24",
      label: "Moderate",
    }
  return {
    color: "#f87171",
    glow: "0 0 18px rgba(248,113,113,0.40)",
    ring: "rgba(248,113,113,0.35)",
    bg: "rgba(248,113,113,0.08)",
    panelBg:
      "linear-gradient(180deg, rgba(34,16,18,0.98), rgba(24,10,12,0.96))",
    panelBorder: "rgba(248,113,113,0.32)",
    text: "#f87171",
    label: "High Impact",
  }
}

function getNodeSize(node: GraphNodeState) {
  const d = node.data
  if (d.kind === "product") return { w: 136, h: 100 }
  if (d.kind === "manufacturer") return { w: 252, h: 120 }
  return { w: 168, h: 68 }
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function getNodeMobility(node: GraphNodeState) {
  if (node.data.kind === "product") {
    return 0
  }

  if (node.data.kind === "component") {
    return 0.5
  }

  return 1
}

function getNodeCenter(
  node: GraphNodeState,
  position: { x: number; y: number } = node.position
) {
  const { w, h } = getNodeSize(node)

  return {
    x: position.x + w / 2,
    y: position.y + h / 2,
  }
}

function getNodeRadius(node: GraphNodeState) {
  const { w, h } = getNodeSize(node)
  return Math.hypot(w / 2, h / 2)
}

function getGraphCrowdingScore(
  nodes: GraphNodeState[],
  viewport: GraphViewportSize | null
) {
  const width = viewport?.width ?? 1200
  const height = viewport?.height ?? 900
  const viewportArea = Math.max(width * height, 1)
  const totalNodeArea = nodes.reduce((sum, node) => {
    const { w, h } = getNodeSize(node)
    return sum + w * h
  }, 0)
  const areaPressure = clamp(totalNodeArea / (viewportArea * 0.58), 0, 1.4)
  const countPressure = clamp((nodes.length - 6) / 14, 0, 1.2)

  return clamp(areaPressure * 0.62 + countPressure * 0.58, 0, 1.4)
}

function getLayoutConfig(
  viewport: GraphViewportSize | null,
  nodes: GraphNodeState[]
) {
  const width = viewport?.width ?? 1200
  const height = viewport?.height ?? 900
  const compactness = clamp((960 - Math.min(width, height)) / 360, 0, 1)
  const crowding = getGraphCrowdingScore(nodes, viewport)

  return {
    componentPull: clamp(
      0.56 - compactness * 0.09 - crowding * 0.08,
      0.28,
      0.58
    ),
    fitPaddingX: 112 - compactness * 34 + crowding * 30,
    fitPaddingY: 96 - compactness * 28 + crowding * 24,
    fitZoomBoost: clamp(
      1.05 + compactness * 0.12 - crowding * 0.18,
      0.78,
      1.18
    ),
    manufacturerPull: clamp(
      0.44 - compactness * 0.12 - crowding * 0.1,
      0.18,
      0.46
    ),
    minFitScale: clamp(0.52 - crowding * 0.16, 0.3, 0.52),
    paddingX: 26 - compactness * 8 + crowding * 24,
    paddingY: 24 - compactness * 7 + crowding * 20,
  }
}

function clonePositionsMap(nodes: GraphNodeState[]) {
  return new Map(nodes.map((node) => [node.id, { ...node.position }]))
}

function buildCompactGraphNodes(
  nodes: GraphNodeState[],
  viewport: GraphViewportSize | null
) {
  const productNode = nodes.find((node) => node.data.kind === "product")

  if (!productNode) {
    return nodes
  }

  const config = getLayoutConfig(viewport, nodes)
  const crowding = getGraphCrowdingScore(nodes, viewport)
  const anchorPositions = new Map<string, { x: number; y: number }>()
  const productAnchor = {
    x: productNode.position.x,
    y: productNode.position.y,
  }
  const productCenter = getNodeCenter(productNode, productAnchor)
  const productSize = getNodeSize(productNode)
  const components = nodes
    .filter((node) => node.data.kind === "component")
    .sort((left, right) => {
      const leftAngle = Math.atan2(
        left.position.y - productAnchor.y,
        left.position.x - productAnchor.x
      )
      const rightAngle = Math.atan2(
        right.position.y - productAnchor.y,
        right.position.x - productAnchor.x
      )
      return leftAngle - rightAngle
    })
  const manufacturersByComponent = new Map<string, GraphNodeState[]>()

  nodes.forEach((node) => {
    if (node.data.kind !== "manufacturer") {
      return
    }

    const bucket = manufacturersByComponent.get(node.data.componentId)
    if (bucket) {
      bucket.push(node)
      return
    }

    manufacturersByComponent.set(node.data.componentId, [node])
  })

  manufacturersByComponent.forEach((manufacturerNodes) => {
    manufacturerNodes.sort((left, right) => {
      if (
        left.data.kind !== "manufacturer" ||
        right.data.kind !== "manufacturer"
      ) {
        return 0
      }

      const statusDelta =
        Number(right.data.isCurrent) - Number(left.data.isCurrent)
      if (statusDelta !== 0) {
        return statusDelta
      }

      return left.data.ecoScore - right.data.ecoScore
    })
  })

  const componentCount = Math.max(components.length, 1)
  const width = viewport?.width ?? 1200
  const height = viewport?.height ?? 900
  const viewportScale = clamp(Math.min(width, height) / 980, 0.82, 1.12)
  const componentRingRadius =
    (138 +
      componentCount * 24 +
      crowding * 56 +
      Math.max(productSize.w, productSize.h) * 0.08) *
    viewportScale
  const manufacturerBaseRadius =
    componentRingRadius +
    (118 + crowding * 62 + componentCount * 8) * viewportScale
  const sectorAngle = (Math.PI * 2) / componentCount
  const manufacturerAngleStep = clamp(0.24 - crowding * 0.05, 0.14, 0.26)
  const maxSpread = clamp(sectorAngle * 0.86, 0.48, 1.24)

  anchorPositions.set(productNode.id, productAnchor)

  components.forEach((component, componentIndex) => {
    const componentAngle =
      (componentIndex / componentCount) * Math.PI * 2 - Math.PI / 2
    const componentNodeSize = getNodeSize(component)
    const componentCenter = {
      x: productCenter.x + Math.cos(componentAngle) * componentRingRadius,
      y: productCenter.y + Math.sin(componentAngle) * componentRingRadius,
    }
    const componentAnchor = {
      x: componentCenter.x - componentNodeSize.w / 2,
      y: componentCenter.y - componentNodeSize.h / 2,
    }
    const manufacturers = manufacturersByComponent.get(component.id) ?? []
    const clampedSpread = Math.min(
      maxSpread,
      manufacturerAngleStep * Math.max(0, manufacturers.length - 1)
    )

    anchorPositions.set(component.id, componentAnchor)

    manufacturers.forEach((manufacturer, manufacturerIndex) => {
      const manufacturerSize = getNodeSize(manufacturer)
      const localOffsetIndex =
        manufacturerIndex - (manufacturers.length - 1) / 2
      const localAngle =
        manufacturers.length <= 1
          ? componentAngle
          : componentAngle +
            (manufacturers.length > 1
              ? (localOffsetIndex / Math.max(manufacturers.length - 1, 1)) *
                clampedSpread
              : 0)
      const radialJitter =
        Math.abs(localOffsetIndex) * (14 + crowding * 10) * viewportScale
      const manufacturerRadius = manufacturerBaseRadius + radialJitter
      const manufacturerCenter = {
        x: productCenter.x + Math.cos(localAngle) * manufacturerRadius,
        y: productCenter.y + Math.sin(localAngle) * manufacturerRadius,
      }

      anchorPositions.set(manufacturer.id, {
        x: manufacturerCenter.x - manufacturerSize.w / 2,
        y: manufacturerCenter.y - manufacturerSize.h / 2,
      })
    })
  })

  const positionedNodes = nodes.map((node) => ({
    ...node,
    position: anchorPositions.get(node.id) ?? node.position,
  }))

  return relaxNodeLayout(positionedNodes, anchorPositions, config)
}

function relaxNodeLayout(
  nodes: GraphNodeState[],
  anchors: Map<string, { x: number; y: number }>,
  config: ReturnType<typeof getLayoutConfig>
) {
  const positions = clonePositionsMap(nodes)

  for (let iteration = 0; iteration < 20; iteration += 1) {
    let totalShift = 0

    for (let index = 0; index < nodes.length; index += 1) {
      for (
        let otherIndex = index + 1;
        otherIndex < nodes.length;
        otherIndex += 1
      ) {
        const node = nodes[index]
        const otherNode = nodes[otherIndex]
        const nodePosition = positions.get(node.id) ?? node.position
        const otherPosition = positions.get(otherNode.id) ?? otherNode.position
        const nodeCenter = getNodeCenter(node, nodePosition)
        const otherCenter = getNodeCenter(otherNode, otherPosition)
        const { w: nodeWidth, h: nodeHeight } = getNodeSize(node)
        const { w: otherWidth, h: otherHeight } = getNodeSize(otherNode)
        const deltaX = nodeCenter.x - otherCenter.x
        const deltaY = nodeCenter.y - otherCenter.y
        const overlapX =
          nodeWidth / 2 + otherWidth / 2 + config.paddingX - Math.abs(deltaX)
        const overlapY =
          nodeHeight / 2 + otherHeight / 2 + config.paddingY - Math.abs(deltaY)

        if (overlapX <= 0 || overlapY <= 0) {
          continue
        }

        const nodeMobility = getNodeMobility(node)
        const otherMobility = getNodeMobility(otherNode)
        const totalMobility = nodeMobility + otherMobility || 1
        const nodeAnchor = anchors.get(node.id) ?? node.position
        const otherAnchor = anchors.get(otherNode.id) ?? otherNode.position

        if (overlapX < overlapY) {
          const direction =
            deltaX === 0
              ? nodeAnchor.x >= otherAnchor.x
                ? 1
                : -1
              : Math.sign(deltaX)
          const shift = overlapX + 0.5

          if (nodeMobility > 0) {
            nodePosition.x += direction * shift * (nodeMobility / totalMobility)
          }

          if (otherMobility > 0) {
            otherPosition.x -=
              direction * shift * (otherMobility / totalMobility)
          }

          totalShift += shift
        } else {
          const direction =
            deltaY === 0
              ? nodeAnchor.y >= otherAnchor.y
                ? 1
                : -1
              : Math.sign(deltaY)
          const shift = overlapY + 0.5

          if (nodeMobility > 0) {
            nodePosition.y += direction * shift * (nodeMobility / totalMobility)
          }

          if (otherMobility > 0) {
            otherPosition.y -=
              direction * shift * (otherMobility / totalMobility)
          }

          totalShift += shift
        }

        positions.set(node.id, nodePosition)
        positions.set(otherNode.id, otherPosition)
      }
    }

    nodes.forEach((node) => {
      const mobility = getNodeMobility(node)

      if (mobility === 0) {
        return
      }

      const anchor = anchors.get(node.id)
      const position = positions.get(node.id) ?? node.position

      if (!anchor) {
        return
      }

      const spring = node.data.kind === "component" ? 0.1 : 0.06

      position.x += (anchor.x - position.x) * spring
      position.y += (anchor.y - position.y) * spring
      positions.set(node.id, position)
    })

    if (totalShift < 0.5) {
      break
    }
  }

  return nodes.map((node) => ({
    ...node,
    position: positions.get(node.id) ?? node.position,
  }))
}

function getGraphBounds(nodes: GraphNodeState[]) {
  if (nodes.length === 0) {
    return {
      bottom: 0,
      centerX: 0,
      centerY: 0,
      height: 1,
      left: 0,
      right: 0,
      top: 0,
      width: 1,
    }
  }

  let left = Number.POSITIVE_INFINITY
  let top = Number.POSITIVE_INFINITY
  let right = Number.NEGATIVE_INFINITY
  let bottom = Number.NEGATIVE_INFINITY

  nodes.forEach((node) => {
    const { w, h } = getNodeSize(node)

    left = Math.min(left, node.position.x)
    top = Math.min(top, node.position.y)
    right = Math.max(right, node.position.x + w)
    bottom = Math.max(bottom, node.position.y + h)
  })

  return {
    bottom,
    centerX: (left + right) / 2,
    centerY: (top + bottom) / 2,
    height: Math.max(1, bottom - top),
    left,
    right,
    top,
    width: Math.max(1, right - left),
  }
}

function getFitTransform(
  nodes: GraphNodeState[],
  viewport: GraphViewportSize | null
) {
  const width = viewport?.width ?? 0
  const height = viewport?.height ?? 0

  if (!width || !height) {
    return null
  }

  const config = getLayoutConfig(viewport, nodes)
  const bounds = getGraphBounds(nodes)
  const availableWidth = Math.max(1, width - config.fitPaddingX * 2)
  const availableHeight = Math.max(1, height - config.fitPaddingY * 2)
  const fittedScale = Math.min(
    availableWidth / bounds.width,
    availableHeight / bounds.height
  )
  const scale = clamp(
    fittedScale * config.fitZoomBoost,
    config.minFitScale,
    1.28
  )

  return {
    scale,
    x: width / 2 - bounds.centerX * scale,
    y: height / 2 - bounds.centerY * scale,
  }
}

function getScaledTransformAtPoint(
  transform: GraphTransform,
  pointer: { x: number; y: number },
  nextScale: number
) {
  const worldX = (pointer.x - transform.x) / transform.scale
  const worldY = (pointer.y - transform.y) / transform.scale

  return {
    scale: nextScale,
    x: pointer.x - worldX * nextScale,
    y: pointer.y - worldY * nextScale,
  }
}

function createVisibleComponentIdSet(
  scenario: SupplyScenario,
  routeVisibleByComponent: Record<string, boolean>
) {
  return new Set(
    scenario.components
      .filter((component) => routeVisibleByComponent[component.id] ?? true)
      .map((component) => component.id)
  )
}

function isGraphNodeVisible(
  node: GraphNodeState,
  visibleComponentIds: Set<string>,
  manufacturerLayerVisible: boolean
) {
  if (node.data.kind === "product") {
    return true
  }

  if (node.data.kind === "component") {
    return visibleComponentIds.has(node.id)
  }

  return (
    manufacturerLayerVisible && visibleComponentIds.has(node.data.componentId)
  )
}

function filterGraphNodes(
  nodes: GraphNodeState[],
  visibleComponentIds: Set<string>,
  manufacturerLayerVisible: boolean
) {
  return nodes.filter((node) =>
    isGraphNodeVisible(node, visibleComponentIds, manufacturerLayerVisible)
  )
}

function filterGraphEdges(
  edges: SupplyScenarioGraphEdge[],
  renderedNodeIds: Set<string>
) {
  return edges.filter(
    (edge) =>
      renderedNodeIds.has(edge.sourceId) && renderedNodeIds.has(edge.targetId)
  )
}

function snapGraphValue(value: number, increment = 0.5) {
  return Math.round(value / increment) * increment
}

function snapGraphPosition(position: { x: number; y: number }) {
  return {
    x: snapGraphValue(position.x),
    y: snapGraphValue(position.y),
  }
}

function createVelocityMap(nodes: GraphNodeState[]) {
  return new Map(nodes.map((node) => [node.id, { x: 0, y: 0 }]))
}

function getInteractiveMobility(
  node: GraphNodeState,
  draggedNodeId: string | null
) {
  if (node.id === draggedNodeId) {
    return 0
  }

  return getNodeMobility(node)
}

function getForceSimulationConfig(
  nodes: GraphNodeState[],
  edges: SupplyScenarioGraphEdge[],
  viewport: GraphViewportSize | null
): ForceSimulationConfig {
  const crowding = getGraphCrowdingScore(nodes, viewport)
  const edgePressure = clamp(
    (edges.length - Math.max(0, nodes.length - 1)) / Math.max(nodes.length, 1),
    0,
    1.2
  )
  const density = clamp(crowding + edgePressure * 0.32, 0, 1.7)

  return {
    anchorStrengthComponent: clamp(0.016 - density * 0.003, 0.008, 0.016),
    anchorStrengthManufacturer: clamp(0.011 - density * 0.003, 0.005, 0.011),
    collisionPadding: 20 + density * 18,
    collisionStrength: 0.024 + density * 0.01,
    damping: clamp(0.82 - density * 0.03, 0.74, 0.82),
    linkSpacing: 30 + density * 24,
    longRangeRepulsion: 0.0028 + density * 0.0014,
    maxSpeed: 26 + density * 12,
    readableGap: 34 + density * 44,
    settleThreshold: 0.18 + density * 0.06,
    springStrength: clamp(0.0052 - density * 0.0007, 0.0036, 0.0052),
  }
}

function applyDistributedForce(
  forces: Map<string, GraphVector>,
  nodeId: string,
  otherNodeId: string,
  forceX: number,
  forceY: number,
  nodeMobility: number,
  otherMobility: number
) {
  const totalMobility = nodeMobility + otherMobility

  if (totalMobility <= 0) {
    return
  }

  if (nodeMobility > 0) {
    const nodeForce = forces.get(nodeId)

    if (nodeForce) {
      nodeForce.x += forceX * (nodeMobility / totalMobility)
      nodeForce.y += forceY * (nodeMobility / totalMobility)
    }
  }

  if (otherMobility > 0) {
    const otherForce = forces.get(otherNodeId)

    if (otherForce) {
      otherForce.x -= forceX * (otherMobility / totalMobility)
      otherForce.y -= forceY * (otherMobility / totalMobility)
    }
  }
}

function getDesiredEdgeDistance(
  sourceNode: GraphNodeState,
  targetNode: GraphNodeState,
  config: ForceSimulationConfig
) {
  const base =
    getNodeRadius(sourceNode) +
    getNodeRadius(targetNode) +
    config.collisionPadding +
    config.linkSpacing

  if (
    sourceNode.data.kind === "product" ||
    targetNode.data.kind === "product"
  ) {
    return base + 40
  }

  if (
    sourceNode.data.kind === "component" ||
    targetNode.data.kind === "component"
  ) {
    return base + 12
  }

  return base
}

function runForceSimulationStep({
  anchors,
  draggedNodeId,
  dtScale,
  edges,
  isResizeActive,
  nodes,
  velocities,
  viewport,
}: {
  anchors: Map<string, { x: number; y: number }>
  draggedNodeId: string | null
  dtScale: number
  edges: SupplyScenarioGraphEdge[]
  isResizeActive: boolean
  nodes: GraphNodeState[]
  velocities: Map<string, GraphVector>
  viewport: GraphViewportSize | null
}) {
  const baseConfig = getForceSimulationConfig(nodes, edges, viewport)
  const interactionDamping = draggedNodeId ? 0.72 : isResizeActive ? 0.34 : 1
  const config = {
    ...baseConfig,
    anchorStrengthComponent:
      baseConfig.anchorStrengthComponent * interactionDamping,
    anchorStrengthManufacturer:
      baseConfig.anchorStrengthManufacturer * interactionDamping,
    collisionStrength: baseConfig.collisionStrength * interactionDamping,
    damping: clamp(
      isResizeActive ? baseConfig.damping * 0.92 : baseConfig.damping,
      0.78,
      0.94
    ),
    longRangeRepulsion: baseConfig.longRangeRepulsion * interactionDamping,
    maxSpeed: isResizeActive ? baseConfig.maxSpeed * 0.45 : baseConfig.maxSpeed,
    springStrength: baseConfig.springStrength * interactionDamping,
  }
  const forces = new Map(nodes.map((node) => [node.id, { x: 0, y: 0 }]))
  const nodeById = new Map(nodes.map((node) => [node.id, node] as const))

  for (let index = 0; index < nodes.length; index += 1) {
    for (
      let otherIndex = index + 1;
      otherIndex < nodes.length;
      otherIndex += 1
    ) {
      const node = nodes[index]
      const otherNode = nodes[otherIndex]
      const nodeCenter = getNodeCenter(node)
      const otherCenter = getNodeCenter(otherNode)
      let deltaX = nodeCenter.x - otherCenter.x
      let deltaY = nodeCenter.y - otherCenter.y

      if (deltaX === 0 && deltaY === 0) {
        deltaX = (otherIndex - index || 1) * 0.01
        deltaY = 0.01
      }

      const distance = Math.hypot(deltaX, deltaY) || 0.0001
      const nodeMobility = getInteractiveMobility(node, draggedNodeId)
      const otherMobility = getInteractiveMobility(otherNode, draggedNodeId)
      const preferredDistance =
        getNodeRadius(node) + getNodeRadius(otherNode) + config.collisionPadding
      const readableDistance = preferredDistance + config.readableGap

      if (distance >= readableDistance) {
        continue
      }

      const normalX = deltaX / distance
      const normalY = deltaY / distance
      const push =
        distance < preferredDistance
          ? (preferredDistance - distance) * config.collisionStrength
          : ((readableDistance - distance) / readableDistance) ** 2 *
            config.longRangeRepulsion *
            readableDistance

      applyDistributedForce(
        forces,
        node.id,
        otherNode.id,
        normalX * push,
        normalY * push,
        nodeMobility,
        otherMobility
      )
    }
  }

  for (const edge of edges) {
    const sourceNode = nodeById.get(edge.sourceId)
    const targetNode = nodeById.get(edge.targetId)

    if (!sourceNode || !targetNode) {
      continue
    }

    const sourceCenter = getNodeCenter(sourceNode)
    const targetCenter = getNodeCenter(targetNode)
    const deltaX = targetCenter.x - sourceCenter.x
    const deltaY = targetCenter.y - sourceCenter.y
    const distance = Math.hypot(deltaX, deltaY) || 0.0001
    const nodeMobility = getInteractiveMobility(sourceNode, draggedNodeId)
    const otherMobility = getInteractiveMobility(targetNode, draggedNodeId)
    const desiredDistance = getDesiredEdgeDistance(
      sourceNode,
      targetNode,
      config
    )
    const stretch = distance - desiredDistance

    if (Math.abs(stretch) < 1) {
      continue
    }

    const normalX = deltaX / distance
    const normalY = deltaY / distance
    const pull = stretch * config.springStrength

    applyDistributedForce(
      forces,
      sourceNode.id,
      targetNode.id,
      normalX * pull,
      normalY * pull,
      nodeMobility,
      otherMobility
    )
  }

  nodes.forEach((node) => {
    const mobility = getInteractiveMobility(node, draggedNodeId)
    const anchor = anchors.get(node.id)
    const force = forces.get(node.id)

    if (!anchor || !force || mobility <= 0) {
      return
    }

    const strength =
      node.data.kind === "component"
        ? config.anchorStrengthComponent
        : config.anchorStrengthManufacturer

    force.x += (anchor.x - node.position.x) * strength
    force.y += (anchor.y - node.position.y) * strength
  })

  let movingNodeCount = 0
  let totalSpeed = 0

  const nextNodes = nodes.map((node) => {
    const anchor = anchors.get(node.id) ?? node.position
    const mobility = getInteractiveMobility(node, draggedNodeId)

    if (node.id === draggedNodeId) {
      velocities.set(node.id, { x: 0, y: 0 })
      return {
        ...node,
        position: { ...node.position },
      }
    }

    if (node.data.kind === "product") {
      velocities.set(node.id, { x: 0, y: 0 })
      return { ...node, position: { ...anchor } }
    }

    if (mobility <= 0) {
      velocities.set(node.id, { x: 0, y: 0 })
      return node
    }

    const velocity = velocities.get(node.id) ?? { x: 0, y: 0 }
    const force = forces.get(node.id) ?? { x: 0, y: 0 }
    const nextVelocity = {
      x: (velocity.x + force.x * dtScale) * config.damping,
      y: (velocity.y + force.y * dtScale) * config.damping,
    }
    const speed = Math.hypot(nextVelocity.x, nextVelocity.y)

    if (speed > config.maxSpeed) {
      const speedScale = config.maxSpeed / speed
      nextVelocity.x *= speedScale
      nextVelocity.y *= speedScale
    }

    velocities.set(node.id, nextVelocity)
    totalSpeed += Math.hypot(nextVelocity.x, nextVelocity.y)
    movingNodeCount += 1

    return {
      ...node,
      position: {
        x: node.position.x + nextVelocity.x * dtScale,
        y: node.position.y + nextVelocity.y * dtScale,
      },
    }
  })

  return {
    meanSpeed: totalSpeed / Math.max(movingNodeCount, 1),
    nodes: nextNodes,
    settleThreshold: config.settleThreshold,
  }
}

// Intersection of a ray from node centre with its boundary
function getIntersection(node: GraphNodeState, dx: number, dy: number) {
  const { w, h } = getNodeSize(node)
  const cx = node.position.x + w / 2
  const cy = node.position.y + h / 2
  if (dx === 0 && dy === 0) return { x: cx, y: cy }
  const pad = 10
  const d = node.data
  if (d.kind === "product") {
    const r = w / 2 + pad
    const dist = Math.hypot(dx, dy)
    return { x: cx + (dx / dist) * r, y: cy + (dy / dist) * r }
  }
  const hw = w / 2 + pad
  const hh = h / 2 + pad
  const sx = dx !== 0 ? Math.abs(hw / dx) : Infinity
  const sy = dy !== 0 ? Math.abs(hh / dy) : Infinity
  const s = Math.min(sx, sy)
  return { x: cx + dx * s, y: cy + dy * s }
}

interface GraphTransformAnimation {
  durationMs: number
  startAt: number | null
  startTransform: GraphTransform
  targetTransform: GraphTransform
}

interface GraphInertiaState {
  x: number
  y: number
}

interface GraphEdgeElementRefs {
  ambient: SVGPathElement | null
  flow: SVGPathElement | null
  glow: SVGPathElement | null
  hit: SVGPathElement | null
  main: SVGPathElement | null
  selectedGlow: SVGPathElement | null
}

interface GraphRenderRefs {
  edges: Map<string, GraphEdgeElementRefs>
  grid: HTMLDivElement | null
  nodes: Map<string, HTMLDivElement>
  world: HTMLDivElement | null
  zoomLabel: HTMLSpanElement | null
}

type GraphEdgeElementPart = keyof GraphEdgeElementRefs

type GraphPointerState =
  | {
      currentClientX: number
      currentClientY: number
      lastClientX: number
      lastClientY: number
      lastTs: number
      moved: boolean
      originTransform: GraphTransform
      pointerId: number
      startClientX: number
      startClientY: number
      type: "canvas"
      velocityX: number
      velocityY: number
    }
  | {
      currentClientX: number
      currentClientY: number
      moved: boolean
      nodeId: string
      originPosition: { x: number; y: number }
      pointerId: number
      startClientX: number
      startClientY: number
      type: "node"
    }

interface GraphSceneState {
  dragState: GraphPointerState | null
  hasManualCameraInteraction: boolean
  inertia: GraphInertiaState | null
  interactionMode: boolean
  isResizeActive: boolean
  transform: GraphTransform
  transformAnimation: GraphTransformAnimation | null
}

function createEdgeElementRefs(): GraphEdgeElementRefs {
  return {
    ambient: null,
    flow: null,
    glow: null,
    hit: null,
    main: null,
    selectedGlow: null,
  }
}

function createRenderRefs(): GraphRenderRefs {
  return {
    edges: new Map(),
    grid: null,
    nodes: new Map(),
    world: null,
    zoomLabel: null,
  }
}

function createSceneState(): GraphSceneState {
  return {
    dragState: null,
    hasManualCameraInteraction: false,
    inertia: null,
    interactionMode: false,
    isResizeActive: false,
    transform: { ...DEFAULT_GRAPH_TRANSFORM },
    transformAnimation: null,
  }
}

function createNodePositionMap(nodes: GraphNodeState[]) {
  return new Map(nodes.map((node) => [node.id, { ...node.position }] as const))
}

function buildSceneNodes(
  nodes: GraphNodeState[],
  positions: Map<string, { x: number; y: number }>
) {
  return nodes.map((node) => ({
    ...node,
    position: positions.get(node.id) ?? node.position,
  }))
}

function syncNodePositionMap(
  positions: Map<string, { x: number; y: number }>,
  nodes: GraphNodeState[]
) {
  let changed = false

  nodes.forEach((node) => {
    const previousPosition = positions.get(node.id)

    if (
      previousPosition &&
      Math.abs(previousPosition.x - node.position.x) < 0.001 &&
      Math.abs(previousPosition.y - node.position.y) < 0.001
    ) {
      return
    }

    positions.set(node.id, { ...node.position })
    changed = true
  })

  return changed
}

function stabilizeSceneNodes(
  nodes: GraphNodeState[],
  positions: Map<string, { x: number; y: number }>,
  velocities: Map<string, GraphVector>
) {
  let changed = false

  nodes.forEach((node) => {
    velocities.set(node.id, { x: 0, y: 0 })

    const currentPosition = positions.get(node.id) ?? node.position
    const nextPosition = snapGraphPosition(currentPosition)

    if (
      Math.abs(currentPosition.x - nextPosition.x) < 0.001 &&
      Math.abs(currentPosition.y - nextPosition.y) < 0.001
    ) {
      return
    }

    positions.set(node.id, nextPosition)
    changed = true
  })

  return changed
}

function getPaintedTransform(transform: GraphTransform) {
  return {
    scale: Math.round(transform.scale * 1000) / 1000,
    x: snapGraphValue(transform.x),
    y: snapGraphValue(transform.y),
  }
}

function hasMeaningfulTransformDelta(
  currentTransform: GraphTransform,
  nextTransform: GraphTransform
) {
  return (
    Math.abs(currentTransform.scale - nextTransform.scale) >= 0.001 ||
    Math.abs(currentTransform.x - nextTransform.x) >= 0.5 ||
    Math.abs(currentTransform.y - nextTransform.y) >= 0.5
  )
}

function clampTransformToViewport(
  transform: GraphTransform,
  nodes: GraphNodeState[],
  viewport: GraphViewportSize | null
) {
  const width = viewport?.width ?? 0
  const height = viewport?.height ?? 0

  if (!width || !height || nodes.length === 0) {
    return null
  }

  const bounds = getGraphBounds(nodes)
  const paddingX = Math.min(96, width * 0.16)
  const paddingY = Math.min(84, height * 0.18)
  const minX = width - paddingX - bounds.right * transform.scale
  const maxX = paddingX - bounds.left * transform.scale
  const minY = height - paddingY - bounds.bottom * transform.scale
  const maxY = paddingY - bounds.top * transform.scale

  return {
    ...transform,
    x: minX > maxX ? (minX + maxX) / 2 : clamp(transform.x, minX, maxX),
    y: minY > maxY ? (minY + maxY) / 2 : clamp(transform.y, minY, maxY),
  }
}

function getEdgePath(sourceNode: GraphNodeState, targetNode: GraphNodeState) {
  const { w: sw, h: sh } = getNodeSize(sourceNode)
  const { w: tw, h: th } = getNodeSize(targetNode)
  const sc = {
    x: sourceNode.position.x + sw / 2,
    y: sourceNode.position.y + sh / 2,
  }
  const tc = {
    x: targetNode.position.x + tw / 2,
    y: targetNode.position.y + th / 2,
  }
  const dx = tc.x - sc.x
  const dy = tc.y - sc.y

  if (Math.hypot(dx, dy) < 10) {
    return null
  }

  const start = getIntersection(sourceNode, dx, dy)
  const end = getIntersection(targetNode, -dx, -dy)

  return `M ${snapGraphValue(start.x)} ${snapGraphValue(start.y)} L ${snapGraphValue(end.x)} ${snapGraphValue(end.y)}`
}

interface EdgeProps {
  drawDelay: number
  edgeId: string
  flowActive: boolean
  hovered: boolean
  initialPath: string | null
  interactionMode: boolean
  /** Flow dashes animate every frame, so they live in their own SVG layer to keep blurred glows from repainting. */
  layer: "base" | "flow"
  mostSustainable: boolean
  onHoverEnd: () => void
  onHoverStart: () => void
  registerElement: (
    edgeId: string,
    part: GraphEdgeElementPart,
    element: SVGPathElement | null
  ) => void
  selected: boolean
}

const ConnectionEdge = React.memo(
  function ConnectionEdge({
    drawDelay,
    edgeId,
    flowActive,
    hovered,
    initialPath,
    interactionMode,
    layer,
    mostSustainable,
    onHoverEnd,
    onHoverStart,
    registerElement,
    selected,
  }: EdgeProps) {
    const path = initialPath ?? "M 0 0 L 0 0"

    if (layer === "flow") {
      const ambientStroke = mostSustainable
        ? "rgba(167,243,208,0.18)"
        : "rgba(226,220,235,0.14)"
      const flowStroke = mostSustainable
        ? selected
          ? MOST_SUSTAINABLE_EDGE.pulseStrong
          : "rgba(167,243,208,0.72)"
        : selected
          ? "rgba(255,250,255,0.94)"
          : "rgba(233,224,255,0.48)"

      if (interactionMode) {
        return null
      }

      return (
        <g style={{ display: initialPath ? undefined : "none" }}>
          <path
            ref={(element) => registerElement(edgeId, "ambient", element)}
            d={path}
            fill="none"
            stroke={ambientStroke}
            strokeWidth={0.9}
            strokeDasharray="7 30"
            className="edge-flow-ambient"
          />
          {selected || flowActive || mostSustainable ? (
            <path
              ref={(element) => registerElement(edgeId, "flow", element)}
              d={path}
              fill="none"
              stroke={flowStroke}
              strokeWidth={
                mostSustainable ? (selected ? 1.9 : 1.35) : selected ? 1.8 : 1.2
              }
              strokeDasharray={
                selected ? "5 14" : mostSustainable ? "6 16" : "6 18"
              }
              className={
                selected || mostSustainable ? "edge-flow" : "edge-flow-subtle"
              }
            />
          ) : null}
        </g>
      )
    }

    const markerId = mostSustainable
      ? selected
        ? "arrow-eco-sel"
        : hovered
          ? "arrow-eco-hov"
          : "arrow-eco-def"
      : selected
        ? "arrow-sel"
        : hovered
          ? "arrow-hov"
          : "arrow-def"
    const mainStroke = mostSustainable
      ? selected
        ? MOST_SUSTAINABLE_EDGE.coreStrong
        : hovered
          ? "rgba(167,243,208,0.98)"
          : "rgba(110,231,183,0.88)"
      : selected
        ? "#F1E9FF"
        : hovered
          ? "rgba(228,219,250,0.88)"
          : "rgba(214,207,224,0.68)"

    return (
      <g
        className="pointer-events-auto"
        onPointerEnter={onHoverStart}
        onPointerLeave={onHoverEnd}
        style={{ display: initialPath ? undefined : "none" }}
      >
        {/* Wide invisible hit area */}
        <path
          ref={(element) => registerElement(edgeId, "hit", element)}
          d={path}
          fill="none"
          stroke="transparent"
          strokeWidth={20}
          className="cursor-pointer"
        />
        {mostSustainable ? (
          <path
            ref={(element) => registerElement(edgeId, "glow", element)}
            d={path}
            fill="none"
            stroke={
              selected || hovered
                ? MOST_SUSTAINABLE_EDGE.glowStrong
                : MOST_SUSTAINABLE_EDGE.glowSoft
            }
            strokeWidth={
              interactionMode
                ? selected
                  ? 10
                  : hovered
                    ? 8
                    : 7
                : selected
                  ? 16
                  : hovered
                    ? 13
                    : 11
            }
            style={{
              filter: interactionMode
                ? selected
                  ? "blur(5px)"
                  : "blur(4px)"
                : selected
                  ? "blur(10px)"
                  : "blur(8px)",
            }}
          />
        ) : null}
        {/* Glow layer when active */}
        {(selected || hovered) && (
          <path
            ref={(element) => registerElement(edgeId, "selectedGlow", element)}
            d={path}
            fill="none"
            stroke={
              selected ? "rgba(233,224,255,0.34)" : "rgba(226,220,235,0.16)"
            }
            strokeWidth={
              interactionMode ? (selected ? 6 : 4) : selected ? 9 : 6
            }
            style={{
              filter: interactionMode
                ? selected
                  ? "blur(4px)"
                  : "blur(2px)"
                : selected
                  ? "blur(6px)"
                  : "blur(3px)",
            }}
          />
        )}
        {/* Main stroke */}
        <path
          ref={(element) => registerElement(edgeId, "main", element)}
          d={path}
          fill="none"
          stroke={mainStroke}
          pathLength={100}
          strokeDasharray="100"
          strokeWidth={
            mostSustainable
              ? selected
                ? 3.4
                : hovered
                  ? 2.9
                  : 2.6
              : selected
                ? 2.6
                : hovered
                  ? 2.1
                  : 1.8
          }
          markerEnd={`url(#${markerId})`}
          className="edge-draw"
          style={{
            animationDelay: `${drawDelay}s`,
            transition: "stroke 0.2s, stroke-width 0.2s",
          }}
        />
      </g>
    )
  },
  (previousProps, nextProps) =>
    previousProps.drawDelay === nextProps.drawDelay &&
    previousProps.edgeId === nextProps.edgeId &&
    previousProps.flowActive === nextProps.flowActive &&
    previousProps.hovered === nextProps.hovered &&
    previousProps.initialPath === nextProps.initialPath &&
    previousProps.interactionMode === nextProps.interactionMode &&
    previousProps.layer === nextProps.layer &&
    previousProps.mostSustainable === nextProps.mostSustainable &&
    previousProps.selected === nextProps.selected
)

// ---------------------------------------------------------------------------
// Main graph component
// ---------------------------------------------------------------------------

interface SupplyChainGraphProps {
  bestEcoManufacturerByComponent: Record<string, string>
  hoveredNodeId: SupplyScenarioSelectableNodeId | null
  isPanelResizing?: boolean
  onHoverNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onSelectNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  pinnedManufacturerByComponent: Record<string, string>
  routeVisibleByComponent: Record<string, boolean>
  scenario: SupplyScenario
  selectedNodeId: SupplyScenarioSelectableNodeId | null
}

export const SupplyChainGraph = React.memo(function SupplyChainGraph({
  bestEcoManufacturerByComponent,
  hoveredNodeId,
  isPanelResizing = false,
  onHoverNode,
  onSelectNode,
  pinnedManufacturerByComponent,
  routeVisibleByComponent,
  scenario,
  selectedNodeId,
}: SupplyChainGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)
  const sceneFrameRef = useRef<number | null>(null)
  const drawerAnimationFrameRef = useRef<number | null>(null)
  const sceneTimestampRef = useRef<number | null>(null)
  const renderRefsRef = useRef(createRenderRefs())
  const sceneRef = useRef(createSceneState())
  const sceneNodePositionsRef = useRef(
    new Map<string, { x: number; y: number }>()
  )
  const cleanFitTransformRef = useRef<GraphTransform | null>(null)
  const layoutAnchorsRef = useRef(new Map<string, { x: number; y: number }>())
  const layoutNodesRef = useRef<GraphNodeState[]>([])
  const renderedNodesRef = useRef<GraphNodeState[]>([])
  const renderedEdgesRef = useRef<SupplyScenarioGraphEdge[]>([])
  const edgesRef = useRef<SupplyScenarioGraphEdge[]>(scenario.graph.edges)
  const viewportRef = useRef<GraphViewportSize | null>(null)
  const velocitiesRef = useRef(new Map<string, GraphVector>())
  const visibleComponentIdsRef = useRef<Set<string>>(new Set())
  const topologySignatureRef = useRef<string | null>(null)
  const drawerPositionRef = useRef<FloatingPanelPosition | null>(null)
  const drawerTargetPositionRef = useRef<FloatingPanelPosition | null>(null)
  const drawerDragStateRef = useRef<FloatingPanelDragState | null>(null)
  const manufacturerLayerVisibleRef = useRef(false)
  const interactionModeRef = useRef(false)
  const sceneDirtyRef = useRef(true)
  const simulationSettledRef = useRef(false)
  const [viewportSize, setViewportSize] = useState<GraphViewportSize | null>(
    null
  )
  const visibleComponentIds = React.useMemo(
    () => createVisibleComponentIdSet(scenario, routeVisibleByComponent),
    [routeVisibleByComponent, scenario]
  )
  const layoutVisibleNodes = React.useMemo(
    () =>
      buildCompactGraphNodes(
        filterGraphNodes(scenario.graph.nodes, visibleComponentIds, true),
        viewportSize
      ),
    [scenario.graph.nodes, viewportSize, visibleComponentIds]
  )
  const layoutVisibleNodeById = React.useMemo(
    () =>
      new Map(
        layoutVisibleNodes.map((node) => [node.id, node.position] as const)
      ),
    [layoutVisibleNodes]
  )
  const layoutNodes = React.useMemo(
    () =>
      scenario.graph.nodes.map((node) => ({
        ...node,
        position: layoutVisibleNodeById.get(node.id) ?? node.position,
      })),
    [layoutVisibleNodeById, scenario.graph.nodes]
  )
  const cleanLayoutNodes = React.useMemo(
    () => filterGraphNodes(layoutNodes, visibleComponentIds, false),
    [layoutNodes, visibleComponentIds]
  )
  const topologySignature = React.useMemo(
    () =>
      [
        scenario.id,
        scenario.graph.nodes.map((node) => node.id).join("|"),
        Array.from(visibleComponentIds).sort().join("|"),
      ].join("::"),
    [scenario.graph.nodes, scenario.id, visibleComponentIds]
  )
  const sceneNodeById = React.useMemo(
    () => new Map(layoutNodes.map((node) => [node.id, node] as const)),
    [layoutNodes]
  )
  const [manufacturerLayerVisible, setManufacturerLayerVisible] =
    useState(false)
  const [animatedManufacturerIds, setAnimatedManufacturerIds] = useState<
    Set<string>
  >(() => new Set())
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null)
  const [interactionMode, setInteractionMode] = useState(false)
  const [activeDraggedNodeId, setActiveDraggedNodeId] = useState<string | null>(
    null
  )
  const [isCanvasDragging, setIsCanvasDragging] = useState(false)
  const [drawerDragState, setDrawerDragState] =
    useState<FloatingPanelDragState | null>(null)
  const [drawerPosition, setDrawerPosition] =
    useState<FloatingPanelPosition | null>(null)
  const [panelVisible, setPanelVisible] = useState(false)
  const stopInertia = useCallback(() => {
    sceneRef.current.inertia = null
  }, [])
  const stopTransformAnimation = useCallback(() => {
    sceneRef.current.transformAnimation = null
  }, [])
  const markSceneDirty = useCallback(() => {
    sceneDirtyRef.current = true
  }, [])
  const updateInteractionMode = useCallback((nextValue: boolean) => {
    if (interactionModeRef.current === nextValue) {
      return
    }

    interactionModeRef.current = nextValue
    setInteractionMode(nextValue)
  }, [])
  const registerNodeElement = useCallback(
    (nodeId: string, element: HTMLDivElement | null) => {
      if (element) {
        renderRefsRef.current.nodes.set(nodeId, element)
        return
      }

      renderRefsRef.current.nodes.delete(nodeId)
    },
    []
  )
  const registerEdgeElement = useCallback(
    (
      edgeId: string,
      part: GraphEdgeElementPart,
      element: SVGPathElement | null
    ) => {
      const edgeRefs =
        renderRefsRef.current.edges.get(edgeId) ?? createEdgeElementRefs()

      edgeRefs[part] = element

      if (Object.values(edgeRefs).some(Boolean)) {
        renderRefsRef.current.edges.set(edgeId, edgeRefs)
        return
      }

      renderRefsRef.current.edges.delete(edgeId)
    },
    []
  )
  const setGridRef = useCallback((element: HTMLDivElement | null) => {
    renderRefsRef.current.grid = element
  }, [])
  const setWorldRef = useCallback((element: HTMLDivElement | null) => {
    renderRefsRef.current.world = element
  }, [])
  const setZoomLabelRef = useCallback((element: HTMLSpanElement | null) => {
    renderRefsRef.current.zoomLabel = element
  }, [])
  const handleHoveredEdgeChange = useCallback(
    (edgeId: string | null) => {
      if (sceneRef.current.dragState?.type === "node") {
        return
      }

      setHoveredEdgeId(edgeId)
    },
    [setHoveredEdgeId]
  )
  const handleHoveredNodeChange = useCallback(
    (nodeId: SupplyScenarioSelectableNodeId | null) => {
      if (sceneRef.current.dragState?.type === "node") {
        return
      }

      onHoverNode(nodeId)
    },
    [onHoverNode]
  )
  const animateTransformTo = useCallback(
    (
      nextTransform: {
        scale: number
        x: number
        y: number
      },
      durationMs = 560
    ) => {
      stopTransformAnimation()

      const startTransform = sceneRef.current.transform
      const deltaX = nextTransform.x - startTransform.x
      const deltaY = nextTransform.y - startTransform.y
      const deltaScale = nextTransform.scale - startTransform.scale

      if (
        Math.abs(deltaX) < 0.5 &&
        Math.abs(deltaY) < 0.5 &&
        Math.abs(deltaScale) < 0.001
      ) {
        sceneRef.current.transform = nextTransform
        markSceneDirty()
        return
      }

      sceneRef.current.transformAnimation = {
        durationMs,
        startAt: null,
        startTransform,
        targetTransform: nextTransform,
      }
      markSceneDirty()
    },
    [markSceneDirty, stopTransformAnimation]
  )
  const stopDrawerAnimation = useCallback(() => {
    if (drawerAnimationFrameRef.current !== null) {
      cancelAnimationFrame(drawerAnimationFrameRef.current)
      drawerAnimationFrameRef.current = null
    }
  }, [])
  const clampDrawerPosition = useCallback((position: FloatingPanelPosition) => {
    const container = containerRef.current
    const drawer = drawerRef.current

    if (!container || !drawer) {
      return position
    }

    return {
      x: clamp(
        position.x,
        16,
        Math.max(16, container.clientWidth - drawer.offsetWidth - 16)
      ),
      y: clamp(
        position.y,
        16,
        Math.max(16, container.clientHeight - drawer.offsetHeight - 16)
      ),
    }
  }, [])
  const animateDrawerTo = useCallback(
    (nextPosition: FloatingPanelPosition, immediate = false) => {
      const clampedPosition = clampDrawerPosition(nextPosition)

      drawerTargetPositionRef.current = clampedPosition

      if (immediate) {
        stopDrawerAnimation()
        drawerPositionRef.current = clampedPosition
        setDrawerPosition(clampedPosition)
        return
      }

      if (drawerAnimationFrameRef.current !== null) {
        return
      }

      const tick = () => {
        const targetPosition = drawerTargetPositionRef.current

        if (!targetPosition) {
          drawerAnimationFrameRef.current = null
          return
        }

        const currentPosition = drawerPositionRef.current ?? targetPosition
        const deltaX = targetPosition.x - currentPosition.x
        const deltaY = targetPosition.y - currentPosition.y
        const nextDrawerPosition =
          Math.abs(deltaX) < 0.6 && Math.abs(deltaY) < 0.6
            ? targetPosition
            : {
                x: currentPosition.x + deltaX * 0.24,
                y: currentPosition.y + deltaY * 0.24,
              }

        drawerPositionRef.current = nextDrawerPosition
        setDrawerPosition(nextDrawerPosition)

        if (
          Math.abs(targetPosition.x - nextDrawerPosition.x) >= 0.6 ||
          Math.abs(targetPosition.y - nextDrawerPosition.y) >= 0.6 ||
          drawerDragStateRef.current
        ) {
          drawerAnimationFrameRef.current = requestAnimationFrame(tick)
          return
        }

        drawerAnimationFrameRef.current = null
      }

      drawerAnimationFrameRef.current = requestAnimationFrame(tick)
    },
    [clampDrawerPosition, stopDrawerAnimation]
  )
  const renderedNodes = React.useMemo(
    () =>
      filterGraphNodes(
        layoutNodes,
        visibleComponentIds,
        manufacturerLayerVisible
      ),
    [layoutNodes, manufacturerLayerVisible, visibleComponentIds]
  )
  const displayedNodes = React.useMemo(
    () =>
      renderedNodes.map((node) => ({
        ...node,
        position: snapGraphPosition(node.position),
      })),
    [renderedNodes]
  )
  const renderedNodeIdSet = React.useMemo(
    () => new Set(displayedNodes.map((node) => node.id)),
    [displayedNodes]
  )
  const renderedNodeById = React.useMemo(
    () => new Map(displayedNodes.map((node) => [node.id, node] as const)),
    [displayedNodes]
  )
  const renderedEdges = React.useMemo(
    () => filterGraphEdges(scenario.graph.edges, renderedNodeIdSet),
    [renderedNodeIdSet, scenario.graph.edges]
  )
  const cleanFitTransform = React.useMemo(
    () => getFitTransform(cleanLayoutNodes, viewportSize),
    [cleanLayoutNodes, viewportSize]
  )
  const manufacturerComponentById = React.useMemo(
    () =>
      new Map(
        scenario.manufacturers.map(
          (manufacturer) => [manufacturer.id, manufacturer.componentId] as const
        )
      ),
    [scenario.manufacturers]
  )
  const componentNodeById = React.useMemo(
    () =>
      new Map(
        displayedNodes
          .filter((node) => node.data.kind === "component")
          .map((node) => [node.id, node] as const)
      ),
    [displayedNodes]
  )

  useEffect(() => {
    renderedNodesRef.current = renderedNodes
    renderedEdgesRef.current = renderedEdges
    markSceneDirty()
  }, [markSceneDirty, renderedEdges, renderedNodes])

  useEffect(() => {
    drawerDragStateRef.current = drawerDragState
  }, [drawerDragState])

  useEffect(() => {
    edgesRef.current = scenario.graph.edges
  }, [scenario.graph.edges])

  useEffect(() => {
    viewportRef.current = viewportSize
  }, [viewportSize])

  useEffect(() => {
    visibleComponentIdsRef.current = visibleComponentIds
  }, [visibleComponentIds])

  useEffect(() => {
    drawerPositionRef.current = drawerPosition
  }, [drawerPosition])

  useEffect(() => {
    manufacturerLayerVisibleRef.current = manufacturerLayerVisible
  }, [manufacturerLayerVisible])

  useEffect(() => {
    cleanFitTransformRef.current = cleanFitTransform
  }, [cleanFitTransform])

  useEffect(() => {
    sceneRef.current.isResizeActive = isPanelResizing

    if (isPanelResizing) {
      stopInertia()
      stopTransformAnimation()
      markSceneDirty()
    }
  }, [isPanelResizing, markSceneDirty, stopInertia, stopTransformAnimation])

  // Measure graph viewport for responsive layout + fit
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const updateSize = () => {
      const { width, height } = el.getBoundingClientRect()
      setViewportSize((previous) =>
        previous?.width === width && previous?.height === height
          ? previous
          : { width, height }
      )
    }

    updateSize()

    const observer = new ResizeObserver(() => {
      updateSize()
    })

    observer.observe(el)

    return () => observer.disconnect()
  }, [])

  const renderScene = useCallback(() => {
    const renderRefs = renderRefsRef.current
    const positions = sceneNodePositionsRef.current
    const paintedTransform = getPaintedTransform(sceneRef.current.transform)

    if (renderRefs.world) {
      renderRefs.world.style.transform = `translate(${paintedTransform.x}px, ${paintedTransform.y}px) scale(${paintedTransform.scale})`
    }

    if (renderRefs.zoomLabel) {
      renderRefs.zoomLabel.textContent = `${Math.round(sceneRef.current.transform.scale * 100)}%`
    }

    if (renderRefs.grid) {
      renderRefs.grid.style.backgroundPosition = `${paintedTransform.x % 26}px ${paintedTransform.y % 26}px, ${paintedTransform.x % 26}px ${paintedTransform.y % 26}px, ${paintedTransform.x % 104}px ${paintedTransform.y % 104}px, ${paintedTransform.x % 104}px ${paintedTransform.y % 104}px`
    }

    renderedNodesRef.current.forEach((node) => {
      const element = renderRefs.nodes.get(node.id)

      if (!element) {
        return
      }

      const position = snapGraphPosition(
        positions.get(node.id) ?? node.position
      )
      element.style.transform = `translate3d(${position.x}px, ${position.y}px, 0)`
    })

    const activeNodeById = new Map(
      renderedNodesRef.current.map(
        (node) =>
          [
            node.id,
            {
              ...node,
              position: positions.get(node.id) ?? node.position,
            },
          ] as const
      )
    )

    renderedEdgesRef.current.forEach((edge) => {
      const sourceNode = activeNodeById.get(edge.sourceId)
      const targetNode = activeNodeById.get(edge.targetId)
      const path =
        sourceNode && targetNode ? getEdgePath(sourceNode, targetNode) : null
      const edgeRefs = renderRefs.edges.get(edge.id)

      if (!edgeRefs) {
        return
      }

      ;(
        [
          edgeRefs.hit,
          edgeRefs.glow,
          edgeRefs.selectedGlow,
          edgeRefs.main,
          edgeRefs.ambient,
          edgeRefs.flow,
        ] as Array<SVGPathElement | null>
      ).forEach((element) => {
        if (!element) {
          return
        }

        element.setAttribute("d", path ?? "M 0 0 L 0 0")
        element.style.display = path ? "" : "none"
      })
    })
  }, [])

  useEffect(() => {
    renderScene()
  }, [
    activeDraggedNodeId,
    hoveredEdgeId,
    hoveredNodeId,
    interactionMode,
    manufacturerLayerVisible,
    renderScene,
    selectedNodeId,
  ])

  useEffect(() => {
    const nextAnchors = new Map(
      layoutNodes.map((node) => [node.id, { ...node.position }])
    )
    layoutAnchorsRef.current = nextAnchors
    layoutNodesRef.current = layoutNodes

    const topologyChanged = topologySignatureRef.current !== topologySignature
    topologySignatureRef.current = topologySignature

    if (topologyChanged) {
      velocitiesRef.current = createVelocityMap(layoutNodes)
      sceneNodePositionsRef.current = createNodePositionMap(layoutNodes)
      markSceneDirty()
      return
    }

    const previousPositions = sceneNodePositionsRef.current
    const nextPositions = new Map<string, { x: number; y: number }>()

    layoutNodes.forEach((node) => {
      const previousPosition = previousPositions.get(node.id)

      nextPositions.set(
        node.id,
        previousPosition ? { ...previousPosition } : { ...node.position }
      )
    })

    const nextVelocities = new Map<string, GraphVector>()

    layoutNodes.forEach((node) => {
      const previousVelocity = velocitiesRef.current.get(node.id) ?? {
        x: 0,
        y: 0,
      }
      const dampingFactor = isPanelResizing ? 0.12 : 0.68

      nextVelocities.set(node.id, {
        x: previousVelocity.x * dampingFactor,
        y: previousVelocity.y * dampingFactor,
      })
    })

    velocitiesRef.current = nextVelocities
    sceneNodePositionsRef.current = nextPositions
    markSceneDirty()
  }, [isPanelResizing, layoutNodes, markSceneDirty, topologySignature])

  useEffect(() => {
    if (isPanelResizing) {
      return
    }

    const frameId = window.requestAnimationFrame(() => {
      if (sceneRef.current.dragState) {
        return
      }

      const activeNodes = buildSceneNodes(
        manufacturerLayerVisibleRef.current
          ? layoutVisibleNodes
          : cleanLayoutNodes,
        sceneNodePositionsRef.current
      )
      const fittedTransform = getFitTransform(activeNodes, viewportSize)

      if (!fittedTransform) {
        return
      }

      if (!sceneRef.current.hasManualCameraInteraction) {
        animateTransformTo(fittedTransform)
        return
      }

      const clampedTransform = clampTransformToViewport(
        sceneRef.current.transform,
        activeNodes,
        viewportSize
      )

      if (
        clampedTransform &&
        hasMeaningfulTransformDelta(
          sceneRef.current.transform,
          clampedTransform
        )
      ) {
        animateTransformTo(clampedTransform, 280)
      }
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [
    animateTransformTo,
    cleanLayoutNodes,
    isPanelResizing,
    layoutVisibleNodes,
    viewportSize,
  ])

  // Show panel with a tick of delay for animation
  useEffect(() => {
    const t = window.setTimeout(
      () => setPanelVisible(Boolean(selectedNodeId)),
      selectedNodeId ? 10 : 0
    )

    return () => window.clearTimeout(t)
  }, [selectedNodeId])

  useEffect(() => {
    if (!panelVisible || !selectedNodeId) {
      return
    }

    const frameId = window.requestAnimationFrame(() => {
      const container = containerRef.current
      const drawer = drawerRef.current

      if (!container || !drawer) {
        return
      }

      const fallbackPosition = {
        x: Math.max(16, container.clientWidth - drawer.offsetWidth - 16),
        y: 16,
      }

      animateDrawerTo(drawerPositionRef.current ?? fallbackPosition, true)
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [animateDrawerTo, panelVisible, selectedNodeId, viewportSize])

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      const activeDragState = drawerDragStateRef.current

      if (!activeDragState || activeDragState.pointerId !== event.pointerId) {
        return
      }

      const container = containerRef.current

      if (!container) {
        return
      }

      const bounds = container.getBoundingClientRect()

      animateDrawerTo({
        x: event.clientX - bounds.left - activeDragState.offsetX,
        y: event.clientY - bounds.top - activeDragState.offsetY,
      })
    }

    const handlePointerUp = (event: PointerEvent) => {
      if (drawerDragStateRef.current?.pointerId !== event.pointerId) {
        return
      }

      setDrawerDragState(null)
    }

    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)
    window.addEventListener("pointercancel", handlePointerUp)

    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("pointercancel", handlePointerUp)
    }
  }, [animateDrawerTo])

  useEffect(() => {
    return () => {
      stopDrawerAnimation()
    }
  }, [stopDrawerAnimation])

  useEffect(() => {
    if (animatedManufacturerIds.size === 0) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      setAnimatedManufacturerIds(new Set())
    }, 520)

    return () => window.clearTimeout(timeoutId)
  }, [animatedManufacturerIds])

  // Prevent page scroll on canvas
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const prevent = (e: WheelEvent) => e.preventDefault()
    el.addEventListener("wheel", prevent, { passive: false })
    return () => el.removeEventListener("wheel", prevent)
  }, [])

  useEffect(() => {
    const STEP_MS = 1000 / 60
    let accumulatorMs = 0

    const tick = (timestamp: number) => {
      if (sceneTimestampRef.current === null) {
        sceneTimestampRef.current = timestamp
      }

      const deltaMs = Math.min(48, timestamp - sceneTimestampRef.current)
      sceneTimestampRef.current = timestamp
      accumulatorMs = Math.min(accumulatorMs + deltaMs, STEP_MS * 3)

      const scene = sceneRef.current
      const positions = sceneNodePositionsRef.current
      const isResizeActive = scene.isResizeActive
      let positionsChanged = false
      let transformChanged = false
      let shouldAnimateNodes = scene.dragState?.type === "node"

      if (scene.transformAnimation) {
        if (scene.transformAnimation.startAt === null) {
          scene.transformAnimation.startAt = timestamp
        }

        const progress = clamp(
          (timestamp - scene.transformAnimation.startAt) /
            scene.transformAnimation.durationMs,
          0,
          1
        )
        const eased = 1 - Math.pow(1 - progress, 3)
        const { startTransform, targetTransform } = scene.transformAnimation

        scene.transform = {
          scale:
            startTransform.scale +
            (targetTransform.scale - startTransform.scale) * eased,
          x: startTransform.x + (targetTransform.x - startTransform.x) * eased,
          y: startTransform.y + (targetTransform.y - startTransform.y) * eased,
        }
        transformChanged = true

        if (progress >= 1) {
          scene.transformAnimation = null
        }
      }

      if (scene.dragState?.type === "canvas") {
        const dx = scene.dragState.currentClientX - scene.dragState.startClientX
        const dy = scene.dragState.currentClientY - scene.dragState.startClientY

        if (!scene.dragState.moved && Math.hypot(dx, dy) > 4) {
          scene.dragState.moved = true
          scene.hasManualCameraInteraction = true
        }

        scene.transform = {
          ...scene.transform,
          x: scene.dragState.originTransform.x + dx,
          y: scene.dragState.originTransform.y + dy,
        }
        transformChanged = true
      } else if (scene.inertia) {
        if (
          Math.abs(scene.inertia.x) < 0.1 &&
          Math.abs(scene.inertia.y) < 0.1
        ) {
          scene.inertia = null
        } else {
          scene.transform = {
            ...scene.transform,
            x: scene.transform.x + scene.inertia.x,
            y: scene.transform.y + scene.inertia.y,
          }
          scene.inertia = {
            x: scene.inertia.x * 0.92,
            y: scene.inertia.y * 0.92,
          }
          transformChanged = true
        }
      }

      if (scene.dragState?.type === "node") {
        const dx = scene.dragState.currentClientX - scene.dragState.startClientX
        const dy = scene.dragState.currentClientY - scene.dragState.startClientY

        if (!scene.dragState.moved && Math.hypot(dx, dy) > 4) {
          scene.dragState.moved = true
        }

        positions.set(scene.dragState.nodeId, {
          x: scene.dragState.originPosition.x + dx / scene.transform.scale,
          y: scene.dragState.originPosition.y + dy / scene.transform.scale,
        })
        positionsChanged = true
      }

      // A settled layout stays asleep until something marks the scene dirty.
      const simulationAwake =
        !simulationSettledRef.current ||
        sceneDirtyRef.current ||
        isResizeActive ||
        scene.dragState?.type === "node"

      if (simulationAwake) {
        simulationSettledRef.current = false
      } else {
        accumulatorMs = 0
      }

      while (simulationAwake && accumulatorMs >= STEP_MS) {
        accumulatorMs -= STEP_MS

        const activeNodes = buildSceneNodes(
          filterGraphNodes(
            layoutNodesRef.current,
            visibleComponentIdsRef.current,
            manufacturerLayerVisibleRef.current
          ),
          positions
        )
        const activeNodeIds = new Set(activeNodes.map((node) => node.id))
        const draggedNodeId =
          scene.dragState?.type === "node" ? scene.dragState.nodeId : null

        if (!draggedNodeId && activeNodes.length <= 1) {
          positionsChanged =
            stabilizeSceneNodes(
              activeNodes,
              positions,
              velocitiesRef.current
            ) || positionsChanged
          shouldAnimateNodes = false
          simulationSettledRef.current = !isResizeActive
          break
        }

        const activeEdges = filterGraphEdges(edgesRef.current, activeNodeIds)

        if (!draggedNodeId && activeEdges.length === 0) {
          positionsChanged =
            stabilizeSceneNodes(
              activeNodes,
              positions,
              velocitiesRef.current
            ) || positionsChanged
          shouldAnimateNodes = false
          simulationSettledRef.current = !isResizeActive
          break
        }

        const result = runForceSimulationStep({
          anchors: layoutAnchorsRef.current,
          draggedNodeId,
          dtScale: 1,
          edges: activeEdges,
          isResizeActive,
          nodes: activeNodes,
          velocities: velocitiesRef.current,
          viewport: viewportRef.current,
        })

        positionsChanged =
          syncNodePositionMap(positions, result.nodes) || positionsChanged
        shouldAnimateNodes =
          Boolean(draggedNodeId) ||
          result.meanSpeed >= result.settleThreshold ||
          shouldAnimateNodes

        if (!draggedNodeId && result.meanSpeed < result.settleThreshold) {
          positionsChanged =
            stabilizeSceneNodes(
              activeNodes,
              positions,
              velocitiesRef.current
            ) || positionsChanged
          shouldAnimateNodes = false
          simulationSettledRef.current = !isResizeActive
          break
        }
      }

      const cleanScale = cleanFitTransformRef.current?.scale
      const nextInteractionMode =
        isResizeActive ||
        Boolean(scene.dragState) ||
        Boolean(scene.inertia) ||
        Boolean(scene.transformAnimation) ||
        shouldAnimateNodes

      if (
        !isResizeActive &&
        cleanScale &&
        !manufacturerLayerVisibleRef.current &&
        scene.transform.scale <= cleanScale * MANUFACTURER_REVEAL_SCALE_FACTOR
      ) {
        manufacturerLayerVisibleRef.current = true
        setManufacturerLayerVisible(true)
        setAnimatedManufacturerIds(
          nextInteractionMode
            ? new Set()
            : new Set(
                layoutVisibleNodes
                  .filter((node) => node.data.kind === "manufacturer")
                  .map((node) => node.id)
              )
        )
      }

      if (
        !isResizeActive &&
        cleanScale &&
        manufacturerLayerVisibleRef.current &&
        scene.transform.scale >= cleanScale * MANUFACTURER_HIDE_SCALE_FACTOR
      ) {
        const componentId = selectedNodeId
          ? manufacturerComponentById.get(selectedNodeId)
          : null

        manufacturerLayerVisibleRef.current = false
        setManufacturerLayerVisible(false)
        setAnimatedManufacturerIds(new Set())

        if (componentId) {
          onSelectNode(
            (routeVisibleByComponent[componentId] ?? true)
              ? componentId
              : scenario.product.id
          )
        }
      }

      scene.interactionMode = nextInteractionMode
      updateInteractionMode(nextInteractionMode)

      if (sceneDirtyRef.current || positionsChanged || transformChanged) {
        renderScene()
        sceneDirtyRef.current = false
      }

      sceneFrameRef.current = requestAnimationFrame(tick)
    }

    sceneFrameRef.current = requestAnimationFrame(tick)

    return () => {
      if (sceneFrameRef.current !== null) {
        cancelAnimationFrame(sceneFrameRef.current)
        sceneFrameRef.current = null
      }

      sceneTimestampRef.current = null
      updateInteractionMode(false)
    }
  }, [
    layoutVisibleNodes,
    manufacturerComponentById,
    onSelectNode,
    renderScene,
    routeVisibleByComponent,
    scenario.product.id,
    selectedNodeId,
    updateInteractionMode,
  ])

  // --- Wheel zoom/pan ---
  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault()
      stopInertia()
      stopTransformAnimation()
      const containerBounds = containerRef.current?.getBoundingClientRect()
      const pointerX = e.clientX - (containerBounds?.left ?? 0)
      const pointerY = e.clientY - (containerBounds?.top ?? 0)

      const previousTransform = sceneRef.current.transform
      const nextScale = clamp(
        previousTransform.scale * Math.exp(-e.deltaY * 0.0025),
        GRAPH_MIN_SCALE,
        GRAPH_MAX_SCALE
      )

      sceneRef.current.hasManualCameraInteraction = true
      sceneRef.current.transform = getScaledTransformAtPoint(
        previousTransform,
        { x: pointerX, y: pointerY },
        nextScale
      )
      markSceneDirty()
    },
    [markSceneDirty, stopInertia, stopTransformAnimation]
  )

  const handleZoom = useCallback(
    (dir: "in" | "out") => {
      const nextScale = clamp(
        sceneRef.current.transform.scale * (dir === "in" ? 1.25 : 0.8),
        GRAPH_MIN_SCALE,
        GRAPH_MAX_SCALE
      )
      const centerX = (containerRef.current?.clientWidth ?? 800) / 2
      const centerY = (containerRef.current?.clientHeight ?? 600) / 2

      sceneRef.current.hasManualCameraInteraction = true
      animateTransformTo(
        getScaledTransformAtPoint(
          sceneRef.current.transform,
          { x: centerX, y: centerY },
          nextScale
        ),
        260
      )
    },
    [animateTransformTo]
  )

  const handleFit = useCallback(() => {
    const fittedTransform = getFitTransform(
      buildSceneNodes(renderedNodesRef.current, sceneNodePositionsRef.current),
      viewportRef.current
    )

    if (fittedTransform) {
      sceneRef.current.hasManualCameraInteraction = false
      animateTransformTo(fittedTransform, 620)
    }
  }, [animateTransformTo])
  const handleDrawerPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) {
        return
      }

      if ((event.target as HTMLElement).closest("button, a, input, textarea")) {
        return
      }

      const container = containerRef.current
      const drawer = drawerRef.current

      if (!container || !drawer) {
        return
      }

      const containerBounds = container.getBoundingClientRect()
      const currentPosition = drawerPositionRef.current ?? {
        x: drawer.offsetLeft,
        y: drawer.offsetTop,
      }

      drawerPositionRef.current = currentPosition
      drawerTargetPositionRef.current = currentPosition
      setDrawerPosition(currentPosition)
      setDrawerDragState({
        offsetX: event.clientX - containerBounds.left - currentPosition.x,
        offsetY: event.clientY - containerBounds.top - currentPosition.y,
        pointerId: event.pointerId,
      })
      event.preventDefault()
    },
    [setDrawerDragState, setDrawerPosition]
  )

  // --- Pointer events ---
  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) {
        return
      }

      stopInertia()
      stopTransformAnimation()

      const target = event.target as HTMLElement
      const nodeEl = target.closest(".gc-node") as HTMLElement | null

      if (nodeEl) {
        const nodeId = nodeEl.dataset.nodeId
        const node = nodeId ? sceneNodeById.get(nodeId) : null

        if (!nodeId || !node) {
          return
        }

        const currentPosition =
          sceneNodePositionsRef.current.get(nodeId) ?? node.position

        sceneRef.current.dragState = {
          currentClientX: event.clientX,
          currentClientY: event.clientY,
          moved: false,
          nodeId,
          originPosition: { ...currentPosition },
          pointerId: event.pointerId,
          startClientX: event.clientX,
          startClientY: event.clientY,
          type: "node",
        }
        sceneRef.current.inertia = null
        setActiveDraggedNodeId(nodeId)
        setIsCanvasDragging(false)
        setHoveredEdgeId(null)
        onHoverNode(null)
        event.currentTarget.setPointerCapture(event.pointerId)
        markSceneDirty()
        event.stopPropagation()
        return
      }

      sceneRef.current.dragState = {
        currentClientX: event.clientX,
        currentClientY: event.clientY,
        lastClientX: event.clientX,
        lastClientY: event.clientY,
        lastTs: performance.now(),
        moved: false,
        originTransform: { ...sceneRef.current.transform },
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        type: "canvas",
        velocityX: 0,
        velocityY: 0,
      }
      sceneRef.current.inertia = null
      setActiveDraggedNodeId(null)
      setIsCanvasDragging(true)
      event.currentTarget.setPointerCapture(event.pointerId)
      markSceneDirty()
    },
    [
      markSceneDirty,
      onHoverNode,
      sceneNodeById,
      setActiveDraggedNodeId,
      setHoveredEdgeId,
      setIsCanvasDragging,
      stopInertia,
      stopTransformAnimation,
    ]
  )

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const activeDragState = sceneRef.current.dragState

      if (!activeDragState || activeDragState.pointerId !== event.pointerId) {
        return
      }

      activeDragState.currentClientX = event.clientX
      activeDragState.currentClientY = event.clientY

      if (activeDragState.type === "canvas") {
        const now = performance.now()
        const dt = now - activeDragState.lastTs

        if (dt > 0) {
          activeDragState.velocityX =
            (event.clientX - activeDragState.lastClientX) / dt
          activeDragState.velocityY =
            (event.clientY - activeDragState.lastClientY) / dt
        }

        activeDragState.lastTs = now
        activeDragState.lastClientX = event.clientX
        activeDragState.lastClientY = event.clientY
      }

      markSceneDirty()
    },
    [markSceneDirty]
  )

  const handlePointerUp = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const activeDragState = sceneRef.current.dragState

      if (!activeDragState || activeDragState.pointerId !== event.pointerId) {
        return
      }

      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId)
      }

      if (activeDragState.type === "canvas") {
        if (!activeDragState.moved) {
          onSelectNode(null)
        } else {
          const velocityX = activeDragState.velocityX * 16
          const velocityY = activeDragState.velocityY * 16

          if (Math.abs(velocityX) > 1 || Math.abs(velocityY) > 1) {
            sceneRef.current.inertia = { x: velocityX, y: velocityY }
          }
        }
      } else if (!activeDragState.moved) {
        onSelectNode(activeDragState.nodeId)
      } else {
        const droppedPosition = sceneNodePositionsRef.current.get(
          activeDragState.nodeId
        )

        if (droppedPosition) {
          layoutAnchorsRef.current.set(activeDragState.nodeId, {
            ...droppedPosition,
          })
          velocitiesRef.current.set(activeDragState.nodeId, { x: 0, y: 0 })
        }
      }

      sceneRef.current.dragState = null
      setActiveDraggedNodeId(null)
      setIsCanvasDragging(false)
      markSceneDirty()
    },
    [markSceneDirty, onSelectNode, setActiveDraggedNodeId, setIsCanvasDragging]
  )

  useEffect(
    () => () => {
      if (sceneFrameRef.current !== null) {
        cancelAnimationFrame(sceneFrameRef.current)
        sceneFrameRef.current = null
      }

      stopInertia()
      stopTransformAnimation()
    },
    [stopInertia, stopTransformAnimation]
  )

  // Keyboard: Escape deselects
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onSelectNode(null)
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [onSelectNode])

  // --- Selected data ---
  const selectedNode = selectedNodeId
    ? (sceneNodeById.get(selectedNodeId) ?? null)
    : null
  const selectedMfr =
    selectedNode?.data.kind === "manufacturer" ? selectedNode.data : null
  const selectedBaseNode =
    selectedNode && selectedNode.data.kind !== "manufacturer"
      ? selectedNode.data
      : null
  const manufacturerById = React.useMemo(
    () =>
      new Map(
        scenario.manufacturers.map((manufacturer) => [
          manufacturer.id,
          manufacturer,
        ])
      ),
    [scenario.manufacturers]
  )
  const manufacturersByComponentId = React.useMemo(() => {
    const nextMap = new Map<string, SupplyScenarioManufacturerNode[]>()

    scenario.components.forEach((component) => {
      nextMap.set(
        component.id,
        component.manufacturerIds
          .map((manufacturerId) => manufacturerById.get(manufacturerId))
          .filter(
            (manufacturer): manufacturer is SupplyScenarioManufacturerNode =>
              Boolean(manufacturer)
          )
      )
    })

    return nextMap
  }, [manufacturerById, scenario.components])
  const componentInsightsById = React.useMemo(() => {
    const nextMap = new Map<string, ComponentInsight>()

    scenario.components.forEach((component) => {
      const manufacturers = manufacturersByComponentId.get(component.id) ?? []
      nextMap.set(component.id, {
        best: getBestEcoManufacturer(
          manufacturers,
          bestEcoManufacturerByComponent[component.id]
        ),
        current: getCurrentManufacturer(manufacturers),
        manufacturers,
        selected: getSelectedManufacturer(
          manufacturers,
          pinnedManufacturerByComponent[component.id]
        ),
      })
    })

    return nextMap
  }, [
    bestEcoManufacturerByComponent,
    manufacturersByComponentId,
    pinnedManufacturerByComponent,
    scenario.components,
  ])
  const visibleComponents = React.useMemo(
    () =>
      scenario.components.filter(
        (component) => routeVisibleByComponent[component.id] ?? true
      ),
    [routeVisibleByComponent, scenario.components]
  )
  const visibleManufacturers = React.useMemo(
    () =>
      scenario.manufacturers.filter(
        (manufacturer) =>
          routeVisibleByComponent[manufacturer.componentId] ?? true
      ),
    [routeVisibleByComponent, scenario.manufacturers]
  )
  const selectedPathEntries = React.useMemo(
    () =>
      visibleComponents
        .map((component) => ({
          component,
          insight: componentInsightsById.get(component.id),
        }))
        .filter((entry): entry is SelectedPathEntry => Boolean(entry.insight)),
    [componentInsightsById, visibleComponents]
  )
  const selectedManufacturers = React.useMemo(
    () =>
      selectedPathEntries
        .map((entry) => entry.insight.selected)
        .filter(
          (manufacturer): manufacturer is SupplyScenarioManufacturerNode =>
            Boolean(manufacturer)
        ),
    [selectedPathEntries]
  )
  const currentManufacturers = React.useMemo(
    () =>
      selectedPathEntries
        .map((entry) => entry.insight.current)
        .filter(
          (manufacturer): manufacturer is SupplyScenarioManufacturerNode =>
            Boolean(manufacturer)
        ),
    [selectedPathEntries]
  )
  const currentRouteTotalTco2e = React.useMemo(
    () =>
      currentManufacturers.reduce(
        (sum, manufacturer) => sum + getEstimatedRouteTotalTco2e(manufacturer),
        0
      ),
    [currentManufacturers]
  )
  const selectedRouteTotalTco2e = React.useMemo(
    () =>
      selectedManufacturers.reduce(
        (sum, manufacturer) => sum + getEstimatedRouteTotalTco2e(manufacturer),
        0
      ),
    [selectedManufacturers]
  )
  const selectedRouteCountryCount = React.useMemo(
    () =>
      new Set(
        selectedManufacturers.map(
          (manufacturer) => manufacturer.location.countryCode
        )
      ).size,
    [selectedManufacturers]
  )
  const visibleManufacturerCountryCount = React.useMemo(
    () =>
      new Set(
        visibleManufacturers.map(
          (manufacturer) => manufacturer.location.countryCode
        )
      ).size,
    [visibleManufacturers]
  )
  const selectedAverageEcoScore = React.useMemo(
    () =>
      selectedManufacturers.length > 0
        ? selectedManufacturers.reduce(
            (sum, manufacturer) => sum + manufacturer.ecoScore,
            0
          ) / selectedManufacturers.length
        : null,
    [selectedManufacturers]
  )
  const statsOverlayData = React.useMemo<GraphStatsOverlayData>(() => {
    const aggregateAccentColor =
      selectedAverageEcoScore !== null
        ? getEcoConfig(selectedAverageEcoScore).color
        : "color-mix(in oklab, var(--primary) 72%, white 14%)"

    return {
      accentColor: aggregateAccentColor,
      eyebrow: "Selected routes",
      metrics: [
        {
          label: "Current q50",
          emphasized: true,
          value: formatTco2e(currentRouteTotalTco2e),
        },
        {
          label: "Selected q50",
          emphasized: true,
          value: formatTco2e(selectedRouteTotalTco2e),
        },
      ],
    }
  }, [currentRouteTotalTco2e, selectedAverageEcoScore, selectedRouteTotalTco2e])
  const ecoConfig = selectedMfr ? getEcoConfig(selectedMfr.ecoScore) : null
  const drawerSectionStyle = {
    background: "rgba(7,12,16,0.58)",
    border: "1px solid rgba(255,255,255,0.07)",
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
  }
  const drawerSurfaceStyle = {
    backgroundColor: "rgb(8 11 16)",
    backgroundImage:
      "linear-gradient(180deg, rgba(12,16,22,0.985) 0%, rgba(8,11,16,0.99) 100%)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "1.35rem",
    boxShadow:
      "inset 0 1px 0 rgba(255,255,255,0.04), 0 18px 42px rgba(0,0,0,0.34)",
    overflow: "hidden" as const,
  }
  const paintedTransform = getPaintedTransform(DEFAULT_GRAPH_TRANSFORM)

  // Cursor
  const cursor = isCanvasDragging ? "cursor-grabbing" : "cursor-grab"

  const renderEdgeLayer = (layer: EdgeProps["layer"]) =>
    renderedEdges.map((edge, edgeIndex) => {
      const src = renderedNodeById.get(edge.sourceId)
      const tgt = renderedNodeById.get(edge.targetId)
      if (!src || !tgt) return null
      const isSelected = selectedNodeId === src.id || selectedNodeId === tgt.id
      const isHovered =
        hoveredEdgeId === edge.id ||
        hoveredNodeId === src.id ||
        hoveredNodeId === tgt.id
      const isMostSustainable =
        (tgt.data.kind === "manufacturer" &&
          bestEcoManufacturerByComponent[tgt.data.componentId] === tgt.id) ||
        (src.data.kind === "product" &&
          tgt.data.kind === "component" &&
          !!bestEcoManufacturerByComponent[tgt.id])
      const flowActive =
        src.data.kind === "product" ||
        (tgt.data.kind === "manufacturer" && tgt.data.isCurrent)
      return (
        <ConnectionEdge
          key={edge.id}
          drawDelay={edgeIndex * 0.08}
          edgeId={edge.id}
          flowActive={flowActive}
          hovered={isHovered}
          initialPath={getEdgePath(src, tgt)}
          interactionMode={interactionMode}
          layer={layer}
          mostSustainable={isMostSustainable}
          onHoverEnd={() => handleHoveredEdgeChange(null)}
          onHoverStart={() => handleHoveredEdgeChange(edge.id)}
          registerElement={registerEdgeElement}
          selected={isSelected}
        />
      )
    })

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div
      className="relative h-full w-full overflow-hidden"
      style={{
        background:
          "radial-gradient(circle at 52% 42%, color-mix(in oklab, var(--primary) 6%, transparent), transparent 36%), linear-gradient(180deg, rgba(7,7,12,0.98), rgba(5,5,8,1))",
      }}
    >
      {/* Keyframe styles */}
      <style>{`
        @keyframes edge-flow {
          from { stroke-dashoffset: 24; }
          to   { stroke-dashoffset: 0;  }
        }
        .edge-flow { animation: edge-flow 1.8s linear infinite; }

        @keyframes edge-flow-subtle {
          from { stroke-dashoffset: 36; }
          to   { stroke-dashoffset: 0;  }
        }
        .edge-flow-subtle { animation: edge-flow-subtle 4.2s linear infinite; }

        @keyframes edge-flow-ambient {
          from { stroke-dashoffset: 54; }
          to   { stroke-dashoffset: 0;  }
        }
        .edge-flow-ambient { animation: edge-flow-ambient 8.5s linear infinite; }

        @keyframes edge-draw {
          from { stroke-dashoffset: 100; }
          to   { stroke-dashoffset: 0; }
        }
        .edge-draw {
          animation: edge-draw 0.95s cubic-bezier(0.2,0.9,0.2,1) both;
        }

        @keyframes node-breathe {
          0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
          50% { transform: translate3d(0, -3px, 0) scale(1.012); }
        }
        .node-breathe {
          animation: node-breathe 11.4s ease-in-out infinite;
          will-change: transform;
        }

        @keyframes node-breathe-sheen {
          0%, 100% { opacity: 0.28; transform: translate3d(0, 0, 0) scale(1); }
          50% { opacity: 0.58; transform: translate3d(0, -1.5%, 0) scale(1.012); }
        }
        .node-breathe-sheen {
          animation: node-breathe-sheen 11.4s ease-in-out infinite;
        }

        @keyframes focus-beacon {
          0%, 100% { opacity: 0.42; transform: scaleX(1); }
          50% { opacity: 0.92; transform: scaleX(1.04); }
        }
        .focus-beacon {
          animation: focus-beacon 5.6s ease-in-out infinite;
          transform-origin: center;
        }

        @keyframes emblem-pulse {
          0%, 100% { opacity: 0.88; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.05); }
        }
        .emblem-pulse {
          animation: emblem-pulse 6.2s ease-in-out infinite;
          transform-origin: center;
        }

        @keyframes panel-slide-in {
          from { opacity: 0; transform: translateX(24px); }
          to   { opacity: 1; transform: translateX(0);    }
        }
        .panel-slide-in { animation: panel-slide-in 0.35s cubic-bezier(0.34,1.56,0.64,1) forwards; }

        @keyframes manufacturer-node-reveal {
          0% {
            opacity: 0;
            transform: translate3d(var(--manufacturer-entry-x, 0px), var(--manufacturer-entry-y, 0px), 0) scale(0.72);
          }
          60% {
            opacity: 1;
            transform: translate3d(calc(var(--manufacturer-entry-x, 0px) * -0.08), calc(var(--manufacturer-entry-y, 0px) * -0.08), 0) scale(1.03);
          }
          100% {
            opacity: 1;
            transform: translate3d(0, 0, 0) scale(1);
          }
        }
        .manufacturer-node-reveal {
          animation: manufacturer-node-reveal 0.48s cubic-bezier(0.22,1,0.36,1) both;
          will-change: transform, opacity;
        }

        @media (prefers-reduced-motion: reduce) {
          .edge-flow,
          .edge-flow-subtle,
          .edge-flow-ambient,
          .edge-draw,
          .focus-beacon,
          .emblem-pulse,
          .panel-slide-in,
          .manufacturer-node-reveal,
          .node-breathe,
          .node-breathe-sheen {
            animation: none !important;
          }
        }
      `}</style>

      {/* Dot grid */}
      <div
        ref={setGridRef}
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(226,223,218,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(226,223,218,0.1) 1px, transparent 1px), linear-gradient(rgba(246,244,240,0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(246,244,240,0.12) 1px, transparent 1px)",
          backgroundPosition: `${paintedTransform.x % 26}px ${paintedTransform.y % 26}px, ${paintedTransform.x % 26}px ${paintedTransform.y % 26}px, ${paintedTransform.x % 104}px ${paintedTransform.y % 104}px, ${paintedTransform.x % 104}px ${paintedTransform.y % 104}px`,
          backgroundSize: "26px 26px, 26px 26px, 104px 104px, 104px 104px",
        }}
      />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-28 -left-28 h-72 w-72 rounded-full opacity-65"
        style={{
          background:
            "radial-gradient(circle, color-mix(in oklab, var(--primary) 8%, transparent) 0%, color-mix(in oklab, var(--accent) 4%, transparent) 42%, transparent 74%)",
          filter: "blur(26px)",
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-24 bottom-10 h-56 w-56 rounded-full opacity-42"
        style={{
          background:
            "radial-gradient(circle, color-mix(in oklab, var(--accent) 6%, transparent) 0%, color-mix(in oklab, var(--primary) 3%, transparent) 48%, transparent 76%)",
          filter: "blur(24px)",
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-8 bottom-6 h-40 w-40 rounded-full opacity-28"
        style={{
          background:
            "radial-gradient(circle, rgba(255,255,255,0.05) 0%, transparent 72%)",
          filter: "blur(22px)",
        }}
      />

      <GraphStatsOverlay data={statsOverlayData} />

      {/* Canvas interaction area */}
      <div
        ref={containerRef}
        className={`absolute inset-0 ${cursor} select-none`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerCancel={handlePointerUp}
        onPointerUp={handlePointerUp}
        onWheel={handleWheel}
      >
        {/* Transformed world layer */}
        <div
          ref={setWorldRef}
          className="absolute top-0 left-0 origin-top-left"
          style={{
            transform: `translate(${paintedTransform.x}px, ${paintedTransform.y}px) scale(${paintedTransform.scale})`,
            willChange: "transform",
          }}
        >
          {/* Edges SVG */}
          <svg
            className="pointer-events-none absolute overflow-visible"
            style={{ zIndex: 1, willChange: "transform" }}
          >
            <defs>
              <marker
                id="arrow-def"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 2 L 10 5 L 0 8 z" fill="rgba(255,255,255,0.07)" />
              </marker>
              <marker
                id="arrow-hov"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 2 L 10 5 L 0 8 z" fill="rgba(255,255,255,0.30)" />
              </marker>
              <marker
                id="arrow-sel"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 2 L 10 5 L 0 8 z" fill="#F1E9FF" />
              </marker>
              <marker
                id="arrow-eco-def"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 2 L 10 5 L 0 8 z" fill="rgba(110,231,183,0.54)" />
              </marker>
              <marker
                id="arrow-eco-hov"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 2 L 10 5 L 0 8 z" fill="rgba(167,243,208,0.82)" />
              </marker>
              <marker
                id="arrow-eco-sel"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 2 L 10 5 L 0 8 z" fill="#ECFDF5" />
              </marker>
            </defs>

            {renderEdgeLayer("base")}
          </svg>
          <svg
            className="pointer-events-none absolute overflow-visible"
            style={{ zIndex: 1, willChange: "transform" }}
          >
            {renderEdgeLayer("flow")}
          </svg>

          {/* Nodes */}
          {displayedNodes.map((node, index) => {
            const { w, h } = getNodeSize(node)
            const isSelected = selectedNodeId === node.id
            const isHovered = hoveredNodeId === node.id
            const isDragging = activeDraggedNodeId === node.id
            const componentNode =
              node.data.kind === "manufacturer"
                ? componentNodeById.get(node.data.componentId)
                : null
            const nodeCenter = getNodeCenter(node)
            const componentCenter = componentNode
              ? getNodeCenter(componentNode)
              : null

            return (
              <div
                key={node.id}
                ref={(element) => registerNodeElement(node.id, element)}
                data-node-id={node.id}
                className="gc-node absolute"
                style={
                  {
                    "--manufacturer-entry-x": componentCenter
                      ? `${componentCenter.x - nodeCenter.x}px`
                      : "0px",
                    "--manufacturer-entry-y": componentCenter
                      ? `${componentCenter.y - nodeCenter.y}px`
                      : "0px",
                    left: 0,
                    top: 0,
                    transform: `translate3d(${node.position.x}px, ${node.position.y}px, 0)`,
                    width: w,
                    height: h,
                    willChange: "transform",
                    zIndex: isSelected || isDragging ? 50 : 10,
                  } as React.CSSProperties
                }
                onPointerEnter={() => handleHoveredNodeChange(node.id)}
                onPointerLeave={() => handleHoveredNodeChange(null)}
              >
                <div
                  className={cn(
                    "h-full w-full",
                    node.data.kind === "manufacturer" &&
                      animatedManufacturerIds.has(node.id)
                      ? "manufacturer-node-reveal"
                      : ""
                  )}
                >
                  <NodeCard
                    allowIdleFloat={!interactionMode}
                    interactionMode={interactionMode}
                    isDragging={isDragging}
                    node={node}
                    isSelected={isSelected}
                    isHovered={isHovered}
                    motionIndex={index}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Zoom controls */}
      <div className="dashboard-control-surface absolute bottom-24 left-5 z-20 flex flex-col gap-1 rounded-xl p-1.5 shadow-2xl sm:bottom-28">
        <button
          onClick={() => handleZoom("in")}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-white/40 transition-colors hover:bg-white/[0.07] hover:text-white/80"
        >
          <HugeiconsIcon
            icon={ZoomInAreaIcon}
            className="h-4 w-4"
            strokeWidth={1.7}
          />
        </button>
        <button
          onClick={() => handleZoom("out")}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-white/40 transition-colors hover:bg-white/[0.07] hover:text-white/80"
        >
          <HugeiconsIcon
            icon={ZoomOutAreaIcon}
            className="h-4 w-4"
            strokeWidth={1.7}
          />
        </button>
        <div className="my-0.5 h-px w-full bg-white/[0.06]" />
        <button
          onClick={handleFit}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-white/40 transition-colors hover:bg-white/[0.07] hover:text-white/80"
        >
          <HugeiconsIcon
            icon={Maximize02Icon}
            className="h-4 w-4"
            strokeWidth={1.7}
          />
        </button>
      </div>

      {/* Zoom level badge */}
      <div className="dashboard-control-surface absolute bottom-32 left-16 z-20 rounded-lg px-2 py-1 sm:bottom-36">
        <span
          ref={setZoomLabelRef}
          className="font-mono text-[10px] text-white/30"
        >
          {Math.round(DEFAULT_GRAPH_TRANSFORM.scale * 100)}%
        </span>
      </div>

      {/* Detail panel */}
      {selectedNode && panelVisible && (
        <div
          ref={drawerRef}
          className="dashboard-drawer panel-slide-in absolute z-30 flex max-h-[calc(100%-2rem)] w-[18rem] max-w-[calc(100%-2rem)] flex-col"
          style={{
            ...drawerSurfaceStyle,
            left: drawerPosition?.x ?? 16,
            top: drawerPosition?.y ?? 16,
          }}
        >
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.06), transparent 22%, transparent 72%, rgba(255,255,255,0.025))",
            }}
          />
          {/* Panel header */}
          <div
            className="relative flex cursor-grab items-start justify-between gap-2 border-b border-white/[0.06] px-4 py-3 active:cursor-grabbing"
            onPointerDown={handleDrawerPointerDown}
          >
            <div className="min-w-0 flex-1">
              <p className="mb-1 text-[10px] font-medium tracking-[0.2em] text-white/30 uppercase">
                {selectedMfr
                  ? "Manufacturer"
                  : selectedBaseNode?.kind === "product"
                    ? "Product"
                    : "Component"}
              </p>
              <h3 className="text-[13px] leading-snug font-semibold text-white/88">
                {selectedMfr ? selectedMfr.name : selectedBaseNode?.label}
              </h3>
              {selectedMfr && (
                <p className="mt-0.5 text-[11px] text-white/35">
                  {selectedMfr.location.city}, {selectedMfr.location.country}
                </p>
              )}
            </div>
            <button
              onClick={() => onSelectNode(null)}
              onPointerDown={(event) => event.stopPropagation()}
              className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md border border-white/[0.06] text-white/25 transition-colors hover:bg-white/[0.05] hover:text-white/60"
            >
              <HugeiconsIcon
                icon={Cancel01Icon}
                className="h-3.5 w-3.5"
                strokeWidth={1.8}
              />
            </button>
          </div>

          {selectedMfr && ecoConfig && (
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pb-4">
              {(() => {
                const status = getManufacturerStatusPresentation(
                  selectedMfr.isCurrent
                )

                return (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span
                      className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] font-medium tracking-[0.12em]"
                      style={{
                        background:
                          "color-mix(in oklab, rgb(10 11 18) 74%, transparent)",
                        borderColor: status.badgeBorder,
                        color: status.badgeText,
                      }}
                    >
                      <span
                        className={cn(
                          "eco-pulse inline-block h-1 w-1 rounded-full",
                          status.pulseClassName
                        )}
                      />
                      {status.label}
                    </span>
                    <span className="dashboard-chip-muted">
                      {selectedMfr.componentLabel}
                    </span>
                  </div>
                )
              })()}

              <div
                className="dashboard-drawer-section rounded-lg p-3"
                style={{
                  ...drawerSectionStyle,
                  border: `1px solid ${ecoConfig.panelBorder}`,
                }}
              >
                <div className="flex items-start gap-3">
                  <EcoScoreRing
                    score={selectedMfr.ecoScore}
                    size={54}
                    strokeWidth={4}
                  />
                  <div className="min-w-0 flex-1 space-y-2">
                    {[
                      {
                        label: "Selected q50",
                        value: formatTco2e(
                          getEstimatedRouteTotalTco2e(selectedMfr)
                        ),
                      },
                      {
                        label: "Manufacturing q50",
                        value: formatTco2e(
                          selectedMfr.manufacturingEmissionsTco2e.q50
                        ),
                      },
                      {
                        label: "Transport",
                        value: formatTco2e(selectedMfr.transportEmissionsTco2e),
                      },
                      {
                        label: "Climate risk",
                        value: formatScore(selectedMfr.climateRiskScore),
                      },
                    ].map((item) => (
                      <div
                        key={item.label}
                        className="flex items-center justify-between gap-3 text-[11px]"
                      >
                        <span className="text-white/38">{item.label}</span>
                        <span className="text-right font-semibold whitespace-nowrap text-white/84">
                          {item.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {selectedMfr.certifications.length > 0 ? (
                <div>
                  <p className="mb-1.5 text-[9px] font-medium tracking-[0.18em] text-white/25 uppercase">
                    Certifications
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedMfr.certifications.map((cert) => (
                      <span key={cert} className="dashboard-chip-accent">
                        {CERT_LABELS[cert] ?? cert}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {selectedMfr.industry ? (
                <div>
                  <p className="mb-1.5 text-[9px] font-medium tracking-[0.18em] text-white/25 uppercase">
                    Industry basis
                  </p>
                  <p className="text-[11px] leading-relaxed text-white/70">
                    {selectedMfr.industry.title}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-white/35">
                    NAICS {selectedMfr.industry.code} · USEEIO emission factor
                  </p>
                </div>
              ) : null}
            </div>
          )}

          {!selectedMfr && (
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 pb-4">
              {selectedBaseNode?.kind === "product" ? (
                <>
                  <div
                    className="dashboard-drawer-section rounded-xl p-4"
                    style={{
                      ...drawerSectionStyle,
                      background:
                        "linear-gradient(180deg, color-mix(in oklab, var(--primary) 8%, rgb(18 20 28 / 0.98)), rgb(13 15 22 / 0.98))",
                      borderColor:
                        "color-mix(in oklab, var(--primary) 16%, transparent)",
                    }}
                  >
                    <p className="text-xs leading-relaxed text-white/54">
                      {scenario.quantity.toLocaleString()} {scenario.unit} of{" "}
                      {scenario.title} route into{" "}
                      {scenario.destination.location.city},{" "}
                      {scenario.destination.location.country}. The current
                      selection spans {formatCount(selectedRouteCountryCount)}{" "}
                      countries with an estimated q50 footprint of{" "}
                      {formatTco2e(selectedRouteTotalTco2e)} across{" "}
                      {formatCount(selectedManufacturers.length)} active
                      supplier nodes.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5">
                    <DrawerMetricCard
                      label="Quantity"
                      value={`${formatCount(scenario.quantity)} ${scenario.unit}`}
                    />
                    <DrawerMetricCard
                      label="Components"
                      value={formatCount(visibleComponents.length)}
                    />
                    <DrawerMetricCard
                      label="Supplier nodes"
                      value={formatCount(visibleManufacturers.length)}
                    />
                    <DrawerMetricCard
                      label="Network countries"
                      value={formatCount(visibleManufacturerCountryCount)}
                    />
                  </div>

                  <div>
                    <p className="mb-2 text-[9px] font-medium tracking-[0.18em] text-white/25 uppercase">
                      Component routing
                    </p>
                    <div className="space-y-2">
                      {selectedPathEntries.map(({ component, insight }) => {
                        const selectedManufacturer = insight.selected
                        const currentManufacturer = insight.current
                        const bestManufacturer = insight.best

                        if (!selectedManufacturer) {
                          return null
                        }

                        const selectedEco = getEcoConfig(
                          selectedManufacturer.ecoScore
                        )

                        return (
                          <div
                            key={component.id}
                            className="dashboard-drawer-section rounded-lg p-3"
                            style={drawerSectionStyle}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-xs font-semibold text-white/84">
                                  {component.label}
                                </p>
                                <p className="mt-1 text-[10px] leading-relaxed text-white/36">
                                  Selected: {selectedManufacturer.name}
                                </p>
                                <p className="text-[10px] leading-relaxed text-white/30">
                                  {selectedManufacturer.location.country}
                                  {currentManufacturer &&
                                  currentManufacturer.id !==
                                    selectedManufacturer.id
                                    ? ` · Current: ${currentManufacturer.name}`
                                    : " · Current route retained"}
                                </p>
                                {bestManufacturer &&
                                bestManufacturer.id !==
                                  selectedManufacturer.id ? (
                                  <p className="text-[10px] leading-relaxed text-white/30">
                                    Best eco: {bestManufacturer.name}
                                  </p>
                                ) : null}
                              </div>
                              <div className="text-right">
                                <p
                                  className="text-xs font-semibold"
                                  style={{ color: selectedEco.color }}
                                >
                                  {formatScore(selectedManufacturer.ecoScore)}
                                </p>
                                <p className="mt-1 font-mono text-[10px] text-white/38">
                                  {formatTco2e(
                                    getEstimatedRouteTotalTco2e(
                                      selectedManufacturer
                                    )
                                  )}
                                </p>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </>
              ) : selectedBaseNode?.kind === "component" ? (
                (() => {
                  const insight = componentInsightsById.get(selectedBaseNode.id)
                  const manufacturers = insight?.manufacturers ?? []
                  const currentManufacturer = insight?.current ?? null
                  const selectedManufacturer = insight?.selected ?? null
                  const bestManufacturer = insight?.best ?? null
                  const countries = new Set(
                    manufacturers.map(
                      (manufacturer) => manufacturer.location.countryCode
                    )
                  )
                  const routeCards: Array<{
                    highlighted?: boolean
                    label: string
                    manufacturer: SupplyScenarioManufacturerNode
                  }> = []
                  const addRouteCard = (
                    label: string,
                    manufacturer: SupplyScenarioManufacturerNode | null,
                    highlighted = false
                  ) => {
                    if (!manufacturer) {
                      return
                    }

                    const existingCard = routeCards.find(
                      (card) => card.manufacturer.id === manufacturer.id
                    )

                    if (existingCard) {
                      existingCard.label = `${existingCard.label} / ${label}`
                      existingCard.highlighted =
                        existingCard.highlighted || highlighted
                      return
                    }

                    routeCards.push({
                      highlighted,
                      label,
                      manufacturer,
                    })
                  }

                  addRouteCard("Selected route", selectedManufacturer, true)

                  if (
                    currentManufacturer &&
                    currentManufacturer.id !== selectedManufacturer?.id
                  ) {
                    addRouteCard("Current route", currentManufacturer)
                  }

                  if (
                    bestManufacturer &&
                    bestManufacturer.id !== selectedManufacturer?.id &&
                    bestManufacturer.id !== currentManufacturer?.id
                  ) {
                    addRouteCard("Best eco", bestManufacturer)
                  }

                  return (
                    <>
                      <div className="flex flex-wrap gap-1.5">
                        <span className="dashboard-chip-muted">
                          {formatCount(manufacturers.length)} suppliers
                        </span>
                        <span className="dashboard-chip-muted">
                          {formatCount(countries.size)} countries
                        </span>
                        {selectedManufacturer &&
                        currentManufacturer &&
                        selectedManufacturer.id !== currentManufacturer.id ? (
                          <span className="dashboard-chip-accent">
                            Rerouted
                          </span>
                        ) : null}
                      </div>

                      {routeCards.length > 0 ? (
                        <div className="space-y-2">
                          {routeCards.map((card) => (
                            <RouteComparisonCard
                              key={`${card.label}-${card.manufacturer.id}`}
                              label={card.label}
                              manufacturer={card.manufacturer}
                              accent={
                                getEcoConfig(card.manufacturer.ecoScore).color
                              }
                              highlighted={card.highlighted}
                            />
                          ))}
                        </div>
                      ) : (
                        <div
                          className="dashboard-drawer-section rounded-lg p-3"
                          style={drawerSectionStyle}
                        >
                          <p className="text-[11px] text-white/44">
                            No supplier routes available for this component.
                          </p>
                        </div>
                      )}
                    </>
                  )
                })()
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  )
})

// ---------------------------------------------------------------------------
// Node card renderer (extracted to keep JSX readable)
// ---------------------------------------------------------------------------

const NodeCard = React.memo(
  function NodeCard({
    allowIdleFloat,
    interactionMode,
    isDragging,
    node,
    isSelected,
    isHovered,
    motionIndex,
  }: {
    allowIdleFloat: boolean
    interactionMode: boolean
    isDragging: boolean
    node: GraphNodeState
    isSelected: boolean
    isHovered: boolean
    motionIndex: number
  }) {
    const d = node.data
    const shouldFloat = !interactionMode && !isDragging && allowIdleFloat
    const shouldEmphasize = !interactionMode && (isSelected || isHovered)

    if (d.kind === "product") {
      return (
        <div
          className={cn(
            "relative flex h-full w-full flex-col items-center overflow-hidden rounded-[20px] px-3 pt-3.5 pb-4",
            shouldFloat ? "node-breathe" : ""
          )}
          style={{
            animationDelay: `${motionIndex * 0.3}s`,
            background:
              "linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.012) 16%, transparent 22%), linear-gradient(180deg, color-mix(in oklab, var(--primary) 6%, rgba(10,10,20,0.92)), rgba(10,10,20,0.9) 46%, rgba(8,8,14,0.96) 100%)",
            border: `1px solid ${isSelected ? "color-mix(in oklab, var(--primary) 42%, white 4%)" : isHovered ? "color-mix(in oklab, var(--accent) 24%, transparent)" : "rgba(255,255,255,0.07)"}`,
            boxShadow: interactionMode
              ? isSelected
                ? "0 10px 20px rgba(0,0,0,0.32), inset 0 1px 0 rgba(255,255,255,0.05)"
                : isHovered
                  ? "0 8px 16px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.04)"
                  : "0 2px 10px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.03)"
              : isSelected
                ? "0 14px 30px rgba(0,0,0,0.42), 0 0 0 1px color-mix(in oklab, var(--primary) 14%, transparent), inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -12px 22px rgba(0,0,0,0.18)"
                : isHovered
                  ? "0 10px 22px rgba(0,0,0,0.38), 0 0 0 1px color-mix(in oklab, var(--accent) 10%, transparent), inset 0 1px 0 rgba(255,255,255,0.05), inset 0 -10px 18px rgba(0,0,0,0.16)"
                  : "0 4px 16px rgba(0,0,0,0.34), inset 0 1px 0 rgba(255,255,255,0.04), inset 0 -10px 16px rgba(0,0,0,0.14)",
            transition: "border-color 0.3s, box-shadow 0.3s",
          }}
        >
          <div
            className="pointer-events-none absolute inset-x-3 top-0 h-px rounded-full"
            style={{
              background:
                "linear-gradient(90deg, transparent, rgba(255,255,255,0.09), transparent)",
              opacity: isSelected ? 0.82 : isHovered ? 0.58 : 0.38,
            }}
          />
          <div
            className={cn(
              "pointer-events-none absolute inset-0 rounded-[20px]",
              !interactionMode ? "node-breathe-sheen" : ""
            )}
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.038), transparent 34%)",
            }}
          />
          {isSelected && (
            <div
              className="absolute inset-[2px] rounded-[18px]"
              style={{
                border:
                  "1px solid color-mix(in oklab, var(--primary) 12%, transparent)",
                opacity: 0.82,
              }}
            />
          )}
          <div className="text-[9px] tracking-[0.18em] text-white/30 uppercase">
            Product
          </div>
          <div className="mt-2 flex flex-1 flex-col items-center justify-center">
            <div
              className={cn(
                "mb-2 rounded-lg p-2",
                shouldEmphasize ? "emblem-pulse" : ""
              )}
              style={{
                background:
                  "color-mix(in oklab, var(--primary) 14%, transparent)",
                border:
                  "1px solid color-mix(in oklab, var(--primary) 24%, transparent)",
              }}
            >
              <HugeiconsIcon
                icon={Leaf01Icon}
                className="h-4 w-4 text-white/80"
                strokeWidth={1.8}
              />
            </div>
            <p className="px-2 text-center text-xs leading-tight font-semibold text-white/88">
              {d.label}
            </p>
            <p className="mt-1 text-[10px] text-white/30">{d.subtitle}</p>
          </div>
        </div>
      )
    }

    if (d.kind === "component") {
      return (
        <div
          className={cn(
            "relative flex h-full w-full items-center gap-2.5 overflow-hidden rounded-xl px-3",
            shouldFloat ? "node-breathe" : ""
          )}
          style={{
            animationDelay: `${motionIndex * 0.3}s`,
            background: isSelected
              ? "linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.01) 16%, transparent 22%), linear-gradient(180deg, color-mix(in oklab, var(--primary) 5%, rgba(10,10,18,0.88)), rgba(10,10,18,0.84) 42%, rgba(8,8,14,0.9) 100%)"
              : "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.008) 16%, transparent 22%), linear-gradient(180deg, rgba(10,10,18,0.76), rgba(10,10,18,0.72) 44%, rgba(8,8,14,0.82) 100%)",
            border: `1px solid ${isSelected ? "color-mix(in oklab, var(--primary) 40%, white 4%)" : isHovered ? "color-mix(in oklab, var(--accent) 22%, transparent)" : "rgba(255,255,255,0.07)"}`,
            boxShadow: interactionMode
              ? isSelected
                ? "0 8px 16px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.035)"
                : isHovered
                  ? "0 6px 14px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.03)"
                  : "0 2px 10px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.025)"
              : isSelected
                ? "0 12px 24px rgba(0,0,0,0.34), 0 0 0 1px color-mix(in oklab, var(--primary) 12%, transparent), inset 0 1px 0 rgba(255,255,255,0.045), inset 0 -10px 18px rgba(0,0,0,0.14)"
                : isHovered
                  ? "0 8px 18px rgba(0,0,0,0.3), 0 0 0 1px color-mix(in oklab, var(--accent) 10%, transparent), inset 0 1px 0 rgba(255,255,255,0.035), inset 0 -8px 14px rgba(0,0,0,0.12)"
                  : "0 4px 14px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.03), inset 0 -8px 14px rgba(0,0,0,0.1)",
            transition: "border-color 0.25s, box-shadow 0.25s",
          }}
        >
          <div
            className="pointer-events-none absolute inset-x-3 top-0 h-px rounded-full"
            style={{
              background:
                "linear-gradient(90deg, transparent, rgba(255,255,255,0.08), transparent)",
              opacity: isSelected ? 0.8 : isHovered ? 0.55 : 0.38,
            }}
          />
          <div
            className={cn(
              "pointer-events-none absolute inset-0 rounded-xl",
              !interactionMode ? "node-breathe-sheen" : ""
            )}
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.038), transparent 34%)",
            }}
          />
          {/* Left accent stripe */}
          <div
            className="absolute top-3 bottom-3 left-0 w-[2px] rounded-full"
            style={{
              background:
                "linear-gradient(180deg, color-mix(in oklab, var(--primary) 82%, white 6%), color-mix(in oklab, var(--accent) 46%, transparent))",
            }}
          />
          <div
            className={cn(
              "absolute top-3 bottom-3 left-0 w-[2px] rounded-full",
              shouldEmphasize ? "focus-beacon" : ""
            )}
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.18), color-mix(in oklab, var(--primary) 68%, transparent), transparent)",
              opacity: isSelected ? 0.8 : isHovered ? 0.56 : 0,
            }}
          />
          <div
            className={cn(
              "flex-shrink-0 rounded-lg p-1.5",
              shouldEmphasize ? "emblem-pulse" : ""
            )}
            style={{
              background:
                "color-mix(in oklab, var(--primary) 10%, transparent)",
              border:
                "1px solid color-mix(in oklab, var(--primary) 18%, transparent)",
            }}
          >
            <HugeiconsIcon
              icon={PuzzleIcon}
              className="h-4 w-4 text-white/80"
              strokeWidth={1.8}
            />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-white/85">
              {d.label}
            </p>
            <p className="mt-0.5 text-[9px] tracking-wide text-white/30 uppercase">
              Component
            </p>
          </div>
        </div>
      )
    }

    if (d.kind === "manufacturer") {
      const eco = getEcoConfig(d.ecoScore)
      const status = getManufacturerStatusPresentation(d.isCurrent)
      const manufacturerSurface = isSelected
        ? `linear-gradient(180deg, rgba(255,255,255,0.065), rgba(255,255,255,0.015) 16%, transparent 24%), ${eco.panelBg}`
        : isHovered
          ? `linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.012) 16%, transparent 24%), linear-gradient(180deg, rgba(16,16,28,0.985), rgba(11,11,21,0.97) 48%, rgba(8,8,16,0.985) 100%)`
          : "linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.008) 18%, transparent 24%), linear-gradient(180deg, rgba(13,13,24,0.985), rgba(10,10,19,0.975) 48%, rgba(8,8,15,0.988) 100%)"
      return (
        <div
          className={cn(
            "relative flex h-full w-full flex-col justify-between overflow-hidden rounded-xl p-3",
            shouldFloat ? "node-breathe" : ""
          )}
          style={{
            animationDelay: `${motionIndex * 0.3}s`,
            WebkitBackdropFilter: interactionMode
              ? "none"
              : isSelected || isHovered
                ? "blur(18px) saturate(135%)"
                : "blur(12px) saturate(115%)",
            backdropFilter: interactionMode
              ? "none"
              : isSelected || isHovered
                ? "blur(18px) saturate(135%)"
                : "blur(12px) saturate(115%)",
            background: manufacturerSurface,
            border: `1px solid ${isSelected ? eco.panelBorder : isHovered ? "color-mix(in oklab, var(--accent) 22%, transparent)" : "rgba(255,255,255,0.10)"}`,
            boxShadow: interactionMode
              ? isSelected
                ? `0 10px 20px rgba(0,0,0,0.34), 0 0 0 1px ${eco.panelBorder}, inset 0 1px 0 rgba(255,255,255,0.045)`
                : isHovered
                  ? "0 8px 16px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.04)"
                  : "0 3px 12px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.03)"
              : isSelected
                ? `0 18px 34px rgba(0,0,0,0.54), 0 0 0 1px ${eco.panelBorder}, 0 0 28px ${eco.ring}, inset 0 1px 0 rgba(255,255,255,0.065), inset 0 -12px 22px rgba(0,0,0,0.22)`
                : isHovered
                  ? "0 12px 24px rgba(0,0,0,0.44), 0 0 0 1px color-mix(in oklab, var(--accent) 10%, transparent), inset 0 1px 0 rgba(255,255,255,0.05), inset 0 -10px 16px rgba(0,0,0,0.16)"
                  : "0 7px 18px rgba(0,0,0,0.44), inset 0 1px 0 rgba(255,255,255,0.035), inset 0 -10px 16px rgba(0,0,0,0.14)",
            transition: interactionMode
              ? "border-color 0.2s, box-shadow 0.2s"
              : "border-color 0.25s, box-shadow 0.25s, backdrop-filter 0.25s",
          }}
        >
          <div
            className="pointer-events-none absolute inset-x-3 top-0 h-px rounded-full"
            style={{
              background:
                "linear-gradient(90deg, transparent, rgba(255,255,255,0.07), transparent)",
              opacity: isSelected ? 0.92 : isHovered ? 0.66 : 0.42,
            }}
          />
          <div
            className={cn(
              "pointer-events-none absolute inset-0 rounded-xl",
              !interactionMode ? "node-breathe-sheen" : ""
            )}
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.04), transparent 34%)",
            }}
          />
          {/* Subtle inner gradient */}
          <div
            className="pointer-events-none absolute inset-0 rounded-xl"
            style={{
              background:
                "linear-gradient(180deg, color-mix(in oklab, var(--primary) 3%, transparent), transparent 38%)",
            }}
          />

          <div className="relative flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p
                className="line-clamp-2 text-[13px] leading-tight font-semibold text-white/96"
                style={{ textShadow: "0 1px 8px rgba(0,0,0,0.34)" }}
              >
                {d.name}
              </p>
              <p
                className="mt-0.5 text-[10px] text-white/52"
                style={{ textShadow: "0 1px 6px rgba(0,0,0,0.28)" }}
              >
                {d.location.city}, {d.location.country}
              </p>
            </div>
            <span
              className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[8px] font-bold tracking-wide"
              style={{
                background: status.badgeBackground,
                color: status.badgeText,
                border: `1px solid ${status.badgeBorder}`,
              }}
            >
              <span
                className={cn(
                  "eco-pulse inline-block h-1 w-1 rounded-full",
                  status.pulseClassName
                )}
              />
              {status.label}
            </span>
          </div>

          <div
            className="relative flex items-center gap-2 pt-2"
            style={{ borderTop: "1px solid rgba(255,255,255,0.10)" }}
          >
            <div className="flex-1">
              <p className="mb-0.5 text-[9px] text-white/42">Eco Score</p>
              <div className="flex items-center gap-1.5">
                {/* Mini bar */}
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/[0.11]">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${d.ecoScore}%`,
                      background: eco.color,
                      boxShadow: `0 0 4px ${eco.color}`,
                    }}
                  />
                </div>
                <span
                  className="text-[11px] font-bold tabular-nums"
                  style={{
                    color: eco.color,
                    textShadow: `0 0 10px ${eco.ring}`,
                  }}
                >
                  {d.ecoScore}
                </span>
              </div>
            </div>
            <div className="flex-shrink-0">
              <div
                className="flex h-7 w-7 items-center justify-center rounded-lg"
                style={{ background: eco.bg, border: `1px solid ${eco.ring}` }}
              >
                <HugeiconsIcon
                  icon={Factory01Icon}
                  className="h-3.5 w-3.5"
                  strokeWidth={1.8}
                  style={{ color: eco.color }}
                />
              </div>
            </div>
          </div>
        </div>
      )
    }

    return null
  },
  (previousProps, nextProps) =>
    previousProps.allowIdleFloat === nextProps.allowIdleFloat &&
    previousProps.interactionMode === nextProps.interactionMode &&
    previousProps.isDragging === nextProps.isDragging &&
    previousProps.isHovered === nextProps.isHovered &&
    previousProps.isSelected === nextProps.isSelected &&
    previousProps.motionIndex === nextProps.motionIndex &&
    previousProps.node.id === nextProps.node.id &&
    previousProps.node.data === nextProps.node.data
)
