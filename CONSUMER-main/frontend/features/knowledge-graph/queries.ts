"use client";

import { useQuery } from "@tanstack/react-query";
import * as api from "./api";
import type { InstitutionQueryParams } from "./api";

const KG_KEY = "knowledge-graph" as const;

export function useCaseListQuery() {
  return useQuery({ queryKey: [KG_KEY, "case-list"], queryFn: api.fetchCaseList, staleTime: 30_000 });
}

export function useCaseGraphQuery(caseId: string | null) {
  return useQuery({
    queryKey: [KG_KEY, "case-graph", caseId],
    queryFn: () => api.fetchCaseGraph(caseId as string),
    enabled: Boolean(caseId),
  });
}

export function useReasoningTrailQuery(caseId: string | null) {
  return useQuery({
    queryKey: [KG_KEY, "reasoning-trail", caseId],
    queryFn: () => api.fetchReasoningTrail(caseId as string),
    enabled: Boolean(caseId),
  });
}

export function useInstitutionGraphQuery(params: InstitutionQueryParams | null) {
  return useQuery({
    queryKey: [KG_KEY, "institution-graph", params],
    queryFn: () => api.fetchInstitutionGraph(params as InstitutionQueryParams),
    enabled: Boolean(params),
  });
}

export function useKnowledgeFootprintQuery() {
  return useQuery({ queryKey: [KG_KEY, "footprint"], queryFn: api.fetchKnowledgeFootprint, staleTime: 15_000 });
}

export function useInstitutionRadarQuery() {
  return useQuery({ queryKey: [KG_KEY, "institution-radar"], queryFn: () => api.fetchInstitutionRadar(50), staleTime: 30_000 });
}
