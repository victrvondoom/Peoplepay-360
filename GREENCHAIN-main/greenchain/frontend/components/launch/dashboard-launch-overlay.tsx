"use client"

import {
  useEffect,
  useId,
  useMemo,
  useState,
  type CSSProperties,
} from "react"

import { type GlobeGeoPoint } from "@/lib/globe-geometry"
import {
  DEFAULT_GLOBE_GEOMETRY,
  loadGlobeGeometry,
  type GlobeGeometryData,
} from "@/lib/natural-earth-globe"
import { getEcoRoutePalette, withAlpha } from "@/lib/eco-visuals"
import { cn } from "@/lib/utils"

export type DashboardLaunchStatus = {
  detail: string
  title: string
}

type DashboardLaunchPhase = "priming" | "shell" | "sync" | "entering"
type RouteTone = "balanced" | "eco" | "risk"

type GlobeRoute = {
  destination: GlobeGeoPoint
  drawEnd: number
  drawStart: number
  key: string
  lift?: number
  origin: GlobeGeoPoint
  pulseDuration: string
  tone: RouteTone
}

type DashboardLaunchOverlayProps = {
  active: boolean
  onComplete: () => void
  reducedMotion: boolean
}

type GlobeRotation = {
  pitch: number
  yaw: number
}

type Vector3 = {
  x: number
  y: number
  z: number
}

type ProjectedPoint = {
  depth: number
  radial: number
  visible: boolean
  x: number
  y: number
}

type HemispherePaths = {
  back: string
  front: string
}

type ProjectedRoute = {
  key: string
  pulseDash: string
  pulseColor: string
  pulseDuration: string
  pulsePath: string | null
  pulseWidth: number
  segments: string[]
  tone: RouteTone
}

type Orbit = {
  key: string
  rotate: number
  rx: number
  ry: number
}

type LaunchTimings = {
  entering: number
  priming: number
  settle: number
  shell: number
  sync: number
}

type LaunchSnapshot = {
  done: boolean
  handoffProgress: number
  phase: DashboardLaunchPhase
  progress: number
  totalMotionDuration: number
}

const DASHBOARD_LAUNCH_STATUSES: Record<
  DashboardLaunchPhase,
  DashboardLaunchStatus
> = {
  entering: {
    detail:
      "Settling the route globe before the launch chooser opens.",
    title: "Opening launch options",
  },
  priming: {
    detail:
      "Bringing the route globe online so the handoff starts inside the product world.",
    title: "Aligning route globe",
  },
  shell: {
    detail:
      "Tracing eco, balanced, and at-risk lanes across the globe before the split.",
    title: "Tracing live routes",
  },
  sync: {
    detail:
      "Surveying live supply lanes around the globe.",
    title: "Surveying global lanes",
  },
}

const DASHBOARD_LAUNCH_PHASES: DashboardLaunchPhase[] = [
  "priming",
  "shell",
  "sync",
  "entering",
]

const ECO_ROUTE_PALETTES: Record<RouteTone, ReturnType<typeof getEcoRoutePalette>> =
  {
    balanced: getEcoRoutePalette(52),
    eco: getEcoRoutePalette(22),
    risk: getEcoRoutePalette(74),
  }

const GLOBE_CENTER = {
  r: 204,
  x: 600,
  y: 484,
} as const

const DEFAULT_ROTATION: GlobeRotation = {
  pitch: degreesToRadians(23.5),
  yaw: degreesToRadians(80),
}

const AUTO_ROTATION_SPEED = 0.00006
const ROUTE_SEGMENTS = 72
const FRONT_PATH_THRESHOLD = 0
const BACK_PATH_THRESHOLD = -0.18
const ROUTE_FRONT_SURFACE_PADDING = 0.004
const LAND_OUTLINE_SUBDIVISIONS = 8
const ROUTE_HUB: GlobeGeoPoint = {
  lat: 32.78,
  lon: -96.8,
}

const GLOBE_ROUTES: GlobeRoute[] = [
  {
    destination: { lat: 40.71, lon: -74.01 },
    drawEnd: 50,
    drawStart: 16,
    key: "route-hub-ny",
    lift: 1.18,
    origin: ROUTE_HUB,
    pulseDuration: "6s",
    tone: "eco",
  },
  {
    destination: { lat: -23.55, lon: -46.63 },
    drawEnd: 64,
    drawStart: 24,
    key: "route-hub-sao-paulo",
    lift: 1.28,
    origin: ROUTE_HUB,
    pulseDuration: "6.3s",
    tone: "balanced",
  },
  {
    destination: { lat: 22.54, lon: 114.06 },
    drawEnd: 78,
    drawStart: 34,
    key: "route-hub-shenzhen",
    lift: 1.34,
    origin: ROUTE_HUB,
    pulseDuration: "6.5s",
    tone: "risk",
  },
  {
    destination: { lat: -33.86, lon: 151.21 },
    drawEnd: 94,
    drawStart: 44,
    key: "route-hub-sydney",
    lift: 1.4,
    origin: ROUTE_HUB,
    pulseDuration: "6.8s",
    tone: "balanced",
  },
] as const

const ORBITS: Orbit[] = [
  { key: "orbit-outer", rotate: -16, rx: 198, ry: 78 },
  { key: "orbit-inner", rotate: 18, rx: 142, ry: 48 },
] as const

const GRID_LATITUDES = [-54, -27, 0, 27, 54] as const
const GRID_LONGITUDES = [-120, -70, -15, 38, 92] as const

function degreesToRadians(value: number) {
  return (value * Math.PI) / 180
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function roundForSvg(value: number, digits = 3) {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function easeInOutCubic(value: number) {
  return value < 0.5
    ? 4 * value * value * value
    : 1 - Math.pow(-2 * value + 2, 3) / 2
}

function easeRouteReveal(value: number) {
  const base = easeInOutCubic(clamp(value, 0, 1))
  const earlyBoost =
    0.055 * easeInOutCubic(getWindowProgress(value, 0.24, 0.46))
  const lateBoost =
    0.03 * easeInOutCubic(getWindowProgress(value, 0.7, 0.9))

  return clamp(base + (1 - base) * (earlyBoost + lateBoost), 0, 1)
}

function getWindowProgress(value: number, start: number, end: number) {
  if (end <= start) {
    return value >= end ? 1 : 0
  }

  return clamp((value - start) / (end - start), 0, 1)
}

function getLaunchSnapshot(
  elapsed: number,
  timings: LaunchTimings,
  reducedMotion: boolean
): LaunchSnapshot {
  const ease = (value: number) =>
    reducedMotion ? clamp(value, 0, 1) : easeInOutCubic(clamp(value, 0, 1))
  const primingEnd = timings.priming
  const shellEnd = primingEnd + timings.shell
  const syncEnd = shellEnd + timings.sync
  const enteringEnd = syncEnd + timings.entering
  const fadeDuration = reducedMotion ? 120 : 280
  const holdDuration = Math.max(0, timings.settle - fadeDuration)
  const fadeStart = enteringEnd + holdDuration
  const settleEnd = enteringEnd + timings.settle

  if (elapsed < primingEnd) {
    return {
      done: false,
      handoffProgress: 0,
      phase: "priming" as const,
      progress: 16 * ease(elapsed / Math.max(timings.priming, 1)),
      totalMotionDuration: enteringEnd,
    }
  }

  if (elapsed < shellEnd) {
    return {
      done: false,
      handoffProgress: 0,
      phase: "shell" as const,
      progress: 16 + (54 - 16) * ease((elapsed - primingEnd) / Math.max(timings.shell, 1)),
      totalMotionDuration: enteringEnd,
    }
  }

  if (elapsed < syncEnd) {
    return {
      done: false,
      handoffProgress: 0,
      phase: "sync" as const,
      progress: 54 + (86 - 54) * ease((elapsed - shellEnd) / Math.max(timings.sync, 1)),
      totalMotionDuration: enteringEnd,
    }
  }

  if (elapsed < enteringEnd) {
    return {
      done: false,
      handoffProgress: 0,
      phase: "entering" as const,
      progress: 86 + (100 - 86) * ease((elapsed - syncEnd) / Math.max(timings.entering, 1)),
      totalMotionDuration: enteringEnd,
    }
  }

  return {
    done: elapsed >= settleEnd,
    handoffProgress: ease(getWindowProgress(elapsed, fadeStart, settleEnd)),
    phase: "entering" as const,
    progress: 100,
    totalMotionDuration: enteringEnd,
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
  { pitch, yaw }: GlobeRotation
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
    x: GLOBE_CENTER.x + yawedX * GLOBE_CENTER.r,
    y: GLOBE_CENTER.y - pitchedY * GLOBE_CENTER.r,
  }
}

function projectGeoPoint(point: GlobeGeoPoint, rotation: GlobeRotation) {
  return rotateVector(toVector(point), rotation)
}

const EMPTY_HEMISPHERE_PATHS: HemispherePaths = { back: "", front: "" }

function flushRun(run: string[], target: string[]) {
  if (run.length > 1) {
    target.push(run.join(""))
  }

  run.length = 0
}

/** Projects every line once and merges each hemisphere into a single path string. */
function projectMergedHemispheres(
  lines: Vector3[][],
  { pitch, yaw }: GlobeRotation
): HemispherePaths {
  const sinYaw = Math.sin(yaw)
  const cosYaw = Math.cos(yaw)
  const sinPitch = Math.sin(pitch)
  const cosPitch = Math.cos(pitch)
  const front: string[] = []
  const back: string[] = []
  const frontRun: string[] = []
  const backRun: string[] = []

  for (const line of lines) {
    for (const vector of line) {
      const yawedX = vector.x * cosYaw + vector.z * sinYaw
      const yawedZ = vector.z * cosYaw - vector.x * sinYaw
      const pitchedY = vector.y * cosPitch - yawedZ * sinPitch
      const depth = yawedZ * cosPitch + vector.y * sinPitch
      const x = (GLOBE_CENTER.x + yawedX * GLOBE_CENTER.r).toFixed(1)
      const y = (GLOBE_CENTER.y - pitchedY * GLOBE_CENTER.r).toFixed(1)

      if (depth >= FRONT_PATH_THRESHOLD) {
        frontRun.push(`${frontRun.length === 0 ? "M" : "L"}${x} ${y}`)
      } else {
        flushRun(frontRun, front)
      }

      if (depth <= BACK_PATH_THRESHOLD) {
        backRun.push(`${backRun.length === 0 ? "M" : "L"}${x} ${y}`)
      } else {
        flushRun(backRun, back)
      }
    }

    flushRun(frontRun, front)
    flushRun(backRun, back)
  }

  return { back: back.join(""), front: front.join("") }
}

function interpolateRoute(
  start: GlobeGeoPoint,
  end: GlobeGeoPoint,
  liftMultiplier = 1
) {
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
  const peakLift = clamp(
    (0.082 + Math.sin(angle / 2) * 0.2) * liftMultiplier,
    0.082,
    0.36
  )
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

function buildProjectedRoute(points: Vector3[], rotation: GlobeRotation) {
  const segments: string[] = []
  let currentSegment: string[] = []
  let longestSegment: string[] = []

  points.forEach((point) => {
    const projected = rotateVector(point, rotation)

    if (!isRoutePointVisible(projected)) {
      if (currentSegment.length > 1) {
        segments.push(currentSegment.join(" "))

        if (currentSegment.length > longestSegment.length) {
          longestSegment = [...currentSegment]
        }
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

    if (currentSegment.length > longestSegment.length) {
      longestSegment = [...currentSegment]
    }
  }

  return {
    pulsePath:
      longestSegment.length > 1 ? longestSegment.join(" ") : null,
    segments,
  }
}

const GRID_VECTOR_LINES: Vector3[][] = [
  ...GRID_LATITUDES.map((latitude) => createLatitudeLine(latitude)),
  ...GRID_LONGITUDES.map((longitude) => createLongitudeLine(longitude)),
].map((line) => line.map(toVector))

const ROUTE_MODELS = GLOBE_ROUTES.map((route) => ({
  ...route,
  points: interpolateRoute(route.origin, route.destination, route.lift),
}))
const ROUTE_META_BY_KEY = new Map(
  GLOBE_ROUTES.map((route) => [route.key, route] as const)
)

export function DashboardLaunchOverlay({
  active,
  onComplete,
  reducedMotion,
}: DashboardLaunchOverlayProps) {
  const [phase, setPhase] = useState<DashboardLaunchPhase>("priming")
  const [handoffProgress, setHandoffProgress] = useState(0)
  const [progress, setProgress] = useState(0)
  const [geometry, setGeometry] =
    useState<GlobeGeometryData>(DEFAULT_GLOBE_GEOMETRY)
  const [rotation, setRotation] = useState<GlobeRotation>(DEFAULT_ROTATION)
  const clipPathId = `dashboard-launch-globe-${useId().replace(/:/g, "")}`

  useEffect(() => {
    if (!active) {
      return
    }

    let mounted = true

    loadGlobeGeometry()
      .then((nextGeometry) => {
        if (mounted) {
          setGeometry(nextGeometry)
        }
      })
      .catch(() => {
        if (mounted) {
          setGeometry(DEFAULT_GLOBE_GEOMETRY)
        }
      })

    return () => {
      mounted = false
    }
  }, [active])

  useEffect(() => {
    if (!active) {
      return
    }

    const timings = reducedMotion
      ? {
          entering: 220,
          priming: 220,
          settle: 260,
          shell: 340,
          sync: 280,
        }
      : {
          entering: 860,
          priming: 880,
          settle: 1280,
          shell: 1880,
          sync: 1460,
        }
    let cancelled = false
    let frameId = 0
    const start = performance.now()

    const tick = (now: number) => {
      if (cancelled) {
        return
      }

      const elapsed = Math.max(0, now - start)
      const snapshot = getLaunchSnapshot(elapsed, timings, reducedMotion)
      const nextRotation = reducedMotion
        ? DEFAULT_ROTATION
        : {
            pitch: DEFAULT_ROTATION.pitch,
            yaw:
              DEFAULT_ROTATION.yaw +
              AUTO_ROTATION_SPEED *
                Math.min(elapsed, snapshot.totalMotionDuration),
          }

      setPhase((currentPhase) =>
        currentPhase === snapshot.phase ? currentPhase : snapshot.phase
      )
      setHandoffProgress(snapshot.handoffProgress)
      setProgress(snapshot.progress)
      setRotation(nextRotation)

      if (snapshot.done) {
        onComplete()
        return
      }

      frameId = window.requestAnimationFrame(tick)
    }

    frameId = window.requestAnimationFrame(tick)

    return () => {
      cancelled = true
      window.cancelAnimationFrame(frameId)
    }
  }, [active, onComplete, reducedMotion])

  const globeRotation = reducedMotion ? DEFAULT_ROTATION : rotation

  const landVectorLines = useMemo(() => {
    if (!active) {
      return []
    }

    // Natural Earth outlines are already dense; only the coarse fallback needs smoothing.
    const outlines =
      geometry.source === "fallback"
        ? geometry.landOutlines.map((outline) =>
            interpolateGeoPath(outline, LAND_OUTLINE_SUBDIVISIONS)
          )
        : [...geometry.landOutlines]
            .sort((left, right) => right.length - left.length)
            .slice(0, 20)

    return outlines
      .filter((outline) => outline.length > 2)
      .map((outline) => outline.map(toVector))
  }, [active, geometry])

  const gridPaths = useMemo(
    () =>
      active
        ? projectMergedHemispheres(GRID_VECTOR_LINES, globeRotation)
        : EMPTY_HEMISPHERE_PATHS,
    [active, globeRotation]
  )

  const landPaths = useMemo(
    () =>
      active
        ? projectMergedHemispheres(landVectorLines, globeRotation)
        : EMPTY_HEMISPHERE_PATHS,
    [active, globeRotation, landVectorLines]
  )

  const projectedRoutes = useMemo<ProjectedRoute[]>(
    () =>
      ROUTE_MODELS.map((route) => {
        const { pulsePath, segments } = buildProjectedRoute(
          route.points,
          globeRotation
        )

        return {
          key: route.key,
          pulseDash: route.tone === "risk" ? "12 88" : "10 90",
          pulseColor:
            route.tone === "risk"
              ? withAlpha(ECO_ROUTE_PALETTES[route.tone].pulseStrong, 0.96)
              : withAlpha(ECO_ROUTE_PALETTES[route.tone].pulseStrong, 0.88),
          pulseDuration: route.pulseDuration,
          pulsePath,
          pulseWidth: route.tone === "risk" ? 2.9 : 2.5,
          segments,
          tone: route.tone,
        }
      }),
    [globeRotation]
  )
  const projectedHub = useMemo(
    () => projectGeoPoint(ROUTE_HUB, globeRotation),
    [globeRotation]
  )

  if (!active) return null

  const currentPhaseIndex = DASHBOARD_LAUNCH_PHASES.indexOf(phase)
  const contentOpacity = roundForSvg(1 - handoffProgress, 3)
  const progressRatio = clamp(progress / 100, 0, 1)
  const progressDisplay = Math.round(progress)
  const status = DASHBOARD_LAUNCH_STATUSES[phase]
  const animatedRoutes = projectedRoutes.map((route) => {
    const meta = ROUTE_META_BY_KEY.get(route.key)
    const revealProgress = easeRouteReveal(
      meta ? getWindowProgress(progress, meta.drawStart, meta.drawEnd) : 1
    )
    const layerOpacity =
      revealProgress <= 0 ? 0 : 0.18 + revealProgress * 0.82
    const pulseOpacity = clamp((revealProgress - 0.56) / 0.18, 0, 1)

    return {
      ...route,
      layerOpacity: roundForSvg(layerOpacity, 3),
      pulseOpacity: roundForSvg(pulseOpacity, 3),
      strokeDashoffset: roundForSvg((1 - revealProgress) * 100, 3),
    }
  })

  return (
    <div
      aria-hidden
      className={cn(
        "dashboard-launch fixed inset-0 z-[100] overflow-hidden px-4 py-6 sm:px-6 md:px-8",
        `is-${phase}`,
        progressRatio >= 1 && "is-settled",
        reducedMotion && "is-reduced-motion"
      )}
    >
      <div className="dashboard-launch__backdrop absolute inset-0" />
      <div
        className="dashboard-launch__blackout absolute inset-0"
        style={{ opacity: handoffProgress }}
      />
      <div className="dashboard-launch__vignette absolute inset-0" />
      <div className="dashboard-launch__grid absolute inset-0" />
      <div className="dashboard-launch__noise absolute inset-0" />

      <div
        className="dashboard-launch__frame relative z-10 mx-auto flex min-h-full w-full max-w-[1220px] items-center justify-center"
        style={{ opacity: contentOpacity }}
      >
        <div className="dashboard-launch__scene w-full">
          <div className="dashboard-launch__header">
            <h2 className="dashboard-launch__title font-heading text-[clamp(2.1rem,4.7vw,4.2rem)] leading-[0.94] tracking-[-0.06em] text-white">
              {status.title}
            </h2>

            <p className="dashboard-launch__detail mt-4 max-w-xl text-sm leading-7 text-white/58 sm:text-base">
              {status.detail}
            </p>

            <div className="dashboard-launch__phase-rail mt-6 flex items-center gap-2">
              {DASHBOARD_LAUNCH_PHASES.map((currentPhase, index) => (
                <span
                  key={currentPhase}
                  className={cn(
                    "dashboard-launch__phase-dot",
                    index <= currentPhaseIndex && "is-active"
                  )}
                />
              ))}
            </div>

            <div className="dashboard-launch__telemetry">
              <div className="dashboard-launch__telemetry-top">
                <span className="dashboard-launch__telemetry-value">
                  {progressDisplay}%
                </span>
                <span className="dashboard-launch__telemetry-label">
                  Launch telemetry
                </span>
              </div>
              <div className="dashboard-launch__telemetry-bar">
                <span
                  className="dashboard-launch__telemetry-fill"
                  style={{ transform: `scaleX(${progressRatio})` }}
                />
              </div>
            </div>
          </div>

          <svg
            className="dashboard-launch__visual pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 1200 760"
            fill="none"
          >
            <defs>
              <clipPath id={clipPathId}>
                <circle
                  cx={GLOBE_CENTER.x}
                  cy={GLOBE_CENTER.y}
                  r={GLOBE_CENTER.r}
                />
              </clipPath>
              <radialGradient
                id={`${clipPathId}-surface`}
                cx="50%"
                cy="46%"
                r="68%"
              >
                <stop offset="0%" stopColor="rgba(234,244,239,0.14)" />
                <stop offset="28%" stopColor="rgba(173,209,195,0.085)" />
                <stop offset="62%" stopColor="rgba(72,101,94,0.05)" />
                <stop offset="100%" stopColor="rgba(8,14,18,0.92)" />
              </radialGradient>
              <radialGradient
                id={`${clipPathId}-atmosphere`}
                cx="50%"
                cy="50%"
                r="62%"
              >
                <stop offset="72%" stopColor="rgba(220,242,233,0)" />
                <stop offset="90%" stopColor="rgba(220,242,233,0.12)" />
                <stop offset="100%" stopColor="rgba(220,242,233,0.22)" />
              </radialGradient>
            </defs>

            <g className="dashboard-launch__globe-group">
              {ORBITS.map((orbit) => (
                <ellipse
                  key={orbit.key}
                  className={cn(
                    "dashboard-launch__orbital",
                    orbit.key === "orbit-inner" &&
                      "dashboard-launch__orbital--inner"
                  )}
                  cx={GLOBE_CENTER.x}
                  cy={GLOBE_CENTER.y}
                  rx={orbit.rx}
                  ry={orbit.ry}
                  transform={`rotate(${orbit.rotate} ${GLOBE_CENTER.x} ${GLOBE_CENTER.y})`}
                />
              ))}

              <circle
                className="dashboard-launch__atmosphere"
                cx={GLOBE_CENTER.x}
                cy={GLOBE_CENTER.y}
                fill={`url(#${clipPathId}-atmosphere)`}
                r={GLOBE_CENTER.r + 18}
              />

              <g className="dashboard-launch__globe-shell">
                <ellipse
                  className="dashboard-launch__globe-shadow"
                  cx={GLOBE_CENTER.x}
                  cy={GLOBE_CENTER.y + 48}
                  rx={GLOBE_CENTER.r * 0.72}
                  ry={GLOBE_CENTER.r * 0.22}
                />

                <circle
                  className="dashboard-launch__surface"
                  cx={GLOBE_CENTER.x}
                  cy={GLOBE_CENTER.y}
                  fill={`url(#${clipPathId}-surface)`}
                  r={GLOBE_CENTER.r}
                />

                <g clipPath={`url(#${clipPathId})`}>
                  <path
                    className="dashboard-launch__globe-grid dashboard-launch__globe-grid--back"
                    d={gridPaths.back}
                  />
                  <path
                    className="dashboard-launch__land dashboard-launch__land--back"
                    d={landPaths.back}
                  />
                  <path
                    className="dashboard-launch__globe-grid dashboard-launch__globe-grid--front"
                    d={gridPaths.front}
                  />
                  <path
                    className="dashboard-launch__land dashboard-launch__land--front"
                    d={landPaths.front}
                  />

                  {projectedHub.visible ? (
                    <g
                      className="dashboard-launch__hub-node"
                      transform={`translate(${roundForSvg(projectedHub.x)} ${roundForSvg(projectedHub.y)})`}
                    >
                      <circle
                        className="dashboard-launch__hub-node-halo"
                        fill="rgba(241,248,244,0.26)"
                        r="14"
                      />
                      <circle
                        className="dashboard-launch__hub-node-ring"
                        fill="none"
                        r="8.8"
                      />
                      <circle
                        className="dashboard-launch__hub-node-core"
                        fill="rgba(255,255,255,0.98)"
                        r="3.8"
                      />
                    </g>
                  ) : null}
                </g>

                <ellipse
                  className="dashboard-launch__terminator"
                  cx={GLOBE_CENTER.x}
                  cy={GLOBE_CENTER.y}
                  rx={GLOBE_CENTER.r * 0.98}
                  ry={GLOBE_CENTER.r * 0.42}
                />
                <circle
                  className="dashboard-launch__rim"
                  cx={GLOBE_CENTER.x}
                  cy={GLOBE_CENTER.y}
                  r={GLOBE_CENTER.r}
                />

                {animatedRoutes.map((route) => {
                  const palette = ECO_ROUTE_PALETTES[route.tone]

                  return (
                    <g
                      key={route.key}
                      className="dashboard-launch__route-layer"
                      style={{ opacity: route.layerOpacity }}
                    >
                      {route.segments.map((segment, index) => (
                        <g key={`${route.key}-segment-${index}`}>
                          <path
                            className="dashboard-launch__route dashboard-launch__route--lifted"
                            d={segment}
                            pathLength={100}
                            stroke={withAlpha(palette.glowStrong, 0.42)}
                            style={
                              {
                                opacity: route.layerOpacity * 0.78,
                                strokeDashoffset: route.strokeDashoffset,
                              } as CSSProperties
                            }
                          />
                          <path
                            className="dashboard-launch__route dashboard-launch__route--glow"
                            d={segment}
                            pathLength={100}
                            stroke={withAlpha(palette.glowStrong, 0.84)}
                            style={
                              {
                                opacity: route.layerOpacity * 0.92,
                                strokeDashoffset: route.strokeDashoffset,
                              } as CSSProperties
                            }
                          />
                          <path
                            className="dashboard-launch__route dashboard-launch__route--core"
                            d={segment}
                            pathLength={100}
                            stroke={palette.coreStrong}
                            style={
                              {
                                opacity: route.layerOpacity,
                                strokeDashoffset: route.strokeDashoffset,
                              } as CSSProperties
                            }
                          />
                        </g>
                      ))}

                      {route.pulsePath && !reducedMotion && route.pulseOpacity > 0 ? (
                        <path
                          className="dashboard-launch__route-pulse"
                          d={route.pulsePath}
                          fill="none"
                          pathLength={100}
                          stroke={route.pulseColor}
                          strokeDasharray={route.pulseDash}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={route.pulseWidth}
                          style={
                            {
                              animationDuration: `${route.pulseDuration}, 1.4s`,
                              opacity: route.pulseOpacity,
                            } as CSSProperties
                          }
                        />
                      ) : null}
                    </g>
                  )
                })}
              </g>
            </g>
          </svg>
        </div>
      </div>
    </div>
  )
}
