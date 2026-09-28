"use client";

import dynamic from "next/dynamic";
import { Search, FileSearch, Network, Target, PenLine, ShieldAlert, Loader2, Check } from "lucide-react";
import { domainTheme } from "./domain-theme";
import { useDeviceTier } from "@/components/landing/useDeviceTier";
import type { FlowStage } from "./PipelineFlow3D";

const PipelineFlow3D = dynamic(() => import("./PipelineFlow3D"), {
  ssr: false,
  loading: () => <div className="h-[300px] animate-pulse rounded-lg bg-white/[.02]" aria-hidden />,
});

export interface DetectedDomain {
  domain: string;
  confidence?: number;
}

const PIPELINE_STAGES = [
  { key: "research", label: "Research Agent", icon: Search, match: (t: string) => t.startsWith("research:") || t === "retrieval:qdrant" },
  { key: "evidence", label: "Evidence Agent", icon: FileSearch, match: (t: string) => t === "evidence:gemini" },
  { key: "knowledge_graph", label: "Knowledge Graph Agent", icon: Network, match: (t: string) => t === "graph:neo4j" },
  { key: "strategy", label: "Strategy Agent", icon: Target, match: (t: string) => t === "strategy:gemini" },
  { key: "negotiation", label: "Negotiation Agent", icon: PenLine, match: (t: string) => t.startsWith("negotiation:") },
  { key: "review", label: "Review Agent", icon: ShieldAlert, match: (t: string) => t === "review:gemini" },
] as const;

export function PipelineSidebar({
  candidates, primaryDomain, primaryRoute, trace, processing,
}: {
  candidates: DetectedDomain[];
  primaryDomain?: string;
  primaryRoute?: string;
  trace: string[];
  processing: boolean;
}) {
  const theme = primaryDomain ? domainTheme(primaryDomain) : undefined;
  const color = theme?.color ?? "#00e5ff";
  const tier = useDeviceTier();
  const stages: FlowStage[] = PIPELINE_STAGES.map((stage) => {
    const done = trace.some(stage.match);
    return { key: stage.key, label: stage.label, done, active: processing && !done && trace.length > 0 };
  });

  return (
    <div className="hidden w-64 shrink-0 flex-col gap-4 xl:flex">
      <div className="rounded-xl border border-white/10 bg-black/20 p-3">
        <p className="mb-2 text-[10px] font-medium uppercase tracking-wide text-proxy-tertiary">Detected</p>
        {candidates.length === 0 ? (
          <p className="text-xs text-proxy-tertiary">Waiting for a question...</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5">
              {candidates.map((c) => {
                const t = domainTheme(c.domain);
                return (
                  <span key={c.domain} className="rounded-full border px-2 py-0.5 text-[10px] font-medium" style={{ borderColor: `${t.color}45`, backgroundColor: `${t.color}18`, color: t.color }}>
                    {t.label}
                    {c.confidence !== undefined && <span className="ml-1 opacity-70">{Math.round(c.confidence * 100)}%</span>}
                  </span>
                );
              })}
            </div>
            {primaryRoute && (
              <p className="mt-2 text-[11px] text-proxy-muted">
                Route: <span className="font-mono text-proxy-text">{primaryRoute}</span>
              </p>
            )}
          </>
        )}
      </div>

      <div className="rounded-xl border border-white/10 bg-black/20 p-3">
        <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-proxy-tertiary">Agent Pipeline</p>
        {tier === "high" ? (
          <PipelineFlow3D stages={stages} color={color} processing={processing} />
        ) : (
          <div className="relative space-y-3 pt-2">
            <div className="absolute bottom-3 left-[11px] top-3 w-px bg-white/10" aria-hidden />
            {PIPELINE_STAGES.map((stage) => {
              const Icon = stage.icon;
              const done = trace.some(stage.match);
              const isNext = processing && !done && trace.length > 0;
              return (
                <div key={stage.key} className="relative flex items-start gap-2.5 pl-0">
                  <span
                    className="relative z-10 grid size-[22px] shrink-0 place-items-center rounded-full border-2 border-black/40"
                    style={{ backgroundColor: done ? color : "rgba(255,255,255,.06)" }}
                  >
                    {done ? <Check className="size-3 text-black" /> : isNext ? <Loader2 className="size-3 animate-spin text-proxy-tertiary" /> : <Icon className="size-3 text-proxy-tertiary" />}
                  </span>
                  <div className="min-w-0 pt-0.5">
                    <p className={`text-[11px] font-medium ${done ? "text-proxy-text" : "text-proxy-tertiary"}`}>{stage.label}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
