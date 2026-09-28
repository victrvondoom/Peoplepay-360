"""Final Report Agent — compiles all agent outputs into a comprehensive case report."""

from __future__ import annotations

from app.agents.state import AgentState
from app.llm.service import llm_service
from app.prompts.health_insurance_agents import final_report_prompt


async def run_final_report_agent(state: AgentState) -> AgentState:
    """Compile the final human-readable case report from all agent outputs."""
    prompt = final_report_prompt(state["domain"], dict(state))
    report = await llm_service.generate(prompt, temperature=0.2, purpose="response")
    state["final_report"] = report
    state["final_answer"] = report
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    state.setdefault("agent_trace", []).append("final_report:gemini")
    return state
