import argparse
import asyncio
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.domain import Domain
from app.services.insurer_document_curation import is_health_relevant
from app.services.knowledge_ingestion import knowledge_ingestion_service

INSURER_IDS = {
    "star health": "star_health",
    "hdfc ergo": "hdfc_ergo",
    "niva bupa": "niva_bupa",
    "icici lombard": "icici_lombard",
    "care health": "care_health",
    "aditya birla": "aditya_birla_health",
    "tata aig": "tata_aig",
    "bajaj allianz": "bajaj_allianz",
    "reliance general": "reliance_general",
    "united india": "united_india",
}


def resolve_insurer_id(name: str) -> str:
    lower = name.lower().strip()
    for key, insurer_id in INSURER_IDS.items():
        if key in lower:
            return insurer_id
    return re.sub(r"[^a-z0-9]+", "_", lower).strip("_")


async def manual_ingest(insurer_name: str, file_path: Path, category: str = "policy_wording") -> dict:
    insurer_id = resolve_insurer_id(insurer_name)
    output_root = ROOT / "knowledge" / "health_insurance" / "insurers"
    target_dir = output_root / insurer_id / category
    metadata_dir = output_root / "metadata" / insurer_id
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    destination = target_dir / file_path.name
    shutil.copy2(file_path, destination)
    metadata = {
        "insurer_id": insurer_id,
        "insurer_name": insurer_name,
        "category": category,
        "label": file_path.name,
        "url": f"manual://{file_path.name}",
        "final_url": f"manual://{file_path.name}",
        "content_type": "application/pdf",
        "content_sha256": str(uuid5(NAMESPACE_URL, destination.as_posix())),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "file_path": str(destination),
        "official_domain": "manual_ingest",
        "ingestion_source": "manual",
        "health_insurance_relevant": True,
    }
    metadata["health_insurance_relevant"] = is_health_relevant(metadata)
    metadata_path = metadata_dir / f"{destination.stem}.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    backlog_path = output_root / "manual_ingest_backlog.jsonl"
    with backlog_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "insurer_id": insurer_id,
                    "insurer_name": insurer_name,
                    "file_path": str(destination),
                    "resolved_by": "manual_ingest",
                    "logged_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            + "\n"
        )

    ingestion = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, output_root)
    return {"metadata": metadata, "ingestion_summary": {
        "documents_ingested": ingestion["documents_ingested"],
        "chunks_indexed": ingestion["chunks_indexed"],
    }}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Manually ingest an insurer PDF into the healthcare knowledge pipeline.")
    parser.add_argument("--insurer", required=True, help='Insurer name, e.g. "Star Health"')
    parser.add_argument("--file", required=True, type=Path, help="Path to PDF file")
    parser.add_argument("--category", default="policy_wording")
    args = parser.parse_args()
    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")
    result = await manual_ingest(args.insurer, args.file, args.category)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
