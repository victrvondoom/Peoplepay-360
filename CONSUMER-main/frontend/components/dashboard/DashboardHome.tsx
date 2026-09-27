"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Send, Loader2, ArrowUpRight, FileStack, Scale, FileText, TrendingUp,
  Activity, Upload, Search, Bot, ClipboardList, Network, Gauge, PenLine,
  FileCheck2, ArrowUpCircle, Radio, Command, Zap,
} from "lucide-react";
import {
  classifyQuery, getReportSummary, listAnalyses,
  type DomainCandidate, type ReportSummary, type AnalysisCase,
} from "@/lib/api-client";
import { domainTheme, DOMAIN_THEME } from "@/components/chat/domain-theme";
import { DomainOrbit } from "./DomainOrbit";

const DOMAIN_PROMPTS: Record<string, string> = {
  health_insurance: "My health insurance claim was denied for a pre-existing condition exclusion.",
  banking: "My bank charged me twice for the same transaction and won't refund it.",
  airlines: "My flight was cancelled and the airline refused a refund.",
  telecom: "My telecom provider is billing me for a plan I cancelled two months ago.",
  ecommerce: "An online seller sent me a counterfeit product and refuses a return.",
  government: "My passport renewal application has been stuck in review for 90 days.",
  housing: "My builder delayed possession of my flat by 18 months under RERA.",
  healthcare: "I was overcharged for a hospital procedure that my insurance should have covered.",
};

const EVENT_ICON: Record<string, typeof Activity> = {
  case_created: PenLine,
  document_uploaded: Upload,
  appeal_drafted: FileCheck2,
  appeal_status_changed: ArrowUpCircle,
  agent_run: Activity,
};

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function useCountUp(target: number, durationMs = 900) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let frame: number;
    const start = performance.now();
    function tick(now: number) {
      const progress = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs]);
  return value;
}

function Reveal({ delay = 0, className = "", children }: { delay?: number; className?: string; children: React.ReactNode }) {
  return (
    <div className={className} style={{ animation: `revealUp .7s cubic-bezier(.16,1,.3,1) ${delay}ms both` }}>
      {children}
    </div>
  );
}

export function DashboardHome() {
  const router = useRouter();
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getReportSummary().catch(() => null), listAnalyses().catch(() => [])]).then(
      ([summaryResult, analysesResult]) => {
        setSummary(summaryResult);
        setAnalyses(analysesResult);
        setLoading(false);
      }
    );
  }, []);

  const domainStats = useMemo(() => {
    const counts = new Map<string, number>(summary?.domain_breakdown.map((d) => [d.domain, d.count]) ?? []);
    const confidenceByDomain = new Map<string, number[]>();
    for (const analysis of analyses) {
      for (const domain of analysis.domains_involved) {
        if (analysis.avg_confidence === null) continue;
        const list = confidenceByDomain.get(domain) ?? [];
        list.push(analysis.avg_confidence);
        confidenceByDomain.set(domain, list);
      }
    }
    return Object.keys(DOMAIN_THEME).map((domain) => {
      const confidences = confidenceByDomain.get(domain) ?? [];
      return {
        domain,
        count: counts.get(domain) ?? 0,
        avgConfidence: confidences.length ? confidences.reduce((s, c) => s + c, 0) / confidences.length : null,
      };
    });
  }, [summary, analyses]);

  const totalRuns = useMemo(() => analyses.reduce((sum, a) => sum + a.run_count, 0), [analyses]);
  const overallConfidence = useMemo(() => {
    const values = analyses.map((a) => a.avg_confidence).filter((c): c is number => c !== null);
    return values.length ? values.reduce((s, c) => s + c, 0) / values.length : null;
  }, [analyses]);

  const recentAnalyses = analyses.slice(0, 6);
  const backendOnline = summary !== null;

  function openDomain(domain: string) {
    router.push(`/dashboard/assistant?q=${encodeURIComponent(DOMAIN_PROMPTS[domain] ?? "")}`);
  }

  return (
    <div className="flex flex-1 flex-col gap-4">
      <Reveal delay={0}>
        <HeroComposer backendOnline={backendOnline} />
      </Reveal>

      <Reveal delay={80}>
        <div className="grid gap-4 xl:grid-cols-[1.05fr_.95fr]">
          <section className="flex flex-col rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
            <div className="mb-1 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Domain orbit</h2>
                <p className="mt-0.5 text-xs text-proxy-muted">Live activity across all 8 specialist domains -- click a node to launch a focused analysis.</p>
              </div>
            </div>
            <DomainOrbit stats={domainStats} overallConfidence={overallConfidence} totalRuns={totalRuns} onSelect={openDomain} />
          </section>

          <StatRail summary={summary} totalRuns={totalRuns} overallConfidence={overallConfidence} loading={loading} />
        </div>
      </Reveal>

      <Reveal delay={140}>
        <RecentAnalysesRail analyses={recentAnalyses} loading={loading} onViewAll={() => router.push("/dashboard/analyses")} />
      </Reveal>

      <Reveal delay={200}>
        <div className="grid gap-4 xl:grid-cols-[.62fr_.38fr]">
          <QuickActions />
          <ActivityFeed events={summary?.recent_activity ?? []} loading={loading} />
        </div>
      </Reveal>

      <style jsx global>{`
        @keyframes revealUp {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

function HeroComposer({ backendOnline }: { backendOnline: boolean }) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [livePreview, setLivePreview] = useState<DomainCandidate[]>([]);
  const [classifying, setClassifying] = useState(false);
  const [now, setNow] = useState<Date | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const greeting = !now
    ? "Welcome"
    : now.getHours() < 12
      ? "Good morning"
      : now.getHours() < 18
        ? "Good afternoon"
        : "Good evening";

  useEffect(() => {
    if (input.trim().length < 12) {
      setLivePreview([]);
      return;
    }
    setClassifying(true);
    const timer = window.setTimeout(async () => {
      try {
        setLivePreview((await classifyQuery(input)).candidates);
      } catch {
        setLivePreview([]);
      } finally {
        setClassifying(false);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    function onKeydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        textareaRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  function launch() {
    const text = input.trim();
    if (!text) return;
    router.push(`/dashboard/assistant?q=${encodeURIComponent(text)}`);
  }

  return (
    <section className="relative overflow-hidden rounded-2xl border border-cyan-300/20 bg-glass p-5 shadow-glow-cyan backdrop-blur-2xl sm:p-8">
      <div className="hero-aurora pointer-events-none absolute inset-0 -z-10" />
      <div className="hero-orb pointer-events-none absolute -right-24 -top-24 -z-10 size-72 rounded-full" />

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/30 px-3 py-1">
            <span className={`size-1.5 rounded-full ${backendOnline ? "bg-green-300 animate-pulse" : "bg-red-300"}`} />
            <span className="text-[10px] uppercase tracking-[.2em] text-cyan-200">
              {backendOnline ? "All systems online" : "Backend unreachable"}
            </span>
          </div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{greeting}, Rakesh</h1>
          <p className="mt-1.5 text-sm text-proxy-muted">
            8 domain specialists standing by &middot; parallel multi-agent reasoning &middot; every claim cited
          </p>
        </div>
        <div className="shrink-0 rounded-xl border border-white/10 bg-black/25 px-4 py-2.5 text-right">
          <p className="font-mono text-lg text-proxy-text">
            {now
              ? now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
              : "--:--:--"}
          </p>
          <p className="text-[11px] text-proxy-tertiary">
            {now
              ? now.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" })
              : "\u00a0"}
          </p>
        </div>
      </div>

      {livePreview.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5 px-1">
          <span className="text-[10px] uppercase tracking-wide text-proxy-tertiary">Detected:</span>
          {livePreview.map((candidate) => {
            const theme = domainTheme(candidate.domain);
            return (
              <span
                key={candidate.domain}
                className="rounded-full border px-2 py-0.5 text-[10px]"
                style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}
              >
                {theme.label}
              </span>
            );
          })}
        </div>
      )}

      <div className="composer-glow flex items-end gap-2 rounded-2xl p-[1.5px]">
        <div className="flex w-full items-end gap-2 rounded-2xl bg-[#07080b] p-2.5">
          <Zap className="mb-2.5 ml-1 size-4 shrink-0 text-cyan-300/70" />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                launch();
              }
            }}
            placeholder="Describe your issue -- across any domain, or several at once... (Ctrl/Cmd+K)"
            rows={1}
            className="max-h-32 flex-1 resize-none bg-transparent px-1 py-2.5 text-sm text-proxy-text outline-none placeholder:text-proxy-tertiary"
          />
          <button
            onClick={launch}
            disabled={!input.trim()}
            className="orb-send grid size-10 shrink-0 place-items-center rounded-full text-black transition-transform disabled:cursor-not-allowed disabled:opacity-40 enabled:hover:scale-105"
          >
            {classifying ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </button>
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-1 px-1 text-[10px] text-proxy-tertiary">
        <Command className="size-3" /> K to focus &middot; Enter to launch in the AI Assistant
      </div>

      <style jsx>{`
        .hero-aurora {
          background: radial-gradient(circle at 8% -10%, rgba(0, 229, 255, 0.14), transparent 40%),
            radial-gradient(circle at 95% 0%, rgba(155, 92, 255, 0.12), transparent 45%);
        }
        .hero-orb {
          background: radial-gradient(circle, rgba(0, 229, 255, 0.16), transparent 70%);
          filter: blur(10px);
          animation: float 8s ease-in-out infinite;
        }
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(14px); }
        }
        .composer-glow {
          background: linear-gradient(120deg, rgba(0, 229, 255, 0.5), rgba(155, 92, 255, 0.5), rgba(0, 229, 255, 0.5));
          background-size: 200% 200%;
          animation: glowShift 6s ease infinite;
        }
        @keyframes glowShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        .orb-send {
          background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0);
          box-shadow: 0 0 18px rgba(0, 229, 255, 0.45);
        }
      `}</style>
    </section>
  );
}

function StatRail({
  summary, totalRuns, overallConfidence, loading,
}: {
  summary: ReportSummary | null;
  totalRuns: number;
  overallConfidence: number | null;
  loading: boolean;
}) {
  const rows = [
    { icon: FileStack, label: "Cases", value: summary?.totals.cases ?? 0, accent: "#00e5ff", suffix: "" },
    { icon: Scale, label: "Appeals Generated", value: summary?.totals.appeals ?? 0, accent: "#9b5cff", suffix: "" },
    { icon: FileText, label: "Documents", value: summary?.totals.documents ?? 0, accent: "#37f29a", suffix: "" },
    {
      icon: TrendingUp,
      label: "Resolution Rate",
      value: summary?.resolution_rate !== null && summary?.resolution_rate !== undefined ? Math.round(summary.resolution_rate * 100) : 0,
      accent: "#ffc857",
      suffix: "%",
    },
    { icon: Radio, label: "Agent Runs", value: totalRuns, accent: "#ff6fb0", suffix: "", footnote: overallConfidence !== null ? `${Math.round(overallConfidence * 100)}% avg confidence` : undefined },
  ];
  const maxValue = Math.max(1, ...rows.map((r) => (r.suffix === "%" ? 100 : r.value)));

  return (
    <section className="flex flex-col justify-center rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <p className="mb-3 text-xs font-medium uppercase tracking-[0.16em] text-proxy-tertiary">Snapshot</p>
      <div className="flex flex-col divide-y divide-white/5">
        {rows.map((row) => (
          <StatRailRow key={row.label} {...row} loading={loading} pct={row.suffix === "%" ? row.value : Math.min(100, (row.value / maxValue) * 100)} />
        ))}
      </div>
    </section>
  );
}

function StatRailRow({
  icon: Icon, label, value, accent, suffix, footnote, loading, pct,
}: {
  icon: typeof FileStack;
  label: string;
  value: number;
  accent: string;
  suffix: string;
  footnote?: string;
  loading: boolean;
  pct: number;
}) {
  const animated = useCountUp(loading ? 0 : value);
  return (
    <div className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
      <div className="grid size-8 shrink-0 place-items-center rounded-lg border" style={{ borderColor: `${accent}40`, backgroundColor: `${accent}15` }}>
        <Icon className="size-3.5" style={{ color: accent }} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-xs text-proxy-muted">{label}</span>
          <span className="text-sm font-semibold text-proxy-text">
            {loading ? <Loader2 className="size-3.5 animate-spin text-proxy-tertiary" /> : `${animated}${suffix}`}
          </span>
        </div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/5">
          <div className="h-full rounded-full transition-all duration-700" style={{ width: loading ? "0%" : `${pct}%`, backgroundColor: accent }} />
        </div>
        {footnote && !loading && <p className="mt-1 text-[10px] text-proxy-tertiary">{footnote}</p>}
      </div>
    </div>
  );
}

function RecentAnalysesRail({
  analyses, loading, onViewAll,
}: {
  analyses: AnalysisCase[];
  loading: boolean;
  onViewAll: () => void;
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Recent analyses</h2>
          <p className="mt-0.5 text-xs text-proxy-muted">Your latest multi-agent runs, freshest first.</p>
        </div>
        <button onClick={onViewAll} className="inline-flex items-center gap-1 text-xs text-cyan-200 hover:text-cyan-100">
          View all <ArrowUpRight className="size-3.5" />
        </button>
      </div>
      {loading ? (
        <div className="flex h-40 items-center justify-center"><Loader2 className="size-5 animate-spin text-proxy-tertiary" /></div>
      ) : analyses.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
          <Bot className="size-7 text-proxy-tertiary" />
          <p className="text-sm text-proxy-muted">No analyses yet.</p>
          <p className="max-w-xs text-xs text-proxy-tertiary">Ask a question above to run your first multi-agent analysis.</p>
        </div>
      ) : (
        <div className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-1">
          {analyses.map((analysis) => {
            const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);
            return (
              <button
                key={analysis.id}
                onClick={onViewAll}
                className="motion-card w-64 shrink-0 snap-start rounded-xl border border-white/10 bg-black/20 p-3.5 text-left transition-colors hover:border-cyan-300/30 hover:bg-cyan-300/[0.04]"
                style={{ borderTopColor: theme.color, borderTopWidth: 3 }}
              >
                <p className="line-clamp-2 min-h-9 text-xs font-medium text-proxy-text">{analysis.title}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {analysis.domains_involved.slice(0, 2).map((d) => {
                    const t = domainTheme(d);
                    return <span key={d} className="rounded-full px-1.5 py-0.5 text-[9px]" style={{ backgroundColor: `${t.color}1a`, color: t.color }}>{t.label}</span>;
                  })}
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2.5">
                  <span className="text-[10px] text-proxy-tertiary">{timeAgo(analysis.updated_at)}</span>
                  {analysis.avg_confidence !== null && (
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-proxy-muted">
                      {Math.round(analysis.avg_confidence * 100)}%
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function QuickActions() {
  const actions = [
    { label: "New Analysis", desc: "Ask the AI Assistant", icon: Bot, href: "/dashboard/assistant", accent: "#00e5ff" },
    { label: "Search Everything", desc: "Cross-domain evidence search", icon: Search, href: "/dashboard/cross-domain-search", accent: "#9b5cff" },
    { label: "Upload Document", desc: "Add to your document vault", icon: Upload, href: "/dashboard/documents", accent: "#37f29a" },
    { label: "Appeals Center", desc: "Review generated appeals", icon: ClipboardList, href: "/dashboard/appeals", accent: "#ffc857" },
    { label: "Knowledge Graph", desc: "Explore entity relationships", icon: Network, href: "/dashboard/knowledge-graph", accent: "#ff6fb0" },
    { label: "Reports", desc: "Full analytics breakdown", icon: Gauge, href: "/dashboard/reports", accent: "#5c9bff" },
  ];
  const router = useRouter();
  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <h2 className="mb-3 text-lg font-semibold">Quick actions</h2>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {actions.map((action) => (
          <button
            key={action.label}
            onClick={() => router.push(action.href)}
            className="motion-card group relative flex flex-col items-start gap-2 overflow-hidden rounded-xl border border-white/10 bg-black/20 p-3 text-left transition-colors hover:border-white/25"
          >
            <div
              className="pointer-events-none absolute -right-6 -top-6 size-16 rounded-full opacity-0 blur-xl transition-opacity duration-300 group-hover:opacity-100"
              style={{ backgroundColor: action.accent }}
            />
            <div className="relative grid size-8 place-items-center rounded-lg border" style={{ borderColor: `${action.accent}40`, backgroundColor: `${action.accent}15` }}>
              <action.icon className="size-4" style={{ color: action.accent }} />
            </div>
            <div className="relative">
              <p className="text-xs font-medium text-proxy-text">{action.label}</p>
              <p className="mt-0.5 text-[10px] leading-4 text-proxy-tertiary">{action.desc}</p>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function ActivityFeed({ events, loading }: { events: ReportSummary["recent_activity"]; loading: boolean }) {
  return (
    <section className="flex flex-col rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-5">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-lg font-semibold">Live activity</h2>
        {!loading && events.length > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full border border-green-300/25 bg-green-300/10 px-2 py-0.5 text-[9px] uppercase tracking-wide text-green-200">
            <span className="size-1.5 animate-pulse rounded-full bg-green-300" /> Live
          </span>
        )}
      </div>
      {loading ? (
        <div className="flex h-32 items-center justify-center"><Loader2 className="size-5 animate-spin text-proxy-tertiary" /></div>
      ) : events.length === 0 ? (
        <p className="text-xs text-proxy-tertiary">No activity yet.</p>
      ) : (
        <div className="relative max-h-72 space-y-4 overflow-y-auto pl-1 pr-1">
          <div className="absolute bottom-1 left-[15px] top-1 w-px bg-gradient-to-b from-white/10 via-white/5 to-transparent" />
          {events.map((event) => {
            const Icon = EVENT_ICON[event.event_type] ?? Activity;
            return (
              <div key={event.id} className="relative flex items-start gap-3">
                <div className="relative z-10 mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border border-white/10 bg-[#0a0b10]">
                  <Icon className="size-3 text-cyan-200" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs text-proxy-text">{event.title}</p>
                  <p className="text-[10px] text-proxy-tertiary">{event.actor} &middot; {timeAgo(event.created_at)}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
