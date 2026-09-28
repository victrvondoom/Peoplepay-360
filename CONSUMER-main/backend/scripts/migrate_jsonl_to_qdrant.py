"""
One-off migration: move already-embedded chunks from the local JSONL
fallback vector store into a real Qdrant instance, WITHOUT re-calling the
NVIDIA embedding API -- the vectors are already computed and sitting in the
JSONL files, this just re-homes them.

Usage:
    Set QDRANT_URL and QDRANT_API_KEY in the environment (or .env) first --
    this always writes to whatever VECTOR_STORE_BACKEND=qdrant resolves to,
    regardless of the CURRENT backend setting, so it's safe to run before
    flipping VECTOR_STORE_BACKEND over in production.

    python scripts/migrate_jsonl_to_qdrant.py
"""
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.domain import ACTIVE_DOMAINS
from app.rag.retrieval.jsonl_vector_store import JsonlVectorStore
from app.rag.retrieval.qdrant_vector_store import QdrantVectorStore
from app.rag.retrieval.qdrant_service import qdrant_service

# Smaller than the original 200 -- a 200-point batch of 1024-dim vectors
# plus text payload timed out writing to a free-tier cluster even with the
# client's timeout raised to 60s. 64 keeps each request body small enough
# to consistently land well under that.
BATCH_SIZE = 64
MAX_RETRIES = 5


def upsert_with_retry(qdrant_store: QdrantVectorStore, collection_name: str, batch: list) -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            qdrant_store.upsert_batch(collection_name, batch)
            return
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            print(f"    retry {attempt}/{MAX_RETRIES} after error ({exc.__class__.__name__}: {exc}); waiting {wait}s")
            time.sleep(wait)


def main():
    jsonl_store = JsonlVectorStore()
    qdrant_store = QdrantVectorStore()

    grand_total = 0
    for domain in ACTIVE_DOMAINS:
        collection_name = qdrant_service.collection_name(domain)
        records = list(jsonl_store._load(collection_name).values())
        if not records:
            print(f"[{domain.value}] nothing to migrate (0 records in {collection_name})")
            continue

        # A handful of stale records can carry a vector dimension left over
        # from before an embedding-model switch (confirmed live: 2 of 7631
        # health_insurance records were 768-dim leftovers among 7629 correct
        # 1024-dim ones). Qdrant rejects a mismatched dimension with a 400,
        # which is not transient -- retrying it endlessly just wastes time
        # and eventually aborts the whole domain. Detect the dominant
        # dimension and skip only the outliers, so a couple of orphaned
        # records don't block migrating everything else.
        dim_counts = Counter(len(r["vector"]) for r in records)
        target_dim = dim_counts.most_common(1)[0][0]
        good_records = [r for r in records if len(r["vector"]) == target_dim]
        skipped = [r for r in records if len(r["vector"]) != target_dim]
        if skipped:
            print(f"  skipping {len(skipped)} record(s) with non-{target_dim} vector dims: "
                  f"{[(r['id'], r['payload'].get('document_id')) for r in skipped]}")

        print(f"[{domain.value}] migrating {len(good_records)} chunks from {collection_name}...")
        migrated = 0
        for i in range(0, len(good_records), BATCH_SIZE):
            batch = good_records[i : i + BATCH_SIZE]
            upsert_with_retry(qdrant_store, collection_name, batch)
            migrated += len(batch)
            print(f"  {migrated}/{len(good_records)}")

        grand_total += migrated
        print(f"[{domain.value}] done -- {migrated} chunks now in real Qdrant "
              f"({len(skipped)} skipped due to dimension mismatch).\n")

    print(f"Migration complete. Total chunks migrated: {grand_total}")
    print("Verify with: qdrant_service.count(<domain>) after setting VECTOR_STORE_BACKEND=qdrant.")


if __name__ == "__main__":
    main()
