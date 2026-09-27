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
from app.services.knowledge_ingestion import knowledge_ingestion_service
from app.services.official_health_sources import OfficialHealthSourceCollector


async def main() -> None:
    parser = argparse.ArgumentParser(description="Collect official health insurance sources and ingest them.")
    parser.add_argument("--limit", type=int, default=None, help="Optional source count for smoke tests.")
    parser.add_argument("--skip-ingest", action="store_true", help="Only collect files, do not index into Qdrant/Neo4j.")
    args = parser.parse_args()

    output_root = ROOT / "knowledge" / "health_insurance" / "official_sources"
    registry_path = output_root / "source_registry.json"
    collector = OfficialHealthSourceCollector(registry_path, output_root)
    result = collector.collect(limit=args.limit)
    print(json.dumps(result, indent=2))

    if not args.skip_ingest:
        ingest_result = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, output_root)
        print(json.dumps({"ingestion": ingest_result}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
