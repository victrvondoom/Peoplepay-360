from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import get_settings
from app.knowledge_graph.graph_store import GraphStore
from app.models.domain import Domain


class Neo4jGraphStore(GraphStore):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._driver = None

    def _get_driver(self):
        if self._driver is not None:
            return self._driver
        if not self.settings.neo4j_password:
            raise RuntimeError("NEO4J_PASSWORD is required when GRAPH_STORE_BACKEND=neo4j")
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )
        self._driver.verify_connectivity()
        return self._driver

    async def add_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if event_type == "case_graph":
            return await self.upsert_case_graph(payload.get("case", {}), payload.get("evidence"))
        if event_type == "knowledge_entity":
            return await self.upsert_knowledge_entity(payload)
        if event_type == "knowledge_relationship":
            return await self.upsert_knowledge_relationship(payload)
        if event_type == "knowledge_document":
            return await self.upsert_knowledge_document(
                Domain(payload["domain"]),
                payload["document_id"],
                payload["title"],
                payload["source_path"],
                payload.get("metadata", {}),
            )
        return {"event_type": event_type, "mode": "neo4j"}

    async def upsert_knowledge_entity(self, payload: dict[str, Any]) -> dict[str, Any]:
        driver = self._get_driver()
        domain = payload.get("domain", "unknown")
        label = payload.get("label") or "Knowledge Entity"
        name = payload.get("name") or label
        safe_label = re.sub(r"[^a-zA-Z0-9]", "", label) or "KnowledgeEntity"
        query = f"""
        MERGE (n:KnowledgeEntity:{safe_label} {{domain: $domain, name: $name}})
          SET n.label = $label,
              n.updatedAt = datetime()
        RETURN n.name AS name
        """
        with driver.session() as session:
            session.run(query, domain=domain, name=name, label=label)
        return {"event_type": "knowledge_entity", "name": name, "mode": "neo4j"}

    async def upsert_knowledge_relationship(self, payload: dict[str, Any]) -> dict[str, Any]:
        driver = self._get_driver()
        domain = payload.get("domain", "unknown")
        source = payload.get("source")
        target = payload.get("target")
        relation = re.sub(r"[^a-zA-Z0-9_]", "_", str(payload.get("relation") or "RELATED_TO").upper())
        if not source or not target:
            return {"event_type": "knowledge_relationship", "mode": "neo4j", "skipped": True}
        query = f"""
        MERGE (a:KnowledgeEntity {{domain: $domain, name: $source}})
          SET a.updatedAt = datetime()
        MERGE (b:KnowledgeEntity {{domain: $domain, name: $target}})
          SET b.updatedAt = datetime()
        MERGE (a)-[r:{relation}]->(b)
          SET r.domain = $domain,
              r.updatedAt = datetime()
        RETURN type(r) AS relation
        """
        with driver.session() as session:
            session.run(query, domain=domain, source=source, target=target)
        return {"event_type": "knowledge_relationship", "source": source, "target": target, "relation": relation, "mode": "neo4j"}
    async def upsert_case_graph(self, case: dict, evidence: dict | None = None) -> dict[str, Any]:
        driver = self._get_driver()
        query = """
        MERGE (ins:Insurer {name: $institution})
        MERGE (c:Case {id: $case_id})
          SET c.title = $title,
              c.summary = $summary,
              c.domain = $domain,
              c.updatedAt = datetime()
        MERGE (c)-[:AGAINST]->(ins)
        WITH c
        OPTIONAL MATCH (c)-[:RESULTED_IN]->(old:Outcome)
        DELETE old
        RETURN c.id AS case_id
        """
        with driver.session() as session:
            session.run(
                query,
                case_id=case["id"],
                domain=case["domain"].value if hasattr(case["domain"], "value") else case["domain"],
                institution=case["institution_name"],
                title=case.get("title", ""),
                summary=case.get("summary", ""),
            )
        return {"case_id": case["id"], "mode": "neo4j"}

    async def upsert_knowledge_document(
        self,
        domain: Domain,
        document_id: str,
        title: str,
        source_path: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        driver = self._get_driver()
        insurer_name = metadata.get("insurer_name") or metadata.get("authority")
        category = metadata.get("category") or metadata.get("knowledge_type") or "policy_document"
        query = """
        MERGE (doc:PolicyDocument {id: $document_id})
          SET doc.title = $title,
              doc.sourcePath = $source_path,
              doc.category = $category,
              doc.domain = $domain,
              doc.metadataJson = $metadata,
              doc.updatedAt = datetime()
        """
        params: dict[str, Any] = {
            "document_id": document_id,
            "title": title,
            "source_path": source_path,
            "category": category,
            "domain": domain.value,
            "metadata": json.dumps(metadata, ensure_ascii=True),
        }
        if insurer_name:
            query += """
        MERGE (ins:Insurer {name: $insurer_name})
        MERGE (ins)-[:PUBLISHES]->(doc)
        """
            params["insurer_name"] = insurer_name
        query += " RETURN doc.id AS document_id"
        with driver.session() as session:
            session.run(query, **params)
        return {"document_id": document_id, "mode": "neo4j"}

    async def query_institution_pattern(self, domain: Domain, institution_name: str) -> list[dict[str, Any]]:
        driver = self._get_driver()
        query = """
        MATCH (ins:Insurer {name: $institution})<-[:AGAINST]-(c:Case {domain: $domain})
        OPTIONAL MATCH (c)-[:CITES]->(cl:Clause)<-[:CONTAINS]-(doc:PolicyDocument)<-[:PUBLISHES]-(ins)
        OPTIONAL MATCH (cl)-[:GOVERNED_BY]->(reg:Regulation)
        OPTIONAL MATCH (c)-[:RESULTED_IN]->(o:Outcome)
        WITH ins, count(DISTINCT c) AS case_count,
             collect(DISTINCT cl.title)[0..5] AS top_clauses,
             collect(DISTINCT o.status) AS outcomes
        RETURN case_count, top_clauses, outcomes
        """
        with driver.session() as session:
            result = session.run(query, institution=institution_name, domain=domain.value).single()
        if not result or not result["case_count"]:
            doc_query = """
            MATCH (ins:Insurer {name: $institution})-[:PUBLISHES]->(doc:PolicyDocument {domain: $domain})
            RETURN count(doc) AS docs
            """
            with driver.session() as session:
                doc_result = session.run(doc_query, institution=institution_name, domain=domain.value).single()
            docs = int(doc_result["docs"]) if doc_result else 0
            if docs:
                return [
                    {
                        "pattern": f"{docs} indexed policy documents published by {institution_name}.",
                        "domain": domain.value,
                        "institution": institution_name,
                        "confidence": 0.74,
                    }
                ]
            # Honest "nothing on file yet" -- an empty list, not a hardcoded
            # insurance-specific sentence ("cite insurer policy wording and
            # IRDAI regulations") that used to get returned for every domain
            # regardless of whether the case was actually about insurance.
            # Domain-appropriate citation guidance already lives in
            # DOMAIN_PROMPTS; this layer shouldn't duplicate or override it.
            return []
        outcomes = [item for item in (result["outcomes"] or []) if item]
        outcome_text = f" Outcomes observed: {', '.join(outcomes)}." if outcomes else ""
        clauses = [item for item in (result["top_clauses"] or []) if item]
        clause_text = f" Top cited clauses: {'; '.join(clauses)}." if clauses else ""
        return [
            {
                "pattern": f"{result['case_count']} prior cases against {institution_name}.{clause_text}{outcome_text}",
                "domain": domain.value,
                "institution": institution_name,
                "confidence": min(0.65 + int(result["case_count"]) * 0.05, 0.95),
            }
        ]

    async def find_similar_cases(self, domain: Domain, institution_name: str, limit: int = 5) -> list[dict[str, Any]]:
        driver = self._get_driver()
        query = """
        MATCH (ins:Insurer {name: $institution})<-[:AGAINST]-(c:Case {domain: $domain})
        RETURN c.id AS case_id, c.title AS title, c.summary AS summary
        ORDER BY c.updatedAt DESC
        LIMIT $limit
        """
        with driver.session() as session:
            rows = session.run(query, institution=institution_name, domain=domain.value, limit=limit)
            return [dict(row) for row in rows]

    def health_check(self) -> dict[str, Any]:
        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run("RETURN 1 AS ok").single()
            return {"status": "ready" if result else "degraded", "backend": "neo4j", "uri": self.settings.neo4j_uri}
        except Exception as exc:
            return {"status": "unreachable", "backend": "neo4j", "uri": self.settings.neo4j_uri, "error": str(exc)}

    async def upsert_citizen_case(
        self,
        user_id: str,
        domain: Domain,
        case_id: str,
        institution_name: str | None,
        title: str,
    ) -> dict[str, Any]:
        driver = self._get_driver()
        query = """
        MERGE (citizen:Citizen {id: $user_id})
        MERGE (d:Domain {name: $domain})
        MERGE (c:Case {id: $case_id})
          SET c.title = $title, c.domain = $domain, c.updatedAt = datetime()
        MERGE (citizen)-[:FILED]->(c)
        MERGE (citizen)-[:HAS_CASE_IN]->(d)
        MERGE (c)-[:IN_DOMAIN]->(d)
        WITH citizen, c
        FOREACH (_ IN CASE WHEN $institution IS NULL THEN [] ELSE [1] END |
            MERGE (inst:Institution {name: $institution})
            MERGE (c)-[:AGAINST_INSTITUTION]->(inst)
        )
        RETURN citizen.id AS user_id
        """
        with driver.session() as session:
            session.run(
                query,
                user_id=user_id,
                domain=domain.value,
                case_id=case_id,
                institution=institution_name,
                title=title,
            )
        return {"user_id": user_id, "case_id": case_id, "mode": "neo4j"}

    async def get_citizen_profile(self, user_id: str) -> dict[str, Any]:
        driver = self._get_driver()
        query = """
        MATCH (citizen:Citizen {id: $user_id})-[:FILED]->(c:Case)-[:IN_DOMAIN]->(d:Domain)
        OPTIONAL MATCH (c)-[:AGAINST_INSTITUTION]->(inst:Institution)
        RETURN d.name AS domain, c.id AS case_id, c.title AS title,
               collect(DISTINCT inst.name) AS institutions
        """
        with driver.session() as session:
            rows = list(session.run(query, user_id=user_id))

        by_domain: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = by_domain.setdefault(row["domain"], {"domain": row["domain"], "cases": [], "institutions": set()})
            entry["cases"].append({"case_id": row["case_id"], "title": row["title"]})
            entry["institutions"].update(name for name in row["institutions"] if name)

        domains_summary = [
            {
                "domain": entry["domain"],
                "case_count": len(entry["cases"]),
                "cases": entry["cases"],
                "institutions": sorted(entry["institutions"]),
            }
            for entry in by_domain.values()
        ]
        domains_summary.sort(key=lambda item: item["case_count"], reverse=True)

        return {
            "user_id": user_id,
            "domains_active_in": [entry["domain"] for entry in domains_summary],
            "total_cases": sum(entry["case_count"] for entry in domains_summary),
            "by_domain": domains_summary,
        }

    async def get_institution_radar(self, limit: int = 25) -> list[dict[str, Any]]:
        driver = self._get_driver()
        # Case records link to their institution through one of two node
        # shapes depending on which write path created them --
        # upsert_case_graph() writes (:Case)-[:AGAINST]->(:Insurer), while
        # upsert_citizen_case() writes (:Case)-[:AGAINST_INSTITUTION]->
        # (:Institution). Neither alone is the complete picture; coalescing
        # both into one institution_name is what makes this aggregate real
        # instead of silently undercounting whichever path a case didn't
        # also go through.
        query = """
        MATCH (c:Case)
        OPTIONAL MATCH (c)-[:AGAINST]->(ins:Insurer)
        OPTIONAL MATCH (c)-[:AGAINST_INSTITUTION]->(inst:Institution)
        WITH c, coalesce(ins.name, inst.name) AS institution_name
        // "Not specified" is the Document Vault's placeholder institution
        // name (see get_or_create_vault_case) for uploads not tied to a
        // real dispute -- neither that nor an empty string is a real
        // institution to rank.
        WHERE institution_name IS NOT NULL AND trim(institution_name) <> "" AND institution_name <> "Not specified"
        WITH institution_name, c.domain AS domain, count(DISTINCT c) AS domain_case_count
        WITH institution_name, collect({domain: domain, case_count: domain_case_count}) AS by_domain,
             sum(domain_case_count) AS total_cases
        RETURN institution_name, total_cases, by_domain
        ORDER BY total_cases DESC
        LIMIT $limit
        """
        with driver.session() as session:
            rows = list(session.run(query, limit=limit))
        return [
            {
                "institution_name": row["institution_name"],
                "total_cases": int(row["total_cases"]),
                "by_domain": sorted(row["by_domain"], key=lambda d: d["case_count"], reverse=True),
            }
            for row in rows
        ]


