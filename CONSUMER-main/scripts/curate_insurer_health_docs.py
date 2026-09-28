import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.insurer_document_curation import curate_insurer_metadata

if __name__ == "__main__":
    print(json.dumps(curate_insurer_metadata(ROOT / "knowledge" / "health_insurance" / "insurers"), indent=2))
