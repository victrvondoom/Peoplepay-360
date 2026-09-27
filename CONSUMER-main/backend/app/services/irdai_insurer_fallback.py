from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

IRDAI_SEARCH_BASE = "https://irdai.gov.in"
IRDAI_ALLOWED = {"irdai.gov.in", "www.irdai.gov.in", "bimasuryog.bima.gov.in", "www.bimasuryog.bima.gov.in"}
NON_HEALTH_TERMS = ["personal accident", " pa ", "motor", "vehicle", "marine", "fire insurance", "crop", "livestock"]


class IrdaiInsurerFallback:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root
        self.log_path = output_root / "manual_ingest_backlog.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _fetch(self, url: str) -> bytes:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-IN,en;q=0.9",
            },
        )
        with urlopen(request, timeout=40) as response:
            return response.read()

    def _is_health_pdf(self, url: str, label: str) -> bool:
        haystack = f"{url} {label}".lower()
        if any(term in haystack for term in NON_HEALTH_TERMS):
            return False
        return any(term in haystack for term in ["health", "mediclaim", "hospital", "indemnity", "arogya", "sanjeevani"])

    def search_irdai_links(self, insurer_id: str, insurer_name: str) -> list[tuple[str, str]]:
        short_name = insurer_name.split()[0]
        query_terms = [
            f"{insurer_name} health insurance policy wording site:irdai.gov.in",
            f"{short_name} health insurance standard policy wording filetype:pdf",
            f"{insurer_name} mediclaim prospectus site:irdai.gov.in",
        ]
        links: dict[str, str] = {}
        for term in query_terms:
            search_url = f"{IRDAI_SEARCH_BASE}/?s={quote(term)}"
            try:
                body = self._fetch(search_url).decode("utf-8", errors="ignore")
            except Exception:
                continue
            for match in re.finditer(r'href=["\\\']([^"\\\']+)["\\\']', body, flags=re.IGNORECASE):
                href = match.group(1)
                if ".pdf" not in href.lower():
                    continue
                full = urljoin(search_url, href)
                host = urlparse(full).netloc.lower()
                if host in IRDAI_ALLOWED or insurer_name.split()[0].lower() in full.lower():
                    if self._is_health_pdf(full, href):
                        links[full] = insurer_name
            time.sleep(2.5)
        return list(links.items())

    def log_manual_gap(self, insurer_id: str, insurer_name: str, reason: str) -> None:
        record = {
            "insurer_id": insurer_id,
            "insurer_name": insurer_name,
            "reason": reason,
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "action": "manual_ingest_required",
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
