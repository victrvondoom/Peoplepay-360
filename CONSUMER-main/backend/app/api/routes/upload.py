from fastapi import APIRouter, Depends, File, UploadFile
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository
from app.models.domain import ACTIVE_DOMAINS, Domain
from app.schemas.knowledge import DocumentUploadResponse
from app.storage.service import storage_service

router = APIRouter()


@router.get("/documents")
async def list_all_documents(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """Every document the user has uploaded across every case -- the
    Document Vault view, not scoped to a single case."""
    return await case_repository.list_documents_for_user(user.id)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    deleted = await case_repository.delete_document(document_id, user.id)
    if not deleted:
        raise ProxyError("Document not found", status_code=404, code="document_not_found")
    return {"deleted": True, "document_id": document_id}


@router.post("/vault/{domain}", response_model=DocumentUploadResponse)
async def upload_to_vault(domain: Domain, file: UploadFile = File(...), user: CurrentUser = Depends(get_current_user)) -> dict:
    """Upload a document without first creating a dispute case -- gets or
    lazily creates a standing per-domain "Document Vault" case for this user
    and attaches the upload to it. Real text extraction, classification, and
    vector indexing all still happen exactly as with a normal case upload."""
    if domain not in ACTIVE_DOMAINS:
        raise ProxyError(f"Domain '{domain.value}' is registered but not active yet", status_code=409, code="domain_not_active")
    case = await case_repository.get_or_create_vault_case(user.id, domain)
    return await storage_service.save_case_document(user.id, case, file)


@router.post("/{case_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(case_id: str, file: UploadFile = File(...), user: CurrentUser = Depends(get_current_user)) -> dict:
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    return await storage_service.save_case_document(user.id, case, file)


@router.get("/{case_id}/documents/{document_id}/signed-url")
async def get_document_signed_url(
    case_id: str,
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    documents = await case_repository.list_documents(case_id)
    document = next((item for item in documents if item.get("document_id") == document_id or item.get("id") == document_id), None)
    if not document:
        raise ProxyError("Document not found", status_code=404, code="document_not_found")
    signed_url = await storage_service.get_signed_download_url(user.id, case, document)
    return {"document_id": document_id, "signed_url": signed_url, "expires_in_seconds": 300}


@router.get("/{case_id}/documents")
async def list_documents(case_id: str, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    return await case_repository.list_documents(case_id)
