import { z } from "zod";
import { API_BASE, getDeviceUserId } from "@/lib/api-client";
import {
  CaseGraphResponseSchema, ReasoningTrailResponseSchema, InstitutionGraphResponseSchema,
  KnowledgeFootprintResponseSchema, CaseListItemSchema, ChatAnswerSchema, InstitutionRadarResponseSchema,
  type CaseGraphResponse, type ReasoningTrailResponse, type InstitutionGraphResponse,
  type KnowledgeFootprintResponse, type CaseListItem, type ChatAnswer, type InstitutionRadarEntry,
} from "./schemas";

/** Self-contained fetch layer for this feature -- same device-identity
 * convention as the rest of the app (lib/api-client.ts's getDeviceUserId),
 * but every response is Zod-parsed at the boundary instead of trusted
 * as-is. Real endpoints only; nothing here is mocked. */
async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getDeviceUserId()}`,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  const json = await response.json();
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    throw new Error(`API response for ${path} failed validation: ${parsed.error.message}`);
  }
  return parsed.data;
}

export function fetchCaseList(): Promise<CaseListItem[]> {
  return request(`/cases/analyses`, z.array(CaseListItemSchema));
}

export function fetchCaseGraph(caseId: string): Promise<CaseGraphResponse> {
  return request(`/graph/case/${encodeURIComponent(caseId)}/graph`, CaseGraphResponseSchema);
}

export function fetchReasoningTrail(caseId: string): Promise<ReasoningTrailResponse> {
  return request(`/graph/case/${encodeURIComponent(caseId)}/reasoning-trail`, ReasoningTrailResponseSchema);
}

export interface InstitutionQueryParams {
  domain: string;
  institutionName: string;
  domain2?: string;
  institutionName2?: string;
}

export function fetchInstitutionGraph(params: InstitutionQueryParams): Promise<InstitutionGraphResponse> {
  const qs = new URLSearchParams({ domain: params.domain, institution_name: params.institutionName });
  if (params.domain2 && params.institutionName2) {
    qs.set("domain2", params.domain2);
    qs.set("institution_name2", params.institutionName2);
  }
  return request(`/graph/institution-graph?${qs.toString()}`, InstitutionGraphResponseSchema);
}

export function fetchKnowledgeFootprint(): Promise<KnowledgeFootprintResponse> {
  return request(`/graph/user/knowledge-footprint`, KnowledgeFootprintResponseSchema);
}

/** Real institutions that already have case data in the graph, ranked by
 * dispute volume -- lets Institution Intelligence mode offer a browsable
 * list instead of forcing the user to blind-guess an exact institution
 * name (which silently returns an empty constellation on any mismatch). */
export function fetchInstitutionRadar(limit = 50): Promise<InstitutionRadarEntry[]> {
  return request(`/graph/institution-radar?limit=${limit}`, InstitutionRadarResponseSchema);
}

export function askAboutCase(caseId: string, message: string): Promise<ChatAnswer> {
  return request(`/case/chat`, ChatAnswerSchema, {
    method: "POST",
    body: JSON.stringify({ case_id: caseId, message }),
  });
}
