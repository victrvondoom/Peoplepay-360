from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = ROOT / "knowledge" / "government"
CHUNK_PATH = KNOWLEDGE_ROOT / "chunks" / "government_chunks.jsonl"
MANIFEST_PATH = KNOWLEDGE_ROOT / "government_corpus_manifest.json"
REPORT_PATH = KNOWLEDGE_ROOT / "government_ingestion_report.json"
SKIP_PARTS = {"metadata", "chunks", "knowledge_graph", "synthetic_cases"}
TEXT_EXTS = {".txt", ".md", ".html"}
DOC_EXTS = TEXT_EXTS | {".pdf"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_text(path: Path) -> str:
    if path.suffix.lower() in TEXT_EXTS:
        return path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""
    return ""


def chunk_text(text: str, chunk_chars: int = 3200, overlap: int = 450) -> list[str]:
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + chunk_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def metadata_for(path: Path) -> dict:
    rel = path.relative_to(KNOWLEDGE_ROOT)
    candidates = [
        KNOWLEDGE_ROOT / "metadata" / rel.parent / f"{path.stem}.json",
        KNOWLEDGE_ROOT / "metadata" / rel.parent.name / f"{path.stem}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
    return {}


def main() -> None:
    files = []
    chunks = 0
    ext_counts: Counter[str] = Counter()
    authority_counts: Counter[str] = Counter()
    folder_counts: Counter[str] = Counter()
    chunk_counts: defaultdict[str, int] = defaultdict(int)
    CHUNK_PATH.parent.mkdir(parents=True, exist_ok=True)

    with CHUNK_PATH.open("w", encoding="utf-8") as chunk_file:
        for path in sorted(KNOWLEDGE_ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(KNOWLEDGE_ROOT)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            if path.suffix.lower() not in DOC_EXTS:
                continue

            meta = metadata_for(path)
            if meta.get("authority") == "Wikipedia":
                continue
            text = read_text(path)
            doc_chunks = chunk_text(text)
            for index, chunk in enumerate(doc_chunks):
                record = {
                    "domain": "government",
                    "source_path": str(rel).replace("\\", "/"),
                    "chunk_index": index,
                    "text": chunk,
                    "metadata": {
                        "title": meta.get("title", path.stem),
                        "authority": meta.get("authority", "unknown"),
                        "category": meta.get("category", rel.parts[0] if rel.parts else "government"),
                        "source_url": meta.get("source_url"),
                    },
                }
                chunk_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            chunks += len(doc_chunks)
            chunk_counts[str(rel).replace("\\", "/")] = len(doc_chunks)
            ext_counts[path.suffix.lower()] += 1
            authority_counts[meta.get("authority", "unknown")] += 1
            folder_counts[rel.parts[0] if rel.parts else "root"] += 1
            files.append({
                "path": str(rel).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "chunks": len(doc_chunks),
                "title": meta.get("title", path.stem),
                "authority": meta.get("authority", "unknown"),
                "category": meta.get("category"),
                "source_url": meta.get("source_url"),
            })

    manifest = {
        "domain": "government",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(KNOWLEDGE_ROOT.relative_to(ROOT)).replace("\\", "/"),
        "files_total": len(files),
        "chunks_total": chunks,
        "bytes_total": sum(item["bytes"] for item in files),
        "extension_counts": dict(sorted(ext_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "folder_counts": dict(sorted(folder_counts.items())),
        "chunk_file": str(CHUNK_PATH.relative_to(ROOT)).replace("\\", "/"),
        "graph_seed_files": [
            "knowledge/government/knowledge_graph/government_entities.jsonl",
            "knowledge/government/knowledge_graph/government_relationships.jsonl",
        ],
        "files": files,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    report = {}
    if REPORT_PATH.exists():
        try:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
    report.update({
        "domain": "government",
        "generated_at": manifest["generated_at"],
        "local_corpus": {
            "files_total": manifest["files_total"],
            "chunks_total": manifest["chunks_total"],
            "bytes_total": manifest["bytes_total"],
            "extension_counts": manifest["extension_counts"],
            "authority_counts": manifest["authority_counts"],
            "chunk_file": manifest["chunk_file"],
            "manifest_file": "knowledge/government/government_corpus_manifest.json",
        },
    })
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["local_corpus"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
