"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, Download, Filter, Layers3, Maximize2, Pause, Play, RotateCcw, Search, Share2 } from "lucide-react";
import { AppShell } from "./Shell";
import { domainRegistry, getDomainConfig, type DomainConfig, type DomainKey } from "@/lib/proxy-analysis-data";
import { listAnalyses } from "@/lib/api-client";
import { intelEdges, intelNodes, intelTimeline, kindStyles, layerKeys, type IntelEdge, type IntelNode, type LayerKey } from "@/lib/intelligence-center-data";

function buildDomainUniverse(config: DomainConfig): IntelNode[] {
  if (config.key === "health_insurance") {
    return intelNodes;
  }

  return intelNodes.map(node => {
    switch (node.id) {
      case "claim":
        return {
          ...node,
          label: config.entityLabel,
          summary: `${config.entityLabel} concerning ${config.sampleMatter.toLowerCase()}.`,
          why: `This is the central dispute object. Every policy, evidence, and regulation relationship is evaluated against it.`,
          source: config.uploadSlots[1] || node.source,
        };
      case "policy":
        return {
          ...node,
          label: config.uploadSlots[0] || "Agreement/Terms",
          summary: `Primary governing terms for the ${config.label} account/matter.`,
          why: `Defines the rules used by the counterparty to evaluate this case.`,
          source: config.uploadSlots[0] || node.source,
        };
      case "coverage":
        return {
          ...node,
          label: config.graphNodes[2] || "Coverage",
          summary: `Specific match conditions and benefits under review.`,
          why: `Ensures valid entitlements are not overlooked.`,
          source: config.uploadSlots[0] || node.source,
        };
      case "waiting":
        return {
          ...node,
          label: "Contested Clause",
          summary: `Relevant exclusion or constraint used in rejection.`,
          why: `The core contested term in this dispute.`,
          source: config.uploadSlots[0] || node.source,
        };
      case "hospital":
        return {
          ...node,
          label: config.sampleCounterparty,
          summary: `Institution processing and billing origin.`,
          why: `Establishes the counterparty timeline and action context.`,
          source: config.uploadSlots[2] || node.source,
        };
      case "diagnosis":
        return {
          ...node,
          label: config.sampleIssue.split(" ")[0] || "Incident Details",
          summary: config.sampleIssue,
          why: `Anchors the facts of the case in evidence.`,
          source: config.uploadSlots[2] || node.source,
        };
      case "treatment":
        return {
          ...node,
          label: config.graphNodes[4] || "Service Event",
          summary: `Specific event or service being disputed.`,
          why: `Links the factual occurrence to the governing policy clauses.`,
          source: config.uploadSlots[2] || node.source,
        };
      case "irdai":
        return {
          ...node,
          label: config.graphNodes[5] || "Regulation",
          summary: `Regulatory protections governing the dispute.`,
          why: `Provides statutory leverage and external recourse standard.`,
          source: config.sourcesLabel,
        };
      case "finding":
        return {
          ...node,
          summary: `Identified gap or inconsistency in the counterparty's reasoning.`,
        };
      case "strategy":
        return {
          ...node,
          summary: `Custom strategy to appeal based on terms and regulatory guidance.`,
          action: config.actionName,
        };
      case "appeal":
        return {
          ...node,
          label: `${config.shortLabel} Notice`,
          summary: `Draft copy of dispute letter containing code citations.`,
        };
      default:
        return node;
    }
  });
}

import { SceneBackground } from "@/components/3d/SceneBackground";

export function IntelligenceCenter() {
  const [domain, setDomain] = useState<DomainKey>("health_insurance");
  const [selectedId, setSelectedId] = useState("claim");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [enabledLayers, setEnabledLayers] = useState<Record<LayerKey, boolean>>({ Documents: true, Entities: true, Relationships: true, "AI Reasoning": true, Recommendations: true, Appeal: true });
  const [minConfidence, setMinConfidence] = useState(60);
  const [timeIndex, setTimeIndex] = useState(6);
  const [playing, setPlaying] = useState(true);
  const [domainConfidence, setDomainConfidence] = useState<Record<string, number>>({});

  useEffect(() => { const saved = window.localStorage.getItem("proxy:last-analysis-domain") as DomainKey | null; if (saved && domainRegistry.some((item) => item.key === saved)) setDomain(saved); }, []);

  // Pull real per-domain confidence from actual analyses
  useEffect(() => {
    listAnalyses().then(analyses => {
      const confByDomain: Record<string, number[]> = {};
      for (const a of analyses) {
        if (a.avg_confidence === null) continue;
        for (const d of a.domains_involved) {
          if (!confByDomain[d]) confByDomain[d] = [];
          confByDomain[d].push(a.avg_confidence);
        }
      }
      const avg: Record<string, number> = {};
      for (const [d, vals] of Object.entries(confByDomain)) {
        avg[d] = Math.round((vals.reduce((s, v) => s + v, 0) / vals.length) * 100);
      }
      setDomainConfidence(avg);
    }).catch(() => {});
  }, []);

  const config = getDomainConfig(domain);
  const realConfidence = domainConfidence[domain] ?? null;
  const domainNodes = useMemo(() => buildDomainUniverse(config), [config]);
  const visibleNodes = useMemo(() => domainNodes.filter((node, index) => enabledLayers[node.layer] && node.confidence >= minConfidence && index <= timeIndex + 4), [domainNodes, enabledLayers, minConfidence, timeIndex]);
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = intelEdges.filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to) && enabledLayers[edge.layer] && edge.confidence >= minConfidence);
  const selected = visibleNodes.find((node) => node.id === selectedId) ?? visibleNodes[0] ?? domainNodes[0];

  return <AppShell><SceneBackground /><div className="relative z-10 mx-auto flex min-h-screen max-w-[1800px] flex-col px-4 py-5 sm:px-6 lg:px-8"><Header domainLabel={config.label} confidence={realConfidence} /><div className="grid min-h-[720px] flex-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)_360px]"><LeftPanel domain={domain} setDomain={setDomain} enabledLayers={enabledLayers} setEnabledLayers={setEnabledLayers} minConfidence={minConfidence} setMinConfidence={setMinConfidence} /><KnowledgeUniverse nodes={visibleNodes} edges={visibleEdges} selectedId={selected.id} hoveredId={hoveredId} setSelectedId={setSelectedId} setHoveredId={setHoveredId} /><RightPanel node={selected} domainLabel={config.label} /></div><BottomTimeline timeIndex={timeIndex} setTimeIndex={setTimeIndex} playing={playing} setPlaying={setPlaying} /></div></AppShell>;
}

function Header({ domainLabel, confidence }: { domainLabel: string; confidence: number | null }) {
  return <header className="mb-4 rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl"><div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between"><div><p className="text-xs uppercase tracking-[.22em] text-cyan-200">PROXY AI Reasoning</p><h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Knowledge Intelligence Center</h1><p className="mt-2 max-w-4xl text-sm leading-6 text-proxy-muted">Watch the AI build relationships between claims, policies, evidence, regulations, and institution decisions in real time — powered by your actual case data.</p></div><div className="grid gap-2 sm:grid-cols-5 xl:min-w-[620px]"><HeaderAction label="Global Search" icon={Search} /><HeaderMetric label="Current Domain" value={domainLabel} /><HeaderMetric label="Avg Confidence" value={confidence !== null ? `${confidence}%` : "—"} /><HeaderAction label="Export PNG" icon={Download} /><HeaderAction label="AI Live" icon={Activity} live /></div></div></header>;
}
function HeaderAction({ label, icon: Icon, live }: { label: string; icon: React.ComponentType<{ className?: string }>; live?: boolean }) { return <button className={`rounded-xl border px-3 py-2 text-left text-xs ${live ? "border-green-300/25 bg-green-300/10 text-green-100 shadow-glow-green" : "border-white/10 bg-white/[.035] text-proxy-muted hover:border-cyan-300/35"}`}><Icon className="mb-1 size-4 text-cyan-200" />{label}</button>; }
function HeaderMetric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p className="text-[11px] text-proxy-tertiary">{label}</p><p className="truncate text-sm font-semibold">{value}</p></div>; }

function LeftPanel({ domain, setDomain, enabledLayers, setEnabledLayers, minConfidence, setMinConfidence }: { domain: DomainKey; setDomain: (domain: DomainKey) => void; enabledLayers: Record<LayerKey, boolean>; setEnabledLayers: (layers: Record<LayerKey, boolean>) => void; minConfidence: number; setMinConfidence: (value: number) => void }) {
  return <aside className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl"><div className="mb-4 flex items-center gap-2"><Filter className="size-4 text-cyan-200" /><h2 className="font-semibold">Filters</h2></div><label className="mb-4 block text-sm"><span className="mb-2 block text-proxy-muted">Domain</span><select value={domain} onChange={(event) => { const next = event.target.value as DomainKey; setDomain(next); window.localStorage.setItem("proxy:last-analysis-domain", next); }} className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-cyan-300/60">{domainRegistry.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label><div className="mb-5"><div className="mb-2 flex items-center justify-between text-sm"><span className="text-proxy-muted">Confidence Filter</span><span className="text-cyan-100">{minConfidence}%+</span></div><input type="range" min="40" max="95" value={minConfidence} onChange={(event) => setMinConfidence(Number(event.target.value))} className="w-full accent-cyan-300" /></div><div className="mb-5"><div className="mb-2 flex items-center gap-2"><Layers3 className="size-4 text-cyan-200" /><h3 className="text-sm font-semibold">Agent Layers</h3></div><div className="space-y-2">{layerKeys.map((layer) => <label key={layer} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm text-proxy-muted"><span>{layer}</span><input type="checkbox" checked={enabledLayers[layer]} onChange={() => setEnabledLayers({ ...enabledLayers, [layer]: !enabledLayers[layer] })} className="accent-cyan-300" /></label>)}</div></div><div className="grid gap-2 text-xs text-proxy-muted"><FilterChip label="Regulation" /><FilterChip label="Hospital" /><FilterChip label="Policy" /><FilterChip label="Claim" /><FilterChip label="Evidence" /></div></aside>;
}
function FilterChip({ label }: { label: string }) { return <button className="rounded-lg border border-white/10 bg-white/[.035] px-3 py-2 text-left hover:border-cyan-300/40">{label} filter active</button>; }

function KnowledgeUniverse({ nodes, edges, selectedId, hoveredId, setSelectedId, setHoveredId }: { nodes: IntelNode[]; edges: IntelEdge[]; selectedId: string; hoveredId: string | null; setSelectedId: (id: string) => void; setHoveredId: (id: string | null) => void }) {
  const map = new Map(nodes.map((node) => [node.id, node]));
  const related = new Set(edges.filter((edge) => edge.from === hoveredId || edge.to === hoveredId || edge.from === selectedId || edge.to === selectedId).flatMap((edge) => [edge.from, edge.to]));
  return <section className="relative overflow-hidden rounded-2xl border border-cyan-300/15 bg-[#050608] shadow-glow-cyan"><div className="absolute left-4 top-4 z-10 rounded-xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur-xl"><p className="text-xs uppercase tracking-[.18em] text-proxy-tertiary">Live Knowledge Universe</p><p className="text-sm text-cyan-100">{nodes.length} entities / {edges.length} relationships</p></div><GraphInsights nodes={nodes} edges={edges} /><svg viewBox="0 0 1180 620" className="h-full min-h-[680px] w-full" role="img" aria-label="Live AI knowledge universe"><defs><radialGradient id="universeGlow"><stop offset="0%" stopColor="rgba(0,229,255,.18)" /><stop offset="100%" stopColor="rgba(0,0,0,0)" /></radialGradient><linearGradient id="edgeGradient" x1="0" x2="1"><stop offset="0%" stopColor="#00e5ff" /><stop offset="100%" stopColor="#9b5cff" /></linearGradient></defs><rect width="1180" height="620" fill="url(#universeGlow)" /><g>{edges.map((edge) => { const from = map.get(edge.from); const to = map.get(edge.to); if (!from || !to) return null; const active = edge.from === hoveredId || edge.to === hoveredId || edge.from === selectedId || edge.to === selectedId; return <g key={`${edge.from}-${edge.to}`} opacity={hoveredId && !active ? .18 : 1}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="url(#edgeGradient)" strokeWidth={Math.max(1.2, edge.confidence / 28)} strokeOpacity={active ? .9 : .34} strokeLinecap="round" className={active ? "animate-pulse" : ""} /><circle r="3" fill="#00e5ff"><animateMotion dur={`${3.8 - edge.confidence / 100}s`} repeatCount="indefinite" path={`M${from.x},${from.y} L${to.x},${to.y}`} /></circle></g>; })}</g><g>{nodes.map((node, index) => <GraphNode key={node.id} node={node} active={node.id === selectedId} dimmed={Boolean(hoveredId) && node.id !== hoveredId && !related.has(node.id)} delay={index * 70} onClick={() => setSelectedId(node.id)} onHover={setHoveredId} />)}</g></svg><MiniMap nodes={nodes} selectedId={selectedId} /></section>;
}

function GraphNode({ node, active, dimmed, delay, onClick, onHover }: { node: IntelNode; active: boolean; dimmed: boolean; delay: number; onClick: () => void; onHover: (id: string | null) => void }) { const style = kindStyles[node.kind]; const Icon = style.icon; return <g role="button" tabIndex={0} onClick={onClick} onMouseEnter={() => onHover(node.id)} onMouseLeave={() => onHover(null)} opacity={dimmed ? .22 : 1} style={{ cursor: "pointer", transition: "opacity .2s ease" }}><circle cx={node.x} cy={node.y} r={active ? 34 : 28} fill="rgba(5,5,5,.88)" stroke={style.color} strokeWidth={active ? 3 : 1.5} filter="drop-shadow(0 0 18px var(--node-glow))" style={{ "--node-glow": style.glow, animation: `breathe 2.8s ease-in-out ${delay}ms infinite` } as React.CSSProperties} /><foreignObject x={node.x - 11} y={node.y - 12} width="22" height="22"><Icon className="size-5" style={{ color: style.color }} /></foreignObject><text x={node.x} y={node.y + 48} textAnchor="middle" fill="#dbeafe" fontSize="12">{node.label}</text><text x={node.x} y={node.y + 64} textAnchor="middle" fill="#687386" fontSize="10">{node.confidence}%</text>{active && <circle cx={node.x} cy={node.y} r="44" fill="none" stroke={style.color} strokeOpacity=".45"><animate attributeName="r" from="38" to="58" dur="1.8s" repeatCount="indefinite" /><animate attributeName="opacity" from=".7" to="0" dur="1.8s" repeatCount="indefinite" /></circle>}</g>; }

function GraphInsights({ nodes, edges }: { nodes: IntelNode[]; edges: IntelEdge[] }) { const avg = Math.round(nodes.reduce((sum, node) => sum + node.confidence, 0) / Math.max(nodes.length, 1)); const cards = [["Entities", nodes.length], ["Relationships", edges.length], ["Evidence", nodes.filter((node) => node.layer === "Entities").length], ["Confidence", `${avg}%`]]; return <div className="absolute right-4 top-4 z-10 grid grid-cols-2 gap-2">{cards.map(([label, value]) => <div key={label} className="rounded-xl border border-white/10 bg-black/45 px-3 py-2 backdrop-blur-xl"><p className="text-[10px] uppercase tracking-[.16em] text-proxy-tertiary">{label}</p><p className="text-sm font-semibold text-cyan-100">{value}</p></div>)}</div>; }
function MiniMap({ nodes, selectedId }: { nodes: IntelNode[]; selectedId: string }) { return <div className="absolute bottom-4 right-4 z-10 rounded-xl border border-white/10 bg-black/55 p-2 backdrop-blur-xl"><svg viewBox="0 0 118 62" className="h-16 w-32">{nodes.map((node) => <circle key={node.id} cx={node.x / 10} cy={node.y / 10} r={node.id === selectedId ? 3 : 1.7} fill={node.id === selectedId ? "#00e5ff" : "#687386"} />)}</svg></div>; }

function RightPanel({ node, domainLabel }: { node: IntelNode; domainLabel: string }) { const style = kindStyles[node.kind]; const Icon = style.icon; return <aside className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl"><div className="mb-4 flex items-start gap-3"><div className="grid size-11 place-items-center rounded-xl border" style={{ borderColor: style.color, boxShadow: `0 0 24px ${style.glow}` }}><Icon className="size-5" style={{ color: style.color }} /></div><div><p className="text-xs uppercase tracking-[.18em] text-proxy-tertiary">Selected Node</p><h2 className="text-xl font-semibold">{node.label}</h2><p className="mt-1 text-xs text-cyan-100">{node.kind} / {domainLabel}</p></div></div><ConfidenceRing value={node.confidence} color={style.color} /><InfoBlock title="Summary" body={node.summary} /><InfoBlock title="Why it exists" body={node.why} /><InfoBlock title="Created by" body={node.agent} /><InfoBlock title="Source document" body={`${node.source} / ${node.page}`} /><div className="rounded-xl border border-cyan-300/20 bg-cyan-300/8 p-3"><p className="text-sm font-medium text-cyan-100">Document synchronization</p><p className="mt-1 text-xs leading-5 text-proxy-muted">Clicking this node would open the source document, scroll to {node.page}, and animate the matching highlight.</p></div><div className="mt-4 grid gap-2"><button className="rounded-lg bg-cyan-300 px-3 py-2 text-sm font-semibold text-black">{node.action}</button><button className="rounded-lg border border-white/10 px-3 py-2 text-sm text-proxy-muted">Pin node</button><button className="rounded-lg border border-white/10 px-3 py-2 text-sm text-proxy-muted">Expand neighborhood</button></div></aside>; }
function ConfidenceRing({ value, color }: { value: number; color: string }) { return <div className="mb-4 rounded-xl border border-white/10 bg-black/20 p-4"><div className="flex items-center gap-4"><svg viewBox="0 0 80 80" className="size-20"><circle cx="40" cy="40" r="31" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="7" /><circle cx="40" cy="40" r="31" fill="none" stroke={color} strokeWidth="7" strokeDasharray={`${value * 1.95} 195`} strokeLinecap="round" transform="rotate(-90 40 40)" /></svg><div><p className="text-3xl font-semibold">{value}%</p><p className="text-xs text-proxy-muted">Node confidence</p></div></div></div>; }
function InfoBlock({ title, body }: { title: string; body: string }) { return <div className="mb-3 rounded-xl border border-white/10 bg-black/20 p-3"><p className="mb-1 text-[11px] uppercase tracking-[.16em] text-proxy-tertiary">{title}</p><p className="text-sm leading-6 text-proxy-muted">{body}</p></div>; }

function BottomTimeline({ timeIndex, setTimeIndex, playing, setPlaying }: { timeIndex: number; setTimeIndex: (value: number) => void; playing: boolean; setPlaying: (value: boolean) => void }) { return <footer className="mt-4 rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl"><div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between"><div><p className="text-xs uppercase tracking-[.18em] text-proxy-tertiary">Time Machine</p><h2 className="font-semibold">Replay AI thinking</h2></div><div className="flex flex-wrap gap-2"><button onClick={() => setPlaying(!playing)} className="rounded-lg border border-white/10 px-3 py-2 text-sm text-proxy-muted">{playing ? <Pause className="mr-2 inline size-4" /> : <Play className="mr-2 inline size-4" />}{playing ? "Pause" : "Resume"}</button><button className="rounded-lg border border-white/10 px-3 py-2 text-sm text-proxy-muted"><RotateCcw className="mr-2 inline size-4" />Reset View</button><button className="rounded-lg border border-white/10 px-3 py-2 text-sm text-proxy-muted"><Share2 className="mr-2 inline size-4" />Share</button><button className="rounded-lg border border-white/10 px-3 py-2 text-sm text-proxy-muted"><Maximize2 className="mr-2 inline size-4" />Fullscreen</button></div></div><input aria-label="Replay timeline" type="range" min="0" max={intelTimeline.length - 1} value={timeIndex} onChange={(event) => setTimeIndex(Number(event.target.value))} className="mb-3 w-full accent-cyan-300" /><div className="grid gap-2 md:grid-cols-7">{intelTimeline.map((event, index) => <button key={event} onClick={() => setTimeIndex(index)} className={`rounded-xl border px-3 py-3 text-left text-xs ${index <= timeIndex ? "border-cyan-300/35 bg-cyan-300/10 text-cyan-100" : "border-white/10 bg-black/20 text-proxy-tertiary"}`}><span className="mb-1 block font-mono">0{index + 1}</span>{event}</button>)}</div><div className="mt-4 rounded-xl border border-white/10 bg-black/25 p-3 font-mono text-xs text-proxy-muted"><p><span className="text-green-300">✓</span> Research Agent created policy and claim nodes</p><p><span className="text-green-300">✓</span> Evidence Agent linked diagnosis, treatment, hospital bill</p><p><span className="text-cyan-300">...</span> Review Agent validating confidence and weak arguments</p></div></footer>; }

