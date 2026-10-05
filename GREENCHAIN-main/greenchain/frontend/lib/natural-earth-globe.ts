import {
  CONTINENT_OUTLINES,
  COUNTRY_BOUNDARIES,
  type GlobeGeoPoint,
} from "@/lib/globe-geometry"

export interface GlobeGeometryData {
  countryBoundaries: GlobeGeoPoint[][]
  landOutlines: GlobeGeoPoint[][]
  source: "fallback" | "natural-earth-admin-0-50m"
}

export const NATURAL_EARTH_ADMIN_0_TOPOLOGY_URL =
  "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"

export const DEFAULT_GLOBE_GEOMETRY: GlobeGeometryData = {
  countryBoundaries: COUNTRY_BOUNDARIES,
  landOutlines: CONTINENT_OUTLINES,
  source: "fallback",
}

interface TopologyTransform {
  scale: [number, number]
  translate: [number, number]
}

interface TopologyPolygonGeometry {
  arcs: number[][]
  type: "Polygon"
}

interface TopologyMultiPolygonGeometry {
  arcs: number[][][]
  type: "MultiPolygon"
}

interface TopologyGeometryCollection {
  geometries: TopologyGeometry[]
  type: "GeometryCollection"
}

type TopologyGeometry =
  | TopologyGeometryCollection
  | TopologyMultiPolygonGeometry
  | TopologyPolygonGeometry

interface Topology {
  arcs: Array<Array<[number, number]>>
  objects: {
    countries: TopologyGeometryCollection
    land: TopologyGeometry
  }
  transform: TopologyTransform
  type: "Topology"
}

function pointsMatch(left: GlobeGeoPoint, right: GlobeGeoPoint) {
  return (
    Math.abs(left.lat - right.lat) < 0.001 &&
    Math.abs(left.lon - right.lon) < 0.001
  )
}

function pointDistance(left: GlobeGeoPoint, right: GlobeGeoPoint) {
  return Math.hypot(left.lat - right.lat, left.lon - right.lon)
}

function simplifyOutline(points: GlobeGeoPoint[], minDistance: number) {
  if (points.length < 3) {
    return points
  }

  const simplified = [points[0]]

  for (let index = 1; index < points.length - 1; index += 1) {
    const point = points[index]
    const previous = simplified[simplified.length - 1]

    if (pointDistance(previous, point) >= minDistance) {
      simplified.push(point)
    }
  }

  const lastPoint = points[points.length - 1]

  if (!pointsMatch(simplified[simplified.length - 1], lastPoint)) {
    simplified.push(lastPoint)
  }

  return simplified
}

function roundCoordinate(value: number) {
  return Math.round(value * 100) / 100
}

function normalizeOutlineSet(outlines: GlobeGeoPoint[][], minDistance: number) {
  return outlines
    .map((outline) =>
      simplifyOutline(outline, minDistance).map((point) => ({
        lat: roundCoordinate(point.lat),
        lon: roundCoordinate(point.lon),
      }))
    )
    .filter((outline) => outline.length > 1)
}

function getArcIndex(reference: number) {
  return reference < 0 ? ~reference : reference
}

function decodeArc(
  topology: Topology,
  arcIndex: number,
  cache: Map<number, GlobeGeoPoint[]>
) {
  const cached = cache.get(arcIndex)

  if (cached) {
    return cached
  }

  const encodedArc = topology.arcs[arcIndex]

  if (!encodedArc) {
    return []
  }

  let x = 0
  let y = 0

  const decoded = encodedArc.map(([deltaX, deltaY]) => {
    x += deltaX
    y += deltaY

    return {
      lat: y * topology.transform.scale[1] + topology.transform.translate[1],
      lon: x * topology.transform.scale[0] + topology.transform.translate[0],
    }
  })

  cache.set(arcIndex, decoded)

  return decoded
}

function decodeArcChain(
  topology: Topology,
  arcReferences: number[],
  cache: Map<number, GlobeGeoPoint[]>
) {
  const line: GlobeGeoPoint[] = []

  arcReferences.forEach((reference) => {
    const points = decodeArc(topology, getArcIndex(reference), cache)
    const orientedPoints = reference < 0 ? [...points].reverse() : points

    orientedPoints.forEach((point, index) => {
      if (line.length > 0 && index === 0) {
        return
      }

      line.push(point)
    })
  })

  return line
}

function collectArcIndices(geometry: TopologyGeometry, target: Set<number>) {
  if (geometry.type === "GeometryCollection") {
    geometry.geometries.forEach((nestedGeometry) => {
      collectArcIndices(nestedGeometry, target)
    })
    return
  }

  if (geometry.type === "Polygon") {
    geometry.arcs.forEach((ring) => {
      ring.forEach((reference) => {
        target.add(getArcIndex(reference))
      })
    })
    return
  }

  geometry.arcs.forEach((polygon) => {
    polygon.forEach((ring) => {
      ring.forEach((reference) => {
        target.add(getArcIndex(reference))
      })
    })
  })
}

function extractLandOutlines(
  topology: Topology,
  geometry: TopologyGeometry,
  cache: Map<number, GlobeGeoPoint[]>
): GlobeGeoPoint[][] {
  if (geometry.type === "GeometryCollection") {
    return geometry.geometries.flatMap((nestedGeometry) =>
      extractLandOutlines(topology, nestedGeometry, cache)
    )
  }

  if (geometry.type === "Polygon") {
    return [decodeArcChain(topology, geometry.arcs[0] ?? [], cache)].filter(
      (outline) => outline.length > 1
    )
  }

  return geometry.arcs
    .map((polygon) => decodeArcChain(topology, polygon[0] ?? [], cache))
    .filter((outline) => outline.length > 1)
}

export function buildNaturalEarthGlobeGeometry(
  topology: Topology
): GlobeGeometryData {
  const arcCache = new Map<number, GlobeGeoPoint[]>()
  const arcUsage = new Map<number, number>()

  topology.objects.countries.geometries.forEach((geometry) => {
    const arcIndices = new Set<number>()
    collectArcIndices(geometry, arcIndices)

    arcIndices.forEach((arcIndex) => {
      arcUsage.set(arcIndex, (arcUsage.get(arcIndex) ?? 0) + 1)
    })
  })

  const countryBoundaries = [...arcUsage.entries()]
    .filter(([, count]) => count > 1)
    .map(([arcIndex]) => decodeArc(topology, arcIndex, arcCache))
    .filter((outline) => outline.length > 1)

  const landOutlines = extractLandOutlines(
    topology,
    topology.objects.land,
    arcCache
  )

  if (countryBoundaries.length === 0 || landOutlines.length === 0) {
    return DEFAULT_GLOBE_GEOMETRY
  }

  return {
    countryBoundaries: normalizeOutlineSet(countryBoundaries, 1.15),
    landOutlines: normalizeOutlineSet(landOutlines, 0.45),
    source: "natural-earth-admin-0-50m",
  }
}

let geometryPromise: Promise<GlobeGeometryData> | null = null

export function loadGlobeGeometry() {
  if (!geometryPromise) {
    geometryPromise = fetch("/api/globe-geometry", {
      cache: "force-cache",
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Globe geometry request failed: ${response.status}`)
        }

        return (await response.json()) as GlobeGeometryData
      })
      .then((geometry) => {
        if (geometry.source === "fallback") {
          geometryPromise = null
        }

        return geometry
      })
      .catch(() => {
        geometryPromise = null
        return DEFAULT_GLOBE_GEOMETRY
      })
  }

  return geometryPromise
}
