"""Strategy Agent — decides the dispute path:

- Can the claim be appealed? YES / NO
- Probability of success
- Recommended strategy
- Evidence still required
"""

from __future__ import annotations

from app.agents.json_parser import parse_agent_json, unwrap_nested_json_summary
from app.agents.state import AgentState, StrategyOutput
from app.llm.service import llm_service
from app.prompts.health_insurance_agents import strategy_prompt

STRATEGY_FALLBACK_FIELDS: dict = {
    "can_appeal": "UNKNOWN",
    "success_probability": 0.0,
    "recommended_strategy": "",
    "evidence_required": [],
    "escalation_path": [],
}


async def run_strategy_agent(state: AgentState) -> AgentState:
    """Execute the strategy agent: assess appeal viability and recommend approach."""
    domain = state["domain"]
    case_summary = state.get("case_summary", "")
    context = state.get("retrieved_context", "")
    evidence_summary = state.get("evidence_summary", "")
    research_summary = state.get("research_summary", "")

    # If review already rejected an earlier pass (review_retry_count > 0),
    # feed its specific findings back in rather than silently re-rolling the
    # same prompt and hoping for a different random output.
    review_feedback = ""
    if state.get("review_retry_count", 0) > 0:
        review_output = state.get("review_output", {})
        parts = []
        if review_output.get("hallucination_risks"):
            parts.append("Hallucinated/unsupported claims to remove: " + "; ".join(review_output["hallucination_risks"]))
        if review_output.get("wrong_clause_risks"):
            parts.append("Incorrectly cited clauses/regulations to fix: " + "; ".join(review_output["wrong_clause_risks"]))
        if review_output.get("weak_arguments"):
            parts.append("Weak arguments to strengthen or replace: " + "; ".join(review_output["weak_arguments"]))
        review_feedback = "\n".join(parts)

    prompt = strategy_prompt(domain, case_summary, context, evidence_summary, research_summary, review_feedback)
    raw = await llm_service.generate(prompt, temperature=0.2, purpose="reasoning")

    # Parse structured output
    parsed = parse_agent_json(raw, STRATEGY_FALLBACK_FIELDS)
    recommended_strategy = parsed.get("recommended_strategy", "")
    strategy_output: StrategyOutput = {
        "can_appeal": parsed.get("can_appeal", "UNKNOWN"),
        "success_probability": float(parsed.get("success_probability", 0.5)),
        "recommended_strategy": recommended_strategy,
        "evidence_required": parsed.get("evidence_required", []),
        "escalation_path": parsed.get("escalation_path", []),
        "summary": unwrap_nested_json_summary(parsed.get("summary", raw[:2000]), fallback=recommended_strategy),
    }
    state["strategy_output"] = strategy_output
    state["strategy"] = strategy_output["summary"]
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    state.setdefault("agent_trace", []).append("strategy:gemini")
    return state
