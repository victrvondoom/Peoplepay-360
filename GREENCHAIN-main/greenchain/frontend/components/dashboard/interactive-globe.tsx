"use client"

import {
  memo,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import { getEcoRoutePalette, withAlpha } from "@/lib/eco-visuals"
import { type GlobeGeoPoint } from "@/lib/globe-geometry"
import {
  DEFAULT_GLOBE_GEOMETRY,
  loadGlobeGeometry,
} from "@/lib/natural-earth-globe"
import {
  type SupplyScenario,
  type SupplyScenarioLocation,
  type SupplyScenarioSelectableNodeId,
} from "@/lib/supply-chain-scenario"
import { cn } from "@/lib/utils"

interface InteractiveGlobeProps {
  bestEcoManufacturerByComponent: Record<string, string>
  className?: string
  hoveredNodeId: SupplyScenarioSelectableNodeId | null
  onHoverNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onSelectNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  pinnedManufacturerByComponent: Record<string, string>
  routeVisibleByComponent: Record<string, boolean>
  scenario: SupplyScenario
  selectedNodeId: SupplyScenarioSelectableNodeId | null
}

interface Vector3 {
  x: number
  y: number
  z: number
}

interface RotationState {
  pitch: number
  yaw: number
}

interface DragState {
  pointerId: number
  timestamp: number
  x: number
  y: number
}

interface ProjectedPoint {
  depth: number
  radial: number
  visible: boolean
  x: number
  y: number
}

interface RouteModel {
  componentId: string
  ecoScore: number
  id: string
  isCurrent: boolean
  isMostSustainable: boolean
  manufacturerId: string
  points: Vector3[]
}

interface RouteVisualStyle {
  coreColor: string
  coreOpacity: number
  coreWidth: number
  glowColor: string
  glowOpacity: number
  glowWidth: number
  highlightCore: string
  highlightGlowSoft: string
  highlightGlowStrong: string
  priority: number
  pulseColor: string
  pulseDash: string
  pulseDuration: string
  pulseOpacity: number
  pulseWidth: number
}

interface RouteCaptionModel {
  angle: number
  componentId: string
  height: number
  isFocused: boolean
  label: string
  manufacturerId: string
  priority: number
  routeId: string
  style: RouteVisualStyle
  width: number
  x: number
  y: number
}

interface AnimatedRouteCaptionModel extends RouteCaptionModel {
  opacity: number
}

interface RouteCaptionAnimationState {
  angle: number
  model: RouteCaptionModel
  opacity: number
  x: number
  y: number
}

interface DestinationLabelModel {
  height: number
  label: string
  side: -1 | 1
  width: number
  x: number
  y: number
}

interface FocusState {
  componentId?: string
  manufacturerId?: string
  product?: boolean
}

const GLOBE_CENTER = 50
const GLOBE_RADIUS = 40
const AUTO_ROTATION_SPEED = 0.000032
const DRAG_SENSITIVITY = 0.0065
const MAX_PITCH = Math.PI / 3
const ROUTE_SEGMENTS = 72
const CONTINENT_SUBDIVISIONS = 20
const COUNTRY_SUBDIVISIONS = 12
const PITCH_VELOCITY_DECAY = 0.94
const YAW_VELOCITY_DECAY = 0.9
const FRONT_PATH_THRESHOLD = 0
const BACK_PATH_THRESHOLD = -0.18
const ROUTE_FRONT_SURFACE_PADDING = 0.004
const MAX_CANVAS_PIXEL_RATIO = 2
const ROTATION_EPSILON = 1e-7
const VELOCITY_EPSILON = 1e-6
const CAPTION_SETTLE_EPSILON = 0.01
const ROUTE_CAPTION_CANDIDATE_PROGRESS = [0.24, 0.34, 0.43] as const
const ROUTE_CAPTION_EASING = 0.18
const ROUTE_CAPTION_FADE_EASING = 0.24
const ROUTE_CAPTION_OFFSET = 2.1
const ROUTE_CAPTION_MARGIN_X = 5.5
const ROUTE_CAPTION_MARGIN_Y = 5.8
const ROUTE_CAPTION_MAX_LENGTH = 18
const INITIAL_DESTINATION_HOLD_MS = 900
const GRID_LATITUDES_PRIMARY = [-60, -36, -12, 12, 36, 60]
const GRID_LATITUDES_SECONDARY = [-72, -48, -24, 0, 24, 48, 72]
const GRID_LONGITUDES_PRIMARY = [
  -150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150,
]
const GRID_LONGITUDES_SECONDARY = [
  -165, -135, -105, -75, -45, -15, 15, 45, 75, 105, 135, 165,
]
const PRODUCT_ORBIT = {
  control: { x: 84, y: 86 },
  end: { x: 96, y: 74 },
  start: { x: 69, y: 90 },
}
const GLOBE_SURFACE_THEME = {
  atmosphereHalo: "rgba(218,240,232,0.1)",
  atmosphereRim: "rgba(222,243,236,0.16)",
  atmosphereStroke: "rgba(216,236,228,0.12)",
  backGrid: "rgba(255,255,255,0.04)",
  countryBack: "rgba(240,246,243,0.045)",
  countryFront: "rgba(238,245,241,0.26)",
  countryGlow: "rgba(208,231,221,0.08)",
  coreShadowStrong: "rgba(0,0,0,0.34)",
  coreShadowWeak: "rgba(0,0,0,0.02)",
  destinationFill: "rgba(255,255,255,0.94)",
  destinationGlow: "rgba(158,198,184,0.12)",
  destinationStroke: "rgba(208,229,220,0.26)",
  labelFill: "rgba(7,12,15,0.8)",
  labelFillStrong: "rgba(7,12,15,0.9)",
  labelStroke: "rgba(226,240,234,0.14)",
  labelText: "rgba(241,248,244,0.95)",
  orbitStroke: "rgba(148,183,171,0.16)",
  productActiveStroke: "rgba(121,194,168,0.38)",
  productStroke: "rgba(220,236,228,0.12)",
  rimStroke: "rgba(228,242,236,0.18)",
  secondaryGrid: "rgba(255,255,255,0.052)",
  shadowFill: "rgba(4,8,10,0.32)",
  surfaceEdge: "rgba(255,255,255,0)",
  surfaceHighlight: "rgba(235,245,240,0.09)",
  surfaceMid: "rgba(130,171,157,0.03)",
  terminatorStroke: "rgba(214,234,226,0.2)",
  titleMuted: "rgba(205,220,213,0.76)",
}

function degreesToRadians(value: number) {
  return (value * Math.PI) / 180
}

function radiansToDegrees(value: number) {
  return (value * 180) / Math.PI
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function roundForSvg(value: number, digits = 6) {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function toGeoPoint(location: SupplyScenarioLocation): GlobeGeoPoint {
  return {
    lat: location.lat,
    lon: location.lng,
  }
}

function toVector({ lat, lon }: GlobeGeoPoint): Vector3 {
  const latRadians = degreesToRadians(lat)
  const lonRadians = degreesToRadians(lon)

  return {
    x: Math.cos(latRadians) * Math.sin(lonRadians),
    y: Math.sin(latRadians),
    z: Math.cos(latRadians) * Math.cos(lonRadians),
  }
}

function normalizeVector(vector: Vector3) {
  const magnitude = Math.hypot(vector.x, vector.y, vector.z) || 1

  return {
    x: vector.x / magnitude,
    y: vector.y / magnitude,
    z: vector.z / magnitude,
  }
}

function rotateVector(
  vector: Vector3,
  { pitch, yaw }: RotationState
): ProjectedPoint {
  const sinYaw = Math.sin(yaw)
  const cosYaw = Math.cos(yaw)
  const yawedX = vector.x * cosYaw + vector.z * sinYaw
  const yawedZ = vector.z * cosYaw - vector.x * sinYaw

  const sinPitch = Math.sin(pitch)
  const cosPitch = Math.cos(pitch)
  const pitchedY = vector.y * cosPitch - yawedZ * sinPitch
  const pitchedZ = yawedZ * cosPitch + vector.y * sinPitch

  return {
    depth: pitchedZ,
    radial: Math.hypot(yawedX, pitchedY),
    visible: pitchedZ > 0,
    x: GLOBE_CENTER + yawedX * GLOBE_RADIUS,
    y: GLOBE_CENTER - pitchedY * GLOBE_RADIUS,
  }
}

function projectGeoPoint(point: GlobeGeoPoint, rotation: RotationState) {
  return rotateVector(toVector(point), rotation)
}

function getDestinationCenteredRotation(
  location: SupplyScenarioLocation
): RotationState {
  return {
    pitch: clamp(degreesToRadians(location.lat), -MAX_PITCH, MAX_PITCH),
    yaw: degreesToRadians(-location.lng),
  }
}

/**
 * Same projection as {@link projectGeoPoint}, with x/y/depth/radial rounded so
 * SVG attributes match between SSR (Node) and the browser — unrounded trig can
 * differ at the last binary digit and trigger hydration warnings.
 */
function projectGeoPointStable(point: GlobeGeoPoint, rotation: RotationState) {
  const projected = projectGeoPoint(point, rotation)

  return {
    ...projected,
    depth: roundForSvg(projected.depth),
    radial: roundForSvg(projected.radial),
    x: roundForSvg(projected.x),
    y: roundForSvg(projected.y),
  }
}

function wrapLongitude(value: number) {
  const wrapped = ((((value + 180) % 360) + 360) % 360) - 180
  return wrapped === -180 ? 180 : wrapped
}

function shortestLongitudeDelta(from: number, to: number) {
  let delta = to - from

  while (delta > 180) {
    delta -= 360
  }

  while (delta < -180) {
    delta += 360
  }

  return delta
}

function pointsMatch(left: GlobeGeoPoint, right: GlobeGeoPoint) {
  return (
    Math.abs(left.lat - right.lat) < 0.001 &&
    Math.abs(left.lon - right.lon) < 0.001
  )
}

function catmullRom(
  previous: number,
  start: number,
  end: number,
  next: number,
  progress: number
) {
  const squared = progress * progress
  const cubed = squared * progress

  return (
    0.5 *
    (2 * start +
      (-previous + end) * progress +
      (2 * previous - 5 * start + 4 * end - next) * squared +
      (-previous + 3 * start - 3 * end + next) * cubed)
  )
}

function interpolateGeoPath(
  points: GlobeGeoPoint[],
  subdivisions: number
): GlobeGeoPoint[] {
  if (points.length < 2) {
    return points
  }

  const closed =
    points.length > 2 && pointsMatch(points[0], points[points.length - 1])
  const source = closed ? points.slice(0, -1) : points

  if (source.length < 2) {
    return points
  }

  const longitudes = [source[0].lon]

  for (let index = 1; index < source.length; index += 1) {
    longitudes[index] =
      longitudes[index - 1] +
      shortestLongitudeDelta(source[index - 1].lon, source[index].lon)
  }

  const getIndex = (index: number) => {
    if (closed) {
      return (index + source.length) % source.length
    }

    return clamp(index, 0, source.length - 1)
  }

  const sampled: GlobeGeoPoint[] = []
  const segmentCount = closed ? source.length : source.length - 1

  for (let index = 0; index < segmentCount; index += 1) {
    const previousIndex = getIndex(index - 1)
    const startIndex = getIndex(index)
    const endIndex = getIndex(index + 1)
    const nextIndex = getIndex(index + 2)

    for (let step = 0; step < subdivisions; step += 1) {
      const progress = step / subdivisions

      sampled.push({
        lat: clamp(
          catmullRom(
            source[previousIndex].lat,
            source[startIndex].lat,
            source[endIndex].lat,
            source[nextIndex].lat,
            progress
          ),
          -89.5,
          89.5
        ),
        lon: wrapLongitude(
          catmullRom(
            longitudes[previousIndex],
            longitudes[startIndex],
            longitudes[endIndex],
            longitudes[nextIndex],
            progress
          )
        ),
      })
    }
  }

  const finalIndex = source.length - 1
  sampled.push(
    closed
      ? source[0]
      : {
          lat: source[finalIndex].lat,
          lon: wrapLongitude(longitudes[finalIndex]),
        }
  )

  return sampled
}

/** Polylines flattened to unit vectors so per-frame projection needs no trig. */
interface PolylineSet {
  offsets: Uint32Array
  xyz: Float32Array
}

function createPolylineSet(lines: GlobeGeoPoint[][]): PolylineSet {
  let pointCount = 0

  for (const line of lines) {
    pointCount += line.length
  }

  const xyz = new Float32Array(pointCount * 3)
  const offsets = new Uint32Array(lines.length + 1)
  let cursor = 0

  lines.forEach((line, lineIndex) => {
    offsets[lineIndex] = cursor

    for (const point of line) {
      const vector = toVector(point)
      xyz[cursor * 3] = vector.x
      xyz[cursor * 3 + 1] = vector.y
      xyz[cursor * 3 + 2] = vector.z
      cursor += 1
    }
  })
  offsets[lines.length] = cursor

  return { offsets, xyz }
}

function traceHemispheres(
  { offsets, xyz }: PolylineSet,
  { pitch, yaw }: RotationState,
  front: Path2D | null,
  back: Path2D | null
) {
  const sinYaw = Math.sin(yaw)
  const cosYaw = Math.cos(yaw)
  const sinPitch = Math.sin(pitch)
  const cosPitch = Math.cos(pitch)

  for (let line = 0; line < offsets.length - 1; line += 1) {
    let frontOpen = false
    let backOpen = false

    for (let index = offsets[line]; index < offsets[line + 1]; index += 1) {
      const x = xyz[index * 3]
      const y = xyz[index * 3 + 1]
      const z = xyz[index * 3 + 2]
      const yawedX = x * cosYaw + z * sinYaw
      const yawedZ = z * cosYaw - x * sinYaw
      const pitchedY = y * cosPitch - yawedZ * sinPitch
      const depth = yawedZ * cosPitch + y * sinPitch
      const screenX = GLOBE_CENTER + yawedX * GLOBE_RADIUS
      const screenY = GLOBE_CENTER - pitchedY * GLOBE_RADIUS

      if (front) {
        if (depth >= FRONT_PATH_THRESHOLD) {
          if (frontOpen) {
            front.lineTo(screenX, screenY)
          } else {
            front.moveTo(screenX, screenY)
            frontOpen = true
          }
        } else {
          frontOpen = false
        }
      }

      if (back) {
        if (depth <= BACK_PATH_THRESHOLD) {
          if (backOpen) {
            back.lineTo(screenX, screenY)
          } else {
            back.moveTo(screenX, screenY)
            backOpen = true
          }
        } else {
          backOpen = false
        }
      }
    }
  }
}

function strokeSurfacePath(
  context: CanvasRenderingContext2D,
  path: Path2D,
  color: string,
  width: number,
  alpha = 1
) {
  context.globalAlpha = alpha
  context.strokeStyle = color
  context.lineWidth = width
  context.stroke(path)
}

function drawGlobeSurface(
  context: CanvasRenderingContext2D,
  pixelScale: number,
  rotation: RotationState,
  landSet: PolylineSet,
  countrySet: PolylineSet
) {
  const { canvas } = context

  context.setTransform(1, 0, 0, 1, 0, 0)
  context.clearRect(0, 0, canvas.width, canvas.height)
  context.setTransform(pixelScale, 0, 0, pixelScale, 0, 0)
  context.save()
  context.beginPath()
  context.arc(GLOBE_CENTER, GLOBE_CENTER, GLOBE_RADIUS, 0, Math.PI * 2)
  context.clip()

  const gridBack = new Path2D()
  const secondaryGridFront = new Path2D()
  const primaryLatitudeFront = new Path2D()
  const primaryLongitudeFront = new Path2D()
  const countryFront = new Path2D()
  const countryBack = new Path2D()
  const landFront = new Path2D()
  const landBack = new Path2D()

  traceHemispheres(ALL_GRID_SET, rotation, null, gridBack)
  traceHemispheres(SECONDARY_GRID_SET, rotation, secondaryGridFront, null)
  traceHemispheres(PRIMARY_LATITUDE_SET, rotation, primaryLatitudeFront, null)
  traceHemispheres(PRIMARY_LONGITUDE_SET, rotation, primaryLongitudeFront, null)
  traceHemispheres(countrySet, rotation, countryFront, countryBack)
  traceHemispheres(landSet, rotation, landFront, landBack)

  context.lineCap = "butt"
  context.lineJoin = "miter"
  strokeSurfacePath(context, gridBack, GLOBE_SURFACE_THEME.backGrid, 0.18)

  context.lineCap = "round"
  context.lineJoin = "round"
  context.setLineDash([1.1, 1.7])
  strokeSurfacePath(context, countryBack, GLOBE_SURFACE_THEME.countryBack, 0.22)
  context.setLineDash([1.8, 2.6])
  strokeSurfacePath(context, landBack, "rgba(220,236,229,0.07)", 0.4)
  context.setLineDash([])

  context.lineCap = "butt"
  context.lineJoin = "miter"
  strokeSurfacePath(
    context,
    secondaryGridFront,
    GLOBE_SURFACE_THEME.secondaryGrid,
    0.18
  )
  strokeSurfacePath(
    context,
    primaryLatitudeFront,
    "rgba(223,238,231,0.094)",
    0.22
  )
  strokeSurfacePath(
    context,
    primaryLongitudeFront,
    "rgba(223,238,231,0.084)",
    0.22
  )

  context.lineCap = "round"
  context.lineJoin = "round"
  strokeSurfacePath(
    context,
    countryFront,
    GLOBE_SURFACE_THEME.countryGlow,
    0.76,
    0.5
  )
  strokeSurfacePath(context, landFront, "rgba(188,222,208,0.15)", 1.34, 0.55)
  strokeSurfacePath(context, countryFront, GLOBE_SURFACE_THEME.countryFront, 0.3)
  strokeSurfacePath(context, landFront, "rgba(229,242,236,0.82)", 0.7)

  context.restore()
}

function createLatitudeLine(latitude: number, steps = 161) {
  return Array.from({ length: steps }, (_, index) => ({
    lat: latitude,
    lon: -180 + (index * 360) / (steps - 1),
  }))
}

function createLongitudeLine(longitude: number, steps = 121) {
  return Array.from({ length: steps }, (_, index) => ({
    lat: -90 + (index * 180) / (steps - 1),
    lon: longitude,
  }))
}

function interpolateRoute(start: GlobeGeoPoint, end: GlobeGeoPoint) {
  const startVector = toVector(start)
  const endVector = toVector(end)
  const clampedDot = clamp(
    startVector.x * endVector.x +
      startVector.y * endVector.y +
      startVector.z * endVector.z,
    -1,
    1
  )
  const angle = Math.acos(clampedDot)
  const peakLift = clamp(0.052 + Math.sin(angle / 2) * 0.12, 0.052, 0.18)
  const route: Vector3[] = []

  for (let step = 0; step <= ROUTE_SEGMENTS; step += 1) {
    const progress = step / ROUTE_SEGMENTS
    let blended: Vector3

    if (angle < 0.001) {
      blended = normalizeVector({
        x: startVector.x + (endVector.x - startVector.x) * progress,
        y: startVector.y + (endVector.y - startVector.y) * progress,
        z: startVector.z + (endVector.z - startVector.z) * progress,
      })
    } else {
      const sinAngle = Math.sin(angle)
      const startWeight = Math.sin((1 - progress) * angle) / sinAngle
      const endWeight = Math.sin(progress * angle) / sinAngle

      blended = normalizeVector({
        x: startVector.x * startWeight + endVector.x * endWeight,
        y: startVector.y * startWeight + endVector.y * endWeight,
        z: startVector.z * startWeight + endVector.z * endWeight,
      })
    }

    const arcHeight = Math.sin(progress * Math.PI) ** 0.94
    const crown = Math.sin(progress * Math.PI) ** 1.75
    const lift = 1 + arcHeight * peakLift + crown * 0.0016

    route.push({
      x: blended.x * lift,
      y: blended.y * lift,
      z: blended.z * lift,
    })
  }

  return route
}

function isRoutePointVisible(projected: ProjectedPoint) {
  if (projected.radial >= 1) {
    return true
  }

  const frontSurfaceDepth = Math.sqrt(
    Math.max(0, 1 - projected.radial * projected.radial)
  )

  return projected.depth > frontSurfaceDepth + ROUTE_FRONT_SURFACE_PADDING
}

function buildRouteSegments(points: Vector3[], rotation: RotationState) {
  const segments: string[] = []
  let currentSegment: string[] = []

  points.forEach((point) => {
    const projected = rotateVector(point, rotation)

    if (!isRoutePointVisible(projected)) {
      if (currentSegment.length > 1) {
        segments.push(currentSegment.join(" "))
      }
      currentSegment = []
      return
    }

    const command = currentSegment.length === 0 ? "M" : "L"
    currentSegment.push(
      `${command} ${projected.x.toFixed(2)} ${projected.y.toFixed(2)}`
    )
  })

  if (currentSegment.length > 1) {
    segments.push(currentSegment.join(" "))
  }

  return segments
}

function sampleProjectedRun(points: ProjectedPoint[], position: number) {
  const clampedPosition = clamp(position, 0, points.length - 1)
  const startIndex = Math.floor(clampedPosition)
  const endIndex = Math.min(points.length - 1, Math.ceil(clampedPosition))
  const mix = clampedPosition - startIndex
  const start = points[startIndex]
  const end = points[endIndex]

  return {
    depth: start.depth + (end.depth - start.depth) * mix,
    radial: start.radial + (end.radial - start.radial) * mix,
    visible: start.visible || end.visible,
    x: start.x + (end.x - start.x) * mix,
    y: start.y + (end.y - start.y) * mix,
  } satisfies ProjectedPoint
}

function getVisibleRouteRun(points: Vector3[], rotation: RotationState) {
  const visibleRuns: ProjectedPoint[][] = []
  let currentRun: ProjectedPoint[] = []

  points.forEach((point) => {
    const projected = rotateVector(point, rotation)

    if (!isRoutePointVisible(projected)) {
      if (currentRun.length > 1) {
        visibleRuns.push(currentRun)
      }
      currentRun = []
      return
    }

    currentRun.push(projected)
  })

  if (currentRun.length > 1) {
    visibleRuns.push(currentRun)
  }

  const longestVisibleRun = visibleRuns.reduce<ProjectedPoint[] | null>(
    (best, current) => (!best || current.length > best.length ? current : best),
    null
  )

  if (
    !longestVisibleRun ||
    longestVisibleRun.length < Math.max(8, Math.round(points.length * 0.18))
  ) {
    return null
  }

  return longestVisibleRun
}

function getRouteCaptionAnchor(
  visibleRun: ProjectedPoint[],
  progress: number,
  offset = ROUTE_CAPTION_OFFSET
) {
  const anchorIndex = clamp(
    (visibleRun.length - 1) * progress,
    1.1,
    visibleRun.length - 2.1
  )
  const anchor = sampleProjectedRun(visibleRun, anchorIndex)
  const previousPoint = sampleProjectedRun(visibleRun, anchorIndex - 1.1)
  const nextPoint = sampleProjectedRun(visibleRun, anchorIndex + 1.1)
  const tangent = {
    x: nextPoint.x - previousPoint.x,
    y: nextPoint.y - previousPoint.y,
  }
  const tangentMagnitude = Math.hypot(tangent.x, tangent.y)

  if (tangentMagnitude < 0.001) {
    return null
  }

  let normal = {
    x: -tangent.y / tangentMagnitude,
    y: tangent.x / tangentMagnitude,
  }
  const outward = {
    x: anchor.x - GLOBE_CENTER,
    y: anchor.y - GLOBE_CENTER,
  }
  const outwardMagnitude = Math.hypot(outward.x, outward.y) || 1
  const outwardDirection = {
    x: outward.x / outwardMagnitude,
    y: outward.y / outwardMagnitude,
  }

  if (normal.x * outwardDirection.x + normal.y * outwardDirection.y < 0) {
    normal = {
      x: -normal.x,
      y: -normal.y,
    }
  }

  let angle = radiansToDegrees(Math.atan2(tangent.y, tangent.x))

  if (angle > 90 || angle < -90) {
    angle += 180
  }

  const x = anchor.x + normal.x * offset
  const y = anchor.y + normal.y * offset

  return {
    angle: roundForSvg(angle, 3),
    x: roundForSvg(x),
    y: roundForSvg(y),
  }
}

function normalizeAngleDelta(current: number, target: number) {
  let delta = target - current

  while (delta > 180) {
    delta -= 360
  }

  while (delta < -180) {
    delta += 360
  }

  return delta
}

function truncateRouteCaption(
  label: string,
  maxLength = ROUTE_CAPTION_MAX_LENGTH
) {
  if (label.length <= maxLength) {
    return label
  }

  return `${label.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`
}

function captionsOverlap(left: RouteCaptionModel, right: RouteCaptionModel) {
  return (
    Math.abs(left.x - right.x) < left.width / 2 + right.width / 2 + 1.8 &&
    Math.abs(left.y - right.y) < left.height / 2 + right.height / 2 + 1.1
  )
}

function orbitPath({
  start,
  control,
  end,
}: {
  control: { x: number; y: number }
  end: { x: number; y: number }
  start: { x: number; y: number }
}) {
  return `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`
}

function resolveFocus(
  nodeId: SupplyScenarioSelectableNodeId | null,
  nodeById: Map<string, SupplyScenario["graph"]["nodes"][number]["data"]>
): FocusState | null {
  if (!nodeId) {
    return null
  }

  const node = nodeById.get(nodeId)

  if (!node) {
    return null
  }

  if (node.kind === "product") {
    return { product: true }
  }

  if (node.kind === "component") {
    return { componentId: node.id }
  }

  return {
    componentId: node.componentId,
    manufacturerId: node.id,
  }
}

function getRouteStyle(
  route: RouteModel,
  selectedFocus: FocusState | null,
  hoveredFocus: FocusState | null,
  pinnedManufacturerByComponent: Record<string, string>
): RouteVisualStyle {
  const palette = getEcoRoutePalette(route.ecoScore)
  const buildStyle = (
    style: Omit<
      RouteVisualStyle,
      "highlightCore" | "highlightGlowSoft" | "highlightGlowStrong"
    >
  ) => ({
    ...style,
    highlightCore: palette.highlightCore,
    highlightGlowSoft: palette.highlightGlowSoft,
    highlightGlowStrong: palette.highlightGlowStrong,
  })
  const activeManufacturerId = pinnedManufacturerByComponent[route.componentId]
  const overviewActive =
    (!selectedFocus && !hoveredFocus) ||
    selectedFocus?.product ||
    hoveredFocus?.product
  const anyFocusedRoute = Boolean(
    selectedFocus?.componentId ||
    selectedFocus?.manufacturerId ||
    hoveredFocus?.componentId ||
    hoveredFocus?.manufacturerId
  )
  const selectedManufacturer =
    selectedFocus?.manufacturerId === route.manufacturerId
  const hoveredManufacturer =
    hoveredFocus?.manufacturerId === route.manufacturerId
  const selectedComponent = selectedFocus?.componentId === route.componentId
  const hoveredComponent = hoveredFocus?.componentId === route.componentId
  const pinnedManufacturer = activeManufacturerId === route.manufacturerId
  const overriddenCurrentRoute = route.isCurrent && !pinnedManufacturer

  if (selectedManufacturer) {
    return buildStyle({
      coreColor: palette.coreStrong,
      coreOpacity: 1,
      coreWidth: 1.38,
      glowColor: palette.glowStrong,
      glowOpacity: 0.86,
      glowWidth: 2.84,
      priority: 6,
      pulseColor: palette.pulseStrong,
      pulseDash: "14 86",
      pulseDuration: "7.2s",
      pulseOpacity: 0.88,
      pulseWidth: 1.42,
    })
  }

  if (hoveredManufacturer) {
    return buildStyle({
      coreColor: palette.coreMedium,
      coreOpacity: 0.94,
      coreWidth: 1.2,
      glowColor: palette.glowStrong,
      glowOpacity: 0.8,
      glowWidth: 2.42,
      priority: 5,
      pulseColor: palette.pulseMedium,
      pulseDash: "13 87",
      pulseDuration: "7.6s",
      pulseOpacity: 0.76,
      pulseWidth: 1.2,
    })
  }

  if (selectedComponent) {
    if (pinnedManufacturer) {
      return buildStyle({
        coreColor: palette.coreStrong,
        coreOpacity: 0.98,
        coreWidth: 1.14,
        glowColor: palette.glowStrong,
        glowOpacity: 0.78,
        glowWidth: 2.32,
        priority: 4.5,
        pulseColor: palette.pulseStrong,
        pulseDash: "13 87",
        pulseDuration: "7.8s",
        pulseOpacity: 0.76,
        pulseWidth: 1.18,
      })
    }

    return overriddenCurrentRoute
      ? buildStyle({
          coreColor: palette.coreSoft,
          coreOpacity: 0.58,
          coreWidth: 0.74,
          glowColor: palette.glowFaint,
          glowOpacity: 0.28,
          glowWidth: 1.34,
          priority: 4,
          pulseColor: palette.pulseFaint,
          pulseDash: "12 88",
          pulseDuration: "8s",
          pulseOpacity: 0.34,
          pulseWidth: 0.76,
        })
      : buildStyle({
          coreColor: palette.coreSoft,
          coreOpacity: 0.72,
          coreWidth: 0.86,
          glowColor: palette.glowMedium,
          glowOpacity: 0.42,
          glowWidth: 1.68,
          priority: 3,
          pulseColor: palette.pulseMedium,
          pulseDash: "11 89",
          pulseDuration: "8.6s",
          pulseOpacity: 0.52,
          pulseWidth: 0.86,
        })
  }

  if (hoveredComponent) {
    if (pinnedManufacturer) {
      return buildStyle({
        coreColor: palette.coreStrong,
        coreOpacity: 0.92,
        coreWidth: 1.04,
        glowColor: palette.glowStrong,
        glowOpacity: 0.72,
        glowWidth: 2.12,
        priority: 3.5,
        pulseColor: palette.pulseStrong,
        pulseDash: "12 88",
        pulseDuration: "8.2s",
        pulseOpacity: 0.7,
        pulseWidth: 1.02,
      })
    }

    return overriddenCurrentRoute
      ? buildStyle({
          coreColor: palette.coreSoft,
          coreOpacity: 0.5,
          coreWidth: 0.68,
          glowColor: palette.glowFaint,
          glowOpacity: 0.22,
          glowWidth: 1.18,
          priority: 3,
          pulseColor: palette.pulseFaint,
          pulseDash: "11 89",
          pulseDuration: "8.4s",
          pulseOpacity: 0.26,
          pulseWidth: 0.68,
        })
      : buildStyle({
          coreColor: palette.coreSoft,
          coreOpacity: 0.66,
          coreWidth: 0.78,
          glowColor: palette.glowFaint,
          glowOpacity: 0.36,
          glowWidth: 1.42,
          priority: 2,
          pulseColor: palette.pulseFaint,
          pulseDash: "11 89",
          pulseDuration: "9s",
          pulseOpacity: 0.38,
          pulseWidth: 0.78,
        })
  }

  if (pinnedManufacturer) {
    return buildStyle({
      coreColor: palette.coreStrong,
      coreOpacity: 0.96,
      coreWidth: 1.18,
      glowColor: palette.glowStrong,
      glowOpacity: 0.8,
      glowWidth: 2.26,
      priority: 2.6,
      pulseColor: palette.pulseStrong,
      pulseDash: "12 88",
      pulseDuration: "8s",
      pulseOpacity: 0.72,
      pulseWidth: 1.08,
    })
  }

  if (overviewActive) {
    return overriddenCurrentRoute
      ? buildStyle({
          coreColor: palette.coreSoft,
          coreOpacity: 0.34,
          coreWidth: 0.54,
          glowColor: palette.glowFaint,
          glowOpacity: 0.12,
          glowWidth: 0.92,
          priority: 2,
          pulseColor: palette.pulseFaint,
          pulseDash: "11 89",
          pulseDuration: "8.8s",
          pulseOpacity: 0.18,
          pulseWidth: 0.54,
        })
      : buildStyle({
          coreColor: palette.coreSoft,
          coreOpacity: 0.5,
          coreWidth: 0.68,
          glowColor: palette.glowFaint,
          glowOpacity: 0.24,
          glowWidth: 1.18,
          priority: 1,
          pulseColor: palette.pulseFaint,
          pulseDash: "10 90",
          pulseDuration: "9.4s",
          pulseOpacity: 0.28,
          pulseWidth: 0.64,
        })
  }

  return overriddenCurrentRoute && anyFocusedRoute
    ? buildStyle({
        coreColor: palette.coreFaint,
        coreOpacity: 0.2,
        coreWidth: 0.42,
        glowColor: palette.glowFaint,
        glowOpacity: 0.08,
        glowWidth: 0.82,
        priority: 0,
        pulseColor: palette.pulseFaint,
        pulseDash: "10 90",
        pulseDuration: "10s",
        pulseOpacity: 0.1,
        pulseWidth: 0.44,
      })
    : buildStyle({
        coreColor: palette.coreFaint,
        coreOpacity: 0.14,
        coreWidth: 0.36,
        glowColor: palette.glowFaint,
        glowOpacity: 0.06,
        glowWidth: 0.72,
        priority: 0,
        pulseColor: palette.pulseFaint,
        pulseDash: "10 90",
        pulseDuration: "10.6s",
        pulseOpacity: 0.08,
        pulseWidth: 0.4,
      })
}

const SMOOTHED_FALLBACK_LAND_OUTLINES = DEFAULT_GLOBE_GEOMETRY.landOutlines.map(
  (outline) => interpolateGeoPath(outline, CONTINENT_SUBDIVISIONS)
)
const SMOOTHED_FALLBACK_COUNTRY_BOUNDARIES =
  DEFAULT_GLOBE_GEOMETRY.countryBoundaries.map((outline) =>
    interpolateGeoPath(outline, COUNTRY_SUBDIVISIONS)
  )
const PRIMARY_LATITUDE_LINES = GRID_LATITUDES_PRIMARY.map((latitude) =>
  createLatitudeLine(latitude)
)
const SECONDARY_LATITUDE_LINES = GRID_LATITUDES_SECONDARY.map((latitude) =>
  createLatitudeLine(latitude)
)
const PRIMARY_LONGITUDE_LINES = GRID_LONGITUDES_PRIMARY.map((longitude) =>
  createLongitudeLine(longitude)
)
const SECONDARY_LONGITUDE_LINES = GRID_LONGITUDES_SECONDARY.map((longitude) =>
  createLongitudeLine(longitude)
)
const PRIMARY_LATITUDE_SET = createPolylineSet(PRIMARY_LATITUDE_LINES)
const PRIMARY_LONGITUDE_SET = createPolylineSet(PRIMARY_LONGITUDE_LINES)
const SECONDARY_GRID_SET = createPolylineSet([
  ...SECONDARY_LATITUDE_LINES,
  ...SECONDARY_LONGITUDE_LINES,
])
const ALL_GRID_SET = createPolylineSet([
  ...PRIMARY_LATITUDE_LINES,
  ...SECONDARY_LATITUDE_LINES,
  ...PRIMARY_LONGITUDE_LINES,
  ...SECONDARY_LONGITUDE_LINES,
])

export const InteractiveGlobe = memo(function InteractiveGlobe({
  bestEcoManufacturerByComponent,
  className,
  hoveredNodeId,
  onHoverNode,
  onSelectNode,
  pinnedManufacturerByComponent,
  routeVisibleByComponent,
  scenario,
  selectedNodeId,
}: InteractiveGlobeProps) {
  const destinationCenteredRotation = useMemo(
    () => getDestinationCenteredRotation(scenario.destination.location),
    [scenario.destination.location]
  )
  const [rotation, setRotation] = useState(destinationCenteredRotation)
  const [renderedRouteCaptions, setRenderedRouteCaptions] = useState<
    AnimatedRouteCaptionModel[]
  >([])
  const [geometry, setGeometry] = useState(DEFAULT_GLOBE_GEOMETRY)
  const clipPathId = `globe-clip-${useId().replaceAll(":", "")}`
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dragStateRef = useRef<DragState | null>(null)
  const autoRotationResumeAtRef = useRef<number | null>(null)
  const rotationRef = useRef(destinationCenteredRotation)
  const surfaceRotationRef = useRef(destinationCenteredRotation)
  const routeCaptionStatesRef = useRef(
    new Map<string, RouteCaptionAnimationState>()
  )
  const routeCaptionTargetsRef = useRef<RouteCaptionModel[]>([])
  const velocityRef = useRef({ pitch: 0, yaw: 0 })

  useEffect(() => {
    let active = true

    loadGlobeGeometry().then((nextGeometry) => {
      if (active) {
        setGeometry(nextGeometry)
      }
    })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let frameId = 0
    let previousTimestamp = performance.now()
    let committedRotation = { ...rotationRef.current }
    let inView = true
    const reducedMotionQuery = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    )
    const container = containerRef.current
    const visibilityObserver = container
      ? new IntersectionObserver(([entry]) => {
          inView = entry?.isIntersecting ?? true
        })
      : null

    if (container && visibilityObserver) {
      visibilityObserver.observe(container)
    }

    if (autoRotationResumeAtRef.current === null) {
      autoRotationResumeAtRef.current =
        previousTimestamp + INITIAL_DESTINATION_HOLD_MS
    }

    const tick = (timestamp: number) => {
      frameId = window.requestAnimationFrame(tick)

      const delta = Math.min(40, timestamp - previousTimestamp)
      previousTimestamp = timestamp

      if (!inView) {
        return
      }

      if (!dragStateRef.current) {
        const shouldAutoRotate =
          !reducedMotionQuery.matches &&
          timestamp >= (autoRotationResumeAtRef.current ?? 0)
        const velocity = velocityRef.current

        rotationRef.current = {
          pitch: clamp(
            rotationRef.current.pitch + velocity.pitch * delta,
            -MAX_PITCH,
            MAX_PITCH
          ),
          yaw:
            rotationRef.current.yaw +
            (shouldAutoRotate ? AUTO_ROTATION_SPEED * delta : 0) +
            velocity.yaw * delta,
        }

        const nextPitchVelocity = velocity.pitch * PITCH_VELOCITY_DECAY
        const nextYawVelocity = velocity.yaw * YAW_VELOCITY_DECAY

        velocityRef.current = {
          pitch:
            Math.abs(nextPitchVelocity) < VELOCITY_EPSILON
              ? 0
              : nextPitchVelocity,
          yaw: Math.abs(nextYawVelocity) < VELOCITY_EPSILON ? 0 : nextYawVelocity,
        }
      }

      const frameScale = delta / (1000 / 60)
      const captionBlend = 1 - Math.pow(1 - ROUTE_CAPTION_EASING, frameScale)
      const captionFadeBlend =
        1 - Math.pow(1 - ROUTE_CAPTION_FADE_EASING, frameScale)
      const captionTargetsByRouteId = new Map(
        routeCaptionTargetsRef.current.map((caption) => [
          caption.routeId,
          caption,
        ])
      )
      let captionsSettled = true

      captionTargetsByRouteId.forEach((caption, routeId) => {
        const state = routeCaptionStatesRef.current.get(routeId) ?? {
          angle: caption.angle,
          model: caption,
          opacity: 0,
          x: caption.x,
          y: caption.y,
        }

        state.model = caption
        state.x += (caption.x - state.x) * captionBlend
        state.y += (caption.y - state.y) * captionBlend
        state.angle +=
          normalizeAngleDelta(state.angle, caption.angle) * captionBlend
        state.opacity += (1 - state.opacity) * captionFadeBlend

        if (
          Math.abs(caption.x - state.x) > CAPTION_SETTLE_EPSILON ||
          Math.abs(caption.y - state.y) > CAPTION_SETTLE_EPSILON ||
          Math.abs(normalizeAngleDelta(state.angle, caption.angle)) >
            CAPTION_SETTLE_EPSILON ||
          1 - state.opacity > CAPTION_SETTLE_EPSILON
        ) {
          captionsSettled = false
        }

        routeCaptionStatesRef.current.set(routeId, state)
      })

      const rotation = rotationRef.current
      const rotationChanged =
        Math.abs(rotation.yaw - committedRotation.yaw) > ROTATION_EPSILON ||
        Math.abs(rotation.pitch - committedRotation.pitch) > ROTATION_EPSILON
      const hasFadingCaptions =
        routeCaptionStatesRef.current.size > captionTargetsByRouteId.size

      if (!rotationChanged && captionsSettled && !hasFadingCaptions) {
        return
      }

      const animatedRouteCaptions = Array.from(
        routeCaptionStatesRef.current.entries()
      )
        .flatMap(([routeId, state]) => {
          if (!captionTargetsByRouteId.has(routeId)) {
            state.opacity += (0 - state.opacity) * captionFadeBlend

            if (state.opacity < 0.035) {
              routeCaptionStatesRef.current.delete(routeId)
              return []
            }
          }

          return [
            {
              ...state.model,
              angle: roundForSvg(state.angle, 3),
              opacity: roundForSvg(clamp(state.opacity, 0, 1), 3),
              x: roundForSvg(state.x),
              y: roundForSvg(state.y),
            } satisfies AnimatedRouteCaptionModel,
          ]
        })
        .sort((left, right) => left.priority - right.priority)

      if (rotationChanged) {
        committedRotation = { ...rotation }
        setRotation(committedRotation)
      }

      setRenderedRouteCaptions(animatedRouteCaptions)
    }

    frameId = window.requestAnimationFrame(tick)

    return () => {
      window.cancelAnimationFrame(frameId)
      visibilityObserver?.disconnect()
    }
  }, [])

  const nodeById = useMemo(
    () =>
      new Map(
        scenario.graph.nodes.map((node) => [node.id, node.data] as const)
      ),
    [scenario.graph.nodes]
  )
  const selectedFocus = useMemo(
    () => resolveFocus(selectedNodeId, nodeById),
    [nodeById, selectedNodeId]
  )
  const hoveredFocus = useMemo(
    () => resolveFocus(hoveredNodeId, nodeById),
    [hoveredNodeId, nodeById]
  )
  const manufacturerById = useMemo(
    () =>
      new Map(
        scenario.manufacturers.map(
          (manufacturer) => [manufacturer.id, manufacturer] as const
        )
      ),
    [scenario.manufacturers]
  )
  const pinnedManufacturerIds = useMemo(
    () => new Set(Object.values(pinnedManufacturerByComponent)),
    [pinnedManufacturerByComponent]
  )
  const routeModels = useMemo(
    () =>
      scenario.routes
        .map((route) => {
          const manufacturer = manufacturerById.get(route.manufacturerId)

          if (!manufacturer) {
            return null
          }

          return {
            componentId: route.componentId,
            ecoScore: manufacturer.ecoScore,
            id: route.id,
            isCurrent: route.isCurrent,
            isMostSustainable:
              bestEcoManufacturerByComponent[route.componentId] ===
              route.manufacturerId,
            manufacturerId: route.manufacturerId,
            points: interpolateRoute(
              toGeoPoint(manufacturer.location),
              toGeoPoint(scenario.destination.location)
            ),
          }
        })
        .filter((route): route is RouteModel => Boolean(route)),
    [
      bestEcoManufacturerByComponent,
      manufacturerById,
      scenario.destination.location,
      scenario.routes,
    ]
  )
  const projectedManufacturerSites = useMemo(
    () =>
      scenario.manufacturers
        .filter(
          (manufacturer) =>
            routeVisibleByComponent[manufacturer.componentId] ?? true
        )
        .map((manufacturer) => ({
          id: manufacturer.id,
          isCurrent: manufacturer.isCurrent,
          location: manufacturer.location,
          point: projectGeoPointStable(
            toGeoPoint(manufacturer.location),
            rotation
          ),
          type: "manufacturer" as const,
        }))
        .filter((site) => site.point.visible)
        .sort((left, right) => left.point.depth - right.point.depth),
    [rotation, routeVisibleByComponent, scenario.manufacturers]
  )
  const projectedDestination = useMemo(() => {
    const point = projectGeoPointStable(
      toGeoPoint(scenario.destination.location),
      rotation
    )

    return point.visible
      ? {
          id: scenario.destination.id,
          point,
        }
      : null
  }, [rotation, scenario.destination])
  const destinationLabel = useMemo<DestinationLabelModel | null>(() => {
    if (!projectedDestination) {
      return null
    }

    const label = truncateRouteCaption(scenario.destination.label, 16)
    const side = projectedDestination.point.x > 67 ? -1 : 1
    const width = clamp(label.length * 1.52 + 9.4, 14, 30)
    const x = clamp(
      projectedDestination.point.x + side * (width / 2 + 5.6),
      width / 2 + 4,
      100 - width / 2 - 4
    )
    const y = clamp(projectedDestination.point.y - 6.2, 10, 92)

    return {
      height: 4.8,
      label,
      side,
      width,
      x: roundForSvg(x),
      y: roundForSvg(y),
    }
  }, [projectedDestination, scenario.destination.label])

  const landOutlines =
    geometry.source === "fallback"
      ? SMOOTHED_FALLBACK_LAND_OUTLINES
      : geometry.landOutlines
  const countryOutlines =
    geometry.source === "fallback"
      ? SMOOTHED_FALLBACK_COUNTRY_BOUNDARIES
      : geometry.countryBoundaries

  const landSet = useMemo(() => createPolylineSet(landOutlines), [landOutlines])
  const countrySet = useMemo(
    () => createPolylineSet(countryOutlines),
    [countryOutlines]
  )
  const paintSurface = useCallback(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext("2d")

    if (!canvas || !context || canvas.width === 0) {
      return
    }

    drawGlobeSurface(
      context,
      canvas.width / 100,
      surfaceRotationRef.current,
      landSet,
      countrySet
    )
  }, [countrySet, landSet])

  // Paint in the same commit as the SVG overlay so map and routes never drift apart.
  useLayoutEffect(() => {
    surfaceRotationRef.current = rotation
    paintSurface()
  }, [paintSurface, rotation])

  useEffect(() => {
    const canvas = canvasRef.current

    if (!canvas) {
      return
    }

    const resizeCanvas = () => {
      const pixelRatio = Math.min(
        window.devicePixelRatio || 1,
        MAX_CANVAS_PIXEL_RATIO
      )
      const size = Math.max(
        1,
        Math.round(canvas.getBoundingClientRect().width * pixelRatio)
      )

      if (canvas.width !== size || canvas.height !== size) {
        canvas.width = size
        canvas.height = size
        paintSurface()
      }
    }

    resizeCanvas()

    const observer = new ResizeObserver(resizeCanvas)
    observer.observe(canvas)

    return () => observer.disconnect()
  }, [paintSurface])
  const routeStyleByRouteId = useMemo(
    () =>
      new Map(
        routeModels.map((route) => [
          route.id,
          getRouteStyle(
            route,
            selectedFocus,
            hoveredFocus,
            pinnedManufacturerByComponent
          ),
        ])
      ),
    [hoveredFocus, pinnedManufacturerByComponent, routeModels, selectedFocus]
  )
  const componentIndexById = useMemo(
    () =>
      new Map(
        scenario.components.map((component, componentIndex) => [
          component.id,
          componentIndex,
        ])
      ),
    [scenario.components]
  )
  const componentById = useMemo(
    () =>
      new Map(
        scenario.components.map((component) => [component.id, component])
      ),
    [scenario.components]
  )
  const routeByManufacturerId = useMemo(
    () =>
      new Map(
        routeModels.map((route) => [route.manufacturerId, route] as const)
      ),
    [routeModels]
  )
  const routesByComponentId = useMemo(() => {
    const groupedRoutes = new Map<string, RouteModel[]>()

    routeModels.forEach((route) => {
      const componentRoutes = groupedRoutes.get(route.componentId)

      if (componentRoutes) {
        componentRoutes.push(route)
        return
      }

      groupedRoutes.set(route.componentId, [route])
    })

    return groupedRoutes
  }, [routeModels])
  const activeRouteByComponentId = useMemo(() => {
    const activeRoutes = new Map<string, RouteModel>()

    scenario.components.forEach((component) => {
      const componentRoutes = routesByComponentId.get(component.id) ?? []
      const activeRoute =
        componentRoutes.find(
          (route) =>
            pinnedManufacturerByComponent[component.id] === route.manufacturerId
        ) ??
        componentRoutes.find((route) => route.isCurrent) ??
        componentRoutes[0]

      if (activeRoute) {
        activeRoutes.set(component.id, activeRoute)
      }
    })

    return activeRoutes
  }, [pinnedManufacturerByComponent, routesByComponentId, scenario.components])
  const visibleRouteModels = useMemo(
    () =>
      Array.from(activeRouteByComponentId.entries())
        .filter(([componentId]) => routeVisibleByComponent[componentId] ?? true)
        .map(([, route]) => route),
    [activeRouteByComponentId, routeVisibleByComponent]
  )
  const routeSegments = useMemo(
    () =>
      visibleRouteModels
        .flatMap((route, routeIndex) => {
          const style = routeStyleByRouteId.get(route.id)

          if (!style) {
            return []
          }

          return buildRouteSegments(route.points, rotation).map(
            (path, segmentIndex) => ({
              drawDelay: `${routeIndex * 0.16 + segmentIndex * 0.05}s`,
              id: `${route.id}-${segmentIndex}`,
              manufacturerId: route.manufacturerId,
              path,
              pulseBegin: `${(routeIndex + segmentIndex) * 0.45}s`,
              route,
              style,
            })
          )
        })
        .sort((left, right) => left.style.priority - right.style.priority),
    [rotation, routeStyleByRouteId, visibleRouteModels]
  )
  const routeCaptionTargets = useMemo(() => {
    const captionRoutes = new Map<
      string,
      {
        isFocused: boolean
        priority: number
        route: RouteModel
      }
    >()

    const registerCaptionRoute = (
      route: RouteModel | undefined,
      priority: number
    ) => {
      if (!route) {
        return
      }

      const existing = captionRoutes.get(route.id)

      captionRoutes.set(route.id, {
        isFocused: existing?.isFocused || false,
        priority: Math.max(
          existing?.priority ?? Number.NEGATIVE_INFINITY,
          priority
        ),
        route,
      })
    }

    scenario.components.forEach((component) => {
      if (!(routeVisibleByComponent[component.id] ?? true)) {
        return
      }

      const activeRoute = activeRouteByComponentId.get(component.id)
      const basePriority =
        selectedFocus?.componentId === component.id
          ? 3.5
          : hoveredFocus?.componentId === component.id
            ? 3
            : 2

      registerCaptionRoute(activeRoute, basePriority)
    })

    const placedCaptions: RouteCaptionModel[] = []

    Array.from(captionRoutes.values())
      .sort((left, right) => {
        if (right.priority !== left.priority) {
          return right.priority - left.priority
        }

        return (
          (componentIndexById.get(left.route.componentId) ?? 0) -
          (componentIndexById.get(right.route.componentId) ?? 0)
        )
      })
      .forEach(({ isFocused, priority, route }) => {
        const component = componentById.get(route.componentId)
        const style = routeStyleByRouteId.get(route.id)
        const visibleRun = getVisibleRouteRun(route.points, rotation)

        if (!component || !style || !visibleRun) {
          return
        }

        const label = truncateRouteCaption(component.label)
        const fontSize = isFocused ? 2.12 : 1.96
        const width = Math.max(12.4, label.length * fontSize * 0.58 + 4.8)
        const height = isFocused ? 4.7 : 4.25

        for (const progress of ROUTE_CAPTION_CANDIDATE_PROGRESS) {
          const anchor = getRouteCaptionAnchor(
            visibleRun,
            progress,
            ROUTE_CAPTION_OFFSET + (isFocused ? 0.16 : 0)
          )

          if (!anchor) {
            continue
          }

          const candidate = {
            angle: anchor.angle,
            componentId: route.componentId,
            height,
            isFocused,
            label,
            manufacturerId: route.manufacturerId,
            priority,
            routeId: route.id,
            style,
            width,
            x: anchor.x,
            y: anchor.y,
          } satisfies RouteCaptionModel
          const withinBounds =
            candidate.x - candidate.width / 2 >= ROUTE_CAPTION_MARGIN_X &&
            candidate.x + candidate.width / 2 <= 100 - ROUTE_CAPTION_MARGIN_X &&
            candidate.y - candidate.height / 2 >= ROUTE_CAPTION_MARGIN_Y &&
            candidate.y + candidate.height / 2 <= 100 - ROUTE_CAPTION_MARGIN_Y

          if (!withinBounds) {
            continue
          }

          if (
            placedCaptions.some((placedCaption) =>
              captionsOverlap(candidate, placedCaption)
            )
          ) {
            continue
          }

          placedCaptions.push(candidate)
          break
        }
      })

    return placedCaptions.sort((left, right) => left.priority - right.priority)
  }, [
    componentById,
    componentIndexById,
    activeRouteByComponentId,
    hoveredFocus,
    rotation,
    routeStyleByRouteId,
    routeVisibleByComponent,
    scenario.components,
    selectedFocus,
  ])
  useEffect(() => {
    routeCaptionTargetsRef.current = routeCaptionTargets

    routeCaptionTargets.forEach((caption) => {
      if (routeCaptionStatesRef.current.has(caption.routeId)) {
        return
      }

      routeCaptionStatesRef.current.set(caption.routeId, {
        angle: caption.angle,
        model: caption,
        opacity: 0,
        x: caption.x,
        y: caption.y,
      })
    })
  }, [routeCaptionTargets])
  const visibleRouteCaptions =
    renderedRouteCaptions.length > 0
      ? renderedRouteCaptions
      : routeCaptionTargets.map((caption) => ({
          ...caption,
          opacity: 1,
        }))

  function updateRotation(nextRotation: RotationState, commit = true) {
    rotationRef.current = {
      pitch: clamp(nextRotation.pitch, -MAX_PITCH, MAX_PITCH),
      yaw: nextRotation.yaw,
    }

    if (commit) {
      setRotation({ ...rotationRef.current })
    }
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    dragStateRef.current = {
      pointerId: event.pointerId,
      timestamp: event.timeStamp,
      x: event.clientX,
      y: event.clientY,
    }
    velocityRef.current = { pitch: 0, yaw: 0 }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const dragState = dragStateRef.current

    if (!dragState || dragState.pointerId !== event.pointerId) {
      return
    }

    const deltaX = event.clientX - dragState.x
    const deltaY = event.clientY - dragState.y
    const deltaTime = Math.max(1, event.timeStamp - dragState.timestamp)
    const deltaYaw = deltaX * DRAG_SENSITIVITY * 0.6
    const deltaPitch = deltaY * DRAG_SENSITIVITY * 0.55

    updateRotation(
      {
        pitch: rotationRef.current.pitch + deltaPitch,
        yaw: rotationRef.current.yaw + deltaYaw,
      },
      false
    )

    velocityRef.current = {
      pitch: deltaPitch / deltaTime,
      yaw: deltaYaw / deltaTime,
    }
    dragStateRef.current = {
      pointerId: event.pointerId,
      timestamp: event.timeStamp,
      x: event.clientX,
      y: event.clientY,
    }
  }

  function releasePointer(
    event: React.PointerEvent<HTMLDivElement | SVGSVGElement>
  ) {
    if (dragStateRef.current?.pointerId !== event.pointerId) {
      return
    }

    dragStateRef.current = null

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (
      event.key !== "ArrowLeft" &&
      event.key !== "ArrowRight" &&
      event.key !== "ArrowUp" &&
      event.key !== "ArrowDown"
    ) {
      return
    }

    event.preventDefault()

    const yawDelta =
      event.key === "ArrowLeft" ? -0.14 : event.key === "ArrowRight" ? 0.14 : 0
    const pitchDelta =
      event.key === "ArrowUp" ? -0.1 : event.key === "ArrowDown" ? 0.1 : 0

    updateRotation({
      pitch: rotationRef.current.pitch + pitchDelta,
      yaw: rotationRef.current.yaw + yawDelta,
    })
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        "group relative aspect-square w-full max-w-[34rem] touch-none select-none md:max-w-[37rem] xl:max-w-[39rem]",
        className
      )}
      onKeyDown={handleKeyDown}
      onPointerCancel={releasePointer}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={releasePointer}
      role="img"
      aria-label="Interactive globe. Drag to rotate."
      tabIndex={0}
    >
      <style>{`
        @keyframes globe-route-draw {
          from {
            stroke-dashoffset: 100;
          }

          to {
            stroke-dashoffset: 0;
          }
        }

        .globe-route-draw {
          animation-duration: 1.05s;
          animation-fill-mode: both;
          animation-name: globe-route-draw;
          animation-timing-function: cubic-bezier(0.2, 0.9, 0.2, 1);
        }

        .globe-route-caption {
          transition: fill 260ms ease, stroke 260ms ease, opacity 180ms ease;
        }
      `}</style>
      <div className="absolute inset-[7%] rounded-full border border-white/[0.09] shadow-[0_0_18px_rgba(145,128,176,0.02)]" />
      <div className="absolute inset-[17%] rounded-full border border-white/[0.07]" />

      <svg
        aria-hidden
        className="pointer-events-none size-full overflow-visible"
        viewBox="0 0 100 100"
      >
        <defs>
          <radialGradient
            id={`${clipPathId}-surface`}
            cx="50"
            cy="50"
            r="68"
            fx="50"
            fy="50"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="rgba(242,249,246,0.14)" />
            <stop offset="22%" stopColor="rgba(180,212,199,0.075)" />
            <stop offset="56%" stopColor="rgba(72,100,92,0.05)" />
            <stop offset="86%" stopColor="rgba(10,15,18,0.22)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0.3)" />
          </radialGradient>
          <radialGradient
            id={`${clipPathId}-atmosphere`}
            cx="50%"
            cy="50%"
            r="50%"
          >
            <stop offset="0%" stopColor="rgba(255,255,255,0)" />
            <stop offset="86%" stopColor="rgba(255,255,255,0)" />
            <stop offset="93%" stopColor={GLOBE_SURFACE_THEME.atmosphereHalo} />
            <stop offset="98%" stopColor={GLOBE_SURFACE_THEME.atmosphereRim} />
            <stop offset="100%" stopColor="rgba(255,255,255,0)" />
          </radialGradient>
        </defs>

        <path
          d={orbitPath(PRODUCT_ORBIT)}
          fill="none"
          stroke={GLOBE_SURFACE_THEME.orbitStroke}
          strokeWidth="0.32"
        />

        <circle
          cx={GLOBE_CENTER}
          cy={GLOBE_CENTER}
          r={GLOBE_RADIUS + 1.05}
          fill={`url(#${clipPathId}-atmosphere)`}
          opacity={0.72}
        />
        <circle
          cx={GLOBE_CENTER}
          cy={GLOBE_CENTER}
          r={GLOBE_RADIUS + 0.34}
          fill="none"
          stroke={GLOBE_SURFACE_THEME.atmosphereStroke}
          strokeWidth="0.34"
          opacity={0.72}
        />

        <circle
          cx={GLOBE_CENTER}
          cy={GLOBE_CENTER}
          r={GLOBE_RADIUS}
          fill={`url(#${clipPathId}-surface)`}
        />
        <circle
          cx={GLOBE_CENTER}
          cy={GLOBE_CENTER}
          r={GLOBE_RADIUS}
          fill="none"
          stroke={GLOBE_SURFACE_THEME.rimStroke}
          strokeWidth="0.72"
        />
      </svg>

      <canvas
        ref={canvasRef}
        aria-hidden
        className="pointer-events-none absolute inset-0 size-full"
      />

      <svg
        className="absolute inset-0 size-full overflow-visible"
        viewBox="0 0 100 100"
        onPointerCancel={releasePointer}
        onPointerUp={releasePointer}
      >
        <defs>
          <clipPath id={clipPathId}>
            <circle cx={GLOBE_CENTER} cy={GLOBE_CENTER} r={GLOBE_RADIUS} />
          </clipPath>
        </defs>

        <g clipPath={`url(#${clipPathId})`}>
          {projectedManufacturerSites.map((site) => {
            const manufacturer = manufacturerById.get(site.id)

            if (!manufacturer) {
              return null
            }

            const palette = getEcoRoutePalette(manufacturer.ecoScore)
            const route = routeByManufacturerId.get(manufacturer.id)
            const routeStyle = route ? routeStyleByRouteId.get(route.id) : null
            const focused =
              selectedNodeId === manufacturer.id ||
              hoveredNodeId === manufacturer.id ||
              selectedFocus?.componentId === manufacturer.componentId ||
              hoveredFocus?.componentId === manufacturer.componentId
            const pinned = pinnedManufacturerIds.has(manufacturer.id)
            const radius = focused
              ? 1.74
              : pinned
                ? 1.48
                : manufacturer.isCurrent
                  ? 1.32
                  : 1.02
            const routeCoreColor = routeStyle
              ? withAlpha(
                  routeStyle.coreColor,
                  focused || pinned || manufacturer.isCurrent ? 1 : 0.9
                )
              : manufacturer.isCurrent || pinned
                ? palette.coreStrong
                : palette.coreSoft
            const routeGlowColor = routeStyle
              ? withAlpha(
                  routeStyle.glowColor,
                  clamp(routeStyle.glowOpacity + 0.08, 0.14, 0.84)
                )
              : palette.glowMedium
            const routeMarkerFill =
              focused || pinned || manufacturer.isCurrent
                ? routeCoreColor
                : palette.pulseMedium
            const routeMarkerStroke = focused
              ? routeCoreColor
              : pinned || manufacturer.isCurrent
                ? withAlpha(routeCoreColor, 0.92)
                : palette.coreSoft

            return (
              <g
                key={site.id}
                onClick={() => onSelectNode(manufacturer.id)}
                onPointerEnter={() => onHoverNode(manufacturer.id)}
                onPointerLeave={() => onHoverNode(null)}
                style={{ cursor: "pointer" }}
              >
                {manufacturer.isCurrent || focused || pinned ? (
                  <circle
                    cx={site.point.x}
                    cy={site.point.y}
                    r={radius + 1.95}
                    fill={routeGlowColor}
                    opacity={manufacturer.isCurrent || pinned ? 0.28 : 0.18}
                    stroke={routeCoreColor}
                    strokeWidth="0.2"
                  >
                    <animate
                      attributeName="r"
                      begin={`${manufacturer.isCurrent || pinned ? 0.2 : 0.6}s`}
                      dur={manufacturer.isCurrent || pinned ? "3.4s" : "2.8s"}
                      repeatCount="indefinite"
                      values={`${radius + 1.2};${radius + 2.65};${radius + 1.2}`}
                    />
                    <animate
                      attributeName="opacity"
                      begin={`${manufacturer.isCurrent || pinned ? 0.2 : 0.6}s`}
                      dur={manufacturer.isCurrent || pinned ? "3.4s" : "2.8s"}
                      repeatCount="indefinite"
                      values={
                        manufacturer.isCurrent || pinned
                          ? "0.22;0.05;0.22"
                          : "0.16;0.04;0.16"
                      }
                    />
                  </circle>
                ) : null}
                {focused ? (
                  <circle
                    cx={site.point.x}
                    cy={site.point.y}
                    r={radius + 1.7}
                    fill={routeGlowColor}
                    stroke={routeCoreColor}
                    strokeWidth="0.34"
                  />
                ) : null}
                <circle
                  cx={site.point.x}
                  cy={site.point.y}
                  r={radius}
                  fill={routeMarkerFill}
                  stroke={routeMarkerStroke}
                  strokeWidth="0.3"
                >
                  <animate
                    attributeName="opacity"
                    begin="0s"
                    dur="0.5s"
                    fill="freeze"
                    from="0"
                    to="1"
                  />
                  <animate
                    attributeName="r"
                    begin="0s"
                    dur="0.5s"
                    fill="freeze"
                    from="0.1"
                    to={`${radius}`}
                  />
                </circle>
              </g>
            )
          })}

          {projectedDestination ? (
            <g>
              <circle
                cx={projectedDestination.point.x}
                cy={projectedDestination.point.y}
                r={5.2}
                fill={GLOBE_SURFACE_THEME.destinationGlow}
                stroke={GLOBE_SURFACE_THEME.destinationStroke}
                strokeWidth="0.2"
              >
                <animate
                  attributeName="r"
                  begin="0.35s"
                  dur="3.5s"
                  repeatCount="indefinite"
                  values="4.5;6.1;4.5"
                />
                <animate
                  attributeName="opacity"
                  begin="0.35s"
                  dur="3.5s"
                  repeatCount="indefinite"
                  values="0.18;0.04;0.18"
                />
              </circle>
              <circle
                cx={projectedDestination.point.x}
                cy={projectedDestination.point.y}
                r={4.2}
                fill="rgba(255,255,255,0.06)"
                stroke={GLOBE_SURFACE_THEME.destinationStroke}
                strokeWidth="0.36"
              >
                <animate
                  attributeName="opacity"
                  begin="0.1s"
                  dur="0.55s"
                  fill="freeze"
                  from="0"
                  to="1"
                />
              </circle>
              <circle
                cx={projectedDestination.point.x}
                cy={projectedDestination.point.y}
                r={1.92}
                fill={GLOBE_SURFACE_THEME.destinationFill}
                stroke={GLOBE_SURFACE_THEME.destinationStroke}
                strokeWidth="0.3"
              >
                <animate
                  attributeName="r"
                  begin="0.1s"
                  dur="0.55s"
                  fill="freeze"
                  from="0.1"
                  to="1.92"
                />
              </circle>
            </g>
          ) : null}
        </g>

        {routeSegments.map(
          ({
            drawDelay,
            id,
            manufacturerId,
            path,
            pulseBegin,
            route,
            style,
          }) => {
            const showSustainableHighlight =
              route.isMostSustainable &&
              pinnedManufacturerByComponent[route.componentId] ===
                route.manufacturerId

            return (
              <g
                key={id}
                onClick={() => onSelectNode(manufacturerId)}
                onPointerEnter={() => onHoverNode(manufacturerId)}
                onPointerLeave={() => onHoverNode(null)}
                style={{ cursor: "pointer" }}
              >
                <path
                  d={path}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={7}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {showSustainableHighlight ? (
                  <>
                    <path
                      d={path}
                      fill="none"
                      stroke={
                        style.priority >= 4
                          ? style.highlightGlowStrong
                          : style.highlightGlowSoft
                      }
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={style.glowWidth + 1.32}
                      style={{
                        filter:
                          style.priority >= 4 ? "blur(5.4px)" : "blur(4px)",
                        transition:
                          "stroke 260ms ease, stroke-width 260ms ease, filter 260ms ease",
                      }}
                    />
                    <path
                      d={path}
                      fill="none"
                      stroke={style.highlightCore}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeOpacity={Math.min(0.88, style.coreOpacity + 0.14)}
                      strokeWidth={style.coreWidth + 0.14}
                      style={{
                        transition:
                          "stroke 260ms ease, stroke-opacity 260ms ease, stroke-width 260ms ease",
                      }}
                    />
                  </>
                ) : null}
                <path
                  d={path}
                  fill="none"
                  pathLength={100}
                  stroke={style.glowColor}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeOpacity={style.glowOpacity}
                  strokeDasharray="100"
                  strokeWidth={style.glowWidth}
                  className="globe-route-draw"
                  style={{
                    animationDelay: drawDelay,
                    transition:
                      "stroke 260ms ease, stroke-opacity 260ms ease, stroke-width 260ms ease",
                  }}
                />
                <path
                  d={path}
                  fill="none"
                  pathLength={100}
                  stroke={style.coreColor}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeOpacity={style.coreOpacity}
                  strokeDasharray="100"
                  strokeWidth={style.coreWidth}
                  className="globe-route-draw"
                  style={{
                    animationDelay: drawDelay,
                    transition:
                      "stroke 260ms ease, stroke-opacity 260ms ease, stroke-width 260ms ease",
                  }}
                />
                <path
                  d={path}
                  fill="none"
                  pathLength={100}
                  stroke={style.pulseColor}
                  strokeDasharray={style.pulseDash}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeOpacity={style.pulseOpacity}
                  strokeWidth={style.pulseWidth}
                  style={{
                    transition:
                      "stroke 260ms ease, stroke-opacity 260ms ease, stroke-width 260ms ease",
                  }}
                >
                  <animate
                    attributeName="stroke-dashoffset"
                    begin={pulseBegin}
                    dur={style.pulseDuration}
                    from="120"
                    repeatCount="indefinite"
                    to="0"
                  />
                </path>
              </g>
            )
          }
        )}

        {projectedDestination && destinationLabel ? (
          <g className="pointer-events-none">
            <path
              d={`M ${projectedDestination.point.x.toFixed(2)} ${projectedDestination.point.y.toFixed(2)} L ${(projectedDestination.point.x + destinationLabel.side * 3.1).toFixed(2)} ${(projectedDestination.point.y - 2.1).toFixed(2)} L ${(destinationLabel.x - destinationLabel.side * (destinationLabel.width / 2 - 1.2)).toFixed(2)} ${destinationLabel.y.toFixed(2)}`}
              fill="none"
              stroke={GLOBE_SURFACE_THEME.destinationStroke}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="0.34"
            />
            <rect
              x={destinationLabel.x - destinationLabel.width / 2}
              y={destinationLabel.y - destinationLabel.height / 2}
              width={destinationLabel.width}
              height={destinationLabel.height}
              rx={destinationLabel.height / 2}
              fill={GLOBE_SURFACE_THEME.labelFill}
              stroke={GLOBE_SURFACE_THEME.labelStroke}
              strokeWidth="0.28"
            />
            <text
              x={destinationLabel.x}
              y={destinationLabel.y + 0.7}
              fill={GLOBE_SURFACE_THEME.labelText}
              fontSize="1.9"
              fontWeight="600"
              letterSpacing="0.01em"
              stroke={GLOBE_SURFACE_THEME.shadowFill}
              strokeWidth="0.42"
              paintOrder="stroke"
              textAnchor="middle"
            >
              {destinationLabel.label}
            </text>
          </g>
        ) : null}

        <ellipse
          cx={GLOBE_CENTER}
          cy={GLOBE_CENTER}
          rx={GLOBE_RADIUS * 0.98}
          ry={GLOBE_RADIUS * 0.42}
          fill="none"
          opacity={0.78}
          stroke={GLOBE_SURFACE_THEME.terminatorStroke}
          strokeWidth="0.32"
        />

        {visibleRouteCaptions.map((caption) => {
          const accentStroke = withAlpha(
            caption.style.coreColor,
            caption.isFocused ? 0.42 : 0.28
          )
          const captionFill = caption.isFocused
            ? GLOBE_SURFACE_THEME.labelFillStrong
            : GLOBE_SURFACE_THEME.labelFill
          const captionTextColor = caption.isFocused
            ? GLOBE_SURFACE_THEME.labelText
            : "rgba(233,243,238,0.9)"
          const fontSize = caption.isFocused ? 2.12 : 1.96
          const fontWeight = caption.isFocused ? 700 : 600

          return (
            <g
              key={`route-caption-${caption.routeId}`}
              transform={`rotate(${caption.angle} ${caption.x} ${caption.y})`}
              opacity={caption.opacity}
            >
              <g
                onClick={() => onSelectNode(caption.manufacturerId)}
                onPointerEnter={() => onHoverNode(caption.manufacturerId)}
                onPointerLeave={() => onHoverNode(null)}
                style={{ cursor: "pointer" }}
              >
                <rect
                  className="globe-route-caption"
                  x={caption.x - caption.width / 2}
                  y={caption.y - caption.height / 2}
                  width={caption.width}
                  height={caption.height}
                  rx={caption.height / 2}
                  fill={captionFill}
                  stroke={accentStroke}
                  strokeWidth={caption.isFocused ? 0.42 : 0.3}
                />
                <text
                  className="globe-route-caption"
                  x={caption.x}
                  y={caption.y}
                  dominantBaseline="middle"
                  fill={captionTextColor}
                  fontSize={fontSize}
                  fontWeight={fontWeight}
                  letterSpacing="0.01em"
                  paintOrder="stroke"
                  stroke={GLOBE_SURFACE_THEME.shadowFill}
                  strokeWidth={caption.isFocused ? 0.44 : 0.34}
                  textAnchor="middle"
                >
                  {caption.label}
                </text>
              </g>
            </g>
          )
        })}
      </svg>

      <div className="pointer-events-none absolute inset-x-0 bottom-2 flex justify-center">
        <div className="rounded-full border border-white/12 bg-black/18 px-3 py-1 text-[0.65rem] tracking-[0.2em] text-white/70 uppercase backdrop-blur-sm">
          Drag to rotate
        </div>
      </div>
    </div>
  )
})
