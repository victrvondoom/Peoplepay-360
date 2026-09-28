"""Negotiation Agent — generates all dispute documents:

- Appeal Letter (formal to GRO)
- Complaint Email (shorter version)
- Escalation Note (internal/ombudsman path)
- Consumer Complaint (IRDAI IGMS / Ombudsman draft)
"""

from __future__ import annotations

import json

from app.agents.json_parser import parse_agent_json, unwrap_nested_json_summary
from app.agents.state import AgentState, NegotiationOutput
from app.llm.service import llm_service
from app.prompts.health_insurance_agents import negotiation_prompt

NEGOTIATION_FALLBACK_FIELDS: dict = {
    "appeal_letter": "",
    "complaint_email": "",
    "escalation_note": "",
    "consumer_complaint": "",
}


async def run_negotiation_agent(state: AgentState) -> AgentState:
    """Execute the negotiation agent: generate all dispute documents."""
    domain = state["domain"]
    case_summary = state.get("case_summary", "")
    context = state.get("retrieved_context", "")
    strategy = state.get("strategy", "")
    evidence_summary = state.get("evidence_summary", "")

    # Use strategy output for richer context if available
    strategy_output = state.get("strategy_output", {})
    if strategy_output:
        strategy_text = (
            f"Can appeal: {strategy_output.get('can_appeal', 'UNKNOWN')}\n"
            f"Probability: {strategy_output.get('success_probability', 'N/A')}\n"
            f"Strategy: {strategy_output.get('recommended_strategy', '')}\n"
            f"Evidence required: {', '.join(strategy_output.get('evidence_required', []))}\n"
            f"Escalation path: {', '.join(strategy_output.get('escalation_path', []))}\n"
            f"Summary: {strategy_output.get('summary', '')}"
        )
    else:
        strategy_text = strategy

    prompt = negotiation_prompt(domain, case_summary, context, strategy_text, evidence_summary)
    raw = await llm_service.generate(prompt, temperature=0.25, purpose="reasoning")

    # Parse structured output. The LLM doesn't always return these fields as
    # plain strings (e.g. it may nest a dict for a domain the prompt wasn't
    # tuned for), so coerce defensively — downstream code slices/concatenates
    # these as free text, and a raw json.dumps() here used to leak literal
    # {"subject": ..., "body": "...\n\n..."} text straight into the UI.
    def _as_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if value in (None, ""):
            return ""
        if isinstance(value, dict):
            # Common nested shape: {"subject": ..., "body": ...} -- render
            # as a real letter opening, not a JSON blob.
            if "body" in value:
                subject = value.get("subject")
                body = str(value.get("body", ""))
                return f"Subject: {subject}\n\n{body}" if subject else body
            lines = []
            for key, val in value.items():
                label = str(key).replace("_", " ").title()
                if isinstance(val, list):
                    lines.append(label + ":\n" + "\n".join(f"- {item}" for item in val))
                else:
                    lines.append(f"{label}: {val}")
            return "\n\n".join(lines)
        if isinstance(value, (list, set, frozenset, tuple)):
            # A set specifically can come from _python_literal_repair()'s
            # ast.literal_eval fallback: a malformed field like
            # {"point one", "point two"} (no colons) is valid Python set
            # syntax, and literal_eval happily parses it as one -- which
            # then crashed json.dumps() below with "Object of type set is
            # not JSON serializable" and took down the whole agent run.
            return "\n".join(f"- {item}" for item in value)
        return json.dumps(value, ensure_ascii=False, indent=2)

    parsed = parse_agent_json(raw, NEGOTIATION_FALLBACK_FIELDS)
    negotiation_output: NegotiationOutput = {
        "appeal_letter": _as_text(parsed.get("appeal_letter", "")),
        "complaint_email": _as_text(parsed.get("complaint_email", "")),
        "escalation_note": _as_text(parsed.get("escalation_note", "")),
        "consumer_complaint": _as_text(parsed.get("consumer_complaint", "")),
        "summary": unwrap_nested_json_summary(_as_text(parsed.get("summary", "Appeal documents generated."))),
    }
    state["negotiation_output"] = negotiation_output

    # Keep backward compatibility: appeal_draft = the formal appeal letter
    state["appeal_draft"] = negotiation_output["appeal_letter"]
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    state.setdefault("agent_trace", []).append("negotiation:all_documents")
    return state
