"""Personal reporting: aggregate stats across every case/appeal/document a
user has, plus a full exportable report for a single case -- built entirely
from data that already existed (cases, appeals, documents, events) but was
never surfaced as a coherent report anywhere in the product.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, get_current_user
from app.database.postgres.repositories import case_repository

router = APIRouter()


@router.get("/events")
async def list_events(limit: int = 30, before: str | None = None, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """Paginated real event feed for the Notifications page -- /summary's
    recent_activity is capped at 20 and has no cursor, so it can't support
    scroll-to-load-more or a multi-week activity heatmap."""
    events = await case_repository.list_events_for_user(user.id, limit=limit, before=before)
    return [
        {
            "id": event.get("id"),
            "case_id": event.get("case_id"),
            "event_type": event.get("event_type"),
            "title": event.get("title"),
            "body": event.get("body"),
            "actor": event.get("actor"),
            "created_at": event.get("created_at"),
        }
        for event in events
    ]


@router.get("/summary")
async def report_summary(user: CurrentUser = Depends(get_current_user)) -> dict:
    cases = await case_repository.list_cases(user.id)
    appeals = await case_repository.list_appeals_for_user(user.id)
    documents = await case_repository.list_documents_for_user(user.id)
    events = await case_repository.list_events_for_user(user.id, limit=20)

    domain_counter: Counter[str] = Counter()
    for case in cases:
        domain = case.get("domain")
        domain_counter[domain.value if hasattr(domain, "value") else str(domain)] += 1
    for appeal in appeals:
        if appeal.get("domain"):
            domain_counter[appeal["domain"]] += 1
    for doc in documents:
        if doc.get("domain"):
            domain_counter[doc["domain"]] += 1

    status_counter: Counter[str] = Counter(appeal.get("status", "draft") for appeal in appeals)
    resolved = status_counter.get("resolved", 0)
    total_appeals = len(appeals)

    case_status_counter: Counter[str] = Counter(
        case["status"].value if hasattr(case["status"], "value") else str(case["status"]) for case in cases
    )

    return {
        "totals": {
            "cases": len(cases),
            "appeals": total_appeals,
            "documents": len(documents),
            "domains_engaged": len(domain_counter),
        },
        "resolution_rate": round(resolved / total_appeals, 3) if total_appeals else None,
        "domain_breakdown": [{"domain": domain, "count": count} for domain, count in domain_counter.most_common()],
        "appeal_status_breakdown": [{"status": status, "count": count} for status, count in status_counter.items()],
        "case_status_breakdown": [{"status": status, "count": count} for status, count in case_status_counter.items()],
        "recent_activity": [
            {
                "id": event.get("id"),
                "case_id": event.get("case_id"),
                "event_type": event.get("event_type"),
                "title": event.get("title"),
                "body": event.get("body"),
                "actor": event.get("actor"),
                "created_at": event.get("created_at"),
            }
            for event in events
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/case/{case_id}")
async def case_report(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """A full report for one case including the latest AI analysis output."""
    case = await case_repository.get_case(case_id, user.id)
    appeals = [a for a in await case_repository.list_appeals(case_id) if a["user_id"] == user.id]
    documents = [d for d in await case_repository.list_documents(case_id) if d["user_id"] == user.id]
    events = await case_repository.list_events(case_id)
    agent_runs = await case_repository.list_agent_runs(case_id)

    if not case and (appeals or documents):
        domain = (appeals[0].get("domain") if appeals else None) or (documents[0].get("domain") if documents else None)
        case = {
            "id": case_id,
            "user_id": user.id,
            "domain": domain,
            "title": appeals[0]["title"] if appeals else documents[0]["filename"],
            "institution_name": "Not specified",
            "summary": "Generated from an AI Assistant conversation, not a manually created case.",
            "status": "intake",
            "synthetic": True,
        }

    # Extract real AI output from the latest completed agent run
    latest_output: dict = {}
    if agent_runs:
        latest_output = agent_runs[-1].get("output", {}) or {}

    return {
        "case": case,
        "appeals": appeals,
        "documents": documents,
        "events": sorted(events, key=lambda e: e.get("created_at") or "", reverse=True),
        "agent_runs": agent_runs,
        # Flattened for easy frontend consumption
        "latest_analysis": {
            "research_summary": latest_output.get("research_summary", ""),
            "evidence_summary": latest_output.get("evidence_summary", ""),
            "strategy": latest_output.get("strategy", ""),
            "appeal_draft": latest_output.get("appeal_draft", ""),
            "final_report": latest_output.get("final_report") or latest_output.get("final_answer", ""),
            "review_notes": latest_output.get("review_notes", []),
            "citations": latest_output.get("citations", []),
            "agent_trace": latest_output.get("agent_trace", []),
            "llm_call_count": latest_output.get("llm_call_count", 0),
            "embedding_mode": latest_output.get("embedding_mode", ""),
        },
    }
