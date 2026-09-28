"""Execution Planner — wraps the existing deterministic build_plan() (which
decides WHICH specialists to route to) with execution-level metadata: what
order stages run in, which stages can run in parallel, their dependencies,
and a per-case LLM-call budget with a retry ceiling per agent.

Additive: state["route"]/state["plan"]["specialists"]/state["plan"]["tools"]
are unchanged, so every existing consumer of the plan keeps working. New
callers can read plan["execution_order"]/["dependencies"]/["budget"].
"""
from __future__ import annotations

from app.agents.role_agents.planner import build_plan
from app.agents.state import AgentState

DEFAULT_MAX_LLM_CALLS_PER_CASE = 12
DEFAULT_MAX_RETRIES_PER_AGENT = 1


def build_execution_plan(state: AgentState) -> dict:
    base_plan = build_plan(state)
    tools = base_plan.get("tools", {})

    stages = ["retrieval"]
    if tools.get("knowledge_graph"):
        stages.append("graph")
    if tools.get("web_search"):
        stages.append("web_search")
    stages.append("specialists")
    if tools.get("negotiator"):
        stages.append("negotiator")
    stages += ["evidence", "strategy", "negotiation", "review", "response"]

    dependencies: dict[str, list[str]] = {
        "specialists": ["retrieval"],
        "evidence": ["specialists"] + (["negotiator"] if tools.get("negotiator") else []),
        "strategy": ["evidence"],
        "negotiation": ["strategy"],
        "review": ["negotiation"],
        "response": ["review"],
    }
    if tools.get("negotiator"):
        dependencies["negotiator"] = ["specialists"]

    return {
        **base_plan,
        "execution_order": stages,
        # Every specialist named here for the "specialists" stage runs
        # concurrently via asyncio.gather (see specialist_dispatch.py), not
        # sequentially — this is the actual parallel-execution group.
        "parallel_groups": {"specialists": base_plan.get("specialists", [])},
        "dependencies": dependencies,
        "budget": {"max_llm_calls": DEFAULT_MAX_LLM_CALLS_PER_CASE},
        "max_retries_per_agent": DEFAULT_MAX_RETRIES_PER_AGENT,
    }


def within_budget(state: AgentState) -> bool:
    """Whether this case still has LLM-call budget left. Agents/response
    formatting can check this to degrade gracefully (e.g. skip an optional
    enrichment step) instead of silently blowing past a cost ceiling."""
    plan = state.get("plan", {})
    max_calls = plan.get("budget", {}).get("max_llm_calls", DEFAULT_MAX_LLM_CALLS_PER_CASE)
    return int(state.get("llm_call_count", 0)) < max_calls


async def run_execution_planner_agent(state: AgentState) -> AgentState:
    plan = build_execution_plan(state)
    state["plan"] = plan
    state["route"] = plan["route"]
    state.setdefault("agent_trace", []).append(f"planner:{plan['route']}")
    return state
