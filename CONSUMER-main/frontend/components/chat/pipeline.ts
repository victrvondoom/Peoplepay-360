/**
 * Maps the real backend agent_trace strings (see backend/app/agents/
 * orchestrator/case_workflow.py and specialist_dispatch.py) to human-
 * readable pipeline stages. This is what makes the "Agent Reasoning" panel
 * honest rather than decorative: after a response arrives, every stage
 * shown was actually executed -- reconstructed from the real trace array
 * the backend returned, not a canned animation pretending to be live data.
 */
export interface PipelineStage {
  key: string;
  label: string;
  detail?: string;
  status: "done" | "running" | "pending";
}

const STAGE_PATTERNS: Array<{ match: (t: string) => boolean; label: string }> = [
  { match: (t) => t === "supervisor:start", label: "Session started" },
  { match: (t) => t.startsWith("domain_router:"), label: "Classified query across domains" },
  { match: (t) => t === "memory:loaded", label: "Loaded citizen memory" },
  { match: (t) => t.startsWith("planner:"), label: "Planned specialist routing" },
  { match: (t) => t.startsWith("research:") || t === "retrieval:qdrant", label: "Retrieved evidence (vector search)" },
  { match: (t) => t === "graph:neo4j", label: "Queried knowledge graph" },
  { match: (t) => t.startsWith("web_search:"), label: "Searched the web for current info" },
  { match: (t) => t.endsWith("_orchestrator:start"), label: "Dispatched domain specialists" },
  { match: (t) => t.startsWith("specialist_executed:"), label: "Specialist analysis" },
  { match: (t) => t.startsWith("specialist_failed:"), label: "Specialist failed (recovered)" },
  { match: (t) => t === "evidence:gemini", label: "Scored evidence quality" },
  { match: (t) => t === "strategy:gemini", label: "Built response strategy" },
  { match: (t) => t.startsWith("negotiation:"), label: "Drafted supporting documents" },
  { match: (t) => t === "review:gemini", label: "Reviewed for accuracy" },
  { match: (t) => t === "response:final", label: "Finalized response" },
  { match: (t) => t === "supervisor:done", label: "Complete" },
];

export function traceToStages(trace: string[]): PipelineStage[] {
  return trace.map((raw, index) => {
    const pattern = STAGE_PATTERNS.find((p) => p.match(raw));
    const specialistName = raw.startsWith("specialist_executed:") ? raw.split(":").slice(1).join(":") : undefined;
    return {
      key: `${raw}-${index}`,
      label: pattern?.label ?? raw,
      detail: specialistName ?? (pattern ? undefined : raw),
      status: "done" as const,
    };
  });
}

// Shown while waiting for the real response -- explicitly an *estimate* of
// what's about to run (labeled as such in the UI), not fabricated telemetry.
export const ESTIMATED_STAGES: string[] = [
  "Classifying query across domains",
  "Retrieving evidence from official sources",
  "Querying knowledge graph",
  "Running domain specialists",
  "Scoring evidence quality",
  "Building response strategy",
  "Generating citations",
  "Reviewing for accuracy",
];
