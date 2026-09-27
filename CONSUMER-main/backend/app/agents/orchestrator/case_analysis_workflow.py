"""Case Analysis Workflow â€” the main LangGraph pipeline.

Upload Documents â†’ Research â†’ Evidence â†’ Knowledge Graph â†’
Strategy â†’ Negotiation â†’ Review â†’ Final Report

This is the core workflow that processes a health insurance case
through all agents in sequence using LangGraph.
"""

from __future__ import annotations

from app.agents.evidence_agent.agent import run_evidence_agent
from app.agents.final_report_agent.agent import run_final_report_agent
from app.agents.graph_agent.agent import run_graph_agent
from app.agents.negotiation_agent.agent import run_negotiation_agent
from app.agents.research_agent.agent import run_research_agent
from app.agents.review_agent.agent import run_review_agent
from app.agents.state import AgentState
from app.agents.strategy_agent.agent import run_strategy_agent


class CaseAnalysisWorkflow:
    """Linear LangGraph pipeline for full health insurance case analysis.

    Pipeline:
    init â†’ research â†’ evidence â†’ graph â†’ strategy â†’ negotiation â†’ review â†’ final_report â†’ done

    Each agent has a single responsibility and writes structured output
    to the shared AgentState.
    """

    def __init__(self) -> None:
        self._graph = self._compile_graph()

    async def run(self, state: AgentState) -> AgentState:
        """Run the full case analysis pipeline."""
        if self._graph is not None:
            return await self._graph.ainvoke(state)
        return await self._run_fallback(state)


    async def run_until(self, state: AgentState, stop_after: str) -> AgentState:
        """Run the case pipeline until a named stage for partial APIs/services."""
        stages = {
            "research": [run_research_agent],
            "evidence": [run_research_agent, run_evidence_agent],
            "graph": [run_research_agent, run_evidence_agent, run_graph_agent],
            "strategy": [run_research_agent, run_evidence_agent, run_graph_agent, run_strategy_agent],
            "negotiation": [run_research_agent, run_evidence_agent, run_graph_agent, run_strategy_agent, run_negotiation_agent],
            "review": [run_research_agent, run_evidence_agent, run_graph_agent, run_strategy_agent, run_negotiation_agent, run_review_agent],
            "final_report": [run_research_agent, run_evidence_agent, run_graph_agent, run_strategy_agent, run_negotiation_agent, run_review_agent, run_final_report_agent],
        }
        if stop_after not in stages:
            raise ValueError(f"Unknown stop_after stage: {stop_after}")
        state = await self._init(state)
        for stage in stages[stop_after]:
            state = await stage(state)
        return await self._done(state)

    async def run_research_only(self, state: AgentState) -> AgentState:
        """Run only research + graph agents for quick research queries."""
        state = await self._init(state)
        state = await run_research_agent(state)
        state = await run_graph_agent(state)
        return state

    async def run_appeal_only(self, state: AgentState) -> AgentState:
        """Run the appeal generation pipeline, auto-filling missing prerequisites."""
        state = await self._init(state)
        if not state.get("research_summary"):
            state = await run_research_agent(state)
            state = await run_graph_agent(state)
        if not state.get("evidence_summary"):
            state = await run_evidence_agent(state)
        if not state.get("strategy"):
            state = await run_strategy_agent(state)
        state = await run_negotiation_agent(state)
        state = await run_review_agent(state)
        return state

    def _compile_graph(self):
        """Compile the LangGraph StateGraph. Returns None if LangGraph is unavailable."""
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None

        graph = StateGraph(AgentState)

        # Define nodes â€” each agent is a node
        graph.add_node("init", self._init)
        graph.add_node("research", run_research_agent)
        graph.add_node("evidence", run_evidence_agent)
        graph.add_node("graph", run_graph_agent)
        graph.add_node("strategy", run_strategy_agent)
        graph.add_node("negotiation", run_negotiation_agent)
        graph.add_node("review", run_review_agent)
        graph.add_node("final_report", run_final_report_agent)
        graph.add_node("done", self._done)

        # Define edges â€” linear pipeline, except review can send the case
        # back to strategy once for a corrective re-pass (see run_review_agent).
        graph.add_edge(START, "init")
        graph.add_edge("init", "research")
        graph.add_edge("research", "evidence")
        graph.add_edge("evidence", "graph")
        graph.add_edge("graph", "strategy")
        graph.add_edge("strategy", "negotiation")
        graph.add_edge("negotiation", "review")
        graph.add_conditional_edges(
            "review",
            lambda state: "strategy" if state.get("review_should_retry") else "final_report",
            {"strategy": "strategy", "final_report": "final_report"},
        )
        graph.add_edge("final_report", "done")
        graph.add_edge("done", END)

        return graph.compile()

    async def _run_fallback(self, state: AgentState) -> AgentState:
        """Deterministic fallback when LangGraph is not installed. Mirrors
        the compiled graph's review->strategy retry loop (see run_review_agent)."""
        state = await self._init(state)
        state = await run_research_agent(state)
        state = await run_evidence_agent(state)
        state = await run_graph_agent(state)
        state = await run_strategy_agent(state)
        state = await run_negotiation_agent(state)
        state = await run_review_agent(state)
        if state.get("review_should_retry"):
            state = await run_strategy_agent(state)
            state = await run_negotiation_agent(state)
            state = await run_review_agent(state)
        state = await run_final_report_agent(state)
        return await self._done(state)

    async def _init(self, state: AgentState) -> AgentState:
        """Initialize workflow metadata."""
        state.setdefault("agent_trace", []).append("case_analysis:start")
        state.setdefault("llm_call_count", 0)
        state["workflow_engine"] = "langgraph" if self._graph is not None else "fallback"
        return state

    async def _done(self, state: AgentState) -> AgentState:
        """Finalize workflow."""
        state.setdefault("agent_trace", []).append("case_analysis:done")
        return state


case_analysis_workflow = CaseAnalysisWorkflow()

