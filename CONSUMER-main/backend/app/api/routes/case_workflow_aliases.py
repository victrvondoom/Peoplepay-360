from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.routes.case_ai import analyze_case, chat_about_case, generate_appeal, get_case_detail, get_case_history, research_case
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository
from app.schemas.case_ai import AnalyzeCaseRequest, AppealCaseRequest, ChatCaseRequest, ResearchCaseRequest
from app.storage.service import storage_service

router = APIRouter()


@router.post("/upload")
async def upload_alias(
    case_id: str = Form(...),
    document_type: str | None = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    return await storage_service.save_case_document(user.id, case, file, document_type=document_type)


@router.post("/analyze")
async def analyze_alias(payload: AnalyzeCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    return await analyze_case(payload, user)


@router.post("/research")
async def research_alias(payload: ResearchCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    return await research_case(payload, user)


@router.post("/appeal")
async def appeal_alias(payload: AppealCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    return await generate_appeal(payload, user)


@router.post("/chat")
async def chat_alias(payload: ChatCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    return await chat_about_case(payload, user)


@router.get("/case/{case_id}")
async def case_detail_alias(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    return await get_case_detail(case_id, user)


@router.get("/history/{case_id}")
async def history_alias(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    return await get_case_history(case_id, user)
