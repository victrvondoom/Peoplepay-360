import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings
from app.rag.retrieval.jsonl_vector_store import JsonlVectorStore
from app.rag.retrieval.qdrant_vector_store import QdrantVectorStore


def migrate(batch_size: int = 100, collection_filter: str | None = None) -> dict:
    settings = get_settings()
    jsonl = JsonlVectorStore()
    qdrant = QdrantVectorStore()

    files = jsonl.iter_collection_files()
    if collection_filter:
        files = [path for path in files if path.stem == collection_filter]
    read_total = 0
    upserted_total = 0
    per_collection: dict[str, dict] = {}

    for path in files:
        collection, records = jsonl.read_collection_file(path)
        read_total += len(records)
        collection_upserted = 0
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            collection_upserted += qdrant.upsert_batch(collection, batch)
        confirmed = qdrant.count(collection)
        per_collection[collection] = {
            "read": len(records),
            "upserted_batches": collection_upserted,
            "confirmed_in_qdrant": confirmed,
        }
        upserted_total += collection_upserted

    confirmed_total = sum(item["confirmed_in_qdrant"] for item in per_collection.values())
    return {
        "qdrant_url": settings.qdrant_url,
        "collection_filter": collection_filter,
        "collections": len(files),
        "records_read": read_total,
        "records_upserted": upserted_total,
        "records_confirmed_in_qdrant": confirmed_total,
        "per_collection": per_collection,
        "match": read_total == confirmed_total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate JSONL vector embeddings to Qdrant.")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--collection", help="Optional collection name, for example proxy_ecommerce")
    args = parser.parse_args()
    result = migrate(batch_size=args.batch_size, collection_filter=args.collection)
    print(json.dumps(result, indent=2))
    if not result["match"]:
        print(
            f"WARNING: count mismatch - read {result['records_read']}, "
            f"confirmed {result['records_confirmed_in_qdrant']}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
