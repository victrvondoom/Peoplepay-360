from app.rag.indexing.service import indexing_service
from app.knowledge_graph.neo4j.service import knowledge_graph


async def index_case_document(domain, document_id: str, text: str, metadata: dict) -> int:
    return await indexing_service.index_document_text(domain, document_id, text, metadata)


async def sync_case_to_graph(case: dict) -> dict:
    return await knowledge_graph.upsert_case_graph(case)
