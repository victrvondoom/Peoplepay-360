"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Printer, X, FileText, ShieldCheck } from "lucide-react";
import type { CaseReportData } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { markdownComponents } from "@/components/chat/markdown-components";

export function CaseReportView({ data, onClose }: { data: CaseReportData; onClose: () => void }) {
  const theme = domainTheme(data.case?.domain ?? "");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 print:static print:bg-transparent print:p-0" onClick={onClose}>
      <div
        className="report-sheet flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#0a0b10] print:max-h-none print:w-auto print:rounded-none print:border-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 p-4 print:hidden">
          <p className="text-sm font-semibold text-proxy-text">Case Report Preview</p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-300/30 bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-100 hover:bg-cyan-300/20"
            >
              <Printer className="size-3.5" /> Print / Save as PDF
            </button>
            <button onClick={onClose} className="rounded-lg border border-white/10 p-1.5 text-proxy-muted hover:text-proxy-text">
              <X className="size-4" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto p-8 print:overflow-visible" id="case-report-printable">
          {/* Letterhead */}
          <div className="mb-6 flex items-center justify-between border-b pb-4" style={{ borderColor: theme.color }}>
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-proxy-tertiary print:text-black">PROXY Case Report</p>
              <h1 className="mt-1 text-2xl font-semibold text-proxy-text print:text-black">{data.case?.title ?? "Untitled case"}</h1>
            </div>
            <span
              className="rounded-full border px-3 py-1 text-xs font-medium print:border-black print:text-black"
              style={{ borderColor: `${theme.color}60`, color: theme.color }}
            >
              {theme.label}
            </span>
          </div>

          {/* Case meta */}
          <div className="mb-6 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <Meta label="Institution" value={data.case?.institution_name ?? "-"} />
            <Meta label="Status" value={data.case?.status ?? "-"} />
            <Meta label="Appeals filed" value={String(data.appeals.length)} />
            <Meta label="Documents" value={String(data.documents.length)} />
          </div>

          {data.case?.summary && (
            <Section title="Summary">
              <p className="text-sm leading-6 text-proxy-muted print:text-black">{data.case.summary}</p>
            </Section>
          )}

          {data.documents.length > 0 && (
            <Section title="Evidence Documents">
              <div className="space-y-2">
                {data.documents.map((doc) => (
                  <div key={doc.id} className="flex items-center gap-2 rounded-lg border border-white/10 p-2.5 text-xs print:border-black">
                    <FileText className="size-3.5 shrink-0 text-proxy-tertiary print:text-black" />
                    <span className="flex-1 text-proxy-text print:text-black">{doc.filename}</span>
                    <span className="text-proxy-tertiary print:text-black">{doc.document_type}</span>
                    {doc.indexed && <ShieldCheck className="size-3.5 text-green-300 print:text-black" />}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {data.appeals.length > 0 && (
            <Section title="Generated Documents">
              <div className="space-y-4">
                {data.appeals.map((appeal) => (
                  <div key={appeal.id} className="rounded-xl border border-white/10 p-4 print:break-inside-avoid print:border-black">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-cyan-100 print:text-black">
                      {appeal.title} <span className="font-normal text-proxy-tertiary print:text-black">v{appeal.version} &middot; {appeal.status}</span>
                    </p>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                      {appeal.content}
                    </ReactMarkdown>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {data.events.length > 0 && (
            <Section title="Timeline">
              <div className="space-y-1.5">
                {data.events.map((event) => (
                  <div key={event.id} className="flex items-center gap-2 text-xs text-proxy-tertiary print:text-black">
                    <span className="size-1.5 rounded-full bg-cyan-300 print:bg-black" />
                    <span className="text-proxy-text print:text-black">{event.title}</span>
                    <span>&middot; {event.actor}</span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          <p className="mt-8 border-t border-white/10 pt-3 text-[10px] text-proxy-tertiary print:border-black print:text-black">
            Generated by PROXY on {new Date().toLocaleString()}. Educational/informational -- verify all facts before submitting to any institution.
          </p>
        </div>
      </div>
      <style jsx global>{`
        @media print {
          body * { visibility: hidden; }
          #case-report-printable, #case-report-printable * { visibility: visible; }
          #case-report-printable { position: absolute; left: 0; top: 0; width: 100%; }
        }
      `}</style>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-proxy-tertiary print:text-black">{label}</p>
      <p className="text-sm font-medium text-proxy-text print:text-black">{value}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-proxy-tertiary print:text-black">{title}</p>
      {children}
    </div>
  );
}
