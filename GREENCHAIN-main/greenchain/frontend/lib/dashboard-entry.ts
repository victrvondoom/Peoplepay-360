export const DASHBOARD_ENTRY_COOKIE = "greenchain_dashboard_entry"
export const DASHBOARD_ENTRY_MODE_DEMO = "demo"

const COOKIE_PATH = "Path=/"
const COOKIE_MAX_AGE = "Max-Age=86400"
const COOKIE_SAME_SITE = "SameSite=Lax"

export function persistDemoDashboardEntry() {
  if (typeof document === "undefined") {
    return
  }

  document.cookie = [
    `${DASHBOARD_ENTRY_COOKIE}=${DASHBOARD_ENTRY_MODE_DEMO}`,
    COOKIE_PATH,
    COOKIE_MAX_AGE,
    COOKIE_SAME_SITE,
  ].join("; ")
}

export function clearDashboardEntry() {
  if (typeof document === "undefined") {
    return
  }

  document.cookie = [
    `${DASHBOARD_ENTRY_COOKIE}=`,
    COOKIE_PATH,
    "Max-Age=0",
    COOKIE_SAME_SITE,
  ].join("; ")
}
