from app.agents.state import AgentState


async def run_negotiator_agent(state: AgentState) -> AgentState:
    outputs = state.get("specialist_outputs", [])
    if len(outputs) <= 1:
        return state
    summary = []
    citations: list[str] = state.get("citations", [])
    for output in outputs:
        summary.append(f"{output['agent']}: {output['answer']}")
        citations.extend(output.get("citations", []))
    state["final_answer"] = "\n\n".join(summary)
    state["citations"] = list(dict.fromkeys(citations))
    state.setdefault("agent_trace", []).append("negotiator:merged-specialists")
    return state
