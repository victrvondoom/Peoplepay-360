from fastapi import APIRouter, Depends
from app.auth.dependencies import CurrentUser, get_current_user
from app.rag.retrieval.qdrant_service import qdrant_service
from app.schemas.knowledge import SearchRequest, SearchResponse

router = APIRouter()


@router.post("", response_model=SearchResponse)
async def search_knowledge(payload: SearchRequest, _: CurrentUser = Depends(get_current_user)) -> dict:
    hits = await qdrant_service.search(payload.domain, payload.query, payload.limit, {"case_id": payload.case_id} if payload.case_id else None)
    return {"hits": hits}
