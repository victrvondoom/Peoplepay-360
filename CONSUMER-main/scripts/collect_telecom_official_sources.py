"""
Collect official telecom-domain knowledge for PROXY.

The collector downloads public pages and PDFs from official TRAI, DoT,
National Consumer Helpline, and telecom operator websites. It stores actual
content under knowledge/telecom, not link-only records, and writes metadata,
chunk previews, and graph seed files for the existing RAG/KG ingestion flow.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = ROOT / "knowledge" / "telecom"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

FOLDERS = [
    "trai",
    "dot",
    "regulations",
    "operators/airtel",
    "operators/jio",
    "operators/vi",
    "operators/bsnl",
    "mobile",
    "broadband",
    "fiber",
    "recharge",
    "billing",
    "complaints",
    "refunds",
    "mnp",
    "network_quality",
    "customer_rights",
    "faqs",
    "templates",
    "synthetic_cases",
    "metadata",
    "chunks",
    "knowledge_graph",
]


@dataclass(frozen=True)
class Source:
    authority: str
    title: str
    url: str
    folder: str
    category: str
    slug: str
    max_linked_pdfs: int = 4


SOURCES = [
    Source("TRAI", "TRAI Quality of Service", "https://www.trai.gov.in/telecom/qos", "trai", "quality_of_service", "trai_qos", 8),
    Source("TRAI", "TRAI Internet and Broadband", "https://www.trai.gov.in/telecom/internet-broadband", "trai", "broadband_regulations", "trai_internet_broadband", 8),
    Source("TRAI", "TRAI Mobile Number Portability", "https://www.trai.gov.in/telecom/mobile-number-portability", "mnp", "mnp", "trai_mnp", 8),
    Source("TRAI", "TRAI Consumer Protection", "https://www.trai.gov.in/telecom/consumer-protection", "customer_rights", "consumer_protection", "trai_consumer_protection", 8),
    Source("TRAI", "TRAI Complaint Redressal", "https://www.trai.gov.in/telecom/complaint-redressal", "complaints", "complaint_redressal", "trai_complaint_redressal", 8),
    Source("TRAI", "TRAI Value Added Services", "https://www.trai.gov.in/telecom/vas", "mobile", "vas", "trai_vas", 6),
    Source("TRAI", "TRAI Telecom FAQs", "https://www.trai.gov.in/consumer-info/telecom/faq-category-listing", "faqs", "faq", "trai_telecom_faq", 4),
    Source("TRAI", "TRAI Consolidated Telecom Regulations", "https://www.trai.gov.in/release-publication/consolidated-regulation/telecom", "regulations", "regulations", "trai_consolidated_telecom_regulations", 10),
    Source("DoT", "DoT National Digital Communications Policy 2018", "https://www.dot.gov.in/national-digital-communications-policy-2018", "dot", "policy", "dot_national_digital_communications_policy_2018", 1),
    Source("DoT", "DoT Home and Consumer Links", "https://www.dot.gov.in/", "dot", "consumer_advisory", "dot_home", 2),
    Source("DoT", "DoT Access Services", "https://www.dot.gov.in/access-services", "dot", "licensing", "dot_access_services", 2),
    Source("NCH", "National Consumer Helpline", "https://consumerhelpline.gov.in/public/", "complaints", "complaint_guidance", "national_consumer_helpline", 3),
    Source("Airtel", "Airtel Terms and Conditions", "https://www.airtel.in/terms-and-conditions", "operators/airtel", "terms", "airtel_terms", 3),
    Source("Airtel", "Airtel Prepaid Plans", "https://www.airtel.in/prepaid/all-prepaid-plans", "operators/airtel", "mobile_plans", "airtel_prepaid_plans", 2),
    Source("Airtel", "Airtel Broadband", "https://www.airtel.in/airtel-broadband", "operators/airtel", "broadband", "airtel_broadband", 2),
    Source("Airtel", "Airtel Xstream Fiber", "https://www.airtel.in/airtel-xstream-fiber", "operators/airtel", "fiber", "airtel_fiber", 2),
    Source("Airtel", "Airtel Help and Support", "https://www.airtel.in/help", "operators/airtel", "complaint_process", "airtel_help", 2),
    Source("Jio", "Jio Terms and Conditions", "https://www.jio.com/en-in/terms-and-conditions", "operators/jio", "terms", "jio_terms", 3),
    Source("Jio", "Jio Prepaid Plans", "https://www.jio.com/en-in/mobile/prepaid-plans", "operators/jio", "mobile_plans", "jio_prepaid_plans", 2),
    Source("Jio", "JioFiber Plans", "https://www.jio.com/en-in/jiofiber", "operators/jio", "fiber", "jio_fiber", 2),
    Source("Jio", "Jio Help and Support", "https://www.jio.com/help/home", "operators/jio", "complaint_process", "jio_help", 2),
    Source("Vi", "Vi Terms and Conditions", "https://www.myvi.in/terms-of-use", "operators/vi", "terms", "vi_terms", 1),
    Source("Vi", "Vi Prepaid Plans", "https://www.myvi.in/prepaid/all-prepaid-plans", "operators/vi", "mobile_plans", "vi_prepaid_plans", 2),
    Source("Vi", "Vi Help and Support", "https://www.myvi.in/help-support/faqs", "operators/vi", "complaint_process", "vi_help", 1),
    Source("BSNL", "BSNL Mobile Services", "https://bsnl.co.in/mobile/recharge", "operators/bsnl", "mobile_plans", "bsnl_mobile_recharge", 1),
    Source("BSNL", "BSNL Broadband", "https://bsnl.co.in/", "operators/bsnl", "broadband", "bsnl_home_broadband", 1),
    Source("BSNL", "BSNL FTTH", "https://bsnl.co.in/sim-order", "operators/bsnl", "fiber", "bsnl_sim_mnp", 1),
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip_depth = 0
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "a":
            attr = dict(attrs)
            self._current_href = attr.get("href")
            self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "a" and self._current_href:
            label = " ".join(" ".join(self._current_text).split())
            self.links.append((self._current_href, label))
            self._current_href = None
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        clean = html.unescape(data).strip()
        if not clean:
            return
        self.parts.append(clean)
        if self._current_href:
            self._current_text.append(clean)

    def text(self) -> str:
        raw = "\n".join(self.parts)
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        return "\n".join(lines)


def ensure_folders() -> None:
    for folder in FOLDERS:
        (KNOWLEDGE_ROOT / folder).mkdir(parents=True, exist_ok=True)


def checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_slug(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")[:90] or "document"


def metadata_path(folder: str, slug: str) -> Path:
    path = KNOWLEDGE_ROOT / "metadata" / folder / f"{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_metadata(folder: str, slug: str, payload: dict) -> None:
    metadata_path(folder, slug).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, headers=HEADERS, timeout=18, allow_redirects=True)
    response.raise_for_status()
    return response


def save_content(folder: str, slug: str, ext: str, content: bytes, metadata: dict) -> Path:
    folder_path = KNOWLEDGE_ROOT / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    path = folder_path / f"{slug}.{ext}"
    path.write_bytes(content)
    metadata = {
        **metadata,
        "stored_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": checksum(content),
        "bytes": len(content),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    write_metadata(folder, slug, metadata)
    return path


def extract_html(content: bytes) -> tuple[str, list[tuple[str, str]]]:
    parser = TextExtractor()
    parser.feed(content.decode("utf-8", errors="ignore"))
    return parser.text(), parser.links


def relevant_pdf_links(source: Source, links: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    keywords = {
        "regulation", "regulations", "order", "orders", "qos", "quality", "consumer",
        "complaint", "redressal", "broadband", "mnp", "portability", "tariff", "billing",
        "refund", "terms", "condition", "charter", "fup", "roaming", "vas", "service",
        "policy", "guideline", "notification", "direction", "manual", "pdf",
    }
    scored: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for href, label in links:
        absolute = urljoin(source.url, href)
        parsed = urlparse(absolute)
        if not parsed.scheme.startswith("http"):
            continue
        text = f"{absolute} {label}".lower()
        if ".pdf" not in text and "download" not in text:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        score = sum(1 for word in keywords if word in text)
        if source.category.replace("_", " ") in text:
            score += 3
        if score:
            scored.append((score, absolute, label or Path(parsed.path).name))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(url, label) for _, url, label in scored[: source.max_linked_pdfs]]


def collect_source(session: requests.Session, source: Source, delay: float) -> dict:
    result = {"source": asdict(source), "status": "pending", "saved": [], "errors": []}
    try:
        response = fetch(session, source.url)
        content_type = response.headers.get("content-type", "").lower()
        final_url = response.url
        if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
            path = save_content(
                source.folder,
                source.slug,
                "pdf",
                response.content,
                {
                    "domain": "telecom",
                    "authority": source.authority,
                    "title": source.title,
                    "category": source.category,
                    "source_url": source.url,
                    "final_url": final_url,
                    "type": "pdf",
                    "official_source": True,
                },
            )
            result["saved"].append(str(path.relative_to(ROOT)).replace("\\", "/"))
        else:
            text, links = extract_html(response.content)
            if len(text) < 120:
                raise RuntimeError(f"too little text extracted: {len(text)} chars")
            path = save_content(
                source.folder,
                source.slug,
                "txt",
                text.encode("utf-8"),
                {
                    "domain": "telecom",
                    "authority": source.authority,
                    "title": source.title,
                    "category": source.category,
                    "source_url": source.url,
                    "final_url": final_url,
                    "type": "html_text",
                    "official_source": True,
                    "raw_chars": len(text),
                },
            )
            result["saved"].append(str(path.relative_to(ROOT)).replace("\\", "/"))

            for index, (pdf_url, label) in enumerate(relevant_pdf_links(source, links), start=1):
                time.sleep(delay)
                try:
                    pdf_response = fetch(session, pdf_url)
                    pdf_content_type = pdf_response.headers.get("content-type", "").lower()
                    if "pdf" not in pdf_content_type and not pdf_response.url.lower().endswith(".pdf"):
                        continue
                    pdf_slug = f"{source.slug}_{index:02d}_{clean_slug(label)}"
                    pdf_path = save_content(
                        source.folder,
                        pdf_slug,
                        "pdf",
                        pdf_response.content,
                        {
                            "domain": "telecom",
                            "authority": source.authority,
                            "title": label or source.title,
                            "parent_title": source.title,
                            "category": source.category,
                            "source_url": pdf_url,
                            "parent_url": source.url,
                            "final_url": pdf_response.url,
                            "type": "linked_pdf",
                            "official_source": True,
                        },
                    )
                    result["saved"].append(str(pdf_path.relative_to(ROOT)).replace("\\", "/"))
                except Exception as exc:  # noqa: BLE001 - report and continue crawl
                    result["errors"].append({"url": pdf_url, "error": str(exc)})
        result["status"] = "ok" if result["saved"] else "empty"
    except Exception as exc:  # noqa: BLE001 - source-level failure is non-fatal
        result["status"] = "failed"
        result["errors"].append({"url": source.url, "error": str(exc)})
    return result


def read_text(path: Path) -> str:
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8", errors="ignore")
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def chunk_text(text: str, chunk_size: int = 3400, overlap: int = 500) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            break_at = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
            if break_at > start + chunk_size // 2:
                end = break_at + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def write_chunk_preview() -> int:
    chunk_path = KNOWLEDGE_ROOT / "chunks" / "telecom_chunks.jsonl"
    count = 0
    with chunk_path.open("w", encoding="utf-8") as handle:
        for path in sorted(KNOWLEDGE_ROOT.rglob("*")):
            if not path.is_file() or "metadata" in path.parts or "chunks" in path.parts:
                continue
            if path.suffix.lower() not in {".txt", ".pdf", ".html", ".md"}:
                continue
            text = read_text(path)
            if len(text.strip()) < 50:
                continue
            rel = str(path.relative_to(KNOWLEDGE_ROOT)).replace("\\", "/")
            for index, chunk in enumerate(chunk_text(text)):
                record = {
                    "domain": "telecom",
                    "source_path": rel,
                    "chunk_index": index,
                    "text": chunk,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
    return count


def write_graph_seed() -> tuple[int, int]:
    entities = [
        "Telecom Operator", "Customer", "SIM Card", "Mobile Number", "Broadband Connection",
        "Fiber Connection", "Recharge", "Billing Cycle", "Invoice", "Plan", "Data Pack",
        "Voice Pack", "SMS Pack", "VAS Service", "Complaint", "Refund", "Tower", "Signal",
        "Network", "Call Drop", "Portability (MNP)", "TRAI Regulation", "DoT Guideline",
        "Consumer Right", "Appeal", "Resolution",
    ]
    relationships = [
        ("Customer", "USES", "Plan"),
        ("Telecom Operator", "PROVIDES", "Broadband Connection"),
        ("Telecom Operator", "PROVIDES", "Fiber Connection"),
        ("Complaint", "REFERENCES", "TRAI Regulation"),
        ("Recharge", "BELONGS_TO", "Customer"),
        ("Invoice", "GENERATED_BY", "Telecom Operator"),
        ("Refund", "FOLLOWS", "Complaint"),
        ("Portability (MNP)", "INVOLVES", "Telecom Operator"),
        ("Network", "AFFECTS", "Customer"),
        ("Call Drop", "INDICATES", "Network"),
        ("VAS Service", "REQUIRES_CONSENT_FROM", "Customer"),
        ("Appeal", "REFERENCES", "Consumer Right"),
        ("Resolution", "CLOSES", "Complaint"),
    ]
    graph_dir = KNOWLEDGE_ROOT / "knowledge_graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    with (graph_dir / "telecom_entities.jsonl").open("w", encoding="utf-8") as handle:
        for name in entities:
            handle.write(json.dumps({"domain": "telecom", "label": name, "name": name}, ensure_ascii=False) + "\n")
    with (graph_dir / "telecom_relationships.jsonl").open("w", encoding="utf-8") as handle:
        for source, relation, target in relationships:
            handle.write(json.dumps({"domain": "telecom", "source": source, "relation": relation, "target": target}, ensure_ascii=False) + "\n")
    return len(entities), len(relationships)


def write_templates() -> None:
    templates = {
        "wrong_bill_appeal.md": "# Wrong Bill Appeal\n\nSubject: Dispute of incorrect telecom invoice\n\nI dispute invoice {{invoice_number}} for {{billing_cycle}} because {{issue_summary}}. Please reverse unsupported charges, provide itemized usage records, and resolve within the applicable grievance timeline.\n",
        "unauthorized_vas_refund.md": "# Unauthorized VAS Refund Request\n\nSubject: Refund request for value added service activated without consent\n\nThe VAS charge of {{amount}} was applied without explicit consent. Please deactivate the service, refund the charge, and share activation proof.\n",
        "mnp_failure_escalation.md": "# MNP Failure Escalation\n\nSubject: Escalation for failed mobile number portability request\n\nMy MNP request for {{mobile_number}} has not been completed/rejected without valid reason. Please provide the rejection reason, UPC status, and corrective action timeline.\n",
        "network_quality_complaint.md": "# Network Quality Complaint\n\nSubject: Complaint regarding poor network quality and data speed\n\nI am experiencing {{issue_type}} at {{location}} since {{start_date}}. Please investigate tower/network performance, restore service quality, and provide compensation for downtime where applicable.\n",
    }
    for filename, content in templates.items():
        (KNOWLEDGE_ROOT / "templates" / filename).write_text(content, encoding="utf-8")


def write_synthetic_cases() -> None:
    cases = [
        {
            "case_type": "wrong_bill",
            "facts": {"operator": "Airtel", "issue": "extra roaming charge after pack activation", "amount": "2499"},
            "expected_agents": ["billing_disputes", "trai_regulatory"],
        },
        {
            "case_type": "fiber_delay",
            "facts": {"operator": "Jio", "issue": "fiber installation delayed after payment", "days_pending": 18},
            "expected_agents": ["network_quality", "general_telecom"],
        },
        {
            "case_type": "mnp_failure",
            "facts": {"operator": "Vi", "issue": "port request rejected without reason", "days_pending": 9},
            "expected_agents": ["mnp_portability", "trai_regulatory"],
        },
        {
            "case_type": "unauthorized_vas",
            "facts": {"operator": "BSNL", "issue": "VAS activated and deducted balance", "amount": "99"},
            "expected_agents": ["billing_disputes", "general_telecom"],
        },
    ]
    path = KNOWLEDGE_ROOT / "synthetic_cases" / "telecom_synthetic_cases.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps({"domain": "telecom", **case}, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download official telecom knowledge and prepare chunks/KG seeds.")
    parser.add_argument("--delay", type=float, default=0.6, help="Polite delay between downloads.")
    parser.add_argument("--skip-download", action="store_true", help="Only regenerate chunk previews, templates, and KG seeds.")
    parser.add_argument("--start-index", type=int, default=1, help="1-based source index to start from.")
    parser.add_argument("--end-index", type=int, default=len(SOURCES), help="1-based source index to end at.")
    args = parser.parse_args()

    ensure_folders()
    results: list[dict] = []
    if not args.skip_download:
        selected_sources = SOURCES[max(args.start_index - 1, 0): args.end_index]
        with requests.Session() as session:
            for source in selected_sources:
                print(f"GET {source.authority}: {source.title}")
                result = collect_source(session, source, args.delay)
                print(f"  {result['status']} saved={len(result['saved'])} errors={len(result['errors'])}")
                results.append(result)
                time.sleep(args.delay)

    write_templates()
    write_synthetic_cases()
    entity_count, relationship_count = write_graph_seed()
    chunk_count = write_chunk_preview()
    report = {
        "domain": "telecom",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_sources": [asdict(source) for source in SOURCES],
        "download_results": results,
        "chunk_preview_count": chunk_count,
        "graph_seed_entities": entity_count,
        "graph_seed_relationships": relationship_count,
    }
    (KNOWLEDGE_ROOT / "telecom_ingestion_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (KNOWLEDGE_ROOT / "telecom_source_registry.json").write_text(json.dumps([asdict(source) for source in SOURCES], indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "sources_attempted": len(SOURCES) if not args.skip_download else 0,
        "sources_downloaded": sum(1 for item in results if item["status"] == "ok"),
        "saved_files": sum(len(item["saved"]) for item in results),
        "chunk_preview_count": chunk_count,
        "graph_seed_entities": entity_count,
        "graph_seed_relationships": relationship_count,
    }, indent=2))


if __name__ == "__main__":
    main()





