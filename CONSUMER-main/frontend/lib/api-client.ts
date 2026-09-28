// api-client.ts — all methods backed by real FastAPI endpoints, no mock fallbacks.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// No real login flow is wired up yet, so there's no session token to attach.
// The backend's dev-mode auth (app/auth/dependencies.py) accepts any bearer
// string as a stand-in user id when ENVIRONMENT=development and no Supabase
// JWT secret is configured -- persist a stable per-browser id so requests
// authenticate consistently instead of getting a fresh identity every call.
// Exported so isolated feature folders (e.g. features/knowledge-graph) can
// build their own fetch helpers against the SAME persisted device identity
// instead of minting a second one under a different localStorage key.
export function getDeviceUserId(): string {
  if (typeof window === "undefined") return "server";
  const key = "proxy:device-user-id";
  let id = window.localStorage.getItem(key);
  if (!id) {
    id = `device-${crypto.randomUUID()}`;
    window.localStorage.setItem(key, id);
  }
  return id;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getDeviceUserId()}`,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

// Legacy helper kept for any old AnalysisWidgets that pass an Analysis id.
// Routes to the real /case/{id} backend endpoint.
export async function getAnalysis(id: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/case/${id}`);
}

export async function runAnalysis(id: string) {
  return request("/case/analyze", { method: "POST", body: JSON.stringify({ case_id: id }) });
}

export interface ChatCitation {
  title: string;
  authority: string;
  url?: string | null;
  retrieved_chunk: string;
  confidence?: number;
}

export interface ChatResponse {
  answer: string;
  question?: string;
  citations?: string[];
  structured_citations?: ChatCitation[];
  graph_patterns?: Array<{ pattern: string; confidence?: number }>;
  agent_trace?: string[];
}

// Chat about a specific case — runs a fresh Qdrant + Neo4j lookup scoped to
// the actual question asked (not just the original case's initial
// research), so a follow-up outside that original scope is still grounded
// in real retrieved evidence instead of falling back to a generic reply.
export async function askAI(caseId: string, message: string): Promise<ChatResponse> {
  return request<ChatResponse>("/case/chat", {
    method: "POST",
    body: JSON.stringify({ case_id: caseId, message }),
  });
}

export interface DomainCandidate {
  domain: string;
  confidence: number;
  matched_terms: string[];
  fallback?: boolean;
}

export interface Citation {
  title: string;
  authority: string;
  url: string | null;
  publication_date: string | null;
  section: string | null;
  domain: string;
  retrieved_chunk: string;
  confidence: number;
}

export interface GlobalSearchResult {
  id: string;
  score: number;
  text: string;
  domain: string;
  metadata: Record<string, unknown>;
  evidence_scores: {
    similarity_score: number;
    authority_score: number;
    legal_weight: number;
    freshness_score: number;
    confidence: number;
    overall_evidence_score: number;
  };
}

export interface GlobalSearchResponse {
  query: string;
  domains_searched: string[];
  results: GlobalSearchResult[];
  total_hits: number;
}

export async function classifyQuery(query: string): Promise<{ query: string; candidates: DomainCandidate[] }> {
  const result = await request<{ query: string; candidates: DomainCandidate[] }>("/intelligence/classify", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
  // The backend returns a single fallback candidate (confidence 0, marked
  // fallback:true) when nothing actually matched, instead of no candidates
  // -- so downstream code that always needs a domain to run against (the
  // multi-domain workflow) has one. That's not a real detection though, so
  // strip it here rather than let every caller show it as one.
  return { ...result, candidates: result.candidates.filter((c) => !c.fallback) };
}

export async function globalSearch(query: string, topKOverall = 15): Promise<GlobalSearchResponse> {
  return request("/intelligence/search", {
    method: "POST",
    body: JSON.stringify({ query, top_k_overall: topKOverall }),
  });
}

export interface Appeal {
  id: string;
  case_id: string;
  user_id: string;
  version: number;
  title: string;
  content: string;
  status: "draft" | "sent" | "escalated" | "resolved";
  document_type: string;
  domain: string | null;
  created_at: string;
}

export interface ResearchAgentOutput {
  applicable_clauses?: string[];
  possible_exclusions?: string[];
  waiting_periods?: string[];
  regulations?: string[];
  // Subset of `regulations` that couldn't be confirmed word-for-word in the
  // actual retrieved source text -- see backend app/services/
  // citation_verification.py. A real regulation phrased differently than
  // the source isn't necessarily wrong, but it's flagged rather than shown
  // with the same unearned confidence as a directly-grounded citation.
  unverified_regulations?: string[];
  summary?: string;
  confidence?: number;
}

// Evidence field names vary per domain (diagnosis/hospital for health
// insurance, transaction_date/dispute_type for banking, flight_number for
// airlines, etc. -- see backend app/prompts/domain_profiles.py), so this is
// intentionally a loose record rather than a fixed shape.
export type EvidenceAgentOutput = Record<string, string | string[] | boolean | undefined> & {
  // False when the Evidence Agent decided the uploaded document(s) don't
  // actually relate to this case -- undefined means either no documents
  // were uploaded, or the model didn't return the field (treat as unknown,
  // not as a false "unrelated" claim).
  evidence_relevant?: boolean;
  documents_missing?: string[];
  key_dates?: string[];
  summary?: string;
};

export interface KnowledgeGraphAgentOutput {
  patterns: Array<{ pattern: string; domain: string; institution: string; confidence: number }>;
}

export interface StrategyAgentOutput {
  can_appeal?: string;
  success_probability?: number;
  recommended_strategy?: string | string[];
  evidence_required?: string[];
  escalation_path?: string[];
  summary?: string;
}

export interface NegotiationAgentOutput {
  appeal_letter?: string;
  complaint_email?: string;
  escalation_note?: string;
  consumer_complaint?: string;
  summary?: string;
}

export interface ReviewAgentOutput {
  missing_evidence?: string[];
  hallucination_risks?: string[];
  wrong_clause_risks?: string[];
  weak_arguments?: string[];
  approval_ready?: boolean;
  summary?: string;
}

export interface AgentBreakdown {
  research: ResearchAgentOutput;
  evidence: EvidenceAgentOutput;
  knowledge_graph: KnowledgeGraphAgentOutput;
  strategy: StrategyAgentOutput;
  negotiation: NegotiationAgentOutput;
  review: ReviewAgentOutput;
  // Every review pass in order (not just the final one) -- pass 1's flagged
  // issues plus proof the retry actually resolved them, not just the
  // already-clean end state.
  review_history?: ReviewAgentOutput[];
  review_retry_count?: number;
}

export interface DomainResult {
  confidence: number;
  route: string;
  final_report: string | null;
  agent_trace: string[];
  appeals: Appeal[];
  agent_breakdown: AgentBreakdown;
}

export interface MultiDomainCaseResponse {
  query: string;
  domains_analyzed: string[];
  primary_domain: string;
  per_domain_results: Record<string, DomainResult>;
  combined_citations: Citation[];
  combined_summary: string;
}

export interface InstitutionRadarEntry {
  institution_name: string;
  total_cases: number;
  by_domain: Array<{ domain: string; case_count: number }>;
}

// Aggregate, cross-citizen dispute volume per institution across every
// domain -- real graph data (no separate tracking system), not a mock.
export async function getInstitutionRadar(limit = 25): Promise<InstitutionRadarEntry[]> {
  return request(`/graph/institution-radar?limit=${limit}`);
}

export async function runMultiDomainCase(
  caseId: string, message: string, generateAppeals = false, documentIds: string[] = []
): Promise<MultiDomainCaseResponse> {
  return request("/intelligence/cases/multi-domain", {
    method: "POST",
    body: JSON.stringify({ case_id: caseId, case_summary: message, generate_appeals: generateAppeals, document_ids: documentIds }),
  });
}

export async function listAppeals(): Promise<Appeal[]> {
  return request("/appeals", { method: "GET" });
}

export async function updateAppealStatus(appealId: string, status: Appeal["status"]): Promise<Appeal> {
  return request(`/appeals/${appealId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export interface VaultDocument {
  id: string;
  document_id: string;
  case_id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  text_extract: string;
  document_type: string;
  domain: string | null;
  indexed: boolean;
  chunks_indexed: number;
  created_at: string;
}

export async function listDocuments(): Promise<VaultDocument[]> {
  return request("/upload/documents", { method: "GET" });
}

export async function deleteDocument(documentId: string): Promise<void> {
  await request(`/upload/documents/${documentId}`, { method: "DELETE" });
}

export async function getDocumentSignedUrl(caseId: string, documentId: string): Promise<string> {
  const result = await request<{ signed_url: string }>(`/upload/${caseId}/documents/${documentId}/signed-url`, { method: "GET" });
  return result.signed_url;
}

export interface UploadProgressHandlers {
  onProgress?: (percent: number) => void;
}

// Matches backend DocumentUploadResponse (app/schemas/knowledge.py) exactly
// -- FastAPI's response_model strips every field not declared there (id,
// user_id, mime_type, size_bytes, text_extract, document_type, domain,
// chunks_indexed, created_at all get dropped), so this is NOT a VaultDocument
// despite the upload endpoint operating on one internally. Callers that need
// the full record must re-fetch via listDocuments().
export interface UploadedDocument {
  document_id: string;
  case_id: string;
  filename: string;
  storage_path: string;
  indexed: boolean;
  extraction_method?: string;
  ocr_applied?: boolean;
  pages_ocrd?: number;
  text_chars?: number;
  text_preview?: string;
  relevance_warning?: string | null;
}

// Uses XMLHttpRequest instead of fetch() so upload progress is observable --
// fetch's request-body progress isn't exposed in a way that works reliably
// across browsers yet. Deliberately bypasses request()'s JSON Content-Type
// default (must NOT be set for multipart/form-data -- the browser sets the
// boundary itself), but still attaches the same bearer auth.
export async function uploadDocument(domain: string, file: File, handlers?: UploadProgressHandlers): Promise<UploadedDocument> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/upload/vault/${domain}`);
    xhr.setRequestHeader("Authorization", `Bearer ${getDeviceUserId()}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && handlers?.onProgress) {
        handlers.onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`Upload failed: ${xhr.status} ${xhr.responseText}`));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed: network error"));
    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  });
}

export interface ReportSummary {
  totals: { cases: number; appeals: number; documents: number; domains_engaged: number };
  resolution_rate: number | null;
  domain_breakdown: Array<{ domain: string; count: number }>;
  appeal_status_breakdown: Array<{ status: string; count: number }>;
  case_status_breakdown: Array<{ status: string; count: number }>;
  recent_activity: Array<{
    id: string;
    case_id: string;
    event_type: string;
    title: string;
    body: string | null;
    actor: string;
    created_at: string | null;
  }>;
  generated_at: string;
}

export interface LatestAnalysis {
  research_summary: string;
  evidence_summary: string;
  strategy: string;
  appeal_draft: string;
  final_report: string;
  review_notes: string[];
  citations: string[];
  agent_trace: string[];
  llm_call_count: number;
  embedding_mode: string;
}

export interface CaseReportData {
  case: {
    id: string;
    domain: string;
    title: string;
    institution_name: string;
    summary: string;
    status: string;
    synthetic?: boolean;
  } | null;
  appeals: Appeal[];
  documents: VaultDocument[];
  events: ReportSummary["recent_activity"];
  agent_runs?: Array<{ id: string; workflow: string; status: string; output: Record<string, unknown>; created_at: string }>;
  latest_analysis?: LatestAnalysis;
}


export async function getReportSummary(): Promise<ReportSummary> {
  return request("/reports/summary", { method: "GET" });
}

export async function getCaseReport(caseId: string): Promise<CaseReportData> {
  return request(`/reports/case/${caseId}`, { method: "GET" });
}

export type TimelineEvent = ReportSummary["recent_activity"][number];

export async function getEvents(limit = 30, before?: string): Promise<TimelineEvent[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (before) params.set("before", before);
  return request(`/reports/events?${params.toString()}`, { method: "GET" });
}

export interface SystemHealth {
  status: string;
  service: string;
  environment: string;
  vector_store: { status: string; backend: string; collections?: number; total_points?: number };
  graph_store: { status: string; backend: string; events?: number };
  supabase: { status: string; url?: string };
  gemini: { status: string };
  llm: { provider: string; status: string; reasoning_model?: string; embedding_model?: string };
  redis: { status: string; error?: string };
  web_search: { status: string };
}

export async function getSystemHealth(): Promise<{ health: SystemHealth; latencyMs: number }> {
  const root = API_BASE.replace(/\/api\/v1\/?$/, "");
  const start = performance.now();
  const response = await fetch(`${root}/health`, { cache: "no-store" });
  const latencyMs = Math.round(performance.now() - start);
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return { health: await response.json(), latencyMs };
}

export type CaseStatus = "draft" | "intake" | "analyzing" | "review_required" | "ready_for_approval" | "submitted" | "resolved" | "closed";

export interface AnalysisCase {
  id: string;
  user_id: string;
  domain: string;
  title: string;
  institution_name: string;
  summary: string;
  jurisdiction: string;
  status: CaseStatus;
  created_at: string;
  updated_at: string;
  avg_confidence: number | null;
  run_count: number;
  completed_runs: number;
  domains_involved: string[];
}

export async function listAnalyses(): Promise<AnalysisCase[]> {
  return request("/cases/analyses", { method: "GET" });
}

export async function updateCaseStatus(caseId: string, status: CaseStatus): Promise<AnalysisCase> {
  return request(`/cases/${caseId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export interface InstitutionPattern {
  pattern: string;
  domain: string;
  institution: string;
  confidence: number;
}

export async function getInstitutionPatterns(domain: string, institutionName: string): Promise<InstitutionPattern[]> {
  return request(`/graph/patterns?domain=${encodeURIComponent(domain)}&institution_name=${encodeURIComponent(institutionName)}`, {
    method: "GET",
  });
}

export interface SimilarCase {
  case_id: string;
  title: string;
  summary: string;
}

export async function getSimilarCases(domain: string, institutionName: string, limit = 5): Promise<SimilarCase[]> {
  return request(
    `/graph/similar-cases?domain=${encodeURIComponent(domain)}&institution_name=${encodeURIComponent(institutionName)}&limit=${limit}`,
    { method: "GET" }
  );
}

export interface CitizenDomainProfile {
  domain: string;
  case_count: number;
  cases: Array<{ case_id: string; title: string }>;
  institutions: string[];
}

export interface CitizenProfile {
  user_id: string;
  domains_active_in: string[];
  total_cases: number;
  by_domain: CitizenDomainProfile[];
}

export async function getCitizenProfile(userId: string): Promise<CitizenProfile> {
  return request(`/graph/citizen/${userId}/profile`, { method: "GET" });
}

export async function getMyCitizenProfile(): Promise<CitizenProfile> {
  return getCitizenProfile(getDeviceUserId());
}
