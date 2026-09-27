from __future__ import annotations

from typing import Any

from app.agents.orchestrator.case_analysis_workflow import case_analysis_workflow
from app.agents.state import AgentState
from app.database.postgres.repositories import case_repository
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.schemas.cases import CaseStatus
from app.services.case_context import build_case_summary


def state_to_response(case_id: str, state: AgentState) -> dict[str, Any]:
    strategy = state.get("strategy_decision") or {}
    return {
        "case_id": case_id,
        "status": "ready_for_human_review",
        "embedding_mode": state.get("embedding_mode", "unknown"),
        "workflow_engine": state.get("workflow_engine", ""),
        "research_summary": state.get("research_summary", ""),
        "research_findings": state.get("research_findings", {}),
        "graph_insights": state.get("graph_insights", {}),
        "evidence_summary": state.get("evidence_summary", ""),
        "evidence_facts": state.get("evidence_facts", {}),
        "strategy": state.get("strategy", ""),
        "strategy_decision": strategy,
        "can_appeal": strategy.get("can_appeal"),
        "success_probability": strategy.get("success_probability"),
        "appeal_draft": state.get("appeal_draft", ""),
        "negotiation_outputs": state.get("negotiation_outputs", {}),
        "review_notes": state.get("review_notes", []),
        "review_flags": state.get("review_flags", {}),
        "final_report": state.get("final_report", ""),
        "final_answer": state.get("final_answer", ""),
        "citations": state.get("citations", []),
        "agent_trace": state.get("agent_trace", []),
        "llm_call_count": state.get("llm_call_count", 0),
    }


async def load_case_state(case: dict, user_id: str) -> AgentState:
    documents = await case_repository.list_documents(case["id"])
    return {
        "case_id": case["id"],
        "user_id": user_id,
        "domain": case["domain"],
        "institution_name": case["institution_name"],
        "case_summary": build_case_summary(case, documents),
        "case_documents": documents,
    }


async def analyze_case(case: dict, user_id: str, stop_after: str | None = None) -> dict[str, Any]:
    await case_repository.update_case_status(case["id"], CaseStatus.ANALYZING)
    state = await load_case_state(case, user_id)
    if stop_after:
        result = await case_analysis_workflow.run_until(state, stop_after)
    else:
        result = await case_analysis_workflow.run(state)
    output = state_to_response(case["id"], result)
    await case_repository.add_agent_run(case["id"], "case_analysis_workflow", "completed", {"stop_after": stop_after}, output)
    await knowledge_graph.upsert_case_graph(case, {"documents": len(state.get("case_documents", [])), "output": output})
    await case_repository.update_case_status(case["id"], CaseStatus.READY_FOR_APPROVAL)
    await case_repository.add_event(
        case["id"],
        {
            "actor": "agent",
            "event_type": "case_analyzed",
            "title": "Case analysis completed",
            "body": output.get("research_summary", "")[:500],
        },
    )
    return output


async def get_case_history(case_id: str, user_id: str) -> dict[str, Any]:
    case = await case_repository.get_case(case_id, user_id)
    if not case:
        return {}
    documents = await case_repository.list_documents(case_id)
    events = await case_repository.list_events(case_id)
    runs = await case_repository.list_agent_runs(case_id)
    appeals = await case_repository.list_appeals(case_id)
    return {
        "case": case,
        "documents": documents,
        "timeline": events,
        "agent_runs": runs,
        "appeals": appeals,
    }
