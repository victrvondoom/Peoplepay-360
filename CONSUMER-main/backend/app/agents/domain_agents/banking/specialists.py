from __future__ import annotations

from dataclasses import dataclass

from app.agents.state import AgentState
from app.llm.gemini.service import gemini_service
from app.prompts.consumer_advocacy import build_agent_prompt


@dataclass(frozen=True)
class BankingSpecialist:
    name: str
    task: str
    model_purpose: str = "reasoning"


SPECIALISTS = {
    "cards": BankingSpecialist(
        name="Credit/Debit Cards Agent",
        task="Analyze credit card terms, debit card rules, chargeback policies, credit card fraud, unauthorized transactions, and merchant dispute resolution. Cite card agreements.",
    ),
    "loans": BankingSpecialist(
        name="Loans & EMI Agent",
        task="Analyze home loan, personal loan, auto loan terms, EMI calculation, interest rates, foreclosure rules, penalty charges, and loan agreements.",
    ),
    "payments": BankingSpecialist(
        name="Payments & Accounts Agent",
        task="Analyze savings/current account terms, failed UPI payments, payment gateway failures, ATM disputes, double debits, and UPI guidelines.",
    ),
    "regulatory": BankingSpecialist(
        name="RBI & Ombudsman Agent",
        task="Analyze RBI Master Directions, consumer protection guidelines, Digital Payment Security guidelines, Banking Ombudsman rules, and RBI CMS procedures.",
    ),
    "faq": BankingSpecialist(
        name="Banking General FAQ Agent",
        task="Give a concise response regarding banking services and state what specific document or transaction details are needed.",
    ),
}


def _prompt_for(specialist: BankingSpecialist, state: AgentState) -> str:
    route_note = (
        "You are part of a supervisor-routed architecture. Only answer your specialist banking scope. "
        "If the retrieved context is insufficient, say exactly what banking document or circular is missing."
    )
    task = f"{route_note}\n\n{specialist.task}"
    return build_agent_prompt(
        state["domain"],
        task,
        state["case_summary"],
        state.get("retrieved_context", ""),
        state.get("evidence_bundle", ""),
    )


async def run_banking_specialist(state: AgentState, route: str) -> AgentState:
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
    state.setdefault("agent_trace", []).append(f"banking_specialist:{route}:gemini_reasoning")
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    return state


async def run_banking_specialists(state: AgentState) -> AgentState:
    routes = state.get("plan", {}).get("specialists", [state.get("route", "faq")])
    for route in routes:
        state = await run_banking_specialist(state, route)
    return state
