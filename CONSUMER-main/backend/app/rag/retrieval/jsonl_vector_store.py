from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock

from app.rag.retrieval.vector_store import VectorStore


class JsonlVectorStore(VectorStore):
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("datasets") / "vector_embeddings"
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, dict]] = {}
        self._dirty: set[str] = set()
        # Records upserted/deleted by THIS process since its last flush,
        # kept separate from `_cache` (which is a full point-in-time
        # snapshot). Two ingestion scripts running concurrently against the
        # same domain each load their own in-memory snapshot at startup; if
        # flush() just wrote `_cache` wholesale, whichever process flushed
        # last would silently overwrite the other's additions with its own
        # stale snapshot. Tracking only this process's deltas lets flush()
        # re-read the file fresh and merge instead of clobbering.
        self._pending_upserts: dict[str, dict[str, dict]] = {}
        self._pending_deletes: dict[str, set[str]] = {}

    def _path(self, collection: str) -> Path:
        safe_name = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in collection)
        return self.root / f"{safe_name}.jsonl"

    def _lock(self, collection: str) -> FileLock:
        return FileLock(str(self._path(collection)) + ".lock", timeout=120)

    def _load(self, collection: str) -> dict[str, dict]:
        if collection not in self._cache:
            self._cache[collection] = {record["id"]: record for record in self._read(self._path(collection))}
        return self._cache[collection]

    def upsert(self, collection: str, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.upsert_batch(collection, [{"id": point_id, "vector": vector, "payload": payload}])

    def upsert_batch(self, collection: str, points: list[dict[str, Any]]) -> int:
        if not points:
            return 0
        cache = self._load(collection)
        pending = self._pending_upserts.setdefault(collection, {})
        for point in points:
            cache[point["id"]] = point
            pending[point["id"]] = point
            self._pending_deletes.get(collection, set()).discard(point["id"])
        self._dirty.add(collection)
        return len(points)

    def flush(self, collection: str | None = None) -> None:
        """Cross-process-safe read-merge-write: acquire a lock on the
        collection, re-read whatever is currently on disk (which may include
        writes from another process made after this process's own `_cache`
        was first loaded), overlay this process's own pending upserts/
        deletes on top, then write-to-temp-then-rename so a crash/kill
        mid-write can never truncate or corrupt the previously-durable file
        (os.replace is atomic — readers always see either the old complete
        file or the new complete file, never a partial one)."""
        targets = [collection] if collection else list(self._dirty)
        for name in targets:
            if name not in self._dirty:
                continue
            target_path = self._path(name)
            with self._lock(name):
                merged = {record["id"]: record for record in self._read(target_path)}
                merged.update(self._pending_upserts.get(name, {}))
                for deleted_id in self._pending_deletes.get(name, set()):
                    merged.pop(deleted_id, None)

                fd, tmp_path = tempfile.mkstemp(dir=target_path.parent, prefix=f".{target_path.stem}.", suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        for record in merged.values():
                            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                    os.replace(tmp_path, target_path)
                except BaseException:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise

            self._cache[name] = merged
            self._pending_upserts.pop(name, None)
            self._pending_deletes.pop(name, None)
            self._dirty.discard(name)

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.flush(collection)
        scored: list[dict[str, Any]] = []
        for record in self._load(collection).values():
            payload = record.get("payload", {})
            if filters and any(payload.get(key) != value for key, value in filters.items()):
                continue
            score = self._cosine(vector, record.get("vector", []))
            scored.append({"id": record["id"], "score": score, "payload": payload})
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]

    def delete(self, collection: str, point_id: str) -> None:
        cache = self._load(collection)
        if point_id in cache:
            del cache[point_id]
            self._pending_upserts.get(collection, {}).pop(point_id, None)
            self._pending_deletes.setdefault(collection, set()).add(point_id)
            self._dirty.add(collection)

    def collection_exists(self, collection: str) -> bool:
        return self._path(collection).exists() or collection in self._cache

    def count(self, collection: str) -> int:
        return len(self._load(collection))

    def get_dimension(self, collection: str) -> int | None:
        for record in self._load(collection).values():
            vector = record.get("vector")
            if vector:
                return len(vector)
        return None

    def health_check(self) -> dict[str, Any]:
        collections = list(self.root.glob("*.jsonl"))
        total = sum(self.count(path.stem) for path in collections) if collections else 0
        return {"status": "ready", "backend": "jsonl", "root": str(self.root), "collections": len(collections), "total_points": total}

    def iter_collection_files(self) -> list[Path]:
        return sorted(self.root.glob("*.jsonl"))

    def read_collection_file(self, path: Path) -> tuple[str, list[dict[str, Any]]]:
        collection = path.stem
        return collection, self._read(path)

    def _read(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _cosine(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)
