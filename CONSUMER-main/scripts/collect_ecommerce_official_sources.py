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
from urllib.parse import urljoin, urlparse

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = ROOT / "knowledge" / "ecommerce"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


@dataclass(frozen=True)
class Source:
    authority: str
    title: str
    url: str
    folder: str
    category: str
    slug: str
    max_linked_pdfs: int = 0


SOURCES = [
    Source("NCH", "National Consumer Helpline Home", "https://consumerhelpline.gov.in/public/", "official/nch", "complaint_redressal", "nch_home"),
    Source("NCH", "National Consumer Helpline About and Complaint Process", "https://consumerhelpline.gov.in/public/about", "official/nch", "complaint_redressal", "nch_about"),
    Source("NCH", "National Consumer Helpline Knowledge Base", "https://consumerhelpline.gov.in/public/knowledgebase", "official/nch", "consumer_knowledge_base", "nch_knowledge_base"),
    Source("NCDRC", "NCDRC Home and Jurisdiction", "https://ncdrc.nic.in/", "official/ncdrc", "consumer_commission", "ncdrc_home"),
    Source("NCDRC", "NCDRC History", "https://ncdrc.nic.in/history.html", "official/ncdrc", "consumer_commission", "ncdrc_history"),
    Source("e-Jagriti", "e-Jagriti Online Filing Portal", "https://e-jagriti.gov.in/", "official/e_jagriti", "online_filing", "e_jagriti_home"),
    Source("Department of Consumer Affairs", "Consumer Protection Acts and Rules", "https://consumeraffairs.nic.in/acts-and-rules/consumer-protection", "official/consumer_affairs", "consumer_protection", "consumer_affairs_consumer_protection", 4),
    Source("Department of Consumer Affairs", "Legal Metrology Act", "https://consumeraffairs.nic.in/acts-and-rules/legal-metrology/the-legal-metrology-act-2009", "official/consumer_affairs", "legal_metrology", "legal_metrology_act", 3),
    Source("Department of Consumer Affairs", "Misleading Advertisements Guidance", "https://consumeraffairs.nic.in/sites/default/files/file-uploads/consumer_information/MisleadingAdvertisements.pdf", "official/consumer_affairs", "misleading_advertisements", "misleading_advertisements"),
    Source("Department of Consumer Affairs", "Direct Selling Guidelines", "https://consumeraffairs.nic.in/sites/default/files/file-uploads/direct-selling/Direct%20Selling%20Guidelines%20Final%20_0.pdf", "official/consumer_affairs", "direct_selling", "direct_selling_guidelines"),
    Source("BIS", "Bureau of Indian Standards", "https://www.bis.gov.in/", "official/standards", "standards", "bis_home"),
    Source("India Post", "India Post Home", "https://www.indiapost.gov.in/", "official/courier", "postal_complaints", "india_post_home"),
    Source("NPCI", "NPCI UPI", "https://www.npci.org.in/what-we-do/upi/product-overview", "official/payment", "upi", "npci_upi_overview"),
    Source("NPCI", "NPCI UPI Dispute Redressal", "https://www.npci.org.in/what-we-do/upi/dispute-redressal-mechanism", "official/payment", "upi_disputes", "npci_upi_disputes"),
    Source("RuPay", "RuPay Contactless and Cardholder Info", "https://www.rupay.co.in/", "official/payment", "card_payments", "rupay_home"),
    Source("Amazon", "Amazon India Returns", "https://www.amazon.in/gp/help/customer/display.html?nodeId=GKM69DUUYKQWKWX7", "marketplaces/amazon", "returns", "amazon_returns_official"),
    Source("Amazon", "Amazon A-to-z Guarantee", "https://www.amazon.in/gp/help/customer/display.html?nodeId=GQ37ZCNECJKTFYQV", "marketplaces/amazon", "marketplace_guarantee", "amazon_a_to_z_official"),
    Source("Amazon", "Amazon Refunds", "https://www.amazon.in/gp/help/customer/display.html?nodeId=201117590", "marketplaces/amazon", "refunds", "amazon_refunds_official"),
    Source("Amazon", "Amazon Conditions of Use", "https://www.amazon.in/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM", "marketplaces/amazon", "terms", "amazon_conditions_official"),
    Source("Flipkart", "Flipkart Return and Cancellation Policy", "https://www.flipkart.com/pages/returnpolicy", "marketplaces/flipkart", "returns", "flipkart_return_policy_official"),
    Source("Flipkart", "Flipkart Terms of Use", "https://www.flipkart.com/pages/terms", "marketplaces/flipkart", "terms", "flipkart_terms_official"),
    Source("Myntra", "Myntra Terms of Use", "https://www.myntra.com/termsofuse", "marketplaces/myntra", "terms", "myntra_terms_official"),
    Source("Myntra", "Myntra FAQ", "https://www.myntra.com/faq", "marketplaces/myntra", "faq", "myntra_faq_official"),
    Source("Meesho", "Meesho Terms and Conditions", "https://www.meesho.com/legal/terms-conditions", "marketplaces/meesho", "terms", "meesho_terms_official"),
    Source("Meesho", "Meesho Privacy Policy", "https://www.meesho.com/legal/privacy", "marketplaces/meesho", "privacy", "meesho_privacy_official"),
    Source("JioMart", "JioMart Terms and Conditions", "https://www.jiomart.com/terms-and-conditions", "marketplaces/jiomart", "terms", "jiomart_terms_official"),
    Source("JioMart", "JioMart Cancellation Return Refund", "https://www.jiomart.com/cancellation-return-refund-policy", "marketplaces/jiomart", "returns_refunds", "jiomart_returns_refunds_official"),
    Source("Blinkit", "Blinkit Terms", "https://blinkit.com/terms", "marketplaces/blinkit", "terms", "blinkit_terms_official"),
    Source("Swiggy", "Swiggy Terms and Conditions", "https://www.swiggy.com/terms-and-conditions", "marketplaces/swiggy_instamart", "terms", "swiggy_terms_official"),
    Source("BigBasket", "BigBasket Terms and Conditions", "https://www.bigbasket.com/terms-and-conditions/", "marketplaces/bigbasket", "terms", "bigbasket_terms_official"),
    Source("Zepto", "Zepto Terms", "https://www.zeptonow.com/terms-of-use", "marketplaces/zepto", "terms", "zepto_terms_official"),
    Source("AJIO", "AJIO Selfcare", "https://www.ajio.com/selfcare", "marketplaces/ajio", "returns_refunds", "ajio_selfcare_official"),
    Source("Delhivery", "Delhivery Terms and Conditions", "https://www.delhivery.com/terms-and-conditions", "courier/delhivery", "courier_terms", "delhivery_terms_official"),
    Source("Blue Dart", "Blue Dart Contact", "https://www.bluedart.com/contactus", "courier/bluedart", "courier_support", "bluedart_contact_official"),
    Source("DTDC", "DTDC Contact Us", "https://www.dtdc.in/contact-us.asp", "courier/dtdc", "courier_support", "dtdc_contact_official"),
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._href: str | None = None
        self._label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag == "a":
            attrs_dict = dict(attrs)
            self._href = attrs_dict.get("href")
            self._label = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag == "a" and self._href:
            label = " ".join(" ".join(self._label).split())
            self.links.append((self._href, label))
            self._href = None
            self._label = []

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        clean = html.unescape(data).strip()
        if not clean:
            return
        self.parts.append(clean)
        if self._href:
            self._label.append(clean)

    def text(self) -> str:
        lines = [line.strip() for line in "\n".join(self.parts).splitlines() if line.strip()]
        return "\n".join(lines)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value[:90] or "document"


def save(folder: str, slug: str, ext: str, content: bytes, metadata: dict) -> Path:
    dest = KNOWLEDGE_ROOT / folder
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{slug}.{ext}"
    path.write_bytes(content)
    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        **metadata,
        "stored_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(content),
        "bytes": len(content),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "official_source": True,
    }
    (meta_dir / f"{slug}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def extract_html(content: bytes) -> tuple[str, list[tuple[str, str]]]:
    parser = TextExtractor()
    parser.feed(content.decode("utf-8", errors="ignore"))
    return parser.text(), parser.links


def linked_pdf_candidates(source: Source, links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if source.max_linked_pdfs <= 0:
        return []
    wanted = {"pdf", "rules", "act", "guideline", "e-commerce", "consumer", "advertisement", "direct", "legal", "metrology"}
    scored: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for href, label in links:
        absolute = urljoin(source.url, href)
        lower = f"{absolute} {label}".lower()
        if absolute in seen or ("pdf" not in lower and "download" not in lower):
            continue
        seen.add(absolute)
        score = sum(1 for word in wanted if word in lower)
        if score:
            scored.append((score, absolute, label or Path(urlparse(absolute).path).name))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(url, label) for _, url, label in scored[: source.max_linked_pdfs]]


def download(session: requests.Session, source: Source, delay: float) -> dict:
    result = {"source": asdict(source), "status": "pending", "saved": [], "errors": []}
    try:
        response = session.get(source.url, headers=HEADERS, timeout=25, allow_redirects=True, verify=False)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        final_url = response.url
        is_pdf = "pdf" in content_type or final_url.lower().endswith(".pdf")
        if is_pdf:
            path = save(source.folder, source.slug, "pdf", response.content, {
                "domain": "ecommerce", "authority": source.authority, "title": source.title,
                "category": source.category, "source_url": source.url, "final_url": final_url, "type": "pdf",
            })
            result["saved"].append(str(path.relative_to(ROOT)).replace("\\", "/"))
        else:
            text, links = extract_html(response.content)
            if len(text) < 80:
                text = f"{source.title}\nSource URL: {source.url}\nFinal URL: {final_url}\nContent was JavaScript-rendered or too small for static extraction."
            path = save(source.folder, source.slug, "txt", text.encode("utf-8"), {
                "domain": "ecommerce", "authority": source.authority, "title": source.title,
                "category": source.category, "source_url": source.url, "final_url": final_url,
                "type": "html_text", "raw_chars": len(text),
            })
            result["saved"].append(str(path.relative_to(ROOT)).replace("\\", "/"))
            for index, (pdf_url, label) in enumerate(linked_pdf_candidates(source, links), start=1):
                time.sleep(delay)
                try:
                    pdf_response = session.get(pdf_url, headers=HEADERS, timeout=30, allow_redirects=True, verify=False)
                    pdf_response.raise_for_status()
                    pdf_type = pdf_response.headers.get("content-type", "").lower()
                    if "pdf" not in pdf_type and not pdf_response.url.lower().endswith(".pdf"):
                        continue
                    pdf_slug = f"{source.slug}_{index:02d}_{clean_slug(label)}"
                    pdf_path = save(source.folder, pdf_slug, "pdf", pdf_response.content, {
                        "domain": "ecommerce", "authority": source.authority, "title": label or source.title,
                        "parent_title": source.title, "category": source.category,
                        "source_url": pdf_url, "parent_url": source.url, "final_url": pdf_response.url,
                        "type": "linked_pdf",
                    })
                    result["saved"].append(str(pdf_path.relative_to(ROOT)).replace("\\", "/"))
                except Exception as exc:
                    result["errors"].append({"url": pdf_url, "error": str(exc)})
        result["status"] = "ok" if result["saved"] else "empty"
    except Exception as exc:
        result["status"] = "failed"
        result["errors"].append({"url": source.url, "error": str(exc)})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Download official e-commerce consumer knowledge sources.")
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int, default=len(SOURCES))
    args = parser.parse_args()
    selected = SOURCES[max(args.start_index - 1, 0):args.end_index]
    results = []
    with requests.Session() as session:
        for source in selected:
            print(f"GET {source.authority}: {source.title}", flush=True)
            result = download(session, source, args.delay)
            print(f"  {result['status']} saved={len(result['saved'])} errors={len(result['errors'])}", flush=True)
            results.append(result)
            time.sleep(args.delay)
    report_path = KNOWLEDGE_ROOT / "ecommerce_official_download_report.json"
    existing = []
    if report_path.exists():
        try:
            existing = json.loads(report_path.read_text(encoding="utf-8")).get("download_results", [])
        except Exception:
            existing = []
    report = {
        "domain": "ecommerce",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_sources": [asdict(source) for source in SOURCES],
        "download_results": existing + results,
        "sources_attempted_this_run": len(selected),
        "sources_downloaded_this_run": sum(1 for item in results if item["status"] == "ok"),
        "files_saved_this_run": sum(len(item["saved"]) for item in results),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "sources_attempted": report["sources_attempted_this_run"],
        "sources_downloaded": report["sources_downloaded_this_run"],
        "files_saved": report["files_saved_this_run"],
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
    }, indent=2))


if __name__ == "__main__":
    main()

