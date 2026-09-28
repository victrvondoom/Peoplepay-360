from __future__ import annotations

import random
import re
import time
from urllib.parse import urljoin

PLAYWRIGHT_INSURERS = {
    "star_health",
    "icici_lombard",
    "care_health",
    "bajaj_allianz",
    "reliance_general",
}


def discover_pdf_links_playwright(urls: list[str], allowed_domains: set[str], max_links: int = 40) -> tuple[list[tuple[str, str]], list[dict]]:
    errors: list[dict] = []
    pdfs: dict[str, str] = {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return [], [{"error": f"playwright not installed: {exc}"}]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-IN",
        )
        page = context.new_page()
        for url in urls:
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                anchors = page.eval_on_selector_all(
                    "a[href]",
                    "elements => elements.map(a => ({href: a.href, text: (a.innerText || '').trim()}))",
                )
                for anchor in anchors:
                    href = anchor.get("href", "")
                    text = anchor.get("text", "")
                    if not href:
                        continue
                    host = re.sub(r"^www\.", "", href.split("/")[2].lower()) if "://" in href else ""
                    if allowed_domains and host and host not in allowed_domains and f"www.{host}" not in allowed_domains:
                        continue
                    if href.lower().endswith(".pdf") or ".pdf" in href.lower():
                        pdfs[href] = text or href
                for link in page.locator("a[href*='.pdf']").all()[:max_links]:
                    href = link.get_attribute("href")
                    if href:
                        pdfs[urljoin(url, href)] = (link.inner_text() or "").strip() or href
            except Exception as exc:
                errors.append({"url": url, "error": str(exc)})
            time.sleep(2 + random.random())
        browser.close()
    return list(pdfs.items())[:max_links], errors
