"""Review Agent — double-checks everything before human approval:

- Missing evidence
- Hallucination risks
- Wrong clause / regulation citations
- Weak arguments
"""

from __future__ import annotations

from app.agents.json_parser import parse_agent_json, unwrap_nested_json_summary
from app.agents.state import AgentState, ReviewOutput
from app.llm.service import llm_service
from app.prompts.health_insurance_agents import review_prompt

REVIEW_FALLBACK_FIELDS: dict = {
    "missing_evidence": [],
    "hallucination_risks": [],
    "wrong_clause_risks": [],
    "weak_arguments": [],
    "approval_ready": False,
}


async def run_review_agent(state: AgentState) -> AgentState:
    """Execute the review agent: audit the entire case for quality before submission."""
    domain = state["domain"]
    case_summary = state.get("case_summary", "")
    context = state.get("retrieved_context", "")
    evidence_summary = state.get("evidence_summary", "")
    strategy = state.get("strategy", "")
    appeal_draft = state.get("appeal_draft", "")

    prompt = review_prompt(domain, case_summary, context, evidence_summary, strategy, appeal_draft)
    raw = await llm_service.generate(prompt, temperature=0.15, purpose="reasoning")

    # Parse structured output
    parsed = parse_agent_json(raw, REVIEW_FALLBACK_FIELDS)
    review_output: ReviewOutput = {
        "missing_evidence": parsed.get("missing_evidence", []),
        "hallucination_risks": parsed.get("hallucination_risks", []),
        "wrong_clause_risks": parsed.get("wrong_clause_risks", []),
        "weak_arguments": parsed.get("weak_arguments", []),
        "approval_ready": bool(parsed.get("approval_ready", False)),
        "summary": unwrap_nested_json_summary(parsed.get("summary", raw[:2000])),
    }
    state["review_output"] = review_output
    # Keep every pass, not just the last one -- a second review_output
    # overwrote the first pass's findings entirely, so there was no way to
    # show "here's what was wrong, and here's proof it got fixed" -- only
    # ever the final, already-clean state. This is what the self-correction
    # timeline (see run_review_agent's caller) actually renders.
    state.setdefault("review_history", []).append(review_output)

    # Blocking = the strategy/negotiation stated something not actually
    # supported by the retrieved evidence -- a genuine defect a re-run with
    # explicit corrective feedback can fix. Missing evidence and "weak"
    # arguments are not blocking: missing evidence needs a document the user
    # hasn't provided (retrying won't produce it), and a weak argument alone
    # may just be an honest assessment, not a defect. Capped at one retry so
    # a persistently uncorrectable case still terminates rather than looping.
    retry_count = state.get("review_retry_count", 0)
    blocking = bool(review_output["hallucination_risks"]) or bool(review_output["wrong_clause_risks"])
    should_retry = blocking and not review_output["approval_ready"] and retry_count < 1
    state["review_retry_count"] = retry_count + 1 if should_retry else retry_count
    state["review_should_retry"] = should_retry

    # Backward compatibility: review_notes = flat list of all issues
    all_issues: list[str] = []
    for issue in review_output.get("missing_evidence", []):
        all_issues.append(f"[Missing] {issue}")
    for issue in review_output.get("hallucination_risks", []):
        all_issues.append(f"[Hallucination] {issue}")
    for issue in review_output.get("wrong_clause_risks", []):
        all_issues.append(f"[Wrong Clause] {issue}")
    for issue in review_output.get("weak_arguments", []):
        all_issues.append(f"[Weak] {issue}")
    if not all_issues:
        all_issues = [review_output.get("summary", "Review completed.")]
    state["review_notes"] = all_issues
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    state.setdefault("agent_trace", []).append("review:gemini")
    return state
