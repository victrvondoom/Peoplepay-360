export const PREF_KEYS = {
  notificationsLive: "proxy:pref-notifications-live",
  notificationsPollMs: "proxy:pref-notifications-poll-ms",
  kgDefaultTab: "proxy:pref-kg-default-tab",
  newAnalysisDefaultDomain: "proxy:pref-new-analysis-domain",
} as const;

export function getPref(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return window.localStorage.getItem(key) ?? fallback;
}

export function setPref(key: string, value: string) {
  window.localStorage.setItem(key, value);
}
