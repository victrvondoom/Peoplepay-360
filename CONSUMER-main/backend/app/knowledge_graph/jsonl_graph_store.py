from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.knowledge_graph.graph_store import GraphStore
from app.models.domain import Domain


class JsonlGraphStore(GraphStore):
    def __init__(self) -> None:
        self.fallback_path = Path("datasets") / "knowledge_graph" / "neo4j_fallback.jsonl"
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {"event_type": event_type, "payload": payload}
        with self.fallback_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    def _read_events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        if not self.fallback_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.fallback_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type is None or record.get("event_type") == event_type:
                events.append(record)
        return events

    async def add_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._append(event_type, payload)
        return {"event_type": event_type, "mode": "jsonl"}

    async def upsert_case_graph(self, case: dict, evidence: dict | None = None) -> dict[str, Any]:
        payload = {"case": self._jsonable(case), "evidence": self._jsonable(evidence or {})}
        self._append("case_graph", payload)
        return {"case_id": case["id"], "mode": "jsonl"}

    async def upsert_knowledge_document(
        self,
        domain: Domain,
        document_id: str,
        title: str,
        source_path: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "domain": domain.value,
            "document_id": document_id,
            "title": title,
            "source_path": source_path,
            "metadata": self._jsonable(metadata),
        }
        self._append("knowledge_document", payload)
        return {"document_id": document_id, "mode": "jsonl"}

    async def query_institution_pattern(self, domain: Domain, institution_name: str) -> list[dict[str, Any]]:
        prior_cases: list[dict[str, Any]] = []
        for event in self._read_events("case_graph"):
            case = event.get("payload", {}).get("case", {})
            case_domain = case.get("domain")
            domain_value = case_domain.value if hasattr(case_domain, "value") else case_domain
            if case.get("institution_name") == institution_name and domain_value == domain.value:
                prior_cases.append(case)
        if prior_cases:
            # Real substance from those prior cases (their titles/summaries),
            # not just a bare count -- a bare "N prior cases" number reads as
            # filler, and find_similar_cases() already surfaces the case
            # details separately, so this complements that with an aggregate
            # read of what keeps coming up against this specific institution.
            topics = list(dict.fromkeys(
                (case.get("title") or case.get("summary", ""))[:80]
                for case in prior_cases
                if case.get("title") or case.get("summary")
            ))
            topic_str = f" Recurring issues: {'; '.join(topics[:3])}." if topics else ""
            return [
                {
                    "pattern": f"{len(prior_cases)} prior case(s) logged against {institution_name} in this domain.{topic_str}",
                    "domain": domain.value,
                    "institution": institution_name,
                    "confidence": 0.7,
                }
            ]
        doc_count = sum(
            1
            for event in self._read_events("knowledge_document")
            if institution_name.lower()
            in str(event.get("payload", {}).get("metadata", {}).get("insurer_name", "")).lower()
        )
        if doc_count:
            return [
                {
                    "pattern": f"{doc_count} indexed policy/claim documents available for {institution_name}.",
                    "domain": domain.value,
                    "institution": institution_name,
                    "confidence": 0.74,
                }
            ]
        # Honest "nothing on file" signal instead of a fabricated pattern --
        # this used to always return a hardcoded health-insurance-specific
        # sentence ("Repeated medical necessity denials require...") no
        # matter what domain the case was actually in, which meant a
        # banking/telecom/airlines/etc. case with no institution history got
        # fed an unrelated, made-up claim dressed up as real graph
        # intelligence. An empty list is the truthful answer: no cross-case
        # pattern exists yet for this institution.
        return []

    async def find_similar_cases(self, domain: Domain, institution_name: str, limit: int = 5) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for event in self._read_events("case_graph"):
            case = event.get("payload", {}).get("case", {})
            case_domain = case.get("domain")
            domain_value = case_domain.value if hasattr(case_domain, "value") else case_domain
            if case.get("institution_name") == institution_name and domain_value == domain.value:
                cases.append({"case_id": case.get("id"), "title": case.get("title"), "summary": case.get("summary")})
        return cases[:limit]

    def health_check(self) -> dict[str, Any]:
        events = len(self._read_events())
        return {"status": "ready", "backend": "jsonl", "events": events, "path": str(self.fallback_path)}

    async def upsert_citizen_case(
        self,
        user_id: str,
        domain: Domain,
        case_id: str,
        institution_name: str | None,
        title: str,
    ) -> dict[str, Any]:
        payload = {
            "user_id": user_id,
            "domain": domain.value,
            "case_id": case_id,
            "institution_name": institution_name,
            "title": title,
        }
        self._append("citizen_case", payload)
        return {"user_id": user_id, "case_id": case_id, "mode": "jsonl"}

    async def get_citizen_profile(self, user_id: str) -> dict[str, Any]:
        by_domain: dict[str, dict[str, Any]] = {}
        for event in self._read_events("citizen_case"):
            payload = event.get("payload", {})
            if payload.get("user_id") != user_id:
                continue
            domain_value = payload.get("domain", "unknown")
            entry = by_domain.setdefault(domain_value, {"domain": domain_value, "cases": [], "institutions": set()})
            entry["cases"].append({"case_id": payload.get("case_id"), "title": payload.get("title")})
            if payload.get("institution_name"):
                entry["institutions"].add(payload["institution_name"])

        domains_summary = []
        for entry in by_domain.values():
            domains_summary.append({
                "domain": entry["domain"],
                "case_count": len(entry["cases"]),
                "cases": entry["cases"],
                "institutions": sorted(entry["institutions"]),
            })
        domains_summary.sort(key=lambda item: item["case_count"], reverse=True)

        return {
            "user_id": user_id,
            "domains_active_in": [entry["domain"] for entry in domains_summary],
            "total_cases": sum(entry["case_count"] for entry in domains_summary),
            "by_domain": domains_summary,
        }

    async def get_institution_radar(self, limit: int = 25) -> list[dict[str, Any]]:
        # Mirrors Neo4jGraphStore.get_institution_radar()'s coalescing of
        # both write paths' institution field -- case_graph events store it
        # on the case dict, citizen_case events store it directly.
        cases_by_key: dict[tuple[str, str], set[str]] = {}
        for event in self._read_events("case_graph"):
            case = event.get("payload", {}).get("case", {})
            institution = case.get("institution_name")
            domain = case.get("domain")
            domain_value = domain.value if hasattr(domain, "value") else domain
            case_id = case.get("id")
            if institution and institution != "Not specified" and domain_value and case_id:
                cases_by_key.setdefault((institution, domain_value), set()).add(case_id)
        for event in self._read_events("citizen_case"):
            payload = event.get("payload", {})
            institution = payload.get("institution_name")
            domain_value = payload.get("domain")
            case_id = payload.get("case_id")
            if institution and institution != "Not specified" and domain_value and case_id:
                cases_by_key.setdefault((institution, domain_value), set()).add(case_id)

        by_institution: dict[str, dict[str, set[str]]] = {}
        for (institution, domain_value), case_ids in cases_by_key.items():
            by_institution.setdefault(institution, {})[domain_value] = case_ids

        radar = [
            {
                "institution_name": institution,
                "total_cases": sum(len(ids) for ids in by_domain_ids.values()),
                "by_domain": sorted(
                    ({"domain": domain_value, "case_count": len(ids)} for domain_value, ids in by_domain_ids.items()),
                    key=lambda d: d["case_count"], reverse=True,
                ),
            }
            for institution, by_domain_ids in by_institution.items()
        ]
        radar.sort(key=lambda item: item["total_cases"], reverse=True)
        return radar[:limit]

    def iter_events(self) -> list[dict[str, Any]]:
        return self._read_events()

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, Domain):
            return value.value
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        return value
