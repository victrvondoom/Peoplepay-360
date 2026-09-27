import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
insurers_root = ROOT / "knowledge" / "health_insurance" / "insurers"
registry = json.loads((insurers_root / "insurer_registry.json").read_text(encoding="utf-8"))

print("Insurer PDF coverage:")
zero_pdfs = []
zero_relevant = []
for insurer in registry["insurers"]:
    insurer_id = insurer["id"]
    insurer_dir = insurers_root / insurer_id
    pdfs = list(insurer_dir.rglob("*.pdf")) if insurer_dir.exists() else []
    relevant = 0
    metadata_dir = insurers_root / "metadata" / insurer_id
    if metadata_dir.exists():
        for meta_path in metadata_dir.glob("*.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("health_insurance_relevant"):
                relevant += 1
    pdf_status = "OK" if pdfs else "MISSING"
    rel_status = "OK" if relevant else "NOT_INDEXED"
    print(f"  {insurer_id}: {len(pdfs)} PDFs [{pdf_status}], {relevant} curated-relevant [{rel_status}]")
    if not pdfs:
        zero_pdfs.append(insurer_id)
    if not relevant:
        zero_relevant.append(insurer_id)

print(f"\nTotal insurers: {len(registry['insurers'])}")
print(f"With PDFs: {len(registry['insurers']) - len(zero_pdfs)}")
print(f"Curated-relevant: {len(registry['insurers']) - len(zero_relevant)}")
if zero_relevant:
    print(f"Not indexed yet: {', '.join(zero_relevant)}")
