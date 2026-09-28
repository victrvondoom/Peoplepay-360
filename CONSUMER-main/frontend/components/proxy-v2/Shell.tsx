"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bell, Bot, ClipboardList, Command, FileSearch, FileText, Gauge, Home, Network, Search, Settings, Upload, Workflow, X, ChevronRight, ScrollText, Loader2, ArrowUpRight, Building2,
} from "lucide-react";
import { listAnalyses, type AnalysisCase } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { SceneBackground } from "@/components/3d/SceneBackground";

const nav = [
  ["Dashboard", "/dashboard", Home], ["New Analysis", "/dashboard/new", Upload], ["My Analyses", "/dashboard/analyses", FileSearch], ["AI Assistant", "/dashboard/assistant", Bot], ["Knowledge Graph", "/dashboard/knowledge-graph", Network], ["Cross-Domain Search", "/dashboard/cross-domain-search", Search], ["Institution Radar", "/dashboard/institution-radar", Building2], ["Documents", "/dashboard/documents", FileText], ["Appeals", "/dashboard/appeals", ClipboardList], ["Reports", "/dashboard/reports", Gauge], ["Notifications", "/dashboard/notifications", Bell], ["Settings", "/dashboard/settings", Settings],
] as const;

function getDeviceId(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("proxy:device-user-id") ?? "";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [deviceId, setDeviceId] = useState("");

  useEffect(() => setDeviceId(getDeviceId()), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <main className="min-h-screen bg-proxy-black text-proxy-text">
      <SceneBackground />
      <Aurora />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-proxy-cyan focus:px-3 focus:py-2 focus:text-black">Skip to content</a>
      <aside className="fixed left-0 top-0 z-30 hidden h-screen w-72 border-r border-white/10 bg-black/45 p-4 backdrop-blur-2xl lg:block">
        <div className="mb-7 flex items-center gap-3"><div className="grid size-11 place-items-center rounded-lg border border-cyan-300/30 bg-cyan-300/10 shadow-glow-cyan"><Workflow className="size-5 text-cyan-200" /></div><div><p className="text-lg font-semibold">PROXY</p><p className="text-xs text-proxy-muted">AI Claim Analysis</p></div></div>
        <nav className="space-y-1" aria-label="Primary navigation">{nav.map(([label, href, Icon]) => <Link key={label} href={href} className="group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-proxy-muted transition hover:bg-white/8 hover:text-proxy-text focus-visible:bg-white/10"><Icon className="size-4 text-cyan-200/70 group-hover:text-cyan-200" />{label}</Link>)}</nav>
        <Link href="/dashboard/new" className="motion-card mt-6 block rounded-lg border border-purple-300/20 bg-purple-400/10 p-4 shadow-glow-purple transition-colors hover:border-purple-300/40">
          <p className="text-sm font-medium">Start a new analysis</p>
          <p className="mt-2 text-xs leading-5 text-proxy-muted">Real multi-agent reasoning across all 8 domains -- evidence, citations, and drafted appeals.</p>
        </Link>
        <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between rounded-lg border border-white/10 bg-white/5 p-3">
          <div className="min-w-0">
            <p className="truncate font-mono text-xs font-medium text-proxy-text">{deviceId ? deviceId.replace("device-", "").slice(0, 13) : "..."}</p>
            <p className="text-xs text-proxy-muted">Your device identity</p>
          </div>
          <Link href="/dashboard/settings" aria-label="Open settings" className="shrink-0 rounded-md border border-white/10 p-2 text-cyan-200 hover:border-cyan-300/30">
            <Settings className="size-4" />
          </Link>
        </div>
      </aside>
      <section id="main" className="lg:pl-72">{children}</section>
      <button onClick={() => setPaletteOpen(true)} className="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-full border border-cyan-300/30 bg-black/70 px-4 py-3 text-sm text-cyan-100 shadow-glow-cyan backdrop-blur-xl"><Command className="size-4" /> Ctrl K</button>
      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
    </main>
  );
}

function Aurora() {
  return <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"><div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(0,229,255,.18),transparent_28%),radial-gradient(circle_at_82%_18%,rgba(155,92,255,.16),transparent_30%),linear-gradient(180deg,#050505,#090a0f_52%,#050505)]" /><div className="absolute inset-0 bg-[linear-gradient(120deg,transparent,rgba(255,255,255,.045),transparent)] opacity-40" /></div>;
}

function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listAnalyses()
      .then(setAnalyses)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const matchedAnalyses = useMemo(() => {
    if (!query.trim()) return analyses.slice(0, 5);
    const q = query.toLowerCase();
    return analyses.filter((a) => a.title.toLowerCase().includes(q) || a.institution_name.toLowerCase().includes(q)).slice(0, 6);
  }, [analyses, query]);

  const matchedNav = useMemo(() => {
    if (!query.trim()) return nav;
    const q = query.toLowerCase();
    return nav.filter(([label]) => label.toLowerCase().includes(q));
  }, [query]);

  function go(href: string) {
    router.push(href);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-start bg-black/70 px-4 pt-20 backdrop-blur-md" role="dialog" aria-modal="true" aria-label="Global command palette" onClick={onClose}>
      <div className="mx-auto w-full max-w-2xl rounded-xl border border-cyan-300/20 bg-[#080a0f]/95 p-3 shadow-glow-cyan" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-white/10 px-2 pb-3">
          <Search className="size-5 text-cyan-200" />
          <input
            ref={inputRef}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && query.trim() && go(`/dashboard/assistant?q=${encodeURIComponent(query.trim())}`)}
            placeholder="Search your analyses, jump to a page, or ask the AI Assistant..."
            className="h-11 flex-1 bg-transparent text-sm outline-none placeholder:text-proxy-tertiary"
          />
          <button onClick={onClose} aria-label="Close command palette" className="rounded-md p-2 text-proxy-muted hover:bg-white/10"><X className="size-4" /></button>
        </div>

        <div className="mt-2 max-h-[60vh] overflow-y-auto">
          {query.trim() && (
            <button onClick={() => go(`/dashboard/assistant?q=${encodeURIComponent(query.trim())}`)} className="flex w-full items-center justify-between rounded-lg px-3 py-3 text-left text-sm text-cyan-100 hover:bg-cyan-300/10">
              <span className="flex items-center gap-2"><Bot className="size-4" /> Ask the AI Assistant: &ldquo;{query.trim()}&rdquo;</span>
              <ArrowUpRight className="size-4" />
            </button>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-6 text-proxy-tertiary"><Loader2 className="size-4 animate-spin" /></div>
          ) : matchedAnalyses.length > 0 ? (
            <div className="mt-1">
              <p className="px-3 py-1 text-[10px] uppercase tracking-wide text-proxy-tertiary">{query.trim() ? "Matching analyses" : "Recent analyses"}</p>
              {matchedAnalyses.map((a) => {
                const theme = domainTheme(a.domains_involved[0] ?? a.domain);
                return (
                  <button
                    key={a.id}
                    onClick={() => go(`/dashboard/analyses?case=${encodeURIComponent(a.id)}`)}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-left text-sm text-proxy-muted hover:bg-white/8 hover:text-proxy-text"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <ScrollText className="size-3.5 shrink-0" style={{ color: theme.color }} />
                      <span className="truncate">{a.title}</span>
                    </span>
                    <ChevronRight className="size-4 shrink-0" />
                  </button>
                );
              })}
            </div>
          ) : query.trim() ? (
            <p className="px-3 py-3 text-xs text-proxy-tertiary">No analyses match &ldquo;{query.trim()}&rdquo;.</p>
          ) : null}

          {matchedNav.length > 0 && (
            <div className="mt-1 border-t border-white/5 pt-1">
              <p className="px-3 py-1 text-[10px] uppercase tracking-wide text-proxy-tertiary">Pages</p>
              {matchedNav.map(([label, href, Icon]) => (
                <button key={label} onClick={() => go(href)} className="flex w-full items-center justify-between rounded-lg px-3 py-3 text-left text-sm text-proxy-muted hover:bg-white/8 hover:text-proxy-text">
                  <span className="flex items-center gap-2"><Icon className="size-4 text-cyan-200/70" /> {label}</span>
                  <ChevronRight className="size-4" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
