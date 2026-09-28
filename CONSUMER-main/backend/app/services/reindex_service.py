"""Resumable per-domain reindex pipeline: read the knowledge/<domain> corpus,
chunk it, embed with the currently configured LLM provider, and upsert into a
NEW versioned Qdrant/jsonl collection — never overwriting the active one in
place. The active collection only switches once the new one is verified.

Progress is checkpointed to disk after every file, so a job interrupted
mid-run (process restart, crash) resumes from the last completed file the
next time it's triggered instead of starting over.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.llm.service import llm_service
from app.models.domain import Domain
from app.rag.chunking.semantic import semantic_chunking
from app.rag.retrieval.collection_registry import get_collection_registry
from app.rag.retrieval.factory import get_vector_store
from app.rag.source_metadata import load_source_metadata

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[3] / "knowledge"
JOB_STATE_ROOT = Path("datasets") / "reindex_jobs"
SKIP_DIR_NAMES = {"metadata", "chunks", "knowledge_graph", "synthetic_cases", "embeddings"}
DOC_EXTENSIONS = {".txt", ".md", ".pdf", ".html"}
# Genuine policy/regulatory documents run at most a few hundred pages of dense
# text. A handful of "policy documents" in real scraped corpora turn out to be
# administrative dumps mislabeled as consumer content (e.g. a multi-thousand-page
# internal agent-code registry) — extracted text this long is a strong signal
# of exactly that, not a document worth chunking into thousands of near-duplicate
# vectors. Flagged in the job report rather than silently dropped.
MAX_DOCUMENT_CHARS = 300_000
# Same rationale, checked before paying the cost of extracting text from every
# page — a genuine policy/regulatory PDF is rarely more than a few hundred
# pages; thousands of pages is the administrative-dump signal on its own.
MAX_PDF_PAGES = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _OversizedDocument(Exception):
    """Raised when a PDF's page count alone signals an administrative dump
    not worth the cost of full text extraction (see MAX_PDF_PAGES)."""


def _read_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            if len(reader.pages) > MAX_PDF_PAGES:
                raise _OversizedDocument(f"{len(reader.pages)} pages")
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except _OversizedDocument:
            raise
        except Exception:
            return ""
    if ext == ".html":
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(path.read_bytes(), "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)
        except Exception:
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def discover_files(domain: Domain) -> list[Path]:
    root = KNOWLEDGE_ROOT / domain.value
    if not root.exists():
        return []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in DOC_EXTENSIONS:
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        files.append(path)
    return files


@dataclass
class ReindexJob:
    domain: str
    status: str = "idle"  # idle | running | verifying | completed | failed | failed_verification
    version_label: str | None = None
    collection_name: str | None = None
    provider: str | None = None
    embedding_model: str | None = None
    target_dimension: int | None = None
    total_files: int = 0
    processed_files: list[str] = field(default_factory=list)
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    retries: int = 0
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    eta_seconds: float | None = None
    error: str | None = None
    skipped_oversized_files: list[str] = field(default_factory=list)

    @property
    def progress_percent(self) -> float:
        if self.total_files == 0:
            return 0.0
        return round(100 * len(self.processed_files) / self.total_files, 1)

    def to_dict(self) -> dict:
        return {**asdict(self), "progress_percent": self.progress_percent}


def _state_path(domain: Domain) -> Path:
    JOB_STATE_ROOT.mkdir(parents=True, exist_ok=True)
    return JOB_STATE_ROOT / f"{domain.value}.json"


_JOB_FIELDS = {f.name for f in ReindexJob.__dataclass_fields__.values()}


def load_job(domain: Domain) -> ReindexJob | None:
    path = _state_path(domain)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # to_dict() adds the computed progress_percent property for API responses;
        # strip it (and any other non-field keys) before reconstructing the dataclass.
        return ReindexJob(**{k: v for k, v in data.items() if k in _JOB_FIELDS})
    except (json.JSONDecodeError, TypeError):
        return None


def _save_job(job: ReindexJob) -> None:
    job.updated_at = _now()
    _state_path(Domain(job.domain)).write_text(json.dumps(job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def _new_collection_name(domain: Domain, prefix: str, version_label: str, provider: str, dimension: int) -> str:
    return f"{prefix}_{domain.value}_{version_label}_{provider}_{dimension}"


async def run_reindex(domain: Domain) -> ReindexJob:
    settings = get_settings()
    registry = get_collection_registry()
    store = get_vector_store()

    existing = load_job(domain)
    resuming = bool(existing and existing.status in {"running", "failed", "failed_verification", "verifying"})

    provider_name = llm_service.name
    dimension = llm_service.embedding_dimension
    embedding_model = settings.nvidia_embedding_model if provider_name == "nvidia" else settings.embedding_model

    if resuming and existing and existing.version_label:
        job = existing
        job.status = "running"
    else:
        version_label = registry.next_version_label(domain.value)
        collection_name = _new_collection_name(domain, settings.qdrant_collection_prefix, version_label, provider_name, dimension)
        job = ReindexJob(
            domain=domain.value,
            status="running",
            version_label=version_label,
            collection_name=collection_name,
            provider=provider_name,
            embedding_model=embedding_model,
            target_dimension=dimension,
            started_at=_now(),
        )
        registry.register_version(
            domain.value, version_label,
            collection_name=collection_name, provider=provider_name,
            embedding_model=embedding_model, dimension=dimension, status="building",
        )

    files = discover_files(domain)
    job.total_files = len(files)
    processed_set = set(job.processed_files)
    remaining = [f for f in files if str(f.relative_to(KNOWLEDGE_ROOT / domain.value)) not in processed_set]
    _save_job(job)

    start_time = time.monotonic()
    for path in remaining:
        rel_path = str(path.relative_to(KNOWLEDGE_ROOT / domain.value))
        try:
            text = _read_file(path)
        except _OversizedDocument as exc:
            job.skipped_oversized_files.append(f"{rel_path} ({exc})")
            job.processed_files.append(rel_path)
            _save_job(job)
            continue
        if not text or len(text.strip()) < 50:
            job.processed_files.append(rel_path)
            _save_job(job)
            continue

        if len(text) > MAX_DOCUMENT_CHARS:
            job.skipped_oversized_files.append(f"{rel_path} ({len(text):,} chars)")
            job.processed_files.append(rel_path)
            _save_job(job)
            continue

        # chunk_size is denominated in "tokens" via a 4-chars/token estimate inside
        # semantic_chunking, but dense legal/tabular text (the norm for regulatory
        # PDFs here) commonly runs closer to 1.5-2 chars/token — a 350-token budget
        # can produce chunks NVIDIA's 512-token embedding limit rejects. 180 keeps
        # the resulting ~720-char chunks under that limit even for dense text, so
        # the fast batch path succeeds instead of falling back to the (correct but
        # much slower, one-rate-limited-call-per-chunk) per-text shrink path.
        chunks = semantic_chunking(text, chunk_size=180, overlap=40)
        job.total_chunks += len(chunks)

        attempt = 0
        while attempt <= 1:
            try:
                vectors = await llm_service.embed_documents(chunks)
                from uuid import NAMESPACE_URL, uuid5

                # Merge the scrape/seed script's sidecar metadata (authority,
                # category, source_url, title) into every chunk's payload so
                # evidence scoring and citations don't need a disk lookup at
                # query time. Falls back to {} for synthetic/authored content
                # that never had a sidecar file.
                source_meta = load_source_metadata(domain, rel_path)
                points = [
                    {
                        "id": str(uuid5(NAMESPACE_URL, f"{domain.value}:{job.version_label}:{rel_path}:{i}")),
                        "vector": vector,
                        "payload": {
                            "document_id": rel_path,
                            "chunk_index": i,
                            "text": chunk,
                            "domain": domain.value,
                            "source_path": rel_path,
                            **source_meta,
                        },
                    }
                    for i, (chunk, vector) in enumerate(zip(chunks, vectors))
                ]
                store.upsert_batch(job.collection_name, points)
                job.completed_chunks += len(points)
                break
            except Exception as exc:
                attempt += 1
                job.retries += 1
                if attempt > 1:
                    job.failed_chunks += len(chunks)
                    job.error = f"{rel_path}: {exc}"

        job.processed_files.append(rel_path)
        # Flush after every file so the checkpoint and the actual stored data
        # stay consistent — if this process is interrupted right after this
        # point, the job state and the vector store agree on what's really
        # been persisted, and a resume never has to re-embed a "done" file.
        store.flush(job.collection_name)
        elapsed = time.monotonic() - start_time
        done = len(job.processed_files)
        if done and job.total_files:
            rate = elapsed / done
            job.eta_seconds = round(rate * (job.total_files - done), 1)
        _save_job(job)

    # Verification: confirm the new collection actually holds the chunks we sent it.
    job.status = "verifying"
    _save_job(job)
    actual_count = store.count(job.collection_name)
    registry.update_version(domain.value, job.version_label, chunk_count=actual_count)

    if actual_count >= job.completed_chunks > 0 or (job.total_chunks == 0 and job.total_files == 0):
        registry.activate_version(domain.value, job.version_label)
        job.status = "completed"
        job.finished_at = _now()
        job.eta_seconds = 0
    else:
        job.status = "failed_verification"
        job.error = job.error or f"expected >= {job.completed_chunks} chunks, found {actual_count}"
        registry.mark_needs_reindex(domain.value, job.version_label)

    _save_job(job)
    return job
