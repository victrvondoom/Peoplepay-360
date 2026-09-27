"""Memory layer — conversation memory (this case's event history), case
memory (this case's documents/agent runs/appeals), and long-term user memory
(a citizen's previous appeals/evidence/reports across all their past cases),
built on the existing CaseRepository rather than a new store.
"""
from __future__ import annotations

from app.database.postgres.repositories import CaseRepository

_repo = CaseRepository()

MAX_USER_HISTORY_CASES = 5
MAX_SUMMARY_CHARS = 300


async def get_conversation_memory(case_id: str) -> list[dict]:
    """Chronological event history for a single case — the conversation so far."""
    return await _repo.list_events(case_id)


async def get_case_memory(case_id: str, user_id: str) -> dict:
    """Everything remembered about one case: the case record, its documents,
    agent runs, and appeal drafts generated so far."""
    case = await _repo.get_case(case_id, user_id)
    if not case:
        return {"case_id": case_id, "found": False}
    return {
        "case_id": case_id,
        "found": True,
        "case": case,
        "documents": await _repo.list_documents(case_id),
        "agent_runs": await _repo.list_agent_runs(case_id),
        "appeals": await _repo.list_appeals(case_id),
    }


async def get_user_memory(user_id: str, limit: int = MAX_USER_HISTORY_CASES) -> dict:
    """Long-term memory: a citizen's past cases across every domain, with
    their most recent appeals/evidence so a new query can build on prior
    context instead of starting cold each time."""
    cases = await _repo.list_cases(user_id)
    cases_sorted = sorted(cases, key=lambda c: c.get("id", ""), reverse=True)[:limit]

    previous_appeals: list[dict] = []
    previous_reports: list[dict] = []
    for case in cases_sorted:
        case_id = case.get("id")
        if not case_id:
            continue
        for appeal in await _repo.list_appeals(case_id):
            previous_appeals.append({
                "case_id": case_id,
                "domain": case.get("domain"),
                "title": appeal.get("title"),
                "content_summary": str(appeal.get("content", ""))[:MAX_SUMMARY_CHARS],
            })
        for run in await _repo.list_agent_runs(case_id):
            if run.get("status") == "completed" and run.get("output_payload"):
                previous_reports.append({
                    "case_id": case_id,
                    "domain": case.get("domain"),
                    "workflow_name": run.get("workflow_name"),
                    "summary": str(run.get("output_payload", ""))[:MAX_SUMMARY_CHARS],
                })

    return {
        "user_id": user_id,
        "total_past_cases": len(cases),
        "domains_seen": sorted({c.get("domain") for c in cases if c.get("domain")}),
        "recent_cases": [
            {"case_id": c.get("id"), "domain": c.get("domain"), "title": c.get("title"), "status": c.get("status")}
            for c in cases_sorted
        ],
        "previous_appeals": previous_appeals[:limit],
        "previous_reports": previous_reports[:limit],
    }


def format_memory_for_prompt(user_memory: dict, case_memory: dict | None = None) -> str:
    """Render memory as plain text the LLM can read alongside retrieved
    context, so follow-up conversations and repeat citizens get continuity."""
    lines: list[str] = []
    if user_memory.get("total_past_cases"):
        lines.append(
            f"This citizen has {user_memory['total_past_cases']} prior case(s) across: "
            f"{', '.join(user_memory['domains_seen']) or 'none'}."
        )
        for appeal in user_memory.get("previous_appeals", [])[:3]:
            lines.append(f"- Previous appeal ({appeal['domain']}): {appeal['title']} — {appeal['content_summary']}")
    if case_memory and case_memory.get("found"):
        appeals = case_memory.get("appeals", [])
        if appeals:
            lines.append(f"This case already has {len(appeals)} prior appeal draft(s) on file.")
    return "\n".join(lines)
