"""
E-Commerce Domain — FAST Ingestion (no Gemini KG extraction per chunk)
Reads all files, chunks them, embeds, stores in Qdrant only.
Run this for quick batch indexing. KG extraction can be done separately.
"""
import asyncio, json, sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.domain import Domain
from app.rag.chunking.semantic import semantic_chunking
from app.rag.retrieval.qdrant_service import qdrant_service

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "ecommerce"
DOMAIN = Domain.ECOMMERCE
MAX_CHARS = 50_000

def read_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            print(f"  PDF read error {path.name}: {e}")
            return ""
    elif ext == ".html":
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(path.read_bytes(), "html.parser")
            for t in soup(["script", "style"]):
                t.decompose()
            return soup.get_text(separator=" ", strip=True)
        except Exception as e:
            print(f"  HTML read error {path.name}: {e}")
            return ""
    else:
        return path.read_text(encoding="utf-8", errors="ignore")

async def run_pipeline():
    print(f"E-Commerce Fast Ingest — {KNOWLEDGE_ROOT}")
    docs = total_chunks = 0

    all_files = []
    for fpath in KNOWLEDGE_ROOT.rglob("*"):
        if not fpath.is_file():
            continue
        if "metadata" in fpath.parts:
            continue
        if fpath.suffix.lower() not in (".md", ".pdf", ".txt", ".html"):
            continue
        all_files.append(fpath)

    print(f"Found {len(all_files)} files to process...")

    for fpath in sorted(all_files):
        text = read_file(fpath)
        if not text or len(text.strip()) < 50:
            continue
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]

        # find metadata sidecar
        rel = fpath.relative_to(KNOWLEDGE_ROOT)
        parts = list(rel.parts)
        meta_path = KNOWLEDGE_ROOT / "metadata" / Path(*parts[:-1]) / f"{fpath.stem}.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        doc_id = str(uuid5(NAMESPACE_URL, f"{DOMAIN.value}:{rel}"))
        try:
            chunks = semantic_chunking(text, chunk_size=350, overlap=80)
        except Exception as e:
            print(f"  Chunking error {fpath.name}: {e} — skipping")
            continue

        if not chunks:
            continue

        try:
            await qdrant_service.upsert_chunks(DOMAIN, doc_id, chunks, meta)
        except Exception as e:
            print(f"  Qdrant error {fpath.name}: {e} — skipping")
            continue

        print(f"  [{docs+1:03d}] {fpath.name:<50s} -> {len(chunks):3d} chunks")
        docs += 1
        total_chunks += len(chunks)

    print(f"\nDone!")
    print(f"  Domain   : {DOMAIN.value}")
    print(f"  Documents: {docs}")
    print(f"  Chunks   : {total_chunks}")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
