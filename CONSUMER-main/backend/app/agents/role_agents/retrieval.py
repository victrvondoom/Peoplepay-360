from app.agents.research_agent.agent import run_research_agent
from app.agents.state import AgentState


async def run_retrieval_agent(state: AgentState) -> AgentState:
    if not state.get("plan", {}).get("tools", {}).get("retrieval", True):
        return state
    state = await run_research_agent(state)
    state.setdefault("agent_trace", []).append("retrieval:qdrant")
    return state
