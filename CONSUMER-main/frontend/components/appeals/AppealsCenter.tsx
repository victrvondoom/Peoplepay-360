"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText, Mail, AlertTriangle, Scale, Search, Copy, Download, Check, Loader2,
  Sparkles, ChevronRight, Send, Inbox, Clock, CheckCircle2, ArrowUpCircle,
  FolderOpen, Wand2,
} from "lucide-react";
import {
  listAppeals, runMultiDomainCase, updateAppealStatus, classifyQuery, listAnalyses, getCaseReport,
  type Appeal, type DomainCandidate, type AnalysisCase,
} from "@/lib/api-client";
import { ReasoningLanes } from "@/components/chat/ReasoningLanes";
import { domainTheme } from "@/components/chat/domain-theme";
import { markdownComponents } from "@/components/chat/markdown-components";
import { ESTIMATED_STAGES } from "@/components/chat/pipeline";

const DOC_TYPE_META: Record<string, { label: string; icon: typeof FileText }> = {
  appeal_letter: { label: "Appeal Letter", icon: FileText },
  complaint_email: { label: "Complaint Email", icon: Mail },
  escalation_note: { label: "Escalation Note", icon: AlertTriangle },
  consumer_complaint: { label: "Consumer Complaint", icon: Scale },
};

const STATUS_META: Record<Appeal["status"], { label: string; color: string; icon: typeof Clock }> = {
  draft: { label: "Draft", color: "#a8b3c7", icon: Clock },
  sent: { label: "Sent", color: "#00e5ff", icon: Send },
  escalated: { label: "Escalated", color: "#ffc857", icon: ArrowUpCircle },
  resolved: { label: "Resolved", color: "#37f29a", icon: CheckCircle2 },
};

const STATUS_ORDER: Appeal["status"][] = ["draft", "sent", "escalated", "resolved"];

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function AppealsCenter() {
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<Appeal["status"] | "all">("all");
  const [search, setSearch] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genQuery, setGenQuery] = useState("");
  const [genDomains, setGenDomains] = useState<DomainCandidate[]>([]);
  const [filledCount, setFilledCount] = useState(0);
  const [genError, setGenError] = useState<string | null>(null);
  const stageTimerRef = useRef<number | null>(null);

  // Cases already analyzed in New Analysis -- generating an appeal from one
  // of these reuses that case's real summary and uploaded documents instead
  // of asking the user to redescribe everything in a disconnected text box
  // that has never seen their evidence.
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [analysesLoading, setAnalysesLoading] = useState(true);
  const [generatingCaseId, setGeneratingCaseId] = useState<string | null>(null);
  const [caseGenError, setCaseGenError] = useState<string | null>(null);

  async function refresh() {
    try {
      const data = await listAppeals();
      setAppeals(data);
      return data;
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }

  async function refreshAnalyses() {
    try {
      setAnalyses(await listAnalyses());
    } catch {
      // keep last-known list on a transient failure
    } finally {
      setAnalysesLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    refreshAnalyses();
  }, []);

  async function generateFromCase(analysis: AnalysisCase) {
    if (generatingCaseId) return;
    setGeneratingCaseId(analysis.id);
    setCaseGenError(null);
    try {
      // Pull the same documents already uploaded for this case in New
      // Analysis, so the appeal letter is grounded in the same evidence --
      // not a fresh analysis that's never seen it.
      const report = await getCaseReport(analysis.id);
      const documentIds = report.documents.map((d) => d.document_id);
      const response = await runMultiDomainCase(analysis.id, analysis.summary, true, documentIds);
      const newAppeals = Object.values(response.per_domain_results).flatMap((r) => r.appeals ?? []);
      const updated = await refresh();
      if (newAppeals.length > 0) {
        const firstNew = updated.find((a) => newAppeals.some((n) => n.id === a.id));
        if (firstNew) setSelectedId(firstNew.id);
      } else {
        setCaseGenError("No appeal documents were produced for this case -- it may need more specific facts (dates, amounts, institution name) to draft from.");
      }
    } catch (err) {
      setCaseGenError(err instanceof Error ? err.message : "Something went wrong generating the appeal.");
    } finally {
      setGeneratingCaseId(null);
    }
  }

  useEffect(() => {
    if (genQuery.trim().length < 12) {
      setGenDomains([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setGenDomains((await classifyQuery(genQuery)).candidates);
      } catch {
        setGenDomains([]);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [genQuery]);

  const filtered = useMemo(() => {
    return appeals.filter((appeal) => {
      if (statusFilter !== "all" && appeal.status !== statusFilter) return false;
      if (search && !appeal.title.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [appeals, statusFilter, search]);

  const selected = appeals.find((a) => a.id === selectedId) ?? filtered[0] ?? null;

  async function generate() {
    const query = genQuery.trim();
    if (!query || generating) return;
    setGenerating(true);
    setGenError(null);
    setFilledCount(0);

    let stageIndex = 0;
    stageTimerRef.current = window.setInterval(() => {
      stageIndex = Math.min(stageIndex + 1, ESTIMATED_STAGES.length);
      setFilledCount(stageIndex);
    }, 1300);

    try {
      const caseId = crypto.randomUUID();
      const response = await runMultiDomainCase(caseId, query, true);
      const newAppeals = Object.values(response.per_domain_results).flatMap((r) => r.appeals ?? []);
      const updated = await refresh();
      if (newAppeals.length > 0) {
        const firstNew = updated.find((a) => newAppeals.some((n) => n.id === a.id));
        if (firstNew) setSelectedId(firstNew.id);
      } else {
        setGenError("The assistant didn't produce any appeal documents for this query -- try adding more specific facts (dates, amounts, institution name).");
      }
      setGenQuery("");
      setGenDomains([]);
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "Something went wrong generating the appeal.");
    } finally {
      if (stageTimerRef.current) window.clearInterval(stageTimerRef.current);
      setGenerating(false);
      setFilledCount(0);
    }
  }

  async function changeStatus(appeal: Appeal, status: Appeal["status"]) {
    setAppeals((current) => current.map((a) => (a.id === appeal.id ? { ...a, status } : a)));
    try {
      await updateAppealStatus(appeal.id, status);
    } catch {
      refresh();
    }
  }

  return (
    <div className="flex min-h-[720px] flex-1 flex-col gap-4 xl:flex-row">
      {/* List pane */}
      <div className="flex w-full flex-col rounded-2xl border border-white/10 bg-glass backdrop-blur-2xl xl:w-[380px]">
        <div className="border-b border-white/10 p-4">
          <CaseAppealPicker
            analyses={analyses}
            loading={analysesLoading}
            appeals={appeals}
            generatingCaseId={generatingCaseId}
            onGenerate={generateFromCase}
          />
          {caseGenError && <p className="mt-2 text-xs text-red-200">{caseGenError}</p>}

          <div className="my-3 flex items-center gap-2 text-[10px] uppercase tracking-wide text-proxy-tertiary">
            <span className="h-px flex-1 bg-white/10" /> or describe a new dispute <span className="h-px flex-1 bg-white/10" />
          </div>

          <GenerateBar
            query={genQuery}
            setQuery={setGenQuery}
            onGenerate={generate}
            generating={generating}
            domains={genDomains}
          />
          {generating && (
            <div className="mt-3">
              <ReasoningLanes
                lanes={(genDomains.length ? genDomains.map((d) => d.domain) : ["health_insurance"]).map((domain) => ({ domain }))}
                processing
                filledCount={filledCount}
              />
            </div>
          )}
          {genError && <p className="mt-2 text-xs text-red-200">{genError}</p>}
        </div>

        <div className="flex items-center gap-2 border-b border-white/10 p-3">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-proxy-tertiary" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search appeals..."
              className="w-full rounded-lg border border-white/10 bg-black/30 py-1.5 pl-8 pr-2 text-xs text-proxy-text outline-none placeholder:text-proxy-tertiary focus:border-cyan-300/40"
            />
          </div>
        </div>
        <div className="flex gap-1.5 overflow-x-auto border-b border-white/10 p-2">
          <FilterChip label="All" active={statusFilter === "all"} onClick={() => setStatusFilter("all")} count={appeals.length} />
          {STATUS_ORDER.map((status) => (
            <FilterChip
              key={status}
              label={STATUS_META[status].label}
              active={statusFilter === status}
              onClick={() => setStatusFilter(status)}
              count={appeals.filter((a) => a.status === status).length}
              color={STATUS_META[status].color}
            />
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex h-full items-center justify-center text-proxy-tertiary">
              <Loader2 className="size-5 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
              <Inbox className="size-8 text-proxy-tertiary" />
              <p className="text-xs text-proxy-tertiary">
                {appeals.length === 0 ? "No appeals yet -- generate your first one above." : "No appeals match this filter."}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {filtered.map((appeal) => (
                <AppealRow key={appeal.id} appeal={appeal} active={selected?.id === appeal.id} onClick={() => setSelectedId(appeal.id)} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Detail pane */}
      <div className="flex-1 rounded-2xl border border-white/10 bg-glass backdrop-blur-2xl">
        {selected ? (
          <AppealDocument appeal={selected} onStatusChange={(status) => changeStatus(selected, status)} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-10 text-center">
            <Scale className="size-10 text-proxy-tertiary" />
            <p className="text-sm text-proxy-muted">Select an appeal to view the full document, or generate a new one.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function CaseAppealPicker({
  analyses, loading, appeals, generatingCaseId, onGenerate,
}: {
  analyses: AnalysisCase[];
  loading: boolean;
  appeals: Appeal[];
  generatingCaseId: string | null;
  onGenerate: (analysis: AnalysisCase) => void;
}) {
  const appealCountByCase = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of appeals) counts.set(a.case_id, (counts.get(a.case_id) ?? 0) + 1);
    return counts;
  }, [appeals]);

  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-proxy-muted">
        <FolderOpen className="size-3.5 text-cyan-200" /> Generate from an existing case
      </p>
      <p className="mb-2 text-[10px] leading-4 text-proxy-tertiary">
        Reuses that case&apos;s real summary and uploaded documents from New Analysis -- no retyping.
      </p>
      {loading ? (
        <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 p-3 text-xs text-proxy-tertiary">
          <Loader2 className="size-3.5 animate-spin" /> Loading your analyses...
        </div>
      ) : analyses.length === 0 ? (
        <div className="rounded-lg border border-dashed border-white/10 bg-black/10 p-3 text-center text-[11px] text-proxy-tertiary">
          No analyses yet -- run one in New Analysis first, then generate its appeal here.
        </div>
      ) : (
        <div className="max-h-40 space-y-1.5 overflow-y-auto pr-0.5">
          {analyses.map((analysis) => {
            const theme = domainTheme(analysis.domain);
            const existing = appealCountByCase.get(analysis.id) ?? 0;
            const isGenerating = generatingCaseId === analysis.id;
            return (
              <div
                key={analysis.id}
                className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 p-2"
              >
                <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: theme.color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] font-medium text-proxy-text">{analysis.title || theme.label}</p>
                  <p className="truncate text-[9px] text-proxy-tertiary">
                    {theme.label}
                    {existing > 0 ? ` · ${existing} appeal${existing === 1 ? "" : "s"} already` : ""}
                  </p>
                </div>
                <button
                  onClick={() => onGenerate(analysis)}
                  disabled={generatingCaseId !== null}
                  className="flex shrink-0 items-center gap-1 rounded-md border border-cyan-300/25 bg-cyan-300/10 px-2 py-1 text-[10px] text-cyan-100 hover:bg-cyan-300/15 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {isGenerating ? <Loader2 className="size-3 animate-spin" /> : <Wand2 className="size-3" />}
                  {isGenerating ? "Drafting" : "Generate"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GenerateBar({
  query, setQuery, onGenerate, generating, domains,
}: {
  query: string;
  setQuery: (v: string) => void;
  onGenerate: () => void;
  generating: boolean;
  domains: DomainCandidate[];
}) {
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-proxy-muted">
        <Sparkles className="size-3.5 text-cyan-200" /> Generate a new appeal
      </p>
      <div className="composer-glow flex items-center gap-2 rounded-xl p-[1.5px]">
        <div className="flex w-full items-center gap-2 rounded-xl bg-[#07080b] p-1.5">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onGenerate()}
            placeholder="Describe the dispute -- e.g. flight cancelled, claim rejected..."
            className="flex-1 bg-transparent px-2 py-1.5 text-xs text-proxy-text outline-none placeholder:text-proxy-tertiary"
          />
          <button
            onClick={onGenerate}
            disabled={generating || !query.trim()}
            className="orb-send grid size-7 shrink-0 place-items-center rounded-full text-black disabled:cursor-not-allowed disabled:opacity-40"
          >
            {generating ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          </button>
        </div>
      </div>
      {domains.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {domains.map((d) => {
            const theme = domainTheme(d.domain);
            return (
              <span key={d.domain} className="rounded-full border px-1.5 py-0.5 text-[9px]" style={{ borderColor: `${theme.color}40`, color: theme.color }}>
                {theme.label}
              </span>
            );
          })}
        </div>
      )}
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
        .orb-send {
          background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0);
        }
      `}</style>
    </div>
  );
}

function FilterChip({ label, active, onClick, count, color }: { label: string; active: boolean; onClick: () => void; count: number; color?: string }) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] transition-colors ${
        active ? "border-cyan-300/40 bg-cyan-300/15 text-cyan-100" : "border-white/10 text-proxy-tertiary hover:border-white/20"
      }`}
      style={active && color ? { borderColor: `${color}50`, backgroundColor: `${color}1a`, color } : undefined}
    >
      {label} <span className="opacity-60">{count}</span>
    </button>
  );
}

function AppealRow({ appeal, active, onClick }: { appeal: Appeal; active: boolean; onClick: () => void }) {
  const docMeta = DOC_TYPE_META[appeal.document_type] ?? DOC_TYPE_META.appeal_letter;
  const statusMeta = STATUS_META[appeal.status];
  const theme = domainTheme(appeal.domain ?? "");
  const Icon = docMeta.icon;

  return (
    <button
      onClick={onClick}
      className={`flex w-full items-start gap-2.5 rounded-xl border p-2.5 text-left transition-colors ${
        active ? "border-cyan-300/30 bg-cyan-300/[0.06]" : "border-transparent hover:bg-white/[0.03]"
      }`}
    >
      <div className="grid size-8 shrink-0 place-items-center rounded-lg border" style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a` }}>
        <Icon className="size-3.5" style={{ color: theme.color }} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-proxy-text">{appeal.title}</p>
        <div className="mt-1 flex items-center gap-1.5">
          <span className="rounded-full px-1.5 py-0.5 text-[9px]" style={{ backgroundColor: `${statusMeta.color}1a`, color: statusMeta.color }}>
            {statusMeta.label}
          </span>
          <span className="text-[10px] text-proxy-tertiary">v{appeal.version} &middot; {timeAgo(appeal.created_at)}</span>
        </div>
      </div>
      <ChevronRight className={`mt-1.5 size-3.5 shrink-0 text-proxy-tertiary transition-opacity ${active ? "opacity-100" : "opacity-0"}`} />
    </button>
  );
}

function AppealDocument({ appeal, onStatusChange }: { appeal: Appeal; onStatusChange: (status: Appeal["status"]) => void }) {
  const [copied, setCopied] = useState(false);
  const docMeta = DOC_TYPE_META[appeal.document_type] ?? DOC_TYPE_META.appeal_letter;
  const theme = domainTheme(appeal.domain ?? "");
  const Icon = docMeta.icon;

  function copy() {
    navigator.clipboard.writeText(appeal.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  function download() {
    const blob = new Blob([appeal.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${appeal.document_type}-v${appeal.version}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-xl border" style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a` }}>
            <Icon className="size-4.5" style={{ color: theme.color }} />
          </div>
          <div>
            <p className="text-sm font-semibold text-proxy-text">{docMeta.label}</p>
            <p className="text-[11px] text-proxy-tertiary">
              {theme.label} &middot; v{appeal.version} &middot; {timeAgo(appeal.created_at)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusSelector status={appeal.status} onChange={onStatusChange} />
          <button onClick={copy} className="grid size-8 place-items-center rounded-lg border border-white/10 text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100">
            {copied ? <Check className="size-3.5 text-green-300" /> : <Copy className="size-3.5" />}
          </button>
          <button onClick={download} className="grid size-8 place-items-center rounded-lg border border-white/10 text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100">
            <Download className="size-3.5" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-2xl rounded-xl border border-white/5 bg-black/20 p-6" style={{ borderTop: `3px solid ${theme.color}` }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {appeal.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

function StatusSelector({ status, onChange }: { status: Appeal["status"]; onChange: (status: Appeal["status"]) => void }) {
  return (
    <select
      value={status}
      onChange={(e) => onChange(e.target.value as Appeal["status"])}
      className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-proxy-text outline-none focus:border-cyan-300/40"
      style={{ color: STATUS_META[status].color }}
    >
      {STATUS_ORDER.map((s) => (
        <option key={s} value={s} className="bg-[#0a0b0f] text-proxy-text">
          {STATUS_META[s].label}
        </option>
      ))}
    </select>
  );
}
