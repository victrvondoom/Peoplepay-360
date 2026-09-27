from app.agents.evidence_agent.agent import run_evidence_agent
from app.agents.graph_agent.agent import run_graph_agent
from app.agents.negotiation_agent.agent import run_negotiation_agent
from app.agents.orchestrator.specialist_dispatch import run_domain_specialists
from app.agents.role_agents.graph import run_graph_role_agent
from app.agents.role_agents.negotiator import run_negotiator_agent
from app.agents.role_agents.execution_planner import run_execution_planner_agent
from app.agents.role_agents.response import run_response_agent
from app.agents.role_agents.retrieval import run_retrieval_agent
from app.agents.role_agents.web_search import run_web_search_agent
from app.agents.research_agent.agent import run_research_agent
from app.agents.review_agent.agent import run_review_agent
from app.agents.state import AgentState
from app.agents.strategy_agent.agent import run_strategy_agent


class CaseWorkflow:
    """LangGraph-backed supervisor workflow.

    Default flow:
    FastAPI -> LangGraph StateGraph -> Supervisor start -> Planner ->
    Retrieval -> Graph/Web tool nodes when needed -> selected domain
    specialists -> Negotiator only when multiple specialists are used -> Response.

    If LangGraph is not installed in a deployment, the same nodes run through a
    deterministic fallback sequence so the API remains functional.
    """

    def __init__(self) -> None:
        self._graph = self._compile_graph()

    async def run(self, state: AgentState) -> AgentState:
        if self._graph is not None:
            return await self._graph.ainvoke(state)
        return await self._run_fallback(state)

    async def run_full_review(self, state: AgentState) -> AgentState:
        state = await run_research_agent(state)
        state = await run_graph_agent(state)
        state = await run_evidence_agent(state)
        state = await run_strategy_agent(state)
        state = await run_negotiation_agent(state)
        state = await run_review_agent(state)
        return state

    def _compile_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None

        graph = StateGraph(AgentState)
        graph.add_node("supervisor_start", self._supervisor_start)
        graph.add_node("planner", run_execution_planner_agent)
        graph.add_node("retrieval", run_retrieval_agent)
        graph.add_node("graph", run_graph_role_agent)
        graph.add_node("web_search", run_web_search_agent)
        graph.add_node("specialists", run_domain_specialists)
        graph.add_node("negotiator", run_negotiator_agent)
        graph.add_node("evidence", run_evidence_agent)
        graph.add_node("strategy", run_strategy_agent)
        graph.add_node("appeal", run_negotiation_agent)
        graph.add_node("review", run_review_agent)
        graph.add_node("response", run_response_agent)
        graph.add_node("supervisor_done", self._supervisor_done)

        graph.add_edge(START, "supervisor_start")
        graph.add_edge("supervisor_start", "planner")
        graph.add_edge("planner", "retrieval")
        graph.add_edge("retrieval", "graph")
        graph.add_edge("graph", "web_search")
        graph.add_edge("web_search", "specialists")
        graph.add_conditional_edges(
            "specialists",
            self._after_specialists,
            {"negotiator": "negotiator", "evidence": "evidence"},
        )
        graph.add_edge("negotiator", "evidence")
        graph.add_edge("evidence", "strategy")
        graph.add_edge("strategy", "appeal")
        graph.add_edge("appeal", "review")
        # Same hard gate as case_analysis_workflow.py: run_review_agent sets
        # review_should_retry when it finds a hallucinated claim or a
        # miscited clause, capped at one retry -- previously this graph
        # flowed review -> response unconditionally, so a rejected strategy
        # still shipped to the user unchanged on this (more heavily used)
        # planner-driven path too.
        graph.add_conditional_edges(
            "review",
            lambda state: "strategy" if state.get("review_should_retry") else "response",
            {"strategy": "strategy", "response": "response"},
        )
        graph.add_edge("response", "supervisor_done")
        graph.add_edge("supervisor_done", END)
        return graph.compile()

    async def _run_fallback(self, state: AgentState) -> AgentState:
        state = await self._supervisor_start(state)
        state = await run_execution_planner_agent(state)
        state = await run_retrieval_agent(state)
        state = await run_graph_role_agent(state)
        state = await run_web_search_agent(state)
        state = await run_domain_specialists(state)

        if self._after_specialists(state) == "negotiator":
            state = await run_negotiator_agent(state)
        state = await run_evidence_agent(state)
        state = await run_strategy_agent(state)
        state = await run_negotiation_agent(state)
        state = await run_review_agent(state)
        if state.get("review_should_retry"):
            state = await run_strategy_agent(state)
            state = await run_negotiation_agent(state)
            state = await run_review_agent(state)
        state = await run_response_agent(state)
        return await self._supervisor_done(state)

    async def _supervisor_start(self, state: AgentState) -> AgentState:
        state.setdefault("agent_trace", []).append("supervisor:start")
        state.setdefault("llm_call_count", 0)
        state["workflow_engine"] = "langgraph" if self._graph is not None else "fallback"
        await self._record_citizen_case(state)
        await self._load_memory(state)
        return state

    async def _load_memory(self, state: AgentState) -> None:
        """Best-effort: load this citizen's long-term memory (past cases,
        appeals, reports) plus this case's own history, and fold a summary
        into retrieved_context so follow-up conversations have continuity."""
        user_id = state.get("user_id")
        case_id = state.get("case_id")
        if not user_id:
            return
        try:
            from app.services.memory_service import (
                format_memory_for_prompt, get_case_memory, get_user_memory,
            )
            user_memory = await get_user_memory(user_id)
            case_memory = await get_case_memory(case_id, user_id) if case_id else None
            memory_text = format_memory_for_prompt(user_memory, case_memory)
            state["memory_context"] = memory_text
            if memory_text:
                existing = state.get("retrieved_context", "")
                state["retrieved_context"] = f"{existing}\n\nCitizen memory:\n{memory_text}".strip()
                state.setdefault("agent_trace", []).append("memory:loaded")
        except Exception:
            pass

    async def _record_citizen_case(self, state: AgentState) -> None:
        """Best-effort: link this case into the cross-domain Enterprise
        Knowledge Graph (Citizen -> Case -> Institution/Domain). Never blocks
        or fails the case on a graph-store hiccup.

        Uses base_case_id (the real, saved case's id) when present, not
        case_id -- multi_domain_workflow.py runs this whole workflow once
        PER matched domain with case_id set to f"{base_case_id}-{domain}"
        (e.g. "abc123-banking", "abc123-telecom") for internal per-domain
        state isolation, but only ever saves ONE actual case record under
        the bare base_case_id. Recording base_case_id here keeps the
        Knowledge Graph's citizen_case entries pointing at case IDs that
        really exist, so "My Knowledge Footprint" -> click a case ->
        Reasoning Trail actually resolves instead of 404ing on a synthetic
        per-domain suffix that was never a real case."""
        user_id = state.get("user_id")
        case_id = state.get("base_case_id") or state.get("case_id")
        domain = state.get("domain")
        if not user_id or not case_id or not domain:
            return
        try:
            from app.knowledge_graph.neo4j.service import knowledge_graph
            await knowledge_graph.upsert_citizen_case(
                user_id=user_id,
                domain=domain,
                case_id=case_id,
                institution_name=state.get("institution_name"),
                title=state.get("case_summary", "")[:200],
            )
        except Exception:
            pass

    async def _supervisor_done(self, state: AgentState) -> AgentState:
        state.setdefault("agent_trace", []).append("supervisor:done")
        return state

    def _after_specialists(self, state: AgentState) -> str:
        if state.get("plan", {}).get("tools", {}).get("negotiator", False):
            return "negotiator"
        return "evidence"


case_workflow = CaseWorkflow()
