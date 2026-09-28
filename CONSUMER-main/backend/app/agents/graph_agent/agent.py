from app.agents.state import AgentState
from app.knowledge_graph.neo4j.service import knowledge_graph


async def run_graph_agent(state: AgentState) -> AgentState:
    patterns = await knowledge_graph.find_institution_patterns(state["domain"], state["institution_name"])
    similar = await knowledge_graph.find_similar_cases(state["domain"], state["institution_name"], limit=3)
    lines = [p.get("pattern", "") for p in patterns if p.get("pattern")]
    for case in similar:
        if case.get("title"):
            lines.append(f"Similar case: {case.get('title')} — {case.get('summary', '')[:200]}")
    state["graph_context"] = "\n".join(lines)
    if lines:
        state["retrieved_context"] = f"{state.get('retrieved_context', '')}\n\nGraph memory:\n{state['graph_context']}".strip()
    state.setdefault("agent_trace", []).append("graph:neo4j")
    return state
