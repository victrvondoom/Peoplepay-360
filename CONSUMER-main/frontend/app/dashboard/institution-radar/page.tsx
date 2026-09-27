"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, AlertTriangle, TrendingUp, Building2, ArrowUpRight, Search, Network } from "lucide-react";
import { getInstitutionRadar, type InstitutionRadarEntry } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";

export default function InstitutionRadarPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<InstitutionRadarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getInstitutionRadar(25);
        if (!cancelled) setEntries(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load the radar. Is the backend running?");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const maxCases = entries.length > 0 ? entries[0].total_cases : 1;
  const filtered = useMemo(
    () => entries.filter((e) => e.institution_name.toLowerCase().includes(search.toLowerCase())),
    [entries, search]
  );
  const totalDisputes = useMemo(() => entries.reduce((sum, e) => sum + e.total_cases, 0), [entries]);
  const domainsCovered = useMemo(() => new Set(entries.flatMap((e) => e.by_domain.map((d) => d.domain))).size, [entries]);

  function viewPatterns(entry: InstitutionRadarEntry) {
    // Deep-link into the Institution Intelligence 3D graph (real patterns +
    // similar cases, not just a text answer) -- default to whichever domain
    // has the most disputes for this institution, since that's what the
    // user almost always means to inspect first.
    const topDomain = [...entry.by_domain].sort((a, b) => b.case_count - a.case_count)[0]?.domain;
    if (!topDomain) return;
    router.push(`/dashboard/knowledge-graph?domain=${encodeURIComponent(topDomain)}&institution=${encodeURIComponent(entry.institution_name)}`);
  }

  return (
    <div className="relative z-10 mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-[0.22em] text-cyan-200">PROXY Enterprise Intelligence</p>
        <h1 className="mt-1 bg-gradient-to-r from-white via-cyan-100 to-purple-200 bg-clip-text text-3xl font-semibold text-transparent sm:text-4xl">
          Institution Accountability Radar
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-proxy-muted">
          Real dispute volume per institution, aggregated across every citizen and every domain in the knowledge graph --
          not a single user's opinion, a pattern that only becomes visible once enough real cases accumulate. A single
          conversation with a chatbot can never show you this; it has no memory of anyone else's case.
        </p>
        {!loading && !error && entries.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-4 text-xs text-proxy-muted">
            <span><span className="font-semibold text-proxy-text">{entries.length}</span> institutions tracked</span>
            <span><span className="font-semibold text-proxy-text">{totalDisputes}</span> disputes on file</span>
            <span><span className="font-semibold text-proxy-text">{domainsCovered}</span> domains covered</span>
          </div>
        )}
      </header>

      {!loading && !error && entries.length > 0 && (
        <div className="relative mb-4 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-proxy-tertiary" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search institutions..."
            className="w-full rounded-lg border border-white/10 bg-black/30 py-1.5 pl-8 pr-2 text-xs text-proxy-text outline-none placeholder:text-proxy-tertiary focus:border-cyan-300/40"
          />
        </div>
      )}

      {loading && (
        <div className="rounded-2xl border border-white/10 bg-glass p-10 text-center backdrop-blur-2xl">
          <Loader2 className="mx-auto mb-3 size-6 animate-spin text-cyan-200" />
          <p className="text-sm text-proxy-muted">Aggregating real case data from the graph...</p>
        </div>
      )}

      {error && !loading && (
        <div className="rounded-xl border border-red-300/25 bg-red-300/10 px-4 py-3 text-sm text-red-100">{error}</div>
      )}

      {!loading && !error && entries.length === 0 && (
        <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.015] p-10 text-center">
          <Building2 className="mx-auto mb-3 size-8 text-proxy-tertiary" />
          <p className="text-sm text-proxy-tertiary">No institution patterns yet -- this fills in as real cases are analyzed.</p>
        </div>
      )}

      {!loading && !error && entries.length > 0 && filtered.length === 0 && (
        <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.015] p-10 text-center">
          <Search className="mx-auto mb-3 size-8 text-proxy-tertiary" />
          <p className="text-sm text-proxy-tertiary">No institution matches &quot;{search}&quot;.</p>
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="space-y-2.5">
          {filtered.map((entry) => (
            <InstitutionRow
              key={entry.institution_name}
              rank={entries.indexOf(entry) + 1}
              entry={entry}
              maxCases={maxCases}
              onAsk={() =>
                router.push(`/dashboard/assistant?q=${encodeURIComponent(`What patterns exist in disputes against ${entry.institution_name}?`)}`)
              }
              onViewPatterns={() => viewPatterns(entry)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function InstitutionRow({
  rank, entry, maxCases, onAsk, onViewPatterns,
}: {
  rank: number;
  entry: InstitutionRadarEntry;
  maxCases: number;
  onAsk: () => void;
  onViewPatterns: () => void;
}) {
  const widthPct = Math.max(4, Math.round((entry.total_cases / maxCases) * 100));
  const isHigh = rank <= 3;
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-2xl">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={`grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold ${isHigh ? "bg-amber-300/20 text-amber-200" : "bg-white/5 text-proxy-tertiary"}`}
          >
            {rank}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-proxy-text">{entry.institution_name}</p>
            <p className="text-[11px] text-proxy-tertiary">
              {entry.by_domain.length} domain{entry.by_domain.length === 1 ? "" : "s"}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {isHigh && <AlertTriangle className="size-4 text-amber-300" />}
          <div className="text-right">
            <p className="text-lg font-semibold text-proxy-text">{entry.total_cases}</p>
            <p className="text-[10px] text-proxy-tertiary">disputes on file</p>
          </div>
        </div>
      </div>

      <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full"
          style={{ width: `${widthPct}%`, backgroundColor: isHigh ? "#ffc857" : "#00e5ff" }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {entry.by_domain.map((d) => {
          const theme = domainTheme(d.domain);
          return (
            <span
              key={d.domain}
              className="rounded-full border px-2 py-0.5 text-[10px]"
              style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}
            >
              {theme.label} &middot; {d.case_count}
            </span>
          );
        })}
        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={onViewPatterns}
            className="inline-flex items-center gap-1 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2.5 py-1 text-[10px] text-cyan-100 hover:bg-cyan-300/20"
          >
            <Network className="size-3" /> View real patterns <ArrowUpRight className="size-3" />
          </button>
          <button
            onClick={onAsk}
            className="inline-flex items-center gap-1 rounded-full border border-purple-300/25 bg-purple-300/10 px-2.5 py-1 text-[10px] text-purple-100 hover:bg-purple-300/20"
          >
            <TrendingUp className="size-3" /> Ask about this institution <ArrowUpRight className="size-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
