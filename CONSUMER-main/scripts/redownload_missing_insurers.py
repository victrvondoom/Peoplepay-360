import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.insurer_document_collector import InsurerDocumentCollector

MISSING_INSURERS = [
    "star_health",
    "icici_lombard",
    "care_health",
    "bajaj_allianz",
    "reliance_general",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-download insurer PDFs for insurers with zero coverage.")
    parser.add_argument("--insurer", action="append", help="Optional insurer id. Can be repeated.")
    parser.add_argument("--all-missing", action="store_true", help="Download all insurers with zero PDFs.")
    args = parser.parse_args()

    output_root = ROOT / "knowledge" / "health_insurance" / "insurers"
    registry_path = output_root / "insurer_registry.json"
    collector = InsurerDocumentCollector(registry_path, output_root)

    if args.all_missing:
        targets = set(MISSING_INSURERS)
    elif args.insurer:
        targets = set(args.insurer)
    else:
        targets = set(MISSING_INSURERS)

    report = collector.collect(targets)
    summary = {
        "targets": sorted(targets),
        "total_downloaded": report["total_downloaded"],
        "per_insurer": [
            {
                "insurer_id": result["insurer_id"],
                "downloaded": result["downloaded"],
                "errors": len(result.get("errors", [])),
            }
            for result in report["results"]
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
