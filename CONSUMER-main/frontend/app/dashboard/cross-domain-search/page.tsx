"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search, Loader2, ExternalLink, ShieldCheck, Sparkles, Command, Clock, X,
  ChevronDown, ChevronUp, MessageSquare, Zap, Layers, Gauge,
} from "lucide-react";
import { classifyQuery, globalSearch, type DomainCandidate, type GlobalSearchResult } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { EvidenceScoreBreakdown } from "@/components/search/EvidenceScoreBreakdown";

const RECENT_KEY = "proxy:search-recent-queries";
const SORT_OPTIONS = [
  { key: "evidence", label: "Evidence score" },
  { key: "domain", label: "Domain" },
] as const;
type SortKey = (typeof SORT_OPTIONS)[number]["key"];

function loadRecent(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveRecent(query: string) {
  const current = loadRecent().filter((q) => q !== query);
  current.unshift(query);
  window.localStorage.setItem(RECENT_KEY, JSON.stringify(current.slice(0, 8)));
}

export default function CrossDomainSearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [livePreview, setLivePreview] = useState<DomainCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<DomainCandidate[]>([]);
  const [results, setResults] = useState<GlobalSearchResult[]>([]);
  const [domainsSearched, setDomainsSearched] = useState<string[]>([]);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey>("evidence");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const [showRecent, setShowRecent] = useState(false);
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setRecent(loadRecent()), []);

  useEffect(() => {
    if (!loading) {
      setLoadingElapsedMs(0);
      return;
    }
    const start = performance.now();
    const timer = window.setInterval(() => setLoadingElapsedMs(Math.round(performance.now() - start)), 200);
    return () => window.clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    function onKeydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  useEffect(() => {
    if (query.trim().length < 12) {
      setLivePreview([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setLivePreview((await classifyQuery(query)).candidates);
      } catch {
        setLivePreview([]);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [query]);

  async function runSearch(overrideQuery?: string) {
    const q = (overrideQuery ?? query).trim();
    if (!q) return;
    setQuery(q);
    setShowRecent(false);
    setLoading(true);
    setError(null);
    setActiveTab("all");
    const start = performance.now();
    try {
      const [classification, search] = await Promise.all([classifyQuery(q), globalSearch(q)]);
      setCandidates(classification.candidates);
      setResults(search.results);
      setDomainsSearched(search.domains_searched);
      setElapsedMs(Math.round(performance.now() - start));
      saveRecent(q);
      setRecent(loadRecent());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed. Is the backend running?");
      setCandidates([]);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  const domainTabs = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of results) counts.set(r.domain, (counts.get(r.domain) ?? 0) + 1);
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [results]);

  const visibleResults = useMemo(() => {
    let filtered = activeTab === "all" ? results : results.filter((r) => r.domain === activeTab);
    filtered = [...filtered];
    if (sortKey === "evidence") {
      filtered.sort((a, b) => b.evidence_scores.overall_evidence_score - a.evidence_scores.overall_evidence_score);
    } else {
      filtered.sort((a, b) => a.domain.localeCompare(b.domain));
    }
    return filtered;
  }, [results, activeTab, sortKey]);

  const avgConfidence = useMemo(() => {
    if (results.length === 0) return 0;
    return results.reduce((sum, r) => sum + r.evidence_scores.overall_evidence_score, 0) / results.length;
  }, [results]);

  function askAboutQuery(q: string) {
    router.push(`/dashboard/assistant?q=${encodeURIComponent(q)}`);
  }

  return (
    <>
      <div className="relative z-10 mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6">
          <p className="text-xs uppercase tracking-[0.22em] text-cyan-200">PROXY Enterprise Intelligence</p>
          <h1 className="mt-1 bg-gradient-to-r from-white via-cyan-100 to-purple-200 bg-clip-text text-3xl font-semibold text-transparent sm:text-4xl">
            Cross-Domain Search
          </h1>
          <p className="mt-1 text-sm text-proxy-muted">
            Ask one question across all 8 domains at once -- classified, ranked by evidence quality, and cited.
          </p>
        </header>

        {/* Search composer */}
        <div className="relative mb-6">
          <div className="composer-glow flex items-center gap-2 rounded-2xl p-[1.5px]">
            <div className="flex w-full items-center gap-2 rounded-2xl bg-[#07080b] p-1.5">
              <Search className="ml-2.5 size-4 shrink-0 text-proxy-muted" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onFocus={() => setShowRecent(true)}
                onBlur={() => window.setTimeout(() => setShowRecent(false), 150)}
                onKeyDown={(event) => event.key === "Enter" && runSearch()}
                placeholder="e.g. My flight was cancelled and my travel insurance rejected the claim... (Ctrl/Cmd+K)"
                className="flex-1 bg-transparent px-1 py-2.5 text-sm text-proxy-text outline-none placeholder:text-proxy-tertiary"
              />
              {query && (
                <button onClick={() => setQuery("")} className="rounded-lg p-1.5 text-proxy-tertiary hover:text-proxy-text">
                  <X className="size-3.5" />
                </button>
              )}
              <button
                onClick={() => runSearch()}
                disabled={loading || !query.trim()}
                className="search-orb mr-1 inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-40"
              >
                {loading ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                {loading ? "Searching" : "Search"}
              </button>
            </div>
          </div>

          {livePreview.length > 0 && !loading && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 px-1">
              <span className="text-[10px] uppercase tracking-wide text-proxy-tertiary">Detected:</span>
              {livePreview.map((c) => {
                const theme = domainTheme(c.domain);
                return (
                  <span key={c.domain} className="rounded-full border px-2 py-0.5 text-[10px]" style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}>
                    {theme.label}
                  </span>
                );
              })}
            </div>
          )}

          {showRecent && recent.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-10 mt-2 rounded-xl border border-white/10 bg-[#0a0b10] p-2 shadow-xl">
              <p className="mb-1.5 flex items-center gap-1.5 px-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">
                <Clock className="size-3" /> Recent searches
              </p>
              {recent.map((q) => (
                <button
                  key={q}
                  onMouseDown={() => runSearch(q)}
                  className="block w-full truncate rounded-lg px-2 py-1.5 text-left text-xs text-proxy-muted hover:bg-white/5 hover:text-proxy-text"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-red-300/25 bg-red-300/10 px-4 py-3 text-sm text-red-100">{error}</div>
        )}

        {loading && <SearchingPanel elapsedMs={loadingElapsedMs} candidates={livePreview.length > 0 ? livePreview : candidates} />}

        {results.length > 0 && !loading && (
          <>
            {/* Stats bar */}
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatChip icon={Layers} label="Results" value={String(results.length)} />
              <StatChip icon={ShieldCheck} label="Domains" value={String(domainsSearched.length)} />
              <StatChip icon={Gauge} label="Avg. evidence" value={`${Math.round(avgConfidence * 100)}%`} />
              <StatChip icon={Zap} label="Search time" value={elapsedMs !== null ? `${elapsedMs}ms` : "-"} />
            </div>

            {/* Domain tabs */}
            <div className="mb-4 flex flex-wrap items-center gap-1.5">
              <TabChip label="All" count={results.length} active={activeTab === "all"} onClick={() => setActiveTab("all")} />
              {domainTabs.map(([domain, count]) => {
                const theme = domainTheme(domain);
                return (
                  <TabChip
                    key={domain}
                    label={theme.label}
                    count={count}
                    active={activeTab === domain}
                    color={theme.color}
                    onClick={() => setActiveTab(domain)}
                  />
                );
              })}
              <div className="ml-auto flex items-center gap-1.5">
                <span className="text-[10px] text-proxy-tertiary">Sort:</span>
                {SORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => setSortKey(opt.key)}
                    className={`rounded-full border px-2 py-1 text-[10px] transition-colors ${
                      sortKey === opt.key ? "border-cyan-300/40 bg-cyan-300/15 text-cyan-100" : "border-white/10 text-proxy-tertiary hover:border-white/20"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Ask AI CTA */}
            <button
              onClick={() => askAboutQuery(query)}
              className="mb-4 inline-flex items-center gap-1.5 rounded-lg border border-purple-300/25 bg-purple-300/10 px-3 py-1.5 text-xs text-purple-100 hover:bg-purple-300/20"
            >
              <MessageSquare className="size-3.5" /> Ask the AI Assistant to reason about this &rarr;
            </button>

            {/* Results */}
            <div className="space-y-3">
              {visibleResults.map((result) => (
                <ResultCard
                  key={result.id}
                  result={result}
                  expanded={expandedId === result.id}
                  onToggle={() => setExpandedId(expandedId === result.id ? null : result.id)}
                />
              ))}
            </div>
          </>
        )}

        {!loading && !error && results.length === 0 && (
          <EmptyState onPick={(q) => runSearch(q)} />
        )}
      </div>
      <style jsx>{`
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
        .search-orb {
          background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0);
          box-shadow: 0 0 18px rgba(0, 229, 255, 0.35);
        }
      `}</style>
    </>
  );
}

function SearchingPanel({ elapsedMs, candidates }: { elapsedMs: number; candidates: DomainCandidate[] }) {
  const seconds = (elapsedMs / 1000).toFixed(1);
  return (
    <div className="mb-6 rounded-2xl border border-cyan-300/15 bg-glass p-6 text-center backdrop-blur-2xl">
      <Loader2 className="mx-auto mb-3 size-6 animate-spin text-cyan-200" />
      <p className="text-sm text-proxy-text">Searching across all 8 domains and ranking by evidence quality...</p>
      <p className="mt-1 font-mono text-xs text-proxy-tertiary">{seconds}s elapsed -- real vector search + LLM-scored evidence, not instant by nature</p>
      {candidates.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wide text-proxy-tertiary">Most relevant:</span>
          {candidates.map((c) => {
            const theme = domainTheme(c.domain);
            return (
              <span key={c.domain} className="rounded-full border px-2 py-0.5 text-[10px]" style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}>
                {theme.label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatChip({ icon: Icon, label, value }: { icon: typeof Layers; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-glass p-3 backdrop-blur-2xl">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-proxy-tertiary">
        <Icon className="size-3" /> {label}
      </div>
      <p className="text-lg font-semibold text-proxy-text">{value}</p>
    </div>
  );
}

function TabChip({ label, count, active, onClick, color }: { label: string; count: number; active: boolean; onClick: () => void; color?: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
        active ? "border-cyan-300/40 bg-cyan-300/15 text-cyan-100" : "border-white/10 text-proxy-muted hover:border-white/20"
      }`}
      style={active && color ? { borderColor: `${color}50`, backgroundColor: `${color}1a`, color } : undefined}
    >
      {label} <span className="opacity-60">{count}</span>
    </button>
  );
}

function ResultCard({ result, expanded, onToggle }: { result: GlobalSearchResult; expanded: boolean; onToggle: () => void }) {
  const theme = domainTheme(result.domain);
  const authority = typeof result.metadata.authority === "string" ? result.metadata.authority : null;
  const sourceUrl = typeof result.metadata.source_url === "string" ? result.metadata.source_url : null;

  return (
    <div
      className="overflow-hidden rounded-2xl border border-white/10 bg-glass backdrop-blur-2xl transition-colors hover:border-cyan-300/25"
      style={{ borderLeftColor: theme.color, borderLeftWidth: 3 }}
    >
      <div className="p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="rounded-full px-2.5 py-0.5 text-[10px]" style={{ backgroundColor: `${theme.color}1a`, color: theme.color }}>
            {theme.label}
          </span>
          {authority && (
            <span className="inline-flex items-center gap-1 text-[11px] text-proxy-tertiary">
              <ShieldCheck className="size-3" /> {authority}
            </span>
          )}
          <button
            onClick={onToggle}
            className="ml-auto flex items-center gap-1 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-proxy-muted hover:border-cyan-300/30"
          >
            {Math.round(result.evidence_scores.overall_evidence_score * 100)}% evidence
            {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </button>
        </div>
        <p className={`text-sm leading-6 text-proxy-muted ${expanded ? "" : "line-clamp-4"}`}>{result.text}</p>
        {sourceUrl && (
          <a href={sourceUrl} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs text-cyan-200 hover:text-cyan-100">
            View source <ExternalLink className="size-3" />
          </a>
        )}
      </div>
      {expanded && (
        <div className="border-t border-white/5 bg-black/20 p-4">
          <p className="mb-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">Why this ranked here</p>
          <EvidenceScoreBreakdown scores={result.evidence_scores} />
        </div>
      )}
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  const suggestions = [
    "My flight was cancelled and my travel insurance rejected the claim",
    "My builder delayed possession of my flat under RERA",
    "What are the symptoms of dengue fever?",
    "My credit card was charged twice for the same transaction",
  ];
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.015] p-10 text-center">
      <Command className="mx-auto mb-3 size-8 text-proxy-tertiary" />
      <p className="mb-4 text-sm text-proxy-tertiary">
        Try a question that spans more than one domain -- e.g. a cancelled flight with a rejected travel insurance
        claim -- to see PROXY classify and search both at once.
      </p>
      <div className="mx-auto grid max-w-lg gap-2 sm:grid-cols-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-left text-xs text-proxy-muted transition-colors hover:border-cyan-300/30 hover:text-proxy-text"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
