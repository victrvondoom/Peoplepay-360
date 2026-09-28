from pydantic import BaseModel, Field
from app.models.domain import Domain


class DocumentUploadResponse(BaseModel):
    document_id: str
    case_id: str
    filename: str
    storage_path: str
    indexed: bool = False
    extraction_method: str = "none"
    ocr_applied: bool = False
    pages_ocrd: int = 0
    text_chars: int = 0
    text_preview: str = ""
    relevance_warning: str | None = None


class SearchRequest(BaseModel):
    domain: Domain = Domain.HEALTH_INSURANCE
    query: str = Field(min_length=3, max_length=1000)
    case_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class SearchHit(BaseModel):
    id: str
    score: float
    text: str
    metadata: dict


class SearchResponse(BaseModel):
    hits: list[SearchHit]
