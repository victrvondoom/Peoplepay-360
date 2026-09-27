"""
Government Domain - Full Data Collection Script
Downloads real content from official Indian government citizen-service portals
(India.gov.in, CPGRAMS, UIDAI, Passport Seva/MEA, Income Tax, Protean/NSDL PAN,
DigiLocker, RTI Online, National Consumer Helpline, data.gov.in) plus background
Wikipedia overviews, and stores it in the correct folder structure under
knowledge/government/, driven by government_source_registry.json.
"""
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "government"
REGISTRY_PATH = KNOWLEDGE_ROOT / "government_source_registry.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def html_to_text(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)


def save(folder: str, name: str, content: bytes, ext: str, metadata: dict):
    dest_dir = KNOWLEDGE_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / f"{name}.{ext}"
    filepath.write_bytes(content)

    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{name}.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return filepath


def download(source: dict) -> bool:
    url = source["url"]
    folder = source["folder"]
    name = source["slug"]
    title = source["title"]
    authority = source["authority"]
    print(f"  GET {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code not in (200, 301, 302):
            print(f"    -> HTTP {resp.status_code} — skipping")
            return False

        is_pdf = (
            url.lower().endswith(".pdf")
            or resp.headers.get("Content-Type", "").startswith("application/pdf")
        )

        if is_pdf:
            filepath = save(
                folder, name, resp.content, "pdf",
                {"title": title, "authority": authority, "source_url": url,
                 "domain": "government", "type": "pdf", "category": source.get("category")}
            )
        else:
            text = html_to_text(resp.content)
            if len(text) < 200:
                print(f"    -> Too little content ({len(text)} chars) — skipping")
                return False
            filepath = save(
                folder, name, text.encode("utf-8"), "txt",
                {"title": title, "authority": authority, "source_url": url,
                 "domain": "government", "type": "html_text",
                 "category": source.get("category"), "raw_chars": len(text)}
            )

        size_kb = filepath.stat().st_size // 1024
        print(f"    -> Saved {size_kb} KB  =>  {filepath.relative_to(KNOWLEDGE_ROOT)}")
        return True

    except Exception as exc:
        print(f"    -> ERROR: {exc}")
        return False


def main():
    print("=" * 60)
    print("GOVERNMENT DOMAIN — LIVE DATA DOWNLOAD")
    print("=" * 60)

    sources = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    ok = fail = 0
    for src in sources:
        success = download(src)
        if success:
            ok += 1
        else:
            fail += 1
        time.sleep(1)  # polite crawl delay

    print("=" * 60)
    print(f"Done.  Downloaded: {ok}   Failed: {fail}   Total: {ok + fail}")
    print("=" * 60)


if __name__ == "__main__":
    main()
