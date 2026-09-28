from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
import json

from app.database.postgres.repositories import case_repository
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.models.domain import Domain
from app.rag.chunking.text import chunk_text
from app.rag.indexing.service import indexing_service

SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".pdf"}
SKIP_NAMES = {"source_registry.json", "insurer_registry.json", "download_report.json", "curation_report.json"}
SKIP_PARTS = {"metadata", "embeddings"}


class KnowledgeIngestionService:
    def iter_documents(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        documents: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.name in SKIP_NAMES or any(part in SKIP_PARTS for part in path.parts):
                continue
            metadata = self.sidecar_metadata(root, path)
            if path.suffix.lower() == ".pdf" and not self.pdf_allowed_by_metadata(metadata):
                continue
            documents.append(path)
        return documents

    def sidecar_metadata(self, root: Path, path: Path) -> dict:
        metadata_root = root / "metadata"
        if metadata_root.exists():
            candidates = list(metadata_root.rglob(f"{path.stem}.json"))
            if candidates:
                try:
                    return json.loads(candidates[0].read_text(encoding="utf-8"))
                except Exception:
                    return {}
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and {"authority", "category", "url"}.intersection(payload.keys()):
                    return payload
            except Exception:
                return {}
        return {}

    def pdf_allowed_by_metadata(self, metadata: dict) -> bool:
        return bool(metadata.get("health_insurance_relevant", True))

    def read_text(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            return self.read_pdf_text(path)
        return path.read_text(encoding="utf-8", errors="ignore")

    def read_pdf_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(page for page in pages if page.strip())
        except Exception:
            return ""

    def source_record(self, domain: Domain, document_id: str, document_path: Path, text: str, metadata: dict) -> dict:
        title = metadata.get("title") or metadata.get("label") or document_path.stem
        return {
            "source_id": document_id,
            "domain": domain.value,
            "title": title,
            "source_path": str(document_path),
            "filename": document_path.name,
            "category": metadata.get("category") or document_path.parent.name,
            "authority": metadata.get("authority") or metadata.get("insurer_name") or metadata.get("official_domain"),
            "final_url": metadata.get("final_url") or metadata.get("url"),
            "content_sha256": metadata.get("content_sha256") or str(uuid5(NAMESPACE_URL, text or document_path.as_posix())),
            "metadata": metadata,
        }

    def document_metadata(self, domain: Domain, root: Path, document_path: Path) -> dict:
        sidecar = self.sidecar_metadata(root, document_path)
        metadata = {
            "domain": domain.value,
            "source_path": str(document_path),
            "filename": document_path.name,
            "title": sidecar.get("title") or sidecar.get("label") or document_path.stem,
            "knowledge_type": sidecar.get("category") or document_path.parent.name,
            "category": sidecar.get("category") or document_path.parent.name,
            "file_extension": document_path.suffix.lower(),
        }
        metadata.update({key: value for key, value in sidecar.items() if value is not None})
        return metadata

    async def ingest_path(self, domain: Domain, root: Path) -> dict:
        documents = self.iter_documents(root)
        indexed_chunks = 0
        graph_documents = 0
        supabase_sources = 0
        supabase_chunks = 0
        skipped_empty = 0
        results: list[dict] = []

        for document_path in documents:
            text = self.read_text(document_path)
            if not text.strip():
                skipped_empty += 1
                continue
            document_id = str(uuid5(NAMESPACE_URL, f"{domain.value}:{document_path.as_posix()}"))
            metadata = self.document_metadata(domain, root, document_path)
            source = self.source_record(domain, document_id, document_path, text, metadata)
            await case_repository.upsert_knowledge_source(source)
            supabase_sources += 1

            chunks = chunk_text(text)
            chunk_records = [
                {
                    "chunk_id": str(uuid5(NAMESPACE_URL, f"{document_id}:{index}")),
                    "chunk_index": index,
                    "text": chunk,
                    "metadata": metadata,
                }
                for index, chunk in enumerate(chunks)
            ]
            supabase_chunks += await case_repository.add_knowledge_chunks(document_id, chunk_records)
            chunk_count = await indexing_service.index_document_text(domain, document_id, text, metadata)
            graph_result = await knowledge_graph.upsert_knowledge_document(
                domain=domain,
                document_id=document_id,
                title=source["title"],
                source_path=str(document_path),
                metadata=metadata,
            )
            indexed_chunks += chunk_count
            graph_documents += 1
            results.append({"document_id": document_id, "path": str(document_path), "chunks": chunk_count, "graph": graph_result})

        from app.rag.retrieval.factory import get_vector_store

        get_vector_store().flush()

        return {
            "domain": domain.value,
            "root": str(root),
            "documents_found": len(documents),
            "documents_ingested": graph_documents,
            "chunks_indexed": indexed_chunks,
            "supabase_sources": supabase_sources,
            "supabase_chunks": supabase_chunks,
            "skipped_empty": skipped_empty,
            "results": results,
        }


knowledge_ingestion_service = KnowledgeIngestionService()
