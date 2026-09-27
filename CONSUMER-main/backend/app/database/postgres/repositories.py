from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.database.supabase.client import get_supabase
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.models.domain import Domain
from app.schemas.cases import CaseCreate, CaseStatus


class LocalRepositoryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("datasets") / "app_store"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, table: str) -> Path:
        return self.root / f"{table}.jsonl"

    def read(self, table: str) -> list[dict]:
        path = self.path(table)
        if not path.exists():
            return []
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def upsert(self, table: str, key: str, row: dict) -> dict:
        rows = self.read(table)
        replaced = False
        for index, existing in enumerate(rows):
            if existing.get(key) == row.get(key):
                rows[index] = row
                replaced = True
                break
        if not replaced:
            rows.append(row)
        self.write(table, rows)
        return row

    def append(self, table: str, row: dict) -> dict:
        path = self.path(table)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
        return row

    def append_many(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        path = self.path(table)
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
        return len(rows)

    def write(self, table: str, rows: list[dict]) -> None:
        path = self.path(table)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")


class CaseRepository:
    """Repository boundary for Supabase/Postgres with durable local fallback."""

    def __init__(self) -> None:
        self._cases: dict[str, dict] = {}
        self._documents: dict[str, dict] = {}
        self._events: list[dict] = []
        self._agent_runs: dict[str, dict] = {}
        self._appeals: dict[str, dict] = {}
        self._knowledge_sources: dict[str, dict] = {}
        self._knowledge_chunks: dict[str, dict] = {}
        self.local = LocalRepositoryStore()
        self.supabase = get_supabase()
        self._hydrate_local()

    def _hydrate_local(self) -> None:
        for row in self.local.read("cases"):
            row["domain"] = Domain(row["domain"]) if isinstance(row.get("domain"), str) else row.get("domain")
            row["status"] = CaseStatus(row["status"]) if isinstance(row.get("status"), str) else row.get("status")
            self._cases[row["id"]] = row
        self._documents = {row["document_id"]: row for row in self.local.read("case_documents")}
        self._events = self.local.read("case_events")
        self._agent_runs = {row["id"]: row for row in self.local.read("agent_runs")}
        self._appeals = {row["id"]: row for row in self.local.read("appeals")}
        self._knowledge_sources = {row["source_id"]: row for row in self.local.read("knowledge_sources")}
        self._knowledge_chunks = {row["chunk_id"]: row for row in self.local.read("knowledge_chunks")}

    def _jsonable(self, value):
        if isinstance(value, Domain) or isinstance(value, CaseStatus):
            return value.value
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        return value

    async def create_case(self, user_id: str, payload: CaseCreate, case_id: str | None = None) -> dict:
        case_id = case_id or str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": case_id,
            "user_id": user_id,
            "domain": payload.domain,
            "title": payload.title,
            "institution_name": payload.institution_name,
            "summary": payload.summary,
            "jurisdiction": payload.jurisdiction,
            "status": CaseStatus.INTAKE,
            "created_at": now,
            "updated_at": now,
        }
        self._cases[case_id] = record
        stored = self._jsonable(record)
        self.local.upsert("cases", "id", stored)
        await self.supabase.upsert("cases", stored, on_conflict="id")
        await self.add_event(case_id, {"actor": "user", "event_type": "case_created", "title": "Case created", "body": payload.summary})
        await knowledge_graph.upsert_case_graph(record)
        return record

    async def update_case_status(self, case_id: str, status: CaseStatus) -> dict | None:
        case = self._cases.get(case_id)
        if not case:
            return None
        case["status"] = status
        case["updated_at"] = datetime.now(timezone.utc).isoformat()
        stored = self._jsonable(case)
        self.local.upsert("cases", "id", stored)
        await self.supabase.upsert("cases", stored, on_conflict="id")
        return case

    _VAULT_TITLE = "Document Vault"

    async def get_or_create_vault_case(self, user_id: str, domain: Domain) -> dict:
        """A stable, lazily-created case per (user, domain) for documents
        uploaded from the Document Vault UI rather than a specific dispute
        case -- so uploading a file only ever requires picking a domain, not
        first filling out a full case-creation form (title/institution/
        summary), while every upload still has a real case to attach to
        (indexing, knowledge-graph registration, and storage paths all key
        off case_id)."""
        existing = [
            case for case in self._cases.values()
            if case["user_id"] == user_id and case["domain"] == domain and case.get("title") == self._VAULT_TITLE
        ]
        if existing:
            return existing[0]
        return await self.create_case(user_id, CaseCreate(
            domain=domain,
            title=self._VAULT_TITLE,
            institution_name="Not specified",
            summary=f"Documents uploaded to the {domain.value} document vault, not tied to a specific dispute case.",
        ))

    async def get_case(self, case_id: str, user_id: str) -> dict | None:
        case = self._cases.get(case_id)
        if case and case["user_id"] == user_id:
            return case
        rows = await self.supabase.select("cases", {"id": case_id, "user_id": user_id}, limit=1)
        if not rows:
            return None
        row = rows[0]
        row["domain"] = Domain(row["domain"])
        row["status"] = CaseStatus(row["status"])
        self._cases[row["id"]] = row
        return row

    async def list_cases(self, user_id: str, domain: Domain | None = None) -> list[dict]:
        rows = [case for case in self._cases.values() if case["user_id"] == user_id]
        if domain:
            rows = [case for case in rows if case["domain"] == domain]
        return rows

    async def list_analyses_for_user(self, user_id: str) -> list[dict]:
        """Every case enriched with its agent-run results -- confidence,
        which domains were actually analyzed, and how many runs completed
        vs failed -- so "My Analyses" can show real status/confidence
        instead of just the raw case record."""
        cases = await self.list_cases(user_id)
        analyses = []
        for case in cases:
            runs = [run for run in self._agent_runs.values() if run["case_id"] == case["id"]]
            confidences = [
                run["output"]["confidence"] for run in runs
                if isinstance(run.get("output"), dict) and isinstance(run["output"].get("confidence"), (int, float))
            ]
            domains_involved = sorted({
                run["output"].get("domain") for run in runs
                if isinstance(run.get("output"), dict) and run["output"].get("domain")
            }) or [case["domain"].value if hasattr(case["domain"], "value") else case["domain"]]
            analyses.append({
                **self._jsonable(case),
                "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
                "run_count": len(runs),
                "completed_runs": sum(1 for run in runs if run.get("status") == "completed"),
                "domains_involved": domains_involved,
            })
        return sorted(analyses, key=lambda a: a.get("updated_at") or a.get("created_at") or "", reverse=True)

    async def add_document(self, document: dict) -> dict:
        document.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        self._documents[document["document_id"]] = document
        stored = self._jsonable(document)
        self.local.upsert("case_documents", "document_id", stored)
        supabase_document = {key: value for key, value in stored.items() if key not in {"document_id", "chunks_indexed"}}
        await self.supabase.upsert("case_documents", supabase_document, on_conflict="id")
        await self.add_event(
            document["case_id"],
            {
                "actor": "system",
                "event_type": "document_uploaded",
                "title": f"Document uploaded: {document['filename']}",
                "body": f"Indexed: {document.get('indexed', False)}",
            },
        )
        return document

    async def list_documents(self, case_id: str) -> list[dict]:
        return [document for document in self._documents.values() if document["case_id"] == case_id]

    async def list_documents_for_user(self, user_id: str) -> list[dict]:
        documents = [document for document in self._documents.values() if document["user_id"] == user_id]
        return sorted(documents, key=lambda d: d.get("created_at") or "", reverse=True)

    async def get_documents_by_ids(self, document_ids: list[str], user_id: str) -> list[dict]:
        """Fetch specific documents by id, scoped to `user_id` -- used to pull
        the exact set of documents a caller uploaded for one analysis run
        (regardless of which case/vault they're attached to), rather than
        every document ever uploaded to that domain's vault."""
        return [
            self._documents[document_id]
            for document_id in document_ids
            if document_id in self._documents and self._documents[document_id]["user_id"] == user_id
        ]

    async def delete_document(self, document_id: str, user_id: str) -> bool:
        document = self._documents.get(document_id)
        if not document or document["user_id"] != user_id:
            return False
        del self._documents[document_id]
        self.local.write("case_documents", [self._jsonable(d) for d in self._documents.values()])
        await self.supabase.delete("case_documents", {"id": document_id})
        return True

    async def add_event(self, case_id: str, event: dict) -> dict:
        record = {"id": str(uuid4()), "case_id": case_id, "created_at": datetime.now(timezone.utc).isoformat(), **event}
        self._events.append(record)
        self.local.append("case_events", self._jsonable(record))
        await self.supabase.insert("case_events", self._jsonable(record))
        return record

    async def list_events(self, case_id: str) -> list[dict]:
        return [event for event in self._events if event["case_id"] == case_id]

    def _user_case_ids(self, user_id: str) -> set[str]:
        """Events don't carry user_id directly (several call sites -- e.g.
        add_agent_run -- don't have it in scope), so cross-case queries
        correlate via case_id instead: every case_id the user has any
        relationship with, across real Cases, appeals, and documents (the
        synthetic per-query case_ids from the multi-domain assistant
        workflow never create a real Case row, so appeals/documents are the
        only source of truth for those)."""
        ids = {case["id"] for case in self._cases.values() if case["user_id"] == user_id}
        ids |= {appeal["case_id"] for appeal in self._appeals.values() if appeal["user_id"] == user_id}
        ids |= {doc["case_id"] for doc in self._documents.values() if doc["user_id"] == user_id}
        return ids

    async def list_events_for_user(self, user_id: str, limit: int = 50, before: str | None = None) -> list[dict]:
        case_ids = self._user_case_ids(user_id)
        events = [event for event in self._events if event["case_id"] in case_ids]
        if before:
            events = [event for event in events if (event.get("created_at") or "") < before]
        return sorted(events, key=lambda e: e.get("created_at") or "", reverse=True)[:limit]

    async def add_agent_run(self, case_id: str, workflow_name: str, status: str, input_payload: dict, output_payload: dict, error: str | None = None) -> dict:
        run = {
            "id": str(uuid4()),
            "case_id": case_id,
            "workflow_name": workflow_name,
            "status": status,
            "input": input_payload,
            "output": output_payload,
            "error": error,
        }
        self._agent_runs[run["id"]] = run
        stored = self._jsonable(run)
        self.local.append("agent_runs", stored)
        await self.supabase.insert("agent_runs", stored)
        await self.add_event(case_id, {"actor": "agent", "event_type": "agent_run", "title": f"{workflow_name} finished", "body": status})
        return run

    async def list_agent_runs(self, case_id: str) -> list[dict]:
        return [run for run in self._agent_runs.values() if run["case_id"] == case_id]

    async def add_appeal(
        self, case_id: str, user_id: str, title: str, content: str,
        *, document_type: str = "appeal_letter", domain: str | None = None,
    ) -> dict:
        version = 1 + len([appeal for appeal in self._appeals.values() if appeal["case_id"] == case_id])
        appeal = {
            "id": str(uuid4()),
            "case_id": case_id,
            "user_id": user_id,
            "version": version,
            "title": title,
            "content": content,
            "status": "draft",
            # Denormalized so the cross-case Appeals Center (list_appeals_for_user)
            # never needs a join with `cases` -- appeals generated from the
            # multi-domain assistant workflow don't create a real Case row,
            # only a synthetic case_id for internal state tracking.
            "document_type": document_type,
            "domain": domain,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._appeals[appeal["id"]] = appeal
        self.local.append("appeals", self._jsonable(appeal))
        await self.supabase.insert("appeals", self._jsonable(appeal))
        await self.add_event(case_id, {"actor": "agent", "event_type": "appeal_drafted", "title": f"Appeal draft v{version} created", "body": title})
        return appeal

    async def list_appeals(self, case_id: str) -> list[dict]:
        return [appeal for appeal in self._appeals.values() if appeal["case_id"] == case_id]

    async def list_appeals_for_user(self, user_id: str) -> list[dict]:
        appeals = [appeal for appeal in self._appeals.values() if appeal["user_id"] == user_id]
        return sorted(appeals, key=lambda a: a.get("created_at") or "", reverse=True)

    async def update_appeal_status(self, appeal_id: str, user_id: str, status: str) -> dict | None:
        appeal = self._appeals.get(appeal_id)
        if not appeal or appeal["user_id"] != user_id:
            return None
        appeal["status"] = status
        self.local.upsert("appeals", "id", self._jsonable(appeal))
        await self.supabase.upsert("appeals", self._jsonable(appeal), on_conflict="id")
        await self.add_event(appeal["case_id"], {"actor": "user", "event_type": "appeal_status_changed", "title": f"Appeal marked {status}", "body": appeal["title"]})
        return appeal

    async def upsert_knowledge_source(self, source: dict) -> dict:
        self._knowledge_sources[source["source_id"]] = source
        stored = self._jsonable(source)
        self.local.upsert("knowledge_sources", "source_id", stored)
        await self.supabase.upsert("knowledge_sources", stored, on_conflict="source_id")
        return source

    async def add_knowledge_chunks(self, source_id: str, chunks: list[dict]) -> int:
        stored_chunks: list[dict] = []
        supabase_records: list[dict] = []
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id") or str(uuid4())
            record = {"chunk_id": chunk_id, "source_id": source_id, **chunk}
            self._knowledge_chunks[chunk_id] = record
            stored = self._jsonable(record)
            stored_chunks.append(stored)
            supabase_records.append({key: value for key, value in stored.items() if key != "chunk_id"})
        self.local.append_many("knowledge_chunks", stored_chunks)
        await self.supabase.upsert_many("knowledge_chunks", supabase_records, on_conflict="source_id,chunk_index")
        return len(chunks)

    async def list_knowledge_sources(self, domain: Domain | None = None) -> list[dict]:
        rows = list(self._knowledge_sources.values())
        if domain:
            rows = [source for source in rows if source.get("domain") == domain.value]
        return rows

    async def list_knowledge_chunks(self, source_id: str | None = None, limit: int = 100) -> list[dict]:
        rows = list(self._knowledge_chunks.values())
        if source_id:
            rows = [chunk for chunk in rows if chunk.get("source_id") == source_id]
        return rows[:limit]


case_repository = CaseRepository()

