import { NextResponse } from "next/server"

import { getServerApiBaseUrl } from "@/lib/server-api-base-url"

export async function GET() {
  try {
    const response = await fetch(`${getServerApiBaseUrl()}/health`, {
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
            : "Health proxy request failed.",
      },
      { status: 502 }
    )
  }
}
