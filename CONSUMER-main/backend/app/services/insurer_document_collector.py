import hashlib
import html.parser
import json
import random
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.services.irdai_insurer_fallback import IrdaiInsurerFallback
from app.services.insurer_document_curation import is_health_relevant
from app.services.playwright_document_fetcher import PLAYWRIGHT_INSURERS, discover_pdf_links_playwright


class LinkExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            self.links.append((self._current_href, " ".join(part for part in self._current_text if part)))
            self._current_href = None
            self._current_text = []


@dataclass(frozen=True)
class Insurer:
    id: str
    name: str
    allowed_domains: list[str]
    seed_urls: list[str]


class InsurerDocumentCollector:
    def __init__(self, registry_path: Path, output_root: Path) -> None:
        self.registry_path = registry_path
        self.output_root = output_root
        self.registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self.categories: dict[str, list[str]] = self.registry["document_categories"]
        self.max_pages = int(self.registry["policy"].get("max_pages_per_insurer", 35))
        self.max_pdfs = int(self.registry["policy"].get("max_pdfs_per_insurer", 40))
        self._last_request_by_host: dict[str, float] = {}
        self.irdai_fallback = IrdaiInsurerFallback(output_root)

    def insurers(self) -> list[Insurer]:
        return [Insurer(**insurer) for insurer in self.registry["insurers"]]

    def host_allowed(self, insurer: Insurer, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host in {domain.lower() for domain in insurer.allowed_domains}

    def normalize_url(self, base: str, href: str) -> str | None:
        if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            return None
        joined = urljoin(base, href)
        clean, _ = urldefrag(joined)
        return clean

    def _rate_limit(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        now = time.time()
        last = self._last_request_by_host.get(host, 0.0)
        wait = 2.5 - (now - last)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.5))
        self._last_request_by_host[host] = time.time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=8))
    def fetch(self, url: str) -> tuple[bytes, str, str]:
        self._rate_limit(url)
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
            },
        )
        with urlopen(request, timeout=45) as response:
            body = response.read()
            content_type = response.headers.get("content-type", "")
            final_url = response.geturl()
        return body, content_type, final_url

    def is_relevant_link(self, url: str, text: str) -> bool:
        haystack = f"{url} {text}".lower()
        keywords = [
            "health", "claim", "claims", "download", "policy", "wording", "brochure", "prospectus",
            "exclusion", "waiting", "rider", "add-on", "addon", "faq", "cashless", "network", "hospital",
            "terms", "condition", "coverage", "benefit",
        ]
        return any(keyword in haystack for keyword in keywords)

    def classify(self, url: str, text: str = "") -> str:
        haystack = re.sub(r"[^a-z0-9]+", " ", f"{url} {text}".lower())
        for category, keywords in self.categories.items():
            for keyword in keywords:
                normalized = re.sub(r"[^a-z0-9]+", " ", keyword.lower()).strip()
                if normalized and normalized in haystack:
                    return category
        return "other_health_document"

    def safe_filename(self, url: str, fallback: str) -> str:
        parsed = urlparse(url)
        name = Path(parsed.path).name or fallback
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"
        return name[:150]

    def discover_pdf_links(self, insurer: Insurer) -> tuple[list[tuple[str, str]], list[dict]]:
        queue = deque(insurer.seed_urls)
        visited: set[str] = set()
        pdfs: dict[str, str] = {}
        errors: list[dict] = []

        while queue and len(visited) < self.max_pages and len(pdfs) < self.max_pdfs:
            url = queue.popleft()
            if url in visited or not self.host_allowed(insurer, url):
                continue
            visited.add(url)
            try:
                body, content_type, final_url = self.fetch(url)
            except Exception as exc:
                errors.append({"url": url, "error": str(exc)})
                continue

            lower_type = content_type.lower()
            if "pdf" in lower_type or final_url.lower().endswith(".pdf"):
                if self.is_relevant_link(final_url, ""):
                    pdfs[final_url] = final_url
                continue
            if "html" not in lower_type:
                continue

            parser = LinkExtractor()
            parser.feed(body.decode("utf-8", errors="ignore"))
            for href, text in parser.links:
                link = self.normalize_url(final_url, href)
                if not link or not self.host_allowed(insurer, link):
                    continue
                lower_link = link.lower()
                if lower_link.endswith(".pdf") or ".pdf" in lower_link:
                    if self.is_relevant_link(link, text):
                        pdfs[link] = text or link
                elif self.is_relevant_link(link, text) and link not in visited and len(queue) < self.max_pages * 3:
                    queue.append(link)

        return list(pdfs.items())[: self.max_pdfs], errors

    def download_pdf(self, insurer: Insurer, url: str, label: str) -> dict:
        body, content_type, final_url = self.fetch(url)
        category = self.classify(final_url, label)
        insurer_dir = self.output_root / insurer.id / category
        metadata_dir = self.output_root / "metadata" / insurer.id
        insurer_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        filename = self.safe_filename(final_url, f"{insurer.id}_{category}.pdf")
        file_path = insurer_dir / filename
        if file_path.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            file_path = insurer_dir / f"{stem}_{hashlib.sha1(final_url.encode()).hexdigest()[:8]}{suffix}"
        file_path.write_bytes(body)

        digest = hashlib.sha256(body).hexdigest()
        metadata = {
            "insurer_id": insurer.id,
            "insurer_name": insurer.name,
            "category": category,
            "label": label,
            "url": url,
            "final_url": final_url,
            "content_type": content_type,
            "content_sha256": digest,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "file_path": str(file_path),
            "official_domain": urlparse(final_url).netloc.lower(),
            "health_insurance_relevant": is_health_relevant({
                "label": label,
                "url": url,
                "final_url": final_url,
                "file_path": str(file_path),
                "category": category,
                "insurer_name": insurer.name,
            }),
        }
        metadata_path = metadata_dir / f"{file_path.stem}.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def collect_insurer(self, insurer: Insurer) -> dict:
        pdf_links, discovery_errors = self.discover_pdf_links(insurer)
        if not pdf_links and insurer.id in PLAYWRIGHT_INSURERS:
            allowed = {domain.lower() for domain in insurer.allowed_domains}
            playwright_links, playwright_errors = discover_pdf_links_playwright(insurer.seed_urls, allowed, self.max_pdfs)
            discovery_errors.extend(playwright_errors)
            pdf_links = playwright_links
        if not pdf_links:
            pdf_links = self.irdai_fallback.search_irdai_links(insurer.id, insurer.name)
            if pdf_links:
                discovery_errors.append({"source": "irdai_fallback", "links_found": len(pdf_links)})
        downloaded: list[dict] = []
        download_errors: list[dict] = []
        for url, label in pdf_links:
            try:
                downloaded.append(self.download_pdf(insurer, url, label))
            except Exception as exc:
                download_errors.append({"url": url, "error": str(exc)})
        if not downloaded:
            self.irdai_fallback.log_manual_gap(insurer.id, insurer.name, "no_documents_after_primary_playwright_and_irdai_fallback")
        categories = sorted(set(item["category"] for item in downloaded))
        return {
            "insurer_id": insurer.id,
            "insurer_name": insurer.name,
            "pdf_links_found": len(pdf_links),
            "downloaded": len(downloaded),
            "categories": categories,
            "documents": downloaded,
            "errors": discovery_errors + download_errors,
        }

    def collect(self, insurer_ids: set[str] | None = None) -> dict:
        results = []
        for insurer in self.insurers():
            if insurer_ids and insurer.id not in insurer_ids:
                continue
            results.append(self.collect_insurer(insurer))
        report = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "insurers_requested": len(insurer_ids) if insurer_ids else len(self.insurers()),
            "insurers_completed": len(results),
            "total_downloaded": sum(result["downloaded"] for result in results),
            "results": results,
        }
        report_path = self.output_root / "download_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
