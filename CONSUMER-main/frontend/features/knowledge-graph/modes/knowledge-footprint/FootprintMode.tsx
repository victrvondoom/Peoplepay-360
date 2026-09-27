"use client";

import { useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import { Building2, ChevronRight, Landmark, Layers, ScrollText, TrendingUp, Users, X } from "lucide-react";
import { useDeviceTier } from "@/components/landing/useDeviceTier";
import { domainTheme } from "@/components/chat/domain-theme";
import { useKnowledgeGraphStore } from "../../store";
import { useKnowledgeFootprintQuery } from "../../queries";
import { LoadingOrbs } from "../../components/LoadingOrbs";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { Fallback2DGraph, type Fallback2DEdge, type Fallback2DNode } from "../../scene/Fallback2DGraph";
import { TimelineScrubber } from "./TimelineScrubber";
import type { OrreryDomain } from "./FootprintScene3D";

const FootprintScene3D = dynamic(() => import("./FootprintScene3D"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[720px] items-center justify-center">
      <div className="size-6 animate-spin rounded-full border-2 border-amber-300/30 border-t-amber-300" />
    </div>
  ),
});

function StatCard({ icon: Icon, label, value, accent }: { icon: typeof Users; label: string; value: string; accent: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl">
      <div className="mb-2 grid size-8 place-items-center rounded-lg border" style={{ borderColor: `${accent}40`, backgroundColor: `${accent}15` }}>
        <Icon className="size-4" style={{ color: accent }} />
      </div>
      <p className="truncate font-mono text-lg font-semibold text-proxy-text">{value}</p>
      <p className="text-[11px] text-proxy-tertiary">{label}</p>
    </div>
  );
}

/** Mode 3: My Knowledge Footprint (spec 7) -- the Personal Knowledge
 * Orrery. YOU at the center; domains orbit as planets (radius = recency,
 * size = case volume); cases orbit their domain as moons; a timeline
 * scrubber replays the history growing. */
export function FootprintMode({ onOpenCase }: { onOpenCase: (caseId: string) => void }) {
  const tier = useDeviceTier();
  const { selectedDomain, setSelectedDomain, revealCount, setRevealCount, scrubPlaying, setScrubPlaying } = useKnowledgeGraphStore();
  const footprintQuery = useKnowledgeFootprintQuery();

  const orreryDomains: OrreryDomain[] = useMemo(() => {
    if (!footprintQuery.data) return [];
    return footprintQuery.data.by_domain.map((entry) => {
      const theme = domainTheme(entry.domain);
      const known = entry.cases.map((c) => c.created_at).filter((v): v is string => Boolean(v));
      const mostRecentAt = known.length ? known.reduce((a, b) => (a > b ? a : b)) : null;
      return {
        domain: entry.domain,
        label: theme.label,
        color: theme.color,
        caseCount: entry.case_count,
        cases: entry.cases.map((c) => ({ caseId: c.case_id, title: c.title, createdAt: c.created_at, avgConfidence: c.avg_confidence })),
        mostRecentAt,
      };
    });
  }, [footprintQuery.data]);

  const timelineEvents = useMemo(() => {
    const events: { caseId: string; title: string; createdAt: string }[] = [];
    orreryDomains.forEach((d) => d.cases.forEach((c) => { if (c.createdAt) events.push({ caseId: c.caseId, title: c.title, createdAt: c.createdAt }); }));
    events.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
    return events;
  }, [orreryDomains]);

  useEffect(() => { setRevealCount(timelineEvents.length); }, [timelineEvents.length, setRevealCount]);

  useEffect(() => {
    if (!scrubPlaying) return;
    if (revealCount >= timelineEvents.length) { setScrubPlaying(false); return; }
    const t = window.setInterval(() => setRevealCount(Math.min(timelineEvents.length, useKnowledgeGraphStore.getState().revealCount + 1)), 420);
    return () => window.clearInterval(t);
  }, [scrubPlaying, timelineEvents.length, revealCount, setRevealCount, setScrubPlaying]);

  const revealedCaseIds = useMemo(() => new Set(timelineEvents.slice(0, revealCount).map((e) => e.caseId)), [timelineEvents, revealCount]);

  const fallbackNodes: Fallback2DNode[] = useMemo(() => {
    const maxCases = Math.max(1, ...orreryDomains.map((d) => d.caseCount));
    return [
      { id: "you", kind: "you", label: "YOU", size: 30 },
      ...orreryDomains.map((d) => ({ id: d.domain, kind: "domain" as const, label: d.label, size: 16 + (d.caseCount / maxCases) * 18 })),
    ];
  }, [orreryDomains]);
  const fallbackEdges: Fallback2DEdge[] = orreryDomains.map((d) => ({ source: "you", target: d.domain }));

  if (footprintQuery.isLoading) return <LoadingOrbs label="Loading your knowledge footprint..." />;
  if (footprintQuery.isError) return <ErrorState message={(footprintQuery.error as Error).message} onRetry={() => footprintQuery.refetch()} />;
  if (!footprintQuery.data || footprintQuery.data.total_cases === 0) {
    return (
      <EmptyState
        icon={Users}
        title="Your orrery is empty"
        description="Ask the AI Assistant a question about any case and YOU will appear at the center, ready for your first domain planet to form around you."
      />
    );
  }

  const profile = footprintQuery.data;
  const activeDomain = orreryDomains.find((d) => d.domain === selectedDomain) ?? null;

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard icon={Users} label="Total cases" value={String(profile.total_cases)} accent="#00e5ff" />
        <StatCard icon={Layers} label="Active domains" value={String(profile.domains_active_in.length)} accent="#9b5cff" />
        <StatCard icon={TrendingUp} label="Avg. confidence" value={profile.avg_confidence !== null ? `${Math.round(profile.avg_confidence * 100)}%` : "-"} accent="#37f29a" />
        <StatCard icon={Building2} label="Most active domain" value={profile.most_active_domain ? domainTheme(profile.most_active_domain).label : "-"} accent="#ffc857" />
      </div>

      <div className="grid flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col gap-3">
          <section className="relative min-h-[720px] flex-1 overflow-hidden rounded-2xl border border-cyan-300/15 bg-[#050608] shadow-glow-cyan">
            <div className="absolute left-4 top-4 z-10 rounded-xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur-xl">
              <p className="font-mono text-xs uppercase tracking-[.18em] text-proxy-tertiary">Personal Knowledge Orrery</p>
              <p className="text-sm text-cyan-100">{profile.total_cases} case{profile.total_cases === 1 ? "" : "s"} across {profile.domains_active_in.length} domain{profile.domains_active_in.length === 1 ? "" : "s"}</p>
            </div>
            {tier === "high" ? (
              <FootprintScene3D domains={orreryDomains} revealedCaseIds={revealedCaseIds} selectedDomain={selectedDomain} onSelectDomain={setSelectedDomain} onSelectCase={onOpenCase} />
            ) : (
              <Fallback2DGraph nodes={fallbackNodes} edges={fallbackEdges} anchorId="you" selectedId={selectedDomain} onSelect={setSelectedDomain} />
            )}
          </section>
          <TimelineScrubber
            events={timelineEvents}
            revealCount={revealCount}
            playing={scrubPlaying}
            onScrub={(count) => { setScrubPlaying(false); setRevealCount(count); }}
            onPlayPause={() => setScrubPlaying(!scrubPlaying)}
            onReset={() => { setScrubPlaying(false); setRevealCount(timelineEvents.length); }}
          />
        </div>

        <aside className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl">
          {activeDomain ? (
            <>
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="grid size-9 place-items-center rounded-lg border" style={{ borderColor: activeDomain.color, boxShadow: `0 0 18px ${activeDomain.color}55` }}>
                    <Layers className="size-4" style={{ color: activeDomain.color }} />
                  </div>
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">Domain</p>
                    <p className="text-sm font-semibold text-proxy-text">{activeDomain.label}</p>
                  </div>
                </div>
                <button onClick={() => setSelectedDomain(null)} className="text-proxy-tertiary hover:text-proxy-text"><X className="size-4" /></button>
              </div>
              <div className="mb-4 grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-white/5 bg-black/20 p-2 text-center">
                  <p className="font-mono text-sm font-semibold text-proxy-text">{activeDomain.caseCount}</p>
                  <p className="text-[9px] text-proxy-tertiary">Cases</p>
                </div>
                <div className="rounded-lg border border-white/5 bg-black/20 p-2 text-center">
                  <p className="font-mono text-sm font-semibold text-proxy-text">
                    {(() => {
                      const confidences = activeDomain.cases.map((c) => c.avgConfidence).filter((v): v is number => v !== null && v !== undefined);
                      return confidences.length ? `${Math.round((confidences.reduce((s, c) => s + c, 0) / confidences.length) * 100)}%` : "-";
                    })()}
                  </p>
                  <p className="text-[9px] text-proxy-tertiary">Avg. confidence</p>
                </div>
              </div>
              {(() => {
                const backing = footprintQuery.data?.by_domain.find((d) => d.domain === activeDomain.domain);
                return backing && backing.institutions.length > 0 ? (
                  <div className="mb-4">
                    <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">Institutions</p>
                    <div className="flex flex-wrap gap-1.5">
                      {backing.institutions.map((name) => (
                        <span key={name} className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-proxy-muted">
                          <Landmark className="size-2.5" /> {name}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null;
              })()}
              <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">Cases</p>
              <div className="space-y-1.5">
                {activeDomain.cases.map((c) => (
                  <button key={c.caseId} onClick={() => onOpenCase(c.caseId)} className="flex w-full items-center gap-2 rounded-lg border border-white/5 bg-black/20 p-2 text-left text-xs text-proxy-text hover:border-cyan-300/25">
                    <ScrollText className="size-3 shrink-0 text-proxy-tertiary" />
                    <span className="min-w-0 flex-1 truncate">{c.title}</span>
                    <ChevronRight className="size-3 shrink-0 text-proxy-tertiary" />
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-proxy-tertiary">Click a domain planet to see confidence, institutions, and cases -- or a moon to jump straight into that case's Reasoning Trail.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
