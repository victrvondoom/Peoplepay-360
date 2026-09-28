from app.agents.state import AgentState
from app.services.web_search import web_search_service


async def run_web_search_agent(state: AgentState) -> AgentState:
    if not state.get("plan", {}).get("tools", {}).get("web_search", False):
        return state
    query = state.get("case_summary", "")
    try:
        results = await web_search_service.search(query, max_results=5)
    except Exception as exc:
        state.setdefault("agent_trace", []).append(f"web_search:error:{exc}")
        state["web_search_results"] = []
        return state
    if not results:
        state.setdefault("agent_trace", []).append("web_search:no_results")
        state["web_search_results"] = []
        return state
    formatted = "\n\n".join(
        f"Title: {item['title']}\nURL: {item['url']}\nSnippet: {item['snippet']}"
        for item in results
    )
    state["retrieved_context"] = f"{state.get('retrieved_context', '')}\n\nWeb search results:\n{formatted}".strip()
    state["web_search_results"] = results
    state.setdefault("agent_trace", []).append("web_search:tavily")
    return state
