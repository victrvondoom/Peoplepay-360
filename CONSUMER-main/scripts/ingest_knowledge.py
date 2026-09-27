import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.domain import Domain
from app.services.knowledge_ingestion import knowledge_ingestion_service


def parse_domain(value: str) -> Domain:
    try:
        return Domain(value)
    except ValueError as exc:
        valid = ", ".join(domain.value for domain in Domain)
        raise argparse.ArgumentTypeError(f"Unknown domain '{value}'. Valid domains: {valid}") from exc


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PROXY domain knowledge into Qdrant and Neo4j.")
    parser.add_argument("--domain", type=parse_domain, default=Domain.HEALTH_INSURANCE)
    parser.add_argument("--path", type=Path, default=None, help="Knowledge folder path. Defaults to knowledge/<domain>.")
    args = parser.parse_args()

    knowledge_root = args.path or ROOT / "knowledge" / args.domain.value
    result = await knowledge_ingestion_service.ingest_path(args.domain, knowledge_root)
    print("Knowledge ingestion complete")
    print(f"Domain: {result['domain']}")
    print(f"Root: {result['root']}")
    print(f"Documents found: {result['documents_found']}")
    print(f"Documents ingested: {result['documents_ingested']}")
    print(f"Chunks indexed: {result['chunks_indexed']}")


if __name__ == "__main__":
    asyncio.run(main())
