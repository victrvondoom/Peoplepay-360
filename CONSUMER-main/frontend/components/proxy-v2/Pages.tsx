"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Check, ChevronRight, FileText, Loader2, MessageSquare, Play, Send, Upload } from "lucide-react";
import { agentStages, type AgentStage, type StageStatus } from "@/lib/design-tokens";
import { analyses, demoAnalysis, domainRegistry, findDomainAnalysis, getAnalysisById, getDomainConfig, type Analysis, type DomainConfig, type DomainKey } from "@/lib/proxy-analysis-data";
import { AppShell } from "./Shell";
import { AnalysesList, AppealWorkflow, ChatPanel, DocumentHighlights, ErrorRecovery, GaugeCard, KnowledgeGraphView, LoadingSkeleton, TimelinePanel } from "./AnalysisWidgets";

type RunState = "idle" | "running" | "complete";
type UploadedFiles = Record<string, string>;

export function DashboardHome() {
  return <WorkbenchPage title="Multi-domain AI dispute command center" compact={false} />;
}

export function NewAnalysisPage() {
  return <WorkbenchPage title="New Multi-domain AI Analysis" compact={false} />;
}

function WorkbenchPage({ title, compact }: { title: string; compact: boolean }) {
  const [activeDomain, setActiveDomain] = useState<DomainKey>("health_insurance");
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFiles>({});
  const [issueText, setIssueText] = useState("");
  const [runState, setRunState] = useState<RunState>("idle");
  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const analysis = useMemo(() => findDomainAnalysis(activeDomain), [activeDomain]);
  const config = getDomainConfig(activeDomain);
  const uploadedCount = Object.values(uploadedFiles).filter(Boolean).length;
  const canRun = uploadedCount > 0 || issueText.trim().length > 12;

  function switchDomain(domain: DomainKey) {
    setActiveDomain(domain);
    setUploadedFiles({});
    setIssueText("");
    setRunState("idle");
    setActiveStageIndex(0);
  }

  function startRun() {
    if (!canRun) return;
    setRunState("running");
    setActiveStageIndex(0);
    const timer = window.setInterval(() => {
      setActiveStageIndex((current) => {
        if (current >= agentStages.length - 1) {
          window.clearInterval(timer);
          window.setTimeout(() => setRunState("complete"), 450);
          return current;
        }
        return current + 1;
      });
    }, 900);
  }

  const stagedAnalysis = withRuntimeStages(analysis, runState, activeStageIndex);

  return (
    <AppShell>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <Topbar title={title} subtitle="A single connected flow: select domain, provide documents or text, run agents, inspect results, draft action, and open the full room." />
        <DomainCommandDeck activeDomain={activeDomain} onSelect={switchDomain} />
        <AnalysisWorkbench
          analysis={stagedAnalysis}
          config={config}
          uploadedFiles={uploadedFiles}
          issueText={issueText}
          runState={runState}
          activeStageIndex={activeStageIndex}
          canRun={canRun}
          onFile={(slot, name) => setUploadedFiles((files) => ({ ...files, [slot]: name }))}
          onIssue={setIssueText}
          onRun={startRun}
        />
        {!compact && <section className="mt-5 grid gap-5 xl:grid-cols-[1fr_.82fr]"><AnalysesList /><DomainIntelligencePanel analysis={stagedAnalysis} /></section>}
      </div>
    </AppShell>
  );
}

export function AnalysisDetailById({ id }: { id: string }) { return <AnalysisDetail analysis={getAnalysisById(id)} />; }

export function AnalysisDetail({ analysis = demoAnalysis }: { analysis?: Analysis }) {
  const config = getDomainConfig(analysis.domain);
  return <AppShell><div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8"><Topbar title={`${analysis.id} / ${config.label}`} subtitle={`${analysis.counterparty} / ${analysis.matter} / ${analysis.claimant}`} /><AnalysisResults analysis={analysis} config={config} full /></div></AppShell>;
}

function AnalysisWorkbench(props: { analysis: Analysis; config: DomainConfig; uploadedFiles: UploadedFiles; issueText: string; runState: RunState; activeStageIndex: number; canRun: boolean; onFile: (slot: string, name: string) => void; onIssue: (value: string) => void; onRun: () => void }) {
  const { analysis, config, uploadedFiles, issueText, runState, activeStageIndex, canRun, onFile, onIssue, onRun } = props;
  return (
    <section className="rounded-2xl border border-cyan-300/25 bg-glass p-4 shadow-glow-cyan backdrop-blur-2xl">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div><p className="text-xs uppercase tracking-[.2em] text-cyan-200">Structured analysis flow</p><h2 className="mt-1 text-2xl font-semibold">{config.label}: Upload, describe, analyze</h2><p className="mt-1 text-sm text-proxy-muted">No disconnected pages. Everything below belongs to the selected domain and current analysis run.</p></div>
        <FlowStepper runState={runState} activeStageIndex={activeStageIndex} />
      </div>
      <div className="grid gap-5 xl:grid-cols-[.9fr_1.1fr]">
        <div className="rounded-xl border border-white/10 bg-black/20 p-4">
          <div className="mb-3 flex items-center justify-between"><h3 className="font-semibold">1. Intake</h3><span className="rounded-full border border-green-300/25 bg-green-300/10 px-2.5 py-1 text-xs text-green-100">{config.sourcesLabel}</span></div>
          <div className="grid gap-3 sm:grid-cols-2">{config.uploadSlots.map((slot) => <label key={slot} className="motion-card min-h-28 cursor-pointer rounded-lg border border-dashed border-white/18 bg-white/[.035] p-4 text-left hover:border-cyan-300/45 hover:bg-cyan-300/8"><Upload className="mb-3 size-5 text-cyan-200" /><p className="text-sm font-medium">{slot}</p><p className="mt-1 text-xs leading-5 text-proxy-muted">{uploadedFiles[slot] || "Choose PDF/image"}</p><input type="file" accept=".pdf,image/*" className="sr-only" onChange={(event) => onFile(slot, event.target.files?.[0]?.name ?? "")} /></label>)}</div>
          <label className="mt-4 block"><span className="mb-2 block text-sm font-medium">Or describe the problem</span><textarea value={issueText} onChange={(event) => onIssue(event.target.value)} placeholder={`Example: ${config.sampleIssue}`} className="min-h-32 w-full rounded-xl border border-white/10 bg-black/25 p-3 text-sm leading-6 text-proxy-muted outline-none focus:border-cyan-300/60" /></label>
          <button onClick={onRun} disabled={!canRun || runState === "running"} className="mt-4 w-full rounded-xl bg-cyan-300 px-4 py-3 text-sm font-semibold text-black shadow-glow-cyan disabled:cursor-not-allowed disabled:opacity-45"><Play className="mr-2 inline size-4" />{runState === "running" ? "Agents running" : `Run ${config.shortLabel} Analysis`}</button>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-4">
          <div className="mb-3 flex items-center justify-between"><h3 className="font-semibold">2. Live Agent Flow</h3><span className="text-xs text-proxy-tertiary">WebSocket/SSE/polling ready</span></div>
          <RuntimePipeline analysis={analysis} runState={runState} activeStageIndex={activeStageIndex} />
          <StreamingConsole config={config} runState={runState} activeStageIndex={activeStageIndex} />
        </div>
      </div>
      <div className="mt-5"><AnalysisResults analysis={analysis} config={config} locked={runState !== "complete"} /></div>
    </section>
  );
}

function AnalysisResults({ analysis, config, locked = false, full = false }: { analysis: Analysis; config: DomainConfig; locked?: boolean; full?: boolean }) {
  if (locked) return <LockedResults config={config} />;
  return (
    <section className="grid gap-5">
      <div className="grid gap-3 md:grid-cols-4"><GaugeCard label={config.primaryMetric} value={analysis.successProbability} /><GaugeCard label="Confidence Score" value={analysis.confidence} /><GaugeCard label={config.matchMetric} value={analysis.policyMatch} /><GaugeCard label="Missing Documents" value={analysis.missingDocuments.length} max={5} /></div>
      <div className="grid gap-5 xl:grid-cols-[1fr_.85fr]"><AIExplanation analysis={analysis} /><ChatPanel caseId={analysis.id} /></div>
      <DocumentHighlights analysis={analysis} />
      <KnowledgeGraphView analysis={analysis} />
      <div className="grid gap-5 xl:grid-cols-[1fr_.82fr]"><AppealWorkflow caseId={analysis.id} /><TimelinePanel caseId={analysis.id} /></div>
      {!full && <Link href={`/dashboard/analyses/${analysis.id}`} className="inline-flex w-fit items-center gap-2 rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-4 py-2 text-sm text-cyan-100">Open full analysis room <ChevronRight className="size-4" /></Link>}
    </section>
  );
}

function LockedResults({ config }: { config: DomainConfig }) { return <section className="rounded-xl border border-white/10 bg-black/20 p-4"><div className="mb-3 flex items-center gap-2 text-proxy-muted"><FileText className="size-4 text-cyan-200" />Results will appear here after the agent run finishes.</div><div className="grid gap-3 md:grid-cols-3"><LoadingSkeleton label={`${config.label} evidence`} /><LoadingSkeleton label={`${config.label} graph`} /><LoadingSkeleton label={`${config.actionName}`} /></div></section>; }

function RuntimePipeline({ analysis, runState, activeStageIndex }: { analysis: Analysis; runState: RunState; activeStageIndex: number }) { return <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">{agentStages.map((stage, index) => { const status = runState === "idle" ? "waiting" : runState === "complete" || index < activeStageIndex ? "done" : index === activeStageIndex ? "running" : "waiting"; return <AgentStageCard key={stage.id} name={stage.label} status={status} line={stage.stream[index % stage.stream.length]} />; })}</div>; }
function AgentStageCard({ name, status, line }: { name: string; status: StageStatus; line: string }) { const icon = status === "done" ? <Check className="size-4" /> : status === "running" ? <Loader2 className="size-4 animate-spin" /> : <span className="size-2 rounded-full bg-proxy-tertiary" />; const tone = status === "done" ? "border-green-300/25 bg-green-300/10 text-green-100" : status === "running" ? "border-cyan-300/40 bg-cyan-300/10 text-cyan-100 shadow-glow-cyan" : "border-white/10 bg-white/[.025] text-proxy-tertiary"; return <div className={`relative rounded-lg border p-3 ${tone}`}><div className="mb-2 flex items-center gap-2">{icon}<p className="text-sm font-medium">{name}</p></div><p className="min-h-10 text-xs leading-5 text-proxy-muted">{status === "running" ? line : status === "done" ? "Complete" : "Waiting for intake"}</p>{status === "running" && <div className="absolute inset-x-3 bottom-2 h-px overflow-hidden bg-white/10"><span className="block h-full w-1/2 animate-flow bg-cyan-200" /></div>}</div>; }
function StreamingConsole({ config, runState, activeStageIndex }: { config: DomainConfig; runState: RunState; activeStageIndex: number }) { const active = agentStages[activeStageIndex] ?? agentStages[0]; const lines = runState === "idle" ? [`Waiting for ${config.label} documents or issue text...`] : runState === "complete" ? [`All agents complete. ${config.actionName} and evidence report are ready.`, "Results unlocked below."] : [`${active.label}: ${active.stream[0]}...`, `${active.label}: ${active.stream[1]}...`, `${active.label}: ${active.stream[2]}...`]; return <div className="mt-4 rounded-xl border border-white/10 bg-[#050608] p-4 font-mono text-xs text-proxy-muted"><div className="mb-2 text-cyan-100">Streaming output</div>{lines.map((line, index) => <p key={line} className="mb-1"><span className="text-green-300">{runState === "running" && index === lines.length - 1 ? "..." : "✓"}</span> {line}</p>)}</div>; }

function FlowStepper({ runState, activeStageIndex }: { runState: RunState; activeStageIndex: number }) { const steps = ["Domain", "Intake", "Agents", "Results", "Action"]; const active = runState === "idle" ? 1 : runState === "running" ? 2 : 4; return <div className="flex max-w-full gap-2 overflow-x-auto">{steps.map((step, index) => <div key={step} className={`min-w-fit rounded-full border px-3 py-1.5 text-xs ${index <= active ? "border-cyan-300/35 bg-cyan-300/10 text-cyan-100" : "border-white/10 text-proxy-tertiary"}`}>{step}{step === "Agents" && runState === "running" ? ` ${activeStageIndex + 1}/6` : ""}</div>)}</div>; }

function Topbar({ title, subtitle }: { title: string; subtitle: string }) { return <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs uppercase tracking-[.22em] text-cyan-200">PROXY Command Center</p><h1 className="mt-2 text-3xl font-semibold sm:text-4xl">{title}</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-proxy-muted">{subtitle}</p></div><div className="flex gap-2"><button className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-proxy-muted">Audit logs</button><Link href="/dashboard/new" className="rounded-lg bg-cyan-300 px-3 py-2 text-sm font-semibold text-black shadow-glow-cyan">New Analysis</Link></div></header>; }

function DomainCommandDeck({ activeDomain, onSelect }: { activeDomain: DomainKey; onSelect: (domain: DomainKey) => void }) { return <section className="mb-5 rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl"><div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-xl font-semibold">8-domain analysis cockpit</h2><p className="mt-1 text-sm text-proxy-muted">Select a domain. The workbench below changes immediately and carries the run from intake to final action.</p></div><span className="rounded-full border border-green-300/25 bg-green-300/10 px-3 py-1 text-xs text-green-100">{domainRegistry.length}/8 UI domains enabled</span></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{domainRegistry.map((domain) => <DomainCard key={domain.key} domain={domain} active={activeDomain === domain.key} onSelect={onSelect} />)}</div></section>; }
function DomainCard({ domain, active, onSelect }: { domain: DomainConfig; active: boolean; onSelect: (domain: DomainKey) => void }) { return <button onClick={() => onSelect(domain.key)} className={`motion-card rounded-lg border p-4 text-left ${active ? "border-cyan-300/50 bg-cyan-300/10 shadow-glow-cyan" : "border-white/10 bg-black/20"}`}><div className="mb-3 flex items-center justify-between"><h3 className="font-semibold">{domain.label}</h3><span className="rounded-full bg-cyan-300/10 px-2 py-1 text-[11px] text-cyan-100">{active ? "Active" : domain.shortLabel}</span></div><p className="min-h-12 text-sm leading-6 text-proxy-muted">{domain.tagline}</p><div className="mt-4 grid grid-cols-2 gap-2 text-xs text-proxy-tertiary"><span>{domain.specialistAgents.length} agents</span><span>{domain.uploadSlots.length} upload slots</span><span>{domain.graphNodes.length} graph nodes</span><span>{domain.actionName}</span></div></button>; }

function AIExplanation({ analysis }: { analysis: Analysis }) { return <section className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl"><h2 className="mb-3 font-semibold">AI Explanation</h2>{analysis.explanation.map((item, index) => <details key={item.question} className="mb-2 rounded-lg border border-white/10 bg-black/20 p-3" open={index === 0}><summary className="cursor-pointer text-sm font-medium">{item.question}</summary><p className="mt-2 text-sm leading-6 text-proxy-muted">{item.answer}</p><p className="mt-2 text-xs text-cyan-100">Citations: {item.citations.join(", ")}</p></details>)}</section>; }
function DomainIntelligencePanel({ analysis }: { analysis: Analysis }) { const config = getDomainConfig(analysis.domain); return <section className="rounded-xl border border-white/10 bg-glass p-4 backdrop-blur-xl"><h2 className="mb-3 font-semibold">{config.label} Intelligence</h2><div className="mb-3 rounded-lg border border-purple-300/20 bg-purple-400/10 p-3"><p className="text-sm text-purple-100">{config.sourcesLabel}</p><p className="mt-1 text-xs leading-5 text-proxy-muted">This domain has its own RAG source family, upload requirements, graph schema, and specialist agents.</p></div><div className="grid gap-2 sm:grid-cols-2">{config.specialistAgents.map((agent) => <div key={agent} className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-proxy-muted">{agent}</div>)}</div><div className="mt-4"><ErrorRecovery /></div></section>; }

function withRuntimeStages(analysis: Analysis, runState: RunState, activeStageIndex: number): Analysis { const stages = agentStages.reduce((acc, stage, index) => { acc[stage.id as AgentStage] = runState === "idle" ? "waiting" : runState === "complete" || index < activeStageIndex ? "done" : index === activeStageIndex ? "running" : "waiting"; return acc; }, {} as Record<AgentStage, StageStatus>); return { ...analysis, stages, status: runState === "complete" ? "Action Ready" : runState === "running" ? "Analyzing" : "Needs Evidence" }; }

export function AnalysesPage() { return <AppShell><div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8"><Topbar title="My Analyses" subtitle="Search, filter, sort, favorite, pin, export history, and review audit activity across all 8 domains." /><AnalysesList /><div className="mt-5"><LoadingSkeleton label="analysis table" /></div></div></AppShell>; }
export function PlaceholderPage({ title }: { title: string }) { return <AppShell><div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8"><Topbar title={title} subtitle="Enterprise-ready workspace with realtime updates, keyboard navigation, all-domain search, and no blank states." /><div className="grid gap-4 md:grid-cols-2"><LoadingSkeleton label={title} /><ErrorRecovery /></div></div></AppShell>; }
export function findAnalysis(id: string) { return getAnalysisById(id); }
