from __future__ import annotations

from dataclasses import dataclass

from app.agents.state import AgentState
from app.llm.gemini.service import gemini_service
from app.prompts.consumer_advocacy import build_agent_prompt


@dataclass(frozen=True)
class HealthSpecialist:
    name: str
    task: str
    model_purpose: str = "reasoning"


SPECIALISTS = {
    "policy": HealthSpecialist(
        name="Policy Agent",
        task="Answer from health insurance policy wording: coverage, exclusions, waiting periods, sub-limits, riders, and product brochure details. Cite retrieved policy text.",
    ),
    "claims": HealthSpecialist(
        name="Claims Agent",
        task="Analyze claim procedure, denial reason, missing documents, pre-authorization, reimbursement, cashless workflow, and appeal next steps.",
    ),
    "medical": HealthSpecialist(
        name="Medical Agent",
        task="Explain the disease, treatment, procedure, medical necessity, and how it connects to insurance coverage. Do not give diagnosis or treatment advice.",
    ),
    "legal": HealthSpecialist(
        name="Legal/Regulations Agent",
        task="Use IRDAI, policyholder rights, complaint, grievance, ombudsman, and regulatory context. Cite official regulatory sources first.",
    ),
    "faq": HealthSpecialist(
        name="FAQ/General Agent",
        task="Give a concise general health insurance answer and say what document or policy detail is needed for certainty.",
    ),
}


def _prompt_for(specialist: HealthSpecialist, state: AgentState) -> str:
    route_note = (
        "You are part of a supervisor-routed architecture. Only answer your specialist scope. "
        "If the retrieved context is insufficient, say exactly what evidence or policy document is missing."
    )
    task = f"{route_note}\n\n{specialist.task}"
    return build_agent_prompt(
        state["domain"],
        task,
        state["case_summary"],
        state.get("retrieved_context", ""),
        state.get("evidence_bundle", ""),
    )


async def run_health_specialist(state: AgentState, route: str) -> AgentState:
    specialist = SPECIALISTS.get(route, SPECIALISTS["faq"])
    model_name = gemini_service.model_for("reasoning")
    answer = await gemini_service.generate(_prompt_for(specialist, state), purpose="reasoning")
    output = {
        "agent": specialist.name,
        "route": route,
        "answer": answer,
        "model_purpose": specialist.model_purpose,
        "model": model_name,
        "citations": state.get("citations", []),
    }
    state.setdefault("specialist_outputs", []).append(output)
    state.setdefault("agent_trace", []).append(f"specialist:{route}:gemini_reasoning")
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    return state


async def run_health_specialists(state: AgentState) -> AgentState:
    routes = state.get("plan", {}).get("specialists", [state.get("route", "faq")])
    for route in routes:
        state = await run_health_specialist(state, route)
    return state
