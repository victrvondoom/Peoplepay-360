"use client";

import { useEffect, useState } from "react";
import {
  Fingerprint, Copy, Check, Activity, Loader2, RefreshCw, Bell, LayoutGrid,
  Download, Trash2, AlertTriangle, Database, Server, Cpu, Cloud, X,
} from "lucide-react";
import {
  listAnalyses, listAppeals, listDocuments, getReportSummary, getMyCitizenProfile,
  getSystemHealth, type SystemHealth,
} from "@/lib/api-client";
import { DOMAIN_THEME, domainTheme } from "@/components/chat/domain-theme";
import { PREF_KEYS, getPref, setPref } from "@/lib/preferences";

const CACHE_KEYS = [
  "proxy:search-recent-queries",
  "proxy:analyses-pinned",
  "proxy:analyses-favorite",
  "proxy:assistant-chat-history",
  "proxy:kg-institution-recent",
  "proxy:notifications-last-seen",
  "proxy:last-analysis-domain",
];

function getDeviceId(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("proxy:device-user-id") ?? "";
}

export function SettingsCenter() {
  return (
    <div className="flex flex-1 flex-col gap-4">
      <IdentityCard />
      <SystemDiagnostics />
      <div className="grid gap-4 lg:grid-cols-2">
        <NotificationPreferences />
        <WorkspacePreferences />
      </div>
      <DataPrivacy />
    </div>
  );
}

function IdentityCard() {
  const [deviceId, setDeviceId] = useState("");
  const [copied, setCopied] = useState(false);
  const [stats, setStats] = useState<{ totals: { cases: number; appeals: number; documents: number; domains_engaged: number }; since: string | null } | null>(null);

  useEffect(() => {
    setDeviceId(getDeviceId());
    Promise.all([getReportSummary(), listAnalyses()])
      .then(([summary, analyses]) => {
        const earliest = analyses.reduce<string | null>((min, a) => {
          if (!a.created_at) return min;
          return !min || a.created_at < min ? a.created_at : min;
        }, null);
        setStats({ totals: summary.totals, since: earliest });
      })
      .catch(() => {});
  }, []);

  function copyId() {
    navigator.clipboard.writeText(deviceId);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <div className="mb-4 flex items-center gap-2">
        <Fingerprint className="size-4 text-cyan-200" />
        <h2 className="font-semibold">Your identity</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-xl border border-white/10 bg-black/20 p-3 sm:col-span-2 xl:col-span-2">
          <p className="mb-1 text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">Device identity</p>
          <div className="flex items-center gap-2">
            <p className="truncate font-mono text-xs text-proxy-text">{deviceId || "-"}</p>
            <button onClick={copyId} className="shrink-0 text-proxy-tertiary hover:text-cyan-200">
              {copied ? <Check className="size-3.5 text-green-300" /> : <Copy className="size-3.5" />}
            </button>
          </div>
          <p className="mt-1 text-[10px] text-proxy-tertiary">No login exists in this app -- this browser-generated id is your entire identity.</p>
        </div>
        <StatBlock label="Cases" value={stats?.totals.cases} />
        <StatBlock label="Appeals" value={stats?.totals.appeals} />
        <StatBlock label="Documents" value={stats?.totals.documents} />
      </div>
      {stats?.since && (
        <p className="mt-3 text-[11px] text-proxy-tertiary">Member since {new Date(stats.since).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}</p>
      )}
    </section>
  );
}

function StatBlock({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-center">
      <p className="text-lg font-semibold text-proxy-text">{value ?? <Loader2 className="mx-auto size-4 animate-spin text-proxy-tertiary" />}</p>
      <p className="text-[10px] text-proxy-tertiary">{label}</p>
    </div>
  );
}

const STATUS_COLOR: Record<string, string> = {
  ready: "#37f29a",
  configured: "#37f29a",
  ok: "#37f29a",
  alive: "#37f29a",
  degraded: "#ffc857",
  missing_key: "#ffc857",
  not_configured: "#a8b3c7",
  unreachable: "#ff4d6d",
  error: "#ff4d6d",
};

function statusColor(status: string): string {
  return STATUS_COLOR[status] ?? "#a8b3c7";
}

function SystemDiagnostics() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const { health: result, latencyMs } = await getSystemHealth();
      setHealth(result);
      setLatency(latencyMs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend unreachable");
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="size-4 text-cyan-200" />
          <h2 className="font-semibold">System diagnostics</h2>
          {health && (
            <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ backgroundColor: `${statusColor(health.status)}1a`, color: statusColor(health.status) }}>
              {health.status}
            </span>
          )}
        </div>
        <button onClick={refresh} disabled={loading} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100">
          {loading ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Refresh{latency !== null && !loading ? ` (${latency}ms)` : ""}
        </button>
      </div>

      {error ? (
        <p className="text-sm text-red-200">{error}</p>
      ) : !health ? (
        <div className="flex h-24 items-center justify-center"><Loader2 className="size-5 animate-spin text-proxy-tertiary" /></div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <DiagCard icon={Cpu} title="LLM Provider" status={health.llm.status}>
            <p className="text-xs text-proxy-muted">{health.llm.provider}</p>
            {health.llm.reasoning_model && <p className="mt-1 truncate text-[10px] text-proxy-tertiary">{health.llm.reasoning_model}</p>}
          </DiagCard>
          <DiagCard icon={Database} title="Vector Store" status={health.vector_store.status}>
            <p className="text-xs text-proxy-muted">{health.vector_store.backend}</p>
            {health.vector_store.total_points !== undefined && (
              <p className="mt-1 text-[10px] text-proxy-tertiary">{health.vector_store.collections} collections &middot; {health.vector_store.total_points.toLocaleString()} points</p>
            )}
          </DiagCard>
          <DiagCard icon={Server} title="Graph Store" status={health.graph_store.status}>
            <p className="text-xs text-proxy-muted">{health.graph_store.backend}</p>
            {health.graph_store.events !== undefined && <p className="mt-1 text-[10px] text-proxy-tertiary">{health.graph_store.events.toLocaleString()} events</p>}
          </DiagCard>
          <DiagCard icon={Cloud} title="Supabase" status={health.supabase.status}>
            <p className="truncate text-[10px] text-proxy-tertiary">{health.supabase.url ?? "not configured"}</p>
          </DiagCard>
          <DiagCard icon={Server} title="Redis Cache" status={health.redis.status}>
            <p className="truncate text-[10px] text-proxy-tertiary">{health.redis.error ?? "connected"}</p>
          </DiagCard>
          <DiagCard icon={Cloud} title="Web Search" status={health.web_search.status}>
            <p className="text-[10px] text-proxy-tertiary">{health.web_search.status === "not_configured" ? "optional -- not enabled" : "enabled"}</p>
          </DiagCard>
        </div>
      )}
    </section>
  );
}

function DiagCard({ icon: Icon, title, status, children }: { icon: typeof Cpu; title: string; status: string; children: React.ReactNode }) {
  const color = statusColor(status);
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
      <div className="mb-1.5 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Icon className="size-3.5" style={{ color }} />
          <p className="text-xs font-medium text-proxy-text">{title}</p>
        </div>
        <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} />
      </div>
      {children}
    </div>
  );
}

function NotificationPreferences() {
  // Stable SSR-safe defaults; the real saved preferences are read
  // client-side after mount to avoid a hydration mismatch (localStorage
  // isn't available during server rendering, so reading it in the useState
  // initializer makes the client's first render disagree with the server's).
  const [live, setLive] = useState(false);
  const [pollMs, setPollMs] = useState("20000");
  useEffect(() => {
    setLive(getPref(PREF_KEYS.notificationsLive, "false") === "true");
    setPollMs(getPref(PREF_KEYS.notificationsPollMs, "20000"));
  }, []);

  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <div className="mb-4 flex items-center gap-2">
        <Bell className="size-4 text-cyan-200" />
        <h2 className="font-semibold">Notification preferences</h2>
      </div>
      <label className="mb-3 flex items-center justify-between rounded-xl border border-white/10 bg-black/20 p-3 text-sm">
        <span className="text-proxy-muted">Start live polling automatically</span>
        <input
          type="checkbox"
          checked={live}
          onChange={(e) => {
            setLive(e.target.checked);
            setPref(PREF_KEYS.notificationsLive, String(e.target.checked));
          }}
          className="size-4 accent-cyan-300"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1.5 block text-xs text-proxy-muted">Polling interval</span>
        <select
          value={pollMs}
          onChange={(e) => {
            setPollMs(e.target.value);
            setPref(PREF_KEYS.notificationsPollMs, e.target.value);
          }}
          className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-cyan-300/60"
        >
          <option value="10000">Every 10 seconds</option>
          <option value="20000">Every 20 seconds</option>
          <option value="30000">Every 30 seconds</option>
          <option value="60000">Every minute</option>
        </select>
      </label>
      <p className="mt-3 text-[10px] text-proxy-tertiary">Controls the Notifications page directly -- these are real settings, not decorative toggles.</p>
    </section>
  );
}

function WorkspacePreferences() {
  // Same SSR-safe pattern as NotificationPreferences above.
  const [kgTab, setKgTab] = useState("case");
  const [domain, setDomain] = useState("health_insurance");
  useEffect(() => {
    setKgTab(getPref(PREF_KEYS.kgDefaultTab, "case"));
    setDomain(getPref(PREF_KEYS.newAnalysisDefaultDomain, "health_insurance"));
  }, []);

  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <div className="mb-4 flex items-center gap-2">
        <LayoutGrid className="size-4 text-cyan-200" />
        <h2 className="font-semibold">Workspace preferences</h2>
      </div>
      <label className="mb-3 block text-sm">
        <span className="mb-1.5 block text-xs text-proxy-muted">Default Knowledge Graph tab</span>
        <select
          value={kgTab}
          onChange={(e) => {
            setKgTab(e.target.value);
            setPref(PREF_KEYS.kgDefaultTab, e.target.value);
          }}
          className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-cyan-300/60"
        >
          <option value="case">Case Graph</option>
          <option value="institution">Institution Intelligence</option>
          <option value="profile">My Cross-Domain Profile</option>
        </select>
      </label>
      <label className="block text-sm">
        <span className="mb-1.5 block text-xs text-proxy-muted">Default New Analysis focus domain</span>
        <select
          value={domain}
          onChange={(e) => {
            setDomain(e.target.value);
            setPref(PREF_KEYS.newAnalysisDefaultDomain, e.target.value);
          }}
          className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-cyan-300/60"
        >
          {Object.entries(DOMAIN_THEME).map(([key, t]) => <option key={key} value={key}>{t.label}</option>)}
        </select>
      </label>
      <p className="mt-3 text-[10px] text-proxy-tertiary">
        Applied next time you open <span style={{ color: domainTheme(domain).color }}>{domainTheme(domain).label}</span>'s New Analysis flow or the Knowledge Graph page.
      </p>
    </section>
  );
}

function DataPrivacy() {
  const [exporting, setExporting] = useState(false);
  const [clearedCache, setClearedCache] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  async function exportAllData() {
    setExporting(true);
    try {
      const deviceId = getDeviceId();
      const [analyses, appeals, documents, summary, profile] = await Promise.all([
        listAnalyses(),
        listAppeals(),
        listDocuments(),
        getReportSummary(),
        getMyCitizenProfile().catch(() => null),
      ]);
      const payload = { exported_at: new Date().toISOString(), device_id: deviceId, summary, analyses, appeals, documents, citizen_profile: profile };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `proxy-data-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  function clearCache() {
    CACHE_KEYS.forEach((key) => window.localStorage.removeItem(key));
    setClearedCache(true);
    window.setTimeout(() => setClearedCache(false), 2500);
  }

  function resetIdentity() {
    window.localStorage.removeItem("proxy:device-user-id");
    window.location.reload();
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <div className="mb-4 flex items-center gap-2">
        <Database className="size-4 text-cyan-200" />
        <h2 className="font-semibold">Data &amp; privacy</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <button
          onClick={exportAllData}
          disabled={exporting}
          className="flex flex-col items-start gap-2 rounded-xl border border-white/10 bg-black/20 p-3 text-left hover:border-cyan-300/30"
        >
          <div className="grid size-8 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-300/10">
            {exporting ? <Loader2 className="size-4 animate-spin text-cyan-200" /> : <Download className="size-4 text-cyan-200" />}
          </div>
          <div>
            <p className="text-xs font-medium text-proxy-text">Export all my data</p>
            <p className="mt-0.5 text-[10px] leading-4 text-proxy-tertiary">Every case, appeal, document, and profile record as JSON.</p>
          </div>
        </button>

        <button
          onClick={clearCache}
          className="flex flex-col items-start gap-2 rounded-xl border border-white/10 bg-black/20 p-3 text-left hover:border-amber-300/30"
        >
          <div className="grid size-8 place-items-center rounded-lg border border-amber-300/25 bg-amber-300/10">
            {clearedCache ? <Check className="size-4 text-green-300" /> : <Trash2 className="size-4 text-amber-200" />}
          </div>
          <div>
            <p className="text-xs font-medium text-proxy-text">{clearedCache ? "Cache cleared" : "Clear local app cache"}</p>
            <p className="mt-0.5 text-[10px] leading-4 text-proxy-tertiary">Chat history, pinned analyses, recent searches -- {CACHE_KEYS.length} keys. Doesn't touch your backend data.</p>
          </div>
        </button>

        <button
          onClick={() => setConfirmReset(true)}
          className="flex flex-col items-start gap-2 rounded-xl border border-red-300/20 bg-red-300/5 p-3 text-left hover:border-red-300/40"
        >
          <div className="grid size-8 place-items-center rounded-lg border border-red-300/25 bg-red-300/10">
            <AlertTriangle className="size-4 text-red-300" />
          </div>
          <div>
            <p className="text-xs font-medium text-red-100">Reset device identity</p>
            <p className="mt-0.5 text-[10px] leading-4 text-proxy-tertiary">Generates a new anonymous id -- you'll lose access to everything under this one.</p>
          </div>
        </button>
      </div>

      {confirmReset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setConfirmReset(false)}>
          <div className="w-full max-w-sm rounded-2xl border border-red-300/25 bg-[#0a0b10] p-5" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-red-100">
                <AlertTriangle className="size-4" />
                <p className="text-sm font-semibold">Reset device identity?</p>
              </div>
              <button onClick={() => setConfirmReset(false)} className="text-proxy-tertiary hover:text-proxy-text"><X className="size-4" /></button>
            </div>
            <p className="mb-4 text-xs leading-6 text-proxy-muted">
              This app has no login -- your device id <strong>is</strong> your account. Resetting it generates a brand-new anonymous identity in this browser.
              Every case, appeal, and document you've created stays in the backend, but you will no longer be able to reach it from here. This cannot be undone from the UI.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setConfirmReset(false)} className="flex-1 rounded-lg border border-white/10 px-3 py-2 text-xs text-proxy-muted hover:border-white/25">
                Cancel
              </button>
              <button onClick={resetIdentity} className="flex-1 rounded-lg border border-red-300/30 bg-red-300/10 px-3 py-2 text-xs text-red-100 hover:bg-red-300/15">
                Reset identity
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
