"use client";

import { useEffect, useMemo, useState } from "react";
import {
  FileStack, Scale, FileText, TrendingUp, Loader2, Activity, ChevronRight,
  FileCheck2, Upload, ArrowUpCircle, CheckCircle2, PenLine,
} from "lucide-react";
import { getReportSummary, getCaseReport, type ReportSummary, type CaseReportData } from "@/lib/api-client";
import { DomainDonutChart } from "./DomainDonutChart";
import { CaseReportView } from "./CaseReportView";

const STATUS_COLORS: Record<string, string> = {
  draft: "#a8b3c7",
  sent: "#00e5ff",
  escalated: "#ffc857",
  resolved: "#37f29a",
  intake: "#a8b3c7",
  analyzing: "#00e5ff",
  review_required: "#ffc857",
  ready_for_approval: "#9b5cff",
  submitted: "#37f29a",
};

const EVENT_ICON: Record<string, typeof Activity> = {
  case_created: PenLine,
  document_uploaded: Upload,
  appeal_drafted: FileCheck2,
  appeal_status_changed: ArrowUpCircle,
  agent_run: Activity,
};

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ReportsDashboard() {
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [openCaseId, setOpenCaseId] = useState<string | null>(null);
  const [caseReport, setCaseReport] = useState<CaseReportData | null>(null);
  const [caseLoading, setCaseLoading] = useState(false);

  useEffect(() => {
    getReportSummary()
      .then(setSummary)
      .finally(() => setLoading(false));
  }, []);

  const recentCases = useMemo(() => {
    if (!summary) return [];
    const seen = new Map<string, { case_id: string; title: string; latest: string | null }>();
    for (const event of summary.recent_activity) {
      if (!seen.has(event.case_id)) {
        seen.set(event.case_id, { case_id: event.case_id, title: event.title, latest: event.created_at });
      }
    }
    return Array.from(seen.values()).slice(0, 6);
  }, [summary]);

  async function openCase(caseId: string) {
    setOpenCaseId(caseId);
    setCaseLoading(true);
    try {
      setCaseReport(await getCaseReport(caseId));
    } finally {
      setCaseLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="size-6 animate-spin text-cyan-200" />
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="rounded-2xl border border-red-300/20 bg-red-300/5 p-6 text-center text-sm text-red-200">
        Couldn't load your reports. Is the backend running?
      </div>
    );
  }

  const hasActivity = summary.totals.cases + summary.totals.appeals + summary.totals.documents > 0;

  return (
    <div className="flex flex-1 flex-col gap-4">
      {/* KPI row */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard icon={FileStack} label="Cases" value={summary.totals.cases} accent="#00e5ff" />
        <KpiCard icon={Scale} label="Appeals Generated" value={summary.totals.appeals} accent="#9b5cff" />
        <KpiCard icon={FileText} label="Documents" value={summary.totals.documents} accent="#37f29a" />
        <KpiCard
          icon={TrendingUp}
          label="Resolution Rate"
          value={summary.resolution_rate !== null ? `${Math.round(summary.resolution_rate * 100)}%` : "-"}
          accent="#ffc857"
        />
      </div>

      {!hasActivity ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1fr_1fr_1.1fr]">
          {/* Domain distribution */}
          <div className="rounded-2xl border border-white/10 bg-glass p-5 backdrop-blur-2xl">
            <p className="mb-4 text-xs font-medium uppercase tracking-[0.16em] text-proxy-tertiary">Domain Distribution</p>
            <DomainDonutChart data={summary.domain_breakdown} />
          </div>

          {/* Appeal status breakdown */}
          <div className="rounded-2xl border border-white/10 bg-glass p-5 backdrop-blur-2xl">
            <p className="mb-4 text-xs font-medium uppercase tracking-[0.16em] text-proxy-tertiary">Appeal Pipeline</p>
            <StatusFunnel breakdown={summary.appeal_status_breakdown} total={summary.totals.appeals} />
          </div>

          {/* Activity timeline */}
          <div className="rounded-2xl border border-white/10 bg-glass p-5 backdrop-blur-2xl">
            <p className="mb-4 text-xs font-medium uppercase tracking-[0.16em] text-proxy-tertiary">Recent Activity</p>
            <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
              {summary.recent_activity.length === 0 ? (
                <p className="text-xs text-proxy-tertiary">No activity yet.</p>
              ) : (
                summary.recent_activity.map((event) => {
                  const Icon = EVENT_ICON[event.event_type] ?? Activity;
                  return (
                    <div key={event.id} className="flex items-start gap-2.5">
                      <div className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border border-white/10 bg-black/30">
                        <Icon className="size-3 text-cyan-200" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs text-proxy-text">{event.title}</p>
                        <p className="text-[10px] text-proxy-tertiary">{event.actor} &middot; {timeAgo(event.created_at)}</p>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* Case reports */}
      {recentCases.length > 0 && (
        <div className="rounded-2xl border border-white/10 bg-glass p-5 backdrop-blur-2xl">
          <p className="mb-3 text-xs font-medium uppercase tracking-[0.16em] text-proxy-tertiary">Generate a Case Report</p>
          <div className="space-y-1.5">
            {recentCases.map((c) => (
              <button
                key={c.case_id}
                onClick={() => openCase(c.case_id)}
                className="flex w-full items-center gap-3 rounded-xl border border-white/10 p-3 text-left transition-colors hover:border-cyan-300/30 hover:bg-cyan-300/[0.04]"
              >
                <div className="grid size-8 shrink-0 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-300/10">
                  <FileText className="size-3.5 text-cyan-200" />
                </div>
                <span className="min-w-0 flex-1 truncate text-xs text-proxy-text">{c.title}</span>
                <span className="shrink-0 text-[10px] text-proxy-tertiary">{timeAgo(c.latest)}</span>
                <ChevronRight className="size-3.5 shrink-0 text-proxy-tertiary" />
              </button>
            ))}
          </div>
        </div>
      )}

      {openCaseId && caseLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <Loader2 className="size-6 animate-spin text-cyan-200" />
        </div>
      )}
      {openCaseId && caseReport && !caseLoading && (
        <CaseReportView
          data={caseReport}
          onClose={() => {
            setOpenCaseId(null);
            setCaseReport(null);
          }}
        />
      )}
    </div>
  );
}

function KpiCard({ icon: Icon, label, value, accent }: { icon: typeof FileStack; label: string; value: number | string; accent: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl">
      <div className="mb-3 grid size-9 place-items-center rounded-xl border" style={{ borderColor: `${accent}40`, backgroundColor: `${accent}15` }}>
        <Icon className="size-4" style={{ color: accent }} />
      </div>
      <p className="text-2xl font-semibold text-proxy-text">{value}</p>
      <p className="text-xs text-proxy-tertiary">{label}</p>
    </div>
  );
}

function StatusFunnel({ breakdown, total }: { breakdown: Array<{ status: string; count: number }>; total: number }) {
  if (total === 0) {
    return <p className="text-xs text-proxy-tertiary">No appeals generated yet.</p>;
  }
  const order = ["draft", "sent", "escalated", "resolved"];
  const map = new Map(breakdown.map((b) => [b.status, b.count]));
  return (
    <div className="space-y-3">
      {order.map((status) => {
        const count = map.get(status) ?? 0;
        const pct = total ? (count / total) * 100 : 0;
        const color = STATUS_COLORS[status] ?? "#a8b3c7";
        return (
          <div key={status}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="capitalize text-proxy-muted">{status}</span>
              <span className="text-proxy-text">{count}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/5">
              <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-white/10 py-16 text-center">
      <CheckCircle2 className="size-8 text-proxy-tertiary" />
      <p className="text-sm text-proxy-muted">No activity yet.</p>
      <p className="max-w-sm text-xs text-proxy-tertiary">
        Reports build automatically from your cases, generated appeals, and uploaded documents -- start a
        conversation in the AI Assistant or upload a document to see your first report.
      </p>
    </div>
  );
}
