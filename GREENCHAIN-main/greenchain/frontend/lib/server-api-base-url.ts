const DEFAULT_SERVER_API_BASE_URL = "http://127.0.0.1:8000"

function normalizeServerApiBaseUrl(value: string | undefined) {
  if (!value) {
    return DEFAULT_SERVER_API_BASE_URL
  }

  const trimmed = value.trim().replace(/\/+$/, "")
  if (!trimmed) {
    return DEFAULT_SERVER_API_BASE_URL
  }

  return trimmed.endsWith("/api") ? trimmed.slice(0, -4) : trimmed
}

export function getServerApiBaseUrl() {
  return normalizeServerApiBaseUrl(
    process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL
  )
}
