from fastapi import APIRouter, Depends
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository

router = APIRouter()


@router.get("/{case_id}")
async def list_timeline(case_id: str, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    return await case_repository.list_events(case_id)
