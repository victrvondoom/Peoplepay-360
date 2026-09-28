import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.domain import Domain
from app.services.insurer_document_curation import curate_insurer_metadata
from app.services.knowledge_ingestion import knowledge_ingestion_service


async def ingest_healthcare_all(skip_curation: bool = False) -> dict:
    official_root = ROOT / "knowledge" / "health_insurance" / "official_sources"
    insurers_root = ROOT / "knowledge" / "health_insurance" / "insurers"
    curation = None if skip_curation else curate_insurer_metadata(insurers_root)
    official = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, official_root)
    insurers = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, insurers_root)
    return {"curation": curation, "official_sources": official, "insurers": insurers}


def compact(result: dict) -> dict:
    return {
        "curation": result["curation"],
        "official_sources": {
            "documents_found": result["official_sources"]["documents_found"],
            "documents_ingested": result["official_sources"]["documents_ingested"],
            "chunks_indexed": result["official_sources"]["chunks_indexed"],
            "supabase_chunks": result["official_sources"]["supabase_chunks"],
        },
        "insurers": {
            "documents_found": result["insurers"]["documents_found"],
            "documents_ingested": result["insurers"]["documents_ingested"],
            "chunks_indexed": result["insurers"]["chunks_indexed"],
            "supabase_chunks": result["insurers"]["supabase_chunks"],
            "skipped_empty": result["insurers"]["skipped_empty"],
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Curate and ingest all healthcare knowledge into RAG and graph stores.")
    parser.add_argument("--skip-curation", action="store_true")
    parser.add_argument("--full-results", action="store_true")
    args = parser.parse_args()
    result = await ingest_healthcare_all(skip_curation=args.skip_curation)
    output = result if args.full_results else compact(result)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
