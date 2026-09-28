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
from app.services.insurer_document_collector import InsurerDocumentCollector
from app.services.knowledge_ingestion import knowledge_ingestion_service


async def main() -> None:
    parser = argparse.ArgumentParser(description="Download official insurer health insurance PDFs and ingest them.")
    parser.add_argument("--insurer", action="append", help="Optional insurer id. Can be repeated.")
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args()

    output_root = ROOT / "knowledge" / "health_insurance" / "insurers"
    registry_path = output_root / "insurer_registry.json"
    collector = InsurerDocumentCollector(registry_path, output_root)
    report = collector.collect(set(args.insurer) if args.insurer else None)
    print(json.dumps(report, indent=2))

    if not args.skip_ingest:
        ingestion = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, output_root)
        print(json.dumps({"ingestion": ingestion}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
