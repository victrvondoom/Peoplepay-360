from app.rag.retrieval.factory import get_vector_store
from app.rag.retrieval.jsonl_vector_store import JsonlVectorStore

local_vector_store = get_vector_store()
if not isinstance(local_vector_store, JsonlVectorStore):
    local_vector_store = JsonlVectorStore()
