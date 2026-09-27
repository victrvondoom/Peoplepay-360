"use client";

import Link from "next/link";
import { useEffect, useState, useMemo } from "react";
import { motion } from "framer-motion";
import { Activity, AlertTriangle, Bot, Check, ChevronRight, CircleDot, ClipboardList, Download, FileText, Heart, Loader2, MessageSquare, Network, Pin, RefreshCw, Search, Sparkles, Star, Upload, Wifi, WifiOff } from "lucide-react";
import { agentStages, appealSteps, type StageStatus } from "@/lib/design-tokens";
import { analyses as mockAnalyses, getDomainConfig, domainRegistry, type Analysis } from "@/lib/proxy-analysis-data";
import { askAI, getReportSummary, listAnalyses, type ReportSummary, type AnalysisCase, type ChatCitation } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { connectAnalysisRealtime, type RealtimeMode } from "@/lib/realtime";

export function LivePipeline({ analysis, large = false }: { analysis: Analysis; large?: boolean }) {
  const [mode, setMode] = useState<RealtimeMode>("offline");
  const [current, setCurrent] = useState(analysis);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const stop = connectAnalysisRealtime(analysis.id, { onMode: setMode, onUpdate: setCurrent, onError: () => setMode("offline") });
    const timer = setInterval(() => setTick((value) => value + 1), 900);
    return () => { stop(); clearInterval(timer); };
  }, [analysis.id]);
  return <section className="rounded-xl border border-white/10 bg-black/20 p-4"><div className="mb-4 flex items-center justify-between"><div><p className="text-xs uppercase tracking-[.18em] text-proxy-tertiary">Live AI Agent Pipeline</p><h2 className="font-semibold">{current.id}</h2></div><RealtimeBadge mode={mode} /></div><div className={`${large ? "grid-cols-1 sm:grid-cols-3 xl:grid-cols-6" : "grid-cols-1 sm:grid-cols-2"} grid gap-3`}>{agentStages.map((stage, index) => <AgentNode key={stage.id} label={stage.label} status={current.stages[stage.id]} stream={stage.stream[tick % stage.stream.length]} index={index} />)}</div></section>;
}

function RealtimeBadge({ mode }: { mode: RealtimeMode }) { const Icon = mode === "offline" ? WifiOff : Wifi; return <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-proxy-muted"><Icon className="size-3.5 text-cyan-200" />{mode}</span>; }
function AgentNode({ label, status, stream, index }: { label: string; status: StageStatus; stream: string; index: number }) { const icon = status === "done" ? <Check className="size-4" /> : status === "running" ? <Loader2 className="size-4 animate-spin" /> : status === "error" ? <AlertTriangle className="size-4" /> : <CircleDot className="size-4" />; const tone = status === "done" ? "border-green-300/25 bg-green-300/10 text-green-100 shadow-glow-green" : status === "running" ? "border-cyan-300/35 bg-cyan-300/10 text-cyan-100 shadow-glow-cyan" : status === "error" ? "border-red-300/35 bg-red-300/10 text-red-100" : "border-white/10 bg-white/[.025] text-proxy-tertiary"; return <div className={`motion-card relative rounded-lg border p-3 ${tone}`} style={{ animationDelay: `${index * 80}ms` }}><div className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-md bg-black/25">{icon}</span><div><p className="text-sm font-medium">{label}</p><p className="text-xs capitalize opacity-75">{status === "running" ? "Running..." : status}</p></div></div><p className="mt-3 min-h-5 text-xs text-proxy-muted">{status === "running" ? stream : status === "done" ? "Complete" : "Waiting"}</p>{status === "running" && <div className="absolute inset-x-3 bottom-2 h-px overflow-hidden bg-white/10"><span className="block h-full w-1/2 animate-flow bg-cyan-200" /></div>}</div>; }

export function KpiGrid({ analysis }: { analysis: Analysis }) {
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [realAnalyses, setRealAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getReportSummary().catch(() => null), listAnalyses().catch(() => [])]).then(
      ([s, a]) => { setSummary(s); setRealAnalyses(a); setLoading(false); }
    );
  }, []);

  const avgConf = realAnalyses.length
    ? realAnalyses.filter(a => a.avg_confidence !== null).reduce((sum, a) => sum + (a.avg_confidence ?? 0), 0) /
      Math.max(1, realAnalyses.filter(a => a.avg_confidence !== null).length)
    : null;
  const totalRuns = realAnalyses.reduce((sum, a) => sum + a.run_count, 0);

  const kpis = [
    ["Total Cases", loading ? "..." : String(summary?.totals.cases ?? 0), "all domains combined"],
    ["Appeals Generated", loading ? "..." : String(summary?.totals.appeals ?? 0), "complaint letters drafted"],
    ["Documents Uploaded", loading ? "..." : String(summary?.totals.documents ?? 0), "indexed in vault"],
    ["Resolution Rate", loading ? "..." : summary?.resolution_rate != null ? `${Math.round(summary.resolution_rate * 100)}%` : "N/A", "resolved appeals"],
    ["Agent Runs", loading ? "..." : String(totalRuns), "total AI pipeline executions"],
    ["Avg Confidence", loading ? "..." : avgConf != null ? `${Math.round(avgConf * 100)}%` : "N/A", "across all analyses"],
    ["Active AI Agents", "6", "per domain pipeline"],
    ["Domain Coverage", `${domainRegistry.length}/8`, "all UI domains enabled"],
  ];

  return (
    <section className="mt-5 grid auto-cols-[minmax(220px,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2 md:grid-flow-row md:grid-cols-2 xl:grid-cols-4">
      {kpis.map(([label, value, sub]) => (
        <div key={label} className="motion-card min-w-[220px] rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm text-proxy-muted">{label}</span>
            <Activity className="size-4 text-cyan-200" />
          </div>
          <p className="text-2xl font-semibold">{value}</p>
          <p className="mt-1 text-xs text-proxy-tertiary">{sub}</p>
        </div>
      ))}
    </section>
  );
}


export function AnalysesList() {
  const [items, setItems] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listAnalyses()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  function timeAgo(iso: string) {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  return (
    <section className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-semibold">My Analyses</h2>
        <span className="text-xs text-proxy-tertiary">{items.length} total</span>
      </div>
      {loading ? (
        <div className="flex h-24 items-center justify-center"><Loader2 className="size-5 animate-spin text-proxy-tertiary" /></div>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-xs text-proxy-tertiary">No analyses yet — run your first multi-domain analysis above.</p>
      ) : (
        items.map((item) => {
          const theme = domainTheme(item.domains_involved[0] ?? item.domain);
          return (
            <a key={item.id} href={`/dashboard/analyses?case=${encodeURIComponent(item.id)}`}
              className="motion-card mb-3 block rounded-lg border border-white/10 bg-black/20 p-3 hover:border-cyan-300/35"
              style={{ borderLeftColor: theme.color, borderLeftWidth: 3 }}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-proxy-text">{item.title}</p>
                  <p className="mt-0.5 text-xs text-proxy-muted">{item.institution_name} &middot; {item.domain}</p>
                </div>
                <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-proxy-tertiary">{item.status}</span>
              </div>
              <div className="mt-2.5 h-1.5 rounded-full bg-white/8">
                <div className="h-full rounded-full bg-cyan-300 shadow-glow-cyan" style={{ width: `${item.avg_confidence != null ? Math.round(item.avg_confidence * 100) : 0}%` }} />
              </div>
              <div className="mt-1.5 flex justify-between text-[10px] text-proxy-tertiary">
                <span>Confidence {item.avg_confidence != null ? `${Math.round(item.avg_confidence * 100)}%` : "—"}</span>
                <span>{timeAgo(item.updated_at)}</span>
              </div>
            </a>
          );
        })
      )}
    </section>
  );
}

export function GaugeCard({ label, value, max = 100 }: { label: string; value: number; max?: number }) { const pct = Math.min(100, Math.round((value / max) * 100)); const color = pct > 75 ? "#37f29a" : pct > 45 ? "#ffc857" : "#ff4d6d"; return <div className="rounded-lg border border-white/10 bg-black/20 p-3"><svg viewBox="0 0 80 80" className="mx-auto size-20" role="img" aria-label={`${label} ${value}`}><circle cx="40" cy="40" r="31" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="7" /><circle cx="40" cy="40" r="31" fill="none" stroke={color} strokeWidth="7" strokeDasharray={`${pct * 1.95} 195`} strokeLinecap="round" transform="rotate(-90 40 40)" /></svg><p className="-mt-12 text-center text-lg font-semibold">{value}{max === 100 ? "%" : ""}</p><p className="mt-8 text-center text-xs text-proxy-muted">{label}</p></div>; }

export function ErrorRecovery() { return <div className="rounded-lg border border-amber-300/20 bg-amber-300/8 p-3 text-sm leading-6 text-proxy-muted"><div className="mb-2 flex items-center gap-2 text-amber-100"><AlertTriangle className="size-4" /> Fallback mode ready</div>Gemini unavailable, reconnecting, or offline? Use Retry, Reconnect, or continue with local preview while the backend recovers.<div className="mt-3 flex flex-wrap gap-2"><button className="rounded-md border border-white/10 px-3 py-1.5 text-xs"><RefreshCw className="mr-1 inline size-3" />Retry</button><button className="rounded-md border border-white/10 px-3 py-1.5 text-xs">Reconnect</button><button className="rounded-md border border-white/10 px-3 py-1.5 text-xs">Offline mode</button></div></div>; }

export function LoadingSkeleton({ label }: { label: string }) { return <div className="rounded-lg border border-white/10 bg-white/[.035] p-4" role="status" aria-live="polite"><div className="mb-3 h-3 w-32 rounded bg-white/10" /><div className="space-y-2"><div className="h-3 rounded bg-white/10" /><div className="h-3 w-4/5 rounded bg-white/10" /><div className="h-3 w-2/3 rounded bg-white/10" /></div><span className="sr-only">Loading {label}</span></div>; }

export function DocumentHighlights({ analysis }: { analysis: Analysis }) { const config = getDomainConfig(analysis.domain); return <section className="grid gap-4 xl:grid-cols-[1fr_360px]"><div className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl"><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{config.documentTitle}</h2><span className="text-xs text-proxy-tertiary">Pinch zoom / swipe tabs on mobile</span></div><div className="min-h-[560px] rounded-lg border border-white/10 bg-[#080a0f] p-4"><div className="mx-auto h-[500px] max-w-md rounded-lg bg-[#10131a] p-6 text-sm leading-7 text-proxy-muted"><p className="text-xs uppercase tracking-[.18em] text-proxy-tertiary">{analysis.documents[0]?.name ?? "Document"} / Page 1</p><p className="mt-8">{config.documentPreview[0]}</p><p className="mt-4 rounded bg-amber-300/20 px-2 text-amber-100 underline decoration-amber-300">{config.documentPreview[1]}</p><p className="mt-4 rounded bg-cyan-300/15 px-2 text-cyan-100 underline decoration-cyan-300">{config.documentPreview[2]}</p></div></div></div><div className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl"><h3 className="mb-3 font-semibold">Highlight layer</h3>{analysis.highlights.map((item) => <button key={`${item.doc}-${item.label}`} className="mb-2 w-full rounded-lg border border-white/10 bg-black/20 p-3 text-left text-sm hover:border-cyan-300/35"><span className="text-cyan-100">{item.doc} p.{item.page} / {item.label}</span><p className="mt-1 text-xs leading-5 text-proxy-muted">{item.text}</p></button>)}</div></section>; }

export function KnowledgeGraphView({ analysis }: { analysis: Analysis }) {
  const config = getDomainConfig(analysis.domain);
  const nodes = config.graphNodes;
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [positions, setPositions] = useState<Array<{ name: string; x: number; y: number; index: number }>>([]);
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [tilt, setTilt] = useState({ rx: 20, ry: -6 });

  // Generate unique seed for random offsets
  const seed = useMemo(() => Math.floor(Math.random() * 100), []);

  const defaultPositions = useMemo(() => [
    { x: 500, y: 60 },   // Claim (Level 0 - Top)
    { x: 300, y: 160 },  // Policy (Level 1 - Left)
    { x: 700, y: 160 },  // Coverage (Level 1 - Right)
    { x: 300, y: 260 },  // Hospital (Level 2 - Left)
    { x: 700, y: 260 },  // Treatment (Level 2 - Right)
    { x: 500, y: 350 },  // IRDAI Regulation (Level 3 - Bottom)
  ], []);

  useEffect(() => {
    setPositions(
      nodes.map((node, index) => ({
        name: node,
        ...(defaultPositions[index] || { x: 100 + index * 120, y: 200 }),
        index,
      }))
    );
  }, [nodes, defaultPositions]);

  const getNodeStatus = (index: number) => {
    const stages = analysis.stages;
    if (!stages) return "done";
    if (index === 0 || index === 1) return stages.research || "done";
    if (index === 2) return stages.graph || "done";
    if (index === 3 || index === 4) return stages.evidence || "done";
    if (index === 5) return stages.strategy || stages.review || "done";
    return "done";
  };

  const handleMouseDown = (index: number, event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const node = positions[index];
    if (!node) return;
    if (getNodeStatus(index) === "waiting") return;
    
    const container = event.currentTarget.closest(".graph-container");
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const scaleX = 1000 / rect.width;
    const scaleY = 400 / rect.height;
    
    const mouseX = (event.clientX - rect.left) * scaleX;
    const mouseY = (event.clientY - rect.top) * scaleY;
    
    setDraggingIndex(index);
    setDragOffset({ x: mouseX - node.x, y: mouseY - node.y });
  };

  const handleMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (draggingIndex === null) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const scaleX = 1000 / rect.width;
    const scaleY = 400 / rect.height;
    
    const mouseX = (event.clientX - rect.left) * scaleX;
    const mouseY = (event.clientY - rect.top) * scaleY;
    
    setPositions((prev) =>
      prev.map((pos, idx) =>
        idx === draggingIndex
          ? {
              ...pos,
              x: Math.max(90, Math.min(910, mouseX - dragOffset.x)),
              y: Math.max(40, Math.min(360, mouseY - dragOffset.y)),
            }
          : pos
      )
    );
  };

  const handleMouseUp = () => setDraggingIndex(null);

  const handleContainerMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (draggingIndex !== null) {
      handleMouseMove(event);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    const px = (x / rect.width) - 0.5;
    const py = (y / rect.height) - 0.5;
    
    setTilt({
      rx: 20 - py * 12,
      ry: -6 + px * 14
    });
  };

  const handleContainerMouseLeave = () => {
    setDraggingIndex(null);
    setTilt({ rx: 20, ry: -6 });
  };

  const resetLayout = () => {
    setPositions(
      nodes.map((node, index) => ({
        name: node,
        ...(defaultPositions[index] || { x: 100 + index * 120, y: 200 }),
        index,
      }))
    );
  };

  const connections = [
    { from: 0, to: 1, label: "governed by" },
    { from: 0, to: 2, label: "asserts" },
    { from: 1, to: 3, label: "references" },
    { from: 2, to: 4, label: "qualifies" },
    { from: 3, to: 5, label: "subject to" },
    { from: 4, to: 5, label: "conforms to" },
    { from: 0, to: 5, label: "regulated by" },
  ].filter(c => c.from < nodes.length && c.to < nodes.length);

  const getInfo = (nodeName: string) => {
    if (nodeName.toLowerCase().includes("claim") || nodeName.toLowerCase().includes("dispute") || nodeName.toLowerCase().includes("issue")) {
      return { title: nodeName, role: "Central Subject", desc: `The core ${config.entityLabel.toLowerCase()} under active appeal and legal justification analysis.`, action: "Inspect Dispute Details" };
    }
    if (nodeName.toLowerCase().includes("policy") || nodeName.toLowerCase().includes("agreement") || nodeName.toLowerCase().includes("subscriber") || nodeName.toLowerCase().includes("account")) {
      return { title: nodeName, role: "Governing Terms", desc: "The primary contractual agreement outlining boundaries and liability limits.", action: "View Policy Clauses" };
    }
    if (nodeName.toLowerCase().includes("coverage") || nodeName.toLowerCase().includes("transaction") || nodeName.toLowerCase().includes("plan")) {
      return { title: nodeName, role: "Entitlements", desc: `Specific service levels, plan benefits, or transaction records under dispute.`, action: "Verify Plan Coverage" };
    }
    if (nodeName.toLowerCase().includes("hospital") || nodeName.toLowerCase().includes("merchant") || nodeName.toLowerCase().includes("service ticket")) {
      return { title: nodeName, role: "Service Provider", desc: `The third-party entity where the transaction, treatment, or issue occurred.`, action: "Audit Provider Invoices" };
    }
    if (nodeName.toLowerCase().includes("treatment") || nodeName.toLowerCase().includes("bill") || nodeName.toLowerCase().includes("flight event") || nodeName.toLowerCase().includes("repair duty")) {
      return { title: nodeName, role: "Occurrence Factuals", desc: "The actual event occurrence details, dates, and itemized charges recorded.", action: "Analyze Factual Evidence" };
    }
    if (nodeName.toLowerCase().includes("regulation") || nodeName.toLowerCase().includes("rule") || nodeName.toLowerCase().includes("guideline")) {
      return { title: nodeName, role: "Statutory Law", desc: `Legally binding consumer protections and regulator guidelines governing ${config.counterpartyLabel}.`, action: "View Regulatory Citations" };
    }
    return { title: nodeName, role: "Knowledge Node", desc: "An extracted conceptual entity verified by PROXY agent intelligence.", action: "Review conceptual link" };
  };

  const activeNodeName = hoveredNode || selectedNode || nodes[0] || "Knowledge Graph";
  const activeInfo = getInfo(activeNodeName);

  return (
    <section className="rounded-xl border border-white/10 bg-glass p-5 backdrop-blur-xl">
      <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-block size-2 animate-pulse rounded-full bg-cyan-300 shadow-glow-cyan" />
            <h2 className="font-semibold text-lg">PROXY Holographic 3D Pipeline</h2>
          </div>
          <p className="text-xs text-proxy-muted mt-0.5">Perspective-tilted real-time relational map with dynamic cursor parallax.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={resetLayout} className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-proxy-muted hover:bg-white/10 hover:text-white transition">Reset Grid</button>
          <span className="rounded-md border border-white/10 bg-black/40 px-2.5 py-1 text-[11px] font-medium text-proxy-muted">Core: {config.label}</span>
          <span className="rounded-md border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 text-[11px] font-medium text-cyan-200">3D Engine</span>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        {/* Graph Container Box */}
        <div 
          className="graph-container relative w-full aspect-[1000/400] overflow-hidden rounded-xl border border-cyan-300/10 bg-[#020305]/98 p-4 shadow-[inset_0_0_80px_rgba(0,0,0,0.85)] cursor-default select-none"
          onMouseMove={handleContainerMouseMove}
          onMouseLeave={handleContainerMouseLeave}
          onMouseUp={handleMouseUp}
          style={{ perspective: "1000px" }}
        >
          {/* 3D Tilted Plane wrapper */}
          <div 
            className="relative w-full h-full"
            style={{
              transform: `rotateX(${tilt.rx}deg) rotateY(${tilt.ry}deg)`,
              transformStyle: "preserve-3d",
              transition: draggingIndex !== null ? "none" : "transform 0.15s cubic-bezier(0.25, 0.46, 0.45, 0.94)"
            }}
          >
            {/* SVG Layer for Connections and background grid */}
            <svg 
              className="absolute inset-0 w-full h-full pointer-events-none" 
              viewBox="0 0 1000 400"
              style={{ transform: "translateZ(0)" }}
            >
              <defs>
                {/* Square Grid representing the 3D floor */}
                <pattern id="perspectiveGrid" width="30" height="30" patternUnits="userSpaceOnUse">
                  <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(0, 229, 255, 0.04)" strokeWidth="0.5" />
                </pattern>
                
                <radialGradient id="radarSweep" cx="50%" cy="50%" r="50%" fx="50%" fy="50%">
                  <stop offset="0%" stopColor="rgba(0,229,255,0.06)" />
                  <stop offset="80%" stopColor="rgba(155,92,255,0.015)" />
                  <stop offset="100%" stopColor="rgba(0,0,0,0)" />
                </radialGradient>
                
                <linearGradient id="edgeFlow" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#00e5ff" stopOpacity="0.8" />
                  <stop offset="50%" stopColor="#9b5cff" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="#00e5ff" stopOpacity="0.8" />
                </linearGradient>

                <filter id="neonGlow">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>

                <filter id="cardGlow">
                  <feGaussianBlur stdDeviation="4" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
                
                {/* Arrow Markers for direction */}
                <marker id="cyanArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#00e5ff" opacity="0.8" />
                </marker>
                <marker id="purpleArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#9b5cff" opacity="0.8" />
                </marker>
                <marker id="grayArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                  <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="rgba(255, 255, 255, 0.15)" />
                </marker>
              </defs>
              
              <rect width="1000" height="400" fill="url(#perspectiveGrid)" rx="12" />
              <circle cx="500" cy="200" r="450" fill="url(#radarSweep)" className="animate-[spin_25s_linear_infinite]" />

              {/* Ambient data dust particles floating slowly */}
              {[...Array(16)].map((_, i) => {
                const x = 50 + (i * 62) % 900;
                const y = 30 + (i * 24) % 340;
                const size = 1 + (i % 3) * 0.5;
                return (
                  <circle key={i} cx={x} cy={y} r={size} fill={i % 2 === 0 ? "#00e5ff" : "#9b5cff"} opacity="0.25">
                    <animate attributeName="cy" from={y + 15} to={y - 15} dur={`${6 + (i % 3) * 2}s`} repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.1;0.4;0.1" dur={`${4 + (i % 2) * 2}s`} repeatCount="indefinite" />
                  </circle>
                );
              })}

              {/* Holographic Projection Shadows & Rings on floor grid */}
              <g>
                {positions.map((node, index) => {
                  const status = getNodeStatus(index);
                  if (status === "waiting") return null;
                  const themeColor = node.index % 2 === 0 ? "#00e5ff" : "#9b5cff";
                  const isHovered = hoveredNode === node.name;
                  const isSelected = selectedNode === node.name;
                  
                  return (
                    <g key={`anchor-${node.name}`}>
                      {/* Floor shadow footprint ellipse */}
                      <ellipse 
                        cx={node.x} 
                        cy={node.y} 
                        rx={isHovered || isSelected ? "45" : "35"} 
                        ry={isHovered || isSelected ? "14" : "10"} 
                        fill="none" 
                        stroke={themeColor} 
                        strokeWidth="0.75" 
                        strokeDasharray="3 3" 
                        opacity={isHovered || isSelected ? 0.7 : 0.25}
                        style={{ transition: "all 0.3s" }}
                      />
                      {/* Floor pulse ring */}
                      {(isHovered || isSelected || status === "running") && (
                        <ellipse cx={node.x} cy={node.y} rx="35" ry="10" fill="none" stroke={themeColor} strokeWidth="1" opacity="0.8">
                          <animate attributeName="rx" from="35" to="70" dur="2.5s" repeatCount="indefinite" />
                          <animate attributeName="ry" from="10" to="20" dur="2.5s" repeatCount="indefinite" />
                          <animate attributeName="opacity" from="0.8" to="0" dur="2.5s" repeatCount="indefinite" />
                        </ellipse>
                      )}
                      {/* Vertical light pillar projection line */}
                      <line 
                        x1={node.x} 
                        y1={node.y} 
                        x2={node.x} 
                        y2={node.y - 12} 
                        stroke={themeColor} 
                        strokeWidth="1" 
                        strokeDasharray="4 4" 
                        opacity={isHovered || isSelected ? 0.8 : 0.3} 
                      />
                    </g>
                  );
                })}
              </g>

              {/* Connections Layer */}
              <g>
                {connections.map((edge) => {
                  const fromNode = positions[edge.from];
                  const toNode = positions[edge.to];
                  if (!fromNode || !toNode) return null;
                  
                  const fromStatus = getNodeStatus(edge.from);
                  const toStatus = getNodeStatus(edge.to);
                  if (fromStatus === "waiting" || toStatus === "waiting") return null;
                  
                  const active = (hoveredNode === fromNode.name || hoveredNode === toNode.name) || (selectedNode === fromNode.name || selectedNode === toNode.name);
                  const isGenerating = fromStatus === "running" || toStatus === "running";

                  // Calculate connecting points at card borders (top-to-bottom)
                  let pathD;
                  if (edge.from === 0 && edge.to === 5) {
                    // Curve wide left to bypass middle row
                    pathD = `M ${fromNode.x - 90} ${fromNode.y} C ${fromNode.x - 300} ${fromNode.y + 60}, ${toNode.x - 300} ${toNode.y - 60}, ${toNode.x - 90} ${toNode.y}`;
                  } else {
                    const fromX = fromNode.x;
                    const fromY = fromNode.y + 38;
                    const toX = toNode.x;
                    const toY = toNode.y - 38;
                    const dy = Math.abs(toY - fromY) * 0.45;
                    pathD = `M ${fromX} ${fromY} C ${fromX} ${fromY + dy}, ${toX} ${toY - dy}, ${toX} ${toY}`;
                  }

                  return (
                    <motion.g key={`${edge.from}-${edge.to}`} initial={{ opacity: 0 }} animate={{ opacity: hoveredNode && !active ? 0.2 : 1 }} transition={{ duration: 0.3 }}>
                      <path
                        d={pathD}
                        fill="none"
                        stroke={active ? "url(#edgeFlow)" : isGenerating ? "#00e5ff" : "rgba(255,255,255,0.06)"}
                        strokeWidth={active ? 2.5 : 1.5}
                        strokeDasharray={isGenerating ? "6,8" : active ? "none" : "3,6"}
                        className={isGenerating ? "animate-dash" : ""}
                        filter={active ? "url(#neonGlow)" : ""}
                        markerEnd={active ? "url(#purpleArrow)" : isGenerating ? "url(#cyanArrow)" : "url(#grayArrow)"}
                        style={{ transition: 'stroke 0.3s, stroke-width 0.3s' }}
                      />
                      
                      {/* Multi-staggered Flowing Telemetry Particles */}
                      {active && !isGenerating && (
                        <>
                          <circle r="3.5" fill="#fff" filter="url(#neonGlow)">
                            <animateMotion dur="2.4s" repeatCount="indefinite" path={pathD} />
                          </circle>
                          <circle r="2" fill="#00e5ff" filter="url(#neonGlow)">
                            <animateMotion dur="2.4s" begin="0.8s" repeatCount="indefinite" path={pathD} />
                          </circle>
                          <circle r="1.5" fill="#9b5cff" filter="url(#neonGlow)">
                            <animateMotion dur="2.4s" begin="1.6s" repeatCount="indefinite" path={pathD} />
                          </circle>
                        </>
                      )}

                      {/* Interactive Telemetry HUD Label */}
                      {active && (
                        <g transform={`translate(${(fromNode.x + toNode.x)/2}, ${(fromNode.y + toNode.y)/2 - 10})`} style={{ transformStyle: "preserve-3d" }}>
                          <rect x="-55" y="-9" width="110" height="15" rx="3" fill="rgba(2,3,5,0.92)" stroke="rgba(0,229,255,0.3)" strokeWidth="1" />
                          <text textAnchor="middle" fill="#00e5ff" fontSize="7" fontFamily="monospace" y="1" letterSpacing="0.05em">
                            {isGenerating ? "SYNCING // 420KB/s" : `FLOW ACTIVE // ${(seed + edge.from * 15) % 100}%`}
                          </text>
                        </g>
                      )}
                    </motion.g>
                  );
                })}
              </g>
            </svg>

            {/* HTML Layer for 3D perspective Cards */}
            <div 
              className="absolute inset-0 w-full h-full pointer-events-none"
              style={{ transform: "translateZ(25px)", transformStyle: "preserve-3d" }} // Pop cards out in 3D depth
            >
              {positions.map((node, index) => {
                const status = getNodeStatus(index);
                const isHovered = hoveredNode === node.name;
                const isSelected = selectedNode === node.name;
                const isDimmed = hoveredNode ? !isHovered && !connections.some(c => (c.from === node.index && positions[c.to].name === hoveredNode) || (c.to === node.index && positions[c.from].name === hoveredNode)) : false;

                const themeColor = node.index % 2 === 0 ? "#00e5ff" : "#9b5cff";
                const isGrabbing = draggingIndex === index;

                return (
                  <div
                    key={node.name}
                    className={`absolute p-0.5 select-none pointer-events-auto transition-all duration-300`}
                    style={{
                      left: `${(node.x / 1000) * 100}%`,
                      top: `${(node.y / 400) * 100}%`,
                      transform: `translate(-50%, -50%) translateZ(${isHovered || isSelected ? '28px' : '0px'})`,
                      width: "180px",
                      height: "76px",
                      cursor: status === "waiting" ? "not-allowed" : isGrabbing ? "grabbing" : "grab",
                      transition: isGrabbing ? "none" : "left 0.15s cubic-bezier(0.25, 0.46, 0.45, 0.94), top 0.15s cubic-bezier(0.25, 0.46, 0.45, 0.94), transform 0.2s, box-shadow 0.2s",
                      opacity: isDimmed ? 0.25 : status === "waiting" ? 0.35 : 1
                    }}
                    onMouseDown={(e) => handleMouseDown(index, e)}
                    onMouseEnter={() => setHoveredNode(node.name)}
                    onMouseLeave={() => setHoveredNode(null)}
                    onClick={() => setSelectedNode(node.name === selectedNode ? null : node.name)}
                  >
                    {/* Double-Clipped Sci-fi SVG Border Panel (renders polygon behind content) */}
                    <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 180 76" preserveAspectRatio="none">
                      <polygon 
                        points="10,0 180,0 180,66 170,76 0,76 0,10" 
                        fill="rgba(4, 6, 12, 0.96)" 
                        stroke={status === "waiting" ? "rgba(255,255,255,0.06)" : status === "running" ? "#00e5ff" : isSelected ? "#ffffff" : themeColor} 
                        strokeWidth={isHovered || isSelected ? "2" : "1.25"}
                        filter={isHovered || isSelected || status === "running" ? "url(#cardGlow)" : "none"}
                        style={{ transition: "stroke 0.3s, stroke-width 0.3s" }}
                      />
                    </svg>

                    {/* Content container aligned with clipped coordinates */}
                    <div className="relative w-full h-full px-3.5 py-3 flex flex-col justify-between text-left">
                      {/* Top Accent corner overlay */}
                      {status !== "waiting" && (
                        <div 
                          className="absolute top-0 left-2 w-3 h-0.5" 
                          style={{ backgroundColor: status === "running" ? "#00e5ff" : themeColor }}
                        />
                      )}

                      {/* Card Header */}
                      <div className="flex items-center justify-between gap-1.5">
                        <div className="flex items-center gap-1.5 truncate">
                          <span className="w-1.5 h-1.5 rounded-sm" style={{ backgroundColor: status === "waiting" ? "#444" : status === "running" ? "#00e5ff" : themeColor }} />
                          <span className="font-mono text-[10px] font-bold tracking-wide uppercase truncate text-white">{node.name}</span>
                        </div>
                        <span className="font-mono text-[7px] text-proxy-tertiary">LVL.0{node.index}</span>
                      </div>

                      {/* Card Middle Status */}
                      <div className="my-1 flex items-center justify-between">
                        <span className="text-[8px] font-mono text-proxy-muted tracking-wider">
                          {status === "waiting" ? "SYS_LOCKED" : status === "running" ? "COMPUTING_FLOW..." : "SYS_VERIFIED"}
                        </span>
                        
                        {status === "running" ? (
                          <span className="relative flex h-1.5 w-1.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-300"></span>
                          </span>
                        ) : status === "done" ? (
                          <span className="inline-flex size-1 rounded-full bg-emerald-400" />
                        ) : (
                          <span className="inline-flex size-1 rounded-full bg-neutral-600" />
                        )}
                      </div>

                      {/* Card Bottom Row */}
                      <div className="flex items-center justify-between border-t border-white/5 pt-1.5 text-[8px] font-mono">
                        <span className="text-proxy-tertiary uppercase">TELEMETRY</span>
                        <span className="font-bold text-white" style={{ color: status === "waiting" ? "#666" : "#00e5ff" }}>
                          {status === "waiting" ? "OFFLINE" : `${92 + (node.index * 1.5) - (node.index % 2)}% ACC`}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Sidebar Info Panel */}
        <div className="flex flex-col justify-between rounded-xl border border-white/10 bg-[#020305]/60 p-5 shadow-2xl backdrop-blur-2xl">
          <div>
            <div className="mb-4 flex items-center justify-between border-b border-white/10 pb-4">
              <span className="text-[10px] uppercase tracking-[.25em] text-proxy-tertiary">Entity Metadata</span>
              <span className="inline-flex items-center gap-1.5 rounded-sm bg-cyan-500/10 px-2 py-1 text-[10px] font-mono text-cyan-300 uppercase shadow-[0_0_10px_rgba(0,229,255,0.2)]">
                {activeInfo.role}
              </span>
            </div>
            
            <h3 className="text-xl font-light text-white tracking-wide">{activeInfo.title}</h3>
            <p className="mt-3 text-xs leading-relaxed text-proxy-muted/80">
              {activeInfo.desc}
            </p>
            
            <div className="mt-5 rounded-lg border border-white/5 bg-black/50 p-4">
              <p className="text-[9px] uppercase tracking-[.18em] text-proxy-tertiary">Verified Authority</p>
              <p className="mt-1.5 text-xs font-mono text-cyan-100/90 leading-relaxed">
                {config.sourcesLabel}
              </p>
            </div>
          </div>
          
          <div className="mt-6">
            <button className="w-full rounded-lg bg-cyan-400 py-3 text-[11px] uppercase tracking-wider font-bold text-black transition-all hover:bg-cyan-300 hover:shadow-[0_0_20px_rgba(0,229,255,0.4)]">
              {activeInfo.action}
            </button>
          </div>
        </div>
      </div>
      
      <div className="mt-3 grid gap-2 md:hidden">
        {nodes.map((node) => (
          <div key={node} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm font-mono text-cyan-50">
            {node}
          </div>
        ))}
      </div>
    </section>
  );
}

// ─── Real-data components (accept caseId: string) ────────────────────────────

export function AppealWorkflow({ caseId }: { caseId: string }) {
  const [draft, setDraft] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    import("@/lib/api-client").then(({ getCaseReport }) => {
      getCaseReport(caseId)
        .then(r => setDraft(r.latest_analysis?.appeal_draft ?? ""))
        .catch(() => setDraft(""))
        .finally(() => setLoading(false));
    });
  }, [caseId]);

  async function copy() {
    if (!draft) return;
    await navigator.clipboard.writeText(draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl">
      <h2 className="mb-3 font-semibold">Appeal Draft</h2>
      {loading ? (
        <LoadingSkeleton label="appeal draft" />
      ) : draft ? (
        <>
          <textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            className="min-h-80 w-full rounded-lg border border-white/10 bg-black/25 p-4 text-sm leading-7 text-proxy-muted outline-none focus:border-cyan-300/60"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <button onClick={copy} className="rounded-lg border border-white/10 px-3 py-2 text-sm">{copied ? "Copied!" : "Copy"}</button>
          </div>
        </>
      ) : (
        <p className="py-6 text-center text-xs text-proxy-tertiary">No appeal draft yet. Run the analysis to generate one.</p>
      )}
    </section>
  );
}

export function ChatPanel({ caseId }: { caseId: string }) {
  const [message, setMessage] = useState("What is the strongest argument in this case?");
  const [answer, setAnswer] = useState("Ask the AI a question about this case. Answers are grounded in your uploaded evidence and case context.");
  const [citations, setCitations] = useState<ChatCitation[]>([]);
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!message.trim()) return;
    setLoading(true);
    try {
      const response = await askAI(caseId, message);
      setAnswer(response.answer);
      setCitations(response.structured_citations ?? []);
    } catch {
      setAnswer("Unable to reach the AI backend. Please ensure the FastAPI server is running.");
      setCitations([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl">
      <h2 className="mb-3 flex items-center gap-2 font-semibold"><Bot className="size-5 text-cyan-200" />AI Assistant</h2>
      {loading ? <LoadingSkeleton label="chat" /> : <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-7 text-proxy-muted">{answer}</div>}
      {!loading && citations.length > 0 && (
        <div className="mt-3 space-y-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-proxy-tertiary">Sources this answer is grounded in</p>
          {citations.map((c, i) => (
            <div key={i} className="rounded-lg border border-white/10 bg-black/15 p-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-proxy-text">{c.title}</span>
                <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-proxy-tertiary">{c.authority}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-proxy-muted">{c.retrieved_chunk}</p>
              {c.url && (
                <a href={c.url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-[11px] text-cyan-300 hover:underline">
                  View source
                </a>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={e => e.key === "Enter" && submit()}
          className="min-h-11 flex-1 rounded-lg border border-white/10 bg-black/25 px-3 text-sm outline-none focus:border-cyan-300/60"
        />
        <button onClick={submit} disabled={loading} className="rounded-lg bg-cyan-300 px-4 py-2 text-sm font-semibold text-black disabled:opacity-40">
          <MessageSquare className="mr-2 inline size-4" />Ask
        </button>
      </div>
    </section>
  );
}

export function TimelinePanel({ caseId }: { caseId: string }) {
  const [events, setEvents] = useState<Array<{ id: string; title: string; body?: string; actor: string; created_at: string | null }>>([]);
  const [loading, setLoading] = useState(true);

  function timeAgo(iso: string | null) {
    if (!iso) return "";
    const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  useEffect(() => {
    import("@/lib/api-client").then(({ getCaseReport }) => {
      getCaseReport(caseId)
        .then(r => setEvents((r.events ?? []).map(e => ({ ...e, body: e.body ?? undefined }))))
        .catch(() => setEvents([]))
        .finally(() => setLoading(false));
    });
  }, [caseId]);

  return (
    <section className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl">
      <h2 className="mb-3 font-semibold">Case Timeline</h2>
      {loading ? <LoadingSkeleton label="timeline" /> : events.length === 0 ? (
        <p className="py-4 text-center text-xs text-proxy-tertiary">No events yet.</p>
      ) : (
        <div className="space-y-3">
          {events.map((event, i) => (
            <div key={event.id || i} className="flex items-start gap-3">
              <div className="mt-1 size-1.5 shrink-0 rounded-full bg-cyan-300/60" />
              <div>
                <p className="text-sm font-medium text-proxy-text">{event.title}</p>
                {event.body && <p className="mt-0.5 text-xs leading-5 text-proxy-muted">{event.body}</p>}
                <p className="mt-0.5 text-[10px] text-proxy-tertiary">{event.actor} · {timeAgo(event.created_at)}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function QuickActions({ onNew }: { onNew?: () => void }) {
  const actions: Array<[string, typeof Upload, string]> = [
    ["Upload Documents", Upload, "/dashboard/documents"],
    ["New Analysis", Sparkles, "/dashboard/new"],
    ["View Appeals", ClipboardList, "/dashboard/appeals"],
    ["AI Assistant", MessageSquare, "/dashboard/assistant"],
  ];
  return (
    <section className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {actions.map(([label, Icon, href]) => (
        <a key={label} href={href} className="motion-card rounded-lg border border-white/10 bg-white/[.035] p-4 text-left text-sm font-medium hover:border-cyan-300/40 hover:bg-cyan-300/[0.08]">
          <Icon className="mb-3 size-5 text-cyan-200" />{label}
        </a>
      ))}
    </section>
  );
}
