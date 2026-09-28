from app.agents.graph_agent.agent import run_graph_agent
from app.agents.state import AgentState


async def run_graph_role_agent(state: AgentState) -> AgentState:
    if not state.get("plan", {}).get("tools", {}).get("knowledge_graph", False):
        return state
    state = await run_graph_agent(state)
    state.setdefault("agent_trace", []).append("graph:neo4j")
    return state
