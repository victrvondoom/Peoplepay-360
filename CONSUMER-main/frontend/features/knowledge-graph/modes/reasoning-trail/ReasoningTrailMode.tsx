"use client";

import { useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import { Loader2, PlayCircle, Search, Sparkles, Zap } from "lucide-react";
import { useDeviceTier } from "@/components/landing/useDeviceTier";
import { domainTheme } from "@/components/chat/domain-theme";
import { useKnowledgeGraphStore } from "../../store";
import { useCaseGraphQuery, useCaseListQuery, useReasoningTrailQuery } from "../../queries";
import { LoadingOrbs } from "../../components/LoadingOrbs";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { NodeDetailPanel } from "../../components/NodeDetailPanel";
import { ENTITY_COLOR, LEGEND_ITEMS } from "../../scene/legend";
import { Fallback2DGraph, type Fallback2DEdge, type Fallback2DNode } from "../../scene/Fallback2DGraph";
import type { ReplayState } from "./ReasoningTrailScene3D";
import { ReplayTransportBar } from "./ReplayTransportBar";
import { enrichReplaySteps } from "./replaySteps";

const ReasoningTrailScene3D = dynamic(() => import("./ReasoningTrailScene3D"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[720px] items-center justify-center">
      <div className="size-6 animate-spin rounded-full border-2 border-cyan-300/30 border-t-cyan-300" />
    </div>
  ),
});

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Mode 1: Reasoning Trail (spec 5). Left case list, center 3D/2D graph,
 * right static inspector that swaps to a Replay caption track during
 * playback. This is the flagship mode -- Reasoning Replay is "the single
 * most-novel feature on the page" per spec 5.1. */
export function ReasoningTrailMode() {
  const tier = useDeviceTier();
  const {
    selectedCaseId, setSelectedCaseId, selectedNodeId, setSelectedNodeId,
    replayActive, replayIndex, replayPlaying, replaySpeed,
    startReplay, exitReplay, setReplayIndex, setReplayPlaying, setReplaySpeed,
  } = useKnowledgeGraphStore();

  const caseListQuery = useCaseListQuery();
  const caseGraphQuery = useCaseGraphQuery(selectedCaseId);
  const trailQuery = useReasoningTrailQuery(selectedCaseId);

  useEffect(() => {
    if (!selectedCaseId && caseListQuery.data && caseListQuery.data.length > 0) {
      setSelectedCaseId(caseListQuery.data[0].id);
    }
  }, [caseListQuery.data, selectedCaseId, setSelectedCaseId]);

  const nodes = caseGraphQuery.data?.nodes ?? [];
  const edges = caseGraphQuery.data?.edges ?? [];
  const replaySteps = useMemo(() => enrichReplaySteps(trailQuery.data?.steps ?? []), [trailQuery.data]);
  const currentStep = replaySteps[replayIndex] ?? null;
  const activeNode = nodes.find((n) => n.id === selectedNodeId) ?? null;
  const replayFocusNode = currentStep ? nodes.find((n) => n.id === currentStep.nodeId) : null;

  // Autoplay
  useEffect(() => {
    if (!replayPlaying || replaySteps.length === 0) return;
    const interval = window.setInterval(() => {
      const next = useKnowledgeGraphStore.getState().replayIndex + 1;
      if (next >= replaySteps.length) {
        setReplayPlaying(false);
        return;
      }
      setReplayIndex(next);
    }, 1700 / replaySpeed);
    return () => window.clearInterval(interval);
  }, [replayPlaying, replaySpeed, replaySteps.length, setReplayIndex, setReplayPlaying]);

  const replayState: ReplayState | null = replayActive
    ? {
        active: true,
        currentNodeId: currentStep?.nodeId ?? null,
        visitedNodeIds: new Set(replaySteps.slice(0, replayIndex + 1).map((s) => s.nodeId)),
      }
    : null;

  const fallbackNodes: Fallback2DNode[] = nodes.map((n) => ({
    id: n.id, kind: n.kind, label: n.label, size: n.id === "case" ? 34 : n.kind === "domain" || n.kind === "institution" ? 24 : 18,
  }));
  const fallbackEdges: Fallback2DEdge[] = edges;

  return (
    <div className="grid flex-1 gap-4 xl:grid-cols-[260px_minmax(0,1fr)_320px]">
      <aside className="rounded-2xl border border-white/10 bg-glass p-3 backdrop-blur-2xl">
        <div className="mb-3 flex items-center gap-2 px-1">
          <Search className="size-3.5 text-proxy-tertiary" />
          <p className="font-mono text-[10px] uppercase tracking-[.18em] text-proxy-tertiary">Your cases</p>
        </div>
        {caseListQuery.isLoading ? (
          <div className="flex h-32 items-center justify-center"><Loader2 className="size-5 animate-spin text-proxy-tertiary" /></div>
        ) : caseListQuery.isError ? (
          <ErrorState message={(caseListQuery.error as Error).message} onRetry={() => caseListQuery.refetch()} />
        ) : !caseListQuery.data || caseListQuery.data.length === 0 ? (
          <p className="p-3 text-center text-xs text-proxy-tertiary">No analyses yet -- ask the AI Assistant a question to create your first real case.</p>
        ) : (
          <div className="max-h-[640px] space-y-1.5 overflow-y-auto pr-1">
            {caseListQuery.data.map((c) => {
              const t = domainTheme(c.domains_involved?.[0] ?? c.domain);
              const isActive = c.id === selectedCaseId;
              return (
                <button
                  key={c.id}
                  onClick={() => setSelectedCaseId(c.id)}
                  className={`w-full rounded-lg border p-2.5 text-left transition-colors ${isActive ? "border-white/25 bg-white/[0.05]" : "border-white/5 bg-black/20 hover:border-white/15"}`}
                  style={isActive ? { borderLeftColor: t.color, borderLeftWidth: 3 } : undefined}
                >
                  <p className="line-clamp-2 text-xs font-medium text-proxy-text">{c.title}</p>
                  <p className="mt-1 font-mono text-[10px] text-proxy-tertiary">{t.label} &middot; {timeAgo(c.updated_at)}</p>
                </button>
              );
            })}
          </div>
        )}
      </aside>

      <div className="flex flex-col gap-3">
        <section className="relative min-h-[720px] flex-1 overflow-hidden rounded-2xl border border-cyan-300/15 bg-[#050608] shadow-glow-cyan">
          {!selectedCaseId ? (
            <EmptyState icon={Sparkles} title="No case selected" description="Pick a case from the list to explore how the AI reasoned through it." />
          ) : caseGraphQuery.isLoading ? (
            <LoadingOrbs label="Loading case graph..." />
          ) : caseGraphQuery.isError ? (
            <ErrorState message={(caseGraphQuery.error as Error).message} onRetry={() => caseGraphQuery.refetch()} />
          ) : (
            <>
              <div className="absolute left-4 top-4 z-10 flex flex-wrap items-center gap-2">
                <div className="rounded-xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur-xl">
                  <p className="font-mono text-xs uppercase tracking-[.18em] text-proxy-tertiary">AI Reasoning Trail</p>
                  <p className="text-sm text-cyan-100">{nodes.length} real entities &middot; drag to orbit, scroll to zoom</p>
                </div>
                {replaySteps.length > 0 && !replayActive && (
                  <button onClick={startReplay} className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-medium text-cyan-100 backdrop-blur-xl hover:bg-cyan-300/20">
                    <PlayCircle className="size-3.5" /> Watch the AI reason ({replaySteps.length} steps)
                  </button>
                )}
              </div>
              {!replayActive && (
                <div className="absolute bottom-4 left-4 z-10 flex flex-wrap gap-2 rounded-xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur-xl">
                  {LEGEND_ITEMS.map((item) => (
                    <span key={item.kind} className="flex items-center gap-1.5 font-mono text-[10px] text-proxy-muted">
                      <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
                      {item.label}
                    </span>
                  ))}
                </div>
              )}
              {tier === "high" ? (
                <ReasoningTrailScene3D nodes={nodes} edges={edges} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} replay={replayState} />
              ) : (
                <Fallback2DGraph nodes={fallbackNodes} edges={fallbackEdges} anchorId="case" selectedId={selectedNodeId} onSelect={setSelectedNodeId} />
              )}
            </>
          )}
        </section>

        {replayActive && (
          <ReplayTransportBar
            steps={replaySteps}
            index={replayIndex}
            playing={replayPlaying}
            speed={replaySpeed}
            onPlayPause={() => setReplayPlaying(!replayPlaying)}
            onStepBack={() => { setReplayPlaying(false); setReplayIndex(Math.max(0, replayIndex - 1)); }}
            onStepForward={() => { setReplayPlaying(false); setReplayIndex(Math.min(replaySteps.length - 1, replayIndex + 1)); }}
            onScrub={(i) => { setReplayPlaying(false); setReplayIndex(i); }}
            onSpeedChange={setReplaySpeed}
            onExit={exitReplay}
          />
        )}
      </div>

      <aside className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl">
        {replayActive && currentStep ? (
          <>
            <div className="mb-3 flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-1 font-mono text-[10px] font-medium" style={{ backgroundColor: `${currentStep.color}22`, color: currentStep.color }}>
                <Zap className="size-3" /> Reasoning Replay
              </span>
            </div>
            <p className="mb-1 font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">Agent</p>
            <p className="mb-3 text-sm font-semibold" style={{ color: currentStep.color }}>{currentStep.agent}</p>
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <p className="mb-1 font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">What happened</p>
              <p className="text-sm leading-6 text-proxy-muted">{currentStep.caption}</p>
            </div>
            {replayFocusNode && (
              <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">Focused entity</p>
                <p className="text-sm text-proxy-text">{replayFocusNode.label}</p>
              </div>
            )}
          </>
        ) : activeNode ? (
          <NodeDetailPanel node={activeNode} />
        ) : (
          <p className="text-xs text-proxy-tertiary">Select a node to inspect it, or start Reasoning Replay to watch the AI think.</p>
        )}
      </aside>
    </div>
  );
}
