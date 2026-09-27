from app.models.domain import Domain
from app.rag.chunking.text import chunk_text
from app.rag.retrieval.qdrant_service import qdrant_service


class IndexingService:
    async def index_document_text(self, domain: Domain, document_id: str, text: str, metadata: dict) -> int:
        chunks = chunk_text(text)
        return await qdrant_service.upsert_chunks(domain, document_id, chunks, metadata)


indexing_service = IndexingService()
