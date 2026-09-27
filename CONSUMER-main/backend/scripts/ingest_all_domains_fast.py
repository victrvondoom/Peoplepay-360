"""
PROXY — Knowledge Base Cleaner + Unified Fast Ingestion
1. Removes low-quality / noisy files (Wikipedia citations, nav boilerplate, tiny files)
2. Cleans all existing text files (strip [1][2] citation refs, dedupe blank lines)
3. Runs fast batch ingestion across ALL domains into Qdrant
"""
import asyncio, json, re, sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.domain import Domain
from app.rag.chunking.semantic import semantic_chunking
from app.rag.retrieval.qdrant_service import qdrant_service

REPO_ROOT      = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"

MAX_CHARS  = 50_000
CHUNK_SIZE = 350
OVERLAP    = 80
MIN_CHARS  = 300   # files below this are too short to be useful

SUPPORTED_EXTS = {".txt", ".md", ".pdf", ".html"}

DOMAIN_MAP = {
    Domain.BANKING:          KNOWLEDGE_ROOT / "banking",
    Domain.AIRLINES:         KNOWLEDGE_ROOT / "airlines",
    Domain.TELECOM:          KNOWLEDGE_ROOT / "telecom",
    Domain.ECOMMERCE:        KNOWLEDGE_ROOT / "ecommerce",
    Domain.HEALTH_INSURANCE: KNOWLEDGE_ROOT / "health_insurance",
}

# Files that contain only noise — delete them
NOISE_PATTERNS = [
    "*test*", "*debug*", "*.tmp",
]

# Text-level cleaning: remove Wikipedia citation artefacts, nav spam, etc.
_WIKI_CITE_RE  = re.compile(r"\[\d+\]")          # [1] [23] etc.
_WIKI_EDIT_RE  = re.compile(r"\[edit\]", re.I)
_BLANK_MULTI   = re.compile(r"\n{3,}")
_REPEATED_DASH = re.compile(r"-{4,}")
_EXTERNAL_LINK = re.compile(r"https?://\S+")     # strip raw URLs in running text


def clean_text(text: str) -> str:
    text = _WIKI_CITE_RE.sub("", text)
    text = _WIKI_EDIT_RE.sub("", text)
    text = _REPEATED_DASH.sub("", text)
    # Remove lines that are purely nav / boilerplate
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # Skip lines that are just numbers, single chars, or pure-URL lines
        if re.fullmatch(r"[\d\s\|•▸▾→←]+", stripped):
            continue
        if re.fullmatch(r"https?://\S+", stripped):
            continue
        if len(stripped) < 3:
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = _BLANK_MULTI.sub("\n\n", text)
    return text.strip()


def read_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            print(f"    [PDF ERR] {path.name}: {e}")
            return ""
    elif ext == ".html":
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(path.read_bytes(), "html.parser")
            for t in soup(["script", "style", "nav", "footer", "header", "noscript",
                           "aside", ".mw-editsection", ".mw-references-wrap"]):
                t.decompose()
            return soup.get_text(separator="\n", strip=True)
        except Exception as e:
            print(f"    [HTML ERR] {path.name}: {e}")
            return ""
    else:
        return path.read_text(encoding="utf-8", errors="ignore")


def find_meta(domain_root: Path, fpath: Path) -> dict:
    rel   = fpath.relative_to(domain_root)
    parts = list(rel.parts)
    meta_path = domain_root / "metadata" / Path(*parts[:-1]) / f"{fpath.stem}.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"domain": domain_root.name}


async def ingest_domain(domain: Domain, domain_root: Path):
    if not domain_root.exists():
        print(f"  [SKIP] Not found: {domain_root}")
        return 0, 0

    files = [
        f for f in domain_root.rglob("*")
        if f.is_file()
        and f.suffix.lower() in SUPPORTED_EXTS
        and "metadata" not in f.parts
    ]

    docs = chunks_total = skipped = 0

    for fpath in sorted(files):
        raw = read_file(fpath)
        if not raw:
            continue

        text = clean_text(raw)

        # Skip files that are still too short after cleaning
        if len(text.strip()) < MIN_CHARS:
            skipped += 1
            continue

        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]

        meta   = find_meta(domain_root, fpath)
        doc_id = str(uuid5(NAMESPACE_URL, f"{domain.value}:{fpath.relative_to(domain_root)}"))

        try:
            chunks = semantic_chunking(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
        except Exception as e:
            print(f"    [CHUNK ERR] {fpath.name}: {e}")
            continue

        if not chunks:
            skipped += 1
            continue

        try:
            await qdrant_service.upsert_chunks(domain, doc_id, chunks, meta)
        except Exception as e:
            print(f"    [QDRANT ERR] {fpath.name}: {e}")
            continue

        rel = str(fpath.relative_to(domain_root))
        print(f"    [{docs+1:04d}] {rel:<55s} {len(chunks):3d} chunks")
        docs         += 1
        chunks_total += len(chunks)

    if skipped:
        print(f"    [INFO] Skipped {skipped} low-quality / too-short files")

    return docs, chunks_total


async def main():
    print("=" * 65)
    print("PROXY — CLEAN + UNIFIED FAST BATCH INGESTION")
    print("=" * 65)
    grand_docs = grand_chunks = 0

    for domain, root in DOMAIN_MAP.items():
        print(f"\n>>> [{domain.value.upper()}]  ({root})")
        d, c = await ingest_domain(domain, root)
        print(f"    Subtotal: {d} docs indexed, {c} chunks stored")
        grand_docs   += d
        grand_chunks += c

    print("\n" + "=" * 65)
    print(f"TOTAL DOCUMENTS INDEXED : {grand_docs}")
    print(f"TOTAL CHUNKS STORED     : {grand_chunks}")
    print("All domains are now searchable in Qdrant.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
