"""Shared specialist dispatch — runs the routed specialists for a domain in
parallel (asyncio.gather) instead of a sequential loop.

Previously duplicated near-identically in supervisor.py and case_workflow.py
for every domain (banking/airlines/telecom/ecommerce/government/housing/
healthcare); each specialist's .process(state) only reads from the shared
state and returns an independent result dict, so running them concurrently
is safe — no specialist writes into the shared state directly.
"""
from __future__ import annotations

import asyncio

from app.agents.state import AgentState
from app.models.domain import Domain

_SPECIALIST_REGISTRY = {
    Domain.AIRLINES: ("app.agents.domain_agents.airlines.specialists", "get_airline_specialists", "general_aviation"),
    Domain.TELECOM: ("app.agents.domain_agents.telecom.specialists", "get_telecom_specialists", "general_telecom"),
    Domain.ECOMMERCE: ("app.agents.domain_agents.ecommerce.specialists", "get_ecommerce_specialists", "consumer_protection"),
    Domain.GOVERNMENT: ("app.agents.domain_agents.government.specialists", "get_government_specialists", "general_government"),
    Domain.HOUSING: ("app.agents.domain_agents.housing.specialists", "get_housing_specialists", "general_housing"),
    Domain.HEALTHCARE: ("app.agents.domain_agents.healthcare.specialists", "get_healthcare_specialists", "general_healthcare"),
}


def _load_specialists(domain: Domain):
    import importlib
    module_path, factory_name, default_route = _SPECIALIST_REGISTRY[domain]
    module = importlib.import_module(module_path)
    factory = getattr(module, factory_name)
    return factory(), default_route


async def run_specialists_for_domain(state: AgentState, domain: Domain) -> AgentState:
    """Runs every routed specialist for `domain` in parallel and appends
    their results to state["specialist_results"]/state["specialist_outputs"]."""
    specialists_map, default_route = _load_specialists(domain)
    state.setdefault("agent_trace", []).append(f"{domain.value}_orchestrator:start")

    plan = state.get("plan", {})
    routes = plan.get("specialists", [default_route])
    agents = [specialists_map[route] for route in routes if route in specialists_map]

    if not agents:
        state["specialist_results"] = []
        return state

    results = await asyncio.gather(*(agent.process(state) for agent in agents), return_exceptions=True)

    all_results = []
    for agent, result in zip(agents, results):
        if isinstance(result, Exception):
            state.setdefault("agent_trace", []).append(f"specialist_failed:{agent.name}:{result}")
            continue
        all_results.append(result)
        state.setdefault("agent_trace", []).append(f"specialist_executed:{agent.name}")

    state["specialist_results"] = all_results
    return state


async def run_domain_specialists(state: AgentState) -> AgentState:
    """Dispatch to Health Insurance/Banking's own specialist runners (they
    predate this shared dispatcher and mutate state sequentially internally,
    so aren't safe to parallelize without changing their internals), the
    shared parallel dispatcher for the other 6 registered domains, or a "not
    yet supported" placeholder for any domain registered in the enum but
    without specialists wired up yet (e.g. Domain.HEALTHCARE_PROVIDER)."""
    domain = state["domain"]
    if domain == Domain.HEALTH_INSURANCE:
        from app.agents.domain_agents.health_insurance.specialists import run_health_specialists
        return await run_health_specialists(state)
    if domain == Domain.BANKING:
        from app.agents.domain_agents.banking.specialists import run_banking_specialists
        return await run_banking_specialists(state)
    if domain in _SPECIALIST_REGISTRY:
        return await run_specialists_for_domain(state, domain)

    state.setdefault("specialist_outputs", []).append({
        "agent": "FAQ/General Agent",
        "route": "faq",
        "answer": f"This domain {domain} is registered for future support. Add domain specialists before production routing.",
        "citations": state.get("citations", []),
    })
    return state
