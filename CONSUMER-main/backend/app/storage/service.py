from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository
from app.database.supabase.client import get_supabase
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.rag.indexing.service import indexing_service
from app.services.case_context import classify_document
from app.services.document_relevance import check_document_relevance
from app.services.ocr_service import ocr_service

TEXT_MIME_PREFIXES = ("text/",)
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json"}
ALLOWED_UPLOAD_MIME = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = get_supabase()

    def _is_text_extractable(self, filename: str, mime_type: str | None) -> bool:
        lower = filename.lower()
        return any(lower.endswith(ext) for ext in TEXT_EXTENSIONS) or bool(mime_type and mime_type.startswith(TEXT_MIME_PREFIXES))

    def _is_pdf(self, filename: str, mime_type: str | None) -> bool:
        lower = filename.lower()
        return lower.endswith(".pdf") or mime_type == "application/pdf"

    def _is_image(self, filename: str, mime_type: str | None) -> bool:
        lower = filename.lower()
        return (
            (mime_type in ALLOWED_UPLOAD_MIME and mime_type.startswith("image/"))
            or lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
        )

    def _validate_upload(self, filename: str, mime_type: str | None, size: int) -> None:
        lower = filename.lower()
        allowed = (
            self._is_pdf(lower, mime_type)
            or self._is_text_extractable(lower, mime_type)
            or (mime_type in ALLOWED_UPLOAD_MIME)
            or lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
        )
        if not allowed:
            raise ProxyError("Only PDF and image uploads are allowed", status_code=400, code="invalid_mime_type")
        if size > MAX_UPLOAD_BYTES:
            raise ProxyError("File exceeds 10MB upload limit", status_code=400, code="file_too_large")

    async def _index_case_text(
        self,
        case: dict,
        user_id: str,
        document_id: str,
        safe_name: str,
        storage_path: str,
        text_extract: str,
        document_type: str,
    ) -> tuple[bool, int]:
        if not text_extract.strip():
            return False, 0
        metadata = {
            "case_id": case["id"],
            "user_id": user_id,
            "filename": safe_name,
            "document_type": document_type,
            "institution_name": case.get("institution_name"),
        }
        chunks_indexed = await indexing_service.index_document_text(case["domain"], document_id, text_extract, metadata)
        await knowledge_graph.upsert_knowledge_document(
            domain=case["domain"],
            document_id=document_id,
            title=safe_name,
            source_path=storage_path,
            metadata=metadata,
        )
        return chunks_indexed > 0, chunks_indexed

    async def save_case_document(
        self,
        user_id: str,
        case: dict,
        file: UploadFile,
        document_type: str | None = None,
    ) -> dict:
        document_id = str(uuid4())
        safe_name = file.filename or f"document-{document_id}"
        storage_path = f"{user_id}/{case['id']}/{document_id}-{safe_name}"
        raw = await file.read()
        self._validate_upload(safe_name, file.content_type, len(raw))

        # Virus-scan hook: run ClamAV sidecar or third-party scanning webhook on `raw` before persisting in production.

        if self.supabase.configured:
            await self.supabase.upload_storage(
                self.settings.storage_bucket_documents,
                storage_path,
                raw,
                file.content_type or "application/octet-stream",
            )

        text_extract = ""
        indexed = False
        chunks_indexed = 0
        extraction_method = "none"
        pages_ocrd = 0
        ocr_applied = False

        if self._is_text_extractable(safe_name, file.content_type):
            text_extract = raw.decode("utf-8", errors="ignore")
            extraction_method = "native"
        elif self._is_pdf(safe_name, file.content_type):
            result = await ocr_service.extract_pdf(raw)
            text_extract = result.text
            extraction_method = result.method
            pages_ocrd = result.pages_ocrd
            ocr_applied = result.method in {"ocr", "mixed"} and result.pages_ocrd > 0
        elif self._is_image(safe_name, file.content_type):
            result = await ocr_service.extract_image(raw, file.content_type)
            text_extract = result.text
            extraction_method = result.method
            pages_ocrd = result.pages_ocrd
            ocr_applied = result.method == "ocr" and bool(result.text)

        resolved_type = document_type or classify_document(safe_name, file.content_type).value

        relevance_warning: str | None = None
        if text_extract.strip():
            domain_val = case.get("domain")
            is_relevant, reason = check_document_relevance(
                text_extract, domain_val, filename=safe_name
            )
            if is_relevant:
                indexed, chunks_indexed = await self._index_case_text(
                    case, user_id, document_id, safe_name, storage_path, text_extract, resolved_type
                )
            else:
                # Store the file but do NOT index it — prevent it from poisoning analysis
                relevance_warning = reason

        domain = case.get("domain")
        document = {
            "id": document_id,
            "document_id": document_id,
            "case_id": case["id"],
            "user_id": user_id,
            "filename": safe_name,
            "mime_type": file.content_type,
            "size_bytes": len(raw),
            "storage_path": storage_path,
            "text_extract": text_extract,
            "document_type": resolved_type,
            "indexed": indexed,
            "chunks_indexed": chunks_indexed,
            "extraction_method": extraction_method,
            "ocr_applied": ocr_applied,
            "pages_ocrd": pages_ocrd,
            "text_chars": len(text_extract),
            # Denormalized so the cross-case Document Vault (list_documents_for_user)
            # can show a domain badge without a join against `cases`.
            "domain": domain.value if hasattr(domain, "value") else domain,
        }
        await case_repository.add_document(document)
        if relevance_warning:
            document["relevance_warning"] = relevance_warning
        document["text_preview"] = text_extract[:240].strip()
        return document

    async def get_signed_download_url(self, user_id: str, case: dict, document: dict, expires_in: int = 300) -> str:
        if document.get("user_id") != user_id or document.get("case_id") != case["id"]:
            raise ProxyError("Document not found", status_code=404, code="document_not_found")
        if not self.supabase.configured:
            raise ProxyError("Storage not configured", status_code=503, code="storage_unavailable")
        signed = await self.supabase.create_signed_url(
            self.settings.storage_bucket_documents,
            document["storage_path"],
            expires_in=expires_in,
        )
        if not signed:
            raise ProxyError("Could not create signed URL", status_code=500, code="signed_url_failed")
        return signed


storage_service = StorageService()
