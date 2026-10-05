import { NextResponse } from "next/server"

import {
  buildNaturalEarthGlobeGeometry,
  DEFAULT_GLOBE_GEOMETRY,
  NATURAL_EARTH_ADMIN_0_TOPOLOGY_URL,
} from "@/lib/natural-earth-globe"

export const revalidate = 86400

export async function GET() {
  try {
    const response = await fetch(NATURAL_EARTH_ADMIN_0_TOPOLOGY_URL, {
      next: {
        revalidate,
      },
    })

    if (!response.ok) {
      throw new Error(`Upstream responded with ${response.status}`)
    }

    const topology = await response.json()

    return NextResponse.json(buildNaturalEarthGlobeGeometry(topology), {
      headers: {
        "Cache-Control":
          "public, s-maxage=86400, stale-while-revalidate=604800",
      },
    })
  } catch {
    return NextResponse.json(DEFAULT_GLOBE_GEOMETRY, {
      headers: {
        "Cache-Control": "public, s-maxage=300, stale-while-revalidate=86400",
      },
    })
  }
}
