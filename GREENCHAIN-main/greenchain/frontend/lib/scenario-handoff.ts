const PENDING_SCENARIO_CSV_KEY = "greenchain.pendingScenarioCsv"

export function savePendingScenarioCsv(csvText: string) {
  if (typeof window === "undefined") return
  window.sessionStorage.setItem(PENDING_SCENARIO_CSV_KEY, csvText)
}

export function readPendingScenarioCsv() {
  if (typeof window === "undefined") return null
  return window.sessionStorage.getItem(PENDING_SCENARIO_CSV_KEY)
}

export function clearPendingScenarioCsv() {
  if (typeof window === "undefined") return
  window.sessionStorage.removeItem(PENDING_SCENARIO_CSV_KEY)
}

export function consumePendingScenarioCsv() {
  const pendingCsv = readPendingScenarioCsv()
  clearPendingScenarioCsv()
  return pendingCsv
}
