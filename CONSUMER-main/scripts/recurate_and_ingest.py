import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.domain import Domain
from app.services.insurer_document_curation import curate_insurer_metadata
from app.services.knowledge_ingestion import knowledge_ingestion_service


async def main() -> None:
    official_root = ROOT / "knowledge" / "health_insurance" / "official_sources"
    insurers_root = ROOT / "knowledge" / "health_insurance" / "insurers"

    curation = curate_insurer_metadata(insurers_root)
    official = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, official_root)
    insurers = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, insurers_root)

    print(json.dumps({
        "curation": {"relevant": curation["relevant"], "irrelevant": curation["irrelevant"]},
        "official_sources": {
            "documents_ingested": official["documents_ingested"],
            "chunks_indexed": official["chunks_indexed"],
        },
        "insurers": {
            "documents_found": insurers["documents_found"],
            "documents_ingested": insurers["documents_ingested"],
            "chunks_indexed": insurers["chunks_indexed"],
            "skipped_empty": insurers["skipped_empty"],
        },
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
