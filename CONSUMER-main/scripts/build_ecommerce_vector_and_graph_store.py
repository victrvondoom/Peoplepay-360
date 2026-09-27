from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.domain import Domain

DOMAIN = Domain.ECOMMERCE.value
COLLECTION = "proxy_ecommerce"
CHUNK_PATH = ROOT / "knowledge" / "ecommerce" / "chunks" / "ecommerce_chunks.jsonl"
MANIFEST_PATH = ROOT / "knowledge" / "ecommerce" / "ecommerce_corpus_manifest.json"
ENTITY_PATH = ROOT / "knowledge" / "ecommerce" / "knowledge_graph" / "ecommerce_entities.jsonl"
REL_PATH = ROOT / "knowledge" / "ecommerce" / "knowledge_graph" / "ecommerce_relationships.jsonl"
VECTOR_PATH = BACKEND / "datasets" / "vector_embeddings" / f"{COLLECTION}.jsonl"
GRAPH_EVENTS_PATH = BACKEND / "datasets" / "knowledge_graph" / "neo4j_fallback.jsonl"


def hash_embedding(text: str, dimensions: int = 768) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        block = hashlib.sha256(digest + counter.to_bytes(4, "little")).digest()
        values.extend(((byte / 127.5) - 1.0) for byte in block)
        counter += 1
    vector = values[:dimensions]
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def build_vectors() -> dict:
    chunks = read_jsonl(CHUNK_PATH)
    VECTOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    source_paths = set()
    authorities = set()
    with VECTOR_PATH.open("w", encoding="utf-8") as handle:
        for record in chunks:
            source_path = record["source_path"]
            chunk_index = int(record["chunk_index"])
            metadata = record.get("metadata", {})
            point_id = str(uuid5(NAMESPACE_URL, f"{DOMAIN}:{source_path}:{chunk_index}"))
            payload = {
                "document_id": str(uuid5(NAMESPACE_URL, f"{DOMAIN}:{source_path}")),
                "chunk_index": chunk_index,
                "text": record["text"],
                "domain": DOMAIN,
                "source_path": source_path,
                **metadata,
            }
            point = {"id": point_id, "vector": hash_embedding(record["text"]), "payload": payload}
            handle.write(json.dumps(point, ensure_ascii=True) + "\n")
            source_paths.add(source_path)
            if metadata.get("authority"):
                authorities.add(metadata["authority"])
    return {"collection": COLLECTION, "points": len(chunks), "documents": len(source_paths), "authorities": sorted(authorities)}


def append_graph_events() -> dict:
    entities = read_jsonl(ENTITY_PATH)
    relationships = read_jsonl(REL_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {"files": []}
    GRAPH_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing_keys = set()
    if GRAPH_EVENTS_PATH.exists():
        for line in GRAPH_EVENTS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload", {})
            existing_keys.add((event.get("event_type"), json.dumps(payload, sort_keys=True, ensure_ascii=True)))

    added = 0
    with GRAPH_EVENTS_PATH.open("a", encoding="utf-8") as handle:
        def add_event(event_type: str, payload: dict) -> None:
            nonlocal added
            key = (event_type, json.dumps(payload, sort_keys=True, ensure_ascii=True))
            if key in existing_keys:
                return
            handle.write(json.dumps({"event_type": event_type, "payload": payload}, ensure_ascii=True) + "\n")
            existing_keys.add(key)
            added += 1

        for entity in entities:
            add_event("knowledge_entity", entity)
        for relationship in relationships:
            add_event("knowledge_relationship", relationship)
        for file_record in manifest.get("files", []):
            add_event(
                "knowledge_document",
                {
                    "domain": DOMAIN,
                    "document_id": str(uuid5(NAMESPACE_URL, f"{DOMAIN}:{file_record['path']}")),
                    "title": file_record.get("title") or Path(file_record["path"]).stem,
                    "source_path": file_record["path"],
                    "metadata": {
                        "authority": file_record.get("authority"),
                        "category": file_record.get("category"),
                        "source_url": file_record.get("source_url"),
                        "sha256": file_record.get("sha256"),
                        "chunks": file_record.get("chunks"),
                    },
                },
            )
    return {"entities": len(entities), "relationships": len(relationships), "documents": len(manifest.get("files", [])), "events_added": added}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build clean e-commerce vector JSONL and graph fallback events.")
    parser.add_argument("--vectors-only", action="store_true")
    parser.add_argument("--graph-only", action="store_true")
    args = parser.parse_args()
    result: dict = {}
    if not args.graph_only:
        result["vectors"] = build_vectors()
    if not args.vectors_only:
        result["graph"] = append_graph_events()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
