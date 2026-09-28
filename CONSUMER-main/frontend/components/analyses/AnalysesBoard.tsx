"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search, LayoutGrid, List as ListIcon, Star, Pin, Plus, X, Download,
  Clock, TrendingUp, Layers, Loader2, GripVertical, FileText, MessageSquare,
} from "lucide-react";
import {
  listAnalyses, updateCaseStatus, getCaseReport,
  type AnalysisCase, type CaseStatus, type CaseReportData,
} from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";

const STATUS_COLUMNS: Array<{ key: string; label: string; statuses: CaseStatus[]; dropStatus: CaseStatus }> = [
  { key: "intake", label: "Intake", statuses: ["draft", "intake"], dropStatus: "intake" },
  { key: "analyzing", label: "Analyzing", statuses: ["analyzing"], dropStatus: "analyzing" },
  { key: "review", label: "Review Required", statuses: ["review_required"], dropStatus: "review_required" },
  { key: "action_ready", label: "Action Ready", statuses: ["ready_for_approval"], dropStatus: "ready_for_approval" },
  { key: "done", label: "Submitted / Resolved", statuses: ["submitted", "resolved", "closed"], dropStatus: "submitted" },
];

const STATUS_LABELS: Record<CaseStatus, string> = {
  draft: "Draft",
  intake: "Intake",
  analyzing: "Analyzing",
  review_required: "Review Required",
  ready_for_approval: "Action Ready",
  submitted: "Submitted",
  resolved: "Resolved",
  closed: "Closed",
};

const PINNED_KEY = "proxy:analyses-pinned";
const FAVORITE_KEY = "proxy:analyses-favorite";

function loadIdSet(key: string): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(window.localStorage.getItem(key) ?? "[]"));
  } catch {
    return new Set();
  }
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function AnalysesBoard() {
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"board" | "list">("board");
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<AnalysisCase | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);

  async function refresh() {
    try {
      setAnalyses(await listAnalyses());
    } catch {
      // keep last-known list on a transient failure
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    setPinned(loadIdSet(PINNED_KEY));
    setFavorites(loadIdSet(FAVORITE_KEY));
  }, []);

  // Deep-link from the command palette or /dashboard/analyses/[id] --
  // opens straight into that case's detail panel instead of requiring the
  // user to find it in the board.
  useEffect(() => {
    if (loading || analyses.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const caseId = params.get("case");
    if (caseId) {
      const match = analyses.find((a) => a.id === caseId);
      if (match) setSelected(match);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [loading, analyses]);

  function togglePin(id: string) {
    setPinned((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      window.localStorage.setItem(PINNED_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  function toggleFavorite(id: string) {
    setFavorites((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      window.localStorage.setItem(FAVORITE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  async function moveToStatus(analysis: AnalysisCase, status: CaseStatus) {
    setAnalyses((current) => current.map((a) => (a.id === analysis.id ? { ...a, status } : a)));
    try {
      await updateCaseStatus(analysis.id, status);
    } catch {
      refresh();
    }
  }

  const filtered = useMemo(() => {
    return analyses.filter((a) => {
      if (search && !a.title.toLowerCase().includes(search.toLowerCase())) return false;
      if (domainFilter !== "all" && !a.domains_involved.includes(domainFilter) && a.domain !== domainFilter) return false;
      return true;
    });
  }, [analyses, search, domainFilter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const aPinned = pinned.has(a.id) ? 1 : 0;
      const bPinned = pinned.has(b.id) ? 1 : 0;
      if (aPinned !== bPinned) return bPinned - aPinned;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
  }, [filtered, pinned]);

  const stats = useMemo(() => {
    const confidences = analyses.map((a) => a.avg_confidence).filter((c): c is number => c !== null);
    const domainsEngaged = new Set(analyses.flatMap((a) => a.domains_involved));
    return {
      total: analyses.length,
      avgConfidence: confidences.length ? confidences.reduce((s, c) => s + c, 0) / confidences.length : null,
      domainsEngaged: domainsEngaged.size,
    };
  }, [analyses]);

  function exportAnalysis(analysis: AnalysisCase) {
    const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `analysis-${analysis.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex min-h-[720px] flex-1 flex-col gap-4">
      {/* Header controls */}
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-glass p-3 backdrop-blur-2xl">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-proxy-tertiary" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search analyses..."
            className="w-full rounded-lg border border-white/10 bg-black/30 py-1.5 pl-8 pr-2 text-xs text-proxy-text outline-none placeholder:text-proxy-tertiary focus:border-cyan-300/40"
          />
        </div>
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-proxy-text outline-none"
        >
          <option value="all">All domains</option>
          {Array.from(new Set(analyses.flatMap((a) => a.domains_involved))).sort().map((d) => (
            <option key={d} value={d}>{domainTheme(d).label}</option>
          ))}
        </select>
        <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-black/20 p-0.5">
          <button
            onClick={() => setView("board")}
            className={`rounded-md p-1.5 ${view === "board" ? "bg-cyan-300/15 text-cyan-100" : "text-proxy-tertiary"}`}
          >
            <LayoutGrid className="size-3.5" />
          </button>
          <button
            onClick={() => setView("list")}
            className={`rounded-md p-1.5 ${view === "list" ? "bg-cyan-300/15 text-cyan-100" : "text-proxy-tertiary"}`}
          >
            <ListIcon className="size-3.5" />
          </button>
        </div>
        <button
          onClick={() => router.push("/dashboard/assistant")}
          className="new-orb ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-black"
        >
          <Plus className="size-3.5" /> New Analysis
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard icon={Layers} label="Total analyses" value={String(stats.total)} />
        <StatCard icon={TrendingUp} label="Avg. confidence" value={stats.avgConfidence !== null ? `${Math.round(stats.avgConfidence * 100)}%` : "-"} />
        <StatCard icon={Clock} label="Domains engaged" value={String(stats.domainsEngaged)} />
      </div>

      {loading ? (
        <div className="flex h-40 items-center justify-center text-proxy-tertiary">
          <Loader2 className="size-6 animate-spin" />
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex h-60 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-white/10 text-center">
          <MessageSquare className="size-8 text-proxy-tertiary" />
          <p className="text-sm text-proxy-tertiary">No analyses yet -- ask the AI Assistant a question to create your first one.</p>
          <button onClick={() => router.push("/dashboard/assistant")} className="rounded-lg border border-cyan-300/30 bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-100">
            Go to AI Assistant
          </button>
        </div>
      ) : view === "board" ? (
        <div className="grid flex-1 gap-3 overflow-x-auto lg:grid-cols-5">
          {STATUS_COLUMNS.map((column) => {
            const items = sorted.filter((a) => column.statuses.includes(a.status));
            return (
              <div
                key={column.key}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOverColumn(column.key);
                }}
                onDragLeave={() => setDragOverColumn(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOverColumn(null);
                  const id = e.dataTransfer.getData("text/plain");
                  const analysis = analyses.find((a) => a.id === id);
                  if (analysis && !column.statuses.includes(analysis.status)) {
                    moveToStatus(analysis, column.dropStatus);
                  }
                  setDraggingId(null);
                }}
                className={`flex min-h-[200px] flex-col gap-2 rounded-2xl border p-2.5 transition-colors ${
                  dragOverColumn === column.key ? "border-cyan-300/40 bg-cyan-300/[0.04]" : "border-white/10 bg-black/10"
                }`}
              >
                <div className="flex items-center justify-between px-1">
                  <p className="text-xs font-medium text-proxy-muted">{column.label}</p>
                  <span className="rounded-full bg-white/5 px-1.5 py-0.5 text-[10px] text-proxy-tertiary">{items.length}</span>
                </div>
                <div className="flex flex-1 flex-col gap-2">
                  {items.map((analysis) => (
                    <AnalysisCardEl
                      key={analysis.id}
                      analysis={analysis}
                      pinned={pinned.has(analysis.id)}
                      favorite={favorites.has(analysis.id)}
                      dragging={draggingId === analysis.id}
                      onDragStart={() => setDraggingId(analysis.id)}
                      onOpen={() => setSelected(analysis)}
                      onTogglePin={() => togglePin(analysis.id)}
                      onToggleFavorite={() => toggleFavorite(analysis.id)}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((analysis) => (
            <AnalysisListRow
              key={analysis.id}
              analysis={analysis}
              pinned={pinned.has(analysis.id)}
              favorite={favorites.has(analysis.id)}
              onOpen={() => setSelected(analysis)}
              onTogglePin={() => togglePin(analysis.id)}
              onToggleFavorite={() => toggleFavorite(analysis.id)}
              onExport={() => exportAnalysis(analysis)}
            />
          ))}
        </div>
      )}

      {selected && (
        <AnalysisDetailPanel analysis={selected} onClose={() => setSelected(null)} onStatusChange={(s) => moveToStatus(selected, s)} onExport={() => exportAnalysis(selected)} />
      )}

      <style jsx>{`
        .new-orb {
          background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0);
        }
      `}</style>
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: typeof Layers; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-glass p-3 backdrop-blur-2xl">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-proxy-tertiary">
        <Icon className="size-3" /> {label}
      </div>
      <p className="text-lg font-semibold text-proxy-text">{value}</p>
    </div>
  );
}

function ConfidenceRing({ value }: { value: number | null }) {
  if (value === null) return <span className="text-[10px] text-proxy-tertiary">-</span>;
  const circumference = 2 * Math.PI * 9;
  const offset = circumference * (1 - value);
  const color = value >= 0.7 ? "#37f29a" : value >= 0.5 ? "#00e5ff" : "#ffc857";
  return (
    <svg width="24" height="24" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="3" />
      <circle
        cx="12" cy="12" r="9" fill="none" stroke={color} strokeWidth="3"
        strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
        transform="rotate(-90 12 12)"
      />
    </svg>
  );
}

function AnalysisCardEl({
  analysis, pinned, favorite, dragging, onDragStart, onOpen, onTogglePin, onToggleFavorite,
}: {
  analysis: AnalysisCase;
  pinned: boolean;
  favorite: boolean;
  dragging: boolean;
  onDragStart: () => void;
  onOpen: () => void;
  onTogglePin: () => void;
  onToggleFavorite: () => void;
}) {
  const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", analysis.id);
        onDragStart();
      }}
      className={`group cursor-pointer rounded-xl border border-white/10 bg-glass p-3 backdrop-blur-2xl transition-all hover:border-cyan-300/25 ${dragging ? "opacity-40" : ""}`}
      style={{ borderLeftColor: theme.color, borderLeftWidth: 3 }}
      onClick={onOpen}
    >
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <p className="line-clamp-2 flex-1 text-xs font-medium text-proxy-text">{analysis.title}</p>
        <GripVertical className="size-3 shrink-0 cursor-grab text-proxy-tertiary opacity-0 group-hover:opacity-100" />
      </div>
      <div className="mb-2 flex flex-wrap gap-1">
        {analysis.domains_involved.slice(0, 3).map((d) => {
          const t = domainTheme(d);
          return (
            <span key={d} className="rounded-full px-1.5 py-0.5 text-[9px]" style={{ backgroundColor: `${t.color}1a`, color: t.color }}>
              {t.label}
            </span>
          );
        })}
      </div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-proxy-tertiary">{timeAgo(analysis.updated_at)}</span>
        <div className="flex items-center gap-1.5">
          <ConfidenceRing value={analysis.avg_confidence} />
          <button onClick={(e) => { e.stopPropagation(); onToggleFavorite(); }} className={favorite ? "text-amber-300" : "text-proxy-tertiary opacity-0 group-hover:opacity-100"}>
            <Star className="size-3" fill={favorite ? "currentColor" : "none"} />
          </button>
          <button onClick={(e) => { e.stopPropagation(); onTogglePin(); }} className={pinned ? "text-cyan-300" : "text-proxy-tertiary opacity-0 group-hover:opacity-100"}>
            <Pin className="size-3" fill={pinned ? "currentColor" : "none"} />
          </button>
        </div>
      </div>
    </div>
  );
}

function AnalysisListRow({
  analysis, pinned, favorite, onOpen, onTogglePin, onToggleFavorite, onExport,
}: {
  analysis: AnalysisCase;
  pinned: boolean;
  favorite: boolean;
  onOpen: () => void;
  onTogglePin: () => void;
  onToggleFavorite: () => void;
  onExport: () => void;
}) {
  const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);
  return (
    <div
      onClick={onOpen}
      className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/10 bg-glass p-3 backdrop-blur-2xl transition-colors hover:border-cyan-300/25"
      style={{ borderLeftColor: theme.color, borderLeftWidth: 3 }}
    >
      <ConfidenceRing value={analysis.avg_confidence} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-proxy-text">{analysis.title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {analysis.domains_involved.map((d) => {
            const t = domainTheme(d);
            return <span key={d} className="rounded-full px-1.5 py-0.5 text-[9px]" style={{ backgroundColor: `${t.color}1a`, color: t.color }}>{t.label}</span>;
          })}
          <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[9px] text-proxy-tertiary">{STATUS_LABELS[analysis.status]}</span>
        </div>
      </div>
      <span className="shrink-0 text-[11px] text-proxy-tertiary">{timeAgo(analysis.updated_at)}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <button onClick={(e) => { e.stopPropagation(); onToggleFavorite(); }} className={favorite ? "text-amber-300" : "text-proxy-tertiary hover:text-amber-200"}>
          <Star className="size-3.5" fill={favorite ? "currentColor" : "none"} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onTogglePin(); }} className={pinned ? "text-cyan-300" : "text-proxy-tertiary hover:text-cyan-200"}>
          <Pin className="size-3.5" fill={pinned ? "currentColor" : "none"} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onExport(); }} className="text-proxy-tertiary hover:text-cyan-200">
          <Download className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

function AnalysisDetailPanel({
  analysis, onClose, onStatusChange, onExport,
}: {
  analysis: AnalysisCase;
  onClose: () => void;
  onStatusChange: (status: CaseStatus) => void;
  onExport: () => void;
}) {
  const [report, setReport] = useState<CaseReportData | null>(null);
  const [loadingReport, setLoadingReport] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "research" | "strategy" | "appeal" | "evidence" | "timeline">("overview");
  const [copied, setCopied] = useState(false);
  const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);

  useEffect(() => {
    setLoadingReport(true);
    setActiveTab("overview");
    getCaseReport(analysis.id)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoadingReport(false));
  }, [analysis.id]);

  const la = report?.latest_analysis;
  const hasAnalysis = la && (la.final_report || la.research_summary || la.strategy || la.appeal_draft);

  async function copyAppeal() {
    if (!la?.appeal_draft) return;
    await navigator.clipboard.writeText(la.appeal_draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const TABS = [
    { key: "overview", label: "Overview" },
    { key: "research", label: "Research", dot: !!la?.research_summary },
    { key: "strategy", label: "Strategy", dot: !!la?.strategy },
    { key: "appeal", label: "Appeal Draft", dot: !!la?.appeal_draft },
    { key: "evidence", label: "Evidence" },
    { key: "timeline", label: "Timeline" },
  ] as const;

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-lg flex-col border-l border-white/10 bg-[#0a0b10]"
        style={{ borderTopColor: theme.color, borderTopWidth: 3 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-white/10 p-4">
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-sm font-semibold text-proxy-text">{analysis.title}</p>
            <p className="mt-1 text-[11px] text-proxy-tertiary">
              {analysis.institution_name} &middot; {timeAgo(analysis.created_at)} &middot; {analysis.run_count} run{analysis.run_count !== 1 ? "s" : ""}
            </p>
          </div>
          <button onClick={onClose} className="ml-3 shrink-0 rounded-lg border border-white/10 p-1.5 text-proxy-muted hover:text-proxy-text">
            <X className="size-4" />
          </button>
        </div>

        {/* Status + Export bar */}
        <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
          <select
            value={analysis.status}
            onChange={(e) => onStatusChange(e.target.value as CaseStatus)}
            className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-proxy-text outline-none"
          >
            {Object.entries(STATUS_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <button onClick={onExport} className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100">
            <Download className="size-3.5" /> Export JSON
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-0.5 overflow-x-auto border-b border-white/10 px-3 pt-2">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`relative shrink-0 rounded-t-lg px-3 py-1.5 text-[11px] font-medium transition-colors ${
                activeTab === tab.key ? "border-b-2 border-cyan-300 text-cyan-100" : "text-proxy-tertiary hover:text-proxy-muted"
              }`}
            >
              {tab.label}
              {"dot" in tab && tab.dot && <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-cyan-400" />}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loadingReport ? (
            <div className="flex items-center justify-center py-12 text-proxy-tertiary">
              <Loader2 className="size-5 animate-spin" />
              <span className="ml-2 text-xs">Loading analysis...</span>
            </div>
          ) : (
            <>
              {/* OVERVIEW TAB */}
              {activeTab === "overview" && (
                <div className="space-y-4">
                  {/* Domain tags */}
                  <div className="flex flex-wrap gap-1.5">
                    {analysis.domains_involved.map((d) => {
                      const t = domainTheme(d);
                      return <span key={d} className="rounded-full px-2 py-0.5 text-[10px]" style={{ backgroundColor: `${t.color}1a`, color: t.color }}>{t.label}</span>;
                    })}
                  </div>

                  {/* Stats grid */}
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-lg border border-white/5 bg-black/20 p-2">
                      <p className="text-sm font-semibold text-proxy-text">{analysis.avg_confidence !== null ? `${Math.round(analysis.avg_confidence * 100)}%` : "—"}</p>
                      <p className="text-[9px] text-proxy-tertiary">Confidence</p>
                    </div>
                    <div className="rounded-lg border border-white/5 bg-black/20 p-2">
                      <p className="text-sm font-semibold text-proxy-text">{analysis.completed_runs}/{analysis.run_count}</p>
                      <p className="text-[9px] text-proxy-tertiary">Runs done</p>
                    </div>
                    <div className="rounded-lg border border-white/5 bg-black/20 p-2">
                      <p className="text-sm font-semibold text-proxy-text">{report?.appeals.length ?? 0}</p>
                      <p className="text-[9px] text-proxy-tertiary">Appeals</p>
                    </div>
                  </div>

                  {/* Case summary */}
                  <div>
                    <p className="mb-1 text-[10px] uppercase tracking-wide text-proxy-tertiary">Case Summary</p>
                    <p className="text-sm leading-6 text-proxy-muted">{analysis.summary || "No summary available."}</p>
                  </div>

                  {/* Final report (top-level result) */}
                  {la?.final_report && (
                    <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/5 p-3">
                      <p className="mb-2 text-[10px] uppercase tracking-wide text-cyan-300/70">AI Final Report</p>
                      <p className="whitespace-pre-wrap text-xs leading-5 text-proxy-text">{la.final_report}</p>
                    </div>
                  )}

                  {!hasAnalysis && (
                    <div className="rounded-xl border border-dashed border-white/10 p-6 text-center">
                      <p className="text-xs text-proxy-tertiary">No AI analysis yet. Click &quot;Analyze&quot; on this case to generate research, strategy, and appeal drafts.</p>
                    </div>
                  )}

                  {/* Generated appeals */}
                  {report && report.appeals.length > 0 && (
                    <div>
                      <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Generated Documents</p>
                      <div className="space-y-1.5">
                        {report.appeals.map((appeal) => (
                          <div key={appeal.id} className="flex items-center gap-2 rounded-lg border border-white/5 bg-black/20 p-2 text-xs">
                            <FileText className="size-3.5 shrink-0 text-cyan-200" />
                            <span className="truncate text-proxy-text">{appeal.title}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* RESEARCH TAB */}
              {activeTab === "research" && (
                <div className="space-y-4">
                  {la?.research_summary ? (
                    <>
                      <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                        <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Research Summary</p>
                        <p className="whitespace-pre-wrap text-xs leading-5 text-proxy-muted">{la.research_summary}</p>
                      </div>
                      {la.citations.length > 0 && (
                        <div>
                          <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Citations</p>
                          <ul className="space-y-1">
                            {la.citations.map((c, i) => (
                              <li key={i} className="rounded-lg border border-white/5 bg-black/20 px-3 py-1.5 text-xs text-proxy-muted">{c}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="py-8 text-center text-xs text-proxy-tertiary">Research output not yet available. Run the analysis to generate it.</p>
                  )}
                </div>
              )}

              {/* STRATEGY TAB */}
              {activeTab === "strategy" && (
                <div className="space-y-4">
                  {la?.strategy ? (
                    <>
                      <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                        <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">AI Strategy</p>
                        <p className="whitespace-pre-wrap text-xs leading-5 text-proxy-muted">{la.strategy}</p>
                      </div>
                      {la.review_notes.length > 0 && (
                        <div>
                          <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Review Notes</p>
                          <ul className="space-y-1.5">
                            {la.review_notes.map((note, i) => (
                              <li key={i} className="rounded-lg border border-amber-300/20 bg-amber-300/5 px-3 py-1.5 text-xs text-amber-100">{note}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="py-8 text-center text-xs text-proxy-tertiary">Strategy not yet generated. Run the analysis to see the AI's recommended action plan.</p>
                  )}
                </div>
              )}

              {/* APPEAL DRAFT TAB */}
              {activeTab === "appeal" && (
                <div className="space-y-3">
                  {la?.appeal_draft ? (
                    <>
                      <div className="flex items-center justify-between">
                        <p className="text-[10px] uppercase tracking-wide text-proxy-tertiary">Generated Appeal / Complaint Draft</p>
                        <button
                          onClick={copyAppeal}
                          className="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100"
                        >
                          {copied ? "Copied!" : "Copy"}
                        </button>
                      </div>
                      <pre className="whitespace-pre-wrap rounded-xl border border-white/10 bg-black/30 p-4 text-xs leading-5 text-proxy-text">{la.appeal_draft}</pre>
                    </>
                  ) : (
                    <p className="py-8 text-center text-xs text-proxy-tertiary">No appeal draft yet. Run the analysis to auto-generate a draft complaint letter.</p>
                  )}
                </div>
              )}

              {/* EVIDENCE TAB */}
              {activeTab === "evidence" && (
                <div className="space-y-4">
                  {la?.evidence_summary && (
                    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                      <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Evidence Summary</p>
                      <p className="whitespace-pre-wrap text-xs leading-5 text-proxy-muted">{la.evidence_summary}</p>
                    </div>
                  )}
                  <div>
                    <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Uploaded Documents ({report?.documents.length ?? 0})</p>
                    {report?.documents && report.documents.length > 0 ? (
                      <div className="space-y-1.5">
                        {report.documents.map((doc) => (
                          <div key={doc.id} className="flex items-center gap-2 rounded-lg border border-white/5 bg-black/20 p-2.5">
                            <FileText className="size-3.5 shrink-0 text-proxy-tertiary" />
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-xs text-proxy-text">{doc.filename}</p>
                              <p className="text-[10px] text-proxy-tertiary">{doc.document_type} &middot; {doc.size_bytes ? `${Math.round(doc.size_bytes / 1024)} KB` : "—"}</p>
                            </div>
                            {doc.indexed && <span className="shrink-0 rounded-full bg-green-500/10 px-1.5 py-0.5 text-[9px] text-green-400">Indexed</span>}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-proxy-tertiary">No documents uploaded for this case.</p>
                    )}
                  </div>
                </div>
              )}

              {/* TIMELINE TAB */}
              {activeTab === "timeline" && (
                <div className="space-y-2">
                  {report?.events && report.events.length > 0 ? (
                    report.events.map((event, i) => (
                      <div key={event.id || i} className="flex gap-3">
                        <div className="flex flex-col items-center">
                          <div className="mt-0.5 size-2 shrink-0 rounded-full border border-cyan-300/40 bg-cyan-300/20" />
                          {i < (report.events.length - 1) && <div className="mt-1 w-px flex-1 bg-white/5" />}
                        </div>
                        <div className="pb-3 min-w-0">
                          <p className="text-xs font-medium text-proxy-text">{event.title}</p>
                          {event.body && <p className="mt-0.5 text-[11px] leading-4 text-proxy-tertiary">{event.body}</p>}
                          <p className="mt-1 text-[10px] text-proxy-tertiary/60">{event.created_at ? timeAgo(event.created_at) : ""} &middot; {event.actor}</p>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="py-8 text-center text-xs text-proxy-tertiary">No timeline events yet.</p>
                  )}

                  {/* Agent trace */}
                  {la?.agent_trace && la.agent_trace.length > 0 && (
                    <div className="mt-4">
                      <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Agent Execution Trace</p>
                      <div className="rounded-xl border border-white/5 bg-black/30 p-3">
                        {la.agent_trace.map((step, i) => (
                          <p key={i} className="font-mono text-[10px] text-proxy-tertiary">{step}</p>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

