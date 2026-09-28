from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.rag.retrieval.vector_store import VectorStore


class QdrantVectorStore(VectorStore):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        from qdrant_client import QdrantClient

        # Default REST timeout (5s) is too short for batch upserts of 100+
        # points with 1024-dim vectors against a free-tier cluster -- writes
        # were confirmed to genuinely take longer than that under real load,
        # not hang indefinitely, so a longer timeout (not a retry-storm) is
        # the correct fix.
        self._client = QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key, timeout=60)
        return self._client

    def _ensure_collection(self, collection: str, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()
        if not client.collection_exists(collection):
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, collection: str, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.upsert_batch(collection, [{"id": point_id, "vector": vector, "payload": payload}])

    def upsert_batch(self, collection: str, points: list[dict[str, Any]]) -> int:
        if not points:
            return 0
        from qdrant_client.models import PointStruct

        vector_size = len(points[0]["vector"])
        self._ensure_collection(collection, vector_size)
        client = self._get_client()
        qdrant_points = [
            PointStruct(id=point["id"], vector=point["vector"], payload=point["payload"])
            for point in points
        ]
        client.upsert(collection_name=collection, points=qdrant_points)
        return len(points)

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        if not self.collection_exists(collection):
            return []
        query_filter = None
        if filters:
            query_filter = Filter(
                must=[FieldCondition(key=key, match=MatchValue(value=value)) for key, value in filters.items()]
            )
        hits = self._get_client().search(
            collection_name=collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k,
        )
        return [
            {
                "id": str(hit.id),
                "score": float(hit.score),
                "payload": hit.payload or {},
            }
            for hit in hits
        ]

    def delete(self, collection: str, point_id: str) -> None:
        if self.collection_exists(collection):
            self._get_client().delete(collection_name=collection, points_selector=[point_id])

    def collection_exists(self, collection: str) -> bool:
        return self._get_client().collection_exists(collection)

    def count(self, collection: str) -> int:
        if not self.collection_exists(collection):
            return 0
        info = self._get_client().get_collection(collection)
        return int(info.points_count)

    def get_dimension(self, collection: str) -> int | None:
        if not self.collection_exists(collection):
            return None
        info = self._get_client().get_collection(collection)
        vectors_config = info.config.params.vectors
        if hasattr(vectors_config, "size"):
            return int(vectors_config.size)
        if isinstance(vectors_config, dict) and vectors_config:
            first = next(iter(vectors_config.values()))
            return int(first.size)
        return None

    def health_check(self) -> dict[str, Any]:
        client = self._get_client()
        collections = client.get_collections().collections
        return {
            "status": "ready",
            "backend": "qdrant",
            "url": self.settings.qdrant_url,
            "collections": len(collections),
        }
