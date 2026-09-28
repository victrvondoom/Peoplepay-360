"""Evidence Agent — reads uploaded documents and extracts structured facts.

The schema of those facts is domain-specific (evidence_prompt builds it from
app.prompts.domain_profiles -- diagnosis/hospital for health insurance,
transaction_date/dispute_type for banking, flight_number/disruption_type for
airlines, etc.), so this agent passes through whatever fields the LLM
actually returned instead of only ever keeping a fixed insurance-shaped
subset -- previously it cherry-picked diagnosis/treatment/hospital/etc. by
hardcoded key name regardless of domain, silently discarding every other
domain's real extracted facts.
"""

from __future__ import annotations

from app.agents.json_parser import parse_agent_json, unwrap_nested_json_summary
from app.agents.state import AgentState, EvidenceOutput
from app.llm.service import llm_service
from app.prompts.health_insurance_agents import evidence_prompt

EVIDENCE_FALLBACK_FIELDS: dict = {
    "documents_missing": [],
    "key_dates": [],
}


async def run_evidence_agent(state: AgentState) -> AgentState:
    """Execute the evidence agent: parse documents and extract domain-appropriate structured facts."""
    domain = state["domain"]
    case_summary = state.get("case_summary", "")
    context = state.get("retrieved_context", "")
    has_uploaded_documents = bool(state.get("evidence_bundle"))
    evidence = state.get("evidence_bundle") or case_summary

    prompt = evidence_prompt(domain, case_summary, context, evidence, has_uploaded_documents)
    raw = await llm_service.generate(prompt, temperature=0.1, purpose="reasoning")

    # Parse structured output -- keep every field the LLM returned (the
    # schema varies per domain) rather than filtering to a fixed key set.
    parsed = parse_agent_json(raw, EVIDENCE_FALLBACK_FIELDS)
    evidence_output: EvidenceOutput = {
        **{key: value for key, value in parsed.items() if key != "_parse_failed"},
        "documents_missing": parsed.get("documents_missing", []),
        "key_dates": parsed.get("key_dates", []),
        "summary": unwrap_nested_json_summary(parsed.get("summary", raw[:2000])),
    }
    state["evidence_output"] = evidence_output
    state["evidence_summary"] = evidence_output["summary"]
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    state.setdefault("agent_trace", []).append("evidence:gemini")
    return state
