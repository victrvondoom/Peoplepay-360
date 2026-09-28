/**
 * Richer per-trace-entry metadata for the step-by-step "Agent reasoning"
 * panel -- which real agent ran, which real backend functions it invoked,
 * and a one-line explanation of why that step exists. Every `invoked` entry
 * names an actual function in this codebase (app/agents/**), not a
 * decorative placeholder -- if a function gets renamed, update it here too.
 */
export interface TraceStepDetail {
  match: (trace: string) => boolean;
  agent: string;
  color: string;
  invoked: string[];
  why: string;
}

export const TRACE_STEP_DETAILS: TraceStepDetail[] = [
  {
    match: (t) => t === "supervisor:start",
    agent: "Supervisor",
    color: "#a8b3c7",
    invoked: ["case_workflow.run()"],
    why: "Initializes the LangGraph state machine that every subsequent agent reads from and writes to.",
  },
  {
    match: (t) => t.startsWith("domain_router:"),
    agent: "Domain Router",
    color: "#00e5ff",
    invoked: ["classify_domains()", "verify_claims()"],
    why: "Deterministic keyword + typo-tolerant fuzzy matching across all 8 domains -- not an LLM call, so classification is fast, reproducible, and auditable.",
  },
  {
    match: (t) => t === "memory:loaded",
    agent: "Memory",
    color: "#a8b3c7",
    invoked: ["knowledge_graph.load_citizen_memory()"],
    why: "Loads prior context for this user from the knowledge graph, if any exists.",
  },
  {
    match: (t) => t.startsWith("planner:"),
    agent: "Planner",
    color: "#9b5cff",
    invoked: ["route_specialist()"],
    why: "Picks the specific route within the domain (e.g. banking's cards vs. loans vs. regulatory) based on the case summary.",
  },
  {
    match: (t) => t.startsWith("research:") || t === "retrieval:qdrant",
    agent: "Research Agent",
    color: "#00e5ff",
    invoked: ["qdrant_service.search_chunks()", "knowledge_graph.find_institution_patterns()", "web_search_service.search()", "llm_service.generate()"],
    why: "Pulls real regulatory text via vector search, cross-user patterns via the graph, and current web context -- every regulation later cited is checked against this retrieved text.",
  },
  {
    match: (t) => t === "graph:neo4j",
    agent: "Knowledge Graph Agent",
    color: "#9b5cff",
    invoked: ["knowledge_graph.find_institution_patterns()"],
    why: "Looks for patterns other users have hit with the same institution -- e.g. a bank that repeatedly denies a specific dispute type.",
  },
  {
    match: (t) => t.startsWith("web_search:"),
    agent: "Web Search",
    color: "#5c9bff",
    invoked: ["web_search_service.search()"],
    why: "Pulls current web context for anything not already in the indexed regulatory knowledge base.",
  },
  {
    match: (t) => t.endsWith("_orchestrator:start") || t.startsWith("specialist_executed:") || t.includes("specialist"),
    agent: "Domain Specialist",
    color: "#ffc857",
    invoked: ["build_agent_prompt()", "verify_claims()", "llm_service.generate()"],
    why: "Domain-specific reasoning grounded in your case summary, uploaded evidence, and retrieved regulations -- every cited rule is verified against the retrieved text, not just asserted.",
  },
  {
    match: (t) => t === "evidence:gemini",
    agent: "Evidence Agent",
    color: "#37f29a",
    invoked: ["evidence_prompt()", "llm_service.generate()"],
    why: "Extracts structured facts from your uploaded documents, and explicitly flags evidence that doesn't match the case instead of guessing.",
  },
  {
    match: (t) => t === "strategy:gemini",
    agent: "Strategy Agent",
    color: "#ffc857",
    invoked: ["strategy_prompt()", "llm_service.generate()"],
    why: "Decides whether to proceed and the recommended path, citing only regulations verified against retrieved sources.",
  },
  {
    match: (t) => t.startsWith("negotiation:"),
    agent: "Negotiation Agent",
    color: "#ff6fb0",
    invoked: ["negotiation_prompt()", "llm_service.generate()"],
    why: "Drafts four structurally different documents -- appeal letter, complaint email, internal escalation memo, regulator complaint form -- each with real contact details for the actual escalation channel.",
  },
  {
    match: (t) => t === "review:gemini",
    agent: "Review Agent",
    color: "#ff4d6d",
    invoked: ["review_prompt()", "llm_service.generate()"],
    why: "Devil's-advocate audit -- checks for hallucinated clauses, missing evidence, and weak arguments before you see the answer.",
  },
  {
    match: (t) => t === "response:final",
    agent: "Response Agent",
    color: "#37f29a",
    invoked: ["run_response_agent()"],
    why: "Merges every agent's output into the final answer, with the evidence-grounded facts and verified citations surfaced first.",
  },
  {
    match: (t) => t === "supervisor:done",
    agent: "Supervisor",
    color: "#a8b3c7",
    invoked: [],
    why: "Case complete -- the full trace above is exactly what ran, not a simulated animation.",
  },
];

export function detailFor(trace: string): TraceStepDetail {
  return (
    TRACE_STEP_DETAILS.find((d) => d.match(trace)) ?? {
      match: () => true,
      agent: trace,
      color: "#a8b3c7",
      invoked: [],
      why: "",
    }
  );
}
