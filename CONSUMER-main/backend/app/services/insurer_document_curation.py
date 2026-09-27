from __future__ import annotations

import json
from pathlib import Path

HEALTH_INCLUDE = [
    "health", "medical", "mediclaim", "hospital", "cashless", "critical", "illness", "disease",
    "wellness", "arogya", "sanjeevani", "top up", "super top", "pre existing", "pre-existing",
    "waiting", "portability", "ayush", "ambulance", "organ donor", "day care", "room rent",
    "pre hospitalization", "post hospitalization", "sum insured", "health check", "dental", "opd",
]

CONTEXTUAL_HEALTH_INCLUDE = [
    "accident", "active", "care", "claim", "claims", "coverage", "exclusion", "policy wording",
]

NON_HEALTH_EXCLUDE = [
    "livestock", "cattle", "shrimp", "fish", "crop", "motor", "marine", "fire", "burglary",
    "aviation", "engineering", "liability", "shop", "home insurance", "travel", "tractor",
    "cyber", "commercial", "business secure", "sookshma", "laghu", "griha", "raksha",
    "bharat griha", "property", "domestic", "householder", "vehicle", "car", "two wheeler",
    "baggage", "overseas", "workmen", "money insurance", "personal cyber", "student travel",
]

REQUESTED_CATEGORIES = {
    "policy_wording",
    "product_brochure",
    "claim_procedure",
    "coverage_details",
    "exclusions",
    "waiting_period",
    "add_on_rider",
    "faq",
}


def _term_in_haystack(term: str, haystack: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return False
    if " " in normalized or len(normalized) > 4:
        return normalized in haystack
    return f" {normalized} " in f" {haystack} "


def is_health_relevant(metadata: dict) -> bool:
    haystack = " ".join(
        str(metadata.get(key, ""))
        for key in ["label", "url", "final_url", "file_path", "category", "insurer_name", "official_domain"]
    ).lower()
    if any(_term_in_haystack(term, haystack) for term in NON_HEALTH_EXCLUDE):
        return False
    has_strong_health_signal = any(_term_in_haystack(term, haystack) for term in HEALTH_INCLUDE)
    has_contextual_signal = any(_term_in_haystack(term, haystack) for term in CONTEXTUAL_HEALTH_INCLUDE)
    if "health insurance" in haystack or "mediclaim" in haystack:
        return True
    official_domain = str(metadata.get("official_domain", "")).lower()
    if official_domain.endswith("irdai.gov.in") and has_strong_health_signal:
        return True
    if metadata.get("category") in REQUESTED_CATEGORIES and has_strong_health_signal:
        return True
    if metadata.get("ingestion_source") in {"manual", "manual_api"}:
        return True
    insurer_domain = official_domain not in {"", "irdai.gov.in", "www.irdai.gov.in", "manual_ingest"}
    if insurer_domain and metadata.get("insurer_id") and has_strong_health_signal:
        return True
    return has_strong_health_signal and has_contextual_signal


def curate_insurer_metadata(root: Path) -> dict:
    metadata_files = list((root / "metadata").rglob("*.json"))
    relevant = 0
    irrelevant = 0
    by_insurer: dict[str, dict] = {}

    for metadata_path in metadata_files:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        keep = is_health_relevant(metadata)
        metadata["health_insurance_relevant"] = keep
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        insurer_id = metadata.get("insurer_id", "unknown")
        insurer_bucket = by_insurer.setdefault(insurer_id, {"relevant": 0, "irrelevant": 0, "categories": {}})
        category = metadata.get("category", "unknown")
        category_bucket = insurer_bucket["categories"].setdefault(category, {"relevant": 0, "irrelevant": 0})
        if keep:
            relevant += 1
            insurer_bucket["relevant"] += 1
            category_bucket["relevant"] += 1
        else:
            irrelevant += 1
            insurer_bucket["irrelevant"] += 1
            category_bucket["irrelevant"] += 1

    report = {"metadata_files": len(metadata_files), "relevant": relevant, "irrelevant": irrelevant, "by_insurer": by_insurer}
    (root / "curation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
