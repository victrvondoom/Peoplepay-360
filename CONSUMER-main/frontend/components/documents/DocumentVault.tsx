"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Upload, FileText, Search, Grid3X3, List, Download, Trash2, X, Loader2,
  CheckCircle2, AlertCircle, Clock, FileWarning, ExternalLink,
} from "lucide-react";
import {
  listDocuments, uploadDocument, deleteDocument, getDocumentSignedUrl, type VaultDocument,
} from "@/lib/api-client";
import { DOMAIN_THEME, domainTheme } from "@/components/chat/domain-theme";

const DOC_TYPE_LABELS: Record<string, string> = {
  policy: "Policy",
  medical_report: "Medical Record",
  rejection_letter: "Rejection Letter",
  bill: "Bill / Invoice",
  other: "Other",
};

function formatSize(bytes: number): string {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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

interface PendingUpload {
  id: string;
  filename: string;
  progress: number;
  error?: string;
}

export function DocumentVault() {
  const [documents, setDocuments] = useState<VaultDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [uploadDomain, setUploadDomain] = useState<string>("health_insurance");
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [selected, setSelected] = useState<VaultDocument | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setDocuments(await listDocuments());
    } catch {
      // keep whatever we last had rather than blanking the list on a transient failure
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      for (const file of list) {
        const pendingId = crypto.randomUUID();
        setPendingUploads((current) => [...current, { id: pendingId, filename: file.name, progress: 0 }]);
        try {
          await uploadDocument(uploadDomain, file, {
            onProgress: (percent) =>
              setPendingUploads((current) => current.map((p) => (p.id === pendingId ? { ...p, progress: percent } : p))),
          });
          setPendingUploads((current) => current.filter((p) => p.id !== pendingId));
          refresh();
        } catch (err) {
          setPendingUploads((current) =>
            current.map((p) => (p.id === pendingId ? { ...p, error: err instanceof Error ? err.message : "Upload failed" } : p))
          );
          window.setTimeout(() => setPendingUploads((current) => current.filter((p) => p.id !== pendingId)), 4000);
        }
      }
    },
    [uploadDomain]
  );

  async function handleDelete(document: VaultDocument) {
    setDocuments((current) => current.filter((d) => d.id !== document.id));
    if (selected?.id === document.id) setSelected(null);
    try {
      await deleteDocument(document.id);
    } catch {
      refresh();
    }
  }

  const filtered = useMemo(() => {
    return documents.filter((doc) => {
      if (search && !doc.filename.toLowerCase().includes(search.toLowerCase())) return false;
      if (domainFilter !== "all" && doc.domain !== domainFilter) return false;
      if (typeFilter !== "all" && doc.document_type !== typeFilter) return false;
      return true;
    });
  }, [documents, search, domainFilter, typeFilter]);

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
        <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center rounded-2xl border-2 border-dashed border-cyan-300/60 bg-cyan-300/5 backdrop-blur-sm">
          <div className="text-center">
            <Upload className="mx-auto mb-2 size-10 text-cyan-200" />
            <p className="text-sm font-medium text-cyan-100">Drop to upload</p>
          </div>
        </div>
      )}

      <UploadBar
        uploadDomain={uploadDomain}
        setUploadDomain={setUploadDomain}
        onPick={() => fileInputRef.current?.click()}
        pendingUploads={pendingUploads}
      />
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.csv,.json,image/*"
        className="hidden"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
      />

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-glass p-3 backdrop-blur-2xl">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-proxy-tertiary" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents..."
            className="w-full rounded-lg border border-white/10 bg-black/30 py-1.5 pl-8 pr-2 text-xs text-proxy-text outline-none placeholder:text-proxy-tertiary focus:border-cyan-300/40"
          />
        </div>
        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-proxy-text outline-none"
        >
          <option value="all">All domains</option>
          {Object.entries(DOMAIN_THEME).map(([key, theme]) => (
            <option key={key} value={key}>{theme.label}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-proxy-text outline-none"
        >
          <option value="all">All types</option>
          {Object.entries(DOC_TYPE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <span className="ml-auto text-xs text-proxy-tertiary">{filtered.length} document{filtered.length === 1 ? "" : "s"}</span>
      </div>

      <div className="flex flex-1 gap-4">
        <div className="flex-1">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-proxy-tertiary">
              <Loader2 className="size-6 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex h-60 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/10 text-center">
              <FileText className="size-8 text-proxy-tertiary" />
              <p className="text-sm text-proxy-tertiary">
                {documents.length === 0 ? "No documents yet -- drag files anywhere on this page to upload." : "No documents match your filters."}
              </p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} onOpen={() => setSelected(doc)} onDelete={() => handleDelete(doc)} />
              ))}
            </div>
          )}
        </div>

        {selected && <DocumentDetail doc={selected} onClose={() => setSelected(null)} onDelete={() => handleDelete(selected)} />}
      </div>
    </div>
  );
}

function UploadBar({
  uploadDomain, setUploadDomain, onPick, pendingUploads,
}: {
  uploadDomain: string;
  setUploadDomain: (v: string) => void;
  onPick: () => void;
  pendingUploads: PendingUpload[];
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onPick}
          className="upload-orb inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-black"
        >
          <Upload className="size-4" /> Upload Documents
        </button>
        <select
          value={uploadDomain}
          onChange={(e) => setUploadDomain(e.target.value)}
          className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-proxy-text outline-none"
        >
          {Object.entries(DOMAIN_THEME).map(([key, theme]) => (
            <option key={key} value={key}>{theme.label}</option>
          ))}
        </select>
        <p className="text-xs text-proxy-tertiary">PDF, text, or images -- up to 10MB. Or drag &amp; drop anywhere.</p>
      </div>

      {pendingUploads.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {pendingUploads.map((upload) => (
            <div key={upload.id} className="rounded-lg border border-white/10 bg-black/20 p-2">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="truncate text-proxy-text">{upload.filename}</span>
                {upload.error ? (
                  <span className="flex items-center gap-1 text-red-200"><AlertCircle className="size-3" /> Failed</span>
                ) : (
                  <span className="text-proxy-tertiary">{upload.progress}%</span>
                )}
              </div>
              {!upload.error && (
                <div className="h-1 overflow-hidden rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-cyan-300 transition-all" style={{ width: `${upload.progress}%` }} />
                </div>
              )}
              {upload.error && <p className="text-[10px] text-red-300">{upload.error}</p>}
            </div>
          ))}
        </div>
      )}
      <style jsx>{`
        .upload-orb {
          background: radial-gradient(circle at 30% 30%, #5cf5ff, #00b8d9 55%, #6a3df0);
          box-shadow: 0 0 18px rgba(0, 229, 255, 0.35);
        }
      `}</style>
    </div>
  );
}

function DocumentCard({ doc, onOpen, onDelete }: { doc: VaultDocument; onOpen: () => void; onDelete: () => void }) {
  const theme = domainTheme(doc.domain ?? "");
  return (
    <div className="group rounded-2xl border border-white/10 bg-glass p-4 backdrop-blur-2xl transition-colors hover:border-cyan-300/25">
      <div className="mb-3 flex items-start justify-between">
        <div className="grid size-11 place-items-center rounded-xl border" style={{ borderColor: `${theme.color}35`, backgroundColor: `${theme.color}15` }}>
          <FileText className="size-5" style={{ color: theme.color }} />
        </div>
        <button onClick={onDelete} className="rounded-lg border border-white/10 p-1.5 text-proxy-muted opacity-0 transition-opacity hover:border-red-300/30 hover:text-red-200 group-hover:opacity-100">
          <Trash2 className="size-3.5" />
        </button>
      </div>
      <button onClick={onOpen} className="text-left">
        <p className="line-clamp-1 text-sm font-medium text-proxy-text">{doc.filename}</p>
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ backgroundColor: `${theme.color}1a`, color: theme.color }}>
          {theme.label}
        </span>
        <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-proxy-tertiary">
          {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}
        </span>
      </div>
      <div className="mt-3 flex items-center justify-between text-[11px] text-proxy-tertiary">
        <span className="flex items-center gap-1"><Clock className="size-3" />{timeAgo(doc.created_at)}</span>
        <span>{formatSize(doc.size_bytes)}</span>
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-3">
        {doc.indexed ? (
          <span className="flex items-center gap-1 text-[11px] text-green-300"><CheckCircle2 className="size-3" /> Indexed &middot; {doc.chunks_indexed} chunks</span>
        ) : (
          <span className="flex items-center gap-1 text-[11px] text-amber-300"><FileWarning className="size-3" /> Not indexed</span>
        )}
        <button onClick={onOpen} className="text-[11px] text-cyan-200 hover:text-cyan-100">View &rarr;</button>
      </div>
    </div>
  );
}

function DocumentDetail({ doc, onClose, onDelete }: { doc: VaultDocument; onClose: () => void; onDelete: () => void }) {
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const theme = domainTheme(doc.domain ?? "");

  async function handleDownload() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const url = await getDocumentSignedUrl(doc.case_id, doc.document_id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      setDownloadError("Original file storage isn't available in this environment -- showing the extracted text instead.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex w-full max-w-md flex-col rounded-2xl border border-white/10 bg-glass backdrop-blur-2xl xl:w-[420px]">
      <div className="flex items-center justify-between border-b border-white/10 p-4" style={{ borderTop: `3px solid ${theme.color}`, borderTopLeftRadius: "1rem", borderTopRightRadius: "1rem" }}>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-proxy-text">{doc.filename}</p>
          <p className="text-[11px] text-proxy-tertiary">{theme.label} &middot; {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}</p>
        </div>
        <button onClick={onClose} className="rounded-lg border border-white/10 p-1.5 text-proxy-muted hover:text-proxy-text">
          <X className="size-4" />
        </button>
      </div>

      <div className="flex items-center gap-2 border-b border-white/10 p-3">
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-proxy-muted hover:border-cyan-300/30 hover:text-cyan-100"
        >
          {downloading ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />} Download original
        </button>
        <button
          onClick={onDelete}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-proxy-muted hover:border-red-300/30 hover:text-red-200"
        >
          <Trash2 className="size-3.5" /> Delete
        </button>
      </div>
      {downloadError && (
        <p className="border-b border-white/10 px-4 py-2 text-[11px] text-amber-200">{downloadError}</p>
      )}

      <div className="flex-1 overflow-y-auto p-4">
        <p className="mb-2 text-[10px] uppercase tracking-[0.16em] text-proxy-tertiary">Extracted content</p>
        {doc.text_extract ? (
          <pre className="whitespace-pre-wrap break-words rounded-xl border border-white/5 bg-black/20 p-3 text-xs leading-6 text-proxy-text">
            {doc.text_extract}
          </pre>
        ) : (
          <p className="text-xs text-proxy-tertiary">No text could be extracted from this file. Try a clearer scan/photo, or upload a text-based PDF.</p>
        )}
      </div>
    </div>
  );
}
