from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, collection: str, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_batch(self, collection: str, points: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, collection: str, point_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def collection_exists(self, collection: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def count(self, collection: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError

    def flush(self, collection: str | None = None) -> None:
        return None

    def get_dimension(self, collection: str) -> int | None:
        """Vector size actually stored in `collection`, or None if empty/missing."""
        return None
