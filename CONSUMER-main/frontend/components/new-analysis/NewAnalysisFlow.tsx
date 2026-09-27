"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Upload, Play, Loader2, FileText, AlertCircle, CheckCircle2, Sparkles,
  ArrowUpRight, Trash2, RotateCcw, ClipboardList, ScrollText,
  Search, FileSearch, Network, Target, PenLine, ShieldAlert,
  ShieldCheck, RefreshCw,
} from "lucide-react";
import {
  classifyQuery, runMultiDomainCase, uploadDocument, deleteDocument, listAnalyses,
  type DomainCandidate, type MultiDomainCaseResponse, type UploadedDocument, type AgentBreakdown,
  type ReviewAgentOutput,
} from "@/lib/api-client";
import { DOMAIN_THEME, domainTheme } from "@/components/chat/domain-theme";
import { ReasoningLanes } from "@/components/chat/ReasoningLanes";
import { CitationConstellation } from "@/components/chat/CitationConstellation";
import { markdownComponents } from "@/components/chat/markdown-components";
import { ESTIMATED_STAGES } from "@/components/chat/pipeline";
import { PREF_KEYS, getPref } from "@/lib/preferences";

const DOMAIN_PROMPTS: Record<string, string> = {
  health_insurance: "My health insurance claim was denied for a pre-existing condition exclusion.",
  banking: "My bank charged me twice for the same transaction and won't refund it.",
  airlines: "My flight was cancelled and the airline refused a refund.",
  telecom: "My telecom provider is billing me for a plan I cancelled two months ago.",
  ecommerce: "An online seller sent me a counterfeit product and refuses a return.",
  government: "My passport renewal application has been stuck in review for 90 days.",
  housing: "My builder delayed possession of my flat by 18 months under RERA.",
  healthcare: "I was overcharged for a hospital procedure that my insurance should have covered.",
};

const DOMAIN_TAGLINES: Record<string, string> = {
  health_insurance: "Claim denials, reimbursement disputes, policy clause interpretation.",
  banking: "Chargebacks, unauthorized transactions, loan and fee disputes.",
  airlines: "Cancellations, delays, denied boarding, baggage claims.",
  telecom: "Billing errors, service outages, plan mis-selling, porting.",
  ecommerce: "Refunds, defective products, warranty denials, delivery disputes.",
  government: "RTI requests, certificates, public scheme grievance appeals.",
  housing: "Security deposits, rent agreements, builder possession delays.",
  healthcare: "Hospital billing, discharge records, duplicate charges.",
};

interface PendingUpload {
  id: string;
  filename: string;
  progress: number;
  phase: "uploading" | "ocr";
  error?: string;
}

interface DomainAnswer {
  domain: string;
  route: string;
  report: string | null;
  breakdown: AgentBreakdown;
}

export function NewAnalysisFlow() {
  const router = useRouter();
  // Stable SSR-safe default; the real saved preference (if any) is only
  // read client-side after mount to avoid a hydration mismatch (see the
  // same fix in NotificationsCenter.tsx for why reading localStorage in a
  // useState initializer is unsafe here).
  const [focusDomain, setFocusDomain] = useState("health_insurance");
  useEffect(() => {
    setFocusDomain(getPref(PREF_KEYS.newAnalysisDefaultDomain, "health_insurance"));
  }, []);
  const [domainCounts, setDomainCounts] = useState<Record<string, number>>({});
  const [issueText, setIssueText] = useState("");
  const [livePreview, setLivePreview] = useState<DomainCandidate[]>([]);
  const [classifying, setClassifying] = useState(false);
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDocument[]>([]);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [draftAppeals, setDraftAppeals] = useState(false);
  const [runState, setRunState] = useState<"idle" | "running" | "complete" | "error">("idle");
  const [filledCount, setFilledCount] = useState(0);
  const [result, setResult] = useState<MultiDomainCaseResponse | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runningElapsedMs, setRunningElapsedMs] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const stageTimerRef = useRef<number | null>(null);

  // The estimated-stages animation (below) necessarily finishes in ~10s, but
  // real multi-agent runs -- several sequential LLM calls per domain, run in
  // parallel across domains -- genuinely take 30-120+s. Without a ticking
  // clock the UI looks frozen for the remainder of a real run, which reads
  // as broken rather than slow.
  useEffect(() => {
    if (runState !== "running") {
      setRunningElapsedMs(0);
      return;
    }
    const start = performance.now();
    const timer = window.setInterval(() => setRunningElapsedMs(Math.round(performance.now() - start)), 200);
    return () => window.clearInterval(timer);
  }, [runState]);

  useEffect(() => {
    listAnalyses()
      .then((analyses) => {
        const counts: Record<string, number> = {};
        for (const a of analyses) for (const d of a.domains_involved) counts[d] = (counts[d] ?? 0) + 1;
        setDomainCounts(counts);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Clear synchronously on every keystroke/domain-switch instead of only
    // once the new classification resolves -- otherwise the "Detected: X"
    // badges (and the reasoning lanes, which fall back to this list) kept
    // showing the *previous* domain for the full 500ms+debounce/network
    // round trip, which read as the UI being stuck on the old domain.
    setLivePreview([]);
    if (issueText.trim().length < 12) {
      setClassifying(false);
      return;
    }
    setClassifying(true);
    const timer = window.setTimeout(async () => {
      try {
        setLivePreview((await classifyQuery(issueText)).candidates);
      } catch {
        setLivePreview([]);
      } finally {
        setClassifying(false);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [issueText]);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      for (const file of list) {
        const pendingId = crypto.randomUUID();
        setPendingUploads((current) => [...current, { id: pendingId, filename: file.name, progress: 0, phase: "uploading" }]);
        try {
          const doc = await uploadDocument(focusDomain, file, {
            onProgress: (percent) =>
              setPendingUploads((current) =>
                current.map((p) =>
                  p.id === pendingId
                    ? { ...p, progress: percent, phase: percent >= 100 ? "ocr" : "uploading" }
                    : p
                )
              ),
          });
          setPendingUploads((current) => current.filter((p) => p.id !== pendingId));
          setUploadedDocs((current) => [doc, ...current]);
        } catch (err) {
          setPendingUploads((current) =>
            current.map((p) => (p.id === pendingId ? { ...p, error: err instanceof Error ? err.message : "Upload failed" } : p))
          );
          window.setTimeout(() => setPendingUploads((current) => current.filter((p) => p.id !== pendingId)), 4000);
        }
      }
    },
    [focusDomain]
  );

  async function removeDoc(doc: UploadedDocument) {
    setUploadedDocs((current) => current.filter((d) => d.document_id !== doc.document_id));
    try {
      await deleteDocument(doc.document_id);
    } catch {
      // best-effort -- it's already removed from this session's intake list
    }
  }

  function pickDomain(domain: string) {
    // Only auto-fill the sample prompt if the box is empty or still holds
    // the *previous* domain's sample prompt untouched -- switching from
    // healthcare to telecom used to leave healthcare's sample text sitting
    // in the box forever, because this only ever checked "is it empty",
    // which was only ever true once, the very first time.
    const isAutofilledPlaceholder = !issueText.trim() || issueText === DOMAIN_PROMPTS[focusDomain];
    if (isAutofilledPlaceholder) setIssueText(DOMAIN_PROMPTS[domain] ?? "");
    setFocusDomain(domain);
  }

  const canRun = issueText.trim().length > 12 && runState !== "running";

  async function runAnalysis() {
    if (!canRun) return;
    setRunState("running");
    setError(null);
    setResult(null);
    setFilledCount(0);
    const id = crypto.randomUUID();
    setCaseId(id);

    let stageIndex = 0;
    stageTimerRef.current = window.setInterval(() => {
      stageIndex = Math.min(stageIndex + 1, ESTIMATED_STAGES.length);
      setFilledCount(stageIndex);
    }, 1300);

    try {
      const response = await runMultiDomainCase(id, issueText, draftAppeals, uploadedDocs.map((doc) => doc.document_id));
      setResult(response);
      // The backend saves the case under this exact id — store it so the
      // "Open in My Analyses" button can deep-link straight into it.
      setCaseId(id);
      setRunState("complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong reaching the multi-agent backend.");
      setRunState("error");
    } finally {
      if (stageTimerRef.current) window.clearInterval(stageTimerRef.current);
      setFilledCount(0);
    }
  }

  function reset() {
    setIssueText("");
    setUploadedDocs([]);
    setResult(null);
    setRunState("idle");
    setCaseId(null);
    setError(null);
  }

  const lanes = useMemo(() => {
    if (runState === "complete" && result) {
      return result.domains_analyzed.map((d) => ({ domain: d, trace: result.per_domain_results[d]?.agent_trace }));
    }
    const domains = livePreview.length ? livePreview.map((c) => c.domain) : [focusDomain];
    return domains.map((d) => ({ domain: d, trace: undefined as string[] | undefined }));
  }, [runState, result, livePreview, focusDomain]);

  return (
    <div
      className="relative flex min-h-[720px] flex-1 flex-col gap-4"
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragActive(false);
        if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
      }}
    >
      {dragActive && (
        <div className="pointer-events-none fixed inset-0 z-30 grid place-items-center bg-black/60 backdrop-blur-sm">
          <div className="rounded-2xl border-2 border-dashed border-cyan-300/60 bg-cyan-300/5 px-10 py-8 text-center">
            <Upload className="mx-auto mb-2 size-9 text-cyan-200" />
            <p className="text-sm font-medium text-cyan-100">Drop to add evidence to this analysis</p>
          </div>
        </div>
      )}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.csv,.json,image/*"
        className="hidden"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
      />

      <DomainDeck focusDomain={focusDomain} counts={domainCounts} onSelect={pickDomain} />

      <section className="rounded-2xl border border-cyan-300/20 bg-glass p-4 shadow-glow-cyan backdrop-blur-2xl sm:p-6">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[.2em] text-cyan-200">Structured analysis flow</p>
            <h2 className="mt-1 text-xl font-semibold sm:text-2xl">{domainTheme(focusDomain).label}: describe, evidence, analyze</h2>
          </div>
          <FlowStepper runState={runState} />
        </div>
        <div className="grid gap-5 xl:grid-cols-[.95fr_1.05fr]">
          <IntakePanel
            issueText={issueText}
            setIssueText={setIssueText}
            livePreview={livePreview}
            classifying={classifying}
            uploadedDocs={uploadedDocs}
            pendingUploads={pendingUploads}
            onPick={() => fileInputRef.current?.click()}
            onRemoveDoc={removeDoc}
            draftAppeals={draftAppeals}
            setDraftAppeals={setDraftAppeals}
            canRun={canRun}
            runState={runState}
            onRun={runAnalysis}
          />
          <LiveFlowPanel
            lanes={lanes}
            runState={runState}
            filledCount={filledCount}
            error={error}
            elapsedMs={runningElapsedMs}
            issueText={issueText}
            classifying={classifying}
            livePreview={livePreview}
            uploadedDocs={uploadedDocs}
            pendingUploads={pendingUploads}
          />
        </div>
      </section>

      {runState === "complete" && result && (
        <ResultsPanel
          result={result}
          caseId={caseId}
          onReset={reset}
          onOpenAnalyses={() => router.push(caseId ? `/dashboard/analyses?case=${encodeURIComponent(caseId)}` : "/dashboard/analyses")}
          onOpenAppeals={() => router.push("/dashboard/appeals")}
        />
      )}
    </div>
  );
}

function FlowStepper({ runState }: { runState: "idle" | "running" | "complete" | "error" }) {
  const steps = ["Domain", "Intake", "Agents", "Results"];
  const active = runState === "idle" ? 1 : runState === "running" ? 2 : 3;
  return (
    <div className="flex max-w-full gap-2 overflow-x-auto">
      {steps.map((step, index) => (
        <div
          key={step}
          className={`min-w-fit rounded-full border px-3 py-1.5 text-xs ${
            index <= active ? "border-cyan-300/35 bg-cyan-300/10 text-cyan-100" : "border-white/10 text-proxy-tertiary"
          }`}
        >
          {step}
        </div>
      ))}
    </div>
  );
}

function DomainDeck({
  focusDomain, counts, onSelect,
}: {
  focusDomain: string;
  counts: Record<string, number>;
  onSelect: (domain: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-xl sm:p-5">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold">8-domain analysis cockpit</h2>
          <p className="mt-1 text-sm text-proxy-muted">Pick a focus domain for uploaded evidence -- the multi-agent router still classifies your description across every domain automatically.</p>
        </div>
        <span className="rounded-full border border-green-300/25 bg-green-300/10 px-3 py-1 text-xs text-green-100">8/8 domains online</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {Object.keys(DOMAIN_THEME).map((domain) => {
          const theme = domainTheme(domain);
          const active = focusDomain === domain;
          return (
            <button
              key={domain}
              onClick={() => onSelect(domain)}
              className={`motion-card rounded-lg border p-4 text-left transition-colors ${
                active ? "border-white/25 bg-white/[0.04] shadow-glow-cyan" : "border-white/10 bg-black/20"
              }`}
              style={active ? { borderColor: `${theme.color}60` } : undefined}
            >
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-semibold">{theme.label}</h3>
                <span
                  className="rounded-full px-2 py-1 text-[11px]"
                  style={{ backgroundColor: active ? `${theme.color}25` : "rgba(255,255,255,.06)", color: active ? theme.color : "var(--proxy-tertiary)" }}
                >
                  {active ? "Active" : "Select"}
                </span>
              </div>
              <p className="min-h-10 text-xs leading-5 text-proxy-muted">{DOMAIN_TAGLINES[domain]}</p>
              <div className="mt-3 text-xs text-proxy-tertiary">{counts[domain] ?? 0} past analys{(counts[domain] ?? 0) === 1 ? "is" : "es"}</div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function extractionLabel(doc: UploadedDocument): string {
  if (doc.ocr_applied) {
    const pages = doc.pages_ocrd ? ` · ${doc.pages_ocrd} page${doc.pages_ocrd === 1 ? "" : "s"}` : "";
    return `OCR${pages}`;
  }
  if (doc.extraction_method === "native") return "Text extracted";
  if (doc.extraction_method === "mixed") return "Mixed OCR";
  if ((doc.text_chars ?? 0) === 0) return "No text found";
  return "Processed";
}

function IntakePanel({
  issueText, setIssueText, livePreview, classifying, uploadedDocs, pendingUploads, onPick, onRemoveDoc, draftAppeals, setDraftAppeals, canRun, runState, onRun,
}: {
  issueText: string;
  setIssueText: (v: string) => void;
  livePreview: DomainCandidate[];
  classifying: boolean;
  uploadedDocs: UploadedDocument[];
  pendingUploads: PendingUpload[];
  onPick: () => void;
  onRemoveDoc: (doc: UploadedDocument) => void;
  draftAppeals: boolean;
  setDraftAppeals: (v: boolean) => void;
  canRun: boolean;
  runState: "idle" | "running" | "complete" | "error";
  onRun: () => void;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">1. Intake</h3>
        <button onClick={onPick} className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100">
          <Upload className="size-3" /> Add evidence
        </button>
      </div>

      {(uploadedDocs.length > 0 || pendingUploads.length > 0) && (
        <div className="mb-3 space-y-1.5">
          {pendingUploads.map((upload) => (
            <div key={upload.id} className="rounded-lg border border-white/10 bg-black/20 p-2">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="truncate text-proxy-text">{upload.filename}</span>
                {upload.error ? (
                  <span className="flex items-center gap-1 text-red-200"><AlertCircle className="size-3" /> Failed</span>
                ) : upload.phase === "ocr" ? (
                  <span className="flex items-center gap-1 text-cyan-200"><Loader2 className="size-3 animate-spin" /> OCR</span>
                ) : (
                  <span className="text-proxy-tertiary">{upload.progress}%</span>
                )}
              </div>
              {!upload.error && (
                <div className="h-1 overflow-hidden rounded-full bg-white/10">
                  <div
                    className={`h-full rounded-full transition-all ${upload.phase === "ocr" ? "animate-pulse bg-purple-300" : "bg-cyan-300"}`}
                    style={{ width: upload.phase === "ocr" ? "100%" : `${upload.progress}%` }}
                  />
                </div>
              )}
            </div>
          ))}
          {uploadedDocs.map((doc) => (
            <div key={doc.document_id} className="rounded-lg border border-white/10 bg-black/20 p-2 text-xs">
              <div className="flex items-center gap-2">
                <FileText className="size-3.5 shrink-0 text-cyan-200" />
                <span className="min-w-0 flex-1 truncate text-proxy-text">{doc.filename}</span>
                {doc.indexed ? (
                  <span className="flex shrink-0 items-center gap-1 text-[10px] text-green-300"><CheckCircle2 className="size-3" /> Indexed</span>
                ) : (doc.text_chars ?? 0) > 0 ? (
                  <span className="shrink-0 text-[10px] text-amber-300">Not indexed</span>
                ) : (
                  <span className="shrink-0 text-[10px] text-red-300">No text</span>
                )}
                <button onClick={() => onRemoveDoc(doc)} className="shrink-0 text-proxy-tertiary hover:text-red-200">
                  <Trash2 className="size-3" />
                </button>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 pl-5 text-[10px] text-proxy-tertiary">
                <span>{extractionLabel(doc)}</span>
                {(doc.text_chars ?? 0) > 0 && <span>{doc.text_chars?.toLocaleString()} chars</span>}
              </div>
              {doc.text_preview && (
                <p className="mt-1.5 line-clamp-2 pl-5 text-[10px] leading-4 text-proxy-muted">{doc.text_preview}</p>
              )}
              {doc.relevance_warning && (
                <p className="mt-1.5 pl-5 text-[10px] leading-4 text-amber-200">{doc.relevance_warning}</p>
              )}
            </div>
          ))}
        </div>
      )}

      <label className="block">
        <span className="mb-2 block text-sm font-medium">Describe the problem</span>
        <textarea
          value={issueText}
          onChange={(event) => setIssueText(event.target.value)}
          placeholder="Example: My builder delayed possession of my flat by 18 months under RERA."
          className="min-h-32 w-full rounded-xl border border-white/10 bg-black/25 p-3 text-sm leading-6 text-proxy-muted outline-none focus:border-cyan-300/60"
        />
      </label>

      {livePreview.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wide text-proxy-tertiary">Detected:</span>
          {livePreview.map((candidate) => {
            const theme = domainTheme(candidate.domain);
            return (
              <span key={candidate.domain} className="rounded-full border px-2 py-0.5 text-[10px]" style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}>
                {theme.label}
              </span>
            );
          })}
        </div>
      )}

      <label className="mt-3 flex items-center gap-2 text-xs text-proxy-muted">
        <input
          type="checkbox"
          checked={draftAppeals}
          onChange={(event) => setDraftAppeals(event.target.checked)}
          className="size-3.5 accent-cyan-300"
        />
        Also draft appeal / complaint letters (slower -- extra reasoning pass per domain)
      </label>

      <button
        onClick={onRun}
        disabled={!canRun}
        className="run-orb mt-3 w-full rounded-xl px-4 py-3 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-40"
      >
        {runState === "running" ? (
          <><Loader2 className="mr-2 inline size-4 animate-spin" /> Agents running{classifying ? "" : "..."}</>
        ) : (
          <><Play className="mr-2 inline size-4" /> Run Multi-Domain Analysis</>
        )}
      </button>

      <style jsx>{`
        .run-orb {
          background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0);
          box-shadow: 0 0 18px rgba(0, 229, 255, 0.35);
        }
      `}</style>
    </div>
  );
}

const STILL_WORKING_PHRASES = [
  "Domain specialists are reasoning over retrieved evidence...",
  "Cross-checking clauses and regulations against your case...",
  "Building response strategy and scoring evidence quality...",
  "Complex multi-domain cases can take up to two minutes -- still working, not stuck.",
];

function LiveFlowPanel({
  lanes, runState, filledCount, error, elapsedMs, issueText, classifying, livePreview, uploadedDocs, pendingUploads,
}: {
  lanes: Array<{ domain: string; trace?: string[] }>;
  runState: "idle" | "running" | "complete" | "error";
  filledCount: number;
  error: string | null;
  elapsedMs: number;
  issueText: string;
  classifying: boolean;
  livePreview: DomainCandidate[];
  uploadedDocs: UploadedDocument[];
  pendingUploads: PendingUpload[];
}) {
  const elapsedSeconds = elapsedMs / 1000;
  const stagesExhausted = filledCount >= ESTIMATED_STAGES.length;
  const stillWorkingPhrase = STILL_WORKING_PHRASES[Math.min(Math.floor(elapsedSeconds / 15), STILL_WORKING_PHRASES.length - 1)];
  // While idle, node 0 ("Classifying query across domains") is genuinely
  // complete the moment the real classifyQuery call resolves -- reflect
  // that instead of leaving every node dormant until the full run starts,
  // which is what made this panel look dead even after real classification
  // and real document uploads had already happened.
  const idleFilledCount = livePreview.length > 0 ? 1 : 0;
  const displayFilledCount = runState === "running" ? filledCount : idleFilledCount;

  const live = runState === "running" || classifying;

  return (
    <div className={`live-flow-card rounded-xl border p-4 transition-colors ${live ? "border-cyan-300/30" : "border-white/10"} bg-black/20`}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold">2. Live Agent Flow</h3>
          <span className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide ${live ? "border-cyan-300/40 text-cyan-200" : "border-white/10 text-proxy-tertiary"}`}>
            <span className={`size-1.5 rounded-full ${live ? "live-dot bg-cyan-300" : "bg-proxy-tertiary"}`} />
            {live ? "Live" : "Idle"}
          </span>
        </div>
        {runState === "running" ? (
          <span className="font-mono text-xs text-cyan-200">{elapsedSeconds.toFixed(1)}s elapsed</span>
        ) : (
          <span className="text-xs text-proxy-tertiary">Real multi-agent trace</span>
        )}
      </div>
      <ReasoningLanes lanes={lanes} processing={live} filledCount={displayFilledCount} />

      <div className="console-frame relative mt-4 overflow-hidden rounded-xl border border-white/10 bg-[#050608] p-4 font-mono text-xs text-proxy-muted">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-cyan-100"><ScrollText className="size-3.5" /> Console</div>
          <div className="flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-red-400/50" />
            <span className="size-1.5 rounded-full bg-amber-300/50" />
            <span className="size-1.5 rounded-full bg-green-300/50" />
          </div>
        </div>
        {error ? (
          <p className="flex items-center gap-2 text-red-200"><AlertCircle className="size-3.5 shrink-0" /> {error}</p>
        ) : runState === "idle" ? (
          <IdleConsole issueText={issueText} classifying={classifying} livePreview={livePreview} uploadedDocs={uploadedDocs} pendingUploads={pendingUploads} />
        ) : runState === "running" ? (
          <>
            <p className="mb-1"><span className="text-green-300">&#10003;</span> Domain Router: classifying across domains...</p>
            {!stagesExhausted ? (
              <>
                <p className="mb-1"><span className="text-green-300">&#10003;</span> {ESTIMATED_STAGES[Math.min(filledCount, ESTIMATED_STAGES.length - 1)]}...</p>
                <p className="text-proxy-tertiary">(estimate -- replaced by the real trace once the response lands)</p>
              </>
            ) : (
              <p className="flex items-center gap-2 text-proxy-muted">
                <Loader2 className="size-3 shrink-0 animate-spin text-cyan-300" /> {stillWorkingPhrase}
              </p>
            )}
          </>
        ) : (
          <p><span className="text-green-300">&#10003;</span> Complete. Results and citations unlocked below.</p>
        )}
        {live && <span className="console-cursor" aria-hidden />}
        {live && <div className="console-scanline" aria-hidden />}
      </div>
      <style jsx>{`
        .live-dot {
          animation: live-pulse 1.4s ease-in-out infinite;
        }
        @keyframes live-pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(0, 229, 255, 0.55); }
          50% { opacity: 0.5; box-shadow: 0 0 0 3px rgba(0, 229, 255, 0); }
        }
        .console-cursor {
          display: inline-block;
          width: 6px;
          height: 12px;
          margin-left: 2px;
          background: #5ff0d7;
          animation: console-blink 1s step-end infinite;
          vertical-align: -2px;
        }
        @keyframes console-blink {
          50% { opacity: 0; }
        }
        .console-scanline {
          position: absolute;
          left: 0;
          right: 0;
          height: 40%;
          background: linear-gradient(180deg, rgba(0, 229, 255, 0) 0%, rgba(0, 229, 255, 0.05) 50%, rgba(0, 229, 255, 0) 100%);
          animation: console-sweep 3.2s linear infinite;
          pointer-events: none;
        }
        @keyframes console-sweep {
          0% { top: -40%; }
          100% { top: 100%; }
        }
        .live-flow-card {
          background-image: radial-gradient(circle at 100% 0%, rgba(0, 229, 255, 0.05), transparent 45%);
        }
      `}</style>
    </div>
  );
}

function IdleConsole({
  issueText, classifying, livePreview, uploadedDocs, pendingUploads,
}: {
  issueText: string;
  classifying: boolean;
  livePreview: DomainCandidate[];
  uploadedDocs: UploadedDocument[];
  pendingUploads: PendingUpload[];
}) {
  const lines: React.ReactNode[] = [];

  for (const upload of pendingUploads) {
    lines.push(
      <p key={`pending-${upload.id}`} className="mb-1 flex items-center gap-2 text-proxy-muted">
        <Loader2 className="size-3 shrink-0 animate-spin text-cyan-300" />
        {upload.phase === "ocr"
          ? `Running OCR on ${upload.filename}...`
          : `Uploading ${upload.filename}... ${upload.progress}%`}
      </p>
    );
  }
  for (const doc of uploadedDocs) {
    const status =
      doc.indexed
        ? "indexed and searchable"
        : (doc.text_chars ?? 0) > 0
          ? `${extractionLabel(doc)} · ${doc.text_chars?.toLocaleString()} chars`
          : "no text extracted — try a clearer scan or photo";
    lines.push(
      <p key={`doc-${doc.document_id}`} className="mb-1">
        <span className={doc.indexed ? "text-green-300" : (doc.text_chars ?? 0) > 0 ? "text-amber-300" : "text-red-300"}>
          {doc.indexed || (doc.text_chars ?? 0) > 0 ? "✓" : "!"}
        </span>{" "}
        {doc.filename} — {status}
      </p>
    );
  }

  if (!issueText.trim() && uploadedDocs.length === 0 && pendingUploads.length === 0) {
    lines.push(<p key="waiting">Waiting for domain, evidence, or issue description...</p>);
  } else if (classifying) {
    lines.push(
      <p key="classifying" className="flex items-center gap-2 text-proxy-muted">
        <Loader2 className="size-3 shrink-0 animate-spin text-cyan-300" /> Domain Router: classifying your description across all 8 domains...
      </p>
    );
  } else if (livePreview.length > 0) {
    const domainList = livePreview.map((c) => domainTheme(c.domain).label).join(", ");
    lines.push(
      <p key="classified" className="mb-1">
        <span className="text-green-300">&#10003;</span> Domain Router: classified as {domainList}.
      </p>
    );
    lines.push(<p key="ready" className="text-proxy-tertiary">Ready -- run the analysis to dispatch the real 6-agent pipeline for each detected domain.</p>);
  } else if (issueText.trim().length > 0 && issueText.trim().length <= 12) {
    lines.push(<p key="typing">Keep typing -- domain classification starts after 12 characters.</p>);
  } else if (issueText.trim().length > 12) {
    lines.push(<p key="no-match" className="text-proxy-tertiary">No strong domain match yet -- analysis will still run using the selected focus domain above.</p>);
  }

  return <>{lines}</>;
}

function ResultsPanel({
  result, caseId, onReset, onOpenAnalyses, onOpenAppeals,
}: {
  result: MultiDomainCaseResponse;
  caseId: string | null;
  onReset: () => void;
  onOpenAnalyses: () => void;
  onOpenAppeals: () => void;
}) {
  const answers: DomainAnswer[] = Object.entries(result.per_domain_results).map(([domain, r]) => ({
    domain, route: r.route, report: r.final_report, breakdown: r.agent_breakdown,
  }));
  const appealCount = Object.values(result.per_domain_results).reduce((sum, r) => sum + r.appeals.length, 0);

  // Trust score: how many cited regulations were actually confirmed present
  // in the retrieved source text vs. just stated by the model -- a signal a
  // raw chat answer can't give you at all, since it never checks its own
  // claims against anything.
  const domainResults = Object.values(result.per_domain_results);
  const trust = domainResults.reduce(
    (acc, r) => {
      const regs = r.agent_breakdown.research.regulations ?? [];
      const unverified = new Set(r.agent_breakdown.research.unverified_regulations ?? []);
      acc.total += regs.length;
      acc.verified += regs.filter((item) => !unverified.has(item)).length;
      return acc;
    },
    { total: 0, verified: 0 },
  );
  const selfCorrections = domainResults.reduce((sum, r) => sum + (r.agent_breakdown.review_retry_count ?? 0), 0);

  return (
    <section className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl sm:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="grid size-8 place-items-center rounded-lg border border-green-300/25 bg-green-300/10">
            <Sparkles className="size-4 text-green-200" />
          </div>
          <div>
            <p className="text-sm font-semibold text-proxy-text">Analysis complete</p>
            <p className="text-[11px] text-proxy-tertiary">
              {result.domains_analyzed.length} domain{result.domains_analyzed.length === 1 ? "" : "s"} analyzed &middot; {appealCount} document{appealCount === 1 ? "" : "s"} drafted
              {caseId ? <> &middot; Case <span className="font-mono text-proxy-muted">{caseId.slice(0, 8)}</span></> : null}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={onOpenAnalyses} className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-100 hover:bg-cyan-300/15">
            Open in My Analyses <ArrowUpRight className="size-3.5" />
          </button>
          {appealCount > 0 && (
            <button onClick={onOpenAppeals} className="inline-flex items-center gap-1.5 rounded-lg border border-purple-300/25 bg-purple-300/10 px-3 py-1.5 text-xs text-purple-100 hover:bg-purple-300/15">
              <ClipboardList className="size-3.5" /> View drafted appeals
            </button>
          )}
          <button onClick={onReset} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-proxy-muted hover:border-white/25">
            <RotateCcw className="size-3.5" /> New analysis
          </button>
        </div>
      </div>

      {(trust.total > 0 || selfCorrections > 0) && (
        <div className="mb-4 flex flex-wrap gap-2">
          {trust.total > 0 && (
            <div className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-black/20 px-2.5 py-1.5 text-[11px]">
              <ShieldCheck className={`size-3.5 ${trust.verified === trust.total ? "text-green-300" : "text-amber-300"}`} />
              <span className="text-proxy-muted">
                <span className="font-medium text-proxy-text">{trust.verified}/{trust.total}</span> cited regulations confirmed in real retrieved sources
              </span>
            </div>
          )}
          {selfCorrections > 0 && (
            <div className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300/25 bg-amber-300/10 px-2.5 py-1.5 text-[11px]">
              <RefreshCw className="size-3.5 text-amber-300" />
              <span className="text-amber-100">
                Review agent caught {selfCorrections} unverified claim{selfCorrections === 1 ? "" : "s"} and re-generated the strategy before showing you this
              </span>
            </div>
          )}
        </div>
      )}

      <div className="space-y-3">
        {answers.map((answer) => (
          <DomainAnswerSection key={answer.domain} answer={answer} />
        ))}
      </div>

      {result.combined_citations.length > 0 && (
        <div className="mt-5 border-t border-white/5 pt-5">
          <p className="mb-3 text-xs font-medium uppercase tracking-[0.16em] text-proxy-tertiary">Citation map</p>
          <CitationConstellation citations={result.combined_citations} />
        </div>
      )}
    </section>
  );
}

function DomainAnswerSection({ answer }: { answer: DomainAnswer }) {
  const theme = domainTheme(answer.domain);
  const [expanded, setExpanded] = useState(true);
  const [tab, setTab] = useState<"report" | "agents">("report");
  if (!answer.report) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-white/5" style={{ borderLeftColor: theme.color, borderLeftWidth: 3 }}>
      <button onClick={() => setExpanded((current) => !current)} className="flex w-full items-center justify-between bg-white/[0.02] px-3 py-2 text-left">
        <span className="flex items-center gap-2 text-xs font-medium" style={{ color: theme.color }}>
          {theme.label}
          <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px] text-proxy-tertiary">{answer.route}</span>
        </span>
        <span className="text-[10px] text-proxy-tertiary">{expanded ? "Collapse" : "Expand"}</span>
      </button>
      {expanded && (
        <div className="px-4 py-3">
          <div className="mb-3 flex gap-1 rounded-lg border border-white/10 bg-black/20 p-0.5">
            <button
              onClick={() => setTab("report")}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-[11px] font-medium transition-colors ${tab === "report" ? "bg-white/10 text-proxy-text" : "text-proxy-tertiary hover:text-proxy-muted"}`}
            >
              <ScrollText className="size-3" /> Plain-English Report
            </button>
            <button
              onClick={() => setTab("agents")}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-[11px] font-medium transition-colors ${tab === "agents" ? "bg-white/10 text-proxy-text" : "text-proxy-tertiary hover:text-proxy-muted"}`}
            >
              <Network className="size-3" /> 6-Agent Breakdown
            </button>
          </div>
          {tab === "report" ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {answer.report}
            </ReactMarkdown>
          ) : (
            <AgentBreakdownView breakdown={answer.breakdown} accent={theme.color} />
          )}
        </div>
      )}
    </div>
  );
}

interface AgentSpec {
  key: keyof AgentBreakdown;
  label: string;
  icon: typeof Search;
  color: string;
  tagline: string;
}

const AGENT_SPECS: AgentSpec[] = [
  { key: "research", label: "Research Agent", icon: Search, color: "#00e5ff", tagline: "Vector search + knowledge graph + web -- what rules apply" },
  { key: "evidence", label: "Evidence Agent", icon: FileSearch, color: "#37f29a", tagline: "Structured facts extracted from your description and documents" },
  { key: "knowledge_graph", label: "Knowledge Graph Agent", icon: Network, color: "#9b5cff", tagline: "Cross-user institution patterns from the live graph" },
  { key: "strategy", label: "Strategy Agent", icon: Target, color: "#ffc857", tagline: "Whether to proceed, and the recommended path" },
  { key: "negotiation", label: "Negotiation Agent", icon: PenLine, color: "#ff6fb0", tagline: "Drafted letters and complaints, ready for your review" },
  { key: "review", label: "Review Agent", icon: ShieldAlert, color: "#ff4d6d", tagline: "Devil's advocate audit of everything above" },
];

// Backend agents occasionally emit a nested object where a plain string is
// expected (see app/agents/negotiation_agent/agent.py's _as_text -- fixed
// server-side, but this is a UI-level safety net so a raw {"subject":...}
// blob can never render as literal JSON text again, even if some future
// field slips through un-flattened).
function safeText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(safeText).join(", ");
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (typeof obj.body === "string") {
      return obj.subject ? `${safeText(obj.subject)}\n\n${obj.body}` : obj.body;
    }
    return Object.entries(obj)
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${safeText(v)}`)
      .join(" · ");
  }
  return String(value);
}

function AgentBreakdownView({ breakdown, accent }: { breakdown: AgentBreakdown; accent: string }) {
  return (
    <div className="relative space-y-2.5 pl-3">
      <div className="absolute bottom-3 left-[15px] top-3 w-px bg-gradient-to-b from-white/15 via-white/10 to-transparent" aria-hidden />
      {AGENT_SPECS.map((spec, i) => (
        <AgentCard key={spec.key} spec={spec} index={i} breakdown={breakdown} fallbackAccent={accent} />
      ))}
    </div>
  );
}

function AgentCard({
  spec, index, breakdown, fallbackAccent,
}: {
  spec: AgentSpec;
  index: number;
  breakdown: AgentBreakdown;
  fallbackAccent: string;
}) {
  const [open, setOpen] = useState(false);
  const Icon = spec.icon;
  const color = spec.color || fallbackAccent;

  return (
    <div className="relative">
      <div
        className="absolute left-[-3px] top-4 grid size-3.5 shrink-0 place-items-center rounded-full border-2 border-black/40 text-[8px] font-bold text-black"
        style={{ backgroundColor: color }}
      >
        {index + 1}
      </div>
      <div
        className={`overflow-hidden rounded-lg border bg-black/20 transition-colors ${open ? "" : "border-white/10"}`}
        style={open ? { borderColor: `${color}45` } : undefined}
      >
        <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2.5 px-3 py-2.5 pl-6 text-left hover:bg-white/[0.03]">
          <div className="grid size-7 shrink-0 place-items-center rounded-lg border" style={{ borderColor: `${color}40`, backgroundColor: `${color}15` }}>
            <Icon className="size-3.5" style={{ color }} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-proxy-text">{spec.label}</p>
            <p className="truncate text-[10px] text-proxy-tertiary">{spec.tagline}</p>
          </div>
          <span
            className="shrink-0 rounded-full border px-2 py-0.5 text-[10px] transition-colors"
            style={open ? { borderColor: `${color}45`, backgroundColor: `${color}15`, color } : { borderColor: "rgba(255,255,255,.1)", color: "var(--proxy-tertiary)" }}
          >
            {open ? "Hide" : "Show"}
          </span>
        </button>
        {open && (
          <div className="aperture-agent-content border-t border-white/5 px-3 py-3 pl-6">
            <AgentContent agentKey={spec.key} breakdown={breakdown} color={color} />
          </div>
        )}
      </div>
    </div>
  );
}

function ListBlock({ label, items, color }: { label: string; items?: unknown[]; color: string }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mb-2.5">
      <p className="mb-1 text-[10px] uppercase tracking-wide text-proxy-tertiary">{label}</p>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs leading-5 text-proxy-muted">
            <span className="mt-1.5 size-1 shrink-0 rounded-full" style={{ backgroundColor: color }} />
            {safeText(item)}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Deterministically checks each cited item against the actual retrieved
// source text server-side (app/services/citation_verification.py) -- this
// renders that verdict inline instead of presenting every citation with
// the same unearned confidence, so a hallucinated regulation name reads
// differently from one directly grounded in what was retrieved.
function CitationListBlock({ label, items, unverified, color }: { label: string; items?: string[]; unverified?: string[]; color: string }) {
  if (!items || items.length === 0) return null;
  const unverifiedSet = new Set(unverified ?? []);
  return (
    <div className="mb-2.5">
      <p className="mb-1 text-[10px] uppercase tracking-wide text-proxy-tertiary">{label}</p>
      <ul className="space-y-1">
        {items.map((item, i) => {
          const flagged = unverifiedSet.has(item);
          return (
            <li key={i} className="flex items-start gap-1.5 text-xs leading-5 text-proxy-muted">
              {flagged ? (
                <AlertCircle className="mt-0.5 size-3 shrink-0 text-amber-300" />
              ) : (
                <CheckCircle2 className="mt-0.5 size-3 shrink-0" style={{ color }} />
              )}
              <span>
                {safeText(item)}
                {flagged && <span className="ml-1.5 text-[10px] text-amber-300">not confirmed in retrieved sources</span>}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AgentContent({ agentKey, breakdown, color }: { agentKey: keyof AgentBreakdown; breakdown: AgentBreakdown; color: string }) {
  if (agentKey === "research") {
    const r = breakdown.research;
    return (
      <>
        <ListBlock label="Applicable clauses / rules" items={r.applicable_clauses} color={color} />
        <ListBlock label="Possible exclusions" items={r.possible_exclusions} color={color} />
        <ListBlock label="Key timelines" items={r.waiting_periods} color={color} />
        <CitationListBlock label="Regulations cited" items={r.regulations} unverified={r.unverified_regulations} color={color} />
        {r.confidence !== undefined && (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[10px] text-proxy-tertiary">Research confidence</span>
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/5"><div className="h-full rounded-full" style={{ width: `${r.confidence * 100}%`, backgroundColor: color }} /></div>
            <span className="text-[10px] text-proxy-muted">{Math.round(r.confidence * 100)}%</span>
          </div>
        )}
        {r.summary && <p className="mt-2.5 text-xs leading-6 text-proxy-muted">{safeText(r.summary)}</p>}
      </>
    );
  }

  if (agentKey === "evidence") {
    const e = breakdown.evidence;
    const fields = Object.entries(e).filter(([k, v]) => !["documents_missing", "key_dates", "summary", "evidence_relevant"].includes(k) && typeof v === "string" && v.trim());
    return (
      <>
        {e.evidence_relevant === false && (
          <div className="mb-2.5 flex items-start gap-2 rounded-lg border border-amber-300/25 bg-amber-300/10 p-2.5">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-amber-300" />
            <p className="text-xs leading-5 text-amber-100">Uploaded evidence doesn't appear to match this case -- nothing was extracted from it to avoid guessing.</p>
          </div>
        )}
        {fields.length > 0 && (
          <div className="mb-2.5 grid grid-cols-2 gap-2">
            {fields.map(([key, value]) => (
              <div key={key} className="rounded-lg border border-white/5 bg-black/20 p-2">
                <p className="text-[9px] uppercase tracking-wide text-proxy-tertiary">{key.replace(/_/g, " ")}</p>
                <p className="mt-0.5 truncate text-xs text-proxy-text">{safeText(value)}</p>
              </div>
            ))}
          </div>
        )}
        <ListBlock label="Documents still missing" items={e.documents_missing} color={color} />
        <ListBlock label="Key dates" items={e.key_dates} color={color} />
        {e.summary && <p className="mt-2.5 text-xs leading-6 text-proxy-muted">{safeText(e.summary)}</p>}
      </>
    );
  }

  if (agentKey === "knowledge_graph") {
    const patterns = breakdown.knowledge_graph.patterns;
    if (patterns.length === 0) return <p className="text-xs text-proxy-tertiary">No cross-user patterns found yet for this institution.</p>;
    return (
      <div className="space-y-2">
        {patterns.map((p, i) => (
          <div key={i} className="rounded-lg border border-white/5 bg-black/20 p-2.5">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[10px] text-proxy-tertiary">{domainTheme(p.domain).label}</span>
              <span className="text-[10px] text-proxy-muted">{Math.round(p.confidence * 100)}% confidence</span>
            </div>
            <p className="text-xs leading-5 text-proxy-text">{p.pattern}</p>
          </div>
        ))}
      </div>
    );
  }

  if (agentKey === "strategy") {
    const s = breakdown.strategy;
    const steps = Array.isArray(s.recommended_strategy) ? s.recommended_strategy : s.recommended_strategy ? [s.recommended_strategy] : [];
    // The strategy model doesn't always return clean JSON -- when parsing
    // falls back, can_appeal lands on the literal "UNKNOWN" placeholder.
    // Showing that next to a confident-looking "0%" ring read as a real
    // answer rather than what it is: a degraded, unparsed response.
    const degraded = s.can_appeal === "UNKNOWN";
    return (
      <>
        {degraded ? (
          <div className="mb-2.5 flex items-start gap-2 rounded-lg border border-white/10 bg-white/[0.03] p-2.5">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-proxy-tertiary" />
            <p className="text-xs leading-5 text-proxy-tertiary">The strategy model's response couldn't be parsed into a clean structure this run -- showing its best-effort summary below instead of a confidence score.</p>
          </div>
        ) : (
          <div className="mb-3 flex items-center gap-3">
            {s.success_probability !== undefined && (
              <div className="flex items-center gap-2">
                <svg width="36" height="36" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="4" />
                  <circle
                    cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round"
                    strokeDasharray={2 * Math.PI * 15} strokeDashoffset={2 * Math.PI * 15 * (1 - s.success_probability)}
                    transform="rotate(-90 18 18)"
                  />
                </svg>
                <div>
                  <p className="text-xs font-semibold text-proxy-text">{Math.round(s.success_probability * 100)}%</p>
                  <p className="text-[9px] text-proxy-tertiary">success probability</p>
                </div>
              </div>
            )}
            {s.can_appeal && (
              <span className="rounded-full border px-2 py-0.5 text-[10px]" style={{ borderColor: `${color}40`, backgroundColor: `${color}15`, color }}>
                Can proceed: {s.can_appeal}
              </span>
            )}
          </div>
        )}
        <ListBlock label="Recommended steps" items={steps} color={color} />
        <ListBlock label="Evidence still required" items={s.evidence_required} color={color} />
        <ListBlock label="Escalation path" items={s.escalation_path} color={color} />
        {s.summary && <p className="mt-2.5 text-xs leading-6 text-proxy-muted">{safeText(s.summary)}</p>}
      </>
    );
  }

  if (agentKey === "negotiation") {
    const n = breakdown.negotiation;
    const docs: Array<[string, string | undefined]> = [
      ["Appeal / dispute letter", n.appeal_letter],
      ["Complaint email", n.complaint_email],
      ["Escalation note", n.escalation_note],
      ["Consumer complaint", n.consumer_complaint],
    ].filter(([, v]) => v && v.trim()) as Array<[string, string]>;
    if (docs.length === 0) return <p className="text-xs text-proxy-tertiary">No documents drafted for this run -- enable "Also draft appeal / complaint letters" and re-run to generate them.</p>;
    return (
      <div className="space-y-2">
        {docs.map(([label, content]) => (
          <details key={label} className="agent-doc rounded-lg border border-white/5 bg-black/20 p-2.5">
            <summary className="cursor-pointer text-xs font-medium" style={{ color }}>{label}</summary>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-proxy-muted">{safeText(content)}</p>
          </details>
        ))}
      </div>
    );
  }

  // review
  const rv = breakdown.review;
  const history = breakdown.review_history ?? [];
  return (
    <>
      {history.length > 1 && <SelfCorrectionTimeline history={history} />}
      {rv.approval_ready !== undefined && (
        <span className={`mb-2.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] ${rv.approval_ready ? "border border-green-300/25 bg-green-300/10 text-green-100" : "border border-amber-300/25 bg-amber-300/10 text-amber-100"}`}>
          {rv.approval_ready ? "Ready for approval" : "Needs attention before approval"}
        </span>
      )}
      <ListBlock label="Missing evidence" items={rv.missing_evidence} color={color} />
      <ListBlock label="Hallucination risks caught" items={rv.hallucination_risks} color={color} />
      <ListBlock label="Wrong clause/regulation risks caught" items={rv.wrong_clause_risks} color={color} />
      <ListBlock label="Weak arguments flagged" items={rv.weak_arguments} color={color} />
      {rv.summary && <p className="mt-2.5 text-xs leading-6 text-proxy-muted">{safeText(rv.summary)}</p>}
    </>
  );
}

/**
 * Renders every review pass, not just the final one -- proof the pipeline
 * actually caught a bad claim and re-generated the strategy, rather than
 * just showing the already-clean end result with no record it wasn't
 * clean the first time. This is real pipeline history (review_history),
 * not a scripted animation.
 */
function SelfCorrectionTimeline({ history }: { history: ReviewAgentOutput[] }) {
  return (
    <div className="mb-3 rounded-lg border border-amber-300/20 bg-amber-300/5 p-2.5">
      <p className="mb-2 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-amber-200">
        <RefreshCw className="size-3" /> Self-correction: {history.length} review passes
      </p>
      <div className="space-y-2">
        {history.map((pass, i) => {
          const issues = [...(pass.hallucination_risks ?? []), ...(pass.wrong_clause_risks ?? [])];
          const isLast = i === history.length - 1;
          return (
            <div key={i} className="flex gap-2 text-xs">
              <div className="flex flex-col items-center">
                <span
                  className="grid size-4 shrink-0 place-items-center rounded-full text-[9px] font-semibold"
                  style={{ backgroundColor: isLast ? "#37f29a" : "#ffc857", color: "#000" }}
                >
                  {i + 1}
                </span>
                {!isLast && <span className="mt-0.5 h-full w-px flex-1 bg-white/10" />}
              </div>
              <div className="pb-2">
                <p className="text-proxy-text">
                  {isLast
                    ? issues.length > 0
                      ? `Pass ${i + 1}: re-generated -- issues resolved`
                      : `Pass ${i + 1}: approved, no issues`
                    : `Pass ${i + 1}: flagged ${issues.length} issue${issues.length === 1 ? "" : "s"}, sent back for correction`}
                </p>
                {!isLast && issues.length > 0 && (
                  <ul className="mt-1 space-y-0.5 text-proxy-tertiary">
                    {issues.map((issue, j) => (
                      <li key={j} className="line-clamp-1">&bull; {issue}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
