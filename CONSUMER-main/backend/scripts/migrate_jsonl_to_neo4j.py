"""
One-off migration: replay the local JSONL graph-store event log
(datasets/knowledge_graph/neo4j_fallback.jsonl) into a real Neo4j instance,
using the same typed upsert methods the app would have called if Neo4j had
been live all along (not raw Cypher against the file), so the resulting
graph shape matches exactly what Neo4jGraphStore produces in production.

Usage:
    Set NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD in the environment first --
    this always writes to whatever GRAPH_STORE_BACKEND=neo4j resolves to,
    regardless of the CURRENT backend setting.

    python scripts/migrate_jsonl_to_neo4j.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.knowledge_graph.jsonl_graph_store import JsonlGraphStore
from app.knowledge_graph.neo4j_graph_store import Neo4jGraphStore
from app.models.domain import Domain


async def main() -> None:
    jsonl_store = JsonlGraphStore()
    neo4j_store = Neo4jGraphStore()

    events = jsonl_store.iter_events()
    print(f"Replaying {len(events)} events from {jsonl_store.fallback_path} into Neo4j...")

    counts: dict[str, int] = {}
    skipped: dict[str, int] = {}
    for i, event in enumerate(events, 1):
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        try:
            if event_type == "case_graph":
                await neo4j_store.upsert_case_graph(payload.get("case", {}), payload.get("evidence"))
            elif event_type == "knowledge_document":
                await neo4j_store.upsert_knowledge_document(
                    Domain(payload["domain"]),
                    payload["document_id"],
                    payload["title"],
                    payload["source_path"],
                    payload.get("metadata", {}),
                )
            elif event_type == "citizen_case":
                await neo4j_store.upsert_citizen_case(
                    payload["user_id"],
                    Domain(payload["domain"]),
                    payload["case_id"],
                    payload.get("institution_name"),
                    payload["title"],
                )
            elif event_type in ("knowledge_entity", "knowledge_relationship"):
                await neo4j_store.add_event(event_type, payload)
            else:
                skipped[event_type] = skipped.get(event_type, 0) + 1
                continue
            counts[event_type] = counts.get(event_type, 0) + 1
        except Exception as exc:
            print(f"  [{i}/{len(events)}] FAILED {event_type}: {exc.__class__.__name__}: {exc}")
            continue
        if i % 100 == 0:
            print(f"  {i}/{len(events)} events replayed")

    print(f"\nDone. Migrated: {counts}")
    if skipped:
        print(f"Skipped (unknown event_type): {skipped}")


if __name__ == "__main__":
    asyncio.run(main())
