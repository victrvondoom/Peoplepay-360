export const proxyTokens = {
  color: {
    black: "#050505",
    glass: "rgba(13, 15, 22, 0.62)",
    glassStrong: "rgba(18, 22, 32, 0.78)",
    line: "rgba(255,255,255,0.10)",
    text: "#f7fbff",
    muted: "#a8b3c7",
    tertiary: "#687386",
    cyan: "#00e5ff",
    purple: "#9b5cff",
    green: "#37f29a",
    amber: "#ffc857",
    red: "#ff4d6d",
  },
  glow: {
    cyan: "0 0 0 1px rgba(0,229,255,.28), 0 0 28px rgba(0,229,255,.24)",
    purple: "0 0 0 1px rgba(155,92,255,.26), 0 0 34px rgba(155,92,255,.22)",
    green: "0 0 0 1px rgba(55,242,154,.22), 0 0 24px rgba(55,242,154,.18)",
  },
} as const;

export type AgentStage = "research" | "evidence" | "graph" | "strategy" | "negotiation" | "review";
export type StageStatus = "done" | "running" | "waiting" | "error";

export const agentStages: Array<{ id: AgentStage; label: string; stream: string[] }> = [
  { id: "research", label: "Research Agent", stream: ["Searching IRDAI circulars", "Searching policy wording", "Ranking exclusions"] },
  { id: "evidence", label: "Evidence Agent", stream: ["Reading medical report", "Extracting diagnosis", "Checking bill totals"] },
  { id: "graph", label: "Knowledge Graph", stream: ["Querying Neo4j", "Linking treatment", "Mapping regulation path"] },
  { id: "strategy", label: "Strategy Agent", stream: ["Scoring appeal viability", "Finding weak points", "Building evidence checklist"] },
  { id: "negotiation", label: "Negotiation Agent", stream: ["Drafting appeal", "Adding citations", "Preparing escalation copy"] },
  { id: "review", label: "Review Agent", stream: ["Checking hallucinations", "Verifying clauses", "Final risk review"] },
];

export const appealSteps = ["Upload Documents", "Research", "Evidence", "AI Strategy", "Appeal Draft", "Export PDF"];
