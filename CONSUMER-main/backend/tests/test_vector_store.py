import tempfile
from pathlib import Path

from app.rag.retrieval.jsonl_vector_store import JsonlVectorStore
from app.rag.retrieval.vector_store import VectorStore


def test_jsonl_vector_store_upsert_and_query() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        store: VectorStore = JsonlVectorStore(Path(temp_dir))
        collection = "test_collection"
        store.upsert(collection, "point-1", [1.0, 0.0, 0.0], {"text": "health policy wording", "domain": "health_insurance"})
        store.upsert(collection, "point-2", [0.0, 1.0, 0.0], {"text": "claim procedure", "domain": "health_insurance"})
        store.flush(collection)
        hits = store.query(collection, [1.0, 0.0, 0.0], top_k=1)
        assert len(hits) == 1
        assert hits[0]["payload"]["text"] == "health policy wording"
        assert store.count(collection) == 2
        assert store.collection_exists(collection)
