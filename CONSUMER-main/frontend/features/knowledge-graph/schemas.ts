import { z } from "zod";

/** Zod contracts for every response this feature consumes. Parsing at the
 * network boundary (see api.ts) means a backend field rename/removal fails
 * loudly in dev instead of silently rendering an empty graph. */

export const NodeKindSchema = z.enum(["case", "domain", "institution", "document", "appeal", "regulation", "you"]);
export type NodeKind = z.infer<typeof NodeKindSchema>;

export const GraphNodeSchema = z.object({
  id: z.string(),
  kind: NodeKindSchema,
  label: z.string(),
  detail: z.record(z.string(), z.unknown()).optional(),
});
export type GraphNodeData = z.infer<typeof GraphNodeSchema>;

export const GraphEdgeSchema = z.object({ source: z.string(), target: z.string() });
export type GraphEdgeData = z.infer<typeof GraphEdgeSchema>;

export const CaseGraphResponseSchema = z.object({
  case_id: z.string(),
  domain: z.string(),
  nodes: z.array(GraphNodeSchema),
  edges: z.array(GraphEdgeSchema),
});
export type CaseGraphResponse = z.infer<typeof CaseGraphResponseSchema>;

export const ReasoningStepSchema = z.object({ index: z.number(), token: z.string(), node_id: z.string() });
export type ReasoningStep = z.infer<typeof ReasoningStepSchema>;
export const ReasoningTrailResponseSchema = z.object({ case_id: z.string(), steps: z.array(ReasoningStepSchema) });
export type ReasoningTrailResponse = z.infer<typeof ReasoningTrailResponseSchema>;

export const InstitutionPatternSchema = z.object({
  pattern: z.string(),
  domain: z.string(),
  institution: z.string(),
  confidence: z.number(),
});
export const SimilarCaseSchema = z.object({ case_id: z.string(), title: z.string(), summary: z.string() });
export const InstitutionEntrySchema = z.object({
  index: z.number(),
  domain: z.string(),
  institution_name: z.string(),
  patterns: z.array(InstitutionPatternSchema),
  similar_cases: z.array(SimilarCaseSchema),
});
export type InstitutionEntry = z.infer<typeof InstitutionEntrySchema>;
export const SharedEntitySchema = z.object({
  type: z.enum(["pattern", "case"]),
  a_i: z.number().optional(),
  b_i: z.number().optional(),
  text: z.string().optional(),
  case_id: z.string().optional(),
  title: z.string().optional(),
});
export type SharedEntity = z.infer<typeof SharedEntitySchema>;
export const InstitutionGraphResponseSchema = z.object({
  institutions: z.array(InstitutionEntrySchema),
  shared: z.array(SharedEntitySchema),
});
export type InstitutionGraphResponse = z.infer<typeof InstitutionGraphResponseSchema>;

export const FootprintCaseSchema = z.object({
  case_id: z.string(),
  title: z.string(),
  created_at: z.string().nullable(),
  avg_confidence: z.number().nullable(),
});
export type FootprintCase = z.infer<typeof FootprintCaseSchema>;
export const FootprintDomainSchema = z.object({
  domain: z.string(),
  case_count: z.number(),
  cases: z.array(FootprintCaseSchema),
  institutions: z.array(z.string()),
});
export type FootprintDomain = z.infer<typeof FootprintDomainSchema>;
export const KnowledgeFootprintResponseSchema = z.object({
  user_id: z.string(),
  total_cases: z.number(),
  domains_active_in: z.array(z.string()),
  by_domain: z.array(FootprintDomainSchema),
  avg_confidence: z.number().nullable(),
  most_active_domain: z.string().nullable(),
});
export type KnowledgeFootprintResponse = z.infer<typeof KnowledgeFootprintResponseSchema>;

export const InstitutionRadarEntrySchema = z.object({
  institution_name: z.string(),
  total_cases: z.number(),
  by_domain: z.array(z.object({ domain: z.string(), case_count: z.number() })),
});
export type InstitutionRadarEntry = z.infer<typeof InstitutionRadarEntrySchema>;
export const InstitutionRadarResponseSchema = z.array(InstitutionRadarEntrySchema);

export const CaseListItemSchema = z.object({
  id: z.string(),
  domain: z.string(),
  title: z.string(),
  institution_name: z.string().nullable().optional(),
  status: z.string(),
  // Nullable/optional: checked the real dataset directly -- 148 of 360
  // stored cases (41%) have no created_at, and all 147 of those also lack
  // updated_at (legacy/placeholder records, e.g. the "Document Vault" entry
  // used for domain uploads not tied to a dispute). A strict required
  // string here fails Zod validation for the WHOLE list the moment any user
  // has even one such case, taking down the entire case picker instead of
  // just that one row's timestamp display.
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  avg_confidence: z.number().nullable().optional(),
  domains_involved: z.array(z.string()).optional(),
});
export type CaseListItem = z.infer<typeof CaseListItemSchema>;

export const ChatAnswerSchema = z.object({
  case_id: z.string().optional(),
  question: z.string().optional(),
  answer: z.string(),
});
export type ChatAnswer = z.infer<typeof ChatAnswerSchema>;
