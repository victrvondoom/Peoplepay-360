import { NextResponse } from "next/server"

import { getServerApiBaseUrl } from "@/lib/server-api-base-url"

export async function POST(request: Request) {
  try {
    const body = await request.text()
    const response = await fetch(`${getServerApiBaseUrl()}/scenario/report`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
    })

    const payload = await response.text()

    return new NextResponse(payload, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") ?? "application/json",
      },
    })
  } catch (error) {
    return NextResponse.json(
      {
        detail:
          error instanceof Error
            ? error.message
            : "Scenario report proxy request failed.",
      },
      { status: 502 }
    )
  }
}
