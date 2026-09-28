"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { AgentBreakdown } from "@/lib/api-client";
import { detailFor } from "./agentTraceDetails";

interface StepBadge {
  label: string;
  color?: string;
}

function badgesFor(trace: string, breakdown?: AgentBreakdown): StepBadge[] {
  if (!breakdown) return [];
  if (trace.startsWith("research:") || trace === "retrieval:qdrant") {
    const r = breakdown.research;
    const badges: StepBadge[] = [];
    if (r.confidence !== undefined) badges.push({ label: `${Math.round(r.confidence * 100)}% confidence` });
    if (r.regulations?.length) badges.push({ label: `${r.regulations.length} regulation${r.regulations.length === 1 ? "" : "s"} cited` });
    if (r.unverified_regulations?.length) badges.push({ label: `${r.unverified_regulations.length} unverified`, color: "#ffc857" });
    return badges;
  }
  if (trace === "evidence:gemini") {
    const e = breakdown.evidence;
    if (e.evidence_relevant === false) return [{ label: "evidence not relevant", color: "#ffc857" }];
    if (e.evidence_relevant === true) return [{ label: "evidence verified", color: "#37f29a" }];
    return [];
  }
  if (trace === "strategy:gemini") {
    const s = breakdown.strategy;
    const badges: StepBadge[] = [];
    if (s.can_appeal) badges.push({ label: `can proceed: ${s.can_appeal}` });
    if (s.success_probability !== undefined) badges.push({ label: `${Math.round(s.success_probability * 100)}% success probability` });
    return badges;
  }
  if (trace === "review:gemini") {
    const rv = breakdown.review;
    if (rv.approval_ready !== undefined) {
      return [{ label: rv.approval_ready ? "ready for approval" : "needs attention", color: rv.approval_ready ? "#37f29a" : "#ffc857" }];
    }
  }
  return [];
}

export function AgentReasoningTrace({ trace, breakdown }: { trace?: string[]; breakdown?: AgentBreakdown }) {
  const [open, setOpen] = useState(false);
  // trace/breakdown can be missing on messages cached in localStorage from
  // before this component existed -- chat history persists across reloads
  // and app updates, so old entries won't have these fields.
  if (!trace || trace.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-black/20">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wide text-proxy-tertiary hover:text-proxy-muted"
      >
        <span>Agent reasoning &middot; {trace.length} steps</span>
        {open ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
      </button>
      {open && (
        <div className="reasoning-trace space-y-0 border-t border-white/5 px-3 py-3">
          {trace.map((t, i) => {
            const detail = detailFor(t);
            const badges = badgesFor(t, breakdown);
            return (
              <div key={`${t}-${i}`} className="trace-step relative pb-4 pl-6 last:pb-0">
                <span
                  className="absolute left-0 top-0.5 grid size-4 place-items-center rounded-full text-[9px] font-bold text-black"
                  style={{ backgroundColor: detail.color }}
                >
                  {i + 1}
                </span>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded-full border px-1.5 py-0.5 text-[10px] font-medium" style={{ borderColor: `${detail.color}45`, backgroundColor: `${detail.color}18`, color: detail.color }}>
                    {detail.agent}
                  </span>
                  {badges.map((b) => (
                    <span key={b.label} className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px] text-proxy-muted" style={b.color ? { color: b.color, borderColor: `${b.color}40` } : undefined}>
                      {b.label}
                    </span>
                  ))}
                </div>
                {detail.why && <p className="mt-1 text-[11px] italic leading-4 text-proxy-tertiary">{detail.why}</p>}
                {detail.invoked.length > 0 && (
                  <p className="mt-1 font-mono text-[10px] text-proxy-tertiary">
                    Invoked: {detail.invoked.join(", ")}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
      <style jsx>{`
        .trace-step:not(:last-child)::before {
          content: "";
          position: absolute;
          left: 7px;
          top: 18px;
          bottom: 0;
          width: 1px;
          background: rgba(255, 255, 255, 0.08);
        }
      `}</style>
    </div>
  );
}
