from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository

router = APIRouter()


@router.get("")
async def list_all_appeals(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """Every appeal document across every one of the user's cases -- the
    Appeals Center view, not scoped to a single case."""
    return await case_repository.list_appeals_for_user(user.id)


class AppealStatusUpdate(BaseModel):
    status: str


@router.patch("/{appeal_id}/status")
async def set_appeal_status(appeal_id: str, payload: AppealStatusUpdate, user: CurrentUser = Depends(get_current_user)) -> dict:
    allowed = {"draft", "sent", "escalated", "resolved"}
    if payload.status not in allowed:
        raise ProxyError(f"status must be one of {sorted(allowed)}", status_code=400, code="invalid_status")
    appeal = await case_repository.update_appeal_status(appeal_id, user.id, payload.status)
    if not appeal:
        raise ProxyError("Appeal not found", status_code=404, code="appeal_not_found")
    return appeal


@router.get("/{case_id}")
async def list_appeals(case_id: str, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    return await case_repository.list_appeals(case_id)
